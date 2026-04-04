# agent_company 五层诊断与提升方案

> 日期: 2026-04-01
> 基于: GitHub 源码审查 + 首次深度学习实跑日志 + 架构 review
> 定位: 从战略到细节的完整梳理

---

## 第一层：战略层 — 这个系统在为什么服务？

### 现状
agent_company 是一个"虚拟研发中心"，服务于智能摩托车全脸头盔的产品研发。五个 Agent 协作，通过飞书接口与 Leo 互动，夜间自主学习扩展知识库。

### 问题
**系统缺乏一个显式的"产品开发路线图"来驱动所有行为。** 现在的任务来源有三种：Leo 手动指定、任务池硬编码、系统自主发现。但这三种来源没有一个统一的"北极星"来排序——系统不知道"V1 最紧迫需要回答的 10 个问题是什么"。

表现在：
- 自主发现的任务重复（HUD 技术选型出现两次）
- 任务优先级靠 `priority: 1/2/3` 手工标注，没有自动排序逻辑
- 系统不知道哪些知识缺口直接阻塞 V1 决策，哪些只是储备

### 提升方案

**S1: 引入"决策树"驱动任务规划**

在 `.ai-state/product_decision_tree.yaml` 中定义 V1 的核心决策树：

```yaml
decisions:
  - id: "v1_display"
    question: "V1 用 OLED+FreeForm 还是 MicroLED+波导？"
    status: "open"  # open / decided / blocked
    blocking_knowledge:
      - "OLED vs MicroLED 户外亮度对比实测数据"
      - "两种方案的 BOM 成本差异"
      - "供应商交期和 MOQ"
    decided_value: null
    decided_at: null

  - id: "v1_soc"
    question: "主 SoC 用 Qualcomm AR1 Gen1 还是替代方案？"
    status: "decided"
    decided_value: "Qualcomm AR1 Gen 1"
    blocking_knowledge: []

  - id: "v1_intercom"
    question: "Mesh Intercom 自研还是用 Cardo DMC？"
    status: "open"
    blocking_knowledge:
      - "Cardo DMC 授权费和技术限制"
      - "自研 Mesh 的开发周期和成本"
```

深度学习的任务发现引擎优先填充 `blocking_knowledge` 中的缺口，而不是泛泛地搜索。这样每个研究任务都直接服务于一个决策点。

**S2: 知识库与决策树双向绑定**

每条 KB 条目标注它服务于哪个决策（`decision_ref: "v1_display"`）。决策树定期扫描 KB，自动更新"这个决策的知识充分度"。当某个决策的知识充分度达到阈值，飞书主动提醒 Leo："V1 显示方案的知识储备已达 85%，是否可以做决定了？"

---

## 第二层：架构层 — 系统的骨架对不对？

### 现状
两套并行系统：LangGraph 状态机（交互式研发任务）+ 五层管道（自主深度研究）。共享 KB 和模型网关。

### 问题

**A1: 两套系统的 Agent 逻辑不统一**

LangGraph 侧的 CTO/CMO/CDO 用的是 `src/config/agent_prompts.yaml` 中的 prompt，走 `src/graph/router.py` 的节点逻辑。五层管道侧的 Agent 用的是 `tonight_deep_research.py` 中内联的 prompt 字符串。

结果：同一个"CTO"在两个系统中的行为不一致。LangGraph 的 CTO 可能说"建议用方案 A"，五层管道的 CTO 可能说"建议用方案 B"，因为它们的 system prompt 不同。

**A2: 知识库是纯文件系统，没有索引**

3235 个 JSON 文件，每次搜索全量 rglob 遍历。现在还行，但增长到 10000+ 会成瓶颈。

**A3: 没有统一的任务状态管理**

深度学习的任务状态分散在：`.ai-state/research_task_pool.yaml`（任务池）、`.ai-state/reports/`（报告）、日志（完成状态）。没有一个统一的地方可以看到"这个任务是计划中/执行中/完成/失败"。

### 提升方案

**A1 修复: Agent prompt 统一管理**

