"""负载管理 — 用量配额 + 任务队列 + 优先级调度
@description: 用户配额管理和任务队列调度
@dependencies: 无
@last_modified: 2026-04-04
"""
import json, time, threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
QUOTA_PATH = PROJECT_ROOT / ".ai-state" / "usage_quotas.json"
TASK_QUEUE = []
_queue_lock = threading.Lock()

ROLE_QUOTAS = {
    "admin": float('inf'),
    "manager": 500,
    "engineer": 200,
    "viewer": 50,
}


def check_quota(open_id: str, role: str) -> bool:
    """检查用户今日是否还有配额"""
    QUOTA_PATH.parent.mkdir(parents=True, exist_ok=True)

    if QUOTA_PATH.exists():
        data = json.loads(QUOTA_PATH.read_text(encoding='utf-8'))
    else:
        data = {"daily_usage": {}}

    today = time.strftime('%Y-%m-%d')
    user_usage = data.get("daily_usage", {}).get(open_id, {}).get(today, 0)
    quota = ROLE_QUOTAS.get(role, 50)

    return user_usage < quota


def record_usage(open_id: str, amount: int = 1):
    """记录用户使用"""
    QUOTA_PATH.parent.mkdir(parents=True, exist_ok=True)

    if QUOTA_PATH.exists():
        data = json.loads(QUOTA_PATH.read_text(encoding='utf-8'))
    else:
        data = {"daily_usage": {}}

    today = time.strftime('%Y-%m-%d')
    data.setdefault("daily_usage", {})
    data["daily_usage"].setdefault(open_id, {})
    data["daily_usage"][open_id][today] = data["daily_usage"][open_id].get(today, 0) + amount

    QUOTA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def enqueue_task(task_type: str, priority: int, open_id: str, callback):
    """任务入队，按优先级排序

    Args:
        task_type: 任务类型
        priority: 优先级（数字越小越优先）
        open_id: 用户标识
        callback: 回调函数
    """
    with _queue_lock:
        TASK_QUEUE.append({
            "type": task_type,
            "priority": priority,
            "user": open_id,
            "callback": callback,
            "queued_at": time.time()
        })
        TASK_QUEUE.sort(key=lambda x: x["priority"])


def dequeue_task() -> dict:
    """取出最高优先级任务"""
    with _queue_lock:
        if TASK_QUEUE:
            return TASK_QUEUE.pop(0)
    return None


def get_queue_length() -> int:
    """获取队列长度"""
    with _queue_lock:
        return len(TASK_QUEUE)


def get_quota_status(open_id: str, role: str) -> dict:
    """获取用户配额状态"""
    QUOTA_PATH.parent.mkdir(parents=True, exist_ok=True)

    if QUOTA_PATH.exists():
        data = json.loads(QUOTA_PATH.read_text(encoding='utf-8'))
    else:
        data = {"daily_usage": {}}

    today = time.strftime('%Y-%m-%d')
    used = data.get("daily_usage", {}).get(open_id, {}).get(today, 0)
    quota = ROLE_QUOTAS.get(role, 50)

    return {
        "used": used,
        "quota": quota if quota != float('inf') else "无限制",
        "remaining": quota - used if quota != float('inf') else "无限制",
    }


if __name__ == "__main__":
    print("负载管理器已就绪")
    print("角色配额:", ROLE_QUOTAS)