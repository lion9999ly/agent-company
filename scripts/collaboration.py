"""协作工作流 — 提交→审批→通知
@description: 提交分析供审批、审批后通知
@dependencies: 无
@last_modified: 2026-04-04
"""
import json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SUBMISSIONS_DIR = PROJECT_ROOT / ".ai-state" / "submissions"
SUBMISSIONS_DIR.mkdir(parents=True, exist_ok=True)


def submit_for_review(content: str, submitter: str, reviewer: str, title: str) -> str:
    """提交分析供审批

    Args:
        content: 提交内容
        submitter: 提交者标识
        reviewer: 审批者标识
        title: 提交标题

    Returns:
        提交 ID
    """
    sub_id = f"sub_{int(time.time())}"
    entry = {
        "id": sub_id,
        "title": title,
        "content": content,
        "submitter": submitter,
        "reviewer": reviewer,
        "status": "pending",
        "submitted_at": time.strftime('%Y-%m-%d %H:%M'),
    }
    path = SUBMISSIONS_DIR / f"{sub_id}.json"
    path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding='utf-8')
    return sub_id


def approve_submission(sub_id: str, comment: str = "") -> bool:
    """审批提交

    Args:
        sub_id: 提交 ID
        comment: 审批备注

    Returns:
        是否成功
    """
    path = SUBMISSIONS_DIR / f"{sub_id}.json"
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding='utf-8'))
    data["status"] = "approved"
    data["comment"] = comment
    data["reviewed_at"] = time.strftime('%Y-%m-%d %H:%M')
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return True


def reject_submission(sub_id: str, reason: str = "") -> bool:
    """拒绝提交"""
    path = SUBMISSIONS_DIR / f"{sub_id}.json"
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding='utf-8'))
    data["status"] = "rejected"
    data["reason"] = reason
    data["reviewed_at"] = time.strftime('%Y-%m-%d %H:%M')
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return True


def get_pending_submissions(reviewer: str = "") -> list:
    """获取待审批的提交

    Args:
        reviewer: 审批者标识（可选筛选）

    Returns:
        待审批提交列表
    """
    results = []
    for f in SUBMISSIONS_DIR.glob("sub_*.json"):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            if data.get("status") == "pending":
                if not reviewer or reviewer in data.get("reviewer", ""):
                    results.append(data)
        except Exception:
            continue
    return results


def get_submission(sub_id: str) -> dict:
    """获取单个提交"""
    path = SUBMISSIONS_DIR / f"{sub_id}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def get_all_submissions() -> list:
    """获取所有提交"""
    results = []
    for f in SUBMISSIONS_DIR.glob("sub_*.json"):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            results.append(data)
        except Exception:
            continue
    return results


if __name__ == "__main__":
    # 测试
    sub_id = submit_for_review("测试提交内容", "system", "Leo", "测试提交")
    print(f"提交 ID: {sub_id}")
    pending = get_pending_submissions()
    print(f"待审批: {len(pending)}")