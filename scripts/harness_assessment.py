"""Harness 成熟度自评 — 六维雷达
@description: 自动评估系统在六个维度的成熟度
@dependencies: 无
@last_modified: 2026-04-04
"""
import json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
HARNESS_PATH = PROJECT_ROOT / ".ai-state" / "harness_history.jsonl"

DIMENSIONS = [
    "Tool Integration",
    "Memory & State",
    "Context Engineering",
    "Planning & Decomposition",
    "Verification & Guardrails",
    "Lifecycle Management",
]


def assess_maturity() -> dict:
    """自动评估六维成熟度（每维 1-5 分）"""
    scores = {}

    # Tool Integration: 模型数量 + 降级链 + 元能力工具数
    scores["Tool Integration"] = _score_tool_integration()

    # Memory & State: KB 条目数 + 工作记忆 + checkpoint
    scores["Memory & State"] = _score_memory_state()

    # Context Engineering: Agent prompt 管理 + 决策树 + 专家框架
    scores["Context Engineering"] = _score_context_engineering()

    # Planning & Decomposition: 五层管道 + 任务去重 + 深钻模式
    scores["Planning & Decomposition"] = _score_planning()

    # Verification & Guardrails: Critic 分级 + 校准 + 安全禁止列表
    scores["Verification & Guardrails"] = _score_verification()

    # Lifecycle Management: KB 治理 + 软删除 + watchdog + 用量追踪
    scores["Lifecycle Management"] = _score_lifecycle()

    result = {"scores": scores, "timestamp": time.strftime('%Y-%m-%d %H:%M')}

    # 保存历史
    HARNESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HARNESS_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")

    return result


def _score_tool_integration() -> int:
    """评分工具整合"""
    score = 1
    # 检查模型注册表
    registry_path = PROJECT_ROOT / "src" / "config" / "model_registry.yaml"
    if registry_path.exists():
        score += 1
        try:
            import yaml
            reg = yaml.safe_load(registry_path.read_text(encoding='utf-8'))
            if len(reg.get("models", {})) >= 10:
                score += 1
        except Exception:
            pass
    # 检查降级映射
    gateway_path = PROJECT_ROOT / "src" / "utils" / "model_gateway.py"
    if gateway_path.exists():
        content = gateway_path.read_text(encoding='utf-8')
        if "FALLBACK" in content or "fallback" in content:
            score += 1
    # 元能力
    meta_path = PROJECT_ROOT / "scripts" / "meta_capability.py"
    if meta_path.exists():
        score += 1
    return min(score, 5)


def _score_memory_state() -> int:
    """评分记忆状态"""
    score = 1
    # KB
    kb_path = PROJECT_ROOT / "knowledge_base"
    if kb_path.exists():
        json_files = list(kb_path.rglob("*.json"))
        if len(json_files) > 50:
            score += 2
        elif len(json_files) > 20:
            score += 1
    # 工作记忆
    work_mem_path = PROJECT_ROOT / ".ai-state" / "work_memory" / "decisions.jsonl"
    if work_mem_path.exists():
        score += 1
    # checkpoint
    checkpoint_path = PROJECT_ROOT / ".ai-state" / "checkpoints"
    if checkpoint_path.exists():
        score += 1
    return min(score, 5)


def _score_context_engineering() -> int:
    """评分上下文工程"""
    score = 1
    # 决策树
    dt_path = PROJECT_ROOT / ".ai-state" / "product_decision_tree.yaml"
    if dt_path.exists():
        score += 1
    # Agent prompts
    prompts_path = PROJECT_ROOT / "src" / "config" / "agent_prompts.yaml"
    if prompts_path.exists():
        score += 1
    # 专家框架
    experts_path = PROJECT_ROOT / ".ai-architecture" / "AGENTS.md"
    if experts_path.exists():
        score += 1
    # 状态定义
    state_path = PROJECT_ROOT / "src" / "schema" / "state.py"
    if state_path.exists():
        score += 1
    return min(score, 5)


def _score_planning() -> int:
    """评分规划能力"""
    score = 1
    # 五层管道
    deep_research_path = PROJECT_ROOT / "scripts" / "tonight_deep_research.py"
    if deep_research_path.exists():
        score += 1
        content = deep_research_path.read_text(encoding='utf-8')
        if "layer" in content.lower() or "Layer" in content:
            score += 1
    # 任务池
    task_pool_path = PROJECT_ROOT / ".ai-state" / "research_task_pool.yaml"
    if task_pool_path.exists():
        score += 1
    # 自学习
    auto_learn_path = PROJECT_ROOT / "scripts" / "auto_learn.py"
    if auto_learn_path.exists():
        score += 1
    return min(score, 5)


def _score_verification() -> int:
    """评分验证护栏"""
    score = 1
    # Critic
    critic_path = PROJECT_ROOT / "scripts" / "critic_calibration.py"
    if critic_path.exists():
        score += 1
    # 安全模块
    security_dir = PROJECT_ROOT / "src" / "security"
    if security_dir.exists():
        files = list(security_dir.glob("*.py"))
        if len(files) >= 2:
            score += 1
    # 护栏
    guardrail_path = PROJECT_ROOT / "scripts" / "guardrail_engine.py"
    if guardrail_path.exists():
        score += 1
    # 禁止列表
    if PROJECT_ROOT / ".ai-architecture" / "01-quality-redlines.md":
        score += 1
    return min(score, 5)


def _score_lifecycle() -> int:
    """评分生命周期管理"""
    score = 1
    # KB 治理
    kb_gov_path = PROJECT_ROOT / "scripts" / "kb_governance.py"
    if kb_gov_path.exists():
        score += 1
    # 用量追踪
    usage_path = PROJECT_ROOT / "src" / "utils" / "token_usage_tracker.py"
    if usage_path.exists():
        score += 1
    # 自愈
    self_heal_path = PROJECT_ROOT / "scripts" / "self_heal.py"
    if self_heal_path.exists():
        score += 1
    # 系统日志
    log_path = PROJECT_ROOT / "scripts" / "system_log_generator.py"
    if log_path.exists():
        score += 1
    return min(score, 5)


def generate_radar_html() -> str:
    """生成六维雷达图 HTML"""
    result = assess_maturity()
    scores = result["scores"]

    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Harness 成熟度雷达</title>
    <style>
        body { font-family: Arial; padding: 20px; }
        .radar { display: flex; justify-content: center; }
        .bar-container { margin: 20px 0; }
        .bar-row { display: flex; align-items: center; margin: 10px 0; }
        .bar-label { width: 200px; }
        .bar { height: 20px; background: #4CAF50; border-radius: 4px; }
        .bar-bg { background: #ddd; width: 200px; border-radius: 4px; }
    </style>
</head>
<body>
    <h1>Harness 成熟度评估</h1>
    <p>时间: %s</p>
    <div class="bar-container">
""" % result["timestamp"]

    for dim, score in scores.items():
        width = score * 40
        html += f"""<div class="bar-row">
            <div class="bar-label">{dim}</div>
            <div class="bar-bg"><div class="bar" style="width:{width}px"></div></div>
            <span>{score}/5</span>
        </div>"""

    avg = sum(scores.values()) / len(scores)
    html += f"""    </div>
    <p>平均分: <b>{avg:.1f}</b></p>
</body>
</html>"""

    output_path = PROJECT_ROOT / ".ai-state" / "exports" / "harness_radar.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding='utf-8')
    return str(output_path)


if __name__ == "__main__":
    result = assess_maturity()
    for dim, score in result["scores"].items():
        print(f"{dim}: {score}/5")
    print(f"平均: {sum(result['scores'].values())/6:.1f}")