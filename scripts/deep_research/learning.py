"""
深度研究 — 学习与知识层
职责: 搜索学习(W1)、Agent教训(W2)、模型效果(W3)、跨任务发现(A3)、报告摘要(A4)、
      好奇心(A5)、经验法则(A6)、趋势预测(A7)、压力测试(A8)、知识综述(A9)、
      类比推理(A10)、覆盖度路由(A11)、反脆弱(A12)、竞品UI(A15)、
      计算引擎(Q2)、推理链(Q3)、自评分(Q5)、KB增强、专家框架、Demo准备
被调用方: pipeline.py, runner.py, critic.py
依赖: models.py
"""
import ast
import json
import operator
import re
import time
import yaml
from pathlib import Path

from src.tools.knowledge_base import add_knowledge, get_knowledge_stats, KB_ROOT
from scripts.deep_research.models import (
    call_model, call_with_backoff, get_model_for_task, get_model_for_role,
    set_learned_model_fn, gateway
)

AI_STATE = Path(__file__).resolve().parent.parent.parent / ".ai-state"


# ============================================================
# W1: 搜索策略学习
# ============================================================
SEARCH_LEARNING_PATH = AI_STATE / "search_learning.jsonl"
SEARCH_BEST_PRACTICES_PATH = AI_STATE / "search_best_practices.yaml"


