# 自进化引擎 v1 — 自测闭环 + 知识引用追踪 + 自动深挖

> 本次落地：闭环 1（知识质量）+ 闭环 2（任务质量）的核心部分
> 嵌入位置：daily_learning.py + overnight_deep_learning_v3.py + knowledge_base.py + router.py

---

## 一、知识引用追踪（闭环 1 基础设施）

每次知识库被检索命中时，给条目 +1 引用计数。30 天内零引用的条目标记为"待审视"。

### 1.1 修改 knowledge_base.py

在 search_knowledge 函数中，每次返回结果后给命中条目增加引用计数：

```python
def _track_knowledge_usage(file_path: Path):
    """追踪知识条目被引用次数"""
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        
        # 增加引用计数
        data["_usage_count"] = data.get("_usage_count", 0) + 1
        data["_last_used"] = datetime.now().isoformat()
        
        # 首次被引用时记录
        if "_first_used" not in data:
            data["_first_used"] = datetime.now().isoformat()
        
        file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except:
        pass
```

在 search_knowledge 的返回结果处调用：

```python
    # 在返回搜索结果前，追踪引用
    for entry in results[:limit]:
        if hasattr(entry, '_file_path'):
            _track_knowledge_usage(entry._file_path)
        # 或者如果结果中包含文件路径
        elif entry.get("_path"):
            _track_knowledge_usage(Path(entry["_path"]))
```

### 1.2 定期审计零引用条目

在 daily_learning.py 的对齐报告生成中，添加零引用审计：

```python
def _audit_unused_knowledge():
    """审计 30 天内零引用的条目"""
    from datetime import timedelta
    
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    unused = []
    total = 0
    
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            total += 1
            
            usage = data.get("_usage_count", 0)
            created = data.get("_created", data.get("timestamp", ""))
            
            # 创建超过 7 天但零引用
            if usage == 0 and created and created < cutoff:
                unused.append({
                    "title": data.get("title", ""),
                    "domain": data.get("domain", ""),
                    "created": created[:10],
                    "path": str(f)
                })
        except:
            continue
    
    return {
        "total": total,
        "unused_count": len(unused),
        "unused_ratio": round(len(unused) / total * 100, 1) if total > 0 else 0,
        "unused_sample": unused[:10]  # 前 10 条示例
    }
```

---

## 二、自测闭环（闭环 1 核心）

学完后自动出题 → 自动答题 → 自动评分 → 发现薄弱点 → 自动深挖

### 2.1 创建 scripts/self_test.py

