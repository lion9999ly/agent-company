# CC 执行文档 — 轨道 C: 知识与数据层

> 文件集: src/tools/knowledge_base.py, scripts/kb_governance.py, scripts/critic_calibration.py, src/utils/token_usage_tracker.py, 各 yaml/json 配置文件
> 不要动: tonight_deep_research.py, deep_research/*.py, text_router.py, commands.py
> 每项改完后: `git add -A && git commit -m "..." && git push origin main`
> **不要重启服务。**

---

## C-1: A1 补充模型定价

在 `src/utils/token_usage_tracker.py` 的 `PRICING` 字典中补充：

```python
# GPT-5.4 (Azure, 2026 估算)
"gpt-5.4": {"input": 0.005, "output": 0.015},
# o3-deep-research
"o3-deep-research-2025-06-26": {"input": 0.010, "output": 0.040},
# Gemini 3.x
"gemini-3.1-pro-preview": {"input": 0.00175, "output": 0.007},
"gemini-3-pro-preview": {"input": 0.00125, "output": 0.005},
# 火山引擎豆包
"doubao-seed-2-0-pro-260215": {"input": 0.00056, "output": 0.00222},
"doubao-seed-2-0-lite-260215": {"input": 0.00014, "output": 0.00042},
"deepseek-v3-2-251201": {"input": 0.00014, "output": 0.00028},
# Azure 其他
"gpt-4o": {"input": 0.0025, "output": 0.01},
"claude-opus-4-6": {"input": 0.015, "output": 0.075},
"claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
"grok-4-fast-reasoning": {"input": 0.005, "output": 0.015},
```

commit: `"fix: add missing model pricing for gpt-5.4, o3, doubao, gemini-3.x"`

注意：同时补充 Grok 定价：
```python
"grok-4-fast-reasoning": {"input": 0.0055, "output": 0.0275},
```

---

## C-2: A2 统一错误处理

在 `scripts/feishu_handlers/chat_helpers.py`（或适合的位置）新增：

```python
def safe_reply_error(send_reply, reply_target: str, task_name: str, error: Exception):
    """统一错误回复：用户看友好消息，详细日志记文件"""
    import traceback
    print(f"[ERROR] {task_name}: {traceback.format_exc()}")
    send_reply(reply_target, f"⚠️ {task_name} 遇到问题，已记录日志。请稍后重试。")
```

然后在 text_router.py 和其他 handler 中，把所有 `except Exception as e: send_reply(f"失败: {e}")` 替换为 `safe_reply_error(send_reply, reply_target, "任务名", e)`。

注意：这个改动涉及 text_router.py，**但只改 except 块内容，不改路由逻辑**，与轨道 B 的改动不冲突。如果轨道 B 同时在改 text_router.py，则跳过此项，让轨道 B 顺带做。

commit: `"fix: unified error handling — friendly messages to user, stacktrace to log"`

---

## C-3: B1 决策就绪通知

修改深度学习汇总报告（在 `tonight_deep_research.py` 或 `deep_research/scheduler.py` 中）的汇总部分，扫描决策树充分度。

注意：汇总报告代码可能在轨道 A 的文件中。如果是，**在 .ai-state/ 下新建一个独立的 `decision_readiness.py` 脚本**，避免冲突：

```python
"""决策就绪检测"""
import yaml, json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

def check_decision_readiness() -> str:
    """扫描决策树，返回各决策点的知识充分度"""
    dt_path = PROJECT_ROOT / ".ai-state" / "product_decision_tree.yaml"
    if not dt_path.exists():
        return ""

    dt = yaml.safe_load(dt_path.read_text(encoding='utf-8'))
    lines = []
    for d in dt.get("decisions", []):
        if d.get("status") != "open":
            continue
        total = len(d.get("blocking_knowledge", []))
        resolved = len(d.get("resolved_knowledge", []))
        if total == 0:
            continue
        ratio = resolved / total
        icon = "🟢" if ratio >= 0.8 else "🟡" if ratio >= 0.5 else "🔴"
        line = f"  {icon} {d['question'][:50]} — {resolved}/{total}"
        if ratio >= 0.8:
            line += " ← 建议做决定"
        lines.append(line)

    if lines:
        return "📌 决策就绪度\n" + "\n".join(lines)
    return ""
```

commit: `"feat: decision readiness notification — scan decision tree completeness"`

---

## C-4: B2 自学习联动决策树

在 `scripts/auto_learn.py` 的 `_find_kb_gaps()` 中，优先从决策树的 blocking_knowledge 生成搜索词。

在函数开头添加：

```python
    # 优先: 从决策树获取阻塞知识缺口
    dt_path = Path(__file__).parent.parent / ".ai-state" / "product_decision_tree.yaml"
    if dt_path.exists():
        try:
            import yaml as _yaml
            dt = _yaml.safe_load(dt_path.read_text(encoding='utf-8'))
            for d in dt.get("decisions", []):
                if d.get("status") != "open":
                    continue
                resolved_texts = [r.get("knowledge", "") for r in d.get("resolved_knowledge", [])]
                for bk in d.get("blocking_knowledge", []):
                    # 检查是否已解决
                    already = any(bk[:20].lower() in rt.lower() for rt in resolved_texts)
                    if not already:
                        gaps.append({
                            "type": "decision_blocking",
                            "domain": "components",
                            "query": bk,
                            "priority": d.get("priority", 2),
                            "decision_id": d.get("id", ""),
                        })
        except:
            pass
```

commit: `"feat: auto-learn aligned with decision tree — prioritize blocking knowledge gaps"`

---

## C-5: B3 研究结果回流决策树

新建 `scripts/decision_tree_updater.py`：

```python
"""研究结果自动回流到决策树"""
import yaml, json, re, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DT_PATH = PROJECT_ROOT / ".ai-state" / "product_decision_tree.yaml"

def update_decision_tree_from_report(report: str, task_title: str):
    """检查报告中的关键发现是否填充了决策树的 blocking_knowledge"""
    if not DT_PATH.exists():
        return

    dt = yaml.safe_load(DT_PATH.read_text(encoding='utf-8'))
    updated = False

    for decision in dt.get("decisions", []):
        if decision.get("status") != "open":
            continue

        for bk in decision.get("blocking_knowledge", []):
            # 检查报告中是否包含相关信息
            bk_keywords = set(re.findall(r'[\u4e00-\u9fff]{2,4}|[A-Z][a-z]+|[A-Z]{2,}', bk))
            report_lower = report.lower()
            matches = sum(1 for kw in bk_keywords if kw.lower() in report_lower)

            if matches >= 2:  # 至少匹配 2 个关键词
                # 检查是否已 resolved
                existing = decision.get("resolved_knowledge", [])
                already = any(bk[:20].lower() in r.get("knowledge", "").lower() for r in existing)
                if not already:
                    if "resolved_knowledge" not in decision:
                        decision["resolved_knowledge"] = []
                    # 从报告中提取相关摘要
                    decision["resolved_knowledge"].append({
                        "knowledge": f"来自研究 '{task_title}' 的相关发现（自动匹配）",
                        "source": f"deep_learn_{task_title}",
                        "resolved_at": time.strftime('%Y-%m-%d'),
                    })
                    updated = True
                    print(f"  [DT-Update] {decision['id']}: resolved '{bk[:40]}...'")

    if updated:
        DT_PATH.write_text(yaml.dump(dt, allow_unicode=True, default_flow_style=False), encoding='utf-8')
```

commit: `"feat: auto-update decision tree from research findings"`

---

## C-6: C2 回答附带置信度和溯源

在 `src/tools/knowledge_base.py` 的 `search_knowledge()` 返回结果中已有 confidence。修改 `format_knowledge_for_prompt()` 增加时间和来源信息：

```python
def format_knowledge_for_answer(entries: List[Dict[str, Any]]) -> str:
    """格式化知识条目用于回答（含置信度和溯源）"""
    if not entries:
        return ""
    parts = []
    for e in entries:
        conf = e.get("confidence", "medium")
        created = e.get("created_at", "?")
        source = e.get("source", "auto")
        conf_icon = {"authoritative": "⭐⭐⭐", "high": "⭐⭐", "medium": "⭐", "low": "⚠️"}.get(conf, "")
        parts.append(f"{conf_icon} {e.get('title', '')} (📅{created} | 🔗{source})")
        parts.append(f"  {e.get('content', '')[:300]}")

        # 检查是否有矛盾标记
        if "needs_reconciliation" in e.get("tags", []):
            parts.append(f"  ⚠️ 此数据存在矛盾，建议交叉验证")
    return "\n".join(parts)
```

commit: `"feat: knowledge answers with confidence, timestamp, and source attribution"`

---

## C-7: C4 知识库"我不确定"能力

在知识库搜索结果后处理中，检测矛盾条目并主动说明。修改 `search_knowledge()` 或新增 `detect_contradictions_in_results()`：

```python
def detect_contradictions_in_results(results: list) -> str:
    """检测搜索结果中的矛盾数据"""
    if len(results) < 2:
        return ""

    # 简单检测：同一实体不同数值
    entities = {}
    for r in results:
        title = r.get("title", "")
        content = r.get("content", "")
        # 提取数值型数据
        numbers = re.findall(r'(\d+(?:\.\d+)?)\s*(万台|nits|mW|USD|元|克|g|mm|小时|h)', content)
        for num, unit in numbers:
            key = f"{title[:10]}_{unit}"
            if key not in entities:
                entities[key] = []
            entities[key].append({"value": float(num), "source": title, "confidence": r.get("confidence", "")})

    contradictions = []
    for key, values in entities.items():
        if len(values) >= 2:
            vals = [v["value"] for v in values]
            if max(vals) / max(min(vals), 0.01) > 1.5:  # 差异超过 50%
                contradictions.append({
                    "key": key,
                    "values": values,
                })

    if contradictions:
        lines = ["⚠️ KB 中存在矛盾信息:"]
        for c in contradictions[:3]:
            for v in c["values"]:
                lines.append(f"  - {v['source']}: {v['value']} ({v['confidence']})")
        return "\n".join(lines)
    return ""
```

commit: `"feat: KB uncertainty detection — auto-detect contradictions in search results"`

---

## C-8: D2 决策树-Anchor 联动

在 `product_decision_tree.yaml` 中为每个决策点添加 `affected_modules` 字段：

```yaml
  - id: "v1_display"
    affected_modules: ["信息中岛", "导航", "视觉交互", "开机动画", "场景模式"]
```

CC 根据每个决策的 question 内容，推断影响的 PRD 模块（参考 `product_spec_anchor.yaml` 中的模块列表）。

commit: `"feat: decision tree linked to PRD anchor modules"`

---

## C-9: E2 知识升级机制

修改 `knowledge_base.py` 的 `add_knowledge()`，在入库前检查是否存在同产品同参数的旧条目，如果有则 merge 更新：

```python
# 在现有的去重检查之后，新增 merge 逻辑：
# 检查是否有同产品的旧条目
for existing in domain_dir.glob("*.json"):
    try:
        old = json.loads(existing.read_text(encoding='utf-8'))
        # 同产品名 + 不同时间 = 更新而非新增
        if (title[:15].lower() in old.get("title", "").lower() and
            old.get("created_at", "") != datetime.now().strftime("%Y-%m-%d")):
            # Merge: 保留旧条目作为历史版本
            history = old.get("_history", [])
            history.append({"content": old["content"], "date": old.get("created_at", ""), "confidence": old.get("confidence", "")})
            old["_history"] = history[-5:]  # 最多保留 5 个历史版本
            old["content"] = content
            old["created_at"] = datetime.now().strftime("%Y-%m-%d")
            old["confidence"] = confidence
            old["tags"] = list(set(old.get("tags", []) + tags))
            existing.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f"[KB] 升级条目: {title[:40]}（保留 {len(history)} 个历史版本）")
            return str(existing)
    except:
        continue
```

commit: `"feat: knowledge upgrade mechanism — merge-update existing entries instead of duplicating"`

---

## C-10: H3 竞品动态时间线

修改 KB 条目结构，竞品数据增加 `observed_at` 时间戳。修改 `add_knowledge()` 在 competitors 域自动添加时间戳：

```python
if domain == "competitors":
    entry["observed_at"] = datetime.now().strftime("%Y-%m-%d")
```

commit: `"feat: competitor timeline — add observed_at timestamp for trend tracking"`

---

## C-11: H4 不确定性量化

在 Layer 2 提炼 prompt 中增加置信分数和区间估算（这个改动在 deep_research 模块中，但这里只改数据结构）。

修改 `knowledge_base.py` 的 `add_knowledge()` 支持 `confidence_score` 和 `uncertainty_range` 字段：

```python
def add_knowledge(..., confidence_score: float = None, uncertainty_range: str = None):
    ...
    entry["confidence_score"] = confidence_score  # 0.0-1.0
    entry["uncertainty_range"] = uncertainty_range  # "500-800万台/年"
```

commit: `"feat: uncertainty quantification — numeric confidence scores and range estimates"`

---

## C-12: I3 项目阶段感知

创建 `.ai-state/project_phase.yaml`：

```yaml
current_phase: "方案论证"
phases:
  方案论证:
    research_focus: ["技术路线对比", "竞品分析", "用户需求"]
    priority_boost: ["v1_display", "v1_intercom", "v1_audio"]
  供应商评选:
    research_focus: ["供应商对比", "成本分析", "交期评估", "MOQ"]
    priority_boost: ["v1_jdm_partner"]
  原型开发:
    research_focus: ["工程实现", "规格书解读", "接口定义"]
    priority_boost: []
  量产准备:
    research_focus: ["认证流程", "品控标准", "供应链风险"]
    priority_boost: ["v1_safety_cert"]
```

commit: `"feat: project phase awareness — auto-adjust research priorities by development stage"`

---

## C-13: I4 方法论与领域知识分离

在 `knowledge_base.py` 中：
- 添加 `"methodology"` 到 `VALID_DOMAINS`
- 添加 `"methodology": "methodology"` 到 `DOMAIN_MAP`
- 创建 `knowledge_base/methodology/` 目录

commit: `"feat: methodology knowledge domain — reusable frameworks across projects"`

---

## 总提交数: 13 个 commit

---

## C-14: Kn3 回答信心校准

在日常智能对话回答后，追加可选反馈提示。在 `_smart_route_and_reply()`（text_router.py 的兜底回复函数）中，如果回答引用了 KB 数据，在末尾追加：

```python
    # 如果回答使用了 KB 数据，追加反馈按钮
    if kb_used:
        reply_text += "\n\n📊 这个回答准确吗？回复 👍 或 👎"
```

注意：这改了 text_router.py。**如果轨道 B 同时在改这个函数，则跳过此项，让轨道 B 顺带做。** 否则在 `knowledge_base.py` 中新增反馈记录函数：

```python
FEEDBACK_PATH = KB_ROOT.parent / "answer_feedback.jsonl"

def record_answer_feedback(query: str, confidence: str, is_accurate: bool):
    """记录回答反馈"""
    import json, time
    entry = {"query": query[:100], "confidence": confidence, "accurate": is_accurate, "timestamp": time.strftime('%Y-%m-%d')}
    with open(FEEDBACK_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def get_calibration_stats() -> dict:
    """统计各 confidence 等级的实际准确率"""
    if not FEEDBACK_PATH.exists():
        return {}
    from collections import defaultdict
    stats = defaultdict(lambda: {"total": 0, "accurate": 0})
    for line in FEEDBACK_PATH.read_text(encoding='utf-8').strip().split('\n'):
        try:
            e = json.loads(line)
            c = e.get("confidence", "unknown")
            stats[c]["total"] += 1
            if e.get("accurate"):
                stats[c]["accurate"] += 1
        except:
            continue
    return {k: {"accuracy": v["accurate"]/max(v["total"],1), "samples": v["total"]} for k, v in stats.items()}
```

commit: `"feat: answer confidence calibration — track accuracy per confidence level"`

---

## C-15: Kn4 可信度传播网络

在 `knowledge_base.py` 的 `add_knowledge()` 中新增 `derived_from` 参数：

```python
def add_knowledge(..., derived_from: str = None):
    ...
    if derived_from:
        entry["derived_from"] = derived_from  # 引用的上游条目 path 或 title
```

在 `kb_governance.py` 中新增传播逻辑：

```python
def _propagate_confidence_changes():
    """当上游条目 confidence 变化时，扫描所有下游条目"""
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            derived = data.get("derived_from")
            if not derived:
                continue
            # 查找上游条目
            upstream = _find_entry_by_path_or_title(derived)
            if upstream and upstream.get("confidence") == "low":
                if data.get("confidence") not in ("low",):
                    data["confidence"] = "low"
                    data["_upstream_warning"] = f"上游数据 '{derived}' 已降级为 low"
                    f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                    print(f"  [Propagate] 降级: {data.get('title', '')[:40]} (上游: {derived[:40]})")
        except:
            continue
```

commit: `"feat: confidence propagation network — cascade confidence changes through derived entries"`

---

## 更新后总提交数: 15 个 commit

---

## C-16: N4 跨项目方法论沉淀

在项目阶段切换时（`.ai-state/project_phase.yaml` 的 `current_phase` 变更），自动触发方法论提取：

```python
def _extract_phase_methodology(completed_phase: str):
    """从已完成阶段提取方法论经验"""
    from src.tools.knowledge_base import add_knowledge, KB_ROOT

    # 收集该阶段产生的所有报告和任务记录
    # 用 gpt-5.4 提取"什么流程有效、什么工具好用、踩了什么坑"
    # 存入 methodology 域
    pass  # CC 自行实现
```

commit: `"feat: methodology extraction — auto-capture process learnings at phase transitions"`

---

## 最终总提交数: 16 个 commit

---

## C-17: O2 时间价值排序

在 `product_decision_tree.yaml` 的每个决策点增加 `deadline` 字段：

```yaml
  - id: "v1_display"
    deadline: "2026-04-30"
```

修改任务优先级计算（在 deep_research scheduler 或 auto_learn 中）：

```python
def _calculate_time_weighted_priority(base_priority: int, deadline: str) -> float:
    """优先级 × 紧迫度系数"""
    if not deadline:
        return float(base_priority)
    from datetime import datetime
    days_left = (datetime.strptime(deadline, "%Y-%m-%d") - datetime.now()).days
    if days_left <= 0:
        urgency = 5.0  # 已过期，最高紧迫
    elif days_left <= 7:
        urgency = 3.0
    elif days_left <= 30:
        urgency = 1.5
    else:
        urgency = 1.0
    return base_priority * urgency
```

注意：这个函数可能在轨道 A 的文件中。如果是，**在本轨道只修改 yaml 文件结构和 auto_learn.py 中的优先级排序**，不改 deep_research 代码。

飞书指令注册（由轨道 B 负责，本轨道只准备数据层）：
```
飞书发"设置截止日: v1_display 2026-04-30" → 更新 decision_tree yaml
```

commit: `"feat: time-value priority — deadline-driven dynamic task urgency"`

---

## 最终总提交数: 17 个 commit

---

## C-18: P1 Demo 研究任务优先执行

在 `.ai-state/research_task_pool.yaml` 中追加 9 个 Demo 研究任务（竞品布局实测、人因工程、光照可见性、色彩方案、信息优先级、竞品 App 流程、骑行 UX、组队地图、配对流程），全部设为 priority: 1。

参考 `handoff_20260331.md` 第八节中的 Demo 研究任务列表，或 `demo_research_tasks.md`（如果存在）。

commit: `"chore: add 9 demo research tasks to pool with priority 1"`

## C-19: Q1 KB 向量搜索

在 `src/tools/knowledge_base.py` 中增加向量搜索能力：

```python
# 尝试导入向量搜索依赖
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    _EMBED_MODEL = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    HAS_VECTOR = True
except ImportError:
    HAS_VECTOR = False
    print("[KB] sentence-transformers 未安装，向量搜索禁用")

EMBEDDINGS_PATH = KB_ROOT.parent / "kb_embeddings.npz"

def _build_embedding_index():
    """构建/更新 embedding 索引"""
    ...

def vector_search(query: str, limit: int = 10) -> list:
    """向量相似度搜索"""
    ...

def search_knowledge(query: str, limit: int = 5) -> list:
    """混合搜索：向量 + 关键词"""
    if HAS_VECTOR:
        vector_results = vector_search(query, limit=limit*2)
        keyword_results = _keyword_search(query, limit=limit*2)
        # 合并去重，向量结果优先
        ...
    else:
        return _keyword_search(query, limit)
```

需要先安装依赖：`pip install sentence-transformers --break-system-packages`

commit: `"feat: KB vector search — semantic similarity search with keyword fallback"`

---

## 最终总提交数: 19 个 commit

---

## C-20: R3 审计日志

所有操作记录到 `.ai-state/audit_log.jsonl`。在 text_router.py 的 `route_text_message()` 入口处追加审计记录调用。CC 自行实现 `audit_logger.py` 模块。

注意：审计日志的**写入**不改 text_router 逻辑（只在入口追加一行调用），与轨道 B 不冲突。

commit: `"feat: audit logging — who asked what when, with data access tracking"`

## C-21: R4 组织学习

在 `knowledge_base.py` 的 `add_knowledge()` 中，当 `caller="team_member"` 时，confidence 直接设为 high（第一手信息）。

在 text_router.py 中识别"记录:"前缀时（轨道 B 已有类似逻辑），确保 caller 参数传递正确。

commit: `"feat: organizational learning — team member first-hand info gets high confidence"`

---

## 最终总提交数: 21 个 commit
