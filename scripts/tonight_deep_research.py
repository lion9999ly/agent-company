"""
@description: JDM供应商选型深度研究 - 完整研究报告生成（五层管道架构 v2）
@dependencies: src.utils.model_gateway, src.tools.knowledge_base, src.tools.tool_registry, scripts.meta_capability
@last_modified: 2026-03-31
"""
import json
import time
import re
import sys
import yaml
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.model_gateway import get_model_gateway, call_for_search, call_for_refine
from src.tools.knowledge_base import add_knowledge, get_knowledge_stats, KB_ROOT
from src.tools.tool_registry import ToolRegistry
from src.utils.progress_heartbeat import ProgressHeartbeat
from scripts.meta_capability import (
    CAPABILITY_GAP_INSTRUCTION,
    scan_capability_gaps,
    resolve_all_gaps,
    generate_evolution_report,
)

registry = ToolRegistry()
gateway = get_model_gateway()


# ============================================================
# 并发控制: 按 provider 限制并发数
# ============================================================
PROVIDER_SEMAPHORES = {
    "o3": threading.Semaphore(3),        # o3 慢，3 并发
    "doubao": threading.Semaphore(8),    # 豆包快，8 并发
    "flash": threading.Semaphore(8),     # Flash 提炼，8 并发
    "gemini_pro": threading.Semaphore(3),# 有限额，保守
    "gpt54": threading.Semaphore(4),     # 成本高
    "gpt4o": threading.Semaphore(4),     # 通用
}


def _get_sem_key(model_name: str) -> str:
    """模型名 → 信号量 key"""
    if "o3" in model_name and "deep" in model_name:
        return "o3"
    elif "doubao" in model_name:
        return "doubao"
    elif "flash" in model_name:
        return "flash"
    elif "gemini" in model_name and "pro" in model_name:
        return "gemini_pro"
    elif "gpt_5_4" in model_name or "gpt-5.4" in model_name:
        return "gpt54"
    elif "4o" in model_name:
        return "gpt4o"
    return "gpt54"  # 默认保守


# ============================================================
# 降级映射表
# ============================================================
FALLBACK_MAP = {
    "gpt_5_4": "gpt_4o_norway",
    "doubao_seed_pro": "doubao_seed_lite",
    "gemini_3_1_pro": "gemini_3_pro",
    "gemini_3_pro": "gemini_2_5_pro",
    "o3_deep_research": "gpt_5_4",  # o3 失败降级到 gpt-5.4
}


# ============================================================
# 模型路由辅助函数 —— 深度研究专用模型分层配置
# ============================================================
# 注意：不使用 Claude 系列模型

def _get_model_for_role(role: str) -> str:
    """深度研究 v2: 各角色模型分配

    原则:
    - CTO/CPO: gpt_5_4（最强推理）→ gpt_4o_norway
    - CMO: doubao_seed_pro（中文互联网）→ doubao_seed_lite
    - CDO: gemini_3_1_pro（多模态）→ gemini_3_pro
    """
    role_model_map = {
        "CTO": "gpt_5_4",
        "CMO": "doubao_seed_pro",
        "CDO": "gemini_3_1_pro",
        "CPO": "gpt_5_4",
    }
    return role_model_map.get(role.upper(), "gpt_5_4")


def _get_model_for_task(task_type: str) -> str:
    """深度研究 v2: 各环节模型分配

    分层:
    - 搜索: o3_deep_research + doubao_seed_pro（并行）
    - 提炼: gemini_2_5_flash（便宜无限额）
    - 整合: gpt_5_4（最强推理）
    - Critic: gemini_3_1_pro（独立于 synthesis 模型）
    """
    task_model_map = {
        "discovery": "gemini_2_5_flash",
        "query_generation": "gemini_2_5_flash",
        "data_extraction": "gemini_2_5_flash",    # Layer 2 提炼
        "role_assign": "gemini_2_5_flash",
        "synthesis": "gpt_5_4",                    # Layer 4
        "re_synthesis": "gpt_5_4",
        "final_synthesis": "gpt_5_4",
        "critic_challenge": "gemini_3_1_pro",      # Layer 5
        "consistency_check": "gemini_3_1_pro",
        "knowledge_extract": "gemini_2_5_flash",
        "fix": "gemini_2_5_pro",
        "cdo_fix": "gemini_2_5_pro",
        "chinese_search": "doubao_seed_pro",
        "deep_research_search": "o3_deep_research",
    }
    return task_model_map.get(task_type, "gpt_5_4")


def _call_model(model_name: str, prompt: str, system_prompt: str = None, task_type: str = "general") -> dict:
    """统一模型调用入口，自动降级"""
    result = gateway.call(model_name, prompt, system_prompt, task_type)
    if result.get("success"):
        return result

    # 自动降级
    fallback = FALLBACK_MAP.get(model_name)
    if fallback and fallback in gateway.models:
        print(f"  [Degrade] {model_name} failed, trying {fallback}")
        result2 = gateway.call(fallback, prompt, system_prompt, task_type)
        result2["degraded_from"] = model_name
        return result2

    return result


def _call_with_backoff(model_name: str, prompt: str, system_prompt: str = None,
                        task_type: str = "general", max_retries: int = 3) -> dict:
    """带限流退避的模型调用（用于 Layer 1/2/3 并发场景）"""
    sem_key = _get_sem_key(model_name)
    sem = PROVIDER_SEMAPHORES.get(sem_key)

    result = None
    for attempt in range(max_retries + 1):
        if sem:
            sem.acquire()
        try:
            result = _call_model(model_name, prompt, system_prompt, task_type)

            # 检查限流
            error = result.get("error", "")
            is_rate_limit = ("429" in str(error) or "rate" in str(error).lower()
                            or "quota" in str(error).lower()
                            or "RESOURCE_EXHAUSTED" in str(error))

            if is_rate_limit and attempt < max_retries:
                wait = (2 ** attempt) * 10  # 10s, 20s, 40s
                print(f"  [RateLimit] {model_name} attempt {attempt+1}, "
                      f"waiting {wait}s...")
                time.sleep(wait)
                continue

            return result
        finally:
            if sem:
                sem.release()

    return result  # 最后一次的结果


# ============================================================
# 专家框架匹配与知识库检索
# ============================================================

def _match_expert_framework(task_goal: str, task_title: str) -> dict:
    """根据任务关键词匹配专家框架"""
    config_path = Path(__file__).parent.parent / "src" / "config" / "expert_frameworks.yaml"
    if not config_path.exists():
        return {}

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            frameworks = yaml.safe_load(f)
    except:
        return {}

    combined_text = task_goal + " " + task_title

    best_match = None
    best_score = 0

    for name, fw in frameworks.items():
        if name == 'general_research':
            continue
        score = sum(1 for kw in fw.get('match_keywords', []) if kw in combined_text)
        if score > best_score:
            best_score = score
            best_match = name

    if best_match and best_score > 0:
        return frameworks[best_match]
    return frameworks.get('general_research', {})


def _get_kb_context_enhanced(task_goal: str, task_title: str) -> str:
    """从知识库检索与任务相关的高质量知识条目（增强版）"""
    queries = []
    # 从任务目标提取关键词
    # 提取中文关键词
    keywords = re.findall(r'[\u4e00-\u9fff]{2,6}', task_goal)[:10]
    # 提取英文技术词
    tech_terms = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*|[A-Z]{2,}', task_goal)[:5]

    queries = keywords[:5] + tech_terms[:3] + [task_title]

    all_entries = []
    seen_ids = set()

    for q in queries:
        # 从 KB_ROOT 目录检索
        for f in KB_ROOT.rglob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                content = data.get("content", "")
                t = data.get("title", "")
                tags = data.get("tags", [])
                confidence = data.get("confidence", "")

                # 关键词匹配
                if q.lower() in t.lower() or q.lower() in content[:500].lower():
                    entry_id = str(f)
                    if entry_id not in seen_ids:
                        seen_ids.add(entry_id)
                        all_entries.append({
                            "title": t,
                            "content": content[:500],
                            "confidence": confidence,
                            "tags": tags
                        })
            except:
                continue

    # 按 confidence 排序，取 top 15
    conf_order = {"authoritative": 3, "high": 2, "medium": 1, "low": 0}
    all_entries.sort(key=lambda x: conf_order.get(x.get('confidence', ''), 0), reverse=True)
    top_entries = all_entries[:15]

    if not top_entries:
        return ""

    result = ""
    for entry in top_entries:
        result += f"\n[KB] {entry['title']}: {entry['content'][:300]}"

    return result[:3000]


# ============================================================
# 结构化数据提取 Schema
# ============================================================

OPTICAL_BENCHMARK_SCHEMA = {
    "product": "string - 产品名称",
    "manufacturer": "string - 制造商",
    "product_type": "string - helmet_integrated / clip_on / smartglasses",
    "display_tech": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "fov_diagonal_deg": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "fov_horizontal_deg": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "resolution": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "brightness_panel_nits": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "brightness_eye_nits": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "eye_box_mm": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "virtual_image_distance_m": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "battery_hours": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "weight_g": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "price_usd": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "display_position": {"value": "string|null - right_eye/left_eye/binocular/visor", "source": "string", "confidence": "high|medium|low"},
    "status": "string - on_sale / announced / prototype / discontinued",
    "notable_issues": "string|null - 已知问题或用户投诉",
    "data_gaps": ["string - 哪些参数搜不到"]
}

LAYOUT_ANALYSIS_SCHEMA = {
    "product": "string",
    "hud_position": {"value": "string|null - 描述显示区域在视野中的位置", "source": "string", "confidence": "high|medium|low"},
    "info_layout": {"value": "string|null - 全屏/分区/单角/多角/底部条", "source": "string", "confidence": "high|medium|low"},
    "simultaneous_elements": {"value": "number|null - 同时显示最多几个信息元素", "source": "string", "confidence": "high|medium|low"},
    "priority_mechanism": {"value": "string|null - 信息优先级切换方式", "source": "string", "confidence": "high|medium|low"},
    "direction_indication": {"value": "string|null - 是否支持方向指示（预警方向）", "source": "string", "confidence": "high|medium|low"}
}

HARDWARE_LAYOUT_SCHEMA = {
    "product": "string",
    "button_count": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "button_position": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "battery_position": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "battery_capacity_mah": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "camera_position": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "camera_specs": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "total_weight_g": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "charging_port": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "led_light_position": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "certification": {"value": "string|null", "source": "string", "confidence": "high|medium|low"}
}

GENERAL_SCHEMA = {
    "topic": "string",
    "key_findings": [{"finding": "string", "source": "string", "confidence": "high|medium|low"}],
    "data_gaps": ["string"]
}


