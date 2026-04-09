"""
@description: 飞书长连接客户端 v2 - 模块化重构版
@dependencies: lark-oapi, scripts/feishu_handlers/*, scripts/agent
@last_modified: 2026-04-08

使用方法：
    python scripts/feishu_sdk_client_v2.py

v2.1 更新：
    - 集成 agent.py (飞书消息 → 快速通道 / Claude Code CLI)
    - 保留旧路由器作为降级方案
"""
import os
import sys
import json
import threading
import time
from pathlib import Path
from datetime import datetime

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

# 强制刷新日志
try:
    sys.stdout.reconfigure(line_buffering=True)
except:
    import functools
    print = functools.partial(print, flush=True)

# === lark SDK 初始化 ===
try:
    import lark_oapi as lark
except ImportError:
    print("请安装: pip install lark-oapi")
    sys.exit(1)

# === 导入各模块 ===
from scripts.feishu_handlers.chat_helpers import send_reply, log, get_session_id, set_reply_context, APP_ID, APP_SECRET
from scripts.feishu_handlers.text_router import route_text_message
from scripts.feishu_handlers.image_handler import handle_image_message, handle_audio_message, handle_file_message

# === 新架构：Agent 模式 ===
# 使用 agent.py 作为消息处理器（飞书 → Claude Code CLI）
USE_AGENT_MODE = os.getenv("USE_AGENT_MODE", "true").lower() == "true"

# === 消息去重 ===
_processed_msgs = set()
_MAX_MSG_CACHE = 500


