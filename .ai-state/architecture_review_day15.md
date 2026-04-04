# agent_company 架构 Review

> 审查日期: 2026-03-31
> 审查范围: 项目结构、核心模块、代码质量、架构合理性
> 数据来源: GitHub 仓库 lion9999ly/agent-company（commit 67b8a10）

---

## 一、整体架构评估

### 架构健康度: 65/100

项目从一个飞书聊天机器人成长为一个五层深度研究管道 + 多 Agent 协作系统，核心功能链路是通的，但积累了大量的技术债务。主要问题不是"什么不能工作"，而是"大量东西积攒在一起，越来越难维护"。

### 核心优势
- **飞书集成完善**: text_router.py 的指令路由清晰，从精确指令到意图识别层层降级
- **模型武器库丰富**: 14+ 个模型配置，降级链设计合理
- **知识库设计合理**: 四域分类（competitors/components/standards/lessons）+ confidence 分级 + 入库 guardrail
- **安全意识好**: hash 校验、文档同构检查、指令防护、行为日志
- **深度研究管道 v2 架构合理**: 五层分层提炼 + 并发 + 降级

### 核心问题（按严重程度排序）

---

## 二、P0 问题（影响系统稳定性）

### 2.1 根目录严重污染

根目录有 30+ 个散落的 `.md` 文件（`prd_v2_round3_fix.md`、`phase_2.1_heartbeat_guidance.md` 等）和异常文件名（`300}`、`80`、`{result}`、`List[Dict[str`、`intent`）。

**风险**: CC 每次启动都要扫描项目根目录来理解代码结构。30+ 个无用文件增加 context 噪音，降低 CC 执行质量。异常文件名说明 CC 曾经误操作，可能在某些情况下还会发生。

**建议**: 
- 立即归档所有根目录 `.md` 到 `docs/archived/` 或 `.ai-state/archived_docs/`
- 删除异常文件（`300}`、`80`、`{result}` 等）
- `.gitignore` 中添加通配规则防止再次出现

### 2.2 CLAUDE.md 严重过时

当前 `CLAUDE.md` 版本 `20260318.4`，核心代码清单还指向旧文件（`src/config/agents.yaml` 而不是 `model_registry.yaml`），没有任何关于五层管道、深度研究、元能力层、Critic 校准等今天改造的内容。

**风险**: CC 每次启动都读这个文件。过时的 CLAUDE.md 意味着 CC 对系统的理解停留在 3 月 18 日的状态，不知道五层管道、并发设计、元能力层的存在。这会导致 CC 在后续改动中做出不一致的决策。

**建议**: 全面更新 CLAUDE.md，至少包含：
- 当前架构概览（五层管道、三个运行模式、元能力层）
- 核心代码清单更新（tonight_deep_research.py、meta_capability.py、critic_calibration.py）
- 模型路由 v2 的设计决策
- 禁止列表和安全边界

### 2.3 多版本脚本共存

`scripts/` 下有三个看起来功能重叠的文件：
- `tonight_deep_research.py`（当前主力，v2 五层管道）
- `overnight_deep_learning_v2.py`（旧版？）
- `overnight_deep_learning_v3.py`（旧版？）
- `tonight_jdm_learning.py`（旧版？）

另外还有 `daily_learning.py` 和 `auto_learn.py`。

**风险**: 不清楚哪些还在被调用、哪些是死代码。如果飞书某个指令还指向旧版脚本，就会跑旧逻辑。

**建议**: 确认 text_router.py 中所有 import 都指向正确的当前文件。旧版脚本移到 `scripts/archived/`。

---

## 三、P1 问题（影响开发效率）

### 3.1 知识库搜索用暴力遍历

`knowledge_base.py` 的 `search_knowledge()` 对 KB_ROOT 下所有 `.json` 文件做 `rglob("*.json")` 全扫描，逐文件读取 JSON 后字符串匹配。现在 ~3235 条，每次搜索遍历 3235 个文件。

**现在还行，但很快会成瓶颈**: 深度学习每次任务都要调 `_get_kb_context_enhanced()` 和 `search_knowledge()`，如果 KB 增长到 10000+ 条，搜索延迟会明显拖慢管道。

**建议**（不急，但应该规划）:
- 短期: 构建内存索引（启动时加载所有条目到 dict，搜索时查内存）
- 中期: 接入 SQLite FTS5 全文搜索
- 长期: 接入向量数据库（如 ChromaDB）

### 3.2 `.cc-connect/images/` 无限备份 Bug