把所有 Agent 的 system prompt 集中到 `src/config/agent_prompts.yaml` 中，五层管道和 LangGraph 都从这里读取。tonight_deep_research.py 中的内联 prompt 改为：

```python
from src.config.prompt_loader import get_agent_prompt
cto_prompt = get_agent_prompt("CTO") + expert_injection + anchor_instruction
```

这样修改 CTO 的行为只需要改一个文件。

**A2 修复: KB 内存索引**

新增 `src/tools/kb_index.py`，在服务启动时加载所有 KB 条目到内存 dict，用关键词倒排索引。搜索时查内存，不读文件。写入时同时更新文件和内存索引。

```python
class KBIndex:
    def __init__(self):
        self.entries = {}       # id → entry dict
        self.keyword_index = {} # keyword → set of ids
        self._load_all()

    def search(self, query: str, limit: int = 15) -> list:
        # O(1) 关键词查找，不再遍历文件
        ...

    def add(self, entry: dict) -> str:
        # 写文件 + 更新内存索引
        ...
```

**A3 修复: 任务状态统一管理**

新增 `.ai-state/task_tracker.jsonl`，每个任务的生命周期事件都追加写入：

```jsonl
{"task_id": "xxx", "event": "created", "title": "...", "timestamp": "..."}
{"task_id": "xxx", "event": "started", "timestamp": "..."}
{"task_id": "xxx", "event": "completed", "duration_min": 20, "kb_added": 5, "p0_count": 1, "timestamp": "..."}
```

飞书新增"任务状态"指令，返回最近 N 个任务的状态一览。

---

## 第三层：模块层 — 每个模块的质量

### 现状
核心模块：model_gateway.py、tonight_deep_research.py、knowledge_base.py、text_router.py、meta_capability.py、critic_calibration.py

### 问题

**M1: tonight_deep_research.py 太大**

这个文件现在可能超过 1000 行（五层管道 + 并发 + 发现 + 专家框架 + schema 定义 + Agent prompt 全在一起）。违反了 CLAUDE.md 中自己的"单文件 ≤ 800 行"红线。CC 改这个文件时 context 压力大，容易出错。

**M2: model_gateway.py 缺少连接池和健康检查**

每次 API 调用都新建 HTTP 连接（`requests.post`）。高并发时（8 个 doubao 并发）TCP 连接频繁创建销毁。应该用 `requests.Session` 复用连接。

同时没有模型健康检查——不知道哪个模型"现在是否可用"，只能靠调用失败后降级。可以加一个轻量的 ping 机制。

**M3: expert_frameworks.yaml 的匹配逻辑太简单**

当前用关键词计数匹配（`score = sum(1 for kw in match_keywords if kw in text)`）。如果任务目标是"光学供应商选型"，但 expert_frameworks 里的 keyword 是"光波导"、"OLED"，可能匹配不上"供应商选型"框架。

**M4: Critic 校准的 few-shot 进化还没有被实际消费**

`critic_calibration.py` 的 `evolve_few_shot()` 会生成 `.ai-state/critic_few_shot_evolved.json`，`get_evolved_few_shot()` 会读取并返回进化版文本。但 `_run_critic_challenge()` 中是否真的调用了 `get_evolved_few_shot()` 取决于 CC 的实现。需要验证。

### 提升方案

**M1 修复: 拆分 tonight_deep_research.py**

```
tonight_deep_research.py (主调度器，~200行)
├── deep_research/pipeline.py (五层管道核心，~300行)
├── deep_research/search.py (Layer 1 搜索，~150行)
├── deep_research/distill.py (Layer 2 提炼，~100行)
├── deep_research/agents.py (Layer 3 Agent 分析，~150行)
├── deep_research/synthesis.py (Layer 4 整合，~150行)
├── deep_research/critic.py (Layer 5 Critic，~200行)
└── deep_research/schemas.py (提取 schema 定义，~100行)
```

**M2 修复: 连接池**