def handle_message(event):
    """处理收到的消息 - v2 模块化版本"""
    try:
        print(f"\n{'='*50}")
        print(f"收到消息!")

        message = event.event.message
        sender = event.event.sender

        # 获取基础信息
        msg_id = message.message_id
        msg_type = message.message_type
        chat_id = message.chat_id

        # 消息去重
        if msg_id in _processed_msgs:
            print(f"[Skip] 重复消息: {msg_id}")
            return
        _processed_msgs.add(msg_id)
        if len(_processed_msgs) > _MAX_MSG_CACHE:
            _processed_msgs.clear()

        # 过滤机器人自己的消息
        sender_type = getattr(sender, 'sender_type', '')
        print(f"  sender_type={sender_type}")  # #2 诊断日志

        if sender_type == 'app':
            print("[Skip] 机器人自己的消息")
            return

        # #2 额外过滤：检查 sender 的 app_id 是否与当前 bot 相同
        sender_id = getattr(sender, 'sender_id', None)
        print(f"  sender_type={sender_type}, sender_id={sender_id}")  # 完整打印诊断
        if sender_id:
            sender_app_id = getattr(sender_id, 'app_id', '')
            if sender_app_id and sender_app_id == APP_ID:
                print(f"[Skip] 来自当前 bot 的消息 (app_id: {sender_app_id[:10]}...)")
                return

        open_id = sender.sender_id.open_id if sender.sender_id else ""
        content = json.loads(message.content) if message.content else {}

        print(f"  msg_type={msg_type}, content_len={len(str(content))}")
        print(f"  Open ID: {open_id}")
        print(f"  Chat ID: {chat_id}")

        # 判断群聊/私聊
        chat_type = message.chat_type if hasattr(message, 'chat_type') else ""
        is_group = chat_type == "group"

        # 群聊需要 @机器人
        if is_group:
            mentions = message.mentions if hasattr(message, 'mentions') else []
            is_mentioned = bool(mentions)
            if not is_mentioned:
                return
            print(f"  [群聊] 检测到 @")

        # 确定回复目标
        reply_target = chat_id if is_group else open_id
        reply_type = "chat_id" if is_group else "open_id"

        # 设置回复上下文
        set_reply_context(reply_target, reply_type)

        # 获取 session_id（用于对话记忆）
        session_id = get_session_id(open_id, chat_id)

        # === 按消息类型分发 ===
        if msg_type == "text":
            text = content.get("text", "")

            # 群聊清理 @mention
            if is_group and hasattr(message, 'mentions') and message.mentions:
                for mention in message.mentions:
                    if hasattr(mention, 'key'):
                        text = text.replace(mention.key, "").strip()
                # 额外清理 @xxx 格式
                text = __import__('re').sub(r'@[^\s]+\s*', '', text).strip()

            print(f"  消息类型: text, 内容: {text[:50]}...")

            # === v2.1: 使用 Agent 模式（飞书 → Claude Code CLI）===
            print(f"  [DEBUG] USE_AGENT_MODE={USE_AGENT_MODE}")
            if USE_AGENT_MODE:
                try:
                    from scripts.agent import handle_message as agent_handle_message
                    print(f"  [Agent模式] 调用 agent.handle_message(text, chat_id={chat_id}, open_id={open_id})")
                    agent_handle_message(text, chat_id, open_id)
                    print(f"  [Agent模式] agent.handle_message 返回")
                except Exception as e:
                    import traceback
                    print(f"  [Agent模式失败] {e}")
                    traceback.print_exc()
                    print(f"  [降级] 使用旧路由器")
                    route_text_message(
                        text=text,
                        reply_target=reply_target,
                        reply_type=reply_type,
                        open_id=open_id,
                        chat_id=chat_id,
                        send_reply=send_reply,
                        session_id=session_id
                    )
            else:
                # 旧路由器
                print(f"  [旧路由器] USE_AGENT_MODE=False")
                route_text_message(
                    text=text,
                    reply_target=reply_target,
                    reply_type=reply_type,
                    open_id=open_id,
                    chat_id=chat_id,
                    send_reply=send_reply,
                    session_id=session_id
                )

        elif msg_type == "image":
            print(f"  消息类型: image")
            image_key = content.get("image_key", "")
            handle_image_message(open_id, image_key, msg_id, reply_target, send_reply)

        elif msg_type == "audio":
            print(f"  消息类型: audio")
            handle_audio_message(open_id, msg_id, json.dumps(content), reply_target, send_reply)

        elif msg_type == "file":
            print(f"  消息类型: file")
            file_key = content.get("file_key", "")
            file_name = content.get("file_name", "unknown")
            handle_file_message(open_id, file_key, file_name, reply_target, send_reply)

        elif msg_type == "post":
            print(f"  消息类型: post (富文本)")
            # 富文本消息提取纯文本
            post_content = content.get("content", [])
            text_parts = []
            for block in post_content:
                if isinstance(block, list):
                    for item in block:
                        if isinstance(item, dict) and "text" in item:
                            text_parts.append(item["text"])
            text = "\n".join(text_parts)
            if text:
                route_text_message(
                    text=text,
                    reply_target=reply_target,
                    reply_type=reply_type,
                    open_id=open_id,
                    chat_id=chat_id,
                    send_reply=send_reply,
                    session_id=session_id
                )

        else:
            print(f"  未支持的消息类型: {msg_type}")

    except Exception as e:
        print(f"[Error] handle_message: {e}")
        import traceback
        traceback.print_exc()


# === 防止定时任务和手动触发冲突 ===
_deep_learning_running = False
_deep_learning_lock = threading.Lock()


def _is_deep_learning_running():
    """检查深度学习是否正在运行"""
    with _deep_learning_lock:
        return _deep_learning_running


def _set_deep_learning_running(running: bool):
    """设置深度学习运行状态"""
    global _deep_learning_running
    with _deep_learning_lock:
        _deep_learning_running = running


# === 定时任务 ===
LEO_OPEN_ID = "ou_8e5e4f183e9eca4241378e96bac3a751"


