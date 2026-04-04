"""
@description: PRD 生成学习 — 从评审反馈中学习模块预算和自动补充
@dependencies: json, yaml, pathlib
@last_modified: 2026-04-04
"""
import json
import yaml
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
PRD_LEARNING_PATH = PROJECT_ROOT / ".ai-state" / "prd_learning.yaml"


def get_default_prd_learning() -> dict:
    """获取默认 PRD 学习配置"""
    return {
        "module_budgets": {
            "来电与通话": {"min_items": 15, "note": "Leo 反馈 R12 只有 5 条太少"},
            "导航": {"min_items": 30, "note": "核心模块，需要深度"},
            "音乐": {"min_items": 20, "note": "用户高频使用"},
            "消息": {"min_items": 12, "note": "需覆盖主流通讯 App"},
            "AI语音助手": {"min_items": 25, "note": "交互复杂度高"},
        },
        "test_case_ratio": 1.2,  # 测试用例数/功能数的目标比例
        "auto_additions": {
            "导航": [
                "离线地图缓存策略",
                "隧道中 GPS 信号丢失的降级方案",
                "骑行与步行场景自动切换",
            ],
            "来电与通话": [
                "骑行中来电的自动接听规则",
                "Mesh 对讲与蜂窝电话的优先级",
            ],
        },
        "learned_from_reviews": [],
    }


def load_prd_learning() -> dict:
    """加载 PRD 学习配置"""
    if PRD_LEARNING_PATH.exists():
        try:
            return yaml.safe_load(PRD_LEARNING_PATH.read_text(encoding="utf-8"))
        except:
            pass
    return get_default_prd_learning()


def save_prd_learning(config: dict):
    """保存 PRD 学习配置"""
    PRD_LEARNING_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRD_LEARNING_PATH.write_text(
        yaml.dump(config, allow_unicode=True, default_flow_style=False),
        encoding="utf-8"
    )


def learn_from_prd_review(module_name: str, feedback: str, action: str):
    """从 PRD 评审反馈中学习

    Args:
        module_name: 模块名
        feedback: 反馈内容
        action: 采取的行动（如 "increase_budget", "add_feature"）
    """
    config = load_prd_learning()

    # 记录反馈
    review_entry = {
        "module": module_name,
        "feedback": feedback[:200],
        "action": action,
        "learned_at": datetime.now().strftime("%Y-%m-%d"),
    }
    config.setdefault("learned_from_reviews", []).append(review_entry)

    # 根据反馈调整配置
    if "太短" in feedback or "太少" in feedback or "不够" in feedback:
        if module_name not in config.get("module_budgets", {}):
            config.setdefault("module_budgets", {})[module_name] = {"min_items": 15}
        config["module_budgets"][module_name]["min_items"] = \
            config["module_budgets"][module_name].get("min_items", 15) + 5
        config["module_budgets"][module_name]["note"] = f"从反馈调整: {feedback[:50]}"

    elif "漏了" in feedback or "缺少" in feedback:
        if action == "add_feature":
            # 提取功能描述
            import re
            features = re.findall(r"['\"](.+?)['\"]", feedback)
            for f in features:
                config.setdefault("auto_additions", {}).setdefault(module_name, []).append(f)

    save_prd_learning(config)
    print(f"[PRD-Learn] 从评审学习: {module_name} -> {action}")


def get_module_budget(module_name: str) -> int:
    """获取模块的建议条目数下限"""
    config = load_prd_learning()
    budgets = config.get("module_budgets", {})
    if module_name in budgets:
        return budgets[module_name].get("min_items", 15)
    return 15  # 默认


def get_auto_additions(module_name: str) -> list:
    """获取模块的自动补充功能列表"""
    config = load_prd_learning()
    additions = config.get("auto_additions", {})
    return additions.get(module_name, [])


def get_test_case_ratio() -> float:
    """获取测试用例比例"""
    config = load_prd_learning()
    return config.get("test_case_ratio", 1.2)


if __name__ == "__main__":
    # 初始化
    save_prd_learning(get_default_prd_learning())
    print("PRD 学习配置已初始化")