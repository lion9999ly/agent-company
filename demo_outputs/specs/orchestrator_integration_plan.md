# Orchestrator 嵌入改造方案

## 核心变化

**现在：** 飞书 → agent.py → roundtable handler → Generator（LLM 生成代码）→ Verifier（LLM 审代码）
**改后：** 飞书 → agent.py → roundtable handler → 圆桌讨论出规格 → **Orchestrator（程序控制 CC 分模块写代码 + 测试 + 截图 + 视觉审查）**

对 Leo 来说触发方式不变：飞书发 `圆桌:hud_demo`，收到好的产出。

---

## 一、roundtable/__init__.py 改造

### run_task 函数改造点

当前步骤 3-4（Generator 生成 + Verifier 审查）替换为 Orchestrator 调用。

```python
# 当前流程
async def run_task(task, gw, kb, feishu):
    # 0. 知识结晶
    # 1. 议题审查
    # 2. 圆桌讨论 → result
    # 3. Generator 生成代码        ← 删除
    # 4. Verifier 审查循环         ← 删除
    # 5. 输出
    # 6-9. 云文档/Issue/Inbox

# 改后流程
async def run_task(task, gw, kb, feishu):
    # 0. 知识结晶
    # 1. 议题审查
    # 2. 圆桌讨论 → result（方案文本）
    # === 分流点 ===
    if task.output_type in ('html', 'code', 'js', 'jsx', 'python'):
        # 3a. 规格生成（LLM 把方案翻译成 tech_spec + test_spec + visual_criteria）
        # 3b. Orchestrator 执行（程序调用 CC 写代码 + 跑测试 + 截图 + 视觉审查）
        output, output_path = await run_code_orchestrator(task, result, gw, feishu)
    else:
        # 文档类产出走原有 Generator（文档不需要执行验证）
        output = await gen.generate(task, result)
        output_path = write_output(task, output)
    # 5-9. 后续流程不变
```

### 分流逻辑说明

- 代码类（html/js/python）：圆桌讨论出方案 → LLM 生成规格文档 → Orchestrator 调用 CC 实现 → 程序化测试 → 视觉审查 → 交付
- 文档类（markdown/report/pptx）：圆桌讨论出方案 → Generator 直接生成 → Verifier 审查（保留现有逻辑，文档不需要执行验证）

---

## 二、新增 run_code_orchestrator 函数

文件：`scripts/roundtable/code_orchestrator.py`（新建）

```python
async def run_code_orchestrator(task, rt_result, gw, feishu):
    """代码类产出的 Orchestrator
    
    流程：
    1. 规格生成（LLM）
    2. 模块化代码编写（CC，逐模块调用）
    3. 程序化质量检查（Python，不依赖 LLM）
    4. 拼装（确定性 Python 脚本）
    5. 结构测试（node test_spec.js）
    6. 截图（puppeteer）
    7. 视觉审查（多模态 LLM）
    8. 返回产出
    
    每一步都是程序控制，CC 只在步骤 2 被调用。
    """
```

### 步骤 1：规格生成

用 LLM（gpt_5_4）把圆桌方案翻译成三份文档：
- tech_spec.md（如果 TaskSpec 里已经提供了就跳过）
- test_spec.js（可执行的测试脚本）
- visual_criteria.md（视觉验收标准）

**关键约束：如果 TaskSpec 已经附带了这三份文档（比如 hud_demo 已经人工写好了），直接用，不要让 LLM 重新生成。** TaskSpec 新增字段：

```json
{
  "spec_files": {
    "tech_spec": "demo_outputs/specs/hud_demo_tech_spec.md",
    "test_spec": "demo_outputs/specs/hud_demo_test_spec.js",
    "visual_criteria": "demo_outputs/specs/hud_demo_visual_criteria.md"
  }
}
```

### 步骤 2-7：复用 run_hud_demo.py 的逻辑

run_hud_demo.py 里的 Phase 2-6 逻辑抽取为可复用的函数，被 code_orchestrator.py 调用。不是让 CC 运行 run_hud_demo.py，是 code_orchestrator.py 内部调用这些函数。

### 步骤 8：返回

```python
return output_html, output_path  # 供 __init__.py 的后续步骤使用
```

---

## 三、Deep Research 管道搜索层修复

文件：`scripts/deep_research/pipeline.py`

