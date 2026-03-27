# 上下文压缩 Hook 架构文档

> **版本**: 1.0
> **创建时间**: 2026-03-17
> **用途**: 定义 PreCompact/PostCompact Hook 的架构设计、安全策略和降级机制

---

## 一、设计目标

1. **上下文连续性**: 在 Claude Code 自动压缩上下文时，保存关键信息
2. **安全存储**: 检查点文件的安全存储和访问控制
3. **优雅降级**: 即使分层记忆不可用，也能提供基本的上下文保护
4. **回滚机制**: 创建失败时自动清理部分状态

---

## 二、架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                     Claude Code Session                               │
└─────────────────────────────┬────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     Auto-Compact 触发                                 │
└─────────────────────────────┬────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│    PreCompact Hook      │     │    (Compact 执行)       │
│  ┌─────────────────┐   │     └─────────────────────────┘
│  │ 1. 创建检查点    │   │                  │
│  │ 2. 提升重要记忆  │   │                  │
│  │ 3. 生成恢复上下文│   │                  ▼
│  └─────────────────┘   │     ┌─────────────────────────┐
└─────────────────────────┘     │    PostCompact Hook     │
              │                  │  ┌─────────────────┐   │
              │                  │  │ 1. 加载恢复上下文│   │
              ▼                  │  │ 2. 恢复检查点    │   │
┌─────────────────────────┐     │  │ 3. 注入到会话    │   │
│ .ai-state/              │     │  └─────────────────┘   │
│ ├── compact_recovery.md │     └─────────────────────────┘
│ └── layered_memory/     │                  │
│     ├── checkpoints/    │                  ▼
│     └── longterm/       │     ┌─────────────────────────┐
└─────────────────────────┘     │   会话继续（上下文恢复）│
                                └─────────────────────────┘
```

---

## 三、安全设计

### 3.1 文件存储安全

| 项目 | 策略 | 原因 |
|------|------|------|
| 存储位置 | `.ai-state/` 目录 | 项目内部，不暴露到外部 |
| Git 忽略 | 必须加入 `.gitignore` | 防止敏感信息提交 |
| 文件权限 | 0o600 (仅所有者可读写) | 防止其他用户访问 |
| 目录权限 | 0o700 (仅所有者可访问) | 保护整个目录树 |

### 3.2 路径安全

```python
# 安全常量 - 所有路径相对于项目根目录
AI_STATE_DIR = Path(".ai-state")
CHECKPOINT_DIR = AI_STATE_DIR / "layered_memory" / "checkpoints"
RECOVERY_FILE = AI_STATE_DIR / "compact_recovery_context.md"

# 禁止使用用户提供的路径
# Hook 不使用 data.get("file_path") 等外部输入作为文件路径
```

### 3.3 原子写入

```python
def _write_secure_file(path: Path, content: str) -> bool:
    """
    安全写入文件，确保原子性

    流程:
    1. 写入临时文件 (.tmp)
    2. 原子性重命名到目标文件
    3. 设置文件权限
    """
    temp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(content)
        temp_path.replace(path)  # 原子操作
        return True
    except Exception:
        if temp_path.exists():
            temp_path.unlink()  # 清理临时文件
        return False
```

---

## 四、回滚机制

### 4.1 部分状态清理

当检查点创建过程中发生错误时，自动清理已创建的文件和目录：

```python
def _cleanup_partial_state(files: List[Path], dirs: List[Path] = None) -> None:
    """
    回滚清理部分状态

    清理顺序:
    1. 先清理文件
    2. 再清理空目录（从最深层开始）
    """
    for f in files:
        if f.exists():
            f.unlink()

    if dirs:
        for d in reversed(dirs):  # 从最深层开始
            if d.exists() and d.is_dir() and not list(d.iterdir()):
                d.rmdir()