```python
"""
@description: 知识库自测引擎 - 出题→答题→评分→发现薄弱→触发深挖
"""
import json
import re
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.model_gateway import get_model_gateway
from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt, KB_ROOT


def generate_test_questions(topics: list, gateway, count=10) -> list:
    """基于最近学习的主题生成测试题"""
    
    titles = [t if isinstance(t, str) else t.get("title", "") for t in topics[:30]]
    
    prompt = (
        f"以下是智能摩托车全盔项目最近学习的知识主题：\n"
        + "\n".join(f"- {t}" for t in titles) + "\n\n"
        f"请生成 {count} 个测试题，用于验证知识库是否真正掌握了有用信息。\n\n"
        f"要求：\n"
        f"1. 每题必须需要具体数据才能回答（型号、参数、价格、数量、时间）\n"
        f"2. 不要问定义类问题（'什么是 XX'），要问对比/选型/决策类问题\n"
        f"3. 覆盖不同领域（硬件/认证/成本/用户/竞品）\n"
        f"4. 难度：专业产品经理或工程师日常会问的问题\n\n"
        f"输出 JSON 数组，每个元素：\n"
        f'{{"question":"问题","domain":"所属领域","expected_data":"期望回答中包含的数据类型"}}\n\n'
        f"只输出 JSON。"
    )
    
    result = gateway.call_azure_openai("cpo", prompt,
        "生成专业测试题。只输出JSON。", "self_test_gen")
    
    if result.get("success"):
        match = re.search(r'\[[\s\S]*\]', result["response"])
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
    return []


def answer_question_from_kb(question: str, gateway) -> dict:
    """用知识库回答问题，并评估回答质量"""
    
    # 搜索知识库
    kb_entries = search_knowledge(question, limit=8)
    kb_context = format_knowledge_for_prompt(kb_entries) if kb_entries else ""
    
    if not kb_context or len(kb_context) < 100:
        return {
            "answer": "",
            "kb_hit": False,
            "score": 0,
            "reason": "知识库无相关内容"
        }
    
    # 用知识库回答
    answer_prompt = (
        f"基于以下知识库内容回答问题。\n"
        f"必须引用具体数据（型号、参数、价格）。\n"
        f"如果知识库中没有相关数据，明确说'知识库中未找到相关数据'。\n"
        f"不要编造数据。\n\n"
        f"知识库内容：\n{kb_context[:4000]}\n\n"
        f"问题：{question}\n\n"
        f"回答（300字以内）："
    )
    
    result = gateway.call_azure_openai("cpo", answer_prompt,
        "基于知识库回答，引用具体数据。", "self_test_answer")
    
    answer = result.get("response", "") if result.get("success") else ""
    
    # 评分
    score, reason = _score_answer(answer, question)
    
    return {
        "answer": answer[:500],
        "kb_hit": len(kb_context) > 200,
        "score": score,
        "reason": reason
    }


def _score_answer(answer: str, question: str) -> tuple:
    """评分：0-10 分"""
    
    if not answer or len(answer) < 50:
        return 0, "无有效回答"
    
    if "未找到" in answer or "没有相关" in answer or "暂无" in answer:
        return 1, "知识库缺失"
    
    # 检查是否有具体数据
    has_number = bool(re.search(r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|\$|%|nits|GHz|MB)', answer))
    has_model = bool(re.search(r'[A-Z]{2,}\d{2,}|IMX\d|QCC\d|BES\d', answer))
    has_brand = bool(re.search(r'(歌尔|索尼|高通|Qualcomm|Sony|Bosch|Sena|Cardo|Forcite)', answer))
    has_comparison = bool(re.search(r'(vs|对比|相比|优于|劣于|高于|低于)', answer))
    
    score = 3  # 基础分（有回答）
    if has_number:
        score += 2
    if has_model:
        score += 2
    if has_brand:
        score += 1
    if has_comparison:
        score += 1
    if len(answer) > 200:
        score += 1
    
    score = min(score, 10)
    
    reasons = []
    if not has_number:
        reasons.append("缺具体数字")
    if not has_model:
        reasons.append("缺型号")
    if not has_brand:
        reasons.append("缺品牌名")
    
    reason = "、".join(reasons) if reasons else "数据充分"
    return score, reason


def run_self_test(topics=None, count=10, notify_func=None) -> dict:
    """执行一轮自测，返回结果和薄弱领域"""
    
    gateway = get_model_gateway()
    
    # 如果没给主题，从知识库最近条目中提取
    if not topics:
        recent = []
        for f in sorted(KB_ROOT.rglob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:30]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                recent.append(data.get("title", ""))
            except:
                continue
        topics = recent
    
    print(f"\n[SelfTest] 生成 {count} 道测试题...")
    questions = generate_test_questions(topics, gateway, count)
    
    if not questions:
        print("[SelfTest] 生成测试题失败")
        return {"score": 0, "weak_areas": [], "questions": []}
    
    print(f"[SelfTest] 开始答题（{len(questions)} 题）...")
    results = []
    total_score = 0
    weak_areas = []
    
    for i, q in enumerate(questions, 1):
        question = q.get("question", "")
        domain = q.get("domain", "")
        
        answer_result = answer_question_from_kb(question, gateway)
        score = answer_result["score"]
        total_score += score
        
        icon = "✅" if score >= 7 else "⚠️" if score >= 4 else "❌"
        print(f"  {icon} [{i}/{len(questions)}] {score}/10 | {question[:50]}... — {answer_result['reason']}")
        
        results.append({
            "question": question,
            "domain": domain,
            "score": score,
            "reason": answer_result["reason"],
            "answer_preview": answer_result["answer"][:200]
        })
        
        # 低分题目 → 薄弱领域
        if score < 5:
            weak_areas.append({
                "question": question,
                "domain": domain,
                "score": score,
                "reason": answer_result["reason"],
                "suggested_searches": [
                    f"{question} 具体数据 参数 型号",
                    f"{domain} specifications comparison 2025 2026",
                ]
            })
    
    avg_score = round(total_score / len(questions), 1) if questions else 0
    pass_rate = round(sum(1 for r in results if r["score"] >= 7) / len(results) * 100, 1) if results else 0
    
    summary = (
        f"\n[SelfTest] 自测完成\n"
        f"  平均分: {avg_score}/10\n"
        f"  及格率(≥7分): {pass_rate}%\n"
        f"  薄弱领域: {len(weak_areas)} 个\n"
    )
    print(summary)
    
    if notify_func:
        try:
            notify_func(
                f"📝 知识库自测完成\n"
                f"平均分: {avg_score}/10 | 及格率: {pass_rate}%\n"
                f"薄弱领域: {len(weak_areas)} 个"
            )
        except:
            pass
    
    # 保存自测报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "avg_score": avg_score,
        "pass_rate": pass_rate,
        "total_questions": len(questions),
        "weak_count": len(weak_areas),
        "results": results,
        "weak_areas": weak_areas
    }
    
    report_dir = Path(__file__).parent.parent / ".ai-state" / "self_tests"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"test_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    
    return {
        "avg_score": avg_score,
        "pass_rate": pass_rate,
        "weak_areas": weak_areas,
        "results": results
    }


def auto_deep_dive_weak_areas(weak_areas: list, notify_func=None) -> dict:
    """自动深挖薄弱领域"""
    if not weak_areas:
        print("[AutoDeepDive] 无薄弱领域需要深挖")
        return {"added": 0}
    
    from src.tools.tool_registry import get_tool_registry
    gateway = get_model_gateway()
    registry = get_tool_registry()
    
    added = 0
    
    for i, weak in enumerate(weak_areas, 1):
        question = weak["question"]
        domain = weak.get("domain", "components")
        searches = weak.get("suggested_searches", [question])
        
        print(f"\n[AutoDeepDive] [{i}/{len(weak_areas)}] 深挖: {question[:50]}...")
        
        # 多轮搜索
        search_data = ""
        for q in searches[:3]:
            result = registry.call("deep_research", q)
            if result.get("success") and len(result.get("data", "")) > 200:
                search_data += f"\n---\n{result['data'][:3000]}"
        
        if len(search_data) < 500:
            print(f"  ⏭️ 搜索不足，跳过")
            continue
        
        # 提炼（针对性回答原始问题）
        refine_prompt = (
            f"以下搜索结果是为了回答这个问题：\n{question}\n\n"
            f"请基于搜索结果输出一条详细的知识条目。\n"
            f"必须包含具体数据（型号、参数、价格、品牌名）。\n"
            f"如果搜不到，标注'未查到'。\n"
            f"输出 800-1500 字。\n\n"
            f"搜索结果：\n{search_data[:6000]}"
        )
        
        result = gateway.call_azure_openai("cpo", refine_prompt,
            "输出有数据支撑的知识条目。", "auto_deep_dive")
        
        if result.get("success") and len(result.get("response", "")) > 300:
            from src.tools.knowledge_base import add_knowledge
            add_knowledge(
                title=f"[自测深挖] {question[:60]}",
                domain=domain,
                content=result["response"][:2000],
                tags=["self_test_dive", "auto_evolution"],
                source="self_test_auto_dive",
                confidence="high"
            )
            added += 1
            print(f"  ✅ 入库成功 ({len(result['response'])}字)")
        else:
            print(f"  ❌ 提炼失败")
    
    print(f"\n[AutoDeepDive] 完成: 深挖 {len(weak_areas)} 个，入库 {added} 个")
    
    if notify_func:
        try:
            notify_func(f"🔬 自动深挖完成: {added}/{len(weak_areas)} 个薄弱领域已补强")
        except:
            pass
    
    return {"added": added}
```

