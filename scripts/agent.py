"""
@description: 飞书 Bot Agent - 飞书消息 → Claude Code CLI 架构
@dependencies: lark-cli, subprocess, feishu_sdk_client_v2 (WebSocket)
@last_modified: 2026-04-08

架构：
    飞书 WebSocket → agent.py → 快速通道 / Claude Code CLI → lark-cli 回复

快速通道（不走 LLM）：
    状态、监控范围、圆桌:xxx、拉取指令、帮助、验证

自然语言 → Claude Code CLI 理解并执行
"""
import os
import sys
import subprocess
import json
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

# Leo 的 open_id 和 chat_id
LEO_OPEN_ID = os.getenv("LEO_OPEN_ID", "ou_8e5e4f183e9eca4241378e96bac3a751")
LEO_CHAT_ID = os.getenv("LEO_CHAT_ID", "oc_43bca641a75a5beed8215541845c7b73")

# Claude Code CLI 路径（Windows nodejs 安装）
NODEJS_PATH = Path.home() / "nodejs"
CLAUDE_CLI_PATH = NODEJS_PATH / "claude.cmd"

# Z.AI 环境变量列表（需要在调用 Claude Code CLI 时清除）
ZAI_ENV_KEYS = [
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
    "CLAUDE_BASE_URL",
]


def _get_clean_env() -> dict:
    """获取干净的环境变量，移除 Z.AI 重定向，并添加 nodejs 到 PATH"""
    clean_env = {**os.environ}
    for key in ZAI_ENV_KEYS:
        clean_env.pop(key, None)
    # 确保 nodejs 在 PATH 中
    nodejs_path = str(NODEJS_PATH)
    if nodejs_path not in clean_env.get("PATH", ""):
        clean_env["PATH"] = nodejs_path + ";" + clean_env.get("PATH", "")
    return clean_env

# 飞书 CLI 路径
from scripts.feishu_output import LARK_CLI


# ============================================================
# 快速通道处理器
# ============================================================

def handle_status(chat_id: str):
    """状态指令快速通道"""
    from scripts.feishu_handlers.text_router import _handle_dashboard
    from scripts.feishu_output import update_doc
    import subprocess

    status_path = PROJECT_ROOT / ".ai-state" / "system_status.md"
    if status_path.exists():
        content = status_path.read_text(encoding="utf-8")
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()
        doc_url = update_doc("系统状态", content)
        if doc_url:
            cli_send_message(f"📊 系统状态已更新\n🔗 {doc_url}", chat_id)
            return

    # 回退
    cli_send_message("📊 系统状态文件不存在，请运行 auto_restart_and_verify.py", chat_id)


def handle_monitor_scope(chat_id: str):
    """监控范围快速通道"""
    # 修复：读取正确的文件名
    scope_path = PROJECT_ROOT / ".ai-state" / "competitor_monitor_config.json"
    if scope_path.exists():
        try:
            scope = json.loads(scope_path.read_text(encoding="utf-8"))
            layers = scope.get("monitor_layers", {})
            msg = f"📡 监控范围（6 层）\n\n"
            for layer_key, layer_info in layers.items():
                desc = layer_info.get("description", layer_key)
                msg += f"【{desc}】\n"
                # 品牌或主题
                if "brands" in layer_info:
                    brands = layer_info["brands"]
                    msg += f"  品牌: {', '.join(brands[:5])}" + ("..." if len(brands) > 5 else "") + "\n"
                if "topics" in layer_info:
                    topics = layer_info["topics"]
                    msg += f"  主题: {', '.join(topics[:5])}" + ("..." if len(topics) > 5 else "") + "\n"
                # 搜索关键词（取前2个）
                keywords = layer_info.get("search_keywords", [])[:2]
                if keywords:
                    msg += f"  关键词: {'; '.join(keywords)}\n"
                msg += "\n"
            cli_send_message(msg, chat_id)
        except Exception as e:
            cli_send_message(f"⚠️ 监控范围解析失败: {e}", chat_id)
    else:
        cli_send_message("⚠️ monitor_scope.json 不存在", chat_id)


