# CC 指令：Day 17 Session 4 — Bug 修复 + 技术债清理

> **来源**：Claude Chat 通过 GitHub 逐文件审查代码后产出
> **执行原则**：先讨论确认，再写代码。每个修复完成后立即 `git add + commit + push`。
> **强制要求**：本轮所有改动完成后必须 `git push`，让 Claude Chat 能通过 GitHub 验证。

---

## 第一部分：P0 Bug 修复（3 个，预计 30 分钟）

### Bug 1：Phase1Output 缺参数默认值

**文件**：`scripts/roundtable/roundtable.py`，约 440 行附近

**问题**：
```python
my_constraints = phase1_outputs.get(role, Phase1Output(role=role))
# TypeError: Phase1Output.__init__() missing 4 required positional arguments
```

**修复方案**：

方案 A（推荐）—— 在 `task_spec.py` 的 `Phase1Output` dataclass 上加默认值：
```python
@dataclass
class Phase1Output:
    role: str
    constraints: list = field(default_factory=list)
    judgments: list = field(default_factory=list)
    uncertainties: list = field(default_factory=list)
    claims: list = field(default_factory=list)
```

方案 B —— 不改 dataclass，改调用点（不推荐，散落多处难维护）。

**验证**：
1. 在 Python 中 `from scripts.roundtable.task_spec import Phase1Output; Phase1Output(role="test")` 不报错
2. 全文搜索 `Phase1Output(` 确认所有构造点兼容

**commit message**：`fix: Phase1Output add default empty lists for optional fields`

---

### Bug 2：load_task_spec 模糊匹配

**文件**：飞书路由中 `load_task_spec()` 函数所在文件（可能在 `scripts/roundtable/__init__.py` 或 `scripts/feishu_handlers/` 某处）

**问题**：
用户发 `圆桌:HUD Demo 生成` → 系统找 `.ai-state/task_specs/` 下的 JSON → 文件名是 `hud_demo.json` → 匹配不到 → 静默降级到旧 demo_generator

**修复方案**：

```python
def load_task_spec(topic: str) -> Optional[TaskSpec]:
    """从 .ai-state/task_specs/ 加载 TaskSpec，支持模糊匹配"""
    import json
    from pathlib import Path
    
    specs_dir = Path(".ai-state/task_specs")
    if not specs_dir.exists():
        return None
    
    # 1. 精确匹配（原逻辑）
    exact = specs_dir / f"{topic}.json"
    if exact.exists():
        return _parse_task_spec(exact)
    
    # 2. 归一化匹配：中文空格→下划线，转小写，去标点
    def normalize(s: str) -> str:
        import re
        s = s.strip().lower()
        s = re.sub(r'[\s\u3000]+', '_', s)          # 空格/全角空格 → _
        s = re.sub(r'[^\w\u4e00-\u9fff]', '', s)    # 去非字母数字非中文
        return s
    
    norm_topic = normalize(topic)
    
    for f in specs_dir.glob("*.json"):
        norm_file = normalize(f.stem)
        if norm_file == norm_topic:
            return _parse_task_spec(f)
    
    # 3. 子串匹配（topic 的归一化版本包含在文件名中，或反之）
    for f in specs_dir.glob("*.json"):
        norm_file = normalize(f.stem)
        if norm_topic in norm_file or norm_file in norm_topic:
            return _parse_task_spec(f)
    
    # 4. JSON 内部 topic 字段匹配
    for f in specs_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if normalize(data.get("topic", "")) == norm_topic:
                return _parse_task_spec(f)
        except:
            continue
    
    return None
```

**关键**：同时检查飞书路由里 `圆桌:` 指令是否有 fallback 到旧 demo_generator 的逻辑。如果有，**删除那个 fallback**。匹配失败应该明确返回"未找到 TaskSpec"，而不是静默走另一条路径。

**验证**：
1. `load_task_spec("HUD Demo 生成")` → 匹配到 `hud_demo.json` ✅
2. `load_task_spec("hud_demo")` → 匹配到 `hud_demo.json` ✅
3. `load_task_spec("不存在的任务")` → 返回 None ✅（不降级到旧逻辑）

**commit message**：`fix: load_task_spec fuzzy matching + remove silent fallback to demo_generator`

---

### Bug 3：确保 meta_cognition 保持禁用

**文件**：`scripts/roundtable/meta_cognition.py`

**问题**：当前通过所有方法 return None 临时禁用，但没有显式的开关，容易被后续改动意外启用。

