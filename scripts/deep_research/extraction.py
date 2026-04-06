"""
深度研究 — 结构化提取层
职责: L2 结构化提取 + Schema + 搜索词生成 + Agent 分片运行
被调用方: pipeline.py
依赖: models.py
"""
import json
import re

from scripts.deep_research.models import (
    call_model, get_model_for_task
)


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
    "hud_position": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "info_layout": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "simultaneous_elements": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "priority_mechanism": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "direction_indication": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
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
    "certification": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
}

GENERAL_SCHEMA = {
    "topic": "string",
    "key_findings": [{"finding": "string", "source": "string", "confidence": "high|medium|low"}],
    "data_gaps": ["string"],
}

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


def extract_structured_data(raw_text: str, task_type: str, topic: str) -> dict:
    """从搜索结果中提取结构化数据点"""
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

    model = get_model_for_task("data_extraction")
    print(f"[L2-Debug] 调用 {model} 提炼，输入长度 {len(raw_text)}")

    result = call_model(model, prompt, task_type="data_extraction")

    print(f"[L2-Debug] 返回 success={result.get('success')}, error={str(result.get('error', ''))[:200]}")

    if result.get("success"):
        try:
            resp = result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            return json.loads(resp)
        except json.JSONDecodeError as e:
            print(f"[L2-Debug] JSON解析失败: {e}, 响应前200字符: {resp[:200]}")
            return None
        except Exception as e:
            print(f"[L2-Debug] 解析异常: {type(e).__name__}: {e}")
            return None
    else:
        print(f"[L2-Debug] 模型调用失败: {result.get('error', 'unknown error')}")
    return None


def generate_targeted_queries(task_spec_text: str, base_queries: list) -> list:
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

    result = call_model(get_model_for_task("query_generation"), prompt, task_type="query_generation")

    if result.get("success"):
        try:
            resp = result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            data = json.loads(resp)
            targeted = data.get("targeted_queries", [])
            return targeted + base_queries
        except:
            return base_queries
    return base_queries


def run_expert_analysis_in_slices(role: str, structured_data_list: list,
                                  system_prompt: str, user_prompt_template: str,
                                  model_name: str) -> list:
    """将结构化数据分组，每组独立让专家模型处理"""
    if not structured_data_list:
        return []

    groups = {}
    for item in structured_data_list:
        product_type = item.get('product_type', item.get('topic', 'general'))
        if product_type not in groups:
            groups[product_type] = []
        groups[product_type].append(item)

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

        result = call_model(model_name, user_prompt, system_prompt,
                            task_type=f"deep_research_{role.lower()}")
        if result.get("success"):
            partial_outputs.append({
                "group": group_name,
                "output": result["response"],
                "items_count": len(group_items)
            })
            print(f"  [{role} {group_name}] {len(result['response'])} chars")

    return partial_outputs