def handle_help(chat_id: str):
    """帮助快速通道"""
    help_msg = """📖 可用指令

【精确指令】
• 状态 - 系统状态仪表盘
• 监控范围 - 当前监控配置
• 圆桌:xxx - 启动圆桌讨论
• 拉取指令 - 从 GitHub 拉取待办
• 自检 / 验证 - 运行系统自检
• 深度学习 - 启动夜间学习（7h）
• 自学习 - 启动自动学习（30min）
• KB治理 - 知识库治理
• 早报 - 生成每日简报

【自然语言】
直接说你想做什么，我会理解并执行。
例如："帮我分析竞品格局"、"整理一下知识库"

---
*由 Claude Code + 飞书 CLI 驱动*"""
    cli_send_message(help_msg, chat_id)


def handle_self_verify(chat_id: str):
    """自检快速通道"""
    cli_send_message("🔍 开始系统自检...", chat_id)

    def _run():
        import subprocess
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "auto_restart_and_verify.py"),
             "--verify-only", "--no-push"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=60,
            encoding='utf-8', errors='ignore'
        )
        # 读取报告
        report_path = PROJECT_ROOT / ".ai-state" / "verify_report.md"
        if report_path.exists():
            report = report_path.read_text(encoding="utf-8")
            passed = report.split("**通过率**: ")
            if len(passed) > 1:
                rate = passed[1].split("\n")[0]
            else:
                rate = "N/A"
            from scripts.feishu_output import update_doc
            doc_url = update_doc("验证报告", report)
            if doc_url:
                cli_send_message(f"🔍 自检完成：{rate}\n📄 详情：{doc_url}", chat_id)
            else:
                cli_send_message(f"🔍 自检完成：{rate}", chat_id)
        else:
            cli_send_message(f"⚠️ 自检失败: {result.stderr[:200] if result.stderr else 'unknown'}", chat_id)

    threading.Thread(target=_run, daemon=True).start()


def handle_roundtable(text: str, chat_id: str):
    """圆桌快速通道"""
    from scripts.feishu_handlers.roundtable_handler import try_handle

    # 使用现有的 roundtable_handler
    def fake_send_reply(target, msg):
        cli_send_message(msg, chat_id)

    try_handle(text.strip(), chat_id, "chat", LEO_OPEN_ID, chat_id, fake_send_reply)


def handle_fetch_instruction(text: str, chat_id: str):
    """拉取指令快速通道"""
    from scripts.feishu_handlers.import_handlers import try_handle

    def fake_send_reply(target, msg):
        cli_send_message(msg, chat_id)

    try_handle(text.strip(), chat_id, "chat", LEO_OPEN_ID, chat_id, fake_send_reply)


def handle_night_learning(chat_id: str):
    """深度学习快速通道"""
    from scripts.feishu_handlers.learning_handlers import try_handle

    def fake_send_reply(target, msg):
        cli_send_message(msg, chat_id)

    try_handle("深度学习", chat_id, "chat", LEO_OPEN_ID, chat_id, fake_send_reply)


def handle_auto_learn(chat_id: str):
    """自学习快速通道"""
    from scripts.feishu_handlers.learning_handlers import try_handle

    def fake_send_reply(target, msg):
        cli_send_message(msg, chat_id)

    try_handle("自学习", chat_id, "chat", LEO_OPEN_ID, chat_id, fake_send_reply)


def handle_kb_govern(chat_id: str):
    """KB治理快速通道"""
    from scripts.feishu_handlers.learning_handlers import try_handle

    def fake_send_reply(target, msg):
        cli_send_message(msg, chat_id)

    try_handle("KB治理", chat_id, "chat", LEO_OPEN_ID, chat_id, fake_send_reply)