def _extract_structured_data(raw_text: str, task_type: str, topic: str) -> dict:
    """从搜索结果中提取结构化数据点"""
    # 根据任务类型选择提取 schema
    if "光学" in task_type or "optics" in task_type.lower() or "对标" in task_type:
        schema = OPTICAL_BENCHMARK_SCHEMA
    elif "布局" in task_type or "layout" in task_type.lower():
        schema = LAYOUT_ANALYSIS_SCHEMA
    elif "硬件" in task_type or "hardware" in task_type.lower():
        schema = HARDWARE_LAYOUT_SCHEMA
    else:
        schema = GENERAL_SCHEMA

    prompt = f"""从以下搜索结果中提取结构化数据。

提取规则：
1. 只提取搜索结果中明确包含的数据，不要推测
2. 搜不到的字段填 null
3. 每个有值的字段必须附 source（URL 或文章标题）
4. confidence: high=官方spec/实测数据, medium=官方宣称/评测引用, low=推算/间接推断

Schema:
{json.dumps(schema, ensure_ascii=False, indent=2)}

搜索主题: {topic}
搜索结果:
{raw_text[:4000]}

只输出 JSON，不要其他内容。"""

    result = _call_model(_get_model_for_task("data_extraction"), prompt, task_type="data_extraction")

    if result.get("success"):
        try:
            resp = result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            return json.loads(resp)
        except:
            return None
    return None


def _generate_targeted_queries(task_spec_text: str, base_queries: list) -> list:
    """从任务 spec 中提取竞品名和参数字段，生成精准搜索词"""
    prompt = f"""分析以下研究任务规格书，提取出：
1. 所有需要对标的具体产品/竞品名称
2. 需要收集的具体参数字段

然后为每个产品生成 2-3 个精准的搜索查询，每个查询聚焦于该产品的具体参数。

任务规格书（节选）：
{task_spec_text[:3000]}

输出格式（JSON）：
{{
  "products": ["产品1", "产品2", ...],
  "params": ["参数1", "参数2", ...],
  "targeted_queries": [
    "产品1 参数1 参数2 specs",
    "产品2 参数1 参数2 review",
    ...
  ]
}}

只输出 JSON，不要其他内容。"""

    result = _call_model(_get_model_for_task("query_generation"), prompt, task_type="query_generation")

    if result.get("success"):
        try:
            resp = result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            data = json.loads(resp)
            targeted = data.get("targeted_queries", [])
            # targeted_queries 优先执行，base_queries 作为补充
            return targeted + base_queries
        except:
            return base_queries
    return base_queries


def _run_expert_analysis_in_slices(role: str, structured_data_list: list, system_prompt: str,
                                    user_prompt_template: str, model_name: str) -> list:
    """将结构化数据分组，每组独立让专家模型处理"""
    if not structured_data_list:
        return []

    # 按产品类型分组
    groups = {}
    for item in structured_data_list:
        product_type = item.get('product_type', item.get('topic', 'general'))
        if product_type not in groups:
            groups[product_type] = []
        groups[product_type].append(item)

    # 如果分组太少（<2），按数量均分
    if len(groups) <= 1:
        items = list(structured_data_list)
        mid = len(items) // 2
        if mid > 0:
            groups = {"group_1": items[:mid], "group_2": items[mid:]}
        else:
            groups = {"group_1": items}

    partial_outputs = []
    for group_name, group_items in groups.items():
        group_data = json.dumps(group_items, ensure_ascii=False, indent=2)

        user_prompt = user_prompt_template + f"""

## 本轮分析的数据（{group_name}，共 {len(group_items)} 条）
{group_data}

请只针对这批数据给出分析。其他批次由同一流程的其他轮次处理，最后会统一整合。"""

        result = _call_model(model_name, user_prompt, system_prompt, task_type=f"deep_research_{role.lower()}")
        if result.get("success"):
            partial_outputs.append({
                "group": group_name,
                "output": result["response"],
                "items_count": len(group_items)
            })
            print(f"  [{role} {group_name}] {len(result['response'])} chars")

    return partial_outputs

# ==========================================
# 三原则：所有 Agent 必须遵循的思维准则
# ==========================================
THINKING_PRINCIPLES = """
## 思维准则（所有分析必须遵循）

1. **第一性原理**：拒绝经验主义和路径盲从。不要假设目标已清楚，若目标模糊，先停下来澄清。从原始需求和本质问题出发，若路径不是最优，直接建议更短、更低成本的办法。

2. **奥卡姆剃刀**：如无必要，勿增实体。暴力删除所有不影响核心交付的冗余。多余的功能、多余的步骤、多余的复杂度，都要砍。

3. **苏格拉底追问**：对每个方案进行连续追问——
   - 这个方案解决的是真正的问题，还是一个 XY 问题？
   - 当前选择的路径有什么弊端？
   - 有没有更优雅、成本更低的替代方案？
   - 如果这个方案失败，最可能的原因是什么？
"""

REPORT_DIR = Path(__file__).parent.parent / ".ai-state" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# 5 个深度研究任务
RESEARCH_TASKS = [
    {
        "id": "goertek_profile",
        "title": "歌尔股份完整画像",
        "goal": "回答：歌尔做智能头盔JDM的核心能力、已有客户案例、产能规模、大致报价水平、优势和风险",
        "searches": [
            "Goertek smart wearable ODM JDM capability 2025 2026 annual report",
            "歌尔股份 2025年报 智能穿戴 营收 客户",
            "Goertek Meta Ray-Ban smart glasses ODM manufacturing details",
            "歌尔 Alpha Labs 智能眼镜 研发能力 团队规模",
            "Goertek XR headset production capacity Weifang factory",
            "歌尔 智能穿戴 代工报价 NRE 模具费 单价",
            "Goertek smart glasses helmet acoustic optical module capability",
            "歌尔股份 竞争优势 劣势 风险 分析师报告 2025",
        ]
    },
    {
        "id": "alternative_jdm",
        "title": "替代JDM供应商对比",
        "goal": "回答：除歌尔外还有哪些供应商能做智能头盔JDM？各自的能力、客户、规模、报价水平如何？",
        "searches": [
            # 发现层：先让搜索引擎告诉我们有哪些供应商
            "smart wearable device JDM ODM supplier list 2026 China",
            "智能穿戴 JDM ODM 供应商 完整名单 龙旗 瑞声 歌尔 立讯",
            # 已知大厂
            "Luxshare Precision smart wearable ODM capability customer 2026",
            "立讯精密 智能穿戴 代工 客户 苹果 Meta 产能 报价",
            "BYD Electronics smart device ODM wearable helmet 2026",
            "Longcheer 龙旗控股 智能穿戴 ODM JDM 能力 客户 2026",
            "AAC Technologies 瑞声科技 声学 光学 触觉 智能穿戴 2026",
            "Flex Jabil smart wearable contract manufacturing capability 2026",
            "Pegatron Compal Inventec smart wearable ODM 2026",
            "深圳 东莞 智能头盔 中小型方案商 ODM 案例 2026",
        ]
    },
    {
        "id": "optical_suppliers",
        "title": "光学方案商深度对比",
        "goal": "回答：HUD/AR显示用什么光学方案？每种方案的供应商、参数、成本、成熟度如何？推荐哪个？",
        "searches": [
            "AR HUD optical engine comparison waveguide birdbath freeform prism 2026",
            "Lumus waveguide supplier pricing motorcycle helmet HUD",
            "DigiLens waveguide smart glasses cost volume production 2026",
            "珑璟光电 灵犀微光 谷东科技 光波导 参数 价格 对比",
            "Micro OLED display Sony JBD BOE Kopin comparison specs price 2026",
            "BirdBath optical solution smart helmet HUD cost weight analysis",
            "motorcycle helmet HUD optical module supplier BOM cost breakdown",
            "光学模组 良率 交期 最小起订量 MOQ 供应商 2026",
        ]
    },
    {
        "id": "audio_camera_suppliers",
        "title": "声学与摄像头方案商对比",
        "goal": "回答：头盔用什么扬声器/麦克风/摄像头？每种方案的供应商、参数、成本对比？",
        "searches": [
            "骨传导扬声器 供应商 韶音 歌尔 瑞声 参数 价格 对比 2026",
            "MEMS microphone Knowles InvenSense Goertek specs price comparison",
            "ANC active noise cancellation chipset BES2700 QCC5181 comparison wearable",
            "微型摄像头 模组 OmniVision Sony IMX 舜宇 丘钛 specs comparison",
            "smart helmet speaker driver waterproof IP67 supplier",
            "helmet intercom microphone wind noise cancellation solution 2026",
            "AAC Technologies acoustic module smart glasses helmet speaker microphone specs",
            "瑞声科技 声学模组 智能眼镜 骨传导 参数 价格 2026",
        ]
    },
    {
        "id": "why_goertek",
        "title": "综合对比：为什么选歌尔（或为什么不选）",
        "goal": "基于前4份研究，给出歌尔 vs 替代方案的综合评估。明确回答：选歌尔的理由、风险、备选方案",
        "searches": [
            "Goertek vs Luxshare smart wearable ODM comparison advantage disadvantage",
            "歌尔 vs 立讯 vs 比亚迪电子 智能穿戴 综合对比 选型建议",
            "smart helmet ODM supplier selection criteria evaluation framework",
            "智能穿戴 JDM 供应商 选型 决策矩阵 权重",
            "Goertek vs AAC Technologies vs Luxshare smart wearable comparison",
            "歌尔 vs 瑞声 vs 龙旗 vs 立讯 智能穿戴 ODM 综合对比",
        ]
    }
]


CRITIC_FEW_SHOT = """
## 挑战质量对标（严格学习这个标准）

❌ 差的 P0（实际应为 P2，没有反证数据）:
"歌尔的产能数据可能不够准确，建议进一步核实。"
→ 无具体反证数据，只是泛泛质疑。降为 P2。

✅ 好的 P0（有反证数据，直接影响决策）:
{
  "issue": "报告结论'歌尔产能不足以独家供货（500万台/年）'可能已过时",
  "evidence": "Layer 2 数据: Goertek Weifang 二期 2025Q3 投产（source: 歌尔2025半年报, confidence: high），实际产能可能已达 800万台/年",
  "fix_required": "用最新产能数据重新评估独家供货可行性"
}
→ 为什么是 P0：产能数据错误会推翻"需要双供应商"的结论，直接影响选型决策。

❌ 差的 P0（不影响决策方向，应降为 P1）:
"BOM 成本估算中，OLED 面板价格引用的是 Q1 数据，Q2 可能有 5% 波动。"
→ 5% 波动不改变 OLED vs Micro LED 的成本对比方向。降为 P1。

✅ 好的 P1（有依据，标记即可）:
{
  "issue": "声学方案对比缺少风噪实测数据，当前结论基于厂商标称值",
  "evidence": "Layer 2 中所有扬声器参数的 confidence 均为 medium（厂商标称）"
}

✅ P2 示例:
{
  "issue": "如能补充 Cardo Packtalk 的拆机 BOM 数据，成本对比会更有说服力"
}
"""