**修复方案**：

在文件顶部加显式开关：
```python
# ============================================================
# ⚠️ 临时禁用 — 等待 CDP 桥接协议重新设计
# 启用条件：完成以下三项
#   1. 频率限制（每个任务最多调 3 次思考通道）
#   2. 内容去重（已推送过的不重复推）
#   3. 长度限制（≤1000 字摘要，不推全文）
# 启用前必须经 Leo 确认
# ============================================================
META_COGNITION_ENABLED = False
```

在每个公开方法的入口：
```python
def check_blind_spots(self, ...):
    if not META_COGNITION_ENABLED:
        return None
    # ... 原逻辑
```

**不要删除任何实现代码**，只加开关。这样重新启用时只需改一个布尔值。

同时在 `scripts/roundtable/roundtable.py` 中所有调用 `meta_cognition` 的地方，确认有 `if result is not None` 的保护。

**验证**：
1. `META_COGNITION_ENABLED = False` 时，圆桌流程不调用 CDP 桥接
2. grep 确认没有绕过开关直接调用 `_build_thinking_context()` 的路径

**commit message**：`fix: meta_cognition explicit disable switch with re-enable checklist`

---

## 第二部分：技术债清理计划（分批执行）

> 以下按优先级排列。每批完成后 commit + push + 飞书通知 Leo。
> **原则**：清理不改行为，只改结构。每次清理后跑 `regression_check.py`。

---

### 批次 A：根目录垃圾清理（15 分钟）

**问题**：根目录有大量不应存在的文件，是 CC 输出解析错误的产物。

**需要删除的文件**（确认后执行）：
```
300},
80
{result}
List[Dict[str
intent
鎺ㄨ崘                    # 推荐的乱码
debug_json.txt
test.db
```

**需要移到 `docs/archive/` 的文件**（历史指令文件，有参考价值但不应在根目录）：
```
bugfix_abc.md
cc_doubao_azure_probe.md
cc_probe_deployments.md
cc_test_models_instruction.md
context_board.md
conversational_agent_upgrade.md
day12_batch2_tasks.md
deep_learn_v3_fixes.md
deep_research_pipeline_fix.md
feishu_refactor_v2.md
fix1_structured_doc_logic.md
fix2_html_template.md
hud_research_tasks.md
mermaid_render_fix.md
overnight_deep_learning_v3.md
phase_0.4_critic_cdo_patch.md
phase_1.3_1.4_critic_upgrade_patch.md
phase_2.1_heartbeat_guidance.md
phase_2.2_reply_target_patch.md
phase_2.3_2.4_guidance.md
phase_3_4_cc_instructions.md
platform_monitor_and_chat_archive.md
prd_architecture_reform.md
prd_complete_evolution.md
prd_evolution_step123.md
prd_full_evolution.md
prd_output_fix.md
prd_quality_evolution_final.md
prd_speed_optimization.md
prd_structure_refactor_cc.md
prd_v2_final_combined_fix.md
prd_v2_round3_full_fix.md
prd_v2_round4_fix.md
prd_v2_round5_fix.md
prd_v2_round8_fix.md
prd_v2_upgrade.md
self_evolution_engine.md
structured_doc_6sheet.md
```

**需要移到合适位置的文件**：
- `feishu_sdk_client_recovered.py` → `_archive_competitors/` 或删除（如果已合并）
- `product_spec_anchor.yaml` → `.ai-state/`（如果还在用）或删除
- `RJ_PRD.JSON` / `RJ_PRD.xlsx` → `docs/deliverables/`

**commit message**：`chore: clean root directory — delete garbage files, archive old instructions`

---

### 批次 B：备份文件清理（5 分钟）

**需要删除的备份文件**（handover 已识别）：
```
scripts/tonight_deep_research_backup_20260406.py     # 3906 行
src/utils/model_gateway_backup_20260406.py            # 1513 行
```

**验证**：确认原文件存在且功能正常后再删除备份。

**commit message**：`chore: remove backup files (originals verified working)`

---

### 批次 C：CLAUDE.md 更新（10 分钟）

**需要更新的内容**：

1. **版本号**更新为 `20260407.1`