```

### 4.2 降级策略

```
┌────────────────────────────────────────────────────────────────────┐
│                     降级矩阵                                        │
├─────────────────────────┬──────────────────────────────────────────┤
│ 场景                     │ 降级行为                                 │
├─────────────────────────┼──────────────────────────────────────────┤
│ LayeredMemory 不可用     │ 使用基本 JSON 文件存储                   │
│ 检查点创建失败           │ 跳过检查点，仅保存恢复上下文             │
│ 文件写入失败             │ 记录错误，继续执行（不阻断压缩）         │
│ 检查点恢复失败           │ 提示用户，但允许会话继续                 │
└─────────────────────────┴──────────────────────────────────────────┘
```

---

## 五、Hook 输入/输出规范

### 5.1 PreCompact 输入

```json
{
  "session_id": "abc123",
  "hook_event_name": "PreCompact",
  "trigger": "auto"
}
```

### 5.2 PreCompact 输出

```json
{
  "systemMessage": "[Pre-Compact] 已创建检查点 ckpt_xxx，关键上下文已保存。",
  "continue": true,
  "hookSpecificOutput": {
    "hookEventName": "PreCompact",
    "additionalContext": "\n[上下文压缩提示]..."
  }
}
```

### 5.3 PostCompact 输入

```json
{
  "session_id": "abc123",
  "hook_event_name": "PostCompact",
  "compact_summary": "..."
}
```

### 5.4 PostCompact 输出

```json
{
  "systemMessage": "[Post-Compact] 上下文压缩完成。✅ 上下文已注入 | ✅ 检查点已恢复",
  "continue": true,
  "hookSpecificOutput": {
    "hookEventName": "PostCompact",
    "additionalContext": "\n## [上下文恢复 - 压缩后自动注入]\n..."
  }
}
```

---

## 六、配置

### 6.1 settings.json 配置

```json
{
  "hooks": {
    "PreCompact": [
      {
        "matcher": "auto",
        "hooks": [
          {
            "type": "command",
            "command": "python scripts/hooks/compact_hook.py"
          }
        ]
      },
      {
        "matcher": "manual",
        "hooks": [
          {
            "type": "command",
            "command": "python scripts/hooks/compact_hook.py"
          }
        ]
      }
    ],
    "PostCompact": [
      {
        "matcher": "auto",
        "hooks": [
          {
            "type": "command",
            "command": "python scripts/hooks/compact_hook.py"
          }
        ]
      },
      {
        "matcher": "manual",
        "hooks": [
          {
            "type": "command",
            "command": "python scripts/hooks/compact_hook.py"
          }
        ]
      }
    ]
  }
}
```

### 6.2 .gitignore 配置

```gitignore
# AI State - 敏感会话数据
.ai-state/
```

---

## 七、测试覆盖

### 7.1 单元测试

| 测试类 | 测试内容 |
|--------|----------|
| TestCompactHookPreCompact | PreCompact 事件处理 |
| TestCompactHookPostCompact | PostCompact 事件处理 |
| TestCompactHookSecurity | 路径遍历攻击防护、JSON 注入防护 |
| TestCompactHookIntegration | 完整压缩周期测试 |
| TestCompactHookRollback | 回滚机制测试 |

### 7.2 测试命令

```bash
# 运行所有测试
pytest tests/test_compact_hook.py -v

# 运行安全测试
pytest tests/test_compact_hook.py::TestCompactHookSecurity -v

# 运行集成测试
pytest tests/test_compact_hook.py::TestCompactHookIntegration -v
```

---

## 八、故障排查

### 8.1 常见问题

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| Hook 未执行 | settings.json 配置错误 | 检查 JSON 语法 |
| 检查点创建失败 | 磁盘空间不足 | 清理 .ai-state/ |
| 权限错误 | 文件权限不正确 | 检查 .ai-state/ 权限 |
| 上下文未恢复 | 恢复文件不存在 | 检查 PreCompact 是否成功 |

### 8.2 日志位置

```
.ai-state/hooks/compact_hook_log.jsonl  # Hook 执行日志
.ai-state/session_archive.json           # 会话归档
```

---

## 九、版本历史

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| 1.0 | 2026-03-17 | 初始版本：安全存储、回滚机制、降级策略 |

---

*文档版本: 1.0*
*最后更新: 2026-03-17*