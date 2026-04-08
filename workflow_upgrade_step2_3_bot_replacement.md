# CC 指令：工作流升级 Step 2+3 — 飞书 CLI 替代自写 bot + SDK 退役

> **前提**：Step 1 已完成（CLI 输出层可用）
> **备份**：`git tag backup-before-lark-cli-step2`

---

## Step 2：飞书 CLI 替代自写 bot 消息处理（7 项）

### 总览

当前架构：feishu_sdk_client_v2.py（WebSocket 长连接）→ text_router.py → handler 模块 → 执行 → SDK send_reply 回复

目标架构：参考 lark-bot-agent 方案：飞书长连接 → Claude Code CLI 理解并执行 → 飞书 CLI 回复

| # | 改动 | 说明 |
|---|------|------|
| 1 | 部署 lark-bot-agent 架构 | 飞书消息 → Claude Code CLI |
| 2 | 保留精确指令快速通道 | 圆桌/状态/监控等不走 LLM |
| 3 | CLAUDE.md 注入飞书操作能力 | CC 知道自己能操作飞书 |
| 4 | 迁移 text_router 核心逻辑 | handler 模块作为 Claude Code 的 skill |
| 5 | 定时任务迁移 | scheduler 独立于 bot 进程 |
| 6 | 用户评判流程适配 | 圆桌完成后的评价识别 |
| 7 | 端到端验证 | 全路由冒烟测试 |

---

### #1 部署 lark-bot-agent 架构

核心思路：飞书消息进来后，不再走 text_router 的 if/elif 路由，而是把消息文本直接传给 Claude Code CLI，让 CC 自己判断该做什么。

```python
# agent.py（参考 lark-bot-agent，适配到现有项目）

import subprocess
import json

def handle_message(message_text: str, chat_id: str, open_id: str):
    """收到飞书消息后的处理"""
    
    # 1. 精确指令快速通道（不走 LLM，直接执行）
    fast_result = try_fast_commands(message_text, chat_id)
    if fast_result:
        return
    
    # 2. 所有其他消息 → Claude Code CLI
    prompt = build_prompt(message_text, chat_id, open_id)
    
    result = subprocess.run(
        ["claude", "-p", prompt, "--no-input"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=300  # 5 分钟超时
    )
    
    if result.returncode == 0 and result.stdout.strip():
        # CC 的回复通过飞书 CLI 发回去
        cli_send_message(result.stdout.strip()[:2000], chat_id)
    else:
        cli_send_message("⚠️ 处理超时或出错，请稍后重试", chat_id)
```

### #2 保留精确指令快速通道

有些指令不需要 LLM 理解，直接执行更快更可靠：

```python
FAST_COMMANDS = {
    "状态": handle_status,
    "系统状态": handle_status,
    "status": handle_status,
    "监控范围": handle_monitor_scope,
    "帮助": handle_help,
    "help": handle_help,
    "自检": handle_self_verify,
    "验证": handle_self_verify,
}

# 前缀匹配
FAST_PREFIXES = {
    "圆桌:": handle_roundtable,
    "圆桌：": handle_roundtable,
    "执行 issue": handle_github_issue,
    "执行issue": handle_github_issue,
    "拉取指令": handle_fetch_instruction,
    "关注 ": handle_add_topic,
    "关注：": handle_add_topic,
}

def try_fast_commands(text: str, chat_id: str) -> bool:
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
    
    return False  # 不是快速指令，走 Claude Code CLI
```

### #3 CLAUDE.md 注入飞书操作能力

在项目 CLAUDE.md 中加入飞书 CLI 的使用说明，让 CC 知道自己能操作飞书：

```markdown
## 飞书操作能力

你可以通过飞书 CLI 直接操作飞书：

### 发消息
lark-cli im +messages-send --chat-id {chat_id} --text "内容" --as bot

### 创建文档
lark-cli docs +create --title "标题" --markdown "内容" --as bot

### 更新文档
lark-cli docs +update --document-id {doc_id} --markdown "内容" --as bot

### 读取消息
lark-cli im +chat-messages-list --chat-id {chat_id} --page-size 5 --as bot

### 多维表格
lark-cli bitable +records-create --app-token {token} --table-id {id} --fields '{"字段":"值"}'

### 使用原则
- 短回复（<500字）直接发消息
- 长内容（报告/代码/分析）创建飞书云文档
- 结构化数据写多维表格
- 操作完成后告知用户结果
```

### #4 迁移 handler 逻辑为 Claude Code skill

现有的 handler 模块（learning_handlers.py、roundtable_handler.py 等）不废弃，而是作为 Claude Code 的 skill 存在。CC 收到消息后，如果识别到是"深度学习"相关指令，它知道应该调用 `scripts/feishu_handlers/learning_handlers.py` 里的函数。

在 CLAUDE.md 中补充：

```markdown
## 飞书指令对应的执行脚本

用户在飞书说 → 你应该执行的操作

"深度学习" / "夜间学习" → from scripts.feishu_handlers.learning_handlers import handle_night_learning
"自学习" → from scripts.feishu_handlers.learning_handlers import handle_auto_learn
"KB治理" → from scripts.feishu_handlers.learning_handlers import handle_kb_governance
"圆桌:XXX" → from scripts.feishu_handlers.roundtable_handler import handle_roundtable
"导入文档" → from scripts.feishu_handlers.import_handlers import handle_import_docs
"拉取指令" / "执行 issue#N" → from scripts.github_instruction_reader import handle_fetch_instruction
```