def record_search_result(query: str, model: str, tokens: int,
                         useful_findings: int, quality: str):
    entry = {
        "query": query, "model": model, "tokens": tokens,
        "useful_findings": useful_findings, "quality": quality,
        "timestamp": time.strftime('%Y-%m-%d %H:%M')
    }
    SEARCH_LEARNING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SEARCH_LEARNING_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def evolve_search_strategy():
    if not SEARCH_LEARNING_PATH.exists():
        return
    lines = SEARCH_LEARNING_PATH.read_text(encoding='utf-8').strip().split('\n')[-50:]
    if len(lines) < 10:
        return

    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except:
            continue

    quality_map = {"high": 3, "medium": 2, "low": 1}
    model_stats = {}
    keyword_patterns = {"price": [], "技术": [], "2024": [], "2025": [], "2026": []}

    for r in records:
        model = r.get("model", "")
        quality = quality_map.get(r.get("quality", "low"), 1)
        if model not in model_stats:
            model_stats[model] = {"total": 0, "score": 0}
        model_stats[model]["total"] += 1
        model_stats[model]["score"] += quality

        query = r.get("query", "").lower()
        for kw in keyword_patterns:
            if kw in query:
                keyword_patterns[kw].append(quality)

    best_practices = {
        "model_ranking": sorted(model_stats.items(),
                                key=lambda x: x[1]["score"] / x[1]["total"],
                                reverse=True)[:3],
        "keyword_effectiveness": {k: sum(v) / len(v) if v else 0
                                  for k, v in keyword_patterns.items()},
        "updated_at": time.strftime('%Y-%m-%d %H:%M')
    }
    with open(SEARCH_BEST_PRACTICES_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(best_practices, f, allow_unicode=True)
    print(f"  [SearchLearning] 更新搜索最佳实践")


def get_optimized_search_model(query: str) -> str:
    if not SEARCH_BEST_PRACTICES_PATH.exists():
        return "o3_deep_research"
    try:
        with open(SEARCH_BEST_PRACTICES_PATH, 'r', encoding='utf-8') as f:
            practices = yaml.safe_load(f)
        model_ranking = practices.get("model_ranking", [])
        if model_ranking:
            return model_ranking[0][0]
    except:
        pass
    return "o3_deep_research"


# ============================================================
# W2: Agent prompt 自进化
# ============================================================
AGENT_LESSONS_PATH = AI_STATE / "agent_lessons.yaml"


def learn_from_p0(agent_role: str, p0_issue: str, cal_id: str = ""):
    if not AGENT_LESSONS_PATH.exists():
        lessons = {}
    else:
        try:
            with open(AGENT_LESSONS_PATH, 'r', encoding='utf-8') as f:
                lessons = yaml.safe_load(f) or {}
        except:
            lessons = {}

    if agent_role not in lessons:
        lessons[agent_role] = []

    lesson = f"{p0_issue[:100]}（来源: P0 {cal_id}）"
    if lesson not in lessons[agent_role]:
        lessons[agent_role].append(lesson)
        with open(AGENT_LESSONS_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(lessons, f, allow_unicode=True)
        print(f"  [AgentLesson] {agent_role} 新增教训: {p0_issue[:50]}...")


def get_agent_prompt_with_lessons(role: str, base_prompt: str) -> str:
    if not AGENT_LESSONS_PATH.exists():
        return base_prompt
    try:
        with open(AGENT_LESSONS_PATH, 'r', encoding='utf-8') as f:
            lessons = yaml.safe_load(f) or {}
        role_lessons = lessons.get(role.upper(), [])
        if role_lessons:
            base_prompt += "\n\n## 从历史错误中学到的注意事项\n"
            for lesson in role_lessons[-5:]:
                base_prompt += f"- {lesson}\n"
    except:
        pass
    return base_prompt


# ============================================================
# W3: 模型效果学习
# ============================================================
MODEL_EFFECTIVENESS_PATH = AI_STATE / "model_effectiveness.jsonl"


def record_model_effectiveness(model: str, task_type: str, quality_score: int):
    entry = {
        "model": model, "task_type": task_type,
        "quality_score": quality_score,
        "timestamp": time.strftime('%Y-%m-%d %H:%M')
    }
    MODEL_EFFECTIVENESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_EFFECTIVENESS_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def select_best_model_learned(task_type: str) -> str:
    """基于历史效果选择最佳模型 — 注册到 models.py 的回调"""
    if not MODEL_EFFECTIVENESS_PATH.exists():
        return None
    lines = MODEL_EFFECTIVENESS_PATH.read_text(encoding='utf-8').strip().split('\n')
    if len(lines) < 10:
        return None

    model_scores = {}
    for line in lines:
        try:
            entry = json.loads(line)
            if entry.get("task_type") == task_type:
                model = entry.get("model")
                score = entry.get("quality_score", 5)
                if model not in model_scores:
                    model_scores[model] = {"total": 0, "sum": 0}
                model_scores[model]["total"] += 1
                model_scores[model]["sum"] += score
        except:
            continue

    if not model_scores:
        return None

    best = max(model_scores.items(), key=lambda x: x[1]["sum"] / x[1]["total"])
    if best[1]["total"] >= 5:
        print(f"  [ModelLearn] {task_type} 最佳模型: {best[0]} "
              f"(平均 {best[1]['sum'] / best[1]['total']:.1f}分)")
        return best[0]
    return None


# 注册 W3 回调到 models.py
set_learned_model_fn(select_best_model_learned)


# ============================================================
# A-3: 跨任务知识传递
# ============================================================
FINDINGS_PATH = AI_STATE / "task_findings.jsonl"


def save_task_findings(task_title: str, report: str):
    result = call_model("gemini_2_5_flash",
        f"从以下研究报告中提取 3-5 个最关键的发现（具体数据点）:\n\n"
        f"{report[:3000]}\n\n"
        f"输出 JSON 数组: [{{\"finding\": \"具体发现\", \"keywords\": [\"关键词1\", \"关键词2\"]}}]",
        task_type="knowledge_extract")
    if result.get("success"):
        try:
            findings = json.loads(re.sub(r'^```json\s*|\s*```$', '', result["response"].strip()))
            entry = {"task_title": task_title, "timestamp": time.strftime('%Y-%m-%d %H:%M'),
                     "findings": findings}
            FINDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(FINDINGS_PATH, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            print(f"  [Findings] 保存 {len(findings)} 个关键发现")
        except:
            pass


def get_related_findings(task_title: str, task_goal: str, limit: int = 5) -> str:
    if not FINDINGS_PATH.exists():
        return ""
    keywords = set(re.findall(r'[\u4e00-\u9fff]{2,4}|[A-Z][a-z]+|[A-Z]{2,}',
                              task_title + " " + task_goal))
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


# ============================================================
# A-4: 报告摘要层
# ============================================================
def generate_report_summary(report: str, task_title: str) -> dict:
    result = call_model("gemini_2_5_flash",
        f"为以下研究报告生成 3 句话摘要:\n"
        f"第 1 句: 核心发现\n第 2 句: 关键数据点\n第 3 句: 对产品决策的影响\n\n"
        f"报告标题: {task_title}\n报告内容:\n{report[:3000]}\n\n"
        f"输出 JSON: {{\"core_finding\": \"...\", \"key_data\": \"...\", \"decision_impact\": \"...\"}}",
        task_type="knowledge_extract")
    if result.get("success"):
        try:
            return json.loads(re.sub(r'^```json\s*|\s*```$', '', result["response"].strip()))
        except:
            pass
    return {}


# ============================================================
# A-5: 好奇心驱动
# ============================================================
def process_serendipity(structured_data_list: list, task_pool_save_fn=None):
    serendipities = []
    for data in structured_data_list:
        if isinstance(data, dict):
            for s in data.get("serendipity", []):
                serendipities.append(s)
    if not serendipities:
        return

    print(f"  [Curiosity] 发现 {len(serendipities)} 个意外线索")

    new_tasks = []
    for s in serendipities[:3]:
        new_tasks.append({
            "id": f"curiosity_{int(time.time())}",
            "title": f"[好奇心] {s.get('finding', '')[:40]}",
            "goal": f"深入调查意外发现: {s.get('finding', '')}。潜在价值: {s.get('potential_value', '')}",
            "priority": 3,
            "source": "serendipity",
            "discovered_at": time.strftime('%Y-%m-%d %H:%M'),
            "searches": [s.get("finding", "")[:50]],
        })
        print(f"  [Curiosity] 追加任务: {new_tasks[-1]['title']}")
    return new_tasks


# ============================================================
# A-6: 经验法则提取
# ============================================================
def extract_experience_rules():
    groups = {}
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            title = data.get("title", "")
            for entity in ["歌尔", "立讯", "Cardo", "Sena", "JBD", "Sony", "OLED", "MicroLED"]:
                if entity.lower() in title.lower():
                    if entity not in groups:
                        groups[entity] = []
                    groups[entity].append(data)
        except:
            continue

    rules_found = 0
    for entity, entries in groups.items():
        if len(entries) < 5:
            continue
        entries_text = "\n".join([f"- {e.get('title', '')}: {e.get('content', '')[:200]}"
                                 for e in entries[:10]])
        result = call_model("gemini_2_5_flash",
            f"以下是关于 {entity} 的 {len(entries)} 条知识库条目:\n\n{entries_text}\n\n"
            f"从中提取可复用的经验法则或模式。\n"
            f"如果数据不足，输出'数据不足'。\n"
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
                        source="pattern_extraction", confidence="medium")
                    rules_found += 1
            except:
                pass
    print(f"  [Rules] 提取 {rules_found} 条经验法则")


# ============================================================
# A-7: 趋势预测
# ============================================================
PREDICTIONS_PATH = AI_STATE / "predictions.jsonl"


def generate_trend_predictions():
    time_series_data = {}
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            content = data.get("content", "")
            title = data.get("title", "")
            year_matches = re.findall(r'(20\d{2})', content)
            number_matches = re.findall(
                r'(\d+\.?\d*)\s*(美元|元|USD|\$|mm|g|mAh|W|V|%)', content)
            if year_matches and number_matches:
                for year, (value, unit) in zip(year_matches, number_matches):
                    key = f"{title[:30]}_{unit}"
                    if key not in time_series_data:
                        time_series_data[key] = []
                    time_series_data[key].append({"year": year, "value": float(value)})
        except:
            continue

    predictions = []
    for key, points in time_series_data.items():
        if len(points) < 3:
            continue
        points.sort(key=lambda x: x["year"])
        years = [int(p["year"]) for p in points]
        values = [p["value"] for p in points]
        if len(set(years)) < 2:
            continue
        n = len(years)
        sum_x = sum(years)
        sum_y = sum(values)
        sum_xy = sum(x * y for x, y in zip(years, values))
        sum_xx = sum(x * x for x in years)
        denom = n * sum_xx - sum_x * sum_x
        slope = (n * sum_xy - sum_x * sum_y) / denom if denom != 0 else 0
        intercept = (sum_y - slope * sum_x) / n
        next_year = max(years) + 1
        predicted_value = slope * next_year + intercept
        predictions.append({
            "topic": key, "historical": points,
            "prediction_12m": round(predicted_value, 2),
            "trend": "increasing" if slope > 0 else "decreasing",
            "confidence": "low"
        })

    if predictions:
        with open(PREDICTIONS_PATH, 'a', encoding='utf-8') as f:
            for pred in predictions:
                pred["timestamp"] = time.strftime('%Y-%m-%d %H:%M')
                f.write(json.dumps(pred, ensure_ascii=False) + "\n")
        print(f"  [Trends] 生成 {len(predictions)} 个趋势预测")


# ============================================================
# A-8: 压力测试
# ============================================================
def stress_test_product(plan_description: str = "", progress_callback=None) -> str:
    scenarios_prompt = (
        f"你是产品风险分析师。针对以下产品方案，生成 15-20 个极端场景:\n\n"
        f"{plan_description[:2000]}\n\n"
        f"场景类型: 环境极端、使用极端、技术故障、用户极端、供应链中断\n\n"
        f"输出 JSON 数组: [{{\"scenario\": \"场景描述\", \"impact\": \"高/中/低\"}}]"
    )
    result = call_model("gpt_5_4", scenarios_prompt, "只输出 JSON 数组。", "stress_test")
    if not result.get("success"):
        return "压力测试失败"

    try:
        scenarios = json.loads(re.sub(r'^```json\s*|\s*```$', '', result["response"].strip()))
    except:
        return "场景解析失败"

    test_results = []
    for scenario in scenarios[:15]:
        check_prompt = (
            f"产品方案:\n{plan_description[:1500]}\n\n"
            f"极端场景: {scenario.get('scenario', '')}\n\n"
            f"检查方案中是否有应对此场景的设计。\n"
            f"输出 JSON: {{\"handled\": true/false, \"gap\": \"缺失的应对措施\"}}"
        )
        check_result = call_model("gemini_2_5_flash", check_prompt, "只输出 JSON。", "stress_check")
        if check_result.get("success"):
            try:
                check_data = json.loads(re.sub(r'^```json\s*|\s*```$', '', check_result["response"].strip()))
                test_results.append({
                    "scenario": scenario.get("scenario"),
                    "impact": scenario.get("impact"), **check_data
                })
            except:
                pass

    handled_count = sum(1 for r in test_results if r.get("handled"))
    resilience_score = handled_count / len(test_results) * 100 if test_results else 0

    report = f"# 产品方案压力测试报告\n\n"
    report += f"## 韧性评分: {resilience_score:.0f}%\n\n"
    report += f"- 测试场景数: {len(test_results)}\n"
    report += f"- 已覆盖: {handled_count}\n- 未覆盖: {len(test_results) - handled_count}\n\n"
    report += "## 未覆盖场景详情\n\n"
    for r in test_results:
        if not r.get("handled"):
            report += f"- **{r.get('scenario')}** (影响: {r.get('impact')})\n"
            report += f"  缺失: {r.get('gap', '未说明')}\n\n"
    return report


# ============================================================
# A-9: 知识综述
# ============================================================
def generate_knowledge_synthesis():
    topic_groups = {}
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            if data.get("type") == "synthesis":
                continue
            title = data.get("title", "")
            for keyword in ["HUD", "光学", "歌尔", "Cardo", "Sena", "MicroLED",
                            "OLED", "Mesh", "ANC", "传感器", "认证"]:
                if keyword.lower() in title.lower():
                    if keyword not in topic_groups:
                        topic_groups[keyword] = []
                    topic_groups[keyword].append(data)
        except:
            continue

    for topic, entries in topic_groups.items():
        if len(entries) < 10:
            continue
        entries_text = "\n".join([f"- {e.get('title', '')}: {e.get('content', '')[:200]}"
                                 for e in entries[:20]])
        result = call_model("gpt_5_4",
            f"以下是关于 '{topic}' 的 {len(entries)} 条知识库碎片。\n"
            f"请整合成一篇结构化综述（1000-1500字）。\n\n知识碎片:\n{entries_text}",
            "你是行业分析师，用数据说话。", "synthesis")
        if result.get("success"):
            add_knowledge(
                title=f"[综述] {topic} 全景分析", domain="lessons",
                content=result["response"],
                tags=["synthesis", topic], source="auto_synthesis", confidence="high")
            print(f"  [Synthesis] 生成综述: {topic}（基于 {len(entries)} 条碎片）")


# ============================================================
# A-10: 类比推理
# ============================================================
ANALOGY_DOMAINS = {
    "骑行头盔 HUD": ["汽车 HUD", "战斗机 HUD", "AR 眼镜"],
    "骑行头盔 ANC": ["TWS 耳机 ANC", "头戴式耳机 ANC"],
    "骑行头盔 市场": ["智能手表市场", "运动相机市场", "TWS 耳机市场"],
    "Mesh 组队": ["对讲机市场", "游戏语音组队"],
}


def try_analogy_reasoning(query: str, kb_results: list) -> str:
    if len(kb_results) >= 3:
        return ""

    best_domain = None
    for key, analogies in ANALOGY_DOMAINS.items():
        if any(kw in query for kw in key.split()):
            best_domain = analogies
            break
    if not best_domain:
        return ""

    result = call_model("gemini_2_5_flash",
        f"问题: {query}\n直接数据不足。请用以下类似领域的数据做类比推理:\n"
        f"类比领域: {', '.join(best_domain)}\n\n"
        f"输出格式:\n⚡ 类比推理（非直接数据）\n类比来源: [领域]\n推理: [具体推理]\n置信度: [低/中]",
        task_type="analogy")
    if result.get("success"):
        return f"\n\n{result['response']}"
    return ""


# ============================================================
# A-11: 覆盖度路由
# ============================================================
def assess_kb_coverage(query: str) -> float:
    results = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            content = data.get("content", "")
            title = data.get("title", "")
            if query.lower() in title.lower() or query.lower() in content[:500].lower():
                results.append(data)
        except:
            continue
    if not results:
        return 0.0
    high_conf = sum(1 for r in results if r.get("confidence") in ("high", "authoritative"))
    return min(1.0, (len(results) * 0.1) + (high_conf * 0.15))


def select_model_by_coverage(query: str, default_model: str) -> str:
    coverage = assess_kb_coverage(query)
    if coverage > 0.7:
        print(f"  [Budget] KB 覆盖度 {coverage:.0%}，用 Flash 补充")
        return "gemini_2_5_flash"
    elif coverage > 0.4:
        return default_model
    else:
        print(f"  [Budget] KB 覆盖度 {coverage:.0%}，用最强模型深搜")
        return "o3_deep_research"


# ============================================================
# A-12: 反脆弱
# ============================================================
def fallback_to_offline_tasks(failed_model: str, failed_query: str):
    print(f"  [AntiFragile] {failed_model} 全部失败，切换离线任务")
    offline_tasks = [
        ("KB治理", lambda: _run_kb_governance_lite()),
        ("知识综述", lambda: generate_knowledge_synthesis()),
        ("决策树扫描", lambda: scan_decision_readiness()),
        ("工作记忆整理", lambda: _organize_work_memory()),
    ]
    for name, task_fn in offline_tasks:
        try:
            print(f"  [AntiFragile] 执行离线任务: {name}")
            task_fn()
        except:
            pass


def _run_kb_governance_lite():
    extract_experience_rules()
    generate_knowledge_synthesis()


def scan_decision_readiness():
    dt_path = AI_STATE / "product_decision_tree.yaml"
    if not dt_path.exists():
        return
    try:
        with open(dt_path, 'r', encoding='utf-8') as f:
            tree = yaml.safe_load(f)
        for decision in tree.get("decisions", []):
            gaps = decision.get("blocking_knowledge", [])
            ready = len(gaps) == 0
            print(f"  [Decision] {decision.get('id')}: {'就绪' if ready else f'缺 {len(gaps)} 项'}")
    except:
        pass


def _organize_work_memory():
    temp_dir = AI_STATE / "temp"
    if temp_dir.exists():
        for f in temp_dir.glob("*"):
            if f.stat().st_mtime < time.time() - 86400:
                f.unlink()


# ============================================================
# A-15: 竞品界面素材库
# ============================================================
COMPETITIVE_UI_PATH = AI_STATE / "competitive_ui"


def collect_competitive_ui(url: str, source_name: str):
    if not url:
        return
    image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
    if any(ext in url.lower() for ext in image_extensions):
        COMPETITIVE_UI_PATH.mkdir(parents=True, exist_ok=True)
        record_path = COMPETITIVE_UI_PATH / "ui_assets.jsonl"
        entry = {"url": url, "source": source_name,
                 "timestamp": time.strftime('%Y-%m-%d %H:%M')}
        with open(record_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"  [UI Asset] 记录: {url[:60]}...")


# ============================================================
# Q2: 数值计算引擎
# ============================================================
CALC_PATTERN = re.compile(r'\[CALC:\s*([^\]]+)\]')

OPERATORS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.USub: operator.neg,
}


def _safe_eval_math(expr: str) -> float:
    def _eval(node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("只允许数字")
        elif isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            op_type = type(node.op)
            if op_type in OPERATORS:
                return OPERATORS[op_type](left, right)
            raise ValueError(f"不支持的操作符: {op_type}")
        elif isinstance(node, ast.UnaryOp):
            operand = _eval(node.operand)
            op_type = type(node.op)
            if op_type in OPERATORS:
                return OPERATORS[op_type](operand)
            raise ValueError(f"不支持的一元操作符: {op_type}")
        else:
            raise ValueError(f"不支持的语法: {type(node)}")
    tree = ast.parse(expr, mode='eval')
    return _eval(tree.body)


def evaluate_calculations(text: str) -> str:
    def replace_calc(match):
        expr = match.group(1)
        try:
            result = _safe_eval_math(expr)
            return f"[CALC: {expr}] = {result:.2f}"
        except Exception as e:
            return f"[CALC: {expr}] = (计算错误: {str(e)[:30]})"
    return CALC_PATTERN.sub(replace_calc, text)


# ============================================================
# Q3: 推理链可见化
# ============================================================
REASONING_CHAIN_PROMPT = """
请在结论之前展示推理过程：
- 数据来源 → 推论 → 结论
- 如果多个数据指向不同结论，说明为什么选择了这个结论

格式示例:
## 推理链
1. 数据来源: [来源A] 显示 X
2. 推论: 基于 X，可以推断 Y
3. 冲突处理: [来源B] 显示 Z，但选择 Y 因为 [理由]
4. 结论: 最终判断为 Y
"""


# ============================================================
# Q5: 系统自评分
# ============================================================
SELF_ASSESSMENT_PATH = AI_STATE / "self_assessments.jsonl"


def run_self_assessment(report: str, task_title: str,
                        search_count: int, structured_count: int):
    assessment_prompt = (
        f"评估以下研究报告的质量（1-10分）:\n\n"
        f"报告标题: {task_title}\n报告长度: {len(report)} 字\n"
        f"搜索结果数: {search_count}\n结构化数据条数: {structured_count}\n\n"
        f"评估维度: 数据密度、结论明确度、来源标注、决策支撑度\n\n"
        f"输出 JSON: {{\"overall\": 1-10, \"data_density\": 1-10, \"clarity\": 1-10, "
        f"\"sourcing\": 1-10, \"decision_support\": 1-10, \"issues\": [\"问题1\"]}}"
    )
    result = call_model("gemini_2_5_flash", assessment_prompt, "只输出 JSON。", "self_assessment")
    if result.get("success"):
        try:
            assessment = json.loads(re.sub(r'^```json\s*|\s*```$', '', result["response"].strip()))
            assessment["task_title"] = task_title
            assessment["timestamp"] = time.strftime('%Y-%m-%d %H:%M')
            assessment["report_length"] = len(report)
            with open(SELF_ASSESSMENT_PATH, 'a', encoding='utf-8') as f:
                f.write(json.dumps(assessment, ensure_ascii=False) + "\n")
            print(f"  [SelfAssess] 评分: {assessment.get('overall', '?')}/10")
            return assessment
        except:
            pass
    return {}


# ============================================================
# KB 增强检索 + 专家框架匹配 + Demo准备
# ============================================================
def get_kb_context_enhanced(task_goal: str, task_title: str) -> str:
    keywords = re.findall(r'[\u4e00-\u9fff]{2,6}', task_goal)[:10]
    tech_terms = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*|[A-Z]{2,}', task_goal)[:5]
    queries = keywords[:5] + tech_terms[:3] + [task_title]

    all_entries = []
    seen_ids = set()
    for q in queries:
        for f in KB_ROOT.rglob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                content = data.get("content", "")
                t = data.get("title", "")
                if q.lower() in t.lower() or q.lower() in content[:500].lower():
                    entry_id = str(f)
                    if entry_id not in seen_ids:
                        seen_ids.add(entry_id)
                        all_entries.append({
                            "title": t, "content": content[:500],
                            "confidence": data.get("confidence", ""),
                            "tags": data.get("tags", [])
                        })
            except:
                continue

    conf_order = {"authoritative": 3, "high": 2, "medium": 1, "low": 0}
    all_entries.sort(key=lambda x: conf_order.get(x.get('confidence', ''), 0), reverse=True)
    top_entries = all_entries[:15]

    if not top_entries:
        return ""
    result = ""
    for entry in top_entries:
        result += f"\n[KB] {entry['title']}: {entry['content'][:300]}"
    return result[:3000]


def match_expert_framework(task_goal: str, task_title: str) -> dict:
    config_path = Path(__file__).resolve().parent.parent.parent / "src" / "config" / "expert_frameworks.yaml"
    if not config_path.exists():
        return {}
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            frameworks = yaml.safe_load(f)
    except:
        return {}

    combined_text = task_goal + " " + task_title
    best_match = None
    best_score = 0
    for name, fw in frameworks.items():
        if name == 'general_research':
            continue
        score = sum(1 for kw in fw.get('match_keywords', []) if kw in combined_text)
        if score > best_score:
            best_score = score
            best_match = name
    if best_match and best_score > 0:
        return frameworks[best_match]
    return frameworks.get('general_research', {})


def ensure_demo_prerequisites(demo_type: str, progress_callback=None) -> dict:
    required_knowledge = {
        "hud_demo": [
            ("HUD 信息布局规范", "HUD layout specification display position motorcycle helmet"),
            ("HUD 色彩方案", "HUD color scheme helmet visor daylight night visibility"),
            ("HUD 信息优先级", "HUD information priority navigation speed call alert"),
            ("HUD 动画规范", "HUD animation transition fade duration interaction"),
            ("竞品 HUD 布局参考", "EyeRide Jarvish Forcite HUD layout screenshot interface"),
        ],
        "app_demo": [
            ("App 配对流程", "smart helmet app pairing bluetooth connection flow"),
            ("App 骑行仪表盘", "motorcycle riding dashboard UI speedometer navigation"),
            ("App 组队地图", "group ride map real-time location sharing mesh"),
            ("竞品 App 参考", "Cardo Sena app UI design screenshot interface"),
        ],
    }

    results = {}
    missing = []

    for topic, search_query in required_knowledge.get(demo_type, []):
        kb_results = []
        for f in KB_ROOT.rglob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if topic.lower() in data.get("title", "").lower() or \
                   topic.lower() in data.get("content", "")[:500].lower():
                    kb_results.append(data)
            except:
                continue
        if len(kb_results) >= 2 and any(
            r.get("confidence") in ("high", "authoritative") for r in kb_results):
            results[topic] = kb_results
        else:
            missing.append((topic, search_query))

    if missing:
        if progress_callback:
            progress_callback(f"  Demo准备: 缺少 {len(missing)} 项信息，自动搜索补齐...")
        print(f"  [DemoPrep] 缺少 {len(missing)} 项信息，自动搜索补齐...")
        for topic, query in missing:
            result = call_with_backoff("gemini_2_5_flash",
                f"搜索关于 {query} 的关键信息，输出 300-500 字摘要。",
                "你是产品研究员，提取关键设计参数。", "demo_prep_search")
            if result.get("success"):
                search_result = result["response"][:1000]
                add_knowledge(
                    title=f"[Demo准备] {topic}", domain="components",
                    content=search_result, tags=["demo_prep", demo_type],
                    source="auto_demo_prep", confidence="medium")
                results[topic] = [{"content": search_result}]
                print(f"  [DemoPrep] 补齐: {topic}")
    return results


# ============================================================
# A-14: 沙盘 What-If
# ============================================================
def sandbox_what_if(parameter_change: str, kb_context: str = "",
                    progress_callback=None) -> str:
    prompt = (
        f"产品: 智能骑行头盔 V1\n参数变更: {parameter_change}\n\n"
        f"已知产品参数和约束:\n{kb_context[:3000]}\n\n"
        f"请推演这个变更的连锁影响链条。每一步标注:\n"
        f"1. 直接影响（确定性高）\n2. 间接影响（确定性中）\n"
        f"3. 远端影响（确定性低）\n\n"
        f"最终给出：这个变更是否值得做？代价是什么？"
    )
    result = gateway.call("o3", prompt,
        "你是系统工程师，擅长因果链条推理。", "sandbox")
    return result.get("response", "") if result.get("success") else "推演失败"