---

## 三、嵌入 daily_learning.py

在每轮学习完成后自动触发自测：

```python
# 在 daily_learning.py 的学习轮次结束后添加：

    # === 自测闭环：每 3 轮学习后做一次自测 ===
    # 用一个计数器追踪轮次
    _learn_round_count = getattr(sys.modules[__name__], '_learn_round_count', 0) + 1
    sys.modules[__name__]._learn_round_count = _learn_round_count
    
    if _learn_round_count % 3 == 0:  # 每 3 轮（约 1.5 小时）自测一次
        try:
            from scripts.self_test import run_self_test, auto_deep_dive_weak_areas
            
            print("\n[SelfTest] 触发定期自测...")
            test_result = run_self_test(count=5)  # 快速测 5 题
            
            # 如果平均分低于 6，自动深挖
            if test_result["avg_score"] < 6 and test_result["weak_areas"]:
                print(f"[SelfTest] 平均分 {test_result['avg_score']}/10，自动深挖薄弱领域...")
                auto_deep_dive_weak_areas(test_result["weak_areas"][:3])  # 最多深挖 3 个
            else:
                print(f"[SelfTest] 平均分 {test_result['avg_score']}/10，暂不需要深挖")
        except Exception as e:
            print(f"[SelfTest] 自测异常: {e}")
```