def _start_scheduled_tasks():
    """启动定时任务调度器"""
    try:
        import schedule
    except ImportError:
        print("[Scheduler] 缺少 schedule 库，跳过定时任务: pip install schedule")
        return

    # 每天 01:00 深度学习 7h
    def _run_deep_research():
        if _is_deep_learning_running():
            print("[Scheduler] 深度学习正在运行，跳过本次定时触发")
            return
        try:
            _set_deep_learning_running(True)
            from scripts.tonight_deep_research import run_deep_learning
            print("[Scheduler] 启动每日深度学习...")
            run_deep_learning(max_hours=7, progress_callback=lambda msg: send_reply(LEO_OPEN_ID, msg, "open_id"))
            # 深度学习完成后发送日报
            from scripts.feishu_handlers.text_router import _handle_morning_brief
            _handle_morning_brief(LEO_OPEN_ID, lambda msg: send_reply(LEO_OPEN_ID, msg, "open_id"))
        except Exception as e:
            print(f"[Scheduler] 深度学习失败: {e}")
        finally:
            _set_deep_learning_running(False)

    # 每天 06:00 竞品监控
    def _run_competitor_monitor():
        try:
            from scripts.competitor_monitor import run_competitor_monitor
            print("[Scheduler] 启动竞品监控...")
            run_competitor_monitor()
        except Exception as e:
            print(f"[Scheduler] 竞品监控失败: {e}")

    # 每天 07:00 系统日报
    def _run_daily_report():
        try:
            from scripts.daily_system_report import generate_daily_report
            print("[Scheduler] 启动系统日报...")
            generate_daily_report()
        except Exception as e:
            print(f"[Scheduler] 系统日报失败: {e}")

    # 注册定时任务
    schedule.every().day.at("01:00").do(_run_deep_research)
    schedule.every().day.at("06:00").do(_run_competitor_monitor)
    schedule.every().day.at("07:00").do(_run_daily_report)

    # 后台线程运行调度器
    def _scheduler_loop():
        while True:
            try:
                schedule.run_pending()
            except Exception as e:
                print(f"[Scheduler] 调度器异常: {e}")
            time.sleep(60)

    threading.Thread(target=_scheduler_loop, daemon=True).start()
    print("[Scheduler] 定时任务已注册:")
    print("  - 01:00 深度学习 (7h)")
    print("  - 06:00 竞品监控")
    print("  - 07:00 系统日报")


def _start_heartbeat():
    """启动心跳"""
    _heartbeat_path = Path(__file__).parent.parent / ".ai-state" / "heartbeat.txt"
    _heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    _heartbeat_path.write_text(datetime.now().isoformat(), encoding="utf-8")
    print("[Heartbeat] 心跳已初始化")

    def _heartbeat_loop():
        while True:
            time.sleep(30)
            try:
                _heartbeat_path.write_text(datetime.now().isoformat(), encoding="utf-8")
            except:
                pass

    threading.Thread(target=_heartbeat_loop, daemon=True).start()


# === 启动服务 ===
def main():
    """启动飞书长连接客户端"""
    # P2 #8: SDK 进程锁 - 检查是否已有实例运行
    PID_FILE = PROJECT_ROOT / ".ai-state" / "sdk.pid"
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    if PID_FILE.exists():
        try:
            existing_pid = int(PID_FILE.read_text().strip())
            # 检查进程是否存在
            import psutil
            if psutil.pid_exists(existing_pid):
                proc = psutil.Process(existing_pid)
                if "feishu_sdk_client" in " ".join(proc.cmdline()):
                    print(f"[Error] SDK 已在运行 (PID: {existing_pid})")
                    print(f"[Error] 如需重启，请先停止：python scripts/feishu_sdk_client_v2.py --stop")
                    sys.exit(1)
        except Exception as e:
            print(f"[Warn] PID 检查失败: {e}，继续启动")

    # 写入当前 PID
    PID_FILE.write_text(str(os.getpid()))
    print(f"[SDK] PID 文件已写入: {os.getpid()}")

    print(f"{'#'*60}")
    print(f"# 飞书长连接客户端 v2 启动")
    print(f"# APP_ID: {APP_ID[:10]}...")
    print(f"# 模块化架构")
    print(f"{'#'*60}")

    if not APP_ID or not APP_SECRET:
        print("[Error] 请设置环境变量 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
        sys.exit(1)

    # 注册消息处理器
    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(handle_message) \
        .build()

    # 创建长连接客户端
    cli = lark.ws.Client(
        APP_ID,
        APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.DEBUG
    )

    # 启动心跳
    _start_heartbeat()

    # 启动定时任务
    try:
        _start_scheduled_tasks()
    except Exception as e:
        print(f"[Scheduler] 定时任务启动失败: {e}")

    # 启动每日定时学习（30min）
    try:
        from scripts.auto_learn import start_auto_learn_scheduler
        start_auto_learn_scheduler()
    except Exception as e:
        print(f"[AutoLearn] 定时器启动失败: {e}")

    print("服务启动，等待消息...")
    cli.start()


if __name__ == "__main__":
    main()