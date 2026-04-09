# Day 17 系统状态审计 - Part 1: 核心代码

## 1. scripts/agent.py（完整 458 行）

```python
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
    scope_path = PROJECT_ROOT / ".ai-state" / "monitor_scope.json"
    if scope_path.exists():
        try:
            scope = json.loads(scope_path.read_text(encoding="utf-8"))
            layers = scope.get("layers", [])
            msg = f"📡 监控范围\n共 {len(layers)} 层：\n"
            for i, layer in enumerate(layers[:6], 1):
                msg += f"{i}. {layer.get('name', '未知')} ({len(layer.get('keywords', []))} 关键词)\n"
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
}

FAST_PREFIXES = {
    "圆桌:": handle_roundtable,
    "圆桌：": handle_roundtable,
    "拉取指令": handle_fetch_instruction,
    "执行 issue": handle_fetch_instruction,
    "执行issue": handle_fetch_instruction,
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
```

---

## 2. scripts/feishu_handlers/text_router.py（完整）

> 文件约 559 行，见 GitHub raw file: https://raw.githubusercontent.com/lion9999ly/agent-company/main/scripts/feishu_handlers/text_router.py

关键结构摘要：
- `route_text_message()` 主入口（第23行）
- 路由优先级：精确指令 → Handler模块 → 结构化文档 → 智能对话兜底
- Handler模块：learning_handlers, roundtable_handler, import_handlers, smart_chat
- `_handle_dashboard()` 状态仪表盘（第325行）
- `_handle_morning_brief()` 早报生成（第278行）

---

## 3. scripts/feishu_output.py（完整）

