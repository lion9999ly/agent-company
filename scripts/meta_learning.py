"""
@description: 元学习自评 — 评估各项学习机制的实际效果
@dependencies: json, yaml, pathlib, datetime
@last_modified: 2026-04-04
"""
import json
import yaml
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent
META_LEARNING_PATH = PROJECT_ROOT / ".ai-state" / "meta_learning_report.yaml"


def meta_learning_assessment() -> dict:
    """评估各项学习机制的实际效果

    Returns:
        元学习评估报告
    """
    report = {
        "assessed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "mechanisms": {},
        "recommendations": [],
    }

    # 1. 评估搜索策略学习
    search_result = _assess_search_learning()
    report["mechanisms"]["search_strategy"] = search_result

    # 2. 评估 Agent prompt 自进化
    agent_result = _assess_agent_prompt_learning()
    report["mechanisms"]["agent_prompt"] = agent_result

    # 3. 评估模型效果学习
    model_result = _assess_model_effectiveness()
    report["mechanisms"]["model_effectiveness"] = model_result

    # 4. 评估输出格式学习
    output_result = _assess_output_preferences()
    report["mechanisms"]["output_preferences"] = output_result

    # 5. 评估 Critic 校准
    critic_result = _assess_critic_calibration()
    report["mechanisms"]["critic_calibration"] = critic_result

    # 生成建议
    if search_result.get("status") == "improved":
        report["recommendations"].append("搜索策略学习有效，继续保持")
    elif search_result.get("status") == "degraded":
        report["recommendations"].append("搜索策略效果下降，建议回滚最近变更")

    if critic_result.get("calibration_count", 0) < 10:
        report["recommendations"].append("Critic 校准样本不足，建议增加校准频率")

    # 保存报告
    META_LEARNING_PATH.parent.mkdir(parents=True, exist_ok=True)
    META_LEARNING_PATH.write_text(
        yaml.dump(report, allow_unicode=True, default_flow_style=False),
        encoding="utf-8"
    )

    return report


def _assess_search_learning() -> dict:
    """评估搜索策略学习效果"""
    search_log_path = PROJECT_ROOT / ".ai-state" / "search_learning.jsonl"
    if not search_log_path.exists():
        return {"status": "no_data", "samples": 0}

    # 读取最近搜索记录
    records = []
    with open(search_log_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                records.append(json.loads(line.strip()))
            except:
                continue

    if len(records) < 20:
        return {"status": "insufficient_data", "samples": len(records)}

    # 对比前后质量
    recent = records[-10:]
    older = records[-20:-10]

    recent_quality = sum(r.get("quality", 0) for r in recent if isinstance(r.get("quality"), (int, float))) / len(recent)
    older_quality = sum(r.get("quality", 0) for r in older if isinstance(r.get("quality"), (int, float))) / len(older)

    if recent_quality > older_quality * 1.1:
        status = "improved"
    elif recent_quality < older_quality * 0.9:
        status = "degraded"
    else:
        status = "stable"

    return {
        "status": status,
        "samples": len(records),
        "recent_avg_quality": round(recent_quality, 2),
        "older_avg_quality": round(older_quality, 2),
    }


def _assess_agent_prompt_learning() -> dict:
    """评估 Agent prompt 自进化效果"""
    lessons_path = PROJECT_ROOT / ".ai-state" / "agent_lessons.yaml"
    if not lessons_path.exists():
        return {"status": "no_lessons", "lessons_count": 0}

    try:
        lessons = yaml.safe_load(lessons_path.read_text(encoding="utf-8"))
    except:
        return {"status": "error", "lessons_count": 0}

    total_lessons = sum(len(v.get("learned_warnings", [])) for v in lessons.values() if isinstance(v, dict))

    return {
        "status": "active",
        "lessons_count": total_lessons,
        "agents_with_lessons": list(lessons.keys()) if isinstance(lessons, dict) else [],
    }


def _assess_model_effectiveness() -> dict:
    """评估模型效果学习"""
    model_log_path = PROJECT_ROOT / ".ai-state" / "model_effectiveness.jsonl"
    if not model_log_path.exists():
        return {"status": "no_data", "records": 0}

    records = []
    with open(model_log_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                records.append(json.loads(line.strip()))
            except:
                continue

    return {
        "status": "active" if len(records) > 20 else "insufficient_data",
        "records": len(records),
    }


def _assess_output_preferences() -> dict:
    """评估输出偏好学习"""
    prefs_path = PROJECT_ROOT / ".ai-state" / "output_preferences.yaml"
    if not prefs_path.exists():
        return {"status": "no_preferences"}

    try:
        prefs = yaml.safe_load(prefs_path.read_text(encoding="utf-8"))
        return {
            "status": "active",
            "preferences": list(prefs.keys()) if isinstance(prefs, dict) else [],
        }
    except:
        return {"status": "error"}


def _assess_critic_calibration() -> dict:
    """评估 Critic 校准效果"""
    cal_path = PROJECT_ROOT / ".ai-state" / "critic_calibration.jsonl"
    if not cal_path.exists():
        return {"status": "no_data", "calibration_count": 0}

    count = 0
    with open(cal_path, 'r', encoding='utf-8') as f:
        for _ in f:
            count += 1

    return {
        "status": "active" if count >= 10 else "insufficient_data",
        "calibration_count": count,
    }


def get_meta_learning_summary() -> str:
    """获取元学习摘要文本"""
    if not META_LEARNING_PATH.exists():
        return "📊 元学习评估: 尚无评估记录"

    try:
        report = yaml.safe_load(META_LEARNING_PATH.read_text(encoding="utf-8"))
    except:
        return "📊 元学习评估: 读取失败"

    lines = ["📊 元学习评估报告"]
    lines.append(f"评估时间: {report.get('assessed_at', '?')}")

    for name, data in report.get("mechanisms", {}).items():
        status = data.get("status", "unknown")
        icon = "✅" if status in ("improved", "active", "stable") else "⚠️" if status in ("degraded", "insufficient_data") else "❓"
        lines.append(f"  {icon} {name}: {status}")

    for rec in report.get("recommendations", []):
        lines.append(f"  💡 {rec}")

    return "\n".join(lines)


if __name__ == "__main__":
    result = meta_learning_assessment()
    print(yaml.dump(result, allow_unicode=True, default_flow_style=False))