### #5 定时任务独立

当前定时任务（01:00 深度学习、06:00 竞品监控、07:00 日报）注册在 feishu_sdk 进程里。需要独立出来：

```python
# scripts/scheduler.py — 独立的定时任务调度器

import schedule
import time
from datetime import datetime

def run_scheduler():
    schedule.every().day.at("01:00").do(trigger_deep_learning)
    schedule.every().day.at("06:00").do(trigger_competitor_monitor)
    schedule.every().day.at("07:00").do(trigger_daily_report)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

def trigger_deep_learning():
    """通过 Claude Code CLI 触发深度学习"""
    subprocess.run(
        ["claude", "-p", "执行深度学习任务（7小时窗口）", "--no-input"],
        cwd=PROJECT_ROOT, timeout=3600 * 8
    )

def trigger_competitor_monitor():
    subprocess.run(
        ["claude", "-p", "执行竞品监控并将结果写入飞书多维表格", "--no-input"],
        cwd=PROJECT_ROOT, timeout=1800
    )
```

用 systemd 或 Windows Task Scheduler 部署，独立于飞书 bot 进程。

### #6 用户评判流程适配

圆桌完成后 CC 发飞书通知带文档链接。用户直接在飞书文档评论区写评价。CC 定期（或通过 webhook）读取文档评论并处理：

```python
# 读取文档评论
# lark-cli docs +comments-list --document-id {doc_id} --as bot
# 解析评论内容 → verdict_parser.py 处理
```

或者保留现有方式：用户在飞书聊天里直接回复评价，agent.py 识别这是评判（基于时间窗口和上下文）传给 Claude Code CLI 处理。

### #7 端到端验证

```python
# 验证清单
tests = [
    ("状态", "快速通道", lambda r: "最近变更" in r or "系统状态" in r),
    ("监控范围", "快速通道", lambda r: "直接竞品" in r or "层" in r),
    ("圆桌:hud_demo", "快速通道", lambda r: "圆桌启动" in r),
    ("帮我分析一下当前的竞品格局", "Claude Code CLI", lambda r: len(r) > 100),
    ("你好", "Claude Code CLI", lambda r: len(r) > 0),
]
```

---

## Step 3：feishu_sdk_client_v2.py 退役（3 项）

### 前提

Step 2 验证全部通过，新架构稳定运行 24 小时无异常。

### #1 feishu_sdk_client_v2.py 精简

不删除文件，而是精简为只保留 WebSocket 长连接监听功能：

```python
# feishu_sdk_client_v2.py 精简版
# 只做一件事：监听飞书消息 → 传给 agent.py 处理

class FeishuMinimalListener:
    """最小飞书消息监听器"""
    
    def on_message(self, event):
        """收到消息后传给 agent 处理"""
        message_text = extract_text(event)
        chat_id = extract_chat_id(event)
        open_id = extract_open_id(event)
        
        # 传给 agent.py（新架构入口）
        handle_message(message_text, chat_id, open_id)
```

所有路由逻辑、handler 逻辑、定时任务、心跳管理——全部移除。

### #2 旧文件归档

```
_archive/feishu_sdk_v2_full/
├── feishu_sdk_client_v2_full.py   # 完整备份
├── text_router_full.py             # 拆分前的完整版
└── README.md                       # 说明为什么归档
```

### #3 启动脚本更新

```bash
# start_all.bat 更新
# 旧：python scripts/feishu_sdk_client_v2.py
# 新：
python scripts/agent.py          # 飞书 bot + Claude Code CLI
python scripts/scheduler.py      # 独立定时任务
```

考虑迁移到 systemd（Linux）或 Windows Service：
- 自动重启
- 开机自启
- 日志管理

---

## 执行顺序

```
git tag backup-before-lark-cli-step2

Step 2（可立即执行）：
#1 agent.py 架构 → commit: feat: lark-bot-agent architecture
#2 快速通道保留 → 同上 commit
#3 CLAUDE.md 飞书能力注入 → commit: docs: add lark-cli capabilities to CLAUDE.md
#4 handler → skill 迁移 → commit: refactor: handlers as Claude Code skills
#5 定时任务独立 → commit: refactor: scheduler independent from bot process
#6 评判流程适配 → commit: feat: verdict via doc comments or chat
#7 端到端验证 → 全路由冒烟测试

Step 3（Step 2 验证通过 24h 后执行）：
#1 feishu_sdk 精简 → commit: refactor: feishu_sdk minimal listener only
#2 旧文件归档 → commit: chore: archive legacy feishu handler files
#3 启动脚本更新 → commit: chore: update start scripts for new architecture

每步 commit + push + 飞书通知。
```

---

## 验证清单

```
=== Step 2 ===
✅ agent.py 架构部署
✅ 快速通道全部命中（状态/监控范围/圆桌/拉取指令/帮助）
✅ 自然语言消息走 Claude Code CLI 并正确回复
✅ CLAUDE.md 含飞书操作说明
✅ 定时任务独立运行
✅ 评判流程可用

=== Step 3（24h 后）===
✅ feishu_sdk 精简为最小监听器
✅ 旧文件已归档
✅ 启动脚本已更新
✅ 全路由 24h 无异常
```
