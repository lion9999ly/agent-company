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
# 并发控制: 按 provider 限制并发数（升级版 - 19 模型支持）
# ============================================================
PROVIDER_SEMAPHORES = {
    "o3_deep": threading.Semaphore(3),    # o3-deep-research 慢，3 并发
    "o3": threading.Semaphore(3),         # o3 推理模型，3 并发
    "o3_mini": threading.Semaphore(5),    # o3-mini 便宜，5 并发
    "grok": threading.Semaphore(3),       # Grok 社交搜索，3 并发
    "gemini_deep": threading.Semaphore(2),# Gemini Deep Research，限额低
    "doubao": threading.Semaphore(8),     # 豆包快，8 并发
    "flash": threading.Semaphore(8),      # Flash 提炼，8 并发
    "gemini_pro": threading.Semaphore(3), # Gemini Pro 系列，有限额
    "gpt54": threading.Semaphore(4),      # GPT-5.4 成本高
    "gpt53": threading.Semaphore(4),      # GPT-5.3
    "gpt4o": threading.Semaphore(4),      # GPT-4o 通用
    "deepseek_r1": threading.Semaphore(3),# DeepSeek R1 推理链长
    "qwen": threading.Semaphore(4),       # Qwen 中文
    "llama": threading.Semaphore(3),      # Llama 多模态
}


def _get_sem_key(model_name: str) -> str:
    """模型名 → 信号量 key（升级版 - 全模型支持）"""
    model_lower = model_name.lower()
    if "o3" in model_lower and "deep" in model_lower:
        return "o3_deep"
    elif "o3_mini" in model_lower or "o3-mini" in model_lower:
        return "o3_mini"
    elif "o3" in model_lower:
        return "o3"
    elif "grok" in model_lower:
        return "grok"
    elif "gemini" in model_lower and "deep" in model_lower:
        return "gemini_deep"
    elif "doubao" in model_lower:
        return "doubao"
    elif "flash" in model_lower:
        return "flash"
    elif "gemini" in model_lower and "pro" in model_lower:
        return "gemini_pro"
    elif "gpt_5_4" in model_lower or "gpt-5.4" in model_lower:
        return "gpt54"
    elif "gpt_5_3" in model_lower or "gpt-5.3" in model_lower:
        return "gpt53"
    elif "4o" in model_lower:
        return "gpt4o"
    elif "deepseek_r1" in model_lower or "deepseek-r1" in model_lower:
        return "deepseek_r1"
    elif "qwen" in model_lower:
        return "qwen"
    elif "llama" in model_lower:
        return "llama"
    return "gpt54"  # 默认保守


# ============================================================
# 降级映射表（升级版 - 全模型支持）
# ============================================================
FALLBACK_MAP = {
    "gpt_5_4": "gpt_5_3",                 # 5.4 → 5.3
    "gpt_5_3": "gpt_4o_norway",           # 5.3 → 4o
    "o3": "deepseek_r1",                  # o3 → DeepSeek R1（同为推理专家）
    "o3_mini": "gemini_2_5_flash",        # o3-mini → Flash
    "deepseek_r1": "o3_mini",             # R1 → o3-mini
    "grok_4": "gpt_4o_norway",            # Grok → 4o
    "gemini_deep_research": "o3_deep_research",  # Gemini Deep → o3 Deep
    "o3_deep_research": "gpt_5_4",        # o3 Deep → 5.4
    "doubao_seed_pro": "doubao_seed_lite",
    "gemini_3_1_pro": "gemini_3_pro",
    "gemini_3_pro": "gemini_2_5_pro",
    "gemini_2_5_pro": "gpt_5_3",          # Gemini Pro → 5.3
    "gemini_2_5_flash": "gpt_4o_norway",  # Flash → 4o（L2提炼降级）
    "qwen_3_32b": "deepseek_v3_2",        # Qwen → DeepSeek（都擅长中文）
    "llama_4_maverick": "gpt_4o_norway",
    "deepseek_v3_2": "qwen_3_32b",        # DeepSeek → Qwen（互为备选）
}


# ============================================================
# 模型路由辅助函数 —— 深度研究专用模型分层配置
# ============================================================
# 注意：不使用 Claude 系列模型

def _get_model_for_role(role: str) -> str:
    """深度研究 v3: 各角色模型分配（升级版）

    原则:
    - CTO/CPO: gpt_5_4（最强推理）→ gpt_4o_norway
    - CMO: gpt_5_3（深度分析）+ doubao 补充中文市场数据
    - CDO: gemini_3_1_pro（多模态）→ gemini_3_pro
    - 推理验证: o3（对 CTO 数值推算做独立验证）
    - 中文交叉: qwen_3_32b（对 CMO 中文市场结论做交叉验证）
    """
    role_model_map = {
        "CTO": "gpt_5_4",
        "CMO": "gpt_5_3",        # 升级：用 5.3 做深度分析
        "CDO": "gemini_3_1_pro",
        "CPO": "gpt_5_4",
        "VERIFIER": "o3",        # 新增：推理验证 Agent
        "CHINESE_CROSS": "qwen_3_32b",  # 新增：中文交叉验证
    }
    return role_model_map.get(role.upper(), "gpt_5_4")