### 当前问题

搜索层依赖 Claude Code WebSearch（harness 配置了不存在的模型，完全不能用）。

### 修复方案：多通道分流

```python
class SearchRouter:
    """搜索路由器：按语言和内容类型分流"""
    
    def search(self, query, language='auto'):
        if language == 'auto':
            language = detect_language(query)
        
        if language == 'zh':
            # 中文查询：doubao 优先（中文搜索增强）
            results = self._search_doubao(query)
            if not results:
                results = self._search_tavily(query)
        else:
            # 英文查询：Tavily 优先（英文搜索强）
            results = self._search_tavily(query)
            if not results:
                results = self._search_gemini(query)
        
        return results
    
    def _search_tavily(self, query):
        """Tavily API 直接调用（已验证可用）"""
        # 注意 Tavily 免费版限制：每分钟有频率限制
        # 批量搜索时加 sleep(2) 间隔
    
    def _search_doubao(self, query):
        """豆包搜索增强（火山引擎，中文优势）"""
        # 通过 model_gateway 调用，task_type='chat' 不用 'deep_research'
    
    def _search_gemini(self, query):
        """Gemini 2.5 Flash 搜索增强"""
        # 通过 model_gateway 调用
    
    def _search_grok(self, query):
        """Grok 4 搜索（Azure 上可用）"""
        # 备用通道
```

### 接入管道

pipeline.py 的 L1（并发搜索层）改用 SearchRouter 而不是直接调用 model_gateway 的 deep_research task_type。

---

## 四、CC 执行纪律的程序化约束

### 问题

CC 被告知"运行 orchestrator"但选择绕过。LLM 的本性是走最短路径，不是遵守流程。

### 解法

CC 不是流程发起者。Orchestrator 通过 `subprocess` 调用 CC（`claude -p`），每次只给一个小任务。CC 看到的是：

```
你是一个前端开发者。请根据以下技术规格写模块 M2 的代码。
[tech_spec 相关段落]
保存到 demo_outputs/hud_modules/m2_state_machine.js
```

CC 不知道有 M1、M3、M4、M5。它只知道当前这一个模块。它不知道有 orchestrator、有测试脚本、有视觉审查。它没有机会绕过，因为它不知道有流程存在。

### 代码实现

run_hud_demo.py 里的 `call_cc()` 函数已经是这个模式。code_orchestrator.py 复用同样的调用方式。

### CLAUDE.md 约束（防止 CC 在其他场景绕过）

```markdown
## 执行纪律（程序化约束）

当收到来自 orchestrator 的调用时：
1. 只完成指定的单一任务
2. 不要询问整体流程
3. 不要自行判断"是否需要这个步骤"
4. 不要替换或简化指定的输出格式
5. 如果任务不清楚，返回"任务不清楚"而不是自行推测
```

---

## 五、实施步骤

### 给 CC 的执行清单（一个 commit）

```
1. 新建 scripts/roundtable/code_orchestrator.py
   - 从 run_hud_demo.py 提取 Phase 2-6 逻辑
   - 封装为 async def run_code_orchestrator(task, rt_result, gw, feishu)

2. 修改 scripts/roundtable/__init__.py
   - run_task 函数加分流逻辑（代码类 → code_orchestrator，文档类 → 原有 Generator）
   - 保留步骤 5-9 不变

3. 修改 scripts/deep_research/pipeline.py
   - 新建 SearchRouter 类
   - L1 搜索层改用 SearchRouter
   - 搜索间隔 sleep(2) 防止 Tavily 限流

4. 修改 .ai-state/task_specs/hud_demo.json
   - 新增 spec_files 字段指向三份已有规格文档

5. 修改 CLAUDE.md
   - 新增执行纪律约束

commit message: feat: orchestrator integration + deep research search fix + CC discipline
```

### 验证方式

Leo 在飞书发 `圆桌:hud_demo`，观察：
- 圆桌讨论后是否走了 orchestrator 路径（日志应显示"[Orchestrator] Phase 2: 写模块 M1"）
- CC 是否被逐模块调用（不是一次性生成完整 HTML）
- 测试是否自动跑（日志显示 test_spec.js 结果）
- 截图是否自动生成
- 视觉审查是否执行
- 最终交付到飞书的是否包含截图 + 测试报告
