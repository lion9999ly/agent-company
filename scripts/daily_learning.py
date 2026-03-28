"""
@description: 每日自学习循环 - Agent 主动追踪行业前沿，LLM提炼后写入知识库
@dependencies: src.tools.tool_registry, src.tools.knowledge_base, src.utils.model_gateway
@last_modified: 2026-03-26
"""
import sys
import os
import json
import re
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))

# 加载 .env 文件
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

from src.tools.tool_registry import get_tool_registry
from src.tools.knowledge_base import add_knowledge, get_knowledge_stats, search_knowledge
from src.utils.model_gateway import get_model_gateway, call_for_search, call_for_refine
from src.utils.progress_heartbeat import ProgressHeartbeat

TOPICS_PATH = Path(__file__).parent.parent / ".ai-state" / "knowledge" / "learning_topics.json"
COVERED_TOPICS_FILE = Path(__file__).parent.parent / ".ai-state" / "covered_topics.json"


def _audit_unused_knowledge():
    """Audit entries with zero usage in the past 30 days"""
    from src.tools.knowledge_base import KB_ROOT

    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    unused = []
    total = 0

    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            total += 1

            usage = data.get("_usage_count", 0)
            created = data.get("_created", data.get("timestamp", ""))

            # Created more than 7 days but zero usage
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
        "unused_sample": unused[:10]  # First 10 samples
    }


def _load_covered_topics() -> dict:
    """加载已覆盖的固定主题及其覆盖时间"""
    if not COVERED_TOPICS_FILE.exists():
        return {}
    try:
        data = json.loads(COVERED_TOPICS_FILE.read_text(encoding="utf-8"))
        covered = data.get("covered", {})
        if isinstance(covered, list):
            # 旧格式是 list，转换为 dict
            covered = {fp: datetime.now().strftime("%Y-%m-%d") for fp in covered}
        return covered
    except:
        return {}


def _save_covered_topics(covered: dict):
    """保存已覆盖的固定主题及时间"""
    COVERED_TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    COVERED_TOPICS_FILE.write_text(
        json.dumps({"covered": covered, "updated": datetime.now().isoformat()}, ensure_ascii=False),
        encoding="utf-8"
    )


def _get_cover_age(fp: str) -> int:
    """获取固定主题覆盖了多少天，返回 None 表示无记录"""
    covered = _load_covered_topics()
    date_str = covered.get(fp)
    if not date_str:
        return None
    try:
        cover_date = datetime.strptime(date_str, "%Y-%m-%d")
        return (datetime.now() - cover_date).days
    except:
        return 0


def _topic_fingerprint(query: str) -> str:
    """固定主题指纹：取前40字符的小写"""
    return query[:40].lower().strip()


def _load_topics() -> list:
    if not TOPICS_PATH.exists():
        return []
    data = json.loads(TOPICS_PATH.read_text(encoding="utf-8"))
    return data.get("topics", [])


def _generate_dynamic_topics() -> list:
    """让 CPO 基于知识库现状和最近任务动态生成搜索词"""
    from src.tools.knowledge_base import get_knowledge_stats, search_knowledge, KB_ROOT

    # 收集上下文
    kb_stats = get_knowledge_stats()

    # 最近经验卡片
    memory_dir = Path(__file__).parent.parent / ".ai-state" / "memory"
    recent_goals = []
    if memory_dir.exists():
        for f in sorted(memory_dir.glob("*.json"), reverse=True)[:5]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                goal = data.get("task_goal", "")
                feedback = data.get("user_feedback", "")
                if goal:
                    recent_goals.append(f"{goal}" + (f" [feedback:{feedback}]" if feedback else ""))
            except Exception:
                continue

    # 知识缺口
    gaps = []
    if memory_dir.exists():
        for f in sorted(memory_dir.glob("*.json"), reverse=True)[:10]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                for gap in data.get("knowledge_gaps", []):
                    if gap:
                        gaps.append(gap)
            except Exception:
                continue

    # 分析竞品维度覆盖缺口
    competitor_coverage = {}
    key_dimensions = ["芯片", "HUD", "摄像头", "音频", "通讯", "电池", "材质", "认证", "售价", "供应商"]

    competitors_dir = Path(__file__).parent.parent / ".ai-state" / "knowledge" / "competitors"
    if competitors_dir.exists():
        for f in competitors_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                title = data.get("title", "").lower()
                content = data.get("content", "").lower()
                # 识别品牌
                for brand in ["shoei", "forcite", "motoeye", "cardo", "sena", "livall", "lumos",
                               "meta", "bleequp", "asmax", "reso", "unit 1", "tali", "雷鸟"]:
                    if brand in title or brand in content[:100]:
                        if brand not in competitor_coverage:
                            competitor_coverage[brand] = set()
                        for dim in key_dimensions:
                            if dim in content:
                                competitor_coverage[brand].add(dim)
            except Exception:
                continue

    # 找出覆盖缺口
    gaps_info = []
    for brand, covered in competitor_coverage.items():
        missing = [d for d in key_dimensions if d not in covered]
        if missing:
            gaps_info.append(f"{brand}: 缺 {', '.join(missing[:3])}")

    # === 29b: 知识库维度覆盖缺口分析 ===
    dimension_counts = {}
    target_dimensions = {
        "HUD/AR显示": ["HUD", "AR", "光机", "光波导", "Micro OLED", "近眼显示", "waveguide"],
        "4K摄像": ["4K", "摄像", "IMX", "EIS", "防抖", "行车记录", "camera", "dashcam"],
        "ANC/ENC降噪": ["ANC", "ENC", "降噪", "风噪", "通话", "麦克风阵列", "noise cancellation"],
        "ADAS安全": ["ADAS", "盲区", "碰撞预警", "前向预警", "雷达", "AEB", "APA", "RPA",
                     "BSD", "LDW", "FCW", "ACC", "主动安全", "被动安全", "预警",
                     "blind spot", "collision", "emergency braking", "lane departure",
                     "泊车", "避障", "毫米波", "超声波", "USS", "ARAS"],
        "SoC/芯片": ["AR1", "BES2800", "高通", "恒玄", "SoC", "芯片", "Nordic", "nRF",
                     "QCC", "J6", "Orin", "TDA4", "征程", "horizon"],
        "认证标准": ["ECE", "DOT", "3C", "FCC", "CE RED", "UN38.3", "GB 811", "FMVSS",
                    "ENCAP", "CNCAP", "EN 1078", "NTA"],
        "供应商/JDM": ["歌尔", "Goertek", "JDM", "ODM", "供应商", "代工", "立讯", "Luxshare"],
        "Mesh对讲": ["Mesh", "对讲", "自组网", "Sena", "Cardo", "intercom", "DMC"],
        "电池/散热": ["电池", "散热", "热管理", "温控", "mAh", "充电", "thermal"],
        "结构/材料": ["碳纤维", "玻纤", "EPS", "壳体", "模具", "重量", "MIPS", "carbon fiber"]
    }

    for dim_name, keywords in target_dimensions.items():
        count = 0
        for f in KB_ROOT.rglob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                text = (data.get("title", "") + " " + data.get("content", "")[:200]).lower()
                if any(kw.lower() in text for kw in keywords):
                    count += 1
            except:
                continue
        dimension_counts[dim_name] = count

    # 找出最薄弱的 3 个维度
    sorted_dims = sorted(dimension_counts.items(), key=lambda x: x[1])
    weak_dims = sorted_dims[:3]
    weak_info = "\n".join([f"  - {d}: 仅{c}条（需要加强）" for d, c in weak_dims])

    # === 29b: 读取最近的 Critic 反馈 ===
    critic_feedback = ""
    memory_dir = Path(__file__).parent.parent / ".ai-state" / "memory"
    if memory_dir.exists():
        recent_files = sorted(memory_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:3]
        for rf in recent_files:
            try:
                rdata = json.loads(rf.read_text(encoding="utf-8"))
                fb = rdata.get("critic_feedback", "") or rdata.get("feedback", "")
                if fb:
                    critic_feedback += f"\n{fb[:200]}"
            except:
                continue

    if not critic_feedback:
        critic_feedback = "暂无 Critic 反馈"

    gateway = get_model_gateway()
    prompt = (
        f"你是智能摩托车头盔（全盔）虚拟研发中心的学习规划师。\n\n"
        f"我们的产品是面向摩托车骑行者的高端智能全盔，核心功能包括：\n"
        f"- HUD/AR近眼显示（P0）\n"
        f"- 4K行车记录（P0）\n"
        f"- AI语音交互+ANC/ENC降噪（P0）\n"
        f"- ADAS盲区/碰撞预警（P0）\n"
        f"- SOS生命救援（P0）\n"
        f"- Mesh车队对讲（P1）\n"
        f"- 碳纤维/玻纤壳体，<=1.65kg，>=3500mAh电池\n"
        f"- 认证：ECE 22.06 / DOT / 3C\n"
        f"- JDM供应商：歌尔（声学+光学+摄像+AR整机）\n\n"
        f"当前知识库状态：{json.dumps(kb_stats, ensure_ascii=False)}\n"
        f"竞品维度覆盖缺口：\n{'  '.join(gaps_info[:8]) if gaps_info else '暂无缺口数据'}\n\n"
        f"## 知识库覆盖率缺口（重点补强以下薄弱维度）\n{weak_info}\n\n"
        f"## 最近研发任务的 Critic 反馈（针对性学习）\n{critic_feedback[:500]}\n\n"
        f"请生成 10 个高价值搜索词。要求：\n"
        f"1. 必须围绕摩托车智能头盔（不是自行车头盔）\n"
        f"2. 优先覆盖薄弱维度，帮助补齐知识缺口\n"
        f"3. 每个搜索词必须具体（含品牌名/公司名/型号/标准号）\n"
        f"4. 中英文混合，优先英文\n"
        f"5. 加入 2025 或 2026 时间词\n\n"
        f"只输出 JSON 数组：[\"搜索词1\", \"搜索词2\", ...]"
    )

    result = gateway.call_azure_openai(
        "cpo", prompt,
        "You are a learning planner. Output only JSON array, no other content.",
        "dynamic_topics"
    )

    if not result.get("success"):
        return []

    response = result["response"].strip()
    response = re.sub(r'^```json\s*', '', response)
    response = re.sub(r'\s*```$', '', response)

    try:
        topics_raw = json.loads(response)
        if isinstance(topics_raw, list):
            # 转换为统一格式
            topics = []
            for item in topics_raw:
                if isinstance(item, str):
                    # 简单字符串，自动分配 domain
                    query = item
                    domain = "components"  # 默认
                    if any(kw in query.lower() for kw in ["certif", "standard", "标准", "认证", "dot", "ece", "en"]):
                        domain = "standards"
                    elif any(kw in query.lower() for kw in ["competitor", "竞品", "shoei", "sena", "livall", "market"]):
                        domain = "competitors"
                    elif any(kw in query.lower() for kw in ["design", "设计", "ux", "user", "用户"]):
                        domain = "lessons"
                    topics.append({"query": query, "domain": domain, "tags": ["dynamic"]})
                elif isinstance(item, dict):
                    topics.append(item)
            print(f"[DailyLearning] Generated {len(topics)} dynamic topics")
            return topics[:15]
    except Exception:
        pass
    return []


