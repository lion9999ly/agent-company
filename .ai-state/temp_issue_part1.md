# Day 17 系统全量审计 - Part 1: 消息处理全链路

## A. 消息处理全链路

### 1. scripts/feishu_sdk_client_v2.py 完整内容

**核心要点：**
- USE_AGENT_MODE 环境变量控制新旧路由
- Agent 模式：飞书消息 → agent.py → 快速通道 / Claude Code CLI
- 旧路由：飞书消息 → text_router.py → 各 handler 模块

### 2. scripts/agent.py 完整内容

**核心要点：**
- 快速通道处理器：状态、监控范围、帮助、自检、圆桌、拉取指令、深度学习、自学习、KB治理、日志
- Claude Code CLI 调用：清除 Z.AI 环境变量，确保调用真正的 Claude Code CLI
- 独立轮询模式：--standalone 参数

### 3. scripts/feishu_handlers/text_router.py 完整内容

**路由优先级：**
1. 精确指令（commands.py）
2. Handler 模块（learning/roundtable/import/smart_chat）
3. 结构化文档快速通道
4. 智能对话兜底

**已知问题：**
- 文件约 2292 行，待拆分

### 4. scripts/feishu_handlers/roundtable_handler.py 完整内容

**流程：**
- 接收 `圆桌:xxx` 指令
- 加载 TaskSpec
- 后台执行圆桌任务
- 生成飞书云文档摘要

### 5. scripts/feishu_handlers/learning_handlers.py 完整内容

**支持的指令：**
- 深度学习、自学习、KB治理、早报、滴灌、KB统计

### 6. scripts/feishu_handlers/import_handlers.py 完整内容

**支持的指令：**
- 导入文档、参考文件、拉取指令、关注主题、URL分享、长文章导入

### 7. scripts/feishu_handlers/smart_chat.py 完整内容

**功能：**
- 教练模式
- 研发任务检测
- 意图智能路由
- 回答反馈处理

### 8. scripts/feishu_handlers/chat_helpers.py 完整内容

**核心功能：**
- send_reply（支持长消息分块）
- get_tenant_access_token
- 日志记录
- 回复上下文管理

### 9. scripts/feishu_output.py 完整内容

**核心功能：**
- get_or_create_doc / update_doc / create_doc
- notify_with_doc
- get_or_create_bitable / add_bitable_record

### 10. grep -rn "USE_AGENT_MODE" --include="*.py" 全部结果

```
scripts/feishu_sdk_client_v2.py:49:USE_AGENT_MODE = os.getenv("USE_AGENT_MODE", "true").lower() == "true"
scripts/feishu_sdk_client_v2.py:128:            print(f"  [DEBUG] USE_AGENT_MODE={USE_AGENT_MODE}")
scripts/feishu_sdk_client_v2.py:129:            if USE_AGENT_MODE:
scripts/feishu_sdk_client_v2.py:151:                print(f"  [旧路由器] USE_AGENT_MODE=False")
```

---

**续接 Part 2/3**