def _run_critic_challenge(report: str, goal: str, agent_outputs: dict,
                          structured_data: str = "",
                          progress_callback=None,
                          task_title: str = "") -> str:
    """Layer 5: Critic 五维挑战

    改进:
    1. 分级: P0（阻断）/ P1（改进）/ P2（备注）
    2. 决策锚定: 挑战标准锚定到具体决策
    3. 数据说话: P0 必须引用 Layer 2 数据
    4. 对标校准: few-shot 示例
    5. 能力验证: 元能力层集成
    """
    if len(report) < 500:
        print("  [Critic] 报告太短，跳过")
        return report

    print("  [L5] 开始 Critic 挑战...")

    # === 构建 prompt ===

    # 决策锚定
    decision_anchor = (
        f"\n## 决策锚定\n"
        f"这份报告要支撑的核心决策是：{goal[:300]}\n\n"
        f"P0 判定标准：报告中的某个错误会导致这个决策做错 → P0。\n"
        f"某个估算偏差 10% 以内但不改变结论方向 → P1。\n"
        f"'有了更好但没有也行' → P2。\n"
        f"严格按此标准分级。P0 应该很少（0-2 个才正常）。\n"
    )

    # Layer 2 数据引用
    data_section = ""
    if structured_data:
        data_section = (
            f"\n## 原始结构化数据（用于交叉验证和引用）\n"
            f"以下是 Layer 2 提炼的结构化数据点，每个字段附有 source 和 confidence。\n"
            f"P0 挑战必须引用这些数据中的具体数据点作为反证。\n"
            f"找不到具体反证 → 该挑战最多 P1。\n\n"
            f"{structured_data[:4000]}\n"
        )

    # 能力缺口标记指引（元能力层集成）
    capability_instruction = ""
    try:
        from scripts.meta_capability import CAPABILITY_GAP_INSTRUCTION
        capability_instruction = CAPABILITY_GAP_INSTRUCTION
    except ImportError:
        pass

    # 尝试使用进化版 few-shot（基于人工标注），如果没有就用默认
    few_shot_to_use = CRITIC_FEW_SHOT
    try:
        from scripts.critic_calibration import get_evolved_few_shot
        evolved_few_shot = get_evolved_few_shot()
        if evolved_few_shot:
            few_shot_to_use = evolved_few_shot
            print("  [Critic] 使用进化版 few-shot 示例")
    except ImportError:
        pass

    critic_prompt = (
        f"你是独立审查员。你的职责不是打分，而是找出会导致决策失误的致命问题。\n\n"
        f"## 任务目标\n{goal}\n"
        f"{decision_anchor}\n"
        f"## 报告（{len(report)}字）\n{report[:8000]}\n"
        f"{data_section}\n"
        f"{few_shot_to_use}\n\n"
        f"## 挑战规则（强制）\n"
        f"1. 每个 P0 必须引用 Layer 2 数据中的具体数据点作为反证。\n"
        f"   格式: \"Layer 2 数据显示 [产品X] 的 [参数Y] 为 [值Z]"
        f"（source: [来源], confidence: [级别]），但报告结论为 [矛盾内容]。\"\n"
        f"2. 找不到具体反证数据点 → 最多 P1，不能是 P0。\n"
        f"3. \"建议进一步调研\"、\"建议加强分析\"等无反证表述 → P2 或不输出。\n"
        f"4. P0 超过 2 个时，重新检查是否真的每个都会导致决策做错。\n\n"
        f"{capability_instruction}\n\n"
        f"## 输出格式（严格 JSON）\n"
        f'{{\n'
        f'  "p0_blocking": [\n'
        f'    {{"issue": "结论与数据矛盾的具体描述",\n'
        f'     "evidence": "引用 Layer 2 具体数据点",\n'
        f'     "fix_required": "需要修正什么"}}\n'
        f'  ],\n'
        f'  "p1_improvement": [\n'
        f'    {{"issue": "可改进但不影响结论", "evidence": "数据来源"}}\n'
        f'  ],\n'
        f'  "p2_note": [\n'
        f'    {{"issue": "建议未来补充的方向"}}\n'
        f'  ],\n'
        f'  "overall": "PASS 或 NEEDS_FIX"\n'
        f'}}\n\n'
        f"判定: p0_blocking 非空 → NEEDS_FIX，否则 → PASS。\n"
        f"只输出 JSON。"
    )

    critic_result = _call_model(
        _get_model_for_task("critic_challenge"), critic_prompt,
        "你是独立审查员。只输出 JSON。", "critic_review"
    )

    if not critic_result.get("success"):
        print(f"  [Critic] 调用失败: {critic_result.get('error', '')[:100]}")
        return report

    # === 解析分级结果 ===
    try:
        resp = critic_result["response"].strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        critic_data = json.loads(resp)

        p0_list = critic_data.get("p0_blocking", [])
        p1_list = critic_data.get("p1_improvement", [])
        p2_list = critic_data.get("p2_note", [])

        print(f"  [Critic] P0: {len(p0_list)}, P1: {len(p1_list)}, P2: {len(p2_list)}")

        needs_fix = len(p0_list) > 0

        if needs_fix:
            print(f"  [Critic] NEEDS_FIX: {len(p0_list)} 个 P0 挑战")
            if progress_callback:
                progress_callback(f"  Critic: {len(p0_list)} P0 challenges")
        else:
            print(f"  [Critic] PASS (P1: {len(p1_list)}, P2: {len(p2_list)})")

    except Exception as e:
        print(f"  [Critic] 解析失败: {e}")
        report += f"\n\n---\n## Critic Review\n{critic_result['response'][:1000]}"
        return report

    # === 元能力层: Critic 缺口扫描 ===
    try:
        from scripts.meta_capability import scan_capability_gaps, resolve_capability_gap
        # 设置飞书回调（用于工具注册通知）
        resolve_capability_gap._feishu_callback = progress_callback

        critic_gaps = scan_capability_gaps(critic_result.get("response", ""))
        resolved_tools = []
        if critic_gaps:
            print(f"  [Meta-Critic] 发现 {len(critic_gaps)} 个验证能力缺口")
            for gap in critic_gaps[:2]:
                result = resolve_capability_gap(gap, gateway)
                if result.get("success"):
                    resolved_tools.append(result)

            # 补齐工具后重新验证 P0
            if resolved_tools and p0_list:
                tool_info = "\n".join([
                    f"[新增工具] {t['tool_name']}: {t['invoke']}"
                    for t in resolved_tools
                ])
                reverify_prompt = (
                    f"你之前提出了以下 P0 挑战但缺乏验证工具。\n"
                    f"现在系统已补齐以下工具:\n{tool_info}\n\n"
                    f"原始 P0 挑战:\n"
                    f"{json.dumps(p0_list, ensure_ascii=False, indent=2)}\n\n"
                    f"请用新工具重新验证每个 P0：\n"
                    f"- 确认 P0 成立 → 保留\n"
                    f"- 发现 P0 不成立 → 降级为 P1 或 P2\n"
                    f"- 发现新问题 → 补充\n\n"
                    f"输出更新后的 p0_blocking JSON 数组。只输出 JSON。"
                )
                reverify = _call_model(
                    _get_model_for_task("critic_challenge"),
                    reverify_prompt, "重新验证 P0 挑战。只输出 JSON。",
                    "critic_reverify"
                )
                if reverify.get("success"):
                    try:
                        r = reverify["response"].strip()
                        r = re.sub(r'^```json\s*', '', r)
                        r = re.sub(r'\s*```$', '', r)
                        updated_p0 = json.loads(r)
                        if isinstance(updated_p0, list):
                            print(f"  [Meta-Critic] P0 重验证: {len(p0_list)} → {len(updated_p0)}")
                            p0_list = updated_p0
                            needs_fix = len(p0_list) > 0
                    except:
                        pass
    except ImportError:
        pass  # 元能力层未安装，跳过

    # === P0 挑战回应循环（仅 P0 触发）===
    if needs_fix and p0_list:
        challenge_responses = []

        for i, p0 in enumerate(p0_list[:3]):
            challenge_text = (
                f"P0 挑战: {p0.get('issue', '')}\n"
                f"反证: {p0.get('evidence', '')}\n"
                f"要求修正: {p0.get('fix_required', '')}"
            )

            # 判断是否需要额外搜索
            needs_search = any(kw in challenge_text for kw in
                             ["数据", "证据", "来源", "补充", "最新", "更新"])
            extra_data = ""
            if needs_search:
                kw_result = _call_model("gemini_2_5_flash",
                    f"从以下挑战中提取 1-2 个搜索关键词:\n{challenge_text}\n只输出关键词，空格分隔",
                    task_type="query_generation")
                if kw_result.get("success"):
                    extra_query = kw_result["response"].strip()
                    if extra_query:
                        search_result = registry.call("tavily_search", extra_query)
                        if search_result.get("success") and len(search_result.get("data", "")) > 100:
                            extra_data = f"\n\n## 补充搜索结果\n{search_result['data'][:2000]}"

            # 让主角色回应
            primary_role = list(agent_outputs.keys())[0] if agent_outputs else "CTO"
            response_model = _get_model_for_role(primary_role)
            response_result = _call_model(response_model,
                f"Critic 对你的分析提出了 P0 级挑战（会导致决策失误的问题）:\n\n"
                f"{challenge_text}\n{extra_data}\n\n"
                f"请直接回应。如果 Critic 说得对，承认并给出修正后的结论。"
                f"如果不对，用数据反驳。",
                task_type=f"challenge_response_{i}")

            if response_result.get("success"):
                challenge_responses.append({
                    "p0": p0,
                    "response": response_result["response"],
                    "extra_search": bool(extra_data)
                })
                print(f"  [P0 Challenge {i+1}] responded")

        # 最终重整合
        if challenge_responses:
            dialogue = ""
            for r in challenge_responses:
                dialogue += (
                    f"\n[P0 挑战] {r['p0'].get('issue', '')}\n"
                    f"[反证] {r['p0'].get('evidence', '')}\n"
                    f"[回应] {r['response']}\n"
                )

            final_result = _call_model(
                _get_model_for_task("final_synthesis"),
                f"以下是研究报告经过 Critic P0 挑战后的完整对话:\n\n"
                f"## 初始报告\n{report[:6000]}\n\n"
                f"## P0 挑战与回应\n{dialogue}\n\n"
                f"请输出最终版报告:\n"
                f"1. P0 挑战中被证实的问题必须修正\n"
                f"2. 补充的新数据必须整合\n"
                f"3. 保持决策支撑格式\n"
                f"4. 末尾添加 'Critic 挑战记录' 小节\n\n"
                f"任务目标: {goal}",
                task_type="final_synthesis"
            )
            if final_result.get("success"):
                report = final_result["response"]
                print(f"  [Final Synthesis] {len(report)} chars")

    # === 附加 Critic 审查结果到报告末尾 ===
    critic_appendix = "\n\n---\n## Critic Review\n\n"

    if p0_list:
        critic_appendix += "### P0 阻断级\n"
        for p0 in p0_list:
            critic_appendix += (
                f"- **{p0.get('issue', '')}**\n"
                f"  反证: {p0.get('evidence', '')}\n"
                f"  处理: {'已修正' if needs_fix else '待修正'}\n\n"
            )

    if p1_list:
        critic_appendix += "### P1 改进级\n"
        for p1 in p1_list:
            critic_appendix += f"- {p1.get('issue', '')} ({p1.get('evidence', '')})\n"

    if p2_list:
        critic_appendix += "\n### P2 备注\n"
        for p2 in p2_list:
            critic_appendix += f"- {p2.get('issue', '')}\n"

    report += critic_appendix

    # === 校准采样 + 漂移检测 ===
    try:
        from scripts.critic_calibration import (
            sample_for_calibration, save_pending_samples,
            push_calibration_to_feishu, check_drift
        )

        # 采样
        report_excerpt = report[:500]
        samples = sample_for_calibration(
            {"p0_blocking": p0_list, "p1_improvement": p1_list, "p2_note": p2_list},
            report_excerpt, goal, task_title
        )
        if samples:
            save_pending_samples(samples)
            push_calibration_to_feishu(samples, progress_callback)

        # 漂移检测
        check_drift(
            {"p0_blocking": p0_list, "p1_improvement": p1_list, "p2_note": p2_list},
            progress_callback
        )

    except ImportError:
        pass  # 校准模块未安装
    except Exception as e:
        print(f"  [Calibration] 采样/漂移检测异常: {e}")

    return report


