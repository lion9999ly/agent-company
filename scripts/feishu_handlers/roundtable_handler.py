"""
@description: 圆桌系统处理器 - 圆桌任务启动与管理
@dependencies: task_spec, roundtable runner
@last_modified: 2026-04-08
"""
import threading
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def try_handle(text_stripped: str, reply_target: str, reply_type: str,
               open_id: str, chat_id: str, send_reply: Callable) -> bool:
    """圆桌系统指令路由

    Returns:
        bool: 是否处理了该消息
    """
    from scripts.feishu_handlers.chat_helpers import log

    # 圆桌启动
    if text_stripped.startswith("圆桌:") or text_stripped.startswith("圆桌："):
        topic = text_stripped.split(":", 1)[1].strip() if ":" in text_stripped else text_stripped.split("：", 1)[1].strip()
        log(f"[圆桌] 收到请求，topic={topic}")

        from scripts.roundtable.task_spec import load_task_spec
        spec = load_task_spec(topic)
        log(f"[圆桌] TaskSpec 加载结果: {spec is not None}")

        if spec:
            send_reply(reply_target, f"🔵 圆桌启动：{topic}")
            _run_roundtable_background(spec, reply_target, send_reply)
            return True
        else:
            send_reply(reply_target, f"未找到预定义任务：{topic}。请先创建 TaskSpec。")
            return True

    return False


def _run_roundtable_background(spec, reply_target: str, send_reply: Callable):
    """后台执行圆桌任务"""
    def _run():
        try:
            import asyncio
            from scripts.roundtable import run_task
            from src.utils.model_gateway import get_model_gateway
            from src.tools import knowledge_base as kb_module
            from scripts.feishu_handlers.chat_helpers import log as _log

            _log("[圆桌] 后台线程启动")

            _log("[圆桌] 获取 model_gateway...")
            gw = get_model_gateway()
            _log(f"[圆桌] model_gateway 获取成功, models={len(gw.models)}")

            _log("[圆桌] 创建 event loop...")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _log("[圆桌] event loop 创建成功")

            # 简化的飞书通知器
            class FeishuNotifier:
                def notify(self, msg):
                    send_reply(reply_target, msg)

            feishu = FeishuNotifier()
            _log(f"[圆桌] 开始执行 run_task, topic={spec.topic}")
            result = loop.run_until_complete(run_task(spec, gw, kb_module, feishu))
            _log(f"[圆桌] run_task 完成")
            send_reply(reply_target, f"🎯 圆桌任务完成：{spec.output_path}")
        except Exception as e:
            import traceback
            _log(f"[圆桌] 异常: {e}\n{traceback.format_exc()}")
            from scripts.feishu_handlers.chat_helpers import _safe_reply_error
            _safe_reply_error(send_reply, reply_target, "圆桌系统", e)

    threading.Thread(target=_run, daemon=True).start()