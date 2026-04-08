# GitHub Issue 指令通道

> Claude Chat → CC 的指令传递机制

---

## 机制说明

Claude Chat 无法直接访问 CC（本地文件系统），通过 GitHub Issue 建立指令通道：

1. **Claude Chat 发布指令**：创建 GitHub Issue，标题格式 `[指令] {描述}`
2. **CC 拉取执行**：通过飞书指令 "拉取指令" 扫描所有 open 的 `[指令]` Issue
3. **结果回写**：执行完成后在 Issue 评论中写执行结果，然后 close Issue

---

## 使用方式

### 从 Claude Chat 发指令

在 GitHub 创建 Issue：
- 标题：`[指令] 检查最近一次圆桌的 critic 评审结果`
- 内容：详细指令（可以是代码修改请求、分析任务等）

### 从飞书触发执行

发送飞书消息：
- `拉取指令` - 执行最新的 open Issue
- `执行 issue 2` - 执行指定编号的 Issue

---

## 技术实现

| 组件 | 文件 | 职责 |
|------|------|------|
| GitHub API 调用 | `scripts/github_instruction_reader.py` | fetch/reply/close Issue |
| 飞书路由 | `scripts/agent.py` | 快速通道注册 |
| 执行入口 | `scripts/feishu_handlers/import_handlers.py` | 路由分发 |

---

## 执行流程

```
飞书 "拉取指令"
  → import_handlers.try_handle()
  → github_instruction_reader.handle_fetch_instruction()
  → fetch_latest_instruction() [GitHub API]
  → CC Agent 模式 / GPT-5.4 执行
  → reply_to_issue() [评论结果]
  → close_issue() [关闭 Issue]
  → 飞书回复执行结果
```

---

## Issue 标签（可选）

可使用 `cc-instruction` 标签标记指令 Issue，便于筛选。

---

## 历史记录

指令执行记录保存在 `.ai-state/claude_chat_instructions/`：
- `issue_{number}.md` - 指令原文
- `latest.md` - 最新指令副本

---

*文档版本: 2026-04-08*