2. **核心代码清单**新增：
```
| scripts/roundtable/           | 圆桌系统（多角色讨论引擎）      |
| scripts/roundtable/roundtable.py | 圆桌核心 Phase 1-4 编排     |
| scripts/roundtable/crystallizer.py | 知识结晶                  |
| scripts/roundtable/verifier.py    | 审查闭环                  |
| scripts/roundtable/generator.py   | 生成器                    |
| scripts/roundtable/meta_cognition.py | 元认知层（当前禁用）     |
| scripts/roundtable/resilience.py  | 韧性机制                  |
| scripts/regression_check.py       | 功能回归验证              |
| .ai-state/capability_registry.json | 功能注册表               |
| .ai-state/task_specs/             | 圆桌 TaskSpec 定义        |
| .ai-state/demo_specs/             | Demo 产品配置             |
```

3. **模型配置表**更新 Gemini 状态（key_1 已恢复可用）

4. **关键文件 URL** 新增圆桌系统相关文件的 raw URL

5. **质量红线**部分加注：
```
> ⚠️ 已知违规：text_router.py 本地 ~2292 行，structured_doc.py ~5637 行
> 这两个文件是拆分优先目标，但当前不阻塞功能开发
```

**commit message**：`docs: CLAUDE.md v20260407.1 — add roundtable system, update model status`

---

### 批次 D：model_gateway.py 去重（30 分钟，可延后）

**问题**：`call_zhipu`、`call_deepseek`、`call_volcengine` 和 `call_azure_openai` 的 80% 代码是重复的。

**重构方案**：

```python
def _call_openai_compatible(self, model_name: str, prompt: str, 
                            system_prompt: str = None,
                            task_type: str = "general") -> Dict[str, Any]:
    """通用 OpenAI 兼容格式调用（覆盖 Azure、智谱、DeepSeek、火山引擎）"""
    cfg = self.models.get(model_name)
    if not cfg or not cfg.api_key:
        return {"success": False, "error": f"Model {model_name} not configured"}
    
    # 各 provider 的 URL 和 header 差异
    url, headers = self._build_request(cfg)
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    payload = self._build_payload(cfg, messages)
    timeout = TIMEOUT_BY_TASK.get(task_type, 120)
    
    start_time = time.time()
    try:
        resp = requests.post(url, json=payload, timeout=timeout, headers=headers)
        result = resp.json()
        latency_ms = int((time.time() - start_time) * 1000)
        
        # 统一错误处理
        if resp.status_code >= 400:
            return self._handle_error(cfg, model_name, resp, result, latency_ms, task_type)
        
        # 统一响应解析
        return self._parse_response(cfg, model_name, result, latency_ms, task_type)
        
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        self._record_failure(cfg, task_type, latency_ms)
        return {"success": False, "error": str(e)}
```

保留 `call_gemini` 作为独立方法（API 格式不同），`call_azure_responses` 作为独立方法（Responses API 不同）。

**重构后预期**：model_gateway.py 从 ~900 行降到 ~500 行，且新增 provider 只需加 URL/header 配置。

**注意**：此批次改动面大，必须在圆桌跑通之后再做。先跑 `regression_check.py` 建立基线。

**commit message**：`refactor: model_gateway extract _call_openai_compatible to deduplicate providers`

---

### 批次 E：model_gateway.py 404 handler 死代码修复（5 分钟）

**文件**：`src/utils/model_gateway.py`，`call_azure_openai` 方法中的 404 处理：

```python
# 当前代码（错误）：
try:
    from scripts.feishu_handlers.text_router import reply_target
    reply_target(f"⚠️ 模型 404\n...", target="alert")
except Exception:
    pass
```

`reply_target` 不是 `text_router.py` 的导出函数。这段代码永远走 except。

**修复方案**：要么删除这段代码（404 已经在 print 输出日志了），要么改成正确的飞书通知调用：

```python
try:
    from scripts.feishu_handlers.chat_helpers import send_reply_safe
    send_reply_safe(f"⚠️ 模型 404: {model_name} deployment={deployment_name}")
except Exception:
    pass  # 告警失败不影响主流程
```

确认 `chat_helpers.py` 中有合适的函数可用。如果没有，直接删除这段死代码。

**commit message**：`fix: model_gateway remove dead 404 feishu alert code`

---

### 批次 F：send_reply 定义统一（10 分钟）

**问题**：handover 提到 `send_reply` 在两处定义，应统一为 `chat_helpers.py` 的版本。

**操作**：
1. 搜索项目中所有 `def send_reply` 定义
2. 确认 `scripts/feishu_handlers/chat_helpers.py` 是权威版本
3. 其他位置改为 `from scripts.feishu_handlers.chat_helpers import send_reply`
4. 如果函数签名不完全一致，以 chat_helpers 为准，调用方适配