```python
"""
@description: 飞书输出工具 — 统一输出到飞书云文档/多维表格
@dependencies: subprocess, lark-cli
@last_modified: 2026-04-08
"""
import subprocess
import json
import shutil
import os
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DOC_REGISTRY_PATH = PROJECT_ROOT / ".ai-state" / "feishu_doc_registry.json"
LEO_OPEN_ID = os.getenv("LEO_OPEN_ID", "ou_8e5e4f183e9eca4241378e96bac3a751")


def _find_lark_cli() -> str:
    """查找 lark-cli 可执行文件路径"""
    result = shutil.which("lark-cli")
    if result:
        return result

    common_paths = [
        "C:\\Users\\uih00653\\nodejs\\lark-cli.cmd",
        os.path.expanduser("~\\nodejs\\lark-cli.cmd"),
        "lark-cli",
    ]
    for path in common_paths:
        if Path(path).exists() or path == "lark-cli":
            return path
    return "lark-cli"


LARK_CLI = _find_lark_cli()


def _load_registry() -> dict:
    """加载文档注册表"""
    if DOC_REGISTRY_PATH.exists():
        try:
            return json.loads(DOC_REGISTRY_PATH.read_text(encoding="utf-8"))
        except:
            return {}
    return {}


def _save_registry(data: dict):
    """保存文档注册表"""
    DOC_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_REGISTRY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_doc_id(output: str) -> Optional[str]:
    """从 lark-cli 输出提取文档 ID"""
    try:
        data = json.loads(output)
        return data.get("data", {}).get("doc_id")
    except:
        import re
        match = re.search(r'"doc_id":\s*"([^"]+)"', output)
        if match:
            return match.group(1)
    return None


def _extract_doc_url(output: str) -> Optional[str]:
    """从 lark-cli 输出提取文档 URL"""
    try:
        data = json.loads(output)
        return data.get("data", {}).get("doc_url")
    except:
        import re
        match = re.search(r'"doc_url":\s*"([^"]+)"', output)
        if match:
            return match.group(1)
    return None


def _add_edit_permission(doc_id: str, doc_type: str = "docx") -> bool:
    """给 Leo 添加文档编辑权限"""
    try:
        result = subprocess.run(
            [LARK_CLI, "drive", "permission.members", "create",
             "--params", json.dumps({"token": doc_id, "type": doc_type}),
             "--data", json.dumps({
                 "member_type": "openid",
                 "member_id": LEO_OPEN_ID,
                 "perm": "edit",
                 "type": "user"
             }),
             "--as", "bot"],
            capture_output=True, text=True, timeout=15,
            encoding='utf-8', errors='ignore'
        )
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                return data.get("code", -1) == 0
            except:
                pass
        return False
    except Exception as e:
        print(f"[FeishuOutput] 添加权限失败: {e}")
        return False


def get_or_create_doc(title: str, initial_content: str = "") -> tuple:
    """获取已有文档 ID，或创建新文档"""
    registry = _load_registry()
    if title in registry:
        entry = registry[title]
        return entry.get("doc_id"), entry.get("doc_url")

    content = initial_content or f"# {title}\n\n初始化中..."
    result = subprocess.run(
        [LARK_CLI, "docs", "+create", "--title", title, "--markdown", "-", "--as", "bot"],
        input=content, capture_output=True, text=True, timeout=30, encoding='utf-8'
    )

    doc_id = _extract_doc_id(result.stdout)
    doc_url = _extract_doc_url(result.stdout)

    if doc_id:
        _add_edit_permission(doc_id, "docx")
        registry[title] = {"doc_id": doc_id, "doc_url": doc_url}
        _save_registry(registry)

    return doc_id, doc_url


def update_doc(title: str, content: str) -> Optional[str]:
    """更新飞书云文档内容"""
    doc_id, doc_url = get_or_create_doc(title)
    if not doc_id:
        doc_id, doc_url = get_or_create_doc(title, content)
        return doc_url

    result = subprocess.run(
        [LARK_CLI, "docs", "+update", "--doc", doc_id, "--markdown", "-", "--as", "bot"],
        input=content, capture_output=True, text=True, timeout=30, encoding='utf-8'
    )
    return doc_url


def create_doc(title: str, content: str) -> Optional[str]:
    """创建新的飞书云文档（不重用）"""
    result = subprocess.run(
        [LARK_CLI, "docs", "+create", "--title", title, "--markdown", "-", "--as", "bot"],
        input=content, capture_output=True, text=True, timeout=30, encoding='utf-8'
    )
    doc_id = _extract_doc_id(result.stdout)
    doc_url = _extract_doc_url(result.stdout)
    if doc_id:
        _add_edit_permission(doc_id, "docx")
    return doc_url


def notify_with_doc(reply_target: str, send_reply, title: str, content: str, short_msg: str = "") -> Optional[str]:
    """发飞书消息 + 同步创建/更新云文档"""
    doc_url = update_doc(title, content)
    msg = short_msg or f"📄 {title}"
    if doc_url:
        msg += f"\n🔗 {doc_url}"
    send_reply(reply_target, msg)
    return doc_url


def get_or_create_bitable(name: str) -> Optional[str]:
    """获取或创建多维表格"""
    registry = _load_registry()
    key = f"bitable:{name}"
    if key in registry:
        return registry[key].get("app_token")

    result = subprocess.run(
        [LARK_CLI, "bitable", "+create", "--name", name, "--as", "bot"],
        capture_output=True, text=True, timeout=30, encoding='utf-8', errors='ignore'
    )
    try:
        data = json.loads(result.stdout)
        app_token = data.get("data", {}).get("app", {}).get("app_token")
        if app_token:
            _add_edit_permission(app_token, "bitable")
            registry[key] = {"app_token": app_token}
            _save_registry(registry)
        return app_token
    except:
        return None


def add_bitable_record(app_token: str, table_id: str, record: dict) -> bool:
    """向多维表格添加记录"""
    result = subprocess.run(
        [LARK_CLI, "bitable", "+records-create",
         "--app-token", app_token, "--table-id", table_id,
         "--record", json.dumps(record, ensure_ascii=False), "--as", "bot"],
        capture_output=True, text=True, timeout=15, encoding='utf-8', errors='ignore'
    )
    try:
        data = json.loads(result.stdout)
        return data.get("ok", False)
    except:
        return False


__all__ = [
    "get_or_create_doc", "update_doc", "create_doc", "notify_with_doc",
    "get_or_create_bitable", "add_bitable_record",
]
```

---

## 4. scripts/roundtable/roundtable.py discuss() 方法（148-309行）

