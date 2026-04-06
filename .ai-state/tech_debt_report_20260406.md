# 技术债扫描报告

> 扫描时间: 2026-04-06
> 扫描范围: scripts/, src/, .ai-state/tools/
> 总 Python 文件数: 106 (scripts) + ~50 (src) + 20 (tools)

---

## 🔴 高严重度（影响功能正确性）

### 1. 大文件超标（>800行红线）

| 文件 | 行数 | 职责分析 | 建议 |
|------|------|----------|------|
| `scripts/feishu_handlers/structured_doc.py` | **5637** | PRD/清单生成，但体积过大，包含大量硬编码模板和重复逻辑 | 🔴 **必须拆分**：拆出模板定义、Excel导出、JSON解析为独立模块 |
| `scripts/feishu_sdk_client.py` | **3474** | 飞书SDK主入口，职责过多（消息处理+定时任务+各种handler） | 🟡 建议拆分：定时任务独立文件，handlers已拆出但仍有残留 |
| `scripts/feishu_handlers/text_router.py` | **2464** | 文本消息路由，包含所有指令处理逻辑 | 🟡 可接受：职责相对单一，但可拆出各指令handler为独立文件 |

### 2. 废弃文件未清理（占用空间、混淆代码）

| 文件 | 行数 | 问题 | 建议 |
|------|------|------|------|
| `scripts/tonight_deep_research_backup_20260406.py` | 3906 | 备份文件，原实现已迁移到 `scripts/deep_research/` 包 | 🔴 **立即删除** |
| `src/utils/model_gateway_backup_20260406.py` | 1513 | 备份文件，原实现已拆分成 `model_gateway/` 包 | 🔴 **立即删除** |

### 3. 重复函数定义（调用方可能混淆）

| 函数 | 定义位置 | 问题 |
|------|----------|------|
| `send_reply()` | `chat_helpers.py:64` + `feishu_sdk_client.py:3093` | 两处完全相同的实现，调用方不知该用哪个 |

**建议**：删除 `feishu_sdk_client.py` 中的重复定义，统一使用 `chat_helpers.send_reply`

### 4. 测试文件散落（应移入 tests/）

当前状态：
- `scripts/test_*.py`：**12个**测试文件混在业务脚本目录
- 包括：`test_auto_research.py`, `test_doubao.py`, `test_gemini_vision.py` 等

**建议**：移动到 `tests/scripts/` 目录，保持 `scripts/` 只含生产代码

---

## 🟡 中严重度（影响可维护性）

### 5. 配置散落（硬编码模型名）

**核心问题**：模型名称在多处硬编码，而非统一从 `model_registry.yaml` 获取

| 文件 | 硬编码内容 | 影响 |
|------|-----------|------|
| `scripts/deep_research/config.py` | `gpt_5_4`, `gemini_3_1_pro`, 角色映射 | 降级链、角色模型映射散落 |
| `scripts/deep_research/models.py` | `PEER_MODELS`, `FALLBACK_MAP`, 角色模型 | 降级链与 config.py 重复定义 |
| `scripts/auto_fixer.py:122` | `"gpt_5_4"` 直接调用 | 应使用 `get_model_for_task()` |

**建议**：
1. 合并 `config.py` 和 `models.py` 的模型映射为单一源
2. 所有模型调用通过 `get_model_for_task()` 路由
3. 删除代码中的直接模型名硬编码

### 6. 已禁用模型仍被引用

`model_registry.yaml` 中有 **12个** `enabled: false` 的模型：
- gpt-5.3-chat-2026-03-03, claude-opus-4-6, claude-sonnet-4-6
- o3, o3-mini, grok-4-fast-reasoning
- DeepSeek-V3.2, DeepSeek-R1, qwen-3-32b, gemini-3.1-pro-preview 等

**代码中仍有引用**：
- `token_usage_tracker.py`：记录了所有禁用模型的定价（可接受，定价数据无害）
- `test_model_availability.py`：测试脚本引用（可接受）
- `tonight_deep_research_backup_20260406.py`：**备份文件中引用，删除文件即可解决**