def handle_logs(text: str, chat_id: str):
    """日志快速通道 - 返回最近日志"""
    import re

    # 解析行数参数
    match = re.search(r'日志\s*(\d+)?', text)
    lines = int(match.group(1)) if match and match.group(1) else 50
    lines = min(lines, 200)  # 最多 200 行

    log_path = PROJECT_ROOT / ".ai-state" / "feishu_sdk.log"

    if not log_path.exists():
        cli_send_message("⚠️ 日志文件不存在", chat_id)
        return

    try:
        # 读取最后 N 行
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:]

        # 组装消息
        content = ''.join(last_lines)
        if len(content) > 4000:
            content = content[-4000:]  # 飞书消息限制

        cli_send_message(f"📋 最近 {len(last_lines)} 行日志：\n\n```\n{content}\n```", chat_id)
    except Exception as e:
        cli_send_message(f"⚠️ 读取日志失败: {e}", chat_id)


# ============================================================
# 快速通道路由表
# ============================================================

FAST_COMMANDS = {
    "状态": handle_status,
    "系统状态": handle_status,
    "status": handle_status,
    "dashboard": handle_status,
    "监控范围": handle_monitor_scope,
    "帮助": handle_help,
    "help": handle_help,
    "自检": handle_self_verify,
    "验证": handle_self_verify,
    "深度学习": handle_night_learning,
    "自学习": handle_auto_learn,
    "KB治理": handle_kb_govern,
    "日志": lambda chat_id: handle_logs("日志", chat_id),
}

FAST_PREFIXES = {
    "圆桌:": handle_roundtable,
    "圆桌：": handle_roundtable,
    "拉取指令": handle_fetch_instruction,
    "执行 issue": handle_fetch_instruction,
    "执行issue": handle_fetch_instruction,
    "日志": handle_logs,
}


def try_fast_commands(text: str, chat_id: str) -> bool:
    """尝试快速通道"""
    text_stripped = text.strip()

    # 精确匹配
    if text_stripped in FAST_COMMANDS:
        FAST_COMMANDS[text_stripped](chat_id)
        return True

    # 前缀匹配
    for prefix, handler in FAST_PREFIXES.items():
        if text_stripped.startswith(prefix):
            handler(text_stripped, chat_id)
            return True

    return False


# ============================================================
# 飞书 CLI 发送消息
# ============================================================

def cli_send_message(text: str, chat_id: str) -> bool:
    """通过飞书 CLI 发送消息

    Args:
        text: 消息内容
        chat_id: 目标聊天 ID（从飞书事件提取，必需）
    """
    if not chat_id:
        print(f"[LarkCLI] 错误: chat_id 为空，无法发送")
        return False

    print(f"[LarkCLI] 发送到 chat_id={chat_id}, 内容长度={len(text)}")
    try:
        result = subprocess.run(
            [LARK_CLI, "im", "+messages-send",
             "--chat-id", chat_id, "--text", text, "--as", "bot"],
            capture_output=True, text=True, timeout=15,
            encoding='utf-8', errors='ignore'
        )
        if result.returncode == 0:
            return True
        else:
            print(f"[LarkCLI] 发送失败: {result.stderr[:100] if result.stderr else result.stdout[:100]}")
            return False
    except Exception as e:
        print(f"[LarkCLI] 发送异常: {e}")
        return False


# ============================================================
# Claude Code CLI 处理自然语言
# ============================================================

def build_prompt(message_text: str, chat_id: str, open_id: str) -> str:
    """构建 Claude Code prompt"""
    return f"""用户在飞书发来消息，请理解并执行：

消息内容：{message_text}

执行要求：
1. 理解用户意图
2. 执行相应操作（如果需要调用脚本，说明调用哪个）
3. 用简洁的语言回复用户（不超过500字）

如果用户只是打招呼或闲聊，友好回复即可。
如果用户请求需要执行复杂任务，告知用户已启动任务并会后续汇报。"""