```python
async def discuss(self, task: TaskSpec, context: CrystalContext) -> RoundtableResult:
    """圆桌讨论主流程（v2: 收敛分层）

    两层迭代：
    - 方案层：最多 3 轮，Critic 只审查方案是否覆盖验收标准、约束是否矛盾
    - 代码层：Generator + Verifier 闭环，不回方案讨论

    震荡检测：如果 P0 数量连续 3 轮不下降，锁定基线
    """
    iteration = 0
    max_iterations = task.max_iterations
    convergence_trace: List[int] = []  # v2: P0 数量追踪（震荡检测）
    baseline_proposal: Optional[str] = None  # v2: 震荡时锁定的基线方案

    # v2: 创建快照目录（roundtable_runs/{topic}_{timestamp}/）
    runs_dir = Path("roundtable_runs")
    runs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = "".join(c for c in task.topic[:20] if c.isalnum() or c in "_-").strip()
    self.current_run_dir = runs_dir / f"{safe_topic}_{timestamp}"
    self.current_run_dir.mkdir(parents=True, exist_ok=True)

    # 保留旧日志目录（兼容）
    self.current_log_dir = self.log_dir / f"{safe_topic}_{timestamp}"
    self.current_log_dir.mkdir(parents=True, exist_ok=True)

    # v2: 保存输入 TaskSpec
    self._save_snapshot("input_task_spec.json", task.to_dict())

    # Phase 1: 独立思考
    phase1_outputs = await self._phase_1_independent(task, context)
    self._log_phase_outputs("phase1", phase1_outputs)

    # v2: 保存 crystal context summary
    if context:
        self._save_snapshot("crystal_context_summary.md", str(context.role_slices)[:5000])

    # === 元认知层：Phase 1 后盲点检测 ===
    if self.meta and META_COGNITION_ENABLED:
        blind_spot = await self.meta.check_blind_spots("Phase 1: 独立思考", phase1_outputs)
        if blind_spot:
            context.meta_injection = f"[元认知提醒] {blind_spot}"
            if self.feishu:
                self.feishu.notify(f"🧠 元认知层发现盲点：{blind_spot[:80]}...")

    # ======== 方案层（最多 MAX_PROPOSAL_ROUNDS 轮）========
    proposal_iteration = 0
    proposal = ""
    phase3_outputs = {}
    prev_critic_result: Optional[CriticResult] = None  # v2: 用于因果链标注

    while proposal_iteration < MAX_PROPOSAL_ROUNDS:
        proposal_iteration += 1
        iteration += 1
        if self.feishu:
            self.feishu.notify(f"🔵 方案层第 {proposal_iteration} 轮")

        # Phase 2: 方案生成
        proposer_prompt_extra = ""
        # v2: 震荡检测 - 如果 P0 数量不下降，锁定基线
        if baseline_proposal and len(convergence_trace) >= OSCILLATION_THRESHOLD:
            if convergence_trace[-1] >= convergence_trace[-OSCILLATION_THRESHOLD]:
                proposer_prompt_extra = "\n⚠️ 修复震荡。方案已锁定为基线。只改 P0 段落，不重写其他部分。"

        proposal = await self._phase_2_propose(task, context, phase1_outputs, proposer_prompt_extra, baseline_proposal)
        self._log_phase("phase2_proposal", task.proposer, proposal)

        # === 元认知层：Phase 2 后方向检查 ===
        if self.meta and META_COGNITION_ENABLED:
            direction_check = await self.meta.check_blind_spots("Phase 2: 方案生成", {"proposal": proposal})
            if direction_check:
                context.meta_injection = f"[元认知提醒] {direction_check}"
                if self.feishu:
                    self.feishu.notify(f"🧠 元认知层提醒：{direction_check[:80]}...")

        # Phase 3: 定向审查
        phase3_outputs = await self._phase_3_review(task, phase1_outputs, proposal)
        self._log_phase_outputs("phase3", phase3_outputs)

        # 碰撞检测
        had_collision = await self._check_collision_quality(phase1_outputs, phase3_outputs)

        # Phase 4: Critic 终审（方案层专用 prompt）
        critic_result = await self._phase_4_critic_proposal(task, proposal, phase3_outputs, had_collision)
        self._log_phase("phase4_critic_proposal", "Critic", critic_result)

        # v2: 记录 P0 数量（震荡检测）
        p0_count = len(critic_result.p0_issues)
        convergence_trace.append(p0_count)
        self._log_phase("convergence_trace", "System", f"Round {proposal_iteration}: P0={p0_count}")

        # v2: 保存最终 Critic 结果
        self._save_snapshot("phase4_critic_final.md",
            f"# Critic Result\n\n## P0 Issues ({len(critic_result.p0_issues)})\n" +
            "\n".join(f"- {issue}" for issue in critic_result.p0_issues) +
            f"\n\n## P1 Issues ({len(critic_result.p1_issues)})\n" +
            "\n".join(f"- {issue}" for issue in critic_result.p1_issues) +
            f"\n\n## Passed: {critic_result.passed}")

        # 收敛判断（方案层）
        if critic_result.passed and not critic_result.p0_issues:
            # 方案层通过，进入代码层
            if self.feishu:
                self.feishu.notify(f"✅ 方案层收敛（{proposal_iteration} 轮），进入代码生成")
            break

        # v2: 震荡检测 - 连续 OSCILLATION_THRESHOLD 轮不下降
        if len(convergence_trace) >= OSCILLATION_THRESHOLD:
            recent = convergence_trace[-OSCILLATION_THRESHOLD:]
            if all(x >= convergence_trace[-OSCILLATION_THRESHOLD] for x in recent):
                if self.feishu:
                    self.feishu.notify(f"⚠️ 检测到震荡（P0 不下降），锁定基线方案")
                baseline_proposal = proposal
                # 强制进入代码层，由 Generator + Verifier 处理
                break

        # v2: 新增 - P0 反弹检测（比上一轮增加）
        if len(convergence_trace) >= 2:
            if convergence_trace[-1] > convergence_trace[-2]:
                if self.feishu:
                    self.feishu.notify(f"⚠️ P0 反弹 ({convergence_trace[-2]} → {convergence_trace[-1]})，锁定基线")
                baseline_proposal = proposal
                break

        # 有 P0 问题，迭代修复
        if critic_result.p0_issues:
            if self.feishu:
                self.feishu.notify(f"🔄 方案层发现 {len(critic_result.p0_issues)} 个 P0 问题，迭代修复")

            # 将 P0 问题反馈给 proposer，修改方案
            feedback = self._build_p0_feedback(critic_result, phase3_outputs, prev_critic_result)
            prev_critic_result = critic_result
            phase1_outputs = await self._phase_1_rethink(task, context, feedback, phase1_outputs)
            continue

    # ======== 代码层（Generator + Verifier 闭环）========
    # 生成执行摘要
    exec_summary = await self._generate_executive_summary(proposal, phase3_outputs, phase1_outputs)

    # 构建圆桌结果（传递给 Generator）
    result = RoundtableResult(
        final_proposal=proposal,
        executive_summary=exec_summary,
        all_constraints=self._collect_constraints(phase1_outputs),
        confidence_map=self._build_confidence_map(phase1_outputs, phase3_outputs),
        full_log_path=str(self.current_log_dir),
        rounds=iteration,
        reviewer_amendments=self._collect_reviewer_amendments(phase3_outputs),
    )

    # v2: 保存快照
    self._save_snapshot("phase2_proposal_full.md", proposal)
    self._save_convergence_trace(convergence_trace)
    self._save_snapshot("generator_input_actual.md",
        f"# Generator Input\n\n## Final Proposal\n{proposal[:3000]}\n\n## Reviewer Amendments\n{result.reviewer_amendments[:1000] if result.reviewer_amendments else 'None'}")

    # 保存元认知日志
    if self.meta and META_COGNITION_ENABLED:
        self.meta.finalize_logs(task.topic)

    return result
```

