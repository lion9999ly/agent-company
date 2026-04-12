---
name: feishu-output
description: Use when sending messages, documents, or reports to Feishu, determining output format (message vs document vs bitable), and handling reply routing
metadata:
  author: leo
  version: "1.0"
---

# Feishu Output Skill

## Overview

飞书输出规范定义了消息路由、文档创建、多维表格写入的标准流程。核心原则是短回复直接发消息，长内容创建云文档。

**核心原则：短消息直接发，长内容云端文档。**

## When to Use

- 需要向飞书发送回复或通知
- 需要创建/更新飞书云文档
- 需要将结构化数据写入多维表格
- 需要处理飞书指令路由

**When NOT to Use:**
- 非飞书通道的消息发送
- 本地文件操作

## Output Format Decision

| 内容类型 | 输出方式 | 命令 |
|----------|----------|------|
| 短文本（<500 字） | 直接发消息 | `lark-cli im +messages-send` |
| 长内容（报告/代码） | 云文档 + 链接 | `lark-cli docs +create` |
| 结构化数据 | 多维表格 | `lark-cli bitable +records-create` |

## Reply Routing

```python
# text_router.py 主路由
route_text_message(text, reply_target, reply_type, open_id, chat_id, send_reply)

# 路由优先级
1. 精确指令（commands.py）
2. Handler 模块（learning/roundtable/import）
3. 结构化文档快速通道
4. 智能对话兜底（smart_chat）
```

## Key Handlers

| Handler | 用途 | 触发词 |
|---------|------|--------|
| commands.py | 精确指令 | "帮助", "状态", "早报" |
| learning_handlers.py | 学习任务 | "深度学习", "自学习", "KB治理" |
| roundtable_handler.py | 圆桌任务 | "/roundtable", "圆桌" |
| import_handlers.py | 文档导入 | "导入", "拉取" |
| smart_chat.py | 智能对话 | 其他文本 |

## Lark-CLI Commands

```bash
# 发消息
lark-cli im +messages-send --chat-id {chat_id} --text "内容" --as bot

# 创建云文档
lark-cli docs +create --title "标题" --markdown "内容" --as bot

# 更新云文档
lark-cli docs +update --document-id {doc_id} --markdown "内容" --as bot

# 读取消息
lark-cli im +chat-messages-list --chat-id {chat_id} --page-size 5 --as bot

# 多维表格写入
lark-cli bitable +records-create --app-token {token} --table-id {id} --fields '{"字段":"值"}' --as bot
```

## Known Pitfalls

| 陷阱 | 规避方法 |
|------|----------|
| 消息过长被截断 | >500 字创建云文档 |
| 文档链接无效 | 返回 URL 后用 notify_with_doc |
| Handler 漏处理 | 主路由最后有智能对话兜底 |
| 指令触发失败 | 检查精确匹配 vs 模糊匹配 |

## Report Output Rules

完成圆桌/诊断/修复报告后**必须**：
1. 创建 GitHub Issue（claude_chat_inbox 可访问）
2. 追加写入 `.ai-state/claude_chat_inbox.md`
3. `git add && git commit && git push`

```python
# GitHub Issue 创建
requests.post(
    "https://api.github.com/repos/lion9999ly/agent-company/issues",
    headers={"Authorization": f"token {GITHUB_TOKEN}"},
    json={"title": "[圆桌] XXX", "body": report, "labels": ["roundtable"]}
)
```

## Verification Criteria

- [ ] 消息/文档成功发送
- [ ] 格式选择正确（短消息 vs 长文档）
- [ ] GitHub Issue 已创建（报告类）
- [ ] claude_chat_inbox.md 已更新

## Key Files

```
scripts/feishu_handlers/text_router.py        # 主路由
scripts/feishu_handlers/commands.py           # 精确指令
scripts/feishu_handlers/learning_handlers.py  # 学习任务
scripts/feishu_handlers/roundtable_handler.py # 圆桌任务
scripts/feishu_handlers/import_handlers.py    # 文档导入
scripts/feishu_handlers/smart_chat.py         # 智能对话
scripts/feishu_output.py                      # 统一输出工具
.ai-state/claude_chat_inbox.md                # Claude Chat 通知池
```

## Quick Reference

```python
# 统一输出工具
from scripts.feishu_output import update_doc, create_doc, notify_with_doc

# 更新云文档
doc_url = update_doc("标题", "markdown内容")

# 发消息 + 云文档
notify_with_doc(reply_target, send_reply, "标题", "内容", "短消息")
```