**commit message**：`refactor: unify send_reply to single source in chat_helpers.py`

---

### 批次 G（延后）：text_router.py 拆分方案

> 这是最大的技术债，但也是风险最高的改动。**不在本 session 执行**，只出方案。

**当前状态**：本地 ~2292 行，所有路由逻辑在一个巨型 `route_text_message` 函数中。

**拆分方案**：

```
scripts/feishu_handlers/
├── text_router.py          # 主路由（仅路由逻辑，~150 行）
├── commands.py             # 精确指令处理（已有，继续扩展）
├── learning_handlers.py    # 学习相关指令（深度学习/自学习/KB治理/对齐）
├── roundtable_handler.py   # 圆桌指令处理
├── import_handlers.py      # 文档导入/URL分享/文章导入
├── smart_chat.py           # 智能对话兜底
└── chat_helpers.py         # 公共工具（已有）
```

**text_router.py 重构后结构**：
```python
def route_text_message(text, ...):
    text_stripped = text.strip()
    
    # 1. 精确指令（优先级最高）
    if handle_command(text_stripped, ...): return
    
    # 2. 帮助
    if text_stripped in HELP_TRIGGERS: ...
    
    # 3. 圆桌（新增，必须在学习指令之前）
    if text_stripped.startswith("圆桌:") or text_stripped.startswith("圆桌："):
        return roundtable_handler.handle(text_stripped, ...)
    
    # 4. 学习类
    if learning_handlers.try_handle(text_stripped, ...): return
    
    # 5. 导入类
    if import_handlers.try_handle(text_stripped, ...): return
    
    # 6. 结构化文档
    if structured_doc.try_fast_track(text_stripped, ...): return
    
    # 7. 研发任务
    if is_rd_task(text_stripped): ...
    
    # 8. 兜底
    smart_chat.handle(text_stripped, ...)
```

**执行时机**：圆桌跑通 + 3 个 bug 修复 + 基础技术债清理之后。

---

## 第三部分：执行顺序

```
1. Bug 1 修复 → commit → push
2. Bug 2 修复 → commit → push
3. Bug 3 修复 → commit → push
4. 飞书发 "圆桌:hud_demo" 跑通完整流程 → 截日志
5. 批次 A（根目录清理）→ commit → push
6. 批次 B（备份文件清理）→ commit → push
7. 批次 C（CLAUDE.md 更新）→ commit → push
8. 批次 E（404 死代码）→ commit → push
9. 批次 F（send_reply 统一）→ commit → push
10. regression_check.py 全量跑一次 → 截图发飞书

批次 D（model_gateway 去重）和批次 G（text_router 拆分）延后到下一 session。
```

---

## 第四部分：验证清单

完成后，CC 在飞书发送以下确认：

```
✅ Bug 1: Phase1Output 默认值 — 已修复 + 测试通过
✅ Bug 2: load_task_spec 模糊匹配 — 已修复 + 3 条测试通过
✅ Bug 3: meta_cognition 显式开关 — 已加 + grep 确认无绕过
✅ 圆桌:hud_demo — 跑通 / 未跑通（附日志路径）
✅ 根目录清理 — N 个文件删除，M 个文件归档
✅ CLAUDE.md — 更新到 v20260407.1
✅ regression_check.py — 全量通过 / 有 N 个失败（附详情）
✅ git push — 完成，最新 commit: {hash}
```

---

## 附：Claude Chat 代码审查发现的额外问题

以下不需要立即修复，但 CC 应记入 `.ai-state/tech_debt_report_20260407.md`：

1. **knowledge_base.py 搜索是纯关键词匹配**：对圆桌 crystallizer 的 KB 搜索质量有影响。中期需要加 TF-IDF 或简单的向量搜索。

2. **model_gateway.py 的 call() 是 if/elif 链**：应改为 dispatch dict `{provider: method}`，但优先级低于去重。

3. **12 个测试文件散落在 scripts/**：应收拢到 `tests/` 目录。

4. **feishu_sdk_client_recovered.py 在根目录**：如果已合并到正式代码，应删除。

5. **CLAUDE.md 关键文件 URL 列表**缺少圆桌系统文件 — 批次 C 中一并修复。

6. **.gitignore 可能缺少规则**：`test.db`、`.ai-state/knowledge/` 中的大量 JSON 文件（3000+ 条 KB）可能不应该全部提交到 Git。需要评估哪些属于代码仓库、哪些属于运行时数据。
