# Day 17 系统全量审计 - scripts/feishu_handlers/learning_handlers.py

```python
"""
@description: 学习相关处理器 - 深度学习、自学习、KB治理
@dependencies: chat_helpers, runner
@last_modified: 2026-04-08
"""
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def try_handle(text_stripped: str, reply_target: str, reply_type: str,
               open_id: str, chat_id: str, send_reply: Callable) -> bool:
    """学习相关指令路由

    Returns:
        bool: 是否处理了该消息
    """
    from scripts.feishu_handlers.chat_helpers import log

    # 深度学习
    if text_stripped in ("深度学习", "deep learning", "今晚学习", "night learning"):
        _handle_deep_learning(reply_target, send_reply)
        return True

    # 自学习
    if text_stripped in ("自学习", "auto learn", "自主学习"):
        _handle_auto_learning(reply_target, send_reply)
        return True

    # KB 治理
    if text_stripped in ("KB治理", "kb governance", "知识库治理"):
        _handle_kb_governance(reply_target, send_reply)
        return True

    # 日报
    if text_stripped in ("早报", "morning", "日报", "daily"):
        _handle_morning_brief(reply_target, send_reply)
        return True

    # 滴灌
    if text_stripped in ("滴灌", "knowledge drip"):
        _handle_drip_knowledge(reply_target, send_reply)
        return True

    if text_stripped in ("关闭滴灌", "stop drip"):
        send_reply(reply_target, "[OK] 已关闭知识滴灌")
        return True

    if text_stripped in ("开启滴灌", "start drip"):
        send_reply(reply_target, "[OK] 已开启知识滴灌")
        return True

    # KB 统计
    if text_stripped in ("KB统计", "kb stats", "知识库统计"):
        _handle_kb_stats(reply_target, send_reply)
        return True

    return False


def _handle_deep_learning(reply_target: str, send_reply: Callable):
    """启动深度学习"""
    try:
        from scripts.deep_research.runner import run_all
        send_reply(reply_target, "[OK] 深度学习已启动，预计运行数小时。完成后会推送报告。")
        import threading
        def _run():
            try:
                run_all(progress_callback=lambda msg: send_reply(reply_target, msg))
            except Exception as e:
                send_reply(reply_target, f"[ERROR] 深度学习失败: {e}")
        threading.Thread(target=_run, daemon=True).start()
    except Exception as e:
        send_reply(reply_target, f"[ERROR] 启动失败: {e}")


def _handle_auto_learning(reply_target: str, send_reply: Callable):
    """启动自学习"""
    try:
        from scripts.auto_learn import run_auto_learn
        send_reply(reply_target, "[OK] 自学习已启动（30分钟周期）。")
        import threading
        threading.Thread(target=run_auto_learn, daemon=True).start()
    except Exception as e:
        send_reply(reply_target, f"[ERROR] 启动失败: {e}")


def _handle_kb_governance(reply_target: str, send_reply: Callable):
    """启动 KB 治理"""
    try:
        from scripts.kb_governance import run_governance
        send_reply(reply_target, "[OK] KB 治理已启动。")
        import threading
        def _run():
            try:
                result = run_governance()
                send_reply(reply_target, result[:1500] if result else "[OK] 治理完成")
            except Exception as e:
                send_reply(reply_target, f"[ERROR] 治理失败: {e}")
        threading.Thread(target=_run, daemon=True).start()
    except Exception as e:
        send_reply(reply_target, f"[ERROR] 启动失败: {e}")


def _handle_morning_brief(reply_target: str, send_reply: Callable):
    """生成早报"""
    try:
        from scripts.feishu_handlers.text_router import _handle_morning_brief as _orig
        _orig(reply_target, send_reply)
    except Exception as e:
        send_reply(reply_target, f"[ERROR] 早报生成失败: {e}")


def _handle_drip_knowledge(reply_target: str, send_reply: Callable):
    """知识滴灌"""
    try:
        from scripts.feishu_handlers.text_router import _handle_drip_knowledge as _orig
        _orig(reply_target, send_reply)
    except Exception as e:
        send_reply(reply_target, f"[ERROR] 滴灌失败: {e}")


def _handle_kb_stats(reply_target: str, send_reply: Callable):
    """KB 统计"""
    try:
        from scripts.feishu_handlers.text_router import _handle_kb_stats as _orig
        _orig(reply_target, send_reply, detailed=False)
    except Exception as e:
        send_reply(reply_target, f"[ERROR] 统计失败: {e}")
```