在 `ModelGateway.__init__()` 中创建 `requests.Session`：
```python
self._sessions = {
    "azure": requests.Session(),
    "google": requests.Session(),
    "volcengine": requests.Session(),
}
```

各 `call_*` 方法用对应的 session 而不是裸 `requests.post`。

**M3 修复: 专家框架模糊匹配**

除了关键词精确匹配，增加语义相关词扩展：
```python
SYNONYM_MAP = {
    "供应商": ["供应链", "JDM", "代工", "ODM", "制造商"],
    "光学": ["光波导", "OLED", "Micro LED", "HUD", "显示"],
    "声学": ["扬声器", "麦克风", "ANC", "降噪", "骨传导"],
}
```

**M4 修复: 验证 few-shot 进化链路**

CC 检查 `_run_critic_challenge()` 中是否有调用 `get_evolved_few_shot()`。如果没有，补上。

---

## 第四层：数据层 — 知识库的质量和结构

### 现状
~3235 条，四域（competitors/components/standards/lessons），confidence 三级（high/medium/low + authoritative）。

### 问题

**D1: 缺乏知识的"时效性"标记**

一条 2026 年 1 月写入的"Cardo Packtalk 售价 $399"到现在可能已经过时。`kb_governance.py` 有 `_mark_stale()` 但阈值是 60 天——对价格类数据太长，对技术参数类又太短。

**D2: 知识之间没有关联**

"歌尔的产能"和"歌尔的报价"是两条独立条目。搜索"歌尔"能找到两条，但系统不知道它们描述的是同一个供应商。没有实体关联。

**D3: 深度研究产出的知识质量参差**

自学习（Layer 1-2 only）产出的条目 confidence 固定为 medium，但有些实际质量很高（直接引用了厂商 datasheet），有些很低（LLM 编造的数据）。没有区分。

**D4: 知识库没有"版本"概念**

条目被覆盖后旧数据就丢了。如果 KB 治理误删了一条实际有用的条目，无法恢复。

### 提升方案

**D1 修复: 分类时效性阈值**

```python
STALE_DAYS_BY_TYPE = {
    "price": 30,          # 价格类 30 天过时
    "market_share": 60,   # 市场份额 60 天
    "tech_spec": 180,     # 技术参数 180 天
    "standard": 365,      # 行业标准 1 年
    "lesson": 365,        # 经验教训 1 年
}
```

在 `add_knowledge()` 时根据 domain 和 tags 自动推断类型，设置对应的过时阈值。

**D2 修复: 轻量实体索引**

不需要完整的知识图谱，只要一个实体→条目的映射：

```python
# .ai-state/entity_index.json
{
    "歌尔": ["kb_entry_001", "kb_entry_042", "kb_entry_103"],
    "Cardo": ["kb_entry_005", "kb_entry_067"],
    "OLED": ["kb_entry_012", "kb_entry_088", "kb_entry_102"],
}
```

搜索"歌尔"时先查实体索引，再读条目。Agent 分析时可以说"关于歌尔，知识库有 3 条相关信息"。

**D3 修复: 自动 confidence 评估**

在 Layer 2 提炼时，让 Flash 同时评估每个数据点的 confidence：
- 引用了具体型号、厂商报价、数据表 → high
- 引用了新闻报道、分析师估算 → medium
- 无明确来源、LLM 推理 → low

**D4 修复: KB 软删除**

`kb_governance.py` 的 `_safe_delete()` 改为软删除——不删除文件，而是移到 `.ai-state/knowledge/_trash/` 并记录删除原因和时间。30 天后自动清理 trash。

---

## 第五层：运维层 — 日常运行的可靠性

### 现状
飞书长连接 → feishu_sdk_client.py → text_router.py。定时任务（自学习 30min、深度学习每晚 1 点）。手动重启。

### 问题

**O1: 没有进程监控和自动重启**

飞书 SDK 长连接断开后不会自动重连（取决于 SDK 内部实现）。如果 Python 进程 crash，系统就停了，只有 Leo 手动发现并重启。

**O2: 没有 API 用量监控告警**