---

## 四、嵌入 overnight_deep_learning_v3.py

Phase A 结束后自测，然后基于自测结果决定 Phase B 深挖什么：

```python
# 在 run_all() 中，Phase A 完成后：

    # Phase A 完成后自测
    from scripts.self_test import run_self_test
    
    log("Phase A+: 广度扫盲后自测...", notify_func)
    test_result = run_self_test(
        topics=[t["title"] for t in topics],
        count=15  # 夜间可以多测几题
    )
    
    log(f"自测结果: 平均 {test_result['avg_score']}/10, "
        f"及格率 {test_result['pass_rate']}%, "
        f"薄弱 {len(test_result['weak_areas'])} 个", notify_func)
    
    # 基于自测结果 + 广度结果 联合决定深挖主题
    # 自测薄弱领域自动加入深挖队列
    for weak in test_result.get("weak_areas", []):
        # 构造一个 topic 格式
        weak_topic = {
            "title": weak["question"][:80],
            "domain": weak.get("domain", "components"),
            "searches": weak.get("suggested_searches", []),
            "tags": ["self_test_weak"]
        }
        # 如果不在已选主题中，追加
        existing_titles = {s["topic"]["title"] for s in selected}
        if weak_topic["title"] not in existing_titles:
            selected.append({
                "topic": weak_topic,
                "score": 15,  # 自测薄弱 = 最高优先深挖
                "reason": f"自测 {weak['score']}/10: {weak['reason']}"
            })
    
    # 重新排序，自测薄弱排最前
    selected.sort(key=lambda x: -x["score"])
    selected = selected[:deep_count]  # 截断到目标数量
```

---

## 五、任务质量自动分析（闭环 2）

当前用户打 D 评价后只是存了经验卡片。升级为自动归因+自动修正。

在 feishu_sdk_client.py 的评价处理逻辑中（搜 "D" 评价处理的位置），升级分析逻辑：