---

## 5. scripts/auto_learn.py _find_kb_gaps() 函数

```python
def _find_kb_gaps() -> list:
    """分析知识库缺口，返回需要补充的搜索词列表

    策略:
    1. 优先从决策树的 blocking_knowledge 获取缺口
    2. 从 research_task_pool.yaml 获取未完成任务
    3. 域分布不均
    4. 时效性（超过 30 天）
    5. 产品锚点覆盖
    """
    gaps = []

    # 0. 优先: 从决策树获取阻塞知识缺口
    dt_path = Path(__file__).parent.parent / ".ai-state" / "product_decision_tree.yaml"
    if dt_path.exists():
        try:
            import yaml as _yaml
            dt = _yaml.safe_load(dt_path.read_text(encoding='utf-8'))
            for d in dt.get("decisions", []):
                if d.get("status") != "open":
                    continue
                resolved_texts = [r.get("knowledge", "") for r in d.get("resolved_knowledge", [])]
                for bk in d.get("blocking_knowledge", []):
                    already = any(bk[:20].lower() in rt.lower() for rt in resolved_texts)
                    if not already:
                        deadline = d.get("deadline", "")
                        base_priority = d.get("priority", 2)
                        weighted_priority = _calculate_time_weighted_priority(base_priority, deadline)
                        gaps.append({
                            "type": "decision_blocking",
                            "domain": "components",
                            "query": bk,
                            "priority": weighted_priority,
                            "decision_id": d.get("id", ""),
                        })
        except Exception as e:
            print(f"[AutoLearn] 决策树读取失败: {e}")

    # 0.5 从 research_task_pool.yaml 获取未完成任务
    rtp_path = Path(__file__).parent.parent / ".ai-state" / "research_task_pool.yaml"
    if rtp_path.exists():
        try:
            import yaml as _yaml
            tasks = _yaml.safe_load(rtp_path.read_text(encoding='utf-8'))
            if tasks:
                for task in tasks:
                    if task.get("completed"):
                        continue
                    searches = task.get("searches", [])
                    if searches:
                        for search in searches[:1]:
                            gaps.append({
                                "type": "research_pool",
                                "domain": "components",
                                "query": search,
                                "priority": task.get("priority", 2),
                                "task_id": task.get("id", ""),
                            })
        except Exception as e:
            print(f"[AutoLearn] research_task_pool 读取失败: {e}")

    # 1. 域分布
    stats = get_knowledge_stats()
    if stats:
        values = list(stats.values()) if isinstance(stats, dict) else []
        if values:
            min_val = min(values)
            max_val = max(values)
            if max_val > 0 and min_val < max_val * 0.3:
                if isinstance(stats, dict):
                    min_domain = min(stats, key=stats.get)
                    gaps.append({
                        "type": "domain_gap",
                        "domain": min_domain,
                        "query": f"智能骑行头盔 {min_domain} 最新技术 供应商 2026",
                        "priority": 1
                    })

    # 2. 时效性（超过 30 天）
    stale_domains = set()
    cutoff = datetime.now() - timedelta(days=30)
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            created = data.get("created_at", "")
            if created:
                try:
                    if datetime.fromisoformat(created) < cutoff:
                        domain = data.get("domain", "general")
                        stale_domains.add(domain)
                except:
                    pass
        except:
            continue

    for domain in list(stale_domains)[:2]:
        gaps.append({
            "type": "stale",
            "domain": domain,
            "query": f"{domain} motorcycle helmet latest update 2026",
            "priority": 2
        })

    # 3. 产品锚点覆盖
    anchor_keywords = [
        "HUD", "光波导", "waveguide", "OLED", "Micro LED",
        "mesh intercom", "Cardo", "骨传导", "ANC",
        "Qualcomm AR1", "主SoC", "胎压", "TPMS",
        "DOT", "ECE", "SNELL", "安全认证",
        "lark-cli", "飞书 CLI",
    ]
    for kw in anchor_keywords:
        count = 0
        for f in KB_ROOT.rglob("*.json"):
            try:
                content = f.read_text(encoding="utf-8")
                if kw.lower() in content.lower():
                    count += 1
            except:
                continue
        if count < 3:
            gaps.append({
                "type": "anchor_gap",
                "keyword": kw,
                "query": f"{kw} motorcycle helmet specs supplier price 2026",
                "priority": 1
            })

    # 按优先级排序
    gaps.sort(key=lambda x: x["priority"])

    # 过滤已覆盖的搜索词
    covered = _load_covered_topics()
    filtered_gaps = []
    for gap in gaps[:20]:
        query = gap["query"]
        if query in covered:
            continue
        filtered_gaps.append(gap)

    return filtered_gaps[:8]
```