### 7. TODO/FIXME 标记（未完成工作）

| 文件 | 行号 | 内容 | 优先级 |
|------|------|------|--------|
| `scripts/claude_thinking_layer.py` | 303-305 | 任务优先级调整、决策记录生成未实现 | 🟡 功能未完成 |
| `src/tools/layered_memory.py` | 41 | `TODO = "todo"` 是枚举值，非标记 | ✅ 无问题 |

**建议**：`claude_thinking_layer.py` 的 TODO 应补充实现或明确放弃

### 8. Shim 文件存在（向后兼容入口）

| 文件 | 职责 | 建议 |
|------|------|------|
| `scripts/tonight_deep_research.py` | 977字节 shim，重导出 `deep_research/` 包接口 | 🟢 可接受：确保旧调用方兼容 |

---

## 🟢 低严重度（代码卫生）

### 9. Bare except Exception 数量

- 总计：**558处** `except Exception` 模式
- 分布：主要在 `feishu_sdk_client.py`（大量容错）、`runner.py`（质量网故意吞异常）

**分析**：
- 大部分是合理的容错设计（飞书消息处理不能因异常中断）
- `_post_learning_quality_check` 的吞异常是**故意设计**（不阻断学习流程）
- `resilience.py` 文档化说明了"不是 try-except-pass，是 try-diagnose-fix-retry"

### 10. 文件结构概览

```
scripts/
├── 94 个业务脚本
├── 12 个测试文件（应移动）
├── archived/  2 个归档文件（overnight_deep_learning v2/v3）
├── deep_research/  包结构（已拆分）
├── roundtable/     包结构（已拆分）
├── feishu_handlers/ 已拆出指令处理
└── tonight_deep_research.py  shim（可接受）

src/
├── config/  配置文件
├── graph/   LangGraph 状态机
├── security/ 安全模块
├── tools/   工具模块
└── utils/model_gateway/  已拆分成包
```

---

## 行动清单

### 立即执行（🔴）

1. **删除备份文件**
   ```bash
   rm scripts/tonight_deep_research_backup_20260406.py
   rm src/utils/model_gateway_backup_20260406.py
   ```

2. **统一 send_reply**
   - 删除 `feishu_sdk_client.py:3093` 的 `send_reply` 定义
   - 确保所有调用方使用 `from scripts.feishu_handlers.chat_helpers import send_reply`

### 近期执行（🟡）

3. **拆分 structured_doc.py**（5637行 → 多个模块）
   - 拆出：`structured_doc_templates.py`（模板定义）
   - 拆出：`structured_doc_excel.py`（Excel 导出）
   - 拆出：`structured_doc_parser.py`（JSON 解析）

4. **合并模型配置**
   - 合并 `deep_research/config.py` 和 `deep_research/models.py` 的模型映射
   - 删除硬编码模型名，统一通过 `get_model_for_task()` 路由

5. **移动测试文件**
   ```bash
   mkdir -p tests/scripts
   mv scripts/test_*.py tests/scripts/
   ```

### 可延后执行（🟢）

6. **claude_thinking_layer.py TODO**
   - 补充实现或标注为"暂不实现"

---

## 健康指标

| 指标 | 当前值 | 目标值 | 状态 |
|------|--------|--------|------|
| 大文件（>800行） | 3个 | 0个 | 🟡 需拆分 |
| 备份文件 | 2个 | 0个 | 🔴 需删除 |
| 重复函数 | 1个 | 0个 | 🔴 需统一 |
| 测试文件散落 | 12个 | 0个 | 🟡 需移动 |
| 禁用模型引用 | 备份文件中 | 0个 | 🔴 删除备份即可 |
| TODO 未完成 | 1处 | 全处理 | 🟢 低优先 |

---

*报告生成: 2026-04-06*
*下次扫描建议: 30天后*