def _refine_with_llm(raw_content: str, query: str) -> str:
    """用 LLM 提炼搜索结果，提取与智能骑行头盔项目相关的关键信息"""
    if len(raw_content) < 50:
        return ""
    gateway = get_model_gateway()
    prompt = (
        f"以下是关于「{query}」的搜索结果原文。\n\n"
        f"请提炼与「智能骑行头盔产品研发」相关的关键信息，包括但不限于：\n"
        f"- 新产品/新技术的具体名称、参数、价格\n"
        f"- 技术趋势和行业变化\n"
        f"- 可借鉴的设计理念或商业模式\n"
        f"- 标准法规的具体变更要点\n\n"
        f"【重要】以下主题与智能骑行头盔直接相关，不要标记为无关：\n"
        f"LED灯控、无线充电、芯片选型、传感器融合、通讯模块、电池管理、\n"
        f"材料科学、HUD显示、音频系统、安全标准、头盔认证、蓝牙模块、\n"
        f"AR/VR技术、AI芯片、语音控制、运动传感器、GPS定位\n\n"
        f"如果搜索结果与智能骑行头盔完全无关（如娱乐八卦、政治新闻），只回复「无相关内容」。\n"
        f"如果有相关内容，用 500 字以内输出结构化摘要。\n\n"
        f"搜索结果：\n{raw_content[:4000]}"
    )
    result = gateway.call_azure_openai("cpo", prompt, "你是研发情报分析专家。只输出有价值的提炼内容，不输出废话。", "learning_refine")
    if result.get("success"):
        refined = result["response"].strip()
        if "无相关内容" in refined and len(refined) < 20:
            return ""
        return refined
    return raw_content[:800]


def _parse_json_response(response: str) -> dict:
    """解析 LLM 返回的 JSON 响应"""
    if not response:
        return None
    try:
        resp = response.strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        return json.loads(resp)
    except Exception:
        return None


def _refine_with_llm_raw(prompt: str) -> dict:
    """用 LLM 处理原始 prompt，返回解析后的 JSON（提炼环节用 GPT-5.4）"""
    result = call_for_refine(prompt, "只输出 JSON，不要有其他内容。", "daily_deep")
    if not result.get("success"):
        return None
    return _parse_json_response(result.get("response", ""))


def _is_duplicate(query: str, domain: str) -> bool:
    """检查今天是否已经对同一 query 学习过（同一天同一主题不重复，不同天允许）"""
    today = datetime.now().strftime("%m%d")
    kb_root = Path(__file__).parent.parent / ".ai-state" / "knowledge"
    domain_dir = kb_root / domain
    if not domain_dir.exists():
        return False

    # 提取 query 的核心关键词（取前 20 字符作为指纹）
    query_fingerprint = query[:20].lower().strip()

    for f in domain_dir.glob("*.json"):
        # 只检查今天创建的文件
        if today not in f.name:
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("source") not in ("daily_learning", "daily_deep"):
                continue
            # 检查标题中是否包含相同的 query 指纹
            title = data.get("title", "").lower()
            if query_fingerprint in title or title in query_fingerprint:
                return True
        except Exception:
            continue
    return False


def _search_one_topic_parallel(topic: dict, registry) -> dict:
    """并行搜索单个主题，返回搜索结果（不包含提炼）

    用于 ThreadPoolExecutor 并行搜索，返回格式：
    {"topic": topic, "sources": [...], "fail_reasons": [...], "success": bool}
    """
    query = topic["query"]
    sources = []
    fail_reasons = []

    # 来源1: deep_research
    r1 = registry.call("deep_research", query)
    r1_ok = r1.get("success") and len(r1.get("data", "")) > 200
    if r1_ok:
        sources.append(r1["data"][:2000])
    else:
        err = r1.get('error', 'unknown')[:50] if r1.get('error') else 'no data'
        fail_reasons.append(f"deep:{err}")

    # 来源2: tavily_search
    r2 = registry.call("tavily_search", query)
    r2_ok = r2.get("success") and len(r2.get("data", "")) > 200
    if r2_ok:
        sources.append(r2["data"][:2000])
    else:
        err = r2.get('error', 'unknown')[:50] if r2.get('error') else 'no data'
        fail_reasons.append(f"tavily:{err}")

    # 来源3: 换角度再搜
    alt_query = query.replace("2026", "latest").replace("新品", "review teardown") if "2026" in query else query + " 2026 review"
    r3 = registry.call("tavily_search", alt_query)
    r3_ok = r3.get("success") and len(r3.get("data", "")) > 200
    if r3_ok:
        sources.append(r3["data"][:2000])
    else:
        err = r3.get('error', 'unknown')[:50] if r3.get('error') else 'no data'
        fail_reasons.append(f"tavily_alt:{err}")

    return {
        "topic": topic,
        "query": query,
        "sources": sources,
        "fail_reasons": fail_reasons,
        "success": len(sources) > 0
    }


