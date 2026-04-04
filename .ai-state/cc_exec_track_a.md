# CC 执行文档 — 轨道 A: 深度研究管道

> 文件集: scripts/deep_research/*.py（或 scripts/tonight_deep_research.py 如果 P0-3 拆分未完成）
> 不要动: text_router.py, knowledge_base.py, model_gateway.py, 任何 yaml/json 配置
> 每项改完后: `git add -A && git commit -m "..." && git push origin main`
> **不要重启服务。**

---

## 前置检查

先确认 P0-3（拆分 tonight_deep_research.py）是否已完成：

```bash
ls scripts/deep_research/
```

如果 `scripts/deep_research/` 目录存在且有 pipeline.py、search.py 等文件，则改对应的模块文件。
如果不存在（P0-3 未完成），则全部改 `scripts/tonight_deep_research.py`。

---

## A-1: F2 深钻模式

在深度研究模块中新增 `_deep_drill()` 函数：

```python
def deep_drill(topic: str, max_rounds: int = 4, progress_callback=None) -> str:
    """深钻模式：对一个主题连续多轮深入研究

    第 1 轮: 广搜 — 搜索该主题的全面信息
    第 2 轮: 追问 — 基于第 1 轮发现的疑点和缺口，生成新的搜索词深入
    第 3 轮: 验证 — 对矛盾数据点交叉验证
    第 4 轮: 结论 — 整合所有轮次发现，形成结论性报告

    每轮的输出作为下一轮的输入。
    """
    all_findings = []

    for round_num in range(1, max_rounds + 1):
        round_type = {1: "广搜", 2: "追问", 3: "验证", 4: "结论"}
        print(f"\n  [DeepDrill] 第 {round_num} 轮: {round_type.get(round_num, '深入')}")

        if progress_callback:
            progress_callback(f"🔬 深钻 [{round_num}/{max_rounds}] {topic}: {round_type.get(round_num, '深入')}")

        if round_num == 1:
            # 第 1 轮: 广搜
            task = {
                "title": f"深钻-{topic}-广搜",
                "goal": f"全面搜索关于 {topic} 的信息，包括技术参数、供应商、价格、竞品、用户评价",
                "searches": _generate_drill_queries(topic, "broad"),
            }
        elif round_num == 2:
            # 第 2 轮: 基于上轮发现追问
            gaps = _extract_gaps_from_findings(all_findings[-1])
            task = {
                "title": f"深钻-{topic}-追问",
                "goal": f"针对以下疑点深入调查:\n{gaps}",
                "searches": _generate_drill_queries(topic, "deep", context=all_findings[-1]),
            }
        elif round_num == 3:
            # 第 3 轮: 验证矛盾点
            contradictions = _extract_contradictions(all_findings)
            if not contradictions:
                print(f"  [DeepDrill] 无矛盾数据，跳过验证轮")
                continue
            task = {
                "title": f"深钻-{topic}-验证",
                "goal": f"验证以下矛盾数据:\n{contradictions}",
                "searches": _generate_drill_queries(topic, "verify", context=contradictions),
            }
        else:
            # 第 4 轮: 形成结论（不搜索，直接整合）
            conclusion_prompt = (
                f"基于以下 {len(all_findings)} 轮深钻研究的全部发现，"
                f"形成关于 {topic} 的最终结论报告。\n\n"
                + "\n\n---\n\n".join([f"## 第{i+1}轮\n{f[:2000]}" for i, f in enumerate(all_findings)])
            )
            result = _call_model("gpt_5_4", conclusion_prompt,
                                  "你是高级分析师，输出结构化的结论报告。", "deep_drill_conclusion")
            if result.get("success"):
                all_findings.append(result["response"])
            break

        # 执行研究（复用 deep_research_one 的 Layer 1-3）
        if round_num < 4:
            report = deep_research_one(task, progress_callback=progress_callback)
            all_findings.append(report)

    # 合并所有发现
    final_report = "\n\n".join([f"## 第{i+1}轮\n{f}" for i, f in enumerate(all_findings)])

    # 入库
    from src.tools.knowledge_base import add_knowledge
    add_knowledge(
        title=f"[深钻] {topic}",
        domain="lessons",
        content=final_report[:2000],
        tags=["deep_drill", topic],
        source="deep_drill",
        confidence="high"  # 多轮验证后的结论
    )

    return final_report


def _generate_drill_queries(topic: str, mode: str, context: str = "") -> list:
    """生成深钻搜索词"""
    prompt = f"为主题 '{topic}' 生成 6-8 个搜索关键词。"
    if mode == "broad":
        prompt += "\n搜索方向: 全面覆盖（技术、市场、供应商、竞品、用户）"
    elif mode == "deep":
        prompt += f"\n搜索方向: 针对以下发现中的疑点和缺口深入追问:\n{context[:1000]}"
    elif mode == "verify":
        prompt += f"\n搜索方向: 验证以下矛盾数据点:\n{context[:1000]}"
    prompt += "\n只输出搜索词列表，每行一个。"

    result = _call_model("gemini_2_5_flash", prompt, task_type="query_generation")
    if result.get("success"):
        queries = [q.strip() for q in result["response"].strip().split("\n") if q.strip()]
        return queries[:8]
    return [topic]


def _extract_gaps_from_findings(findings: str) -> str:
    """从研究发现中提取知识缺口和疑点"""
    result = _call_model("gemini_2_5_flash",
        f"从以下研究发现中，提取 3-5 个还不清楚的疑点、数据缺口或需要深入的方向:\n\n{findings[:2000]}\n\n只输出疑点列表。",
        task_type="query_generation")
    return result.get("response", "") if result.get("success") else ""


def _extract_contradictions(all_findings: list) -> str:
    """从多轮发现中提取矛盾数据"""
    combined = "\n---\n".join([f[:1000] for f in all_findings])
    result = _call_model("gemini_2_5_flash",
        f"从以下多轮研究中，找出数据矛盾的地方（同一个指标出现了不同的值）:\n\n{combined}\n\n只输出矛盾列表。如果没有矛盾，输出'无矛盾'。",
        task_type="query_generation")
    resp = result.get("response", "") if result.get("success") else ""
    if "无矛盾" in resp:
        return ""
    return resp
```

commit: `"feat: deep drill mode — multi-round deep research on single topic"`

---

## A-2: F3 Agent 辩论机制

在 Layer 3 Agent 并行分析完成后、进入 Layer 4 之前，插入辩论环节。

找到 Layer 3 完成后的位置（agent_outputs 已收集完），插入：

```python
    # === Layer 3.5: Agent 辩论 ===
    if len(agent_outputs) >= 2:
        agent_outputs = _run_agent_debate(agent_outputs, goal, distilled_material)


def _run_agent_debate(agent_outputs: dict, goal: str, evidence: str) -> dict:
    """检测 Agent 间分歧，触发交锋，生成裁决

    流程:
    1. 用 Flash 检测分歧点
    2. 如果有分歧，让持不同意见的 Agent 交锋
    3. 用 gpt-5.4 做最终裁决
    """
    # Step 1: 检测分歧
    combined = "\n\n".join([f"[{role}]\n{output[:1500]}" for role, output in agent_outputs.items()])
    detect_prompt = (
        f"以下是不同 Agent 对同一研究任务的分析：\n\n{combined}\n\n"
        f"找出他们之间的观点分歧（如果有的话）。\n"
        f"输出 JSON: {{\"has_conflict\": true/false, \"conflicts\": ["
        f"{{\"topic\": \"分歧主题\", \"side_a\": {{\"agent\": \"CTO\", \"position\": \"观点\"}}, "
        f"\"side_b\": {{\"agent\": \"CMO\", \"position\": \"观点\"}}}}]}}\n"
        f"如果没有实质性分歧，has_conflict=false。只输出 JSON。"
    )
    detect_result = _call_model("gemini_2_5_flash", detect_prompt, task_type="data_extraction")
    if not detect_result.get("success"):
        return agent_outputs

    try:
        resp = detect_result["response"].strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        conflicts = json.loads(resp)
    except:
        return agent_outputs

    if not conflicts.get("has_conflict") or not conflicts.get("conflicts"):
        print("  [Debate] 无实质分歧")
        return agent_outputs

    print(f"  [Debate] 发现 {len(conflicts['conflicts'])} 个分歧点，开始交锋...")

    # Step 2: 交锋
    debate_record = []
    for conflict in conflicts["conflicts"][:2]:  # 最多处理 2 个分歧
        topic = conflict.get("topic", "")
        side_a = conflict.get("side_a", {})
        side_b = conflict.get("side_b", {})

        # 让 side_a 用数据反驳 side_b
        rebuttal_a = _call_model(
            _get_model_for_role(side_a.get("agent", "CTO")),
            f"你之前的观点是：{side_a.get('position', '')}\n"
            f"{side_b.get('agent', 'CMO')} 的反对观点是：{side_b.get('position', '')}\n"
            f"请用具体数据反驳或承认对方有道理。\n"
            f"参考数据:\n{evidence[:2000]}",
            task_type="debate"
        )

        # 让 side_b 用数据反驳 side_a
        rebuttal_b = _call_model(
            _get_model_for_role(side_b.get("agent", "CMO")),
            f"你之前的观点是：{side_b.get('position', '')}\n"
            f"{side_a.get('agent', 'CTO')} 的反驳是：{rebuttal_a.get('response', '')[:500]}\n"
            f"请用具体数据回应。\n"
            f"参考数据:\n{evidence[:2000]}",
            task_type="debate"
        )

        debate_record.append({
            "topic": topic,
            "side_a": {"agent": side_a.get("agent"), "rebuttal": rebuttal_a.get("response", "")[:500]},
            "side_b": {"agent": side_b.get("agent"), "rebuttal": rebuttal_b.get("response", "")[:500]},
        })

    # Step 3: 裁决（追加到 agent_outputs）
    debate_text = json.dumps(debate_record, ensure_ascii=False, indent=2)
    agent_outputs["_debate"] = (
        f"\n## Agent 辩论记录\n\n"
        f"以下分歧经过交锋后的记录，synthesis 请在整合时重点关注并裁决：\n\n"
        f"{debate_text[:3000]}"
    )
    print(f"  [Debate] 交锋完成，{len(debate_record)} 个分歧点记录已注入 synthesis")

    return agent_outputs
```

commit: `"feat: agent debate mechanism — detect conflicts, cross-argue with data, record for synthesis"`

---

## A-3: G2 跨任务知识传递

在每个深度研究任务完成后，提取 key findings。在新任务启动时，注入相关的历史发现。

```python
FINDINGS_PATH = Path(__file__).parent.parent / ".ai-state" / "task_findings.jsonl"

def _save_task_findings(task_title: str, report: str):
    """从报告中提取 3-5 个关键发现，存入 findings 日志"""
    result = _call_model("gemini_2_5_flash",
        f"从以下研究报告中提取 3-5 个最关键的发现（具体数据点，不是泛泛总结）:\n\n"
        f"{report[:3000]}\n\n"
        f"输出 JSON 数组: [{{\"finding\": \"具体发现\", \"keywords\": [\"关键词1\", \"关键词2\"]}}]",
        task_type="knowledge_extract")
    if result.get("success"):
        try:
            findings = json.loads(re.sub(r'^```json\s*|\s*```$', '', result["response"].strip()))
            entry = {"task_title": task_title, "timestamp": time.strftime('%Y-%m-%d %H:%M'), "findings": findings}
            with open(FINDINGS_PATH, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            print(f"  [Findings] 保存 {len(findings)} 个关键发现")
        except:
            pass


def _get_related_findings(task_title: str, task_goal: str, limit: int = 5) -> str:
    """检索与当前任务相关的历史发现"""
    if not FINDINGS_PATH.exists():
        return ""
    keywords = set(re.findall(r'[\u4e00-\u9fff]{2,4}|[A-Z][a-z]+|[A-Z]{2,}', task_title + " " + task_goal))
    related = []
    for line in FINDINGS_PATH.read_text(encoding='utf-8').strip().split('\n'):
        try:
            entry = json.loads(line)
            for f in entry.get("findings", []):
                f_keywords = set(f.get("keywords", []))
                overlap = keywords & f_keywords
                if overlap:
                    related.append((len(overlap), f["finding"], entry["task_title"]))
        except:
            continue
    related.sort(reverse=True)
    if not related:
        return ""
    text = "\n## 前序任务的相关发现\n"
    for _, finding, source in related[:limit]:
        text += f"- [{source}] {finding}\n"
    return text
```

在 `deep_research_one()` 或 `_run_layers_1_to_3()` 开头注入历史发现：

```python
    prior_findings = _get_related_findings(task.get("title", ""), task.get("goal", ""))
    # 注入到 Agent prompt 的 KB 材料之后
```

在任务完成后保存发现：

```python
    _save_task_findings(task.get("title", ""), report)
```

commit: `"feat: cross-task knowledge transfer — save and inject key findings across research tasks"`

---

## A-4: G3 报告摘要层

在报告保存到文件后，自动生成 3 句话摘要：

```python
def _generate_report_summary(report: str, task_title: str) -> dict:
    """生成报告的 3 句话摘要"""
    result = _call_model("gemini_2_5_flash",
        f"为以下研究报告生成 3 句话摘要:\n"
        f"第 1 句: 核心发现（最重要的一个结论）\n"
        f"第 2 句: 关键数据点（最有决策价值的一个数字）\n"
        f"第 3 句: 对产品决策的影响（这个发现意味着什么）\n\n"
        f"报告标题: {task_title}\n"
        f"报告内容:\n{report[:3000]}\n\n"
        f"输出 JSON: {{\"core_finding\": \"...\", \"key_data\": \"...\", \"decision_impact\": \"...\"}}",
        task_type="knowledge_extract")
    if result.get("success"):
        try:
            return json.loads(re.sub(r'^```json\s*|\s*```$', '', result["response"].strip()))
        except:
            pass
    return {}
```

在报告保存后调用：

```python
    summary = _generate_report_summary(report, task.get("title", ""))
    if summary:
        # 保存摘要到报告元数据
        summary_path = report_path.with_suffix('.summary.json')
        summary_path.write_text(json.dumps({
            "task_title": task.get("title", ""),
            "timestamp": time.strftime('%Y-%m-%d %H:%M'),
            **summary
        }, ensure_ascii=False, indent=2), encoding='utf-8')
```

commit: `"feat: report summary layer — auto-generate 3-sentence abstract for each research report"`

---

## A-5: G4 好奇心驱动

在 Layer 2 提炼时增加 serendipity 检测。修改 `_extract_structured_data()` 的 prompt，在末尾追加：

```
另外，如果你在文本中发现了与当前研究主题不直接相关，但可能对智能骑行头盔项目有价值的意外信息（如新技术突破、新竞品发布、供应链变化），请标记：
"serendipity": [{"finding": "意外发现描述", "potential_value": "可能的价值"}]
```

在 Layer 4 synthesis 完成后，扫描所有结构化数据中的 serendipity 标记，生成新任务追加到任务池：

```python
def _process_serendipity(structured_data_list: list):
    """处理意外发现，追加到任务池"""
    serendipities = []
    for data in structured_data_list:
        if isinstance(data, dict):
            for s in data.get("serendipity", []):
                serendipities.append(s)

    if not serendipities:
        return

    print(f"  [Curiosity] 发现 {len(serendipities)} 个意外线索")

    for s in serendipities[:3]:
        new_task = {
            "id": f"curiosity_{int(time.time())}",
            "title": f"[好奇心] {s.get('finding', '')[:40]}",
            "goal": f"深入调查意外发现: {s.get('finding', '')}。潜在价值: {s.get('potential_value', '')}",
            "priority": 3,
            "source": "serendipity",
            "discovered_at": time.strftime('%Y-%m-%d %H:%M'),
            "searches": [s.get("finding", "")[:50]],
        }
        # 追加到任务池
        pool = _load_task_pool()
        pool.append(new_task)
        _save_task_pool(pool)
        print(f"  [Curiosity] 追加任务: {new_task['title']}")
```

commit: `"feat: curiosity-driven research — detect serendipitous findings and auto-queue new tasks"`

---

## A-6: H1 经验法则提取

在 KB 治理阶段（深度学习结束后）增加模式扫描：

```python
def _extract_experience_rules():
    """从 KB 中提取经验法则

    扫描同类数据（如多个供应商的报价），提取模式。
    """
    from src.tools.knowledge_base import KB_ROOT, add_knowledge

    # 按产品/供应商分组
    groups = {}
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            # 提取供应商名或产品名
            title = data.get("title", "")
            for entity in ["歌尔", "立讯", "Cardo", "Sena", "JBD", "Sony", "OLED", "MicroLED"]:
                if entity.lower() in title.lower():
                    if entity not in groups:
                        groups[entity] = []
                    groups[entity].append(data)
        except:
            continue

    # 对有 5+ 条数据的实体，尝试提取模式
    rules_found = 0
    for entity, entries in groups.items():
        if len(entries) < 5:
            continue

        entries_text = "\n".join([f"- {e.get('title', '')}: {e.get('content', '')[:200]}" for e in entries[:10]])
        result = _call_model("gemini_2_5_flash",
            f"以下是关于 {entity} 的 {len(entries)} 条知识库条目:\n\n{entries_text}\n\n"
            f"从中提取可复用的经验法则或模式（如果有的话）。\n"
            f"例如: '该供应商首次报价通常是最终成本的 X%' 或 '该技术每年降价约 Y%'\n"
            f"如果数据不足以提取可靠模式，输出'数据不足'。\n"
            f"输出 JSON: [{{\"rule\": \"经验法则\", \"sample_count\": N, \"confidence\": 0.0-1.0}}]",
            task_type="knowledge_extract")

        if result.get("success") and "数据不足" not in result["response"]:
            try:
                rules = json.loads(re.sub(r'^```json\s*|\s*```$', '', result["response"].strip()))
                for rule in rules:
                    add_knowledge(
                        title=f"[经验法则] {entity}: {rule.get('rule', '')[:50]}",
                        domain="lessons",
                        content=f"{rule.get('rule', '')}\n\n基于 {rule.get('sample_count', '?')} 个样本，置信度 {rule.get('confidence', '?')}",
                        tags=["experience_rule", entity, "derived"],
                        source="pattern_extraction",
                        confidence="medium"
                    )
                    rules_found += 1
            except:
                pass

    print(f"  [Rules] 提取 {rules_found} 条经验法则")
```

在深度学习结束后的 KB 治理环节调用 `_extract_experience_rules()`。

commit: `"feat: experience rule extraction — auto-detect patterns from accumulated KB data"`

---

## A-7: J1 趋势预测

```python
def _generate_trend_predictions():
    """对 KB 中有时间序列的数据做趋势外推"""
    # 扫描 KB 中有多个时间点数据的指标
    # 用 Flash 做简单线性趋势预测
    # 结果存入 .ai-state/predictions.jsonl
    pass  # CC 自行实现，逻辑参考 improvement_backlog_complete.md 中 J1 描述
```

commit: `"feat: trend prediction — extrapolate time-series data for 6-12 month forecasts"`

---

## A-8: J4 方案压力测试

```python
def stress_test_product(plan_description: str = "", progress_callback=None) -> str:
    """对产品方案做极端场景压力测试"""
    # 生成 15-20 个极端场景
    # 逐个检查方案中是否有应对设计
    # 产出韧性评估报告
    pass  # CC 自行实现，逻辑参考 improvement_backlog_complete.md 中 J4 描述
```

commit: `"feat: product stress test — extreme scenario analysis for V1 plan"`

---

## 总提交数: 8 个 commit

---

## A-9: Kn1 知识综述生成

在 KB 治理阶段（深度学习结束后），扫描同一主题下超过 10 条零散知识，用 gpt-5.4 整合成结构化综述。综述作为 `type: synthesis` 条目入库，confidence=high。

```python
def _generate_knowledge_synthesis():
    """扫描 KB，对碎片知识生成综述"""
    from src.tools.knowledge_base import KB_ROOT, add_knowledge
    from collections import Counter

    # 按主题关键词分组
    topic_groups = {}
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            if data.get("type") == "synthesis":
                continue  # 跳过已有综述
            title = data.get("title", "")
            for keyword in ["HUD", "光学", "歌尔", "Cardo", "Sena", "MicroLED", "OLED", "Mesh", "ANC", "传感器", "认证"]:
                if keyword.lower() in title.lower():
                    if keyword not in topic_groups:
                        topic_groups[keyword] = []
                    topic_groups[keyword].append(data)
        except:
            continue

    for topic, entries in topic_groups.items():
        if len(entries) < 10:
            continue

        entries_text = "\n".join([f"- {e.get('title','')}: {e.get('content','')[:200]}" for e in entries[:20]])
        result = _call_model("gpt_5_4",
            f"以下是关于 '{topic}' 的 {len(entries)} 条知识库碎片。\n"
            f"请整合成一篇结构化综述（1000-1500字），包含：\n"
            f"1. 技术/市场现状概览\n2. 关键供应商/竞品对比\n3. 成本结构\n4. 风险和机会\n5. 决策建议\n\n"
            f"知识碎片:\n{entries_text}",
            "你是行业分析师，用数据说话。", "synthesis")

        if result.get("success"):
            add_knowledge(
                title=f"[综述] {topic} 全景分析",
                domain="lessons",
                content=result["response"],
                tags=["synthesis", topic],
                source="auto_synthesis",
                confidence="high"
            )
            print(f"  [Synthesis] 生成综述: {topic}（基于 {len(entries)} 条碎片）")
```

commit: `"feat: auto knowledge synthesis — merge fragmented entries into structured overviews"`

---

## A-10: Kn2 类比推理引擎

在智能对话和 Agent 分析中，当 KB 缺乏直接数据时自动做类比推理：

```python
def _try_analogy_reasoning(query: str, kb_results: list) -> str:
    """当 KB 直接数据不足时，尝试类比推理"""
    if len(kb_results) >= 3:
        return ""  # 直接数据足够，不需要类比

    analogy_domains = {
        "骑行头盔 HUD": ["汽车 HUD", "战斗机 HUD", "AR 眼镜"],
        "骑行头盔 ANC": ["TWS 耳机 ANC", "头戴式耳机 ANC"],
        "骑行头盔 市场": ["智能手表市场", "运动相机市场", "TWS 耳机市场"],
        "Mesh 组队": ["对讲机市场", "游戏语音组队"],
    }

    # 找到最匹配的类比域
    best_domain = None
    for key, analogies in analogy_domains.items():
        if any(kw in query for kw in key.split()):
            best_domain = analogies
            break

    if not best_domain:
        return ""

    result = _call_model("gemini_2_5_flash",
        f"问题: {query}\n"
        f"直接数据不足。请用以下类似领域的数据做类比推理:\n"
        f"类比领域: {', '.join(best_domain)}\n\n"
        f"输出格式:\n⚡ 类比推理（非直接数据）\n"
        f"类比来源: [领域]\n推理: [具体推理]\n置信度: [低/中]",
        task_type="analogy")

    if result.get("success"):
        return f"\n\n{result['response']}"
    return ""
```

commit: `"feat: analogy reasoning — infer from similar domains when direct data is insufficient"`

---

## 更新后总提交数: 10 个 commit

---

## A-11: M4 信息增量感知的预算路由

在搜索前用 Flash 快速评估 KB 覆盖度，决定用什么模型：

```python
def _assess_kb_coverage(query: str) -> float:
    """评估 KB 对某个 query 的已有覆盖度 (0.0-1.0)"""
    from src.tools.knowledge_base import search_knowledge
    results = search_knowledge(query, limit=10)
    if not results:
        return 0.0
    # 粗估：有 5+ 条高 confidence 结果 = 高覆盖
    high_conf = sum(1 for r in results if r.get("confidence") in ("high", "authoritative"))
    return min(1.0, (len(results) * 0.1) + (high_conf * 0.15))


def _select_model_by_coverage(query: str, default_model: str) -> str:
    """根据 KB 覆盖度选择模型——覆盖度低用强模型，覆盖度高用便宜模型"""
    coverage = _assess_kb_coverage(query)
    if coverage > 0.7:
        print(f"  [Budget] KB 覆盖度 {coverage:.0%}，用 Flash 补充")
        return "gemini_2_5_flash"
    elif coverage > 0.4:
        print(f"  [Budget] KB 覆盖度 {coverage:.0%}，用默认模型")
        return default_model
    else:
        print(f"  [Budget] KB 覆盖度 {coverage:.0%}，用最强模型深搜")
        return "o3_deep_research"
```

在 Layer 1 搜索分配模型时调用此函数。

commit: `"feat: budget-aware model routing — select model by information marginal value"`

---

## A-12: N1 反脆弱运行

在 `_call_with_backoff()` 的全部重试失败后，不抛异常，而是切换到离线任务：

```python
def _fallback_to_offline_tasks(failed_model: str, failed_query: str):
    """API 全部失败时切换到离线任务"""
    print(f"  [AntiFragile] {failed_model} 全部失败，切换离线任务")

    offline_tasks = [
        ("KB治理", lambda: _run_kb_governance_lite()),
        ("知识综述", lambda: _generate_knowledge_synthesis_offline()),
        ("决策树扫描", lambda: _scan_decision_readiness()),
        ("工作记忆整理", lambda: _organize_work_memory()),
    ]

    for name, task_fn in offline_tasks:
        try:
            print(f"  [AntiFragile] 执行离线任务: {name}")
            task_fn()
        except:
            pass
```

commit: `"feat: anti-fragile operation — auto-switch to offline tasks when APIs fail"`

---

## 最终总提交数: 12 个 commit

---

## A-13: O3 对抗性数据验证

在 Layer 2 提炼 prompt 末尾追加对抗性提问指引：

```
对每个关键数据点（价格、产能、良率、功耗等数值），追加以下字段：
"data_caveat": {
    "price_basis": "含税/不含税/未知",
    "volume_basis": "样品/千片/万片/未知",
    "time_basis": "2024/2025/2026/未知",
    "source_type": "官方datasheet/新闻报道/分析师估算/论坛帖子/未知",
    "needs_clarification": true/false
}
如果以上任何字段为"未知"，则 needs_clarification 必须为 true。
```

KB 入库时，如果 `needs_clarification=true`，标记到条目的 tags 中。KB 治理时汇总所有 needs_clarification 条目推送飞书提醒。

commit: `"feat: adversarial data validation — challenge every data point's basis and scope"`

---

## A-14: O4 沙盘 What-If 模式

新增沙盘推演函数（在 deep_research 模块或独立脚本中）：

```python
def sandbox_what_if(parameter_change: str, gateway, kb_context: str = "") -> str:
    """沙盘推演：调整一个参数，推算连锁影响"""
    prompt = (
        f"产品: 智能骑行头盔 V1\n"
        f"参数变更: {parameter_change}\n\n"
        f"已知产品参数和约束:\n{kb_context[:3000]}\n\n"
        f"请推演这个变更的连锁影响链条。每一步标注:\n"
        f"1. 直接影响（确定性高）\n"
        f"2. 间接影响（确定性中）\n"
        f"3. 远端影响（确定性低）\n\n"
        f"对每个影响给出具体数值估算（如有数据支撑）或定性判断。\n"
        f"最终给出：这个变更是否值得做？代价是什么？"
    )
    result = gateway.call("gpt_5_4", prompt,
        "你是系统工程师，擅长因果链条推理。每一步必须有依据。", "sandbox")
    return result.get("response", "") if result.get("success") else "推演失败"
```

commit: `"feat: sandbox what-if mode — parameter change cascade impact analysis"`

---

## 最终总提交数: 14 个 commit

---

## A-15: P4 竞品界面素材库

在 Layer 1 搜索结果处理中，检测到竞品界面截图的 URL 时，自动保存到 `.ai-state/competitive_ui/`。CC 自行实现 URL 检测和图片下载逻辑。

commit: `"feat: competitive UI asset library — auto-collect competitor interface screenshots"`

## A-16: Q2 数值计算引擎

在 Agent prompt 中注入规则："涉及数值计算（BOM、续航、成本对比、功耗汇总）时，输出 Python 计算公式而非直接给结果。格式：`[CALC: expression]`"。

在 Layer 4 synthesis 后，扫描输出中的 `[CALC: ...]` 标记，用 Python eval 执行并回填结果。

commit: `"feat: numeric calculation engine — Python-computed numbers replace LLM guesswork"`

## A-17: Q3 推理链可见化

Layer 4 synthesis prompt 追加：
```
请在结论之前展示推理过程：
- 数据来源 → 推论 → 结论
- 如果多个数据指向不同结论，说明为什么选择了这个结论
```

commit: `"feat: visible reasoning chain — show why, not just what"`

## A-18: Q5 系统自评分

深度学习结束后自动评估本次产出质量。CC 自行实现评分维度（搜索召回率、提炼质量、Agent 深度、Critic 精度）和趋势对比。

commit: `"feat: system self-assessment — auto-evaluate output quality and suggest improvements"`

---

## 最终总提交数: 18 个 commit

---

## A-19: Grok 作为第三搜索通道

Layer 1 搜索从"双通道"升级为"三通道"并行：

```
o3-deep-research → 英文技术/专利/学术
doubao-seed-pro  → 中文互联网（小红书/B站/知乎）
grok-4           → 社交媒体/实时动态/X-Twitter（新增）
tavily           → fallback
```

在搜索分配逻辑中，为每个 query 同时发给三个通道。Grok 特别适合：
- 竞品动态（"Cardo latest product 2026"）
- 用户声音（"motorcycle helmet HUD review"）  
- 行业新闻（"smart helmet startup funding"）
- KOL 评价（"骑行头盔推荐"）

实现：在 `_search_one_query()` 或等效位置，除了 o3 和 doubao，新增 grok 并发搜索：

```python
# Grok 搜索（社交媒体+实时动态）
grok_future = executor.submit(
    _call_with_backoff, "grok_4", 
    f"Search for the latest information about: {query}. "
    f"Focus on social media discussions, recent news, and real-time updates.",
    task_type="deep_research_search"
)
```

降级映射表新增：
```python
FALLBACK_MAP["grok_4"] = "gpt_4o_norway"  # Grok 失败降级到 gpt-4o
```

并发信号量新增：
```python
PROVIDER_SEMAPHORES["grok"] = threading.Semaphore(3)  # Grok 3 并发
```

commit: `"feat: Grok as third search channel — social media and real-time intelligence"`

---

## 最终最终总提交数: 19 个 commit