def handle_with_claude_code(message_text: str, chat_id: str, open_id: str):
    """通过 Claude Code CLI 处理自然语言"""
    # DEBUG: 打印收到的参数
    print(f"[Agent-Debug] 收到文本: '{message_text[:100]}...' (len={len(message_text)})")
    print(f"[Agent-Debug] chat_id: {chat_id}, open_id: {open_id}")

    prompt = build_prompt(message_text, chat_id, open_id)
    print(f"[Agent-Debug] CLI prompt 长度: {len(prompt)}")

    # 清除 Z.AI 环境变量，确保调用真正的 Claude Code CLI
    clean_env = _get_clean_env()

    # 使用完整的 Claude CLI 路径
    claude_cmd = str(CLAUDE_CLI_PATH) if CLAUDE_CLI_PATH.exists() else "claude"
    print(f"[Agent-Debug] claude_cmd: {claude_cmd}")

    try:
        result = subprocess.run(
            [claude_cmd, "-p", prompt],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120,  # 2分钟超时
            encoding='utf-8', errors='ignore',
            env=clean_env,  # 使用干净的环境变量
            shell=True  # Windows 需要 shell=True 找到 .cmd 文件
        )

        if result.returncode == 0 and result.stdout.strip():
            response = result.stdout.strip()
            # 截断到飞书消息限制
            if len(response) > 2000:
                response = response[:2000] + "..."
            cli_send_message(response, chat_id)
        else:
            error_msg = result.stderr[:200] if result.stderr else "未知错误"
            cli_send_message(f"⚠️ 处理出错：{error_msg}", chat_id)

    except subprocess.TimeoutExpired:
        cli_send_message("⚠️ 处理超时，请稍后重试或简化请求", chat_id)
    except FileNotFoundError:
        cli_send_message("⚠️ Claude Code CLI 未安装，请安装后使用", chat_id)
    except Exception as e:
        cli_send_message(f"⚠️ 处理异常：{str(e)[:100]}", chat_id)


# ============================================================
# 主消息处理入口
# ============================================================

def handle_message(message_text: str, chat_id: str, open_id: str):
    """飞书消息主入口"""

    # 1. 快速通道
    if try_fast_commands(message_text, chat_id):
        return

    # 2. 自然语言 → Claude Code CLI
    handle_with_claude_code(message_text, chat_id, open_id)


# ============================================================
# WebSocket 监听器桥接
# ============================================================

def on_feishu_message(event: dict):
    """飞书 WebSocket 消息回调"""
    try:
        # 解析消息
        message = event.get("message", {})
        content = json.loads(message.get("content", "{}"))
        text = content.get("text", "")

        if not text:
            return

        chat_id = message.get("chat_id", "")
        open_id = message.get("sender", {}).get("sender_id", {}).get("open_id", "")

        print(f"[Agent] 收到消息: {text[:50]}... (chat={chat_id})")

        # 传给 handle_message
        handle_message(text, chat_id, open_id)

    except Exception as e:
        print(f"[Agent] 解析消息异常: {e}")


# ============================================================
# 独立运行模式（用于测试）
# ============================================================

def run_standalone():
    """独立运行模式（轮询飞书消息）"""
    print("[Agent] 独立模式启动，轮询飞书消息...")

    last_msg_time = ""

    while True:
        try:
            # 通过 CLI 获取最新消息
            result = subprocess.run(
                [LARK_CLI, "im", "+chat-messages-list",
                 "--chat-id", LEO_CHAT_ID, "--page-size", "1", "--as", "bot"],
                capture_output=True, text=True, timeout=10,
                encoding='utf-8', errors='ignore'
            )

            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    items = data.get("data", {}).get("items", [])
                    if items:
                        msg = items[0]
                        msg_time = msg.get("create_time", "")
                        if msg_time != last_msg_time:
                            last_msg_time = msg_time
                            content = json.loads(msg.get("body", {}).get("content", "{}"))
                            text = content.get("text", "")
                            if text:
                                print(f"[Agent] 新消息: {text[:50]}")
                                handle_message(text, LEO_CHAT_ID, LEO_OPEN_ID)
                except json.JSONDecodeError:
                    pass

            time.sleep(5)  # 5秒轮询

        except KeyboardInterrupt:
            print("\n[Agent] 停止")
            break
        except Exception as e:
            print(f"[Agent] 轮询异常: {e}")
            time.sleep(10)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--standalone", action="store_true", help="独立轮询模式")
    args = parser.parse_args()

    if args.standalone:
        run_standalone()
    else:
        # WebSocket 模式需要 feishu_sdk_client_v2.py 调用
        print("[Agent] WebSocket 模式需通过 feishu_sdk_client_v2.py 启动")
        print("使用 --standalone 参数运行轮询模式")