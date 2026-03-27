"""
@description: 会话结束Hook - 强制评审、检查点、归档
@dependencies: sys, json, datetime
@last_modified: 2026-03-17

触发条件: Claude Code会话结束(Stop hook)
执行内容:
1. 检查是否有待评审的变更
2. 创建检查点
3. 执行交叉评审（如有需要）
4. 归档会话状态
5. 输出会话摘要

使用: python scripts/hooks/session_end_hook.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime


def check_pending_review() -> dict:
    """检查是否有待评审的变更"""
    review_request_path = Path(".ai-state/review_request.json")
    if review_request_path.exists():
        with open(review_request_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def create_session_checkpoint() -> str:
    """创建会话检查点"""
    try:
        from src.tools.layered_memory import get_layered_memory
        mem = get_layered_memory()
        ckpt = mem.create_checkpoint("Session end checkpoint")
        return ckpt.checkpoint_id
    except ImportError:
        return "checkpoint_unavailable"


def run_final_review(review_request: dict) -> dict:
    """执行最终评审"""
    try:
        from src.utils.model_gateway import get_model_gateway
        gateway = get_model_gateway()

        # 构建评审内容
        review_prompt = f"""
## 任务后评审请求

文件: {review_request.get('file', 'Unknown')}
原因: {review_request.get('reason', 'Unknown')}
时间: {review_request.get('timestamp', 'Unknown')}

请评审本次会话的变更是否符合项目规范。
输出格式:
{{
  "verdict": "PASS" or "BLOCK",
  "score": <1-10>,
  "issues": [...],
  "suggestions": [...]
}}
"""

        result = gateway.dual_review(
            prompt=review_prompt,
            system_prompt="你是CPO_Critic，负责最终评审。请严格检查变更质量。"
        )

        return {
            "success": True,
            "verdict": result.get("verdict"),
            "passing_models": result.get("passing_models", [])
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def archive_session_state():
    """归档会话状态"""
    session_state = {
        "ended_at": datetime.now().isoformat(),
        "pending_reviews": [],
        "checkpoints": []
    }

    # 收集检查点
    checkpoint_dir = Path(".ai-state/layered_memory/checkpoints")
    if checkpoint_dir.exists():
        for ckpt_file in checkpoint_dir.glob("*.json"):
            session_state["checkpoints"].append(ckpt_file.name)

    # 保存会话状态
    archive_path = Path(".ai-state/session_archive.json")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with open(archive_path, 'w', encoding='utf-8') as f:
        json.dump(session_state, f, ensure_ascii=False, indent=2)

    return session_state


def generate_session_summary() -> str:
    """生成会话摘要"""
    try:
        from src.tools.layered_memory import get_layered_memory
        mem = get_layered_memory()
        return mem.generate_session_summary_for_llm()
    except ImportError:
        return "Summary unavailable"


def main():
    print("=" * 60)
    print("[SESSION END HOOK]")
    print("=" * 60)

    result = {
        "timestamp": datetime.now().isoformat(),
        "checkpoint_id": None,
        "review_result": None,
        "verdict": "OK"
    }

    # 1. 检查待评审
    print("\n[1/4] Checking pending reviews...")
    review_request = check_pending_review()
    if review_request:
        print(f"  Found pending review: {review_request.get('file')}")
    else:
        print("  No pending reviews")

    # 2. 创建检查点
    print("\n[2/4] Creating session checkpoint...")
    result["checkpoint_id"] = create_session_checkpoint()
    print(f"  Checkpoint: {result['checkpoint_id']}")

    # 3. 执行评审（如有需要）
    if review_request:
        print("\n[3/4] Running final review...")
        result["review_result"] = run_final_review(review_request)
        verdict = result["review_result"].get("verdict", "UNKNOWN")
        print(f"  Review verdict: {verdict}")

        if verdict == "BLOCK":
            result["verdict"] = "BLOCK"
            print("\n[BLOCK] Review failed. Please fix issues before next session.")
        else:
            # 清除评审请求
            Path(".ai-state/review_request.json").unlink(missing_ok=True)
    else:
        print("\n[3/4] No review needed")

    # 4. 归档会话状态
    print("\n[4/4] Archiving session state...")
    archive_result = archive_session_state()
    print(f"  Checkpoints archived: {len(archive_result.get('checkpoints', []))}")

    # 5. 生成摘要
    print("\n[SESSION SUMMARY]")
    summary = generate_session_summary()
    print(summary[:500])

    # 保存Hook日志
    log_path = Path(".ai-state/hooks/session_end_log.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")

    print("\n" + "=" * 60)

    # 如果BLOCK，返回非零退出码
    if result["verdict"] == "BLOCK":
        sys.exit(1)

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)