"""决策与否决记录
@description: 记录决策过程和否决选项，供后续参考
@dependencies: 无
@last_modified: 2026-04-04
"""
import json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
LOG_PATH = PROJECT_ROOT / ".ai-state" / "decision_log.jsonl"


def log_decision(decision_id: str, decision_type: str, content: str, reason: str):
    """记录决策或否决

    Args:
        decision_id: 决策唯一标识
        decision_type: "decided" / "rejected" / "deferred"
        content: 决策内容
        reason: 决策理由
    """
    entry = {
        "decision_id": decision_id,
        "type": decision_type,
        "content": content,
        "reason": reason,
        "timestamp": time.strftime('%Y-%m-%d %H:%M'),
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_rejections(query: str = "") -> list:
    """获取否决记录"""
    if not LOG_PATH.exists():
        return []
    results = []
    for line in LOG_PATH.read_text(encoding='utf-8').strip().split('\n'):
        try:
            e = json.loads(line)
            if e.get("type") == "rejected":
                if not query or query.lower() in e.get("content", "").lower():
                    results.append(e)
        except Exception:
            continue
    return results


def get_all_decisions() -> list:
    """获取所有决策记录"""
    if not LOG_PATH.exists():
        return []
    decisions = []
    for line in LOG_PATH.read_text(encoding='utf-8').strip().split('\n'):
        try:
            e = json.loads(line)
            decisions.append(e)
        except Exception:
            continue
    return decisions


def get_recent_decisions(limit: int = 10) -> list:
    """获取最近的决策"""
    all_decisions = get_all_decisions()
    return all_decisions[-limit:]


if __name__ == "__main__":
    # 初始化空文件
    if not LOG_PATH.exists():
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text("", encoding='utf-8')
    print(f"决策日志路径: {LOG_PATH}")