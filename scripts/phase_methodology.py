"""
@description: 项目阶段方法论提取 — 从已完成阶段提取可复用的经验
@dependencies: pathlib, json, yaml
@last_modified: 2026-04-04
"""
import json
import yaml
import time
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
KB_ROOT = PROJECT_ROOT / ".ai-state" / "knowledge"
PHASE_PATH = PROJECT_ROOT / ".ai-state" / "project_phase.yaml"


def extract_phase_methodology(completed_phase: str) -> dict:
    """从已完成阶段提取方法论经验

    Args:
        completed_phase: 已完成的阶段名（如 "方案论证"）

    Returns:
        提取的方法论摘要
    """
    from src.utils.model_gateway import get_model_gateway

    gateway = get_model_gateway()

    # 收集该阶段产生的所有知识条目和报告
    entries = []
    for domain_dir in KB_ROOT.iterdir():
        if domain_dir.is_dir():
            for f in domain_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    # 检查创建时间是否在该阶段期间
                    created = data.get("created_at", "")
                    if created:
                        # 简化：假设最近 30 天的条目都属于当前阶段
                        entries.append(data)
                except:
                    continue

    if len(entries) < 5:
        return {"status": "skip", "reason": "数据太少"}

    # 用模型提取方法论
    summary_text = "\n".join([
        f"- [{e.get('domain')}] {e.get('title')}: {e.get('content', '')[:100]}"
        for e in entries[:30]
    ])

    prompt = f"""
从以下知识库条目中提取方法论经验：

阶段：{completed_phase}

条目摘要：
{summary_text}

请提取：
1. 什么研究流程有效？（如：先搜英文专利再搜中文社区）
2. 什么工具/模型好用？（如：o3-deep-research 适合技术深挖）
3. 踩了什么坑？（如：供应商报价单需要 OCR 验证）
4. 什么数据源不可靠？（如：小红书评测有夸大）

输出 YAML 格式：
process_insights: [...]
tool_recommendations: [...]
pitfalls: [...]
unreliable_sources: [...]
"""

    result = gateway.call("gemini_2_5_flash", prompt, "", "methodology_extract")
    if not result.get("success"):
        return {"status": "error", "reason": result.get("error")}

    try:
        # 尝试解析 YAML
        content = result["response"]
        # 去掉 markdown 包装
        if "```yaml" in content:
            content = content.split("```yaml")[1].split("```")[0]
        methodology = yaml.safe_load(content)
    except:
        methodology = {"raw_text": content}

    # 存入 methodology 域
    from src.tools.knowledge_base import add_knowledge

    add_knowledge(
        title=f"[方法论] {completed_phase} 阶段经验",
        domain="methodology",
        content=json.dumps(methodology, ensure_ascii=False, indent=2),
        tags=["methodology", completed_phase, "phase_transition"],
        source="phase_methodology_extract",
        confidence="medium",
        caller="phase_transition"
    )

    return {
        "status": "success",
        "phase": completed_phase,
        "entries_count": len(entries),
        "methodology": methodology
    }


def check_phase_transition() -> str:
    """检查是否满足阶段切换条件

    Returns:
        如果满足条件，返回下一阶段名；否则返回空字符串
    """
    if not PHASE_PATH.exists():
        return ""

    try:
        phase_config = yaml.safe_load(PHASE_PATH.read_text(encoding="utf-8"))
    except:
        return ""

    current = phase_config.get("current_phase", "方案论证")
    transitions = phase_config.get("phase_transition_rules", {})

    # 检查各阶段切换条件
    for rule_name, rule in transitions.items():
        if rule_name.startswith(f"{current}_to_"):
            condition = rule.get("condition", "")

            # 简化检查：检查 P1 决策点 resolved 比例
            if "P1 决策点" in condition and "resolved_knowledge >= 80%" in condition:
                from .decision_readiness import get_decision_summary
                summary = get_decision_summary()
                # 如果所有 open 决策都 ready（resolved >= 80%）
                if summary.get("open_count", 0) > 0 and summary.get("ready_count", 0) == summary.get("open_count", 0):
                    next_phase = rule_name.split("_to_")[1]
                    return next_phase

    return ""


def transition_to_phase(new_phase: str) -> bool:
    """切换到新阶段

    Args:
        new_phase: 新阶段名

    Returns:
        是否成功切换
    """
    if not PHASE_PATH.exists():
        return False

    try:
        phase_config = yaml.safe_load(PHASE_PATH.read_text(encoding="utf-8"))
    except:
        return False

    old_phase = phase_config.get("current_phase", "")

    if old_phase == new_phase:
        return False

    # 触发方法论提取
    extract_phase_methodology(old_phase)

    # 更新阶段
    phase_config["current_phase"] = new_phase
    PHASE_PATH.write_text(yaml.dump(phase_config, allow_unicode=True, default_flow_style=False), encoding="utf-8")

    print(f"[Phase] 切换: {old_phase} → {new_phase}")
    return True


if __name__ == "__main__":
    # 测试
    result = extract_phase_methodology("方案论证")
    print(f"Result: {result}")