def _get_model_for_task(task_type: str) -> str:
    """深度研究 v3: 各环节模型分配（升级版 - 四通道搜索 + Gemini Pro 整合）

    分层:
    - 搜索: o3_deep_research + doubao_seed_pro + grok_4 + gemini_deep_research（四通道并行）
    - 提炼: gemini_2_5_flash（便宜无限额）
    - 整合: gemini_2_5_pro（65K 上下文，能看完所有 Agent 输出）
    - Critic: gemini_3_1_pro + o3（双 Critic 交叉）
    """
    # W3: 尝试使用学习到的最佳模型
    learned_model = _select_best_model_learned(task_type)
    if learned_model:
        return learned_model

    task_model_map = {
        "discovery": "gemini_2_5_flash",
        "query_generation": "gemini_2_5_flash",
        "data_extraction": "gemini_2_5_flash",    # Layer 2 提炼
        "role_assign": "gemini_2_5_flash",
        "synthesis": "gemini_2_5_pro",             # Layer 4 整合（升级）
        "re_synthesis": "gemini_2_5_pro",
        "final_synthesis": "gemini_2_5_pro",
        "critic_challenge": "gemini_3_1_pro",      # Layer 5 主审
        "critic_cross": "o3",                      # Layer 5 交叉审查（新增）
        "consistency_check": "gemini_3_1_pro",
        "knowledge_extract": "gemini_2_5_flash",
        "fix": "gemini_2_5_pro",
        "cdo_fix": "gemini_2_5_pro",
        "chinese_search": "doubao_seed_pro",
        "deep_research_search": "o3_deep_research",
        "grok_search": "grok_4",                   # 社交搜索（新增）
        "gemini_deep_search": "gemini_deep_research",  # 学术深挖（新增）
        "deep_drill_conclusion": "gpt_5_4",
        "debate": "gpt_5_3",                       # Agent 辩论
        "analogy": "gemini_2_5_flash",
        "sandbox": "o3",                           # 沙盘推演用 o3（65K output）
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
# A-1: F2 深钻模式 — 对单个主题连续多轮深入研究
# ============================================================

def deep_drill(topic: str, max_rounds: int = 4, progress_callback=None) -> str:
    """深钻模式：对一个主题连续多轮深入研究

    第 1 轮: 广搜 — 搜索该主题的全面信息
    第 2 轮: 追问 — 基于第 1 轮发现的疑点和缺口，生成新的搜索词深入
    第 3 轮: 验证 — 对矛盾数据点交叉验证
    第 4 轮: 结论 — 整合所有轮次发现，形成结论性报告

    每轮的输出作为下一轮的输入。
    """
    all_findings = []

    for round_num in range(1, max_rounds + 1):
        round_type = {1: "广搜", 2: "追问", 3: "验证", 4: "结论"}
        print(f"\n  [DeepDrill] 第 {round_num} 轮: {round_type.get(round_num, '深入')}")

        if progress_callback:
            progress_callback(f"深钻 [{round_num}/{max_rounds}] {topic}: {round_type.get(round_num, '深入')}")

        if round_num == 1:
            # 第 1 轮: 广搜
            task = {
                "title": f"深钻-{topic}-广搜",
                "goal": f"全面搜索关于 {topic} 的信息，包括技术参数、供应商、价格、竞品、用户评价",
                "searches": _generate_drill_queries(topic, "broad"),
            }
        elif round_num == 2:
            # 第 2 轮: 基于上轮发现追问
            gaps = _extract_gaps_from_findings(all_findings[-1] if all_findings else "")
            task = {
                "title": f"深钻-{topic}-追问",
                "goal": f"针对以下疑点深入调查:\n{gaps}",
                "searches": _generate_drill_queries(topic, "deep", context=all_findings[-1] if all_findings else ""),
            }
        elif round_num == 3:
            # 第 3 轮: 验证矛盾点
            contradictions = _extract_contradictions(all_findings)
            if not contradictions:
                print(f"  [DeepDrill] 无矛盾数据，跳过验证轮")
                continue
            task = {
                "title": f"深钻-{topic}-验证",
                "goal": f"验证以下矛盾数据:\n{contradictions}",
                "searches": _generate_drill_queries(topic, "verify", context=contradictions),
            }
        else:
            # 第 4 轮: 形成结论（不搜索，直接整合）
            conclusion_prompt = (
                f"基于以下 {len(all_findings)} 轮深钻研究的全部发现，"
                f"形成关于 {topic} 的最终结论报告。\n\n"
                + "\n\n---\n\n".join([f"## 第{i+1}轮\n{f[:2000]}" for i, f in enumerate(all_findings)])
            )
            result = _call_model("gpt_5_4", conclusion_prompt,
                                  "你是高级分析师，输出结构化的结论报告。", "deep_drill_conclusion")
            if result.get("success"):
                all_findings.append(result["response"])
            break

        # 执行研究（复用 deep_research_one 的 Layer 1-3）
        if round_num < 4:
            report = deep_research_one(task, progress_callback=progress_callback)
            all_findings.append(report)

    # 合并所有发现
    final_report = "\n\n".join([f"## 第{i+1}轮\n{f}" for i, f in enumerate(all_findings)])

    # 入库
    add_knowledge(
        title=f"[深钻] {topic}",
        domain="lessons",
        content=final_report[:2000],
        tags=["deep_drill", topic],
        source="deep_drill",
        confidence="high"  # 多轮验证后的结论
    )

    return final_report


def _generate_drill_queries(topic: str, mode: str, context: str = "") -> list:
    """生成深钻搜索词"""
    prompt = f"为主题 '{topic}' 生成 6-8 个搜索关键词。"
    if mode == "broad":
        prompt += "\n搜索方向: 全面覆盖（技术、市场、供应商、竞品、用户）"
    elif mode == "deep":
        prompt += f"\n搜索方向: 针对以下发现中的疑点和缺口深入追问:\n{context[:1000]}"
    elif mode == "verify":
        prompt += f"\n搜索方向: 验证以下矛盾数据点:\n{context[:1000]}"
    prompt += "\n只输出搜索词列表，每行一个。"

    result = _call_model("gemini_2_5_flash", prompt, task_type="query_generation")
    if result.get("success"):
        queries = [q.strip() for q in result["response"].strip().split("\n") if q.strip()]
        return queries[:8]
    return [topic]


def _extract_gaps_from_findings(findings: str) -> str:
    """从研究发现中提取知识缺口和疑点"""
    result = _call_model("gemini_2_5_flash",
        f"从以下研究发现中，提取 3-5 个还不清楚的疑点、数据缺口或需要深入的方向:\n\n{findings[:2000]}\n\n只输出疑点列表。",
        task_type="query_generation")
    return result.get("response", "") if result.get("success") else ""


def _extract_contradictions(all_findings: list) -> str:
    """从多轮发现中提取矛盾数据"""
    combined = "\n---\n".join([f[:1000] for f in all_findings])
    result = _call_model("gemini_2_5_flash",
        f"从以下多轮研究中，找出数据矛盾的地方（同一个指标出现了不同的值）:\n\n{combined}\n\n只输出矛盾列表。如果没有矛盾，输出'无矛盾'。",
        task_type="query_generation")
    resp = result.get("response", "") if result.get("success") else ""
    if "无矛盾" in resp:
        return ""
    return resp


# ============================================================
# A-2: F3 Agent 辩论机制 — 检测分歧并交锋
# ============================================================

def _run_agent_debate(agent_outputs: dict, goal: str, evidence: str) -> dict:
    """检测 Agent 间分歧，触发交锋，生成裁决

    流程:
    1. 用 Flash 检测分歧点
    2. 如果有分歧，让持不同意见的 Agent 交锋
    3. 用 gpt-5.4 做最终裁决
    """
    # Step 1: 检测分歧
    combined = "\n\n".join([f"[{role}]\n{output[:1500]}" for role, output in agent_outputs.items()])
    detect_prompt = (
        f"以下是不同 Agent 对同一研究任务的分析：\n\n{combined}\n\n"
        f"找出他们之间的观点分歧（如果有的话）。\n"
        f"输出 JSON: {{\"has_conflict\": true/false, \"conflicts\": ["
        f"{{\"topic\": \"分歧主题\", \"side_a\": {{\"agent\": \"CTO\", \"position\": \"观点\"}}, "
        f"\"side_b\": {{\"agent\": \"CMO\", \"position\": \"观点\"}}}}]}}\n"
        f"如果没有实质性分歧，has_conflict=false。只输出 JSON。"
    )
    detect_result = _call_model("gemini_2_5_flash", detect_prompt, task_type="data_extraction")
    if not detect_result.get("success"):
        return agent_outputs

    try:
        resp = detect_result["response"].strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        conflicts = json.loads(resp)
    except:
        return agent_outputs

    if not conflicts.get("has_conflict") or not conflicts.get("conflicts"):
        print("  [Debate] 无实质分歧")
        return agent_outputs

    print(f"  [Debate] 发现 {len(conflicts['conflicts'])} 个分歧点，开始交锋...")

    # Step 2: 交锋
    debate_record = []
    for conflict in conflicts["conflicts"][:2]:  # 最多处理 2 个分歧
        topic = conflict.get("topic", "")
        side_a = conflict.get("side_a", {})
        side_b = conflict.get("side_b", {})

        # 让 side_a 用数据反驳 side_b
        rebuttal_a = _call_model(
            _get_model_for_role(side_a.get("agent", "CTO")),
            f"你之前的观点是：{side_a.get('position', '')}\n"
            f"{side_b.get('agent', 'CMO')} 的反对观点是：{side_b.get('position', '')}\n"
            f"请用具体数据反驳或承认对方有道理。\n"
            f"参考数据:\n{evidence[:2000]}",
            task_type="debate"
        )

        # 让 side_b 用数据反驳 side_a
        rebuttal_b = _call_model(
            _get_model_for_role(side_b.get("agent", "CMO")),
            f"你之前的观点是：{side_b.get('position', '')}\n"
            f"{side_a.get('agent', 'CTO')} 的反驳是：{rebuttal_a.get('response', '')[:500]}\n"
            f"请用具体数据回应。\n"
            f"参考数据:\n{evidence[:2000]}",
            task_type="debate"
        )

        debate_record.append({
            "topic": topic,
            "side_a": {"agent": side_a.get("agent"), "rebuttal": rebuttal_a.get("response", "")[:500]},
            "side_b": {"agent": side_b.get("agent"), "rebuttal": rebuttal_b.get("response", "")[:500]},
        })

    # Step 3: 裁决（追加到 agent_outputs）
    debate_text = json.dumps(debate_record, ensure_ascii=False, indent=2)
    agent_outputs["_debate"] = (
        f"\n## Agent 辩论记录\n\n"
        f"以下分歧经过交锋后的记录，synthesis 请在整合时重点关注并裁决：\n\n"
        f"{debate_text[:3000]}"
    )
    print(f"  [Debate] 交锋完成，{len(debate_record)} 个分歧点记录已注入 synthesis")

    return agent_outputs


# ============================================================
# A-3: G2 跨任务知识传递
# ============================================================

FINDINGS_PATH = Path(__file__).parent.parent / ".ai-state" / "task_findings.jsonl"

def _save_task_findings(task_title: str, report: str):
    """从报告中提取 3-5 个关键发现，存入 findings 日志"""
    result = _call_model("gemini_2_5_flash",
        f"从以下研究报告中提取 3-5 个最关键的发现（具体数据点，不是泛泛总结）:\n\n"
        f"{report[:3000]}\n\n"
        f"输出 JSON 数组: [{{\"finding\": \"具体发现\", \"keywords\": [\"关键词1\", \"关键词2\"]}}]",
        task_type="knowledge_extract")
    if result.get("success"):
        try:
            findings = json.loads(re.sub(r'^```json\s*|\s*```$', '', result["response"].strip()))
            entry = {"task_title": task_title, "timestamp": time.strftime('%Y-%m-%d %H:%M'), "findings": findings}
            FINDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(FINDINGS_PATH, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            print(f"  [Findings] 保存 {len(findings)} 个关键发现")
        except:
            pass


def _get_related_findings(task_title: str, task_goal: str, limit: int = 5) -> str:
    """检索与当前任务相关的历史发现"""
    if not FINDINGS_PATH.exists():
        return ""
    keywords = set(re.findall(r'[\u4e00-\u9fff]{2,4}|[A-Z][a-z]+|[A-Z]{2,}', task_title + " " + task_goal))
    related = []
    for line in FINDINGS_PATH.read_text(encoding='utf-8').strip().split('\n'):
        try:
            entry = json.loads(line)
            for f in entry.get("findings", []):
                f_keywords = set(f.get("keywords", []))
                overlap = keywords & f_keywords
                if overlap:
                    related.append((len(overlap), f["finding"], entry["task_title"]))
        except:
            continue
    related.sort(reverse=True)
    if not related:
        return ""
    text = "\n## 前序任务的相关发现\n"
    for _, finding, source in related[:limit]:
        text += f"- [{source}] {finding}\n"
    return text


# ============================================================
# A-4: G3 报告摘要层 — 生成 3 句话摘要
# ============================================================

def _generate_report_summary(report: str, task_title: str) -> dict:
    """生成报告的 3 句话摘要"""
    result = _call_model("gemini_2_5_flash",
        f"为以下研究报告生成 3 句话摘要:\n"
        f"第 1 句: 核心发现（最重要的一个结论）\n"
        f"第 2 句: 关键数据点（最有决策价值的一个数字）\n"
        f"第 3 句: 对产品决策的影响（这个发现意味着什么）\n\n"
        f"报告标题: {task_title}\n"
        f"报告内容:\n{report[:3000]}\n\n"
        f"输出 JSON: {{\"core_finding\": \"...\", \"key_data\": \"...\", \"decision_impact\": \"...\"}}",
        task_type="knowledge_extract")
    if result.get("success"):
        try:
            return json.loads(re.sub(r'^```json\s*|\s*```$', '', result["response"].strip()))
        except:
            pass
    return {}


# ============================================================
# A-5: G4 好奇心驱动 — 意外发现检测与任务追加
# ============================================================

def _process_serendipity(structured_data_list: list, progress_callback=None):
    """处理意外发现，追加到任务池"""
    serendipities = []
    for data in structured_data_list:
        if isinstance(data, dict):
            for s in data.get("serendipity", []):
                serendipities.append(s)

    if not serendipities:
        return

    print(f"  [Curiosity] 发现 {len(serendipities)} 个意外线索")

    pool = _load_task_pool()
    for s in serendipities[:3]:
        new_task = {
            "id": f"curiosity_{int(time.time())}",
            "title": f"[好奇心] {s.get('finding', '')[:40]}",
            "goal": f"深入调查意外发现: {s.get('finding', '')}。潜在价值: {s.get('potential_value', '')}",
            "priority": 3,
            "source": "serendipity",
            "discovered_at": time.strftime('%Y-%m-%d %H:%M'),
            "searches": [s.get("finding", "")[:50]],
        }
        pool.append(new_task)
        print(f"  [Curiosity] 追加任务: {new_task['title']}")
    _save_task_pool(pool)


# ============================================================
# A-6: H1 经验法则提取 — 从 KB 提取可复用模式
# ============================================================

def _extract_experience_rules():
    """从 KB 中提取经验法则"""
    groups = {}
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            title = data.get("title", "")
            for entity in ["歌尔", "立讯", "Cardo", "Sena", "JBD", "Sony", "OLED", "MicroLED"]:
                if entity.lower() in title.lower():
                    if entity not in groups:
                        groups[entity] = []
                    groups[entity].append(data)
        except:
            continue

    rules_found = 0
    for entity, entries in groups.items():
        if len(entries) < 5:
            continue

        entries_text = "\n".join([f"- {e.get('title', '')}: {e.get('content', '')[:200]}" for e in entries[:10]])
        result = _call_model("gemini_2_5_flash",
            f"以下是关于 {entity} 的 {len(entries)} 条知识库条目:\n\n{entries_text}\n\n"
            f"从中提取可复用的经验法则或模式（如果有的话）。\n"
            f"例如: '该供应商首次报价通常是最终成本的 X%' 或 '该技术每年降价约 Y%'\n"
            f"如果数据不足以提取可靠模式，输出'数据不足'。\n"
            f"输出 JSON: [{{\"rule\": \"经验法则\", \"sample_count\": N, \"confidence\": 0.0-1.0}}]",
            task_type="knowledge_extract")

        if result.get("success") and "数据不足" not in result["response"]:
            try:
                rules = json.loads(re.sub(r'^```json\s*|\s*```$', '', result["response"].strip()))
                for rule in rules:
                    add_knowledge(
                        title=f"[经验法则] {entity}: {rule.get('rule', '')[:50]}",
                        domain="lessons",
                        content=f"{rule.get('rule', '')}\n\n基于 {rule.get('sample_count', '?')} 个样本，置信度 {rule.get('confidence', '?')}",
                        tags=["experience_rule", entity, "derived"],
                        source="pattern_extraction",
                        confidence="medium"
                    )
                    rules_found += 1
            except:
                pass

    print(f"  [Rules] 提取 {rules_found} 条经验法则")


# ============================================================
# A-7: J1 趋势预测 — 时间序列数据外推
# ============================================================

PREDICTIONS_PATH = Path(__file__).parent.parent / ".ai-state" / "predictions.jsonl"

def _generate_trend_predictions():
    """对 KB 中有时间序列的数据做趋势外推"""
    # 收集有多个时间点的指标
    time_series_data = {}
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            content = data.get("content", "")
            title = data.get("title", "")
            # 提取数字和年份
            year_matches = re.findall(r'(20\d{2})', content)
            number_matches = re.findall(r'(\d+\.?\d*)\s*(美元|元|USD|\$|mm|g|mAh|W|V|%)', content)
            if year_matches and number_matches:
                for year, (value, unit) in zip(year_matches, number_matches):
                    key = f"{title[:30]}_{unit}"
                    if key not in time_series_data:
                        time_series_data[key] = []
                    time_series_data[key].append({"year": year, "value": float(value)})
        except:
            continue

    predictions = []
    for key, points in time_series_data.items():
        if len(points) < 3:
            continue
        # 按年份排序
        points.sort(key=lambda x: x["year"])
        # 简单线性趋势预测
        years = [int(p["year"]) for p in points]
        values = [p["value"] for p in points]
        if len(set(years)) < 2:
            continue
        # 线性回归
        n = len(years)
        sum_x = sum(years)
        sum_y = sum(values)
        sum_xy = sum(x * y for x, y in zip(years, values))
        sum_xx = sum(x * x for x in years)
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x) if n * sum_xx != sum_x * sum_x else 0
        intercept = (sum_y - slope * sum_x) / n
        # 预测未来 12 个月
        next_year = max(years) + 1
        predicted_value = slope * next_year + intercept
        predictions.append({
            "topic": key,
            "historical": points,
            "prediction_12m": round(predicted_value, 2),
            "trend": "increasing" if slope > 0 else "decreasing",
            "confidence": "low"  # 简单线性回归置信度低
        })

    if predictions:
        with open(PREDICTIONS_PATH, 'a', encoding='utf-8') as f:
            for pred in predictions:
                pred["timestamp"] = time.strftime('%Y-%m-%d %H:%M')
                f.write(json.dumps(pred, ensure_ascii=False) + "\n")
        print(f"  [Trends] 生成 {len(predictions)} 个趋势预测")


# ============================================================
# A-8: J4 方案压力测试 — 极端场景分析
# ============================================================

def stress_test_product(plan_description: str = "", progress_callback=None) -> str:
    """对产品方案做极端场景压力测试"""
    # 生成 15-20 个极端场景
    scenarios_prompt = (
        f"你是产品风险分析师。针对以下产品方案，生成 15-20 个极端场景:\n\n"
        f"{plan_description[:2000]}\n\n"
        f"场景类型:\n"
        f"- 环境极端（高温、极寒、暴雨、沙尘）\n"
        f"- 使用极端（连续骑行 12h、摔车、高速冲击）\n"
        f"- 技术故障（GPS 丢失、电池耗尽、系统崩溃）\n"
        f"- 用户极端（老年用户、听力障碍、新手）\n"
        f"- 供应链中断（芯片缺货、供应商倒闭）\n\n"
        f"输出 JSON 数组: [{{\"scenario\": \"场景描述\", \"impact\": \"高/中/低\"}}]"
    )
    result = _call_model("gpt_5_4", scenarios_prompt, "只输出 JSON 数组。", "stress_test")
    if not result.get("success"):
        return "压力测试失败"

    try:
        scenarios = json.loads(re.sub(r'^```json\s*|\s*```$', '', result["response"].strip()))
    except:
        return "场景解析失败"

    # 逐个场景检查方案是否有应对设计
    test_results = []
    for scenario in scenarios[:15]:
        check_prompt = (
            f"产品方案:\n{plan_description[:1500]}\n\n"
            f"极端场景: {scenario.get('scenario', '')}\n\n"
            f"检查方案中是否有应对此场景的设计。\n"
            f"输出 JSON: {{\"handled\": true/false, \"gap\": \"缺失的应对措施（如果有）\"}}"
        )
        check_result = _call_model("gemini_2_5_flash", check_prompt, "只输出 JSON。", "stress_check")
        if check_result.get("success"):
            try:
                check_data = json.loads(re.sub(r'^```json\s*|\s*```$', '', check_result["response"].strip()))
                test_results.append({
                    "scenario": scenario.get("scenario"),
                    "impact": scenario.get("impact"),
                    **check_data
                })
            except:
                pass

    # 生成韧性评估报告
    handled_count = sum(1 for r in test_results if r.get("handled"))
    resilience_score = handled_count / len(test_results) * 100 if test_results else 0

    report = f"# 产品方案压力测试报告\n\n"
    report += f"## 韧性评分: {resilience_score:.0f}%\n\n"
    report += f"- 测试场景数: {len(test_results)}\n"
    report += f"- 已覆盖场景: {handled_count}\n"
    report += f"- 未覆盖场景: {len(test_results) - handled_count}\n\n"
    report += "## 未覆盖场景详情\n\n"
    for r in test_results:
        if not r.get("handled"):
            report += f"- **{r.get('scenario')}** (影响: {r.get('impact')})\n"
            report += f"  缺失: {r.get('gap', '未说明')}\n\n"

    return report


# ============================================================
# A-9: Kn1 知识综述生成 — 整合碎片知识
# ============================================================

def _generate_knowledge_synthesis():
    """扫描 KB，对碎片知识生成综述"""
    from collections import Counter

    topic_groups = {}
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            if data.get("type") == "synthesis":
                continue  # 跳过已有综述
            title = data.get("title", "")
            for keyword in ["HUD", "光学", "歌尔", "Cardo", "Sena", "MicroLED", "OLED", "Mesh", "ANC", "传感器", "认证"]:
                if keyword.lower() in title.lower():
                    if keyword not in topic_groups:
                        topic_groups[keyword] = []
                    topic_groups[keyword].append(data)
        except:
            continue

    for topic, entries in topic_groups.items():
        if len(entries) < 10:
            continue

        entries_text = "\n".join([f"- {e.get('title','')}: {e.get('content','')[:200]}" for e in entries[:20]])
        result = _call_model("gpt_5_4",
            f"以下是关于 '{topic}' 的 {len(entries)} 条知识库碎片。\n"
            f"请整合成一篇结构化综述（1000-1500字），包含：\n"
            f"1. 技术/市场现状概览\n2. 关键供应商/竞品对比\n3. 成本结构\n4. 风险和机会\n5. 决策建议\n\n"
            f"知识碎片:\n{entries_text}",
            "你是行业分析师，用数据说话。", "synthesis")

        if result.get("success"):
            add_knowledge(
                title=f"[综述] {topic} 全景分析",
                domain="lessons",
                content=result["response"],
                tags=["synthesis", topic],
                source="auto_synthesis",
                confidence="high"
            )
            print(f"  [Synthesis] 生成综述: {topic}（基于 {len(entries)} 条碎片）")


# ============================================================
# A-10: Kn2 类比推理引擎 — 跨领域推理
# ============================================================

def _try_analogy_reasoning(query: str, kb_results: list) -> str:
    """当 KB 直接数据不足时，尝试类比推理"""
    if len(kb_results) >= 3:
        return ""  # 直接数据足够，不需要类比

    analogy_domains = {
        "骑行头盔 HUD": ["汽车 HUD", "战斗机 HUD", "AR 眼镜"],
        "骑行头盔 ANC": ["TWS 耳机 ANC", "头戴式耳机 ANC"],
        "骑行头盔 市场": ["智能手表市场", "运动相机市场", "TWS 耳机市场"],
        "Mesh 组队": ["对讲机市场", "游戏语音组队"],
    }

    best_domain = None
    for key, analogies in analogy_domains.items():
        if any(kw in query for kw in key.split()):
            best_domain = analogies
            break

    if not best_domain:
        return ""

    result = _call_model("gemini_2_5_flash",
        f"问题: {query}\n"
        f"直接数据不足。请用以下类似领域的数据做类比推理:\n"
        f"类比领域: {', '.join(best_domain)}\n\n"
        f"输出格式:\n⚡ 类比推理（非直接数据）\n"
        f"类比来源: [领域]\n推理: [具体推理]\n置信度: [低/中]",
        task_type="analogy")

    if result.get("success"):
        return f"\n\n{result['response']}"
    return ""


# ============================================================
# A-11: M4 信息增量感知的预算路由 — 按覆盖度选模型
# ============================================================

def _assess_kb_coverage(query: str) -> float:
    """评估 KB 对某个 query 的已有覆盖度 (0.0-1.0)"""
    results = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            content = data.get("content", "")
            title = data.get("title", "")
            if query.lower() in title.lower() or query.lower() in content[:500].lower():
                results.append(data)
        except:
            continue
    if not results:
        return 0.0
    high_conf = sum(1 for r in results if r.get("confidence") in ("high", "authoritative"))
    return min(1.0, (len(results) * 0.1) + (high_conf * 0.15))


def _select_model_by_coverage(query: str, default_model: str) -> str:
    """根据 KB 覆盖度选择模型——覆盖度低用强模型，覆盖度高用便宜模型"""
    coverage = _assess_kb_coverage(query)
    if coverage > 0.7:
        print(f"  [Budget] KB 覆盖度 {coverage:.0%}，用 Flash 补充")
        return "gemini_2_5_flash"
    elif coverage > 0.4:
        print(f"  [Budget] KB 覆盖度 {coverage:.0%}，用默认模型")
        return default_model
    else:
        print(f"  [Budget] KB 覆盖度 {coverage:.0%}，用最强模型深搜")
        return "o3_deep_research"


# ============================================================
# A-12: N1 反脆弱运行 — API 失败时切换离线任务
# ============================================================

def _fallback_to_offline_tasks(failed_model: str, failed_query: str):
    """API 全部失败时切换到离线任务"""
    print(f"  [AntiFragile] {failed_model} 全部失败，切换离线任务")

    offline_tasks = [
        ("KB治理", lambda: _run_kb_governance_lite()),
        ("知识综述", lambda: _generate_knowledge_synthesis()),
        ("决策树扫描", lambda: _scan_decision_readiness()),
        ("工作记忆整理", lambda: _organize_work_memory()),
    ]

    for name, task_fn in offline_tasks:
        try:
            print(f"  [AntiFragile] 执行离线任务: {name}")
            task_fn()
        except:
            pass


def _run_kb_governance_lite():
    """轻量级 KB 治理"""
    _extract_experience_rules()
    _generate_knowledge_synthesis()


def _scan_decision_readiness():
    """扫描决策树就绪状态"""
    decision_tree_path = Path(__file__).parent.parent / ".ai-state" / "product_decision_tree.yaml"
    if not decision_tree_path.exists():
        return
    try:
        with open(decision_tree_path, 'r', encoding='utf-8') as f:
            tree = yaml.safe_load(f)
        for decision in tree.get("decisions", []):
            gaps = decision.get("blocking_knowledge", [])
            ready = len(gaps) == 0
            print(f"  [Decision] {decision.get('id')}: {'就绪' if ready else f'缺 {len(gaps)} 项'}")
    except:
        pass


def _organize_work_memory():
    """整理工作记忆"""
    # 清理过期的临时文件
    temp_dir = Path(__file__).parent.parent / ".ai-state" / "temp"
    if temp_dir.exists():
        for f in temp_dir.glob("*"):
            if f.stat().st_mtime < time.time() - 86400:  # 24小时前
                f.unlink()


# ============================================================
# A-13: O3 对抗性数据验证 — 数据口径质疑
# ============================================================

ADVERSARIAL_PROMPT_SUFFIX = """
对每个关键数据点（价格、产能、良率、功耗等数值），追加以下字段：
"data_caveat": {
    "price_basis": "含税/不含税/未知",
    "volume_basis": "样品/千片/万片/未知",
    "time_basis": "2024/2025/2026/未知",
    "source_type": "官方datasheet/新闻报道/分析师估算/论坛帖子/未知",
    "needs_clarification": true/false
}
如果以上任何字段为"未知"，则 needs_clarification 必须为 true。
"""


# ============================================================
# A-14: O4 沙盘 What-If 模式 — 参数变更影响推演
# ============================================================

def sandbox_what_if(parameter_change: str, kb_context: str = "", progress_callback=None) -> str:
    """沙盘推演：调整一个参数，推算连锁影响"""
    prompt = (
        f"产品: 智能骑行头盔 V1\n"
        f"参数变更: {parameter_change}\n\n"
        f"已知产品参数和约束:\n{kb_context[:3000]}\n\n"
        f"请推演这个变更的连锁影响链条。每一步标注:\n"
        f"1. 直接影响（确定性高）\n"
        f"2. 间接影响（确定性中）\n"
        f"3. 远端影响（确定性低）\n\n"
        f"对每个影响给出具体数值估算（如有数据支撑）或定性判断。\n"
        f"最终给出：这个变更是否值得做？代价是什么？"
    )
    result = gateway.call("o3", prompt,
        "你是系统工程师，擅长因果链条推理。每一步必须有依据。", "sandbox")
    return result.get("response", "") if result.get("success") else "推演失败"


# ============================================================
# A-15: P4 竞品界面素材库 — 自动收集截图
# ============================================================

COMPETITIVE_UI_PATH = Path(__file__).parent.parent / ".ai-state" / "competitive_ui"

def _collect_competitive_ui(url: str, source_name: str):
    """检测并保存竞品界面截图 URL"""
    if not url:
        return

    # 检测是否是图片 URL
    image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
    if any(ext in url.lower() for ext in image_extensions):
        COMPETITIVE_UI_PATH.mkdir(parents=True, exist_ok=True)
        # 记录 URL 和来源
        record_path = COMPETITIVE_UI_PATH / "ui_assets.jsonl"
        entry = {
            "url": url,
            "source": source_name,
            "timestamp": time.strftime('%Y-%m-%d %H:%M')
        }
        with open(record_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"  [UI Asset] 记录: {url[:60]}...")


# ============================================================
# A-16: Q2 数值计算引擎 — Python 计算替代 LLM 猜测
# ============================================================

CALC_PATTERN = re.compile(r'\[CALC:\s*([^\]]+)\]')

def _evaluate_calculations(text: str) -> str:
    """扫描输出中的 [CALC: expression] 标记，用 Python 执行并回填结果"""
    def replace_calc(match):
        expr = match.group(1)
        try:
            # 安全评估：只允许数学运算
            allowed_chars = set('0123456789.+-*/() ')
            if all(c in allowed_chars for c in expr):
                result = eval(expr)
                return f"[CALC: {expr}] = {result:.2f}"
            else:
                return f"[CALC: {expr}] = (不安全表达式)"
        except Exception as e:
            return f"[CALC: {expr}] = (计算错误: {str(e)[:30]})"

    return CALC_PATTERN.sub(replace_calc, text)


# ============================================================
# A-17: Q3 推理链可见化 — 展示推理过程
# ============================================================

REASONING_CHAIN_PROMPT = """
请在结论之前展示推理过程：
- 数据来源 → 推论 → 结论
- 如果多个数据指向不同结论，说明为什么选择了这个结论

格式示例:
## 推理链
1. 数据来源: [来源A] 显示 X
2. 推论: 基于 X，可以推断 Y
3. 冲突处理: [来源B] 显示 Z，但选择 Y 因为 [理由]
4. 结论: 最终判断为 Y
"""


# ============================================================
# A-18: Q5 系统自评分 — 输出质量评估
# ============================================================

SELF_ASSESSMENT_PATH = Path(__file__).parent.parent / ".ai-state" / "self_assessments.jsonl"

def _run_self_assessment(report: str, task_title: str, search_count: int, structured_count: int):
    """评估本次产出质量"""
    assessment_prompt = (
        f"评估以下研究报告的质量（1-10分）:\n\n"
        f"报告标题: {task_title}\n"
        f"报告长度: {len(report)} 字\n"
        f"搜索结果数: {search_count}\n"
        f"结构化数据条数: {structured_count}\n\n"
        f"评估维度:\n"
        f"1. 数据密度（具体数字/参数的比例）\n"
        f"2. 结论明确度（是否有明确推荐）\n"
        f"3. 来源标注（是否标注数据来源）\n"
        f"4. 决策支撑度（是否帮助决策）\n\n"
        f"输出 JSON: {{\"overall\": 1-10, \"data_density\": 1-10, \"clarity\": 1-10, "
        f"\"sourcing\": 1-10, \"decision_support\": 1-10, \"issues\": [\"问题1\", \"问题2\"]}}"
    )
    result = _call_model("gemini_2_5_flash", assessment_prompt, "只输出 JSON。", "self_assessment")
    if result.get("success"):
        try:
            assessment = json.loads(re.sub(r'^```json\s*|\s*```$', '', result["response"].strip()))
            assessment["task_title"] = task_title
            assessment["timestamp"] = time.strftime('%Y-%m-%d %H:%M')
            assessment["report_length"] = len(report)
            with open(SELF_ASSESSMENT_PATH, 'a', encoding='utf-8') as f:
                f.write(json.dumps(assessment, ensure_ascii=False) + "\n")
            print(f"  [SelfAssess] 评分: {assessment.get('overall', '?')}/10")
            return assessment
        except:
            pass
    return {}


# ============================================================
# W1: 搜索策略学习 — 记录什么搜索词有效
# ============================================================

SEARCH_LEARNING_PATH = Path(__file__).parent.parent / ".ai-state" / "search_learning.jsonl"
SEARCH_BEST_PRACTICES_PATH = Path(__file__).parent.parent / ".ai-state" / "search_best_practices.yaml"

def _record_search_result(query: str, model: str, tokens: int, useful_findings: int, quality: str):
    """记录搜索结果用于学习"""
    entry = {
        "query": query,
        "model": model,
        "tokens": tokens,
        "useful_findings": useful_findings,
        "quality": quality,  # high/medium/low
        "timestamp": time.strftime('%Y-%m-%d %H:%M')
    }
    SEARCH_LEARNING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SEARCH_LEARNING_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _evolve_search_strategy():
    """从搜索历史中提取最佳实践"""
    if not SEARCH_LEARNING_PATH.exists():
        return

    # 读取最近 50 条搜索记录
    lines = SEARCH_LEARNING_PATH.read_text(encoding='utf-8').strip().split('\n')[-50:]
    if len(lines) < 10:
        return

    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except:
            continue

    # 按 quality 分组统计
    quality_map = {"high": 3, "medium": 2, "low": 1}
    model_stats = {}
    keyword_patterns = {"price": [], "技术": [], "2024": [], "2025": [], "2026": []}

    for r in records:
        model = r.get("model", "")
        quality = quality_map.get(r.get("quality", "low"), 1)
        if model not in model_stats:
            model_stats[model] = {"total": 0, "score": 0}
        model_stats[model]["total"] += 1
        model_stats[model]["score"] += quality

        # 检查关键词模式
        query = r.get("query", "").lower()
        for kw in keyword_patterns:
            if kw in query:
                keyword_patterns[kw].append(quality)

    # 生成最佳实践
    best_practices = {
        "model_ranking": sorted(model_stats.items(), key=lambda x: x[1]["score"]/x[1]["total"], reverse=True)[:3],
        "keyword_effectiveness": {k: sum(v)/len(v) if v else 0 for k, v in keyword_patterns.items()},
        "updated_at": time.strftime('%Y-%m-%d %H:%M')
    }

    with open(SEARCH_BEST_PRACTICES_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(best_practices, f, allow_unicode=True)
    print(f"  [SearchLearning] 更新搜索最佳实践")


def _get_optimized_search_model(query: str) -> str:
    """基于学习结果选择最佳搜索模型"""
    if not SEARCH_BEST_PRACTICES_PATH.exists():
        return "o3_deep_research"  # 默认

    try:
        with open(SEARCH_BEST_PRACTICES_PATH, 'r', encoding='utf-8') as f:
            practices = yaml.safe_load(f)

        model_ranking = practices.get("model_ranking", [])
        if model_ranking:
            best_model = model_ranking[0][0]
            return best_model
    except:
        pass
    return "o3_deep_research"


# ============================================================
# W2: Agent prompt 自进化 — 从 Critic P0 学教训
# ============================================================

AGENT_LESSONS_PATH = Path(__file__).parent.parent / ".ai-state" / "agent_lessons.yaml"

def _learn_from_p0(agent_role: str, p0_issue: str, cal_id: str = ""):
    """从 P0 问题中学习，追加到 Agent 教训列表"""
    if not AGENT_LESSONS_PATH.exists():
        lessons = {}
    else:
        try:
            with open(AGENT_LESSONS_PATH, 'r', encoding='utf-8') as f:
                lessons = yaml.safe_load(f) or {}
        except:
            lessons = {}

    if agent_role not in lessons:
        lessons[agent_role] = []

    lesson = f"{p0_issue[:100]}（来源: P0 {cal_id}）"
    if lesson not in lessons[agent_role]:
        lessons[agent_role].append(lesson)
        with open(AGENT_LESSONS_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(lessons, f, allow_unicode=True)
        print(f"  [AgentLesson] {agent_role} 新增教训: {p0_issue[:50]}...")


def _get_agent_prompt_with_lessons(role: str, base_prompt: str) -> str:
    """获取带教训注入的 Agent prompt"""
    if not AGENT_LESSONS_PATH.exists():
        return base_prompt

    try:
        with open(AGENT_LESSONS_PATH, 'r', encoding='utf-8') as f:
            lessons = yaml.safe_load(f) or {}

        role_lessons = lessons.get(role.upper(), [])
        if role_lessons:
            base_prompt += "\n\n## 从历史错误中学到的注意事项\n"
            for lesson in role_lessons[-5:]:  # 最多显示 5 条
                base_prompt += f"- {lesson}\n"
    except:
        pass
    return base_prompt


# ============================================================
# W3: 模型效果学习 — 记录各模型任务效果
# ============================================================

MODEL_EFFECTIVENESS_PATH = Path(__file__).parent.parent / ".ai-state" / "model_effectiveness.jsonl"

def _record_model_effectiveness(model: str, task_type: str, quality_score: int):
    """记录模型在特定任务上的效果"""
    entry = {
        "model": model,
        "task_type": task_type,
        "quality_score": quality_score,  # 1-10
        "timestamp": time.strftime('%Y-%m-%d %H:%M')
    }
    MODEL_EFFECTIVENESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_EFFECTIVENESS_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _select_best_model_learned(task_type: str) -> str:
    """基于历史效果选择最佳模型"""
    if not MODEL_EFFECTIVENESS_PATH.exists():
        return None

    # 读取历史记录
    lines = MODEL_EFFECTIVENESS_PATH.read_text(encoding='utf-8').strip().split('\n')
    if len(lines) < 10:
        return None

    # 按模型统计
    model_scores = {}
    for line in lines:
        try:
            entry = json.loads(line)
            if entry.get("task_type") == task_type:
                model = entry.get("model")
                score = entry.get("quality_score", 5)
                if model not in model_scores:
                    model_scores[model] = {"total": 0, "sum": 0}
                model_scores[model]["total"] += 1
                model_scores[model]["sum"] += score
        except:
            continue

    if not model_scores:
        return None

    # 选择平均分最高的
    best = max(model_scores.items(), key=lambda x: x[1]["sum"]/x[1]["total"])
    if best[1]["total"] >= 5:  # 至少 5 次记录
        print(f"  [ModelLearn] {task_type} 最佳模型: {best[0]} (平均 {best[1]['sum']/best[1]['total']:.1f}分)")
        return best[0]
    return None


# ============================================================
# Demo V1: Demo 信息自动补齐 — 生成前检查并补齐设计信息
# ============================================================

def _ensure_demo_prerequisites(demo_type: str, progress_callback=None) -> dict:
    """检查并补齐 Demo 生成所需的前置信息

    Args:
        demo_type: "hud_demo" 或 "app_demo"
        progress_callback: 进度回调函数

    Returns:
        包含所有必需知识的字典
    """
    required_knowledge = {
        "hud_demo": [
            ("HUD 信息布局规范", "HUD layout specification display position motorcycle helmet"),
            ("HUD 色彩方案", "HUD color scheme helmet visor daylight night visibility"),
            ("HUD 信息优先级", "HUD information priority navigation speed call alert"),
            ("HUD 动画规范", "HUD animation transition fade duration interaction"),
            ("竞品 HUD 布局参考", "EyeRide Jarvish Forcite HUD layout screenshot interface"),
        ],
        "app_demo": [
            ("App 配对流程", "smart helmet app pairing bluetooth connection flow"),
            ("App 骑行仪表盘", "motorcycle riding dashboard UI speedometer navigation"),
            ("App 组队地图", "group ride map real-time location sharing mesh"),
            ("竞品 App 参考", "Cardo Sena app UI design screenshot interface"),
        ],
    }

    results = {}
    missing = []

    for topic, search_query in required_knowledge.get(demo_type, []):
        # 检查 KB 中是否有足够信息
        kb_results = []
        for f in KB_ROOT.rglob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                content = data.get("content", "")
                title = data.get("title", "")
                if topic.lower() in title.lower() or topic.lower() in content[:500].lower():
                    kb_results.append(data)
            except:
                continue

        if len(kb_results) >= 2 and any(r.get("confidence") in ("high", "authoritative") for r in kb_results):
            results[topic] = kb_results
        else:
            missing.append((topic, search_query))

    # 自动补齐缺失信息
    if missing:
        if progress_callback:
            progress_callback(f"  Demo准备: 缺少 {len(missing)} 项信息，自动搜索补齐...")
        print(f"  [DemoPrep] 缺少 {len(missing)} 项信息，自动搜索补齐...")

        for topic, query in missing:
            # 用快速研究补齐
            search_result = _quick_research_for_demo(query)
            if search_result:
                add_knowledge(
                    title=f"[Demo准备] {topic}",
                    domain="components",
                    content=search_result,
                    tags=["demo_prep", demo_type],
                    source="auto_demo_prep",
                    confidence="medium"
                )
                results[topic] = [{"content": search_result}]
                print(f"  [DemoPrep] 补齐: {topic}")

    return results


def _quick_research_for_demo(query: str) -> str:
    """快速搜索用于 Demo 准备"""
    # 用单通道快速搜索
    result = _call_with_backoff(
        "gemini_2_5_flash",
        f"搜索关于 {query} 的关键信息，输出 300-500 字摘要。",
        "你是产品研究员，提取关键设计参数。", "demo_prep_search"
    )
    if result.get("success"):
        return result["response"][:1000]
    return ""


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

额外字段要求（必须包含在输出的 JSON 中）：
- confidence_score: 数值型，1.0-10.0，表示数据可信度
- uncertainty_range: 如 "±10%" 或 "5-7小时"，表示数据不确定性范围
- derived_from: 数据来源说明，如 "官方datasheet"、"新闻报道"
- observed_at: 数据观测时间，如 "2024Q3"、"2025年3月"

只输出 JSON，不要其他内容。"""

    model = _get_model_for_task("data_extraction")
    print(f"[L2-Debug] 调用 {model} 提炼，输入长度 {len(raw_text)}")

    result = _call_model(model, prompt, task_type="data_extraction")

    print(f"[L2-Debug] 返回 success={result.get('success')}, error={str(result.get('error',''))[:200]}")

    if result.get("success"):
        try:
            resp = result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            parsed = json.loads(resp)
            return parsed
        except json.JSONDecodeError as e:
            print(f"[L2-Debug] JSON解析失败: {e}, 响应前200字符: {resp[:200]}")
            return None
        except Exception as e:
            print(f"[L2-Debug] 解析异常: {type(e).__name__}: {e}")
            return None
    else:
        print(f"[L2-Debug] 模型调用失败: {result.get('error', 'unknown error')}")
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
        from scripts.critic_calibration import get_evolved_few_shot, get_evolved_rules
        evolved_few_shot = get_evolved_few_shot()
        if evolved_few_shot:
            few_shot_to_use = evolved_few_shot
            print("  [Critic] 使用进化版 few-shot 示例")
        # W6: 检查是否有进化版规则
        evolved_rules = get_evolved_rules()
        if evolved_rules:
            print(f"  [Critic] 加载 {len(evolved_rules.get('p0_triggers', []))} 条进化规则")
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

    # === Dual Critic: o3 交叉审查 ===
    # 用 o3 对主 Critic 的结论进行交叉验证
    print("  [Critic Cross] o3 开始交叉审查...")
    cross_critic_prompt = (
        f"你是第二独立审查员，用逻辑挑战报告中的漏洞。\n\n"
        f"## 主审查员的结论\n"
        f"P0 数量: {len(p0_list)}\n"
        f"P1 数量: {len(p1_list)}\n\n"
        f"## 报告目标\n{goal[:300]}\n\n"
        f"## 报告内容\n{report[:6000]}\n\n"
        f"## 你的任务\n"
        f"1. 检查主审查员是否漏掉了关键的逻辑漏洞\n"
        f"2. 检查报告中的数值推算是否合理\n"
        f"3. 检查结论与数据之间的逻辑链条是否完整\n\n"
        f"输出 JSON:\n"
        f'{{\n'
        f'  "additional_p0": [{{"issue": "主审查员漏掉的P0问题", "reason": "为什么这是P0"}}],\n'
        f'  "logic_gaps": ["逻辑漏洞1", "逻辑漏洞2"],\n'
        f'  "calculation_concerns": ["数值问题1"],\n'
        f'  "agreement": "agree/partially_agree/disagree"\n'
        f'}}\n'
        f"如果同意主审查员的结论，additional_p0 为空数组。\n"
        f"只输出 JSON。"
    )
    cross_result = _call_model("o3", cross_critic_prompt, "你是逻辑审查员。只输出 JSON。", "critic_cross")
    if cross_result.get("success"):
        try:
            cross_resp = cross_result["response"].strip()
            cross_resp = re.sub(r'^```json\s*', '', cross_resp)
            cross_resp = re.sub(r'\s*```$', '', cross_resp)
            cross_data = json.loads(cross_resp)

            additional_p0 = cross_data.get("additional_p0", [])
            if additional_p0:
                print(f"  [Critic Cross] o3 发现 {len(additional_p0)} 个额外 P0")
                for ap0 in additional_p0:
                    p0_list.append({
                        "issue": ap0.get("issue", ""),
                        "evidence": f"[o3 交叉审查] {ap0.get('reason', '')}",
                        "fix_required": "需要验证"
                    })
                needs_fix = True

            logic_gaps = cross_data.get("logic_gaps", [])
            if logic_gaps:
                p2_list.extend([{"issue": f"[逻辑检查] {g}"} for g in logic_gaps])

            # 记录交叉审查结果
            report += f"\n\n<!-- Dual Critic: o3 {cross_data.get('agreement', 'unknown')} -->"
        except Exception as e:
            print(f"  [Critic Cross] 解析失败: {e}")

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

    # === A-3: 注入相关历史发现 ===
    prior_findings = _get_related_findings(title, goal)
    if prior_findings:
        print(f"  [Knowledge Transfer] 发现相关历史发现")
        goal = goal + prior_findings

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

    # === Layer 1: 并发四通道搜索（升级版）===
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
        """单个 query 的四通道并行搜索（在线程中运行）

        通道分配:
        - o3-deep-research: 英文技术/专利/学术论文
        - doubao-seed-pro: 中文互联网（小红书/B站/知乎）
        - grok-4: 社交媒体实时动态/X-Twitter（新增）
        - gemini-deep-research: Google学术/行业报告（新增）
        - tavily: fallback 兜底
        """
        source_text = ""
        channel_results = {}

        # Channel A: o3-deep-research（英文技术 + 专利）
        o3_result = _call_with_backoff(
            "o3_deep_research", query,
            "Search for technical specifications, patents, and research papers.",
            "deep_research_search")
        if o3_result.get("success") and len(o3_result.get("response", "")) > 200:
            channel_results["o3"] = o3_result["response"][:3000]
            model_used = o3_result.get("degraded_from", "o3_deep_research") if o3_result.get("degraded_from") else "o3"
            print(f"    [{i}] o3: {len(o3_result['response'])} 字 (via {model_used})")

        # Channel B: doubao（中文互联网）
        doubao_result = _call_with_backoff(
            "doubao_seed_pro", query,
            "搜索中文互联网信息，重点关注小红书、B站、知乎、雪球、1688等平台的相关内容。",
            "chinese_search")
        if doubao_result.get("success") and len(doubao_result.get("response", "")) > 200:
            channel_results["doubao"] = doubao_result["response"][:3000]
            print(f"    [{i}] doubao: {len(doubao_result['response'])} 字")

        # Channel C: grok-4（社交媒体实时动态 - 新增）
        grok_result = _call_with_backoff(
            "grok_4", query,
            "Search for real-time social media discussions, Twitter/X posts, industry news, and KOL opinions. Focus on latest updates and user feedback.",
            "grok_search")
        if grok_result.get("success") and len(grok_result.get("response", "")) > 200:
            channel_results["grok"] = grok_result["response"][:3000]
            print(f"    [{i}] grok: {len(grok_result['response'])} 字")

        # Channel D: gemini-deep-research（学术深挖 - 新增）
        gemini_deep_result = _call_with_backoff(
            "gemini_deep_research", query,
            "Search for academic papers, Google Scholar results, industry reports, and detailed technical analysis.",
            "gemini_deep_search")
        if gemini_deep_result.get("success") and len(gemini_deep_result.get("response", "")) > 200:
            channel_results["gemini_deep"] = gemini_deep_result["response"][:3000]
            print(f"    [{i}] gemini_deep: {len(gemini_deep_result['response'])} 字")

        # 合并所有通道结果
        for channel, text in channel_results.items():
            if source_text:
                source_text += f"\n--- [{channel}] ---\n"
            source_text += text

        # Fallback: tavily（仅当所有通道都失败时）
        if not source_text:
            tavily_result = registry.call("tavily_search", query)
            if tavily_result.get("success") and len(tavily_result.get("data", "")) > 200:
                source_text = tavily_result["data"][:3000]
                print(f"    [{i}] tavily(fallback): {len(source_text)} 字")

        return {"index": i, "query": query, "content": source_text, "channels": list(channel_results.keys())}

    # 展平 searches（discovery 可能返回嵌套 list）
    flat_searches = []
    for s in searches:
        if isinstance(s, list):
            flat_searches.extend([str(item) for item in s])
        else:
            flat_searches.append(str(s))
    searches = flat_searches

    # 并发搜索所有 query（四通道）
    print(f"  [L1] 并发四通道搜索 {len(searches)} 个 query (o3 + doubao + grok + gemini_deep)...")
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

    # W1: 记录搜索效果
    try:
        import json as _json_w1
        from pathlib import Path as _Path_w1
        _learning_path = _Path_w1(__file__).parent.parent / ".ai-state" / "search_learning.jsonl"
        _learning_path.parent.mkdir(parents=True, exist_ok=True)
        for _src in all_sources:
            try:
                with open(_learning_path, 'a', encoding='utf-8') as _f:
                    _f.write(_json_w1.dumps({
                        "query": str(_src.get("query", ""))[:200],
                        "task": title,
                        "chars_returned": len(_src.get("content", "")),
                        "timestamp": time.strftime('%Y-%m-%d %H:%M')
                    }, ensure_ascii=False) + "\n")
            except Exception as _e:
                print(f"  [W1] 记录失败: {_e}")
        print(f"  [W1] 搜索学习已记录: {len(all_sources)} 条")
    except Exception as _e:
        print(f"  [W1] 学习记录失败: {_e}")

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

    # === Layer 3.5: Agent 辩论（如果有多于 1 个 Agent 输出）===
    if len(agent_outputs) >= 2:
        agent_outputs = _run_agent_debate(agent_outputs, goal, distilled_material)

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

    # === Layer 4.5: 护栏检查（D模块集成）===
    try:
        from scripts.guardrail_engine import check_guardrails
        triggered = check_guardrails(report, source="deep_research")
        if triggered:
            print(f"  [Guardrail] 触发 {len(triggered)} 个护栏")
            for g in triggered[:3]:
                action = g.get("action", "warn")
                if action == "warn":
                    report += f"\n\n⚠️ **注意**: {g.get('message', '检测到潜在风险')}"
                elif action == "block":
                    print(f"  [Guardrail] BLOCK: {g.get('id')}")
    except ImportError:
        pass

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

    # C-5: 回流决策树
    try:
        import yaml as _yaml_c5
        _dt_path = Path(__file__).parent.parent / ".ai-state" / "product_decision_tree.yaml"
        if _dt_path.exists():
            _dt = _yaml_c5.safe_load(_dt_path.read_text(encoding='utf-8'))
            _report_lower = (report or "").lower()
            for _d in _dt.get("decisions", []):
                _q = _d.get("question", "")
                # 用问题中的关键词匹配报告内容
                _keywords = [w for w in _q.replace("？", "").replace("?", "").split() if len(w) > 1]
                _match_count = sum(1 for kw in _keywords if kw.lower() in _report_lower)
                if _match_count >= 2:  # 至少匹配 2 个关键词
                    _d["resolved_knowledge"] = _d.get("resolved_knowledge", 0) + 1
                    print(f"  [DecisionTree] {_d.get('id')}: +1 -> {_d['resolved_knowledge']}")
            _dt_path.write_text(
                _yaml_c5.dump(_dt, allow_unicode=True, default_flow_style=False),
                encoding='utf-8'
            )
    except Exception as _e:
        print(f"  [DecisionTree] 回流失败: {_e}")

    # W3: 模型效果记录
    try:
        _meff_path = Path(__file__).parent.parent / ".ai-state" / "model_effectiveness.jsonl"
        with open(_meff_path, 'a', encoding='utf-8') as _f:
            _f.write(json.dumps({
                "task": title,
                "report_chars": len(report or ""),
                "sources_count": len(all_sources),
                "timestamp": time.strftime('%Y-%m-%d %H:%M')
            }, ensure_ascii=False) + "\n")
        print(f"  [W3] 模型效果已记录")
    except Exception as _e:
        print(f"  [W3] 记录失败: {_e}")

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

    # === A-3: 保存关键发现供未来任务使用 ===
    _save_task_findings(title, report)

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

    # 用 LLM 分析 KB 现状，生成研究建议
    kb_summary = _get_kb_summary()

    discover_prompt = (
        f"你是智能骑行头盔项目的研究规划师。\n\n"
        f"## 当前知识库状态\n{kb_summary}\n\n"
        f"## 产品方向\n"
        f"全脸头盔，HUD显示，语音控制，组队骑行，主动安全。\n"
        f"V1 关键技术: OLED+Free Form / Micro LED+树脂衍射光波导（并行路线）\n"
        f"主SoC: Qualcomm AR1 Gen 1\n"
        f"通信: Mesh Intercom\n\n"
        f"## 已有任务（避免重复）\n"
        f"以下任务已经存在或已完成，不要生成与它们高度重叠的新任务：\n"
        f"{existing_titles_text}\n\n"
        f"如果你要研究的方向与已有任务重叠超过 50%，请换一个角度或跳过。\n\n"
        f"## 任务\n"
        f"分析知识库的薄弱环节，生成 3-5 个新研究任务。\n"
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


def _discover_from_decision_tree() -> list:
    """从决策树的未解决决策中生成研究任务"""
    try:
        dt_path = Path(__file__).parent.parent / ".ai-state" / "product_decision_tree.yaml"
        if not dt_path.exists():
            return []
        dt = yaml.safe_load(dt_path.read_text(encoding='utf-8'))
        tasks = []
        for d in dt.get("decisions", []):
            resolved = d.get("resolved_knowledge", 0)
            needed = d.get("total_needed", 3)
            if resolved < needed:
                tasks.append({
                    "id": f"dt_{d.get('id', 'unknown')}",
                    "title": f"决策补充: {d.get('question', '')[:40]}",
                    "goal": f"补充决策所需信息: {d.get('question', '')}。目前进度 {resolved}/{needed}。",
                    "priority": 2,
                    "searches": 4,
                    "source": "decision_tree_gap"
                })
        if tasks:
            print(f"  [DecisionTree] 发现 {len(tasks)} 个补充任务")
        return tasks
    except Exception as e:
        print(f"  [DecisionTree] 发现失败: {e}")
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

    # API 健康检查
    def _pre_flight_api_check():
        """30 秒验证关键模型是否可用"""
        results = {}
        critical = ["gpt_5_4", "o3_deep_research"]
        important = ["doubao_seed_pro", "gpt_4o_norway", "deepseek_v3_volcengine"]

        for model in critical + important:
            try:
                r = _call_model(model, "Ping", task_type="health_check")
                results[model] = "OK" if r.get("success") else f"FAIL: {str(r.get('error',''))[:30]}"
            except Exception as e:
                results[model] = f"FAIL: {str(e)[:30]}"

        unavailable_critical = [m for m in critical if "FAIL" in results.get(m, "FAIL")]

        status_msg = "API 健康检查:\n" + "\n".join([f"  {m}: {s}" for m, s in results.items()])

        if unavailable_critical:
            status_msg += f"\n\n核心模型不可用: {unavailable_critical}，深度学习暂停"
            if progress_callback:
                progress_callback(status_msg)
            print(status_msg)
            return False

        if any("FAIL" in v for v in results.values()):
            status_msg += "\n\n部分非核心模型不可用，将使用降级方案"
        else:
            status_msg += "\n\n所有模型可用"

        if progress_callback:
            progress_callback(status_msg)
        print(status_msg)
        return True

    if not _pre_flight_api_check():
        return {"status": "aborted", "reason": "API health check failed"}

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
            if not new_tasks:
                # Fallback: 从决策树缺口中发现
                new_tasks = _discover_from_decision_tree()
                if new_tasks:
                    print(f"[Scheduler] 从决策树发现 {len(new_tasks)} 个补充任务")
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