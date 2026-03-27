# Claude Code 权限与自动化治理方案

## 问题诊断

### 当前问题
1. **任务后评审未自动触发** - 依赖手动调用，必然遗漏
2. **Hook机制未配置** - 规则在文档中，但没有强制执行
3. **权限边界模糊** - Claude应该在什么情况下主动评审？

### 根本原因
- Claude Code的Hook系统需要手动配置到`settings.json`
- 文档中的规则对Claude是"建议"而非"强制约束"
- 没有技术手段阻止违反规则的行为

---

## 解决方案

### 方案1: Hook自动化层 (推荐)

在`settings.json`中配置以下Hooks：

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": {
          "toolName": "Write|Edit"
        },
        "hooks": [
          {
            "type": "command",
            "command": "python scripts/hooks/post_write_hook.py --file ${file_path}"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python scripts/hooks/session_end_hook.py"
          }
        ]
      }
    ]
  }
}
```

**PostToolUse Hook职责：**
- 文件写入后检查是否为关键文件
- 触发质量检查(`quality_check.py`)
- 标记需要评审的变更

**Stop Hook职责：**
- 会话结束前强制评审
- 生成检查点
- 归档会话状态

### 方案2: 规则强化层

更新CLAUDE.md，添加**强制指令**：

```markdown
## 🚨 强制执行规则 (Claude MUST obey)

### 任务完成检查清单
每次完成任务后，Claude MUST执行：

1. [ ] 调用 `python scripts/post_task_review.py`
2. [ ] 等待评审结果
3. [ ] 如果BLOCK，必须修复后再继续
4. [ ] 记录评审结果到 `.ai-state/review_logs.jsonl`

### 文件写入检查清单
每次Write/Edit工具调用后，Claude MUST：

1. [ ] 检查文件是否在核心代码清单中
2. [ ] 如果是，运行 `python scripts/hooks/quality_check.py --file <path>`
3. [ ] 如果质量检查失败，立即修复

### 会话结束检查清单
每次会话结束前，Claude MUST：

1. [ ] 创建检查点 `from src.tools.session_manager import checkpoint`
2. [ ] 生成会话摘要
3. [ ] 归档重要信息到长期记忆
```

### 方案3: 权限边界明确定义

```yaml
# .ai-architecture/claude_permissions.yaml

claude_permissions:
  # 必须执行的（不可跳过）
  mandatory:
    - task_post_review        # 任务后评审
    - quality_check_on_write  # 写入后质量检查
    - checkpoint_on_stop      # 停止时检查点
    - security_scan_on_read   # 读取时安全扫描

  # 需要确认的（AskUserQuestion）
  confirmation_required:
    - git_push               # 推送代码
    - file_delete            # 删除文件
    - config_change          # 修改配置
    - external_api_call      # 调用外部API

  # 禁止的（硬性阻止）
  prohibited:
    - eval_exec_usage        # 使用eval/exec
    - hardcoded_secrets      # 硬编码密钥
    - bypass_hooks           # 绕过Hook
    - skip_review            # 跳过评审

  # 自动执行的（无需确认）
  auto_allowed:
    - read_project_files     # 读取项目文件
    - run_tests              # 运行测试
    - quality_check          # 质量检查
    - create_checkpoint      # 创建检查点
```

---

## 实施计划

### Phase 1: Hook脚本创建 (立即)
- [ ] `scripts/hooks/post_write_hook.py` - 写入后检查
- [ ] `scripts/hooks/session_end_hook.py` - 会话结束处理
- [ ] `scripts/hooks/pre_commit_hook.py` - 提交前检查

### Phase 2: Settings.json配置
- [ ] 配置PostToolUse Hook
- [ ] 配置Stop Hook
- [ ] 测试Hook触发

### Phase 3: 规则文档更新
- [ ] 更新CLAUDE.md添加强制规则
- [ ] 创建`.ai-architecture/claude_permissions.yaml`
- [ ] 更新`.ai-architecture/RULES.md`

### Phase 4: 持续监控
- [ ] Hook执行日志记录
- [ ] 违规行为告警
- [ ] 定期审计

---

## 当前缺失的Hook脚本

需要立即创建：

1. **post_write_hook.py** - 检测关键文件写入，触发质量检查
2. **session_end_hook.py** - 强制评审+检查点
3. **auto_checkpoint_hook.py** - 定期自动检查点

---

*本文档由 Claude 生成，待用户审批后执行*
*创建时间: 2026-03-17*