def deep_research_one(task: dict, progress_callback=None, constraint_context: str = None) -> str:
    """对一个任务做深度研究，返回完整报告

    Args:
        task: 任务字典，包含 id, title, goal, searches
        progress_callback: 进度回调函数
        constraint_context: 约束文件内容，注入到研究 prompt 中
    """
    task_id = task["id"]
    title = task["title"]
    goal = task["goal"]
    searches = task.get("searches", [])

    # 如果有约束文件内容，注入到 goal 中
    if constraint_context:
        goal = f"{goal}\n\n【研究约束】\n{constraint_context}"

    print(f"\n{'='*60}")
    print(f"[Deep Research] {title}")
    print(f"[Goal] {goal[:200]}...")
    print(f"[Sources] {len(searches)} searches")
    if constraint_context:
        print(f"[Constraints] 附带约束文件")
    print(f"{'='*60}")

    if progress_callback:
        progress_callback(f"Researching: {title[:20]}...")

    # 如果 searches 为空，自动生成搜索词
    if not searches:
        gen_prompt = (
            f"你是智能骑行头盔项目的研究规划师。\n"
            f"研究主题：{title}\n目标：{goal}\n\n"
            f"请生成 6-8 个搜索词用于调研这个主题。\n"
            f"要求：具体、含品牌名/公司名/型号、中英文混合。\n"
            f"只输出 JSON 数组。"
        )
        # === Phase 2.3: 搜索词生成用 Flash ===
        gen_result = call_for_search(gen_prompt, "只输出 JSON 数组。", "gen_searches")
        if gen_result.get("success"):
            try:
                resp = gen_result["response"].strip()
                resp = re.sub(r'^```json\s*', '', resp)
                resp = re.sub(r'\s*```$', '', resp)
                searches = json.loads(resp)
                if isinstance(searches, list):
                    task["searches"] = searches
                    print(f"  [Auto] Generated {len(searches)} search queries")
            except:
                pass
        if not searches:
            searches = [title + " 2026", title + " analysis report"]
            task["searches"] = searches
            print(f"  [Fallback] Using {len(searches)} default searches")

    # Step 0: 发现层——先搜一轮开放性问题，补充我们可能遗漏的供应商/方案
    discovery_query = f"{title} 2026 完整供应商名单 对比"
    print(f"  [Discovery] {discovery_query[:50]}...")
    disc_result = registry.call("deep_research", discovery_query)
    if disc_result.get("success") and len(disc_result.get("data", "")) > 200:
        # 让 LLM 从发现结果中提取我们可能遗漏的搜索词（限定骑行头盔领域）
        discover_prompt = (
            f"以下是关于「{title}」的搜索结果。\n"
            f"我们正在做智能骑行头盔（摩托车/自行车）项目的研究。\n\n"
            f"请从搜索结果中提取与以下领域直接相关的公司/品牌/产品/技术：\n"
            f"- 头盔制造商、头盔配件供应商\n"
            f"- 声学/光学/摄像头/通讯/电池/芯片方案商\n"
            f"- 智能穿戴ODM/JDM供应商\n"
            f"- 骑行装备品牌和竞品\n\n"
            f"严格排除与骑行头盔无关的公司（如Gartner、Netflix、Adobe、IBM、Salesforce等咨询/软件公司）。\n\n"
            f"只输出 JSON 数组，每个元素是一个搜索词：[\"公司A 产品 能力\", \"公司B 参数 对比\"]\n"
            f"最多 5 个。不要输出与骑行头盔无关的搜索词。\n\n"
            f"{disc_result['data'][:3000]}"
        )
        disc_llm = _call_model(_get_model_for_task("discovery"), discover_prompt, "只输出 JSON 数组。", "discovery")
        if disc_llm.get("success"):
            resp = disc_llm["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            try:
                extra_searches = json.loads(resp)
                if isinstance(extra_searches, list):
                    searches = searches + extra_searches[:5]
                    print(f"  [Discovery] 补充 {len(extra_searches[:5])} 个搜索词: {extra_searches[:3]}")
            except:
                pass

    # === Layer 1: 并发双搜索 ===
    all_sources = []
    source_lock = threading.Lock()

    hb = ProgressHeartbeat(
        f"深度研究:{title[:20]}",
        total=len(searches),
        feishu_callback=progress_callback,
        log_interval=3,
        feishu_interval=5,
        feishu_time_interval=180
    )

    def _search_one_query(i: int, query: str) -> dict:
        """单个 query 的双通道搜索（在线程中运行）"""
        source_text = ""

        # Channel A: o3-deep-research（英文技术 + 专利）
        o3_result = _call_with_backoff(
            "o3_deep_research", query,
            "Search for technical specifications, patents, and research papers.",
            "deep_research_search")
        o3_text = ""
        if o3_result.get("success") and len(o3_result.get("response", "")) > 200:
            o3_text = o3_result["response"][:3000]
            model_used = o3_result.get("degraded_from", "o3_deep_research") if o3_result.get("degraded_from") else "o3"
            print(f"    [{i}] o3: {len(o3_result['response'])} 字 (via {model_used})")

        # Channel B: doubao（中文互联网）
        doubao_result = _call_with_backoff(
            "doubao_seed_pro", query,
            "搜索中文互联网信息，重点关注小红书、B站、知乎、雪球、1688等平台的相关内容。",
            "chinese_search")
        doubao_text = ""
        if doubao_result.get("success") and len(doubao_result.get("response", "")) > 200:
            doubao_text = doubao_result["response"][:3000]
            print(f"    [{i}] doubao: {len(doubao_result['response'])} 字")

        source_text = o3_text
        if doubao_text:
            source_text += "\n---\n" + doubao_text if source_text else doubao_text

        # Fallback: tavily（仅当双通道都失败时）
        if not source_text:
            tavily_result = registry.call("tavily_search", query)
            if tavily_result.get("success") and len(tavily_result.get("data", "")) > 200:
                source_text = tavily_result["data"][:3000]
                print(f"    [{i}] tavily(fallback): {len(source_text)} 字")

        return {"index": i, "query": query, "content": source_text}

    # 展平 searches（discovery 可能返回嵌套 list）
    flat_searches = []
    for s in searches:
        if isinstance(s, list):
            flat_searches.extend([str(item) for item in s])
        else:
            flat_searches.append(str(s))
    searches = flat_searches

    # 并发搜索所有 query
    print(f"  [L1] 并发搜索 {len(searches)} 个 query...")
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(_search_one_query, i, q): i
            for i, q in enumerate(searches, 1)
        }
        for future in as_completed(futures):
            result = future.result()
            if result["content"]:
                with source_lock:
                    all_sources.append({
                        "query": result["query"],
                        "content": result["content"][:6000]
                    })
                hb.tick(detail=result["query"][:40], success=True)
            else:
                hb.tick(detail=f"失败: {result['query'][:40]}", success=False)

    hb.finish(f"搜索完成，{len(all_sources)}/{len(searches)} 有效")

    if not all_sources:
        return f"# {title}\n\n调研失败：所有搜索均无结果"

    # === Layer 2: 并发结构化提炼 ===
    print(f"  [L2] 并发提炼 {len(all_sources)} 条...")
    structured_data_list = []
    struct_lock = threading.Lock()
    task_type_hint = task.get("goal", "") + " " + title

    def _extract_one(src: dict) -> dict:
        """单条搜索结果的结构化提取"""
        return _extract_structured_data(
            raw_text=src["content"],
            task_type=task_type_hint,
            topic=src["query"]
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_extract_one, src): src for src in all_sources}
        for future in as_completed(futures):
            extracted = future.result()
            if extracted:
                with struct_lock:
                    structured_data_list.append(extracted)

    print(f"  [L2] 提炼完成: {len(structured_data_list)}/{len(all_sources)} 成功")

    # 序列化供后续层使用
    structured_dump = ""
    if structured_data_list:
        structured_dump = json.dumps(structured_data_list, ensure_ascii=False, indent=2)

    # Step 2: 读取知识库中已有的相关知识（内部文档优先）
    kb_context = ""
    internal_context = ""
    keywords = title.split() + goal.split()[:5]

    # 先收集所有匹配条目
    kb_entries = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            content = data.get("content", "")
            t = data.get("title", "")
            tags = data.get("tags", [])
            source = data.get("source", "")
            confidence = data.get("confidence", "")

            # 判断是否为内部文档
            is_internal = (
                "internal" in tags
                or "prd" in tags
                or "product_definition" in tags
                or "anchor" in tags
                or "user_upload" in source
                or confidence == "authoritative"
            )

            # 关键词匹配
            matched = any(kw in t or kw in content[:300] for kw in keywords)
            if not matched:
                # 也匹配常见领域关键词
                matched = any(kw in t or kw in content[:200] for kw in [
                    "歌尔", "Goertek", "立讯", "Luxshare", "JDM", "ODM",
                    "光波导", "waveguide", "MEMS", "骨传导", "BOM", "供应商", "代工",
                    "光学", "声学", "摄像头", "模组", "PRD", "产品定义", "规格", "参数"
                ])

            if matched:
                kb_entries.append({
                    "title": t,
                    "content": content,
                    "is_internal": is_internal
                })
        except:
            continue

    # 内部文档排在最前面
    kb_entries.sort(key=lambda x: -x["is_internal"])

    for entry in kb_entries[:10]:
        if entry["is_internal"]:
            internal_context += f"\n[内部产品定义] {entry['title']}:\n{entry['content'][:2000]}\n"
        else:
            kb_context += f"\n[KB] {entry['title']}: {entry['content'][:300]}"

    # 内部文档在最前面
    kb_context = internal_context + kb_context
    kb_context = kb_context[:5000]

    # 合并搜索材料
    source_dump = ""
    for s in all_sources:
        source_dump += f"\n\n### 搜索: {s['query']}\n{s['content']}"

    # Step 3: CPO 判断需要哪些 Agent 参与
    role_prompt = (
        f"你是智能骑行头盔项目的产品VP（CPO）。\n"
        f"研究任务：{title}\n目标：{goal}\n\n"
        f"判断这个任务需要以下哪些角色参与分析：\n"
        f"- CTO：技术可行性、参数对比、芯片/模组选型、风险评估\n"
        f"- CMO：市场验证、竞争格局、定价策略、商业模式、用户画像、中文互联网信息\n"
        f"- CDO：产品形态、用户体验、工业设计、外观约束\n\n"
        f"默认分配 CTO+CMO+CDO 全部三个角色，除非任务内容与某个角色完全无关。\n"
        f"CMO 擅长中文互联网搜索和市场分析，大部分任务都应该包含 CMO。\n"
        f"只输出 JSON 数组，如 [\"CTO\", \"CMO\"] 或 [\"CTO\", \"CMO\", \"CDO\"]\n"
    )

    role_result = _call_model(_get_model_for_task("role_assign"), role_prompt, "只输出 JSON 数组。", "role_assign")
    roles = ["CTO", "CMO", "CDO"]  # 默认全部参与
    if role_result.get("success"):
        try:
            resp = role_result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            parsed = json.loads(resp)
            if isinstance(parsed, list) and all(r in ("CTO", "CMO", "CDO") for r in parsed):
                roles = parsed
        except:
            pass

    print(f"  [Roles] {roles}")
    if progress_callback:
        progress_callback(f"  Participants: {', '.join(roles)}")

    # 构建产品定义锚点（不可违背的约束）
    product_anchor = ""
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            tags = data.get("tags", [])
            if "internal" in tags and ("prd" in tags or "product_definition" in tags):
                product_anchor = data.get("content", "")[:3000]
                break
        except:
            continue

    # 产品定义硬约束（注入每个 Agent 的 prompt）
    anchor_instruction = (
        f"\n\n## 产品定义锚点（不可违背）\n"
        f"以下是用户已确定的产品定义，你的所有分析必须在此框架内进行。\n"
        f"你可以建议功能分阶段（V1/V2），可以指出风险，可以建议优先级调整，\n"
        f"但**绝不能替用户更换产品品类、目标用户群或核心产品方向**。\n"
        f"如果你认为某个方向风险很高，应该说\"建议V1先做XX，V2再做YY\"，\n"
        f"而不是说\"不应该做XX\"。产品愿景的最终决定权在用户。\n\n"
        f"{product_anchor[:2500] if product_anchor else '无内部产品定义文档。'}\n"
    )

    # === Layer 3: Agent 并行分析 ===
    agent_outputs = {}
    agent_lock = threading.Lock()

    # Step 3.4: 匹配专家框架
    expert_fw = _match_expert_framework(goal, title)
    expert_role = expert_fw.get("role", "")
    expert_pitfalls = expert_fw.get("known_pitfalls", [])
    expert_criteria = expert_fw.get("evaluation_criteria", [])

    expert_injection = ""
    if expert_role:
        expert_injection += f"\n## 你的专家背景\n{expert_role}\n"
    if expert_pitfalls:
        expert_injection += f"\n## 已知陷阱（必须检查）\n"
        for i, p in enumerate(expert_pitfalls, 1):
            expert_injection += f"{i}. {p}\n"
    if expert_criteria:
        expert_injection += f"\n## 评估标准\n"
        for i, c in enumerate(expert_criteria, 1):
            expert_injection += f"{i}. {c}\n"

    if expert_injection:
        print(f"  [ExpertFW] 匹配到专家框架，注入 {len(expert_injection)} 字")

    # Layer 3 输入: 提炼数据 + KB，不是原始搜索材料
    distilled_material = structured_dump[:8000] if structured_dump else source_dump[:8000]
    kb_material = kb_context[:2000]

    # 构建 Agent prompts
    cto_prompt = (
        f"你是智能骑行头盔项目的技术合伙人（CTO）。\n"
        f"你拥有顶尖的技术判断力，不会泛泛而谈，每个判断都有具体数据支撑。\n"
        f"{expert_injection}\n"
        f"## 调研数据（已结构化提炼，每个数据点附 source 和 confidence）\n{distilled_material}\n\n"
        f"## 已有知识库\n{kb_material}\n\n"
        f"{anchor_instruction}\n"
        f"{THINKING_PRINCIPLES}\n"
        f"## 研究任务\n{title}\n\n## 目标\n{goal}\n\n"
        f"## 你的任务\n"
        f"从技术角度分析这个问题。要求：\n"
        f"1. 给出具体的技术参数对比（型号、规格、价格区间）\n"
        f"2. 评估技术可行性和风险\n"
        f"3. 给出明确的技术推荐（不要模棱两可）\n"
        f"4. 标注你不确定的信息\n"
        f"5. 如果某些功能风险高，建议分阶段实现，而不是砍掉\n"
        f"6. 输出 1000-1500 字\n"
        f"{CAPABILITY_GAP_INSTRUCTION}"
    )

    cmo_prompt = (
        f"你是智能骑行头盔项目的市场合伙人（CMO）。\n"
        f"你拥有敏锐的商业判断力，能识别伪需求，每个判断都基于数据或逻辑推演。\n"
        f"{expert_injection}\n"
        f"## 调研数据（已结构化提炼）\n{distilled_material}\n\n"
        f"## 已有知识库\n{kb_material}\n\n"
        f"{anchor_instruction}\n"
        f"{THINKING_PRINCIPLES}\n"
        f"## 研究任务\n{title}\n\n## 目标\n{goal}\n\n"
        f"## 你的任务\n"
        f"从市场和商业角度分析这个问题。要求：\n"
        f"1. 竞品是怎么做的？成功还是失败？为什么？\n"
        f"2. 用户真正在意什么？购买决策的关键因素？\n"
        f"3. 定价和商业模式建议\n"
        f"4. 给出明确的市场判断（不要两边讨好）\n"
        f"5. 如果市场风险高，建议如何分阶段验证，而不是放弃方向\n"
        f"6. 输出 1000-1500 字\n"
        f"{CAPABILITY_GAP_INSTRUCTION}"
    )

    cdo_prompt = (
        f"你是智能骑行头盔项目的设计合伙人（CDO）。\n"
        f"你懂工程约束，用设计语言表达品牌战略。\n"
        f"{expert_injection}\n"
        f"## 调研数据（已结构化提炼）\n{distilled_material}\n\n"
        f"## 已有知识库\n{kb_material}\n\n"
        f"{anchor_instruction}\n"
        f"{THINKING_PRINCIPLES}\n"
        f"## 研究任务\n{title}\n\n## 目标\n{goal}\n\n"
        f"## 你的任务\n"
        f"从产品设计和用户体验角度分析。要求：\n"
        f"1. 产品形态和用户体验的关键约束\n"
        f"2. 设计上的取舍建议（重量、体积、外观、佩戴感）\n"
        f"3. 竞品的设计优劣势\n"
        f"4. 如果设计约束导致某些功能难以首代实现，建议分阶段路径\n"
        f"5. 输出 800-1200 字\n"
        f"{CAPABILITY_GAP_INSTRUCTION}"
    )

    def _run_agent(role: str, prompt: str, sys_prompt: str) -> tuple:
        """运行单个 Agent（在线程中）"""
        model = _get_model_for_role(role)
        result = _call_with_backoff(model, prompt, sys_prompt,
                                     f"deep_research_{role.lower()}")
        if result.get("success"):
            return (role, result["response"])
        return (role, None)

    # 构建各 Agent 的任务
    agent_tasks = []
    if "CTO" in roles:
        agent_tasks.append(("CTO", cto_prompt, "你是资深技术合伙人，输出专业的技术分析。"))
    if "CMO" in roles:
        agent_tasks.append(("CMO", cmo_prompt, "你是资深市场合伙人，输出专业的商业分析。"))
    if "CDO" in roles:
        agent_tasks.append(("CDO", cdo_prompt, "你是资深设计合伙人，输出专业的设计分析。"))

    print(f"  [L3] 并行运行 {len(agent_tasks)} 个 Agent...")
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_run_agent, role, prompt, sys): role
            for role, prompt, sys in agent_tasks
        }
        for future in as_completed(futures):
            role, output = future.result()
            if output:
                with agent_lock:
                    agent_outputs[role] = output
                print(f"  [{role}] {len(output)} chars")
            else:
                print(f"  [{role}] ❌ failed")

    # === 元能力层: 扫描并补齐能力缺口 ===
    if agent_outputs:
        all_gaps = []
        for role, output in agent_outputs.items():
            gaps = scan_capability_gaps(output)
            for g in gaps:
                g["source_agent"] = role
            all_gaps.extend(gaps)

        if all_gaps:
            resolved_tools = resolve_all_gaps(all_gaps, gateway, max_resolve=3)

            # 如果补齐了新能力，为受影响的 Agent 提供补充分析
            if resolved_tools:
                print(f"  [Meta] 补齐 {len(resolved_tools)} 个能力，补充分析...")
                for gap in all_gaps[:3]:
                    source_agent = gap.get("source_agent")
                    if source_agent and source_agent in agent_outputs:
                        tool_info = "\n".join([
                            f"[新增工具] {t['tool_name']}: {t.get('invoke', '')}"
                            for t in resolved_tools
                        ])
                        supplement_prompt = (
                            f"你之前的分析中标记了能力缺口: {gap['description']}\n"
                            f"现在系统已补齐以下工具:\n{tool_info}\n\n"
                            f"请基于你之前的分析，补充使用新工具后可以得出的额外结论。"
                            f"只输出补充部分（300-500字），不要重复之前的内容。"
                        )
                        supplement = _call_model(
                            _get_model_for_role(source_agent),
                            supplement_prompt, task_type="meta_supplement"
                        )
                        if supplement.get("success"):
                            agent_outputs[source_agent] += (
                                f"\n\n## 补充分析（能力补齐后）\n"
                                f"{supplement['response']}"
                            )

    if not agent_outputs:
        # 全部失败，fallback 到单 CPO 模式
        print("  [WARN] All agents failed, fallback to single CPO")
        synthesis_prompt_fallback = (
            f"## 研究任务\n{title}\n## 目标\n{goal}\n"
            f"## 知识库\n{kb_material}\n## 材料\n{source_material}\n"
            f"写一份 2000-3000 字的完整研究报告。"
        )
        fallback = _call_model("gpt_5_4", synthesis_prompt_fallback,
            "你是资深研发顾问。", "deep_research_fallback")
        report = fallback.get("response", "报告生成失败") if fallback.get("success") else "报告生成失败"
    else:
        # Step 4: CPO 整合多视角
        agent_section = ""
        for role, output in agent_outputs.items():
            agent_section += f"\n\n### {role} 分析\n{output}"

        synthesis_prompt = (
            f"你是智能骑行头盔项目的高级技术整合分析师。你的输出目标不是'给出推荐'，而是'提供决策支撑'。\n\n"
            f"{THINKING_PRINCIPLES}\n"
            f"特别注意：如果团队某个角色在解决 XY 问题（表面问题而非真正问题），你必须指出并纠正。\n\n"
            f"## 产品定义锚点（最高优先级）\n"
            f"用户已确定的产品方向不可更改。你可以建议功能分V1/V2，但不能替用户换产品品类。\n\n"
            f"## 研究任务\n{title}\n\n"
            f"## 目标\n{goal}\n\n"
            f"## 团队各视角分析\n{agent_section}\n\n"
            f"## 输出要求（严格遵守）\n\n"
            f"### 一、数据对比表\n"
            f"- 必须包含每个数据点的来源和 confidence\n"
            f"- 未公开的数据标注 null，不要填推测值\n"
            f"- 如果有推算值，单独列一列标注推算方法\n\n"
            f"### 二、候选方案（2-3 个）\n"
            f"- 每个方案附完整的 pros/cons\n"
            f"- 每个 pros/cons 必须有量化依据\n"
            f"- 不要只说'成本更低'，要说'BOM 低 40-60%，约 $80-180 vs $180-400'\n\n"
            f"### 三、关键分歧点（不超过 5 个）\n"
            f"- 方案之间的核心分歧，每个分歧点用一句话概括\n"
            f"- 每个分歧点附：支持 A 方案的证据 vs 支持 B 方案的证据\n\n"
            f"### 四、需要决策者判断的问题\n"
            f"- 列出 3-5 个你无法替决策者回答的问题\n"
            f"- 每个问题附上你能提供的背景信息\n"
            f"- 格式：'[决策点] 问题描述。背景：xxx'\n\n"
            f"### 五、数据缺口\n"
            f"- 本次研究中哪些关键数据没有找到\n"
            f"- 建议通过什么渠道补充（供应商询价 / 竞品拆机 / 专利检索 / 行业报告）\n\n"
            f"你不要替用户做最终选择。用户的价值是定义 Why，你的价值是把 How 的选项和代价摆清楚。\n"
        )

        synthesis_result = _call_model(_get_model_for_task("synthesis"), synthesis_prompt,
            "你是产品VP，整合团队分析并裁决。", "deep_research_synthesis")

        if not synthesis_result.get("success"):
            # 重试一次，用更精简的 prompt
            retry_prompt = (
                f"请整合以下团队分析，写一份 2000-3000 字的研究报告。\n"
                f"任务：{title}\n目标：{goal}\n\n"
                f"{agent_section[:8000]}\n\n"
                f"要求：有执行摘要、有明确结论、保留所有具体数据。"
            )
            retry_result = _call_model(_get_model_for_task("synthesis"), retry_prompt,
                "整合团队分析。", "synthesis_retry")
            if retry_result.get("success"):
                report = retry_result["response"]
                print(f"  [Synthesis Retry] OK {len(report)} chars")
            else:
                # 最终 fallback：让 CPO 基于最长的 Agent 输出扩写
                longest_role = max(agent_outputs.keys(), key=lambda r: len(agent_outputs[r]))
                longest_output = agent_outputs[longest_role]
                other_highlights = ""
                for role, output in agent_outputs.items():
                    if role != longest_role:
                        other_highlights += f"\n{role} 要点：{output[:500]}\n"

                expand_prompt = (
                    f"以下是 {longest_role} 对「{title}」的分析，以及其他角色的要点摘要。\n"
                    f"请在此基础上写一份完整的 2000-3000 字研究报告。\n\n"
                    f"## {longest_role} 完整分析\n{longest_output}\n\n"
                    f"## 其他角色要点\n{other_highlights}\n\n"
                    f"要求：有执行摘要、有明确结论。"
                )
                expand_result = _call_model("gpt_5_4", expand_prompt,
                    "写研究报告。", "synthesis_expand")
                report = expand_result.get("response", agent_section) if expand_result.get("success") else agent_section
                print(f"  [Synthesis Expand] {len(report)} chars")
        else:
            report = synthesis_result["response"]

    # === Layer 5: Critic（所有路径统一执行）===
    report = _run_critic_challenge(report, goal, agent_outputs,
                                    structured_data=structured_dump,
                                    progress_callback=progress_callback,
                                    task_title=title)

    # Step 4: 保存报告到文件
    report_path = REPORT_DIR / f"{task_id}_{time.strftime('%Y%m%d_%H%M')}.md"
    report_path.write_text(f"# {title}\n\n> 目标: {goal}\n> 生成时间: {time.strftime('%Y-%m-%d %H:%M')}\n> 来源数: {len(all_sources)}\n\n{report}", encoding="utf-8")
    print(f"\n[Saved] {report_path}")

    # Step 4.5: 完整报告存入知识库
    from src.tools.knowledge_base import add_report
    report_kb_path = add_report(
        title=f"[研究报告] {title}",
        domain="components",
        content=report,  # 全文
        tags=["deep_research", "report", task_id],
        source=f"deep_research:{task_id}",
        confidence="high"
    )
    print(f"[KB Report] {report_kb_path}")

    # Step 5: 从报告中提取关键知识条目存入知识库（作为索引）
    extract_prompt = (
        f"从以下研究报告中提取 3-5 条最有价值的知识条目。\n"
        f"每条应该是一个可以直接用于决策的具体事实或数据点。\n"
        f"输出 JSON 数组：[{{\"title\": \"标题(含公司名/型号)\", \"domain\": \"components\", "
        f"\"summary\": \"200字摘要，保留所有数字\", \"tags\": [\"标签\"]}}]\n\n"
        f"报告：\n{report[:6000]}"
    )

    extract_result = _call_model(
        _get_model_for_task("knowledge_extract"), extract_prompt,
        "只输出 JSON 数组。",
        "deep_research_extract"
    )

    if extract_result.get("success"):
        resp = extract_result["response"].strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        try:
            items = json.loads(resp)
            added_count = 0
            skipped_count = 0
            for item in items:
                domain = item.get("domain", "components")
                if domain not in ("competitors", "components", "standards", "lessons"):
                    domain = "components"

                # === 29a: 自主质量评估——入库前过滤 ===
                title_text = item.get("title", "")[:80]
                content_text = item.get("summary", "")[:800]

                is_low_quality = False
                quality_reasons = []

                # 规则1：内容太短（<150字）
                if len(content_text) < 150:
                    is_low_quality = True
                    quality_reasons.append("内容<150字")

                # 规则2：没有任何具体数据（数字、型号、价格、百分比）
                has_data = bool(re.search(r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|USD|\$|%|nits|lux|fps|°|μm)', content_text))
                has_model = bool(re.search(r'[A-Z]{2,}\d{2,}|[A-Z]\d{4,}|IMX\d|QCC\d|BES\d|nRF\d|AR\d|ECE\s*\d|SN\d|KS\d', content_text))
                if not has_data and not has_model:
                    is_low_quality = True
                    quality_reasons.append("无具体数据或型号")

                # 规则3：标题是泛泛的描述
                generic_titles = ["智能头盔", "骑行头盔", "头盔方案", "技术方案", "市场分析", "智能摩托车头盔", "摩托车头盔"]
                if any(title_text.strip() == g for g in generic_titles):
                    is_low_quality = True
                    quality_reasons.append("标题太泛")

                if is_low_quality:
                    print(f"  [SKIP] {title_text[:40]}... — 质量不足: {', '.join(quality_reasons)}")
                    skipped_count += 1
                    continue

                add_knowledge(
                    title=title_text,
                    domain=domain,
                    content=content_text,
                    tags=item.get("tags", []) + ["deep_research", task_id],
                    source=f"deep_research:{task_id}",
                    confidence="high"
                )
                added_count += 1
            print(f"[KB] 提取 {added_count} 条知识，跳过 {skipped_count} 条低质量")
        except:
            print("[KB] 提取失败")

    return report


def run_all(progress_callback=None):
    """运行所有深度研究任务

    注意：夜间（23:00-07:00）不推送进度，只打印
    """
    from datetime import datetime

    # 白天/夜间模式检测
    current_hour = datetime.now().hour
    is_night = current_hour >= 23 or current_hour < 7

    print(f"\n{'#'*60}")
    print(f"# 智能骑行头盔 JDM 供应商选型 — 深度研究")
    print(f"# 共 {len(RESEARCH_TASKS)} 个任务")
    print(f"# 开始时间: {time.strftime('%Y-%m-%d %H:%M')}")
    if is_night:
        print("# [夜间模式] 进度不推送，仅本地打印")
    print(f"{'#'*60}")

    # 夜间模式：不推送进度
    effective_callback = None if is_night else progress_callback

    if effective_callback:
        effective_callback(f"🚀 开始深度研究（{len(RESEARCH_TASKS)} 个任务）")

    reports = []
    for idx, task in enumerate(RESEARCH_TASKS, 1):
        if effective_callback:
            effective_callback(f"🔍 [{idx}/{len(RESEARCH_TASKS)}] 开始: {task['title']}")

        report = deep_research_one(task, progress_callback=effective_callback)
        reports.append({"title": task["title"], "report": report})
        print(f"\n✅ {task['title']} 完成 ({len(report)} 字)")

        if effective_callback:
            effective_callback(f"✅ [{idx}/{len(RESEARCH_TASKS)}] {task['title']} ({len(report)}字)")

        time.sleep(5)

    # 汇总保存
    summary_path = REPORT_DIR / f"jdm_summary_{time.strftime('%Y%m%d_%H%M')}.md"
    summary = "# JDM 供应商选型 — 深度研究汇总\n\n"
    summary += f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M')}\n\n"
    for r in reports:
        summary += f"\n---\n\n# {r['title']}\n\n{r['report']}\n"
    summary_path.write_text(summary, encoding="utf-8")

    stats = get_knowledge_stats()
    total = sum(stats.values())

    print(f"\n{'#'*60}")
    print(f"# 全部完成！")
    print(f"# 报告: {summary_path}")
    print(f"# 知识库: {total} 条")
    print(f"# 完成时间: {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*60}")

    # 任务完成提示音
    try:
        from src.utils.notifier import notify
        notify("success")
    except:
        print('\a')  # ASCII bell fallback

    return str(summary_path)


def parse_research_tasks_from_md(md_path: str) -> list:
    """从 markdown 文件解析研究任务

    支持的格式：
    - # 研究 A：标题 -> 解析为任务
    - ## A.1 子任务标题 -> 解析为 searches
    - goal 从 "研究目标" 部分提取
    """
    content = Path(md_path).read_text(encoding="utf-8")
    tasks = []

    # 匹配研究标题：# 研究 A：XXX 或 # 研究 B：XXX
    research_pattern = re.compile(r'^# 研究 ([A-Z])：(.+)$', re.MULTILINE)

    for match in research_pattern.finditer(content):
        task_id = f"research_{match.group(1).lower()}"
        title = match.group(2).strip()

        # 提取该研究的完整内容（到下一个 # 研究 或文件结束）
        start_pos = match.end()
        next_match = research_pattern.search(content, start_pos)
        end_pos = next_match.start() if next_match else len(content)
        section_content = content[start_pos:end_pos]

        # 提取目标（从 ## X.0 研究目标 部分）
        goal_match = re.search(r'## [A-Z]\.0\s*(?:研究目标|分析目标)\s*\n([^\n]+(?:\n(?![#])[^\n]+)*)', section_content)
        goal = goal_match.group(1).strip() if goal_match else f"深度研究：{title}"

        # 提取 searches（从子任务标题 ## A.1.1 等）
        searches = []

        # 匹配子任务：### A.1.1 标题 或 ## A.1 标题
        subtask_pattern = re.compile(r'^#{2,3}\s+[A-Z]\.\d+(?:\.\d+)?\s+(.+)$', re.MULTILINE)
        for sub_match in subtask_pattern.finditer(section_content):
            sub_title = sub_match.group(1).strip()
            # 将子任务标题转换为搜索关键词
            search_query = f"{sub_title} motorcycle helmet HUD specs parameters 2025 2026"
            searches.append(search_query)

        # 添加默认搜索词
        if not searches:
            searches = [
                f"{title} motorcycle helmet HUD 2025 2026",
                f"{title} optical display specifications",
            ]

        tasks.append({
            "id": task_id,
            "title": title,
            "goal": goal,
            "searches": searches[:10],  # 最多 10 个搜索
            "source_file": str(md_path),
        })

    return tasks


def run_research_from_file(md_path: str, progress_callback=None, task_ids: list = None, constraint_context: str = None):
    """从 markdown 文件运行研究任务

    Args:
        md_path: 任务定义文件路径
        progress_callback: 进度回调函数
        task_ids: 指定运行的任务 ID 列表，如 ['research_a', 'research_b']；None 表示全部运行
        constraint_context: 约束文件内容，注入到每个研究任务的 prompt 中
    """
    tasks = parse_research_tasks_from_md(md_path)

    if not tasks:
        print(f"[Warning] 未从 {md_path} 解析到任务")
        return None

    # 过滤指定任务
    if task_ids:
        tasks = [t for t in tasks if t["id"] in task_ids]

    if not tasks:
        print(f"[Warning] 指定的 task_ids {task_ids} 未在文件中找到")
        return None

    print(f"\n{'#'*60}")
    print(f"# 从文件运行深度研究: {md_path}")
    print(f"# 共 {len(tasks)} 个任务")
    print(f"# 开始时间: {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*60}")

    reports = []
    for idx, task in enumerate(tasks, 1):
        if progress_callback:
            progress_callback(f"🔍 [{idx}/{len(tasks)}] 开始: {task['title']}")

        report = deep_research_one(task, progress_callback=progress_callback, constraint_context=constraint_context)
        reports.append({"id": task["id"], "title": task["title"], "report": report})
        print(f"\n✅ {task['title']} 完成 ({len(report)} 字)")

        if progress_callback:
            progress_callback(f"✅ [{idx}/{len(tasks)}] {task['title']} ({len(report)}字)")

        time.sleep(3)

    # === 跨研究一致性校验 ===
    if len(reports) >= 2:
        print(f"\n  [ConsistencyCheck] 检查 {len(reports)} 份报告的结论一致性...")

        # 提取每份报告的关键结论
        conclusions = ""
        for r in reports:
            conclusions += f"\n\n### {r['title']}\n{r['report'][:2000]}"

        consistency_prompt = (
            f"以下是同一个项目（智能骑行头盔）的 {len(reports)} 份研究报告的结论部分。\n\n"
            f"请检查它们之间是否存在自相矛盾：\n"
            f"1. 研究 A 推荐方案 X，但研究 B 推荐方案 Y？\n"
            f"2. 研究 A 说某参数为 P，研究 B 说同一参数为 Q？\n"
            f"3. 同一产品在不同报告中被不同评价？\n\n"
            f"输出 JSON：\n"
            f'{{"contradictions": [{{"report_a": "标题", "report_b": "标题", '
            f'"description": "矛盾描述", "severity": "high/medium/low"}}], '
            f'"consistent": true/false}}\n\n'
            f"如果没有发现矛盾，contradictions 为空数组，consistent 为 true。\n\n"
            f"{conclusions}"
        )

        check_result = _call_model(
            _get_model_for_task("critic_challenge"),
            consistency_prompt,
            "只输出 JSON。",
            "consistency_check"
        )

        if check_result.get("success"):
            try:
                resp = check_result["response"].strip()
                resp = re.sub(r'^```json\s*', '', resp)
                resp = re.sub(r'\s*```$', '', resp)
                check_data = json.loads(resp)

                contradictions = check_data.get("contradictions", [])
                if contradictions:
                    print(f"  [ConsistencyCheck] ⚠️ 发现 {len(contradictions)} 个矛盾:")
                    for c in contradictions:
                        print(f"    - [{c.get('severity','?')}] {c.get('description','')[:100]}")

                    # 将矛盾信息附加到汇总报告中
                    contradiction_section = "\n\n---\n## ⚠️ 跨研究一致性问题\n\n"
                    for c in contradictions:
                        contradiction_section += (
                            f"- **[{c.get('severity','')}]** {c.get('report_a','')} vs {c.get('report_b','')}：\n"
                            f"  {c.get('description','')}\n\n"
                        )
                    # 附加到最后一份报告的末尾
                    reports[-1]["report"] += contradiction_section

                    if progress_callback:
                        progress_callback(
                            f"⚠️ 一致性检查：发现 {len(contradictions)} 个跨报告矛盾，已记录在汇总中"
                        )
                else:
                    print(f"  [ConsistencyCheck] ✅ 无矛盾")
            except Exception as e:
                print(f"  [ConsistencyCheck] 解析失败: {e}")
        else:
            print(f"  [ConsistencyCheck] 调用失败: {check_result.get('error', '')[:100]}")

    # 汇总保存
    md_name = Path(md_path).stem
    summary_path = REPORT_DIR / f"{md_name}_summary_{time.strftime('%Y%m%d_%H%M')}.md"
    summary = f"# {md_name} — 深度研究汇总\n\n"
    summary += f"> 来源文件: {md_path}\n"
    summary += f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M')}\n\n"
    for r in reports:
        summary += f"\n---\n\n## {r['title']}\n\n{r['report']}\n"
    summary_path.write_text(summary, encoding="utf-8")

    print(f"\n{'#'*60}")
    print(f"# 全部完成！")
    print(f"# 报告: {summary_path}")
    print(f"# 完成时间: {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*60}")

    return str(summary_path)


# ============================================================
# Part 2: 深度学习调度器 — 任务池 + 自主发现 + 7h 窗口
# ============================================================

TASK_POOL_PATH = Path(__file__).parent.parent / ".ai-state" / "research_task_pool.yaml"


def _load_task_pool() -> list:
    """加载任务池，返回未完成的任务（按优先级排序）"""
    if not TASK_POOL_PATH.exists():
        return []
    try:
        with open(TASK_POOL_PATH, 'r', encoding='utf-8') as f:
            pool = yaml.safe_load(f) or []
        # 过滤已完成的
        return [t for t in pool if not t.get("completed")]
    except:
        return []


def _save_task_pool(pool: list):
    """保存任务池"""
    TASK_POOL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TASK_POOL_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(pool, f, allow_unicode=True)


def _mark_task_done(task_id: str):
    """标记任务完成"""
    pool = _load_task_pool()
    all_tasks = []
    # 重新加载完整池（包括已完成的）
    if TASK_POOL_PATH.exists():
        try:
            with open(TASK_POOL_PATH, 'r', encoding='utf-8') as f:
                all_tasks = yaml.safe_load(f) or []
        except:
            all_tasks = pool

    for t in all_tasks:
        if t.get("id") == task_id:
            t["completed"] = True
            t["completed_at"] = time.strftime('%Y-%m-%d %H:%M')
    _save_task_pool(all_tasks)


def _discover_new_tasks() -> list:
    """自主发现新研究方向

    基于:
    1. KB 缺口分析
    2. 产品锚点中未覆盖的技术方向
    3. 竞品动态
    4. 供应链变化
    """
    # 收集已有任务标题（用于去重）
    pool = _load_task_pool()
    existing_titles = [t.get("title", "") for t in pool]

    # 已完成的任务（从报告目录扫描）
    reports_dir = Path(__file__).parent.parent / ".ai-state" / "reports"
    if reports_dir.exists():
        for f in reports_dir.glob("*.md"):
            existing_titles.append(f.stem.replace("_", " "))

    existing_titles_text = "\n".join(f"- {t}" for t in existing_titles[-30:])

    # 读取决策树
    decision_tree_path = Path(__file__).parent.parent / ".ai-state" / "product_decision_tree.yaml"
    decision_tree_text = ""
    if decision_tree_path.exists():
        try:
            with open(decision_tree_path, 'r', encoding='utf-8') as f:
                dt = yaml.safe_load(f)
            open_decisions = [d for d in dt.get("decisions", []) if d.get("status") == "open"]
            if open_decisions:
                decision_tree_text = "\n## 待决策事项（优先填充这些知识缺口）\n"
                for d in sorted(open_decisions, key=lambda x: x.get("priority", 99)):
                    decision_tree_text += f"\n### {d['question']}\n"
                    decision_tree_text += f"优先级: P{d.get('priority', 3)}\n"
                    decision_tree_text += "需要的知识:\n"
                    for bk in d.get("blocking_knowledge", []):
                        decision_tree_text += f"  - {bk}\n"
        except:
            pass

    # 用 LLM 分析 KB 现状，生成研究建议
    kb_summary = _get_kb_summary()

    discover_prompt = (
        f"你是智能骑行头盔项目的研究规划师。\n\n"
        f"## 当前知识库状态\n{kb_summary}\n\n"
        f"## 产品方向\n"
        f"全脸头盔，HUD显示，语音控制，组队骑行，主动安全。\n"
        f"V1 关键技术: OLED+Free Form / Micro LED+树脂衍射光波导（并行路线）\n"
        f"主SoC: Qualcomm AR1 Gen 1\n"
        f"通信: Mesh Intercom\n"
        f"{decision_tree_text}\n"
        f"## 已有任务（避免重复）\n"
        f"以下任务已经存在或已完成，不要生成与它们高度重叠的新任务：\n"
        f"{existing_titles_text}\n\n"
        f"如果你要研究的方向与已有任务重叠超过 50%，请换一个角度或跳过。\n\n"
        f"## 任务\n"
        f"优先生成能填充"待决策事项"中知识缺口的研究任务。\n"
        f"每个任务的 goal 应该明确指向某个决策点的某个知识缺口。\n"
        f"每个任务要有明确的研究目标和 6-8 个搜索关键词。\n"
        f"优先级: 1=紧急（影响V1决策）, 2=重要（影响成本/供应链）, 3=储备\n\n"
        f"输出 JSON 数组:\n"
        f'[{{"id": "auto_xxx", "title": "标题", "goal": "研究目标", '
        f'"priority": 1, "searches": ["搜索词1", "搜索词2", ...]}}]\n'
        f"只输出 JSON。"
    )

    result = _call_model("gemini_2_5_flash", discover_prompt,
                          task_type="discovery")
    if result.get("success"):
        try:
            resp = result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            tasks = json.loads(resp)
            if isinstance(tasks, list):
                print(f"  [Discover] 发现 {len(tasks)} 个新方向")

                # 去重：新任务标题不能与已有任务过于相似
                deduped = []
                for task in tasks:
                    new_title = task.get("title", "")
                    is_duplicate = False
                    for existing in existing_titles:
                        # 简单去重：超过 3 个相同的中文双字词
                        new_words = set(re.findall(r'[\u4e00-\u9fff]{2,4}', new_title))
                        old_words = set(re.findall(r'[\u4e00-\u9fff]{2,4}', existing))
                        overlap = new_words & old_words
                        if len(overlap) >= 3 and len(overlap) / max(len(new_words), 1) > 0.5:
                            print(f"  [Discover] 去重: '{new_title}' 与 '{existing}' 重叠")
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        deduped.append(task)

                print(f"  [Discover] 去重后: {len(tasks)} → {len(deduped)}")
                return deduped
        except:
            pass
    return []


def _get_kb_summary() -> str:
    """获取知识库摘要"""
    stats = get_knowledge_stats()
    summary = f"知识库统计: {stats}\n"

    # 扫描最近条目
    recent = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            recent.append({
                "title": data.get("title", "")[:50],
                "domain": data.get("domain", ""),
                "confidence": data.get("confidence", "")
            })
        except:
            continue

    if recent:
        summary += f"总条目数: {len(recent)}\n"
        domains = {}
        for e in recent:
            d = e.get("domain", "unknown")
            domains[d] = domains.get(d, 0) + 1
        summary += f"域分布: {domains}\n"

    return summary


def _run_layers_1_to_3(task: dict, progress_callback=None) -> dict:
    """执行 Layer 1-3，返回中间结果供 Layer 4-5 使用

    返回的 dict 包含:
    - agent_outputs: {role: output_text}
    - structured_dump: JSON 字符串
    - kb_context: 知识库上下文
    - goal, title: 元数据
    - l1_l3_duration: 耗时（秒）
    """
    # 复用 deep_research_one 的逻辑，但只执行到 Agent 分析
    # 这里简化实现：直接调用 deep_research_one，然后提取中间结果
    # 完整实现需要将 deep_research_one 拆分为两阶段
    t0 = time.time()

    # 调用 deep_research_one 获取报告
    report = deep_research_one(task, progress_callback=progress_callback)

    return {
        "title": task.get("title", ""),
        "goal": task.get("goal", ""),
        "task": task,
        "report": report,
        "l1_l3_duration": time.time() - t0,
    }


def _run_layers_4_to_5(intermediate: dict, progress_callback=None) -> str:
    """执行 Layer 4-5: 整合→Critic→入库

    输入: _run_layers_1_to_3 的输出
    输出: 最终报告文本
    """
    # 简化实现：直接返回报告
    # 完整实现需要拆分 deep_research_one
    return intermediate.get("report", "")


def run_deep_learning(max_hours: float = 7.0, progress_callback=None):
    """深度学习主调度器

    在 max_hours 时间窗口内，持续执行研究任务:
    1. 先从任务池取
    2. 任务池空了 → 自主发现新方向
    3. 每个任务完成后检查剩余时间
    4. 不够跑下一个就收尾
    """
    import queue
    from src.tools.knowledge_base import get_knowledge_stats

    # 记录 KB 初始状态
    kb_stats_before = get_knowledge_stats()
    kb_total_before = sum(kb_stats_before.values())

    start_time = time.time()
    deadline = start_time + max_hours * 3600
    completed = []

    print(f"\n{'#'*60}")
    print(f"# 深度学习模式 — {max_hours}h 窗口")
    print(f"# 开始: {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"# 截止: {time.strftime('%Y-%m-%d %H:%M', time.localtime(deadline))}")
    print(f"{'#'*60}")

    if progress_callback:
        progress_callback(f"🎓 深度学习开始 ({max_hours}h 窗口)")

    while True:
        remaining_hours = (deadline - time.time()) / 3600
        if remaining_hours < 0.5:
            print(f"\n[Scheduler] 剩余 {remaining_hours:.1f}h < 0.5h，收尾")
            break

        # 1. 从任务池取
        pool = _load_task_pool()
        task = None
        if pool:
            task = pool[0]  # 取优先级最高的
            print(f"\n[Scheduler] 从任务池取: {task['title']} (剩余 {remaining_hours:.1f}h)")
        else:
            # 2. 自主发现
            print(f"\n[Scheduler] 任务池空，自主发现新方向...")
            new_tasks = _discover_new_tasks()
            if new_tasks:
                # 加入任务池
                existing_pool = _load_task_pool()
                for nt in new_tasks:
                    nt["source"] = "auto_discover"
                    nt["discovered_at"] = time.strftime('%Y-%m-%d %H:%M')
                existing_pool.extend(new_tasks)
                _save_task_pool(existing_pool)
                task = new_tasks[0]
                print(f"  发现 {len(new_tasks)} 个新任务，开始: {task['title']}")
            else:
                print("[Scheduler] 无新任务可发现，结束")
                break

        # 3. 执行（完整五层管道）
        task_start = time.time()

        if progress_callback:
            progress_callback(
                f"📖 [{len(completed)+1}] {task['title']} "
                f"(剩余 {remaining_hours:.1f}h)"
            )

        report = deep_research_one(task, progress_callback=progress_callback)
        task_duration = (time.time() - task_start) / 60

        completed.append({
            "title": task["title"],
            "duration_min": round(task_duration, 1),
            "report_len": len(report) if report else 0
        })

        _mark_task_done(task.get("id", ""))
        print(f"\n✅ {task['title']} 完成 ({task_duration:.0f}min, {len(report) if report else 0}字)")

        if progress_callback:
            progress_callback(
                f"✅ {task['title']} ({task_duration:.0f}min)"
            )

        time.sleep(5)

    # 收尾: 运行 KB 治理
    print(f"\n[Scheduler] 任务完成，运行 KB 治理...")
    try:
        from scripts.kb_governance import run_governance
        gov_report = run_governance()
    except ImportError:
        gov_report = "KB 治理模块未安装"
        print(f"  [Warn] {gov_report}")

    # === 深度学习汇总报告 ===
    from src.tools.knowledge_base import get_knowledge_stats

    kb_stats_after = get_knowledge_stats()
    kb_total_after = sum(kb_stats_after.values())
    total_hours = (time.time() - start_time) / 3600

    summary_lines = [
        f"📊 深度学习完成报告",
        f"",
        f"⏱️ 耗时: {total_hours:.1f}h / {max_hours}h",
        f"📝 任务: {len(completed)} 个完成",
    ]

    for c in completed:
        summary_lines.append(f"  • {c['title']} ({c.get('duration_min', '?')}min)")

    summary_lines.append(f"")
    summary_lines.append(f"📚 KB 变化: {kb_total_before} → {kb_total_after} (+{kb_total_after - kb_total_before})")

    # Critic 统计
    p0_total = sum(1 for c in completed if c.get("p0_count", 0) > 0)
    summary_lines.append(f"🔍 Critic: {p0_total}/{len(completed)} 个任务触发 P0")

    # 元能力层统计
    try:
        from scripts.meta_capability import load_registry
        reg = load_registry()
        new_tools = [t for t in reg.get("tools", [])
                     if t.get("installed_at", "").startswith(time.strftime('%Y-%m-%d'))]
        if new_tools:
            summary_lines.append(f"🧬 元能力进化: +{len(new_tools)} 个新工具")
            for t in new_tools:
                summary_lines.append(f"  • {t['name']}: {t.get('description', '')[:40]}")
    except:
        pass

    # KB 治理
    if gov_report:
        summary_lines.append(f"🗄️ KB 治理: {gov_report}")

    summary = "\n".join(summary_lines)

    print(f"\n{'#'*60}")
    print(f"# 深度学习完成")
    print(f"# 耗时: {total_hours:.1f}h / {max_hours}h")
    print(f"# 任务: {len(completed)} 个")
    for c in completed:
        print(f"#   - {c['title']} ({c['duration_min']}min, {c['report_len']}字)")
    print(f"# KB 治理: {gov_report}")

    # 进化报告
    evolution_report = generate_evolution_report()
    print(f"\n{evolution_report}")

    print(f"{'#'*60}")

    if progress_callback:
        # 推送汇总报告
        progress_callback(summary)

        # 推送批量校准摘要
        try:
            from scripts.critic_calibration import push_batch_calibration_summary
            push_batch_calibration_summary(reply_func=progress_callback)
        except Exception as e:
            print(f"  [Calibration] 批量摘要推送失败: {e}")

    return completed


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # 支持命令行参数：python tonight_deep_research.py path/to/tasks.md [task_ids...]
        md_path = sys.argv[1]
        task_ids = sys.argv[2:] if len(sys.argv) > 2 else None
        run_research_from_file(md_path, task_ids=task_ids)
    else:
        # 默认运行内置任务
        run_all()