def run_daily_learning(progress_callback=None) -> str:
    """执行每日学习循环，返回学习简报"""
    topics = _load_topics()
    if not topics:
        return "[Warning] Learning topics empty, check learning_topics.json"

    # 白天/夜间模式检测（夜间 23:00-07:00 不推送进度，只打印）
    current_hour = datetime.now().hour
    is_night = current_hour >= 23 or current_hour < 7

    # 动态生成本轮搜索词（基于知识库现状 + 最近任务）
    dynamic_topics = _generate_dynamic_topics()
    dynamic_query_set = set()
    if dynamic_topics:
        fixed_count = len(topics)
        topics = topics + dynamic_topics
        dynamic_query_set = set(t["query"] for t in dynamic_topics)
        print(f"[DailyLearning] Fixed {fixed_count} + Dynamic {len(dynamic_topics)} = {len(topics)} topics")

    registry = get_tool_registry()
    gateway = get_model_gateway()
    report_lines = [f"[Daily Learning] Report ({datetime.now().strftime('%Y-%m-%d %H:%M')})"]
    report_lines.append(f"[Info] {len(topics)} topics to search\n")
    new_count = 0
    skip_count = 0
    fail_count = 0

    # === 心跳初始化 ===
    hb = ProgressHeartbeat(
        "每日学习",
        total=len(topics),
        feishu_callback=None if is_night else progress_callback,
        log_interval=5,
        feishu_interval=10,       # 每 10 个主题推一次飞书
        feishu_time_interval=180  # 或至少每 3 分钟推一次
    )

    # === 固定主题覆盖追踪 ===
    covered = _load_covered_topics()
    newly_covered = {}  # fp -> date

    # 导入优先级管理器
    from src.utils.task_priority import get_priority_manager
    pm = get_priority_manager()

    # === 阶段 A：过滤需要搜索的主题 ===
    topics_to_search = []
    for i, topic in enumerate(topics):
        pm.wait_if_p0_active(timeout=30)
        query = topic["query"]
        is_dynamic = query in dynamic_query_set
        short_query = query[:35] + "..." if len(query) > 35 else query

        if not is_dynamic:
            fp = _topic_fingerprint(query)
            if fp in covered:
                cover_age = _get_cover_age(fp)
                if cover_age is not None and cover_age < 7:
                    skip_count += 1
                    hb.tick(detail=f"[Skip] {short_query}", success=True)
                    continue
                print(f"  [Refresh] 固定主题已覆盖 {cover_age} 天，重新搜索: {short_query}")
        topics_to_search.append(topic)

    # === 阶段 B：并行搜索（4 路） ===
    print(f"  [并行搜索] {len(topics_to_search)} 个主题，4 路并行...")
    search_results = []
    done_count = 0

    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_search_one_topic_parallel, t, registry): t for t in topics_to_search}
        for f in as_completed(futs):
            result = f.result()
            search_results.append(result)
            done_count += 1
            # 进度心跳：每 5 条搜索完成打日志
            if done_count % 5 == 0:
                print(f"  [搜索进度] {done_count}/{len(topics_to_search)}")
            hb.tick(detail=f"搜索: {result['query'][:30]}", success=result["success"])

    print(f"  [搜索完成] {len(search_results)}/{len(topics_to_search)}")

    # === 阶段 C：串行提炼 ===
    for i, sr in enumerate(search_results, 1):
        topic = sr["topic"]
        query = sr["query"]
        domain = topic["domain"]
        tags = topic.get("tags", [])
        short_query = query[:35] + "..." if len(query) > 35 else query
        is_dynamic = query in dynamic_query_set
        sources = sr["sources"]

        if not sr["success"]:
            report_lines.append(f"  X {short_query} -- {'; '.join(sr['fail_reasons'])}")
            fail_count += 1
            continue

        # LLM 综合多源写深度条目（提炼环节用 call_for_refine）
        combined = "\n---\n".join(sources)
        refine_prompt = (
            f"基于以下 {len(sources)} 个来源的搜索结果，撰写一条高质量知识条目。\n"
            f"【产品约束】我们是智能摩托车头盔（全盔），不是自行车头盔。如果来源涉及自行车头盔，必须明确排除或标注差异。\n"
            f"要求：500-800字，包含具体数据（型号、参数、价格、供应商名），不要泛泛而谈。\n"
            f"如果来源之间有矛盾，标注出来。\n"
            f"输出 JSON：{{\"title\": \"标题\", \"domain\": \"competitors/components/standards/lessons\", "
            f"\"content\": \"500-800字深度内容\", \"tags\": [\"标签\"]}}\n\n"
            f"搜索词：{query}\n来源：\n{combined[:5000]}"
        )
        # === Phase 2.3: 提炼用 GPT-5.4 ===
        refine_result = call_for_refine(refine_prompt, "撰写知识条目，输出JSON。", "daily_learn_refine")
        refined = None
        if refine_result.get("success"):
            refined = _parse_json_response(refine_result.get("response", ""))

        if not refined:
            report_lines.append(f"  ⏭️ {short_query} — 与项目无关，跳过")
            skip_count += 1
            continue

        # === 搜索结果方向自检 ===
        refined_content_text = refined.get("content", "") if refined else ""
        refined_title_text = refined.get("title", "") if refined else ""
        combined_text = (refined_content_text + refined_title_text).lower()

        # 检测是否偏离摩托车方向（输出了自行车内容但没提摩托车）
        is_bicycle_only = (
            ("自行车" in combined_text or "bicycle" in combined_text or "cycling helmet" in combined_text)
            and "摩托" not in combined_text
            and "motorcycle" not in combined_text
            and "全盔" not in combined_text
            and "full-face" not in combined_text
        )

        if is_bicycle_only:
            report_lines.append(f"  [FIX] {short_query} — 结果偏向自行车，自动追加摩托车限定重搜")
            # 自动重搜：在原 query 前加"摩托车"限定
            fixed_query = f"摩托车 motorcycle {query}"
            r_fix = registry.call("deep_research", fixed_query)
            if r_fix.get("success") and len(r_fix.get("data", "")) > 200:
                fix_prompt = (
                    f"基于以下搜索结果，撰写一条与摩托车智能全盔相关的知识条目。\n"
                    f"【重要】排除自行车头盔内容。\n"
                    f"输出 JSON：{{\"title\": \"标题\", \"domain\": \"...\", \"content\": \"500-800字\", \"tags\": [...]}}\n\n"
                    f"搜索词：{fixed_query}\n来源：\n{r_fix['data'][:4000]}"
                )
                refined = _refine_with_llm_raw(fix_prompt)
                if not refined:
                    skip_count += 1
                    continue
            else:
                skip_count += 1
                continue

        # 去重检查：固定主题按天去重，动态主题不去重（每轮都搜新词）
        refined_domain = refined.get("domain", domain)
        if not is_dynamic and _is_duplicate(query, refined_domain):
            report_lines.append(f"  [SKIP] {short_query} -- 今日已学习，跳过")
            skip_count += 1
            continue

        # === 29a: 自主质量评估——入库前过滤 ===
        refined_title = refined.get("title", short_query)[:60]
        refined_content = refined.get("content", "")[:800]
        refined_tags = refined.get("tags", []) + tags

        # 快速过滤规则（不需要调 LLM）
        is_low_quality = False
        quality_reasons = []

        # 规则1：内容太短（<150字）
        if len(refined_content) < 150:
            is_low_quality = True
            quality_reasons.append("内容<150字")

        # 规则2：没有任何具体数据（数字、型号、价格、百分比）
        has_data = bool(re.search(r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|USD|\$|%|nits|lux|fps|°|μm)', refined_content))
        has_model = bool(re.search(r'[A-Z]{2,}\d{2,}|[A-Z]\d{4,}|IMX\d|QCC\d|BES\d|nRF\d|AR\d|ECE\s*\d|SN\d|KS\d', refined_content))

        # === 无数据条目补充（不跳过，要求 LLM 补充具体数据） ===
        if not has_data and not has_model and len(refined_content) >= 150 and len(sources) > 0:
            # 内容够长但缺数据，让 LLM 补充
            enrich_prompt = (
                f"以下知识条目内容缺少具体数据。请基于原始搜索结果补充：\n"
                f"- 具体型号（如 IMX678、BES2800、QCC5181）\n"
                f"- 具体参数（如 3000nits、42dB、1.65kg）\n"
                f"- 具体价格（如 $15-25/颗、￥200-300）\n"
                f"- 具体公司/品牌名\n\n"
                f"如果原始搜索结果中确实没有这些数据，保持原文不变。\n\n"
                f"当前条目：\n标题：{refined_title}\n内容：{refined_content}\n\n"
                f"原始搜索结果：\n{combined[:3000]}\n\n"
                f"输出 JSON：{{\"content\": \"补充数据后的完整内容(500-800字)\"}}"
            )
            enrich_result = _refine_with_llm_raw(enrich_prompt)
            if enrich_result and len(enrich_result.get("content", "")) > len(refined_content):
                old_len = len(refined_content)
                refined_content = enrich_result["content"][:800]
                print(f"  [ENRICH] {short_query} data enriched: {old_len} -> {len(refined_content)} chars")
                # 重新检查是否有数据
                has_data = bool(re.search(r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|USD|\$|%|nits|lux|fps|°|μm)', refined_content))
                has_model = bool(re.search(r'[A-Z]{2,}\d{2,}|[A-Z]\d{4,}|IMX\d|QCC\d|BES\d|nRF\d|AR\d|ECE\s*\d|SN\d|KS\d', refined_content))

        if not has_data and not has_model:
            is_low_quality = True
            quality_reasons.append("no data or model")

        # 规则4：推测性内容标记
        speculative_signals = ["假想", "假设", "推测", "推演", "设想", "预测",
                               "hypothetical", "speculated", "可能采用", "预计将"]
        is_speculative = any(sig in refined_content or sig in refined_title for sig in speculative_signals)
        if is_speculative:
            refined_tags.append("speculative")
            # 不跳过，但降低置信度
            print(f"  [SPEC] {short_query} — 标记为推测性内容")

        # 规则3：标题是泛泛的描述（没有品牌/公司/产品名）
        generic_titles = ["智能头盔", "骑行头盔", "头盔方案", "技术方案", "市场分析", "智能摩托车头盔", "摩托车头盔"]
        if any(refined_title.strip() == g or refined_title.strip().startswith(g + "。") for g in generic_titles):
            is_low_quality = True
            quality_reasons.append("标题太泛")

        if is_low_quality:
            report_lines.append(f"  [SKIP] {refined_title[:40]}... — 质量不足: {', '.join(quality_reasons)}")
            skip_count += 1
            continue

        if refined_domain not in ("competitors", "components", "standards", "lessons"):
            refined_domain = domain

        add_knowledge(
            title=f"{datetime.now().strftime('%m%d')}_{refined_title}",
            domain=refined_domain,
            content=refined_content,
            tags=refined_tags,
            source="daily_deep",
            confidence="high",
            caller="self_learning"
        )
        new_count += 1
        # 标记固定主题已覆盖（带日期）
        if not is_dynamic:
            newly_covered[_topic_fingerprint(query)] = datetime.now().strftime("%Y-%m-%d")
        report_lines.append(f"  OK {short_query} -> {refined_domain}/ ({len(sources)} src)")
        # 每完成 10 条提炼打日志
        if i % 10 == 0:
            print(f"  [提炼进度] {i}/{len(search_results)}，已入库 {new_count}")

    # 保存新覆盖的固定主题
    if newly_covered:
        covered.update(newly_covered)
        _save_covered_topics(covered)
        report_lines.append(f"[Cover] 新覆盖 {len(newly_covered)} 个固定主题，累计 {len(covered)} 个")

    stats = get_knowledge_stats()
    report_lines.append(f"\n{'='*40}")
    report_lines.append(f"📊 知识库现状: {stats}")
    report_lines.append(f"📝 本次新增: {new_count} 条 | 跳过: {skip_count} 条 | 失败: {fail_count} 条")
    report_lines.append(f"📋 总主题数: {len(topics)}")

    report = "\n".join(report_lines)
    print(report)

    # === 心跳完成 ===
    hb.finish(f"新增 {new_count} 条知识")

    # 任务完成提示音
    from src.utils.notifier import notify
    notify("success")

    # === Self-test closed loop: every 3 rounds do a self-test ===
    _learn_round_count = getattr(sys.modules[__name__], '_learn_round_count', 0) + 1
    sys.modules[__name__]._learn_round_count = _learn_round_count

    if _learn_round_count % 3 == 0:  # Every 3 rounds (~1.5 hours) self-test once
        try:
            from scripts.self_test import run_self_test, auto_deep_dive_weak_areas

            print("\n[SelfTest] Triggering periodic self-test...")
            test_result = run_self_test(count=5)  # Quick test 5 questions

            # If average score below 6, auto deep dive
            if test_result["avg_score"] < 6 and test_result["weak_areas"]:
                print(f"[SelfTest] Average score {test_result['avg_score']}/10, auto deep diving weak areas...")
                auto_deep_dive_weak_areas(test_result["weak_areas"][:3])  # Max 3 deep dives
            else:
                print(f"[SelfTest] Average score {test_result['avg_score']}/10, no deep dive needed")
        except Exception as e:
            print(f"[SelfTest] Self-test exception: {e}")

    return report


def run_night_deep_learning(progress_callback=None) -> str:
    """夜间深度学习（1am-5am），从知识库出发向广度和深度探索

    注意：此函数夜间执行，progress_callback 会被抑制（只打印不推送）
    """
    from src.tools.knowledge_base import search_knowledge, get_knowledge_stats, add_knowledge, KB_ROOT

    registry = get_tool_registry()
    gateway = get_model_gateway()
    report_lines = [f"[NightLearn] 夜间深度学习 ({datetime.now().strftime('%H:%M')})"]
    new_count = 0

    # 夜间模式：所有 progress_callback 转为本地打印
    is_night = True  # 此函数本身就是夜间任务

    # 导入优先级管理器
    from src.utils.task_priority import get_priority_manager
    pm = get_priority_manager()

    # === 阶段 1：知识库深化——找浅条目，深入搜索 ===
    report_lines.append("\n--- Phase 1: 知识库深化 ---")
    shallow_entries = []
    if KB_ROOT.exists():
        for f in KB_ROOT.rglob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                data["_filepath"] = str(f)
                content = data.get("content", "")
                tags = data.get("tags", [])
                # 跳过已深化的条目
                if "night_deepened" in tags:
                    continue
                if len(content) < 300 and data.get("confidence") != "high":
                    shallow_entries.append(data)
            except Exception:
                continue

    for entry in shallow_entries[:10]:
        # 用户任务优先
        pm.wait_if_p0_active(timeout=30)

        title = entry.get("title", "")
        if not title:
            continue
        query = f"{title} 详细参数 技术方案 用户评价 2026"
        result = registry.call("deep_research", query)
        if result.get("success") and len(result.get("data", "")) > 200:
            refined = _refine_with_llm(result["data"], query)
            if refined and len(refined) > 50:
                add_knowledge(
                    title=f"深化:{title[:30]}",
                    domain=entry.get("domain", "lessons"),
                    content=refined[:800],
                    tags=entry.get("tags", []) + ["night_deep"],
                    source="night_deep_learning",
                    confidence="medium",
                    caller="self_learning"
                )
                new_count += 1
                report_lines.append(f"  [OK] 深化: {title[:40]}")
                # 标记原条目已深化
                try:
                    orig_path = Path(entry.get("_filepath", ""))
                    if orig_path.exists():
                        orig_data = json.loads(orig_path.read_text(encoding="utf-8"))
                        if "night_deepened" not in orig_data.get("tags", []):
                            orig_data.setdefault("tags", []).append("night_deepened")
                            orig_path.write_text(json.dumps(orig_data, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
        # 夜间只打印不推送
        if new_count % 3 == 0:
            print(f"  [NightLearn] 深化中... {new_count} 条")

    # === 阶段 2：知识库拓展——找覆盖盲区 ===
    report_lines.append("\n--- Phase 2: 知识库拓展 ---")
    kb_stats = get_knowledge_stats()

    # 读取已拓展历史
    EXPANDED_FILE = Path(__file__).parent.parent / ".ai-state" / "night_expanded.json"
    expanded_history = []
    if EXPANDED_FILE.exists():
        try:
            expanded_history = json.loads(EXPANDED_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    expanded_exclude = "\n".join(list(set(expanded_history[-200:]))) if expanded_history else "暂无"

    expand_prompt = (
        f"你是智能骑行头盔研发中心的学习规划师。\n"
        f"当前知识库覆盖：{kb_stats}\n"
        f"以下主题已经拓展过（不要重复）：\n{expanded_exclude}\n\n"
        f"请分析知识库的覆盖盲区，生成 15 个深度搜索词，分三类：\n"
        f"1. 竞品深挖（5个）：我们可能还没覆盖的头盔品牌、新品、拆解分析\n"
        f"2. 技术深挖（5个）：HUD、摄像头、跌倒检测、骨传导、新材料等具体方案\n"
        f"3. 标准法规（5个）：中国GB、欧洲ECE、美国DOT、EMC认证的具体要求\n"
        f"每个搜索词要具体（含品牌名/标准编号/芯片型号），不要泛泛。\n"
        f"只输出 JSON 数组：[{{\"query\": \"搜索词\", \"domain\": \"分类\", \"tags\": [\"标签\"]}}]"
    )

    expand_result = gateway.call_azure_openai("cpo", expand_prompt, "只输出 JSON 数组。", "night_expand")
    expand_topics = []
    if expand_result.get("success"):
        try:
            resp = expand_result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            expand_topics = json.loads(resp)
        except Exception:
            pass

    for topic in expand_topics[:15]:
        # 用户任务优先
        pm.wait_if_p0_active(timeout=30)

        query = topic.get("query", "")
        domain = topic.get("domain", "lessons")
        tags = topic.get("tags", [])
        if not query:
            continue
        # 强制 domain 白名单
        if domain not in ("competitors", "components", "standards", "lessons"):
            domain = "lessons"

        result = registry.call("deep_research", query)
        if result.get("success") and len(result.get("data", "")) > 200:
            refined = _refine_with_llm(result["data"], query)
            if refined and len(refined) > 50:
                add_knowledge(
                    title=query[:50],
                    domain=domain,
                    content=refined[:800],
                    tags=tags + ["night_expand"],
                    source="night_deep_learning",
                    confidence="medium",
                    caller="self_learning"
                )
                new_count += 1
                report_lines.append(f"  [OK] 拓展: {query[:40]}")
                # 记录已拓展主题
                expanded_history.append(query[:50])
        # 夜间只打印不推送
        if new_count % 5 == 0:
            print(f"  [NightLearn] 拓展中... {new_count} 条")

    # === 阶段 3：跨界灵感（动态生成） ===
    report_lines.append("\n--- Phase 3: 跨界探索 ---")

    # 读取已拓展历史（Phase 2 和 Phase 3 共享）
    all_expanded = list(set(expanded_history[-100:]))  # 去重
    expanded_exclude_text = "\n".join(all_expanded[-30:]) if all_expanded else "暂无"

    cross_prompt = (
        f"你是智能骑行头盔研发中心的学习规划师。\n"
        f"请生成 8 个跨界探索搜索词，用于从其他行业获取灵感。\n"
        f"要求：\n"
        f"1. 每个搜索词涉及不同行业（汽车、滑雪、建筑、军事、医疗、航空等）\n"
        f"2. 与智能头盔有潜在技术或设计关联\n"
        f"3. 具体（含品牌名/技术名/产品名），不要泛泛\n"
        f"4. 加入 2026 或 latest 等时间词\n"
        f"5.【重要】以下主题已经搜过，绝对不要重复：\n{expanded_exclude_text}\n\n"
        f"只输出 JSON 数组：[\"搜索词1\", \"搜索词2\", ...]"
    )

    cross_result = gateway.call_azure_openai("cpo", cross_prompt, "只输出 JSON 数组。", "night_cross")
    cross_topics = []
    if cross_result.get("success"):
        try:
            resp = cross_result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            cross_topics = json.loads(resp)
        except Exception:
            pass

    if not cross_topics:
        # fallback 到固定列表
        cross_topics = [
            "智能摩托车头盔 新品 2026",
            "AR 运动眼镜 最新技术",
            "军用头盔 通讯系统 集成方案",
        ]

    for query in cross_topics:
        # 用户任务优先
        pm.wait_if_p0_active(timeout=30)

        result = registry.call("deep_research", query)
        # 记录已搜过（不管成功失败）
        expanded_history.append(query[:50])
        if result.get("success") and len(result.get("data", "")) > 200:
            refined = _refine_with_llm(result["data"], query)
            if refined and len(refined) > 50:
                add_knowledge(
                    title=f"跨界:{query[:30]}",
                    domain="lessons",
                    content=refined[:800],
                    tags=["night_cross", "跨界"],
                    source="night_deep_learning",
                    confidence="medium",
                    caller="self_learning"
                )
                new_count += 1
                report_lines.append(f"  [OK] 跨界: {query[:40]}")

    # 保存已拓展历史
    if expanded_history:
        try:
            EXPANDED_FILE.parent.mkdir(parents=True, exist_ok=True)
            EXPANDED_FILE.write_text(json.dumps(expanded_history[-200:], ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    stats = get_knowledge_stats()
    report_lines.append(f"\n[Stats] 知识库: {stats}, 总计 {sum(stats.values())} 条")
    report_lines.append(f"[Summary] 本次新增: {new_count} 条")

    report = "\n".join(report_lines)
    print(report)

    # === 29c: 夜间学习结束后自动生成对齐报告 ===
    try:
        alignment = generate_alignment_report()
        # 保存到文件
        reports_dir = Path(__file__).parent.parent / ".ai-state" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = reports_dir / f"alignment_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        report_path.write_text(alignment, encoding="utf-8")
        print(f"\n[Alignment] 对齐报告已生成: {report_path}")
        print(alignment[:500])

        # === 自主研究：基于对齐报告自动发起（每晚只触发一次） ===
        AUTO_RESEARCH_FLAG = Path(__file__).parent.parent / ".ai-state" / f"auto_research_{datetime.now().strftime('%Y%m%d')}.flag"
        if not AUTO_RESEARCH_FLAG.exists():
            print("[AutoResearch] 今晚首次触发，开始自主研究...")
            try:
                # 夜间不推送进度，传 None
                auto_report = auto_schedule_research(alignment, progress_callback=None)
                AUTO_RESEARCH_FLAG.write_text(datetime.now().isoformat(), encoding="utf-8")
                print(f"[AutoResearch] 完成")
                report += f"\n\n{auto_report}"
                # 夜间只打印不推送
                print(auto_report[:500])
            except Exception as ar_e:
                import traceback
                print(f"[AutoResearch] 失败: {ar_e}")
                print(traceback.format_exc())
        else:
            print("[AutoResearch] 今晚已执行过，跳过")
    except Exception as e:
        import traceback
        print(f"[Alignment] 报告生成失败: {e}")
        print(traceback.format_exc())

    # === 自主深挖：每晚自动判断该深挖什么，执行一批 ===
    DEEPDIVE_FLAG = Path(__file__).parent.parent / ".ai-state" / f"deepdive_{datetime.now().strftime('%Y%m%d')}.flag"
    if not DEEPDIVE_FLAG.exists():
        try:
            print("[AutoDeepDive] 开始今晚的自主深挖")
            from scripts.knowledge_graph_expander import run_autonomous_deep_dive
            # 夜间不推送进度，传 None
            dd_report = run_autonomous_deep_dive(progress_callback=None)
            DEEPDIVE_FLAG.write_text(datetime.now().isoformat(), encoding="utf-8")
            report += f"\n\n{dd_report}"
            # 夜间只打印不推送
            print(f"[AutoDeepDive] 自主深挖完成\n{dd_report[:500]}")
        except Exception as e:
            import traceback
            print(f"[AutoDeepDive] 失败: {e}")
            print(traceback.format_exc())
    else:
        print("[AutoDeepDive] 今晚已执行过")

    # === 知识自完整性检测（每 3 天一次） ===
    COMPLETENESS_FLAG = Path(__file__).parent.parent / ".ai-state" / f"completeness_{datetime.now().strftime('%Y%m%d')}.flag"
    day_of_year = datetime.now().timetuple().tm_yday
    if day_of_year % 3 == 0 and not COMPLETENESS_FLAG.exists():
        try:
            print("[Completeness] 触发自完整性检测")
            from scripts.knowledge_completeness_checker import run_completeness_check
            # 夜间不推送进度，传 None
            comp_report = run_completeness_check(progress_callback=None)
            COMPLETENESS_FLAG.write_text(datetime.now().isoformat(), encoding="utf-8")
            report += f"\n\n{comp_report}"
            # 夜间只打印不推送
            print(comp_report[:500])
        except Exception as e:
            import traceback
            print(f"[Completeness] 失败: {e}")
            print(traceback.format_exc())

    # 任务完成提示音
    from src.utils.notifier import notify
    notify("success")

    return report


def auto_schedule_research(alignment_report: str, progress_callback=None) -> str:
    """基于对齐报告 + 主动建议队列，自动发起深度研究"""
    from src.utils.model_gateway import get_model_gateway

    gateway = get_model_gateway()

    # === 读取最近 7 天已完成的研究标题，避免重复 ===
    recent_reports = []
    reports_dir = Path(__file__).parent.parent / ".ai-state" / "reports"
    if reports_dir.exists():
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=7)
        for f in sorted(reports_dir.glob("*.md"), reverse=True)[:50]:
            try:
                if datetime.fromtimestamp(f.stat().st_mtime) > cutoff:
                    # 从文件名或第一行提取标题
                    first_line = f.read_text(encoding="utf-8").split("\n")[0][:100]
                    recent_reports.append(first_line.strip("# ").strip())
            except:
                continue

    recent_exclude = "\n".join(recent_reports[:20]) if recent_reports else "暂无"

    # === 读取主动建议中的知识缺口队列 ===
    queue_context = ""
    queue_file = Path(__file__).parent.parent / ".ai-state" / "auto_research_queue.json"
    if queue_file.exists():
        try:
            queue = json.loads(queue_file.read_text(encoding="utf-8"))
            if queue:
                queue_context = "\n\n## 研发任务中发现的知识缺口（优先研究）\n"
                for item in queue[-5:]:
                    queue_context += f"- 来自任务「{item.get('task_goal', '')[:50]}」: {item.get('advice', '')[:200]}\n"
                # 读完清空
                queue_file.write_text("[]", encoding="utf-8")
        except:
            pass

    # === 读取产品目标 ===
    goal_file = Path(__file__).parent.parent / ".ai-state" / "product_goal.json"
    goal_text = ""
    if goal_file.exists():
        try:
            goal_data = json.loads(goal_file.read_text(encoding="utf-8"))
            goal_text = goal_data.get("goal", "")
        except:
            pass

    goal_context = f"\n\n## 产品目标（研究主题必须服务于此目标）\n{goal_text}\n" if goal_text else ""

    # 让 LLM 从对齐报告 + 队列中提取可执行的研究任务
    extract_prompt = (
        f"你是智能摩托车全盔项目的研究规划师。\n\n"
        f"## 你的任务\n"
        f"基于对齐报告和知识缺口，规划 2-3 个深度研究任务。\n\n"
        f"## 最近 7 天已完成的研究（绝对不要重复这些主题）\n{recent_exclude}\n\n"
        f"{goal_context}"
        f"## 规划原则\n"
        f"1. 不要选太泛的主题（如'智能头盔市场分析'），要选具体到可以搜到数据的（如'高通AR1 vs 恒玄BES2800 功耗对比'）\n"
        f"2. 至少一个主题应该是'跨领域关联'——从别的行业借鉴（如'汽车ADAS供应商向摩托车迁移的案例'）\n"
        f"3. 优先填补知识缺口队列中的空白\n"
        f"4. 搜索词要能搜到英文 datasheet 和中文行业报告（各一半）\n\n"
        f"## 输出格式\n"
        f"JSON 数组，每个元素：\n"
        f'{{"title": "具体主题（含品牌/型号）", '
        f'"goal": "这个研究要回答的一个核心问题", '
        f'"searches": ["英文搜索词1", "中文搜索词2", "英文搜索词3", "中文搜索词4"]}}\n\n'
        f"## 对齐报告\n{alignment_report[:2000]}"
        f"{queue_context}"
    )

    result = gateway.call_azure_openai("cpo", extract_prompt, "只输出 JSON 数组。", "auto_research_plan")
    if not result.get("success"):
        return "[AutoResearch] LLM 提取失败"

    resp = result["response"].strip()
    resp = re.sub(r'^```json\s*', '', resp)
    resp = re.sub(r'^```\s*', '', resp)
    resp = re.sub(r'\s*```$', '', resp)

    try:
        tasks = json.loads(resp)
    except:
        return "[AutoResearch] JSON 解析失败"

    if not isinstance(tasks, list) or not tasks:
        return "[AutoResearch] 无有效研究任务"

    # 执行研究
    from scripts.tonight_deep_research import deep_research_one

    report_lines = [f"[AutoResearch] 自动发起 {len(tasks[:3])} 个研究任务"]

    for i, task in enumerate(tasks[:3], 1):
        task_dict = {
            "id": f"auto_{datetime.now().strftime('%Y%m%d')}_{i}",
            "title": task.get("title", f"自动研究{i}"),
            "goal": task.get("goal", ""),
            "searches": task.get("searches", [])
        }

        if progress_callback:
            progress_callback(f"[{i}/{len(tasks[:3])}]: {task_dict['title'][:20]}...")

        try:
            report = deep_research_one(task_dict, progress_callback=progress_callback)

            # === 自评研究质量 ===
            quality_check = gateway.call_azure_openai("cpo",
                f"以下研究报告是否有价值？标准：包含具体数据（型号/参数/价格）、有明确结论、能帮助决策。\n"
                f"只回答 HIGH/MEDIUM/LOW 和一句话理由。\n\n{report[:3000]}",
                "只输出 HIGH/MEDIUM/LOW 和理由。", "auto_research_quality")

            quality = "?"
            if quality_check.get("success"):
                resp = quality_check["response"].strip().upper()
                if "HIGH" in resp:
                    quality = "HIGH"
                elif "LOW" in resp:
                    quality = "LOW"
                else:
                    quality = "MEDIUM"

            report_lines.append(f"  OK {task_dict['title'][:40]} ({len(report)} chars, quality:{quality})")
        except Exception as e:
            report_lines.append(f"  FAIL {task_dict['title'][:40]}: {e}")

        time.sleep(5)

    return "\n".join(report_lines)


def audit_knowledge_base() -> dict:
    """审计知识库质量，返回审计报告"""
    from src.tools.knowledge_base import KB_ROOT

    if not KB_ROOT.exists():
        return {"total": 0}

    total = 0
    shallow = 0  # < 150 字
    medium = 0   # 150-300 字
    deep = 0     # > 300 字
    no_data = 0  # 无具体数据
    duplicates = 0

    seen_fingerprints = set()
    import hashlib

    shallow_entries = []  # 需要深化的浅条目

    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            content = data.get("content", "")
            title = data.get("title", "")
            total += 1

            # 深度分布
            if len(content) < 150:
                shallow += 1
                if data.get("type") != "report" and "night_deepened" not in data.get("tags", []):
                    shallow_entries.append({
                        "path": str(f),
                        "title": title[:50],
                        "domain": data.get("domain", ""),
                        "content_len": len(content)
                    })
            elif len(content) < 300:
                medium += 1
            else:
                deep += 1

            # 重复检测
            fp = hashlib.md5(f"{title[:30]}||{content[:200]}".encode()).hexdigest()
            if fp in seen_fingerprints:
                duplicates += 1
            seen_fingerprints.add(fp)

            # 无数据检测
            has_number = bool(re.search(r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|USD|\$|%|nits)', content))
            has_model = bool(re.search(r'[A-Z]{2,}\d{2,}|IMX\d|QCC\d|BES\d|ECE\s*\d', content))
            if not has_number and not has_model:
                no_data += 1
                # 无数据条目也加入待深化列表
                if data.get("type") != "report" and "night_deepened" not in data.get("tags", []):
                    shallow_entries.append({
                        "path": str(f),
                        "title": title[:50],
                        "domain": data.get("domain", ""),
                        "content_len": len(content),
                        "reason": "no_data"
                    })

        except:
            continue

    shallow_pct = round(shallow / total * 100, 1) if total > 0 else 0

    return {
        "total": total,
        "shallow": shallow,
        "shallow_pct": shallow_pct,
        "medium": medium,
        "deep": deep,
        "no_data": no_data,
        "duplicates": duplicates,
        "shallow_entries": shallow_entries[:20],  # 最多返回 20 个待深化
    }


def generate_daily_report() -> str:
    """生成每日学习日报"""
    from src.tools.knowledge_base import get_knowledge_stats, KB_ROOT

    stats = get_knowledge_stats()
    total = sum(stats.values())

    lines = [f"[Daily Report] {datetime.now().strftime('%Y-%m-%d')} 学习日报"]
    lines.append("=" * 35)

    # 知识库总量
    lines.append(f"\n[KB Total] {total} 条")
    for domain in sorted(stats.keys()):
        lines.append(f"  {domain}: {stats[domain]}")

    # 过去 24 小时新增
    yesterday = datetime.now() - timedelta(hours=24)
    new_today = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime) > yesterday:
                data = json.loads(f.read_text(encoding="utf-8"))
                new_today.append({
                    "title": data.get("title", "")[:40],
                    "domain": f.parent.name,
                    "source": data.get("source", "")[:15]
                })
        except Exception:
            continue

    lines.append(f"\n[New 24h] {len(new_today)} 条新增")
    # 按来源分组
    by_source = {}
    for entry in new_today:
        src = entry["source"]
        if src not in by_source:
            by_source[src] = []
        by_source[src].append(entry)

    for src, entries in by_source.items():
        lines.append(f"\n  [{src}] {len(entries)} 条:")
        for e in entries[:5]:
            lines.append(f"    - [{e['domain']}] {e['title']}")
        if len(entries) > 5:
            lines.append(f"    ... 及其他 {len(entries)-5} 条")

    # 经验卡片统计
    memory_dir = Path(__file__).parent.parent / ".ai-state" / "memory"
    if memory_dir.exists():
        cards = list(memory_dir.glob("*.json"))
        recent_cards = [f for f in cards if datetime.fromtimestamp(f.stat().st_mtime) > yesterday]
        lines.append(f"\n[Tasks 24h] {len(recent_cards)} 个研发任务")
        for f in recent_cards[:3]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                goal = data.get("task_goal", "")[:40]
                rating = data.get("user_rating", "未评")
                lines.append(f"  - {goal} [评价:{rating}]")
            except Exception:
                continue

    # 进化记录
    evo_dir = Path(__file__).parent.parent / ".ai-state" / "evolution"
    if evo_dir.exists():
        recent_evo = [f for f in evo_dir.glob("*.json") if datetime.fromtimestamp(f.stat().st_mtime) > yesterday]
        if recent_evo:
            lines.append(f"\n[Evolution] {len(recent_evo)} 次自动复盘")

    # 知识深度分布
    all_depths = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            all_depths.append(len(data.get("content", "")))
        except Exception:
            continue

    shallow = sum(1 for d in all_depths if d < 150)
    medium_d = sum(1 for d in all_depths if 150 <= d < 300)
    deep = sum(1 for d in all_depths if d >= 300)

    lines.append(f"\n[Depth] 浅:{shallow} | 中:{medium_d} | 深:{deep}")

    # 知识鲜度
    week_ago = datetime.now() - timedelta(days=7)
    fresh = sum(1 for f in KB_ROOT.rglob("*.json") if datetime.fromtimestamp(f.stat().st_mtime) > week_ago)
    lines.append(f"[Fresh] 7天内: {fresh}/{total} 条")

    # Token 使用统计
    try:
        from src.utils.token_usage_tracker import TokenUsageTracker
        _tracker = TokenUsageTracker()
        _today_tokens = _tracker.get_today_stats()
        _week_tokens = _tracker.get_stats(days=7)

        lines.append(f"\n[Token] 今日: {_today_tokens['total_tokens']:,} | 7日: {_week_tokens['total_tokens']:,}")
        lines.append(f"  今日成本: ${_today_tokens['total_cost']:.4f} | 7日: ${_week_tokens['total_cost']:.4f}")

        # 模型分布
        _ranking = _tracker.get_model_ranking(days=7)
        if _ranking:
            lines.append(f"  主力模型: {_ranking[0]['model']} ({_ranking[0]['calls']}次)")
    except Exception:
        pass

    # 知识库质量审计
    try:
        audit = audit_knowledge_base()
        lines.append(f"\n[Quality] 浅条目: {audit['shallow']}({audit['shallow_pct']}%) | 无数据: {audit['no_data']} | 重复: {audit['duplicates']}")
        if audit['shallow_pct'] > 15:
            lines.append(f"  浅条目占比过高，夜间学习将优先深化")
    except Exception:
        pass

    lines.append(f"\n{'=' * 35}")
    lines.append("发送「知识库」查看详情 | 发送「token」查看用量")

    return "\n".join(lines)


def start_daily_scheduler(interval_hours: float = 2.0, feishu_notify=None):
    """启动定时学习线程，默认每 2 小时一轮"""
    # === 启动资源自动管理（每 2 小时清理一次）===
    from scripts.resource_manager import start_resource_monitor, auto_cleanup
    auto_cleanup()  # 启动时先清理一轮
    start_resource_monitor(interval_hours=2.0, feishu_notify=feishu_notify)

    def _scheduler():
        while True:
            # 检查是否该推送日报（每天 7:30）
            current_hour = datetime.now().hour
            current_min = datetime.now().minute
            if current_hour == 7 and 25 <= current_min <= 35:
                try:
                    report = generate_daily_report()
                    print(report)
                    if feishu_notify:
                        feishu_notify(report)
                    print("[DailyReport] 日报已推送")
                    time.sleep(3600)  # 推送后等 1 小时避免重复
                    continue
                except Exception as e:
                    print(f"[DailyReport] 推送失败: {e}")

            # 检查是否在夜间深度学习窗口（1:00-5:00）
            if 1 <= current_hour < 5:
                print(f"[NightLearn] 夜间深度学习 ({current_hour}:{datetime.now().minute:02d})")
                try:
                    report = run_night_deep_learning(
                        progress_callback=lambda msg: feishu_notify(msg) if feishu_notify else None
                    )
                    if feishu_notify:
                        feishu_notify(report)
                except Exception as e:
                    print(f"[NightLearn] 失败: {e}")
                    if feishu_notify:
                        feishu_notify(f"[NightLearn] 失败: {e}")
                # 夜间每 30 分钟一轮（而非 30 分钟固定等待）
                elapsed = (datetime.now() - datetime.now().replace(minute=0, second=0)).total_seconds()
                wait = max(600, 1800 - elapsed)  # 至少等 10 分钟
                time.sleep(wait)
                continue

            from src.tools.knowledge_base import get_knowledge_stats
            stats = get_knowledge_stats()
            total = sum(stats.values())

            # 永远保持 30 分钟一轮学习
            wait_hours = 0.5

            wait_seconds = wait_hours * 3600
            next_run = datetime.now() + timedelta(hours=wait_hours)
            print(f"[DailyLearning] 知识库 {total} 条，30分钟后下次学习（约 {next_run.strftime('%H:%M')}）")
            time.sleep(wait_seconds)

            print(f"[DailyLearning] 开始学习轮次...")
            try:
                report = run_daily_learning(
                    progress_callback=lambda msg: feishu_notify(msg) if feishu_notify else None
                )
                if feishu_notify:
                    feishu_notify(report)

                # === 每天第一次学习时顺带跑平台监控 ===
                try:
                    from scripts.platform_monitor import run_platform_monitor
                    pm_state_file = Path(__file__).parent.parent / ".ai-state" / "platform_monitor_state.json"
                    should_run = True
                    if pm_state_file.exists():
                        try:
                            pm_state = json.loads(pm_state_file.read_text(encoding="utf-8"))
                            last_run = pm_state.get("last_run", "")
                            if last_run and last_run[:10] == datetime.now().strftime("%Y-%m-%d"):
                                should_run = False  # 今天已跑过
                        except Exception:
                            pass
                    if should_run:
                        print("[DailyLearning] 触发每日平台监控...")
                        pm_report = run_platform_monitor(since_days=7, feishu_notify=feishu_notify)
                        print(pm_report)
                except Exception as pm_err:
                    print(f"[DailyLearning] 平台监控失败: {pm_err}")

            except Exception as e:
                print(f"[DailyLearning] 学习失败: {e}")
                if feishu_notify:
                    feishu_notify(f"[NightLearn] 学习失败: {e}")

    print("[DailyLearning] 定时学习已启动（每30分钟）")
    t = threading.Thread(target=_scheduler, daemon=True)
    t.start()
    return t


# ==========================================
# Phase 29c: 每日对齐报告
# ==========================================
def generate_alignment_report() -> str:
    """生成每日对齐报告——不只是数字，而是认知变化和行动建议"""
    from src.tools.knowledge_base import get_knowledge_stats, KB_ROOT
    from src.utils.model_gateway import get_model_gateway

    gateway = get_model_gateway()
    stats = get_knowledge_stats()
    total = sum(stats.values())

    # 收集今日新增条目
    today = datetime.now().strftime("%Y%m%d")
    today_items = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            if today in f.name:
                data = json.loads(f.read_text(encoding="utf-8"))
                today_items.append({
                    "title": data.get("title", "")[:60],
                    "domain": f.parent.name,
                    "tags": data.get("tags", []),
                    "source": data.get("source", ""),
                    "is_report": data.get("type") == "report"
                })
        except:
            continue

    # 分析维度覆盖
    dimension_counts = {}
    target_dimensions = {
        "HUD/AR显示": ["HUD", "AR", "光机", "光波导", "Micro OLED", "近眼显示", "waveguide"],
        "4K摄像": ["4K", "摄像", "IMX", "EIS", "防抖", "行车记录", "camera", "dashcam"],
        "ANC/ENC降噪": ["ANC", "ENC", "降噪", "风噪", "通话", "麦克风阵列", "noise cancellation"],
        "ADAS安全": ["ADAS", "盲区", "碰撞预警", "前向预警", "雷达", "AEB", "APA", "RPA",
                     "BSD", "LDW", "FCW", "ACC", "主动安全", "被动安全", "预警",
                     "blind spot", "collision", "emergency braking", "lane departure",
                     "泊车", "避障", "毫米波", "超声波", "USS", "ARAS"],
        "SoC/芯片": ["AR1", "BES2800", "高通", "恒玄", "SoC", "芯片", "Nordic", "nRF",
                     "QCC", "J6", "Orin", "TDA4", "征程", "horizon"],
        "认证标准": ["ECE", "DOT", "3C", "FCC", "CE RED", "UN38.3", "GB 811", "FMVSS",
                    "ENCAP", "CNCAP", "EN 1078", "NTA"],
        "供应商/JDM": ["歌尔", "Goertek", "JDM", "ODM", "供应商", "代工", "立讯", "Luxshare"],
        "Mesh对讲": ["Mesh", "对讲", "自组网", "Sena", "Cardo", "intercom", "DMC"],
        "电池/散热": ["电池", "散热", "热管理", "温控", "mAh", "充电", "thermal"],
        "结构/材料": ["碳纤维", "玻纤", "EPS", "壳体", "模具", "重量", "MIPS", "carbon fiber"]
    }

    for dim_name, keywords in target_dimensions.items():
        count = 0
        for f in KB_ROOT.rglob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                text = (data.get("title", "") + " " + data.get("content", "")[:200]).lower()
                if any(kw.lower() in text for kw in keywords):
                    count += 1
            except:
                continue
        dimension_counts[dim_name] = count

    sorted_dims = sorted(dimension_counts.items(), key=lambda x: -x[1])

    # 收集今日新增的标题列表给 LLM 分析
    today_titles = [item["title"] for item in today_items[:30]]
    report_count = sum(1 for item in today_items if item.get("is_report"))

    # === 注入产品锚点 ===
    product_anchor = ""
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            tags = data.get("tags", [])
            if "internal" in tags and ("prd" in tags or "product_definition" in tags):
                product_anchor = data.get("content", "")[:1500]
                break
        except:
            continue

    anchor_context = ""
    if product_anchor:
        anchor_context = (
            f"\n## 产品定义锚点（不可违背）\n"
            f"本项目是智能摩托车全盔（不是自行车头盔），HUD/AR显示、4K摄像、ADAS安全均为P0。\n"
            f"你的所有建议必须在此框架内。可以建议分V1/V2阶段，但不能建议'不做'某个P0功能。\n"
            f"{product_anchor[:1000]}\n"
        )

    # 让 LLM 生成认知分析
    analysis_prompt = (
        f"你是智能摩托车头盔项目的研发总监。{anchor_context}\n\n"
        f"以下是今天知识库的变化。\n\n"
        f"## 知识库总量: {total} 条\n"
        f"## 今日新增: {len(today_items)} 条（含 {report_count} 份深度报告）\n\n"
        f"## 今日新增标题:\n" + "\n".join([f"- {t}" for t in today_titles[:20]]) + "\n\n"
        f"## 各维度覆盖:\n" + "\n".join([f"- {d}: {c}条" for d, c in sorted_dims]) + "\n\n"
        f"请分析并输出以下内容（总共 500 字以内）：\n"
        f"1. 【新发现】今天的学习中有什么值得注意的新信息？（2-3 条）\n"
        f"2. 【认知变化】基于今天的信息，对项目决策有什么新的判断？\n"
        f"3. 【知识缺口】哪些维度最薄弱，明天应该重点补？\n"
        f"4. 【行动建议】建议明天做什么？（具体的研究任务或学习方向）\n"
    )

    result = gateway.call_azure_openai("cpo", analysis_prompt,
        "你是研发总监，输出简洁的每日对齐分析。", "alignment_report")

    if result.get("success"):
        analysis = result["response"]
    else:
        analysis = "LLM 分析失败"

    # 组装报告
    report = f"📊 每日对齐报告 ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n\n"
    report += f"知识库: {total} 条 | 今日新增: {len(today_items)} 条 | 深度报告: {report_count} 份\n"
    report += f"分布: {json.dumps(stats, ensure_ascii=False)}\n\n"
    report += f"维度覆盖:\n"
    for d, c in sorted_dims:
        bar = "█" * min(c // 5, 20) + "░" * max(0, 10 - c // 5)
        report += f"  {d}: {bar} {c}条\n"
    report += f"\n{analysis}"

    return report


if __name__ == "__main__":
    run_daily_learning()