```python
# 原来的 D 评价处理可能只是简单保存。改为：

    if rating == "D":
        # 自动归因分析
        analysis_prompt = (
            f"一个研发任务收到了用户差评(D)。请分析失败根因并归类。\n\n"
            f"用户需求：{task_goal[:500]}\n\n"
            f"系统输出（摘要）：{task_output[:1000]}\n\n"
            f"请从以下维度归因（可多选）：\n"
            f"1. KNOWLEDGE_GAP: 知识库缺乏相关数据\n"
            f"2. FORMAT_WRONG: 输出格式不符合用户要求\n"
            f"3. GOAL_MISALIGN: 没有对齐用户目标\n"
            f"4. SPECULATIVE: 输出了太多推测内容\n"
            f"5. INCOMPLETE: 遗漏了用户明确要求的内容\n"
            f"6. TOO_VERBOSE: 输出太冗长，不够精炼\n"
            f"7. WRONG_ROUTE: 用了错误的处理路径（如该走快速通道走了多Agent）\n\n"
            f"输出 JSON：{{'causes':['原因1','原因2'],'fix_actions':['建议修复1','建议修复2'],'knowledge_gaps':['需要补充的知识1']}}\n"
            f"只输出 JSON。"
        )
        
        # 分析
        analysis = gateway.call_azure_openai("cpo", analysis_prompt, 
            "分析失败原因。只输出JSON。", "failure_analysis")
        
        if analysis.get("success"):
            try:
                result = json.loads(re.search(r'\{[\s\S]*\}', analysis["response"]).group())
                
                causes = result.get("causes", [])
                knowledge_gaps = result.get("knowledge_gaps", [])
                
                print(f"[Evolution] D评价归因: {causes}")
                
                # 如果是知识缺口，自动触发深挖
                if "KNOWLEDGE_GAP" in causes and knowledge_gaps:
                    from scripts.self_test import auto_deep_dive_weak_areas
                    weak = [{"question": g, "domain": "components", 
                             "suggested_searches": [g]} for g in knowledge_gaps[:3]]
                    auto_deep_dive_weak_areas(weak)
                
                # 保存归因结果供后续分析趋势
                evolution_dir = Path(__file__).parent.parent / ".ai-state" / "evolution"
                evolution_dir.mkdir(parents=True, exist_ok=True)
                (evolution_dir / f"d_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json").write_text(
                    json.dumps({"task": task_goal[:200], "causes": causes, 
                               "fixes": result.get("fix_actions", []),
                               "gaps": knowledge_gaps}, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
            except:
                pass
```

---

## 六、验证

```bash
# 1. 确认自测模块可导入
python -c "from scripts.self_test import run_self_test, auto_deep_dive_weak_areas; print('OK')"

# 2. 快速自测（3 题）
python -c "
from scripts.self_test import run_self_test
result = run_self_test(count=3)
print(f'平均分: {result[\"avg_score\"]}/10')
print(f'薄弱: {len(result[\"weak_areas\"])} 个')
"

# 3. 确认知识引用追踪
python -c "
from src.tools.knowledge_base import search_knowledge
results = search_knowledge('HUD 导航 转向箭头', limit=3)
print(f'搜索到 {len(results)} 条')
# 检查是否有 _usage_count
"
```

---

## 七、Week 3 进化路线（本次不做，记入 plan）

| 闭环 | 能力 | 安排 |
|------|------|------|
| 闭环 3 | 能力成熟度评分（按任务类型统计 A/B/C/D 趋势） | Week 3 Day 1 |
| 闭环 4 | 用户兴趣追踪（近 7 天高频关键词 → 调整学习方向）| Week 3 Day 2 |
| 闭环 4 | 行业动态监测（每日扫竞品新闻 → 自动入库）| Week 3 Day 3 |
| 闭环 5 | 每日健康报告（API 失败率/知识增长/满意度趋势）| Week 3 Day 1 |
| 进阶 | prompt 自优化（基于 D 评价归因自动调 prompt）| Week 3 Day 4 |
| 进阶 | 知识过时淘汰（6 个月零引用 + 无更新 → 标记过时）| Week 3 Day 5 |