```
img_1773824060971_0_bak.jpg
img_1773824060971_0_bak_bak.jpg
img_1773824060971_0_bak_bak_bak.jpg
... (12 层嵌套 bak)
```

`feishu_bridge/ocr_middleware.py` 或图片处理逻辑在每次处理图片时创建 `_bak` 后缀的备份，但不清理旧备份。

**建议**: 找到创建 `_bak` 的代码，改为只保留最新一个备份，或完全不备份。

### 3.3 `src/huge_code.py` 的存在

文件名暗示这是一个超大单体文件。违反了 CLAUDE.md 中自己定义的"单文件 ≤ 800 行"红线。

**建议**: 如果还在用，拆分。如果是废弃的，删除。

### 3.4 LangGraph 状态机与深度研究管道割裂

`src/graph/router.py` 定义了完整的 LangGraph 状态机（hash_check → doc_sync_check → planning → agent 分析 → synthesis → critic），但 `tonight_deep_research.py` 的五层管道完全绕过了它，自己实现了一套搜索→提炼→分析→整合→Critic 流程。

**影响**: 两套系统共存。飞书的"研发任务"走 LangGraph，"深度学习"走 tonight_deep_research.py。它们共享 KB 和模型网关，但 Agent 逻辑、Critic 逻辑、安全检查各自独立。

**这不一定是问题** — LangGraph 适合交互式研发任务（有来有回），五层管道适合批量自主研究（无人值守）。但要注意：
- LangGraph 侧的 Critic 逻辑没有今天的 P0/P1/P2 分级改进
- LangGraph 侧的模型路由还是旧的（agents.yaml），不是 v2 的角色分配
- 两边的知识入库逻辑可能不一致

**建议**: 短期不改（两套各有用途），但应该在 CLAUDE.md 中明确记录"两套系统的边界和各自职责"，避免 CC 在改一套时意外影响另一套。

---

## 四、P2 问题（代码卫生）

### 4.1 元能力层的 forbidden 列表和 CLAUDE.md 的安全黑名单不一致

CLAUDE.md 禁止 `eval()`、`exec()`、`os.system()`、`subprocess.Popen(shell=True)`。
meta_capability.py 禁止 `eval`、`exec`、`git push`、`rm -rf`、`DROP TABLE` 等。

两个列表有重叠但不完全一致。应该统一。

### 4.2 `_archive_competitors/` 有大量 HTML 爬虫产物

~60 个 HTML 文件 + JSON 文件，是早期竞品分析的爬虫产物。占空间且不再使用。

**建议**: 移出 Git 跟踪（加入 .gitignore），或压缩归档。

### 4.3 `.ai-state/` 下 CC 执行文档应该归档

`.ai-state/cc_exec_part1_pipeline_overhaul.md` 等 6 个执行文档已经执行完毕，不应该留在 .ai-state 根目录。

**建议**: 移到 `.ai-state/archived_cc_docs/` 或 `docs/cc_history/`。

---

## 五、架构亮点（值得保留和强化）

### 5.1 ProgressHeartbeat 机制
进度心跳推送到飞书，夜间跑批也能通过手机看进度。设计优秀。

### 5.2 知识库 Guardrail
入库前的三层防护（最小长度、confidence 上限、去重指纹）有效防止了低质量数据污染。

### 5.3 模型降级链
`FALLBACK_MAP` + `_call_with_backoff()` 的降级+退避设计，在今天的测试中表现良好（o3 404 自动降级到 gpt_5_4）。

### 5.4 Critic 校准的"人不在循环里，但判断在循环里"
飞书按钮打标 → 积累校准数据 → 自动进化 few-shot 的设计理念优秀。

---

## 六、建议的优先级操作

| 优先级 | 操作 | 预计耗时 |
|--------|------|---------|
| P0-1 | 清理根目录垃圾文件 | 10 min |
| P0-2 | 更新 CLAUDE.md 到当前架构 | 30 min |
| P0-3 | 确认 text_router.py 所有 import 指向正确文件 | 15 min |
| P1-1 | 旧版脚本归档到 scripts/archived/ | 10 min |
| P1-2 | 修复 .cc-connect 图片无限备份 | 15 min |
| P1-3 | 检查 src/huge_code.py 是否可删除 | 5 min |
| P2-1 | 统一安全禁止列表 | 10 min |
| P2-2 | 归档 _archive_competitors/ | 5 min |
| P2-3 | 归档已执行的 CC 文档 | 5 min |

**P0 操作建议今晚给 CC 做**，尤其是 CLAUDE.md 更新——这是 CC 每次启动的"大脑"，过时的大脑 = 低质量的执行。