Azure、Google、火山引擎的 API 调用没有日粒度汇总。如果某天因为 bug 导致 API 调用暴增（比如无限重试循环），不会有任何告警直到账单到来。

**O3: 日志分散**

运行日志在 stdout（PowerShell 窗口），飞书调试日志在 `.ai-state/feishu_debug.log`，API 用量在 `.ai-state/usage_logs/`。没有统一的日志聚合。排查问题需要同时看三个地方。

**O4: 没有定时任务管理器**

自学习 30min 和深度学习每晚 1 点的定时触发，实现方式未知（可能是 APScheduler，可能是 threading.Timer，可能是 Windows 任务计划程序）。如果进程重启，定时任务是否自动恢复？

**O5: Git 工作流不完整**

CC 每次 commit 后 push，但没有分支策略。所有改动直接 push 到 main。如果 CC 改出了 bug，没有快速 rollback 的机制（只能 git revert）。

### 提升方案

**O1 修复: watchdog + 自动重启**

创建 `scripts/watchdog.py`，监控飞书连接状态和主进程心跳：

```python
# 每 60 秒检查:
# 1. 飞书连接是否活跃（检查 heartbeat.txt 的最后修改时间）
# 2. 主进程是否存在
# 如果超过 5 分钟没有心跳，自动重启
```

或者更简单：用 Windows 任务计划程序设置"程序崩溃后自动重启"。

**O2 修复: API 用量日报**

在 `token_usage_tracker.py` 中增加日报功能，每天早上 8:00 推送到飞书：

```
📊 API 用量日报 (2026-03-31)
Azure: 125 次, ~$3.50
Google: 89 次, ~$1.20
豆包: 156 次, ~$0.80
总计: 370 次, ~$5.50
```

**O3 修复: 统一日志**

所有模块的 print 语句统一走 Python logging，输出到 `.ai-state/logs/agent_company.log`，同时保留 stdout。用 RotatingFileHandler 自动轮转。

**O4 修复: 确认定时任务机制**

CC 检查现有的定时任务实现方式，确认：
- 自学习 30min 的 scheduler 是否在 `feishu_sdk_client.py` 启动时注册
- 深度学习每晚 1 点是否注册
- 进程重启后定时任务是否自动恢复

如果没有，用 APScheduler 的 `BackgroundScheduler` 统一管理。

**O5 修复: 简单的 rollback 机制**

不需要分支策略，只需要在 CLAUDE.md 中加一条规则：

```
每次重大改动前，CC 先执行 git tag pre-{feature} 打标签。
如果改动出问题，可以 git checkout pre-{feature} 快速回滚。
```

---

## 执行优先级

| 优先级 | 改进 | 层面 | 预计工作量 |
|--------|------|------|-----------|
| P0 | S1 决策树驱动任务规划 | 战略 | 1h（yaml + 注入发现引擎） |
| P0 | A1 Agent prompt 统一管理 | 架构 | 30min |
| P0 | M1 拆分 tonight_deep_research.py | 模块 | 1h |
| P1 | A3 任务状态统一管理 | 架构 | 30min |
| P1 | M2 连接池 | 模块 | 15min |
| P1 | D1 分类时效性 | 数据 | 20min |
| P1 | D3 自动 confidence 评估 | 数据 | 20min |
| P1 | D4 KB 软删除 | 数据 | 15min |
| P1 | O1 watchdog | 运维 | 30min |
| P1 | O2 API 用量日报 | 运维 | 30min |
| P2 | A2 KB 内存索引 | 架构 | 1h |
| P2 | D2 实体索引 | 数据 | 30min |
| P2 | M3 专家框架模糊匹配 | 模块 | 15min |
| P2 | M4 验证 few-shot 链路 | 模块 | 10min |
| P2 | O3 统一日志 | 运维 | 30min |
| P2 | O4 定时任务确认 | 运维 | 15min |
| P2 | O5 rollback 标签 | 运维 | 5min |
| P2 | S2 知识库-决策树绑定 | 战略 | 1h |
