"""
@description: 审计日志 — 记录所有操作到审计日志
@dependencies: json, time, pathlib
@last_modified: 2026-04-04
"""
import json
import time
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
AUDIT_LOG_PATH = PROJECT_ROOT / ".ai-state" / "audit_log.jsonl"


def log_audit(action: str, user: str = "system", details: dict = None,
              kb_access: list = None) -> bool:
    """记录审计日志

    Args:
        action: 操作类型（如 "query", "add_knowledge", "deep_research"）
        user: 用户标识（飞书用户ID或"system"）
        details: 操作详情
        kb_access: 访问的知识库条目路径列表

    Returns:
        是否记录成功
    """
    if not AUDIT_LOG_PATH.parent.exists():
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "user": user,
        "details": details or {},
    }

    if kb_access:
        entry["kb_access"] = kb_access

    try:
        with open(AUDIT_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except:
        return False


def get_audit_log(limit: int = 100, action: str = None,
                  user: str = None, start_date: str = None) -> list:
    """读取审计日志

    Args:
        limit: 最大返回条数
        action: 过滤操作类型
        user: 过滤用户
        start_date: 过滤开始日期 (YYYY-MM-DD)

    Returns:
        审计日志列表
    """
    if not AUDIT_LOG_PATH.exists():
        return []

    logs = []
    with open(AUDIT_LOG_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                # 过滤
                if action and entry.get("action") != action:
                    continue
                if user and entry.get("user") != user:
                    continue
                if start_date and entry.get("timestamp", "") < start_date:
                    continue
                logs.append(entry)
            except:
                continue

    return logs[-limit:]


def get_audit_stats(days: int = 7) -> dict:
    """获取审计统计

    Args:
        days: 统计天数

    Returns:
        统计摘要
    """
    from datetime import timedelta

    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    logs = get_audit_log(limit=10000, start_date=start_date)

    if not logs:
        return {}

    stats = {
        "total_actions": len(logs),
        "by_action": {},
        "by_user": {},
        "kb_access_count": 0,
    }

    for log in logs:
        action = log.get("action", "unknown")
        stats["by_action"][action] = stats["by_action"].get(action, 0) + 1

        user = log.get("user", "unknown")
        stats["by_user"][user] = stats["by_user"].get(user, 0) + 1

        if log.get("kb_access"):
            stats["kb_access_count"] += len(log["kb_access"])

    return stats


if __name__ == "__main__":
    # 测试
    log_audit("test_action", "test_user", {"query": "HUD"})
    print(get_audit_stats(1))