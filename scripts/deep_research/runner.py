"""
深度研究 — 调度入口
职责: 深度学习主调度器、任务池管理、自主发现、run_all、CLI 入口
被调用方: feishu_handlers, start_all.bat, __main__
依赖: pipeline.py, night_watch.py, learning.py, models.py
"""
import json
import re
import time
import yaml
from datetime import datetime
from pathlib import Path

from src.tools.knowledge_base import (
    get_knowledge_stats, KB_ROOT, get_recent_entries, update_knowledge_flag
)
from scripts.meta_capability import generate_evolution_report

from scripts.deep_research.models import call_model, get_model_for_task
from scripts.deep_research.pipeline import deep_research_one
from scripts.deep_research.night_watch import (
    set_feishu_callback, generate_night_report
)
from scripts.deep_research.learning import (
    generate_knowledge_synthesis, extract_experience_rules,
    scan_decision_readiness,
)

AI_STATE = Path(__file__).resolve().parent.parent.parent / ".ai-state"
REPORT_DIR = AI_STATE / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
TASK_POOL_PATH = AI_STATE / "research_task_pool.yaml"


# ============================================================
# 内置研究任务
# ============================================================
RESEARCH_TASKS = [
    {
        "id": "goertek_profile",
        "title": "歌尔股份完整画像",
        "goal": "回答：歌尔做智能头盔JDM的核心能力、已有客户案例、产能规模、大致报价水平、优势和风险",
        "searches": [
            "Goertek smart wearable ODM JDM capability 2025 2026 annual report",
            "歌尔股份 2025年报 智能穿戴 营收 客户",
            "Goertek Meta Ray-Ban smart glasses ODM manufacturing details",
            "歌尔 Alpha Labs 智能眼镜 研发能力 团队规模",
            "Goertek XR headset production capacity Weifang factory",
            "歌尔 智能穿戴 代工报价 NRE 模具费 单价",
            "Goertek smart glasses helmet acoustic optical module capability",
            "歌尔股份 竞争优势 劣势 风险 分析师报告 2025",
        ]
    },
    {
        "id": "alternative_jdm",
        "title": "替代JDM供应商对比",
        "goal": "回答：除歌尔外还有哪些供应商能做智能头盔JDM？各自的能力、客户、规模、报价水平如何？",
        "searches": [
            "smart wearable device JDM ODM supplier list 2026 China",
            "智能穿戴 JDM ODM 供应商 完整名单 龙旗 瑞声 歌尔 立讯",
            "Luxshare Precision smart wearable ODM capability customer 2026",
            "立讯精密 智能穿戴 代工 客户 苹果 Meta 产能 报价",
            "BYD Electronics smart device ODM wearable helmet 2026",
            "Longcheer 龙旗控股 智能穿戴 ODM JDM 能力 客户 2026",
            "AAC Technologies 瑞声科技 声学 光学 触觉 智能穿戴 2026",
            "Flex Jabil smart wearable contract manufacturing capability 2026",
            "Pegatron Compal Inventec smart wearable ODM 2026",
            "深圳 东莞 智能头盔 中小型方案商 ODM 案例 2026",
        ]
    },
    {
        "id": "optical_suppliers",
        "title": "光学方案商深度对比",
        "goal": "回答：HUD/AR显示用什么光学方案？每种方案的供应商、参数、成本、成熟度如何？推荐哪个？",
        "searches": [
            "AR HUD optical engine comparison waveguide birdbath freeform prism 2026",
            "Lumus waveguide supplier pricing motorcycle helmet HUD",
            "DigiLens waveguide smart glasses cost volume production 2026",
            "珑璟光电 灵犀微光 谷东科技 光波导 参数 价格 对比",
            "Micro OLED display Sony JBD BOE Kopin comparison specs price 2026",
            "BirdBath optical solution smart helmet HUD cost weight analysis",
            "motorcycle helmet HUD optical module supplier BOM cost breakdown",
            "光学模组 良率 交期 最小起订量 MOQ 供应商 2026",
        ]
    },
    {
        "id": "audio_camera_suppliers",
        "title": "声学与摄像头方案商对比",
        "goal": "回答：头盔用什么扬声器/麦克风/摄像头？每种方案的供应商、参数、成本对比？",
        "searches": [
            "骨传导扬声器 供应商 韶音 歌尔 瑞声 参数 价格 对比 2026",
            "MEMS microphone Knowles InvenSense Goertek specs price comparison",
            "ANC active noise cancellation chipset BES2700 QCC5181 comparison wearable",
            "微型摄像头 模组 OmniVision Sony IMX 舜宇 丘钛 specs comparison",
            "smart helmet speaker driver waterproof IP67 supplier",
            "helmet intercom microphone wind noise cancellation solution 2026",
            "AAC Technologies acoustic module smart glasses helmet speaker microphone specs",
            "瑞声科技 声学模组 智能眼镜 骨传导 参数 价格 2026",
        ]
    },
    {
        "id": "why_goertek",
        "title": "综合对比：为什么选歌尔（或为什么不选）",
        "goal": "基于前4份研究，给出歌尔 vs 替代方案的综合评估。明确回答：选歌尔的理由、风险、备选方案",
        "searches": [
            "Goertek vs Luxshare smart wearable ODM comparison advantage disadvantage",
            "歌尔 vs 立讯 vs 比亚迪电子 智能穿戴 综合对比 选型建议",
            "smart helmet ODM supplier selection criteria evaluation framework",
            "智能穿戴 JDM 供应商 选型 决策矩阵 权重",
            "Goertek vs AAC Technologies vs Luxshare smart wearable comparison",
            "歌尔 vs 瑞声 vs 龙旗 vs 立讯 智能穿戴 ODM 综合对比",
        ]
    }
]


# ============================================================
# 任务池管理
# ============================================================
def _load_task_pool() -> list:
    if not TASK_POOL_PATH.exists():
        return []
    try:
        with open(TASK_POOL_PATH, 'r', encoding='utf-8') as f:
            pool = yaml.safe_load(f) or []
        return [t for t in pool if not t.get("completed")]
    except:
        return []


def _save_task_pool(pool: list):
    TASK_POOL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TASK_POOL_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(pool, f, allow_unicode=True)


def _mark_task_done(task_id: str):
    all_tasks = []
    if TASK_POOL_PATH.exists():
        try:
            with open(TASK_POOL_PATH, 'r', encoding='utf-8') as f:
                all_tasks = yaml.safe_load(f) or []
        except:
            pass
    for t in all_tasks:
        if t.get("id") == task_id:
            t["completed"] = True
            t["completed_at"] = time.strftime('%Y-%m-%d %H:%M')
    _save_task_pool(all_tasks)


def _get_kb_summary() -> str:
    stats = get_knowledge_stats()
    summary = f"知识库统计: {stats}\n"
    recent = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            recent.append({
                "title": data.get("title", "")[:50],
                "domain": data.get("domain", ""),
            })
        except:
            continue
    if recent:
        summary += f"总条目数: {len(recent)}\n"
        domains = {}
        for e in recent:
            d = e.get("domain", "unknown")
            domains[d] = domains.get(d, 0) + 1
        summary += f"域分布: {domains}\n"
    return summary


# ============================================================
# 自主发现
# ============================================================
def _discover_new_tasks() -> list:
    pool = _load_task_pool()
    existing_titles = [t.get("title", "") for t in pool]

    if REPORT_DIR.exists():
        for f in REPORT_DIR.glob("*.md"):
            existing_titles.append(f.stem.replace("_", " "))

    existing_titles_text = "\n".join(f"- {t}" for t in existing_titles[-30:])
    kb_summary = _get_kb_summary()

    discover_prompt = (
        f"你是智能骑行头盔项目的研究规划师。\n\n"
        f"## 当前知识库状态\n{kb_summary}\n\n"
        f"## 产品方向\n全脸头盔，HUD显示，语音控制，组队骑行，主动安全。\n\n"
        f"## 已有任务（避免重复）\n{existing_titles_text}\n\n"
        f"## 任务\n分析知识库薄弱环节，生成 3-5 个新研究任务。\n"
        f"优先级: 1=紧急, 2=重要, 3=储备\n\n"
        f"输出 JSON 数组:\n"
        f'[{{"id": "auto_xxx", "title": "标题", "goal": "目标", '
        f'"priority": 1, "searches": ["搜索词1", "搜索词2"]}}]\n只输出 JSON。'
    )

    result = call_model("gemini_2_5_flash", discover_prompt, task_type="discovery")
    if result.get("success"):
        try:
            resp = result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            tasks = json.loads(resp)
            if isinstance(tasks, list):
                # 去重
                deduped = []
                for task in tasks:
                    new_title = task.get("title", "")
                    is_duplicate = False
                    for existing in existing_titles:
                        new_words = set(re.findall(r'[\u4e00-\u9fff]{2,4}', new_title))
                        old_words = set(re.findall(r'[\u4e00-\u9fff]{2,4}', existing))
                        overlap = new_words & old_words
                        if len(overlap) >= 3 and len(overlap) / max(len(new_words), 1) > 0.5:
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        # === BUG FIX: 确保 searches 是 list ===
                        if not isinstance(task.get("searches"), list):
                            task["searches"] = [task.get("title", "unknown") + " 2026"]
                        deduped.append(task)
                print(f"  [Discover] 去重后: {len(tasks)} → {len(deduped)}")
                return deduped
        except:
            pass
    return []


def _discover_from_decision_tree() -> list:
    """从决策树缺口中发现任务（BUG FIX: searches 改为 list）"""
    try:
        dt_path = AI_STATE / "product_decision_tree.yaml"
        if not dt_path.exists():
            return []
        dt = yaml.safe_load(dt_path.read_text(encoding='utf-8'))
        tasks = []
        for d in dt.get("decisions", []):
            resolved = d.get("resolved_knowledge", 0)
            needed = d.get("total_needed", 3)
            if resolved < needed:
                question = d.get('question', '')
                tasks.append({
                    "id": f"dt_{d.get('id', 'unknown')}",
                    "title": f"决策补充: {question[:40]}",
                    "goal": f"补充决策所需信息: {question}。目前进度 {resolved}/{needed}。",
                    "priority": 2,
                    # BUG FIX: 原来是 int(4)，现在生成搜索词列表
                    "searches": [
                        f"{question[:30]} motorcycle helmet 2026",
                        f"{question[:30]} 智能头盔 技术参数 对比",
                        f"{question[:30]} supplier cost analysis",
                        f"{question[:30]} 方案对比 优劣势",
                    ],
                    "source": "decision_tree_gap"
                })
        if tasks:
            print(f"  [DecisionTree] 发现 {len(tasks)} 个补充任务")
        return tasks
    except Exception as e:
        print(f"  [DecisionTree] 发现失败: {e}")
        return []


# ============================================================
# Pre-flight 健康检查（完整版：覆盖四通道搜索 + Critic 所有模型）
# ============================================================
def _pre_flight_api_check(progress_callback=None) -> bool:
    """验证所有关键模型是否可用，不可用的自动禁用（跳过而非重复 404）"""
    from scripts.deep_research.models import (
        call_model as _call, disable_model, reset_disabled_models
    )

    # 每次深度学习开始前重置禁用列表
    reset_disabled_models()

    results = {}
    # 深度学习管道用到的所有模型，按重要性分层
    critical = ["gpt_5_4", "gemini_2_5_flash"]
    # 四通道搜索 + Agent + Critic 用到的全部模型
    important = [
        "o3_deep_research",       # L1 Channel A
        "doubao_seed_pro",        # L1 Channel B
        "grok_4",                 # L1 Channel C
        "gemini_deep_research",   # L1 Channel D
        "gpt_4o_norway",          # CMO + 多处降级目标
        "deepseek_v3_volcengine", # CDO
        "gemini_2_5_pro",         # L4 synthesis
        "gemini_3_1_pro",         # Critic
        "deepseek_r1_volcengine", # Critic cross + verifier
        "o3",                     # Critic cross
        "glm_4_7",                # 守夜诊断
    ]

    for model in critical + important:
        try:
            r = _call(model, "Ping", task_type="health_check")
            results[model] = "OK" if r.get("success") else f"FAIL: {str(r.get('error', ''))[:30]}"
        except Exception as e:
            results[model] = f"FAIL: {str(e)[:30]}"

    # 禁用失败的非核心模型（避免运行时重复 404）
    disabled_count = 0
    for model in important:
        if "FAIL" in results.get(model, "FAIL"):
            disable_model(model)
            disabled_count += 1

    unavailable_critical = [m for m in critical if "FAIL" in results.get(m, "FAIL")]

    status_msg = "API 健康检查:\n" + "\n".join([f"  {m}: {s}" for m, s in results.items()])

    if unavailable_critical:
        status_msg += f"\n\n核心模型不可用: {unavailable_critical}，深度学习暂停"
        if progress_callback:
            progress_callback(status_msg)
        print(status_msg)
        return False

    if disabled_count > 0:
        status_msg += f"\n\n{disabled_count} 个非核心模型不可用，已禁用（本轮自动跳过，走降级链）"
    else:
        status_msg += "\n\n所有模型可用 ✅"

    if progress_callback:
        progress_callback(status_msg)
    print(status_msg)
    return True


# ============================================================
# run_all（内置任务）
# ============================================================
def run_all(progress_callback=None):
    current_hour = datetime.now().hour
    is_night = current_hour >= 23 or current_hour < 7

    print(f"\n{'#' * 60}")
    print(f"# 智能骑行头盔 JDM 供应商选型 — 深度研究")
    print(f"# 共 {len(RESEARCH_TASKS)} 个任务")
    print(f"{'#' * 60}")

    effective_callback = None if is_night else progress_callback

    reports = []
    for idx, task in enumerate(RESEARCH_TASKS, 1):
        if effective_callback:
            effective_callback(f"🔍 [{idx}/{len(RESEARCH_TASKS)}] 开始: {task['title']}")
        report = deep_research_one(task, progress_callback=effective_callback)
        reports.append({"title": task["title"], "report": report})
        print(f"\n✅ {task['title']} 完成 ({len(report)} 字)")
        time.sleep(5)

    summary_path = REPORT_DIR / f"jdm_summary_{time.strftime('%Y%m%d_%H%M')}.md"
    summary = "# JDM 供应商选型 — 深度研究汇总\n\n"
    summary += f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M')}\n\n"
    for r in reports:
        summary += f"\n---\n\n# {r['title']}\n\n{r['report']}\n"
    summary_path.write_text(summary, encoding="utf-8")

    print(f"\n# 全部完成！报告: {summary_path}")
    return str(summary_path)


# ============================================================
# 从文件运行 + 一致性校验
# ============================================================
def parse_research_tasks_from_md(md_path: str) -> list:
    content = Path(md_path).read_text(encoding="utf-8")
    tasks = []
    research_pattern = re.compile(r'^# 研究 ([A-Z])：(.+)$', re.MULTILINE)

    for match in research_pattern.finditer(content):
        task_id = f"research_{match.group(1).lower()}"
        title = match.group(2).strip()

        start_pos = match.end()
        next_match = research_pattern.search(content, start_pos)
        end_pos = next_match.start() if next_match else len(content)
        section_content = content[start_pos:end_pos]

        goal_match = re.search(
            r'## [A-Z]\.0\s*(?:研究目标|分析目标)\s*\n([^\n]+(?:\n(?![#])[^\n]+)*)',
            section_content)
        goal = goal_match.group(1).strip() if goal_match else f"深度研究：{title}"

        searches = []
        subtask_pattern = re.compile(r'^#{2,3}\s+[A-Z]\.\d+(?:\.\d+)?\s+(.+)$', re.MULTILINE)
        for sub_match in subtask_pattern.finditer(section_content):
            sub_title = sub_match.group(1).strip()
            searches.append(f"{sub_title} motorcycle helmet HUD specs 2025 2026")

        if not searches:
            searches = [f"{title} motorcycle helmet HUD 2025 2026"]

        tasks.append({
            "id": task_id, "title": title, "goal": goal,
            "searches": searches[:10], "source_file": str(md_path),
        })
    return tasks


def run_research_from_file(md_path: str, progress_callback=None,
                           task_ids: list = None, constraint_context: str = None):
    tasks = parse_research_tasks_from_md(md_path)
    if not tasks:
        print(f"[Warning] 未从 {md_path} 解析到任务")
        return None

    if task_ids:
        tasks = [t for t in tasks if t["id"] in task_ids]
    if not tasks:
        return None

    reports = []
    for idx, task in enumerate(tasks, 1):
        if progress_callback:
            progress_callback(f"🔍 [{idx}/{len(tasks)}] 开始: {task['title']}")
        report = deep_research_one(task, progress_callback=progress_callback,
                                   constraint_context=constraint_context)
        reports.append({"id": task["id"], "title": task["title"], "report": report})
        time.sleep(3)

    # 跨研究一致性校验
    if len(reports) >= 2:
        _check_cross_consistency(reports, progress_callback)

    md_name = Path(md_path).stem
    summary_path = REPORT_DIR / f"{md_name}_summary_{time.strftime('%Y%m%d_%H%M')}.md"
    summary = f"# {md_name} — 深度研究汇总\n\n"
    for r in reports:
        summary += f"\n---\n\n## {r['title']}\n\n{r['report']}\n"
    summary_path.write_text(summary, encoding="utf-8")

    print(f"\n# 全部完成！报告: {summary_path}")
    return str(summary_path)


def _check_cross_consistency(reports: list, progress_callback=None):
    print(f"\n  [ConsistencyCheck] 检查 {len(reports)} 份报告一致性...")
    conclusions = "\n\n".join([f"### {r['title']}\n{r['report'][:2000]}" for r in reports])
    prompt = (
        f"以下是同一个项目的 {len(reports)} 份研究报告。\n"
        f"检查自相矛盾:\n1. 推荐冲突\n2. 参数冲突\n3. 评价冲突\n\n"
        f"输出 JSON: {{\"contradictions\": [{{\"report_a\": \"标题\", \"report_b\": \"标题\", "
        f"\"description\": \"矛盾\", \"severity\": \"high/medium/low\"}}], \"consistent\": true/false}}\n\n"
        f"{conclusions}"
    )
    result = call_model(get_model_for_task("critic_challenge"), prompt,
        "只输出 JSON。", "consistency_check")
    if result.get("success"):
        try:
            resp = result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            data = json.loads(resp)
            contradictions = data.get("contradictions", [])
            if contradictions:
                print(f"  [ConsistencyCheck] ⚠️ 发现 {len(contradictions)} 个矛盾")
                section = "\n\n---\n## ⚠️ 跨研究一致性问题\n\n"
                for c in contradictions:
                    section += f"- **[{c.get('severity', '')}]** {c.get('description', '')}\n"
                reports[-1]["report"] += section
            else:
                print(f"  [ConsistencyCheck] ✅ 无矛盾")
        except:
            pass


# ============================================================
# 学习管道出口质量网
# ============================================================
def _post_learning_quality_check(progress_callback=None) -> dict:
    """两层质量检查：矛盾检测 + 元认知审查

    在 KB 写入完成后调用，发现问题时标记条目（不阻止入库）。
    任何异常都不中断学习流程。

    Returns:
        {"contradictions": int, "sense_check_issues": int, "flagged_entries": list}
    """
    result = {"contradictions": 0, "sense_check_issues": 0, "flagged_entries": []}

    try:
        # Step 1: 获取最近入库的 KB 条目（过去 60 分钟）
        recent_entries = get_recent_entries(minutes=60)
        if not recent_entries:
            print("[QualityNet] 无近期 KB 条目，跳过检查")
            return result

        print(f"[QualityNet] 检查 {len(recent_entries)} 个近期 KB 条目...")

        # Step 2: 加载决策树，获取已定结论
        decision_tree_path = AI_STATE / "product_decision_tree.yaml"
        if not decision_tree_path.exists():
            print("[QualityNet] 决策树文件不存在，跳过矛盾检测")
            return result

        with open(decision_tree_path, 'r', encoding='utf-8') as f:
            decision_tree = yaml.safe_load(f)

        decided_items = [
            d for d in decision_tree.get("decisions", [])
            if d.get("status") == "decided" and d.get("decided_value")
        ]

        if not decided_items:
            print("[QualityNet] 无已定结论，跳过矛盾检测")
            return result

        # Step 3: 矛盾检测（用 gemini_2_5_flash，轻量快）
        kb_summary = "\n".join([
            f"- [{e.get('type', 'unknown')}] {e.get('title', '')[:100]}: {e.get('content', '')[:200]}"
            for e in recent_entries[:10]
        ])

        decisions_summary = "\n".join([
            f"- {d.get('question', '')}: 已定结论 = {d.get('decided_value', '')}"
            for d in decided_items[:10]
        ])

        contra_prompt = f"""检查以下新入库的知识条目是否与已有决策结论矛盾。

已有决策结论：
{decisions_summary}

新入库知识条目：
{kb_summary}

如有矛盾，输出 JSON：
{{"contradictions": [{{"kb_entry": "标题", "decision": "问题", "conflict": "冲突描述"}}]}}
如无矛盾，输出：{{"contradictions": []}}"""

        contra_result = call_model("gemini_2_5_flash", contra_prompt,
            "只输出 JSON，无其他文字。", "quality_check")

        if contra_result.get("success"):
            try:
                resp = contra_result["response"].strip()
                resp = re.sub(r'^```json\s*', '', resp)
                resp = re.sub(r'\s*```$', '', resp)
                data = json.loads(resp)
                contradictions = data.get("contradictions", [])

                if contradictions:
                    print(f"[QualityNet] ⚠️ 发现 {len(contradictions)} 个矛盾")
                    result["contradictions"] = len(contradictions)

                    # 标记相关条目
                    for c in contradictions:
                        kb_title = c.get("kb_entry", "")
                        for entry in recent_entries:
                            if kb_title in entry.get("title", ""):
                                flag_ok = update_knowledge_flag(
                                    entry.get("id", ""),
                                    "contradiction_detected",
                                    c.get("conflict", "")
                                )
                                if flag_ok:
                                    result["flagged_entries"].append(entry.get("id", ""))
                                    print(f"  → 已标记: {entry.get('title', '')[:50]}")

                    if progress_callback:
                        progress_callback(f"⚠️ KB矛盾检测: 发现 {len(contradictions)} 个冲突，已标记")
                else:
                    print("[QualityNet] ✅ 无矛盾")
            except Exception as e:
                print(f"[QualityNet] 矛盾检测解析失败: {e}")

        # Step 4: 元认知 sense check（思考通道，60s超时，不可用就跳过）
        try:
            from scripts import claude_bridge

            sense_prompt = f"""刚完成一轮深度学习，新增了 {len(recent_entries)} 个 KB 条目。
从产品战略视角看，这些新增知识：
1. 是否有价值？会不会是噪音？
2. 是否遗漏重要角度？
3. 有没有方向性问题？

简要回复，不超过100字。如果没问题回复"没问题"。"""

            sense_result = claude_bridge.call_claude_via_cdp(
                sense_prompt, timeout=60, inject_context=True
            )

            if sense_result and "没问题" not in sense_result:
                print(f"[QualityNet] 元认知审查发现问题: {sense_result[:200]}")
                result["sense_check_issues"] = 1

                # 标记最近的条目需要验证
                for entry in recent_entries[:3]:
                    flag_ok = update_knowledge_flag(
                        entry.get("id", ""),
                        "needs_verification",
                        f"元认知审查: {sense_result[:100]}"
                    )
                    if flag_ok:
                        result["flagged_entries"].append(entry.get("id", ""))

                if progress_callback:
                    progress_callback(f"🧠 元认知审查: {sense_result[:100]}")
            else:
                print("[QualityNet] ✅ 元认知审查通过")
        except Exception as e:
            # 思考通道不可用就跳过，不报错
            print(f"[QualityNet] 元认知审查跳过（思考通道不可用）: {e}")

    except Exception as e:
        # 整个质量网的任何异常都不中断学习流程
        print(f"[QualityNet] 质量网异常（已吞掉，不影响流程）: {e}")

    return result


# ============================================================
# 深度学习主调度器
# ============================================================
def run_deep_learning(max_hours: float = 7.0, progress_callback=None):
    set_feishu_callback(progress_callback, None)

    if not _pre_flight_api_check(progress_callback):
        return {"status": "aborted", "reason": "API health check failed"}

    kb_stats_before = get_knowledge_stats()
    kb_total_before = sum(kb_stats_before.values())

    start_time = time.time()
    deadline = start_time + max_hours * 3600
    completed = []

    print(f"\n{'#' * 60}")
    print(f"# 深度学习模式 — {max_hours}h 窗口")
    print(f"# 开始: {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"# 截止: {time.strftime('%Y-%m-%d %H:%M', time.localtime(deadline))}")
    print(f"{'#' * 60}")

    if progress_callback:
        progress_callback(f"🎓 深度学习开始 ({max_hours}h 窗口)")

    while True:
        remaining_hours = (deadline - time.time()) / 3600
        if remaining_hours < 0.5:
            print(f"\n[Scheduler] 剩余 {remaining_hours:.1f}h < 0.5h，收尾")
            break

        pool = _load_task_pool()
        task = None
        if pool:
            task = pool[0]
            print(f"\n[Scheduler] 从任务池取: {task['title']} (剩余 {remaining_hours:.1f}h)")
        else:
            print(f"\n[Scheduler] 任务池空，自主发现新方向...")
            new_tasks = _discover_new_tasks()
            if not new_tasks:
                new_tasks = _discover_from_decision_tree()
            if new_tasks:
                existing_pool = _load_task_pool()
                for nt in new_tasks:
                    nt["source"] = "auto_discover"
                    nt["discovered_at"] = time.strftime('%Y-%m-%d %H:%M')
                existing_pool.extend(new_tasks)
                _save_task_pool(existing_pool)
                task = new_tasks[0]
            else:
                print("[Scheduler] 无新任务可发现，结束")
                break

        task_start = time.time()
        if progress_callback:
            progress_callback(f"📖 [{len(completed) + 1}] {task['title']} (剩余 {remaining_hours:.1f}h)")

        report = deep_research_one(task, progress_callback=progress_callback)
        task_duration = (time.time() - task_start) / 60

        completed.append({
            "title": task["title"],
            "duration_min": round(task_duration, 1),
            "report_len": len(report) if report else 0,
            "success": bool(report and len(report) > 500),
        })

        _mark_task_done(task.get("id", ""))
        print(f"\n✅ {task['title']} 完成 ({task_duration:.0f}min, {len(report) if report else 0}字)")

        if progress_callback:
            progress_callback(f"✅ {task['title']} ({task_duration:.0f}min)")

        time.sleep(5)

    # 收尾: KB 治理
    print(f"\n[Scheduler] 任务完成，运行 KB 治理...")
    gov_report = ""
    try:
        from scripts.kb_governance import run_governance
        gov_report = run_governance()
    except ImportError:
        gov_report = "KB 治理模块未安装"

    # 收尾: 质量网（两层检查）
    print(f"\n[Scheduler] 运行出口质量网...")
    quality_result = _post_learning_quality_check(progress_callback)

    # 汇总报告
    kb_stats_after = get_knowledge_stats()
    kb_total_after = sum(kb_stats_after.values())
    total_hours = (time.time() - start_time) / 3600

    summary_lines = [
        f"📊 深度学习完成报告",
        f"",
        f"⏱️ 耗时: {total_hours:.1f}h / {max_hours}h",
        f"📝 任务: {len(completed)} 个完成",
    ]
    for c in completed:
        summary_lines.append(f"  • {c['title']} ({c.get('duration_min', '?')}min)")
    summary_lines.append(f"")
    summary_lines.append(f"📚 KB 变化: {kb_total_before} → {kb_total_after} (+{kb_total_after - kb_total_before})")

    # 元能力层统计
    try:
        from scripts.meta_capability import load_registry
        reg = load_registry()
        new_tools = [t for t in reg.get("tools", [])
                     if t.get("installed_at", "").startswith(time.strftime('%Y-%m-%d'))]
        if new_tools:
            summary_lines.append(f"🧬 元能力进化: +{len(new_tools)} 个新工具")
    except:
        pass

    if gov_report:
        summary_lines.append(f"🗄️ KB 治理: {gov_report}")

    # 质量网结果
    if quality_result.get("contradictions") or quality_result.get("sense_check_issues"):
        summary_lines.append(f"🔍 质量网: {quality_result['contradictions']} 矛盾, {quality_result['sense_check_issues']} 元认知问题")
        if quality_result.get("flagged_entries"):
            summary_lines.append(f"  → 已标记 {len(quality_result['flagged_entries'])} 条待验证")

    summary = "\n".join(summary_lines)

    print(f"\n{'#' * 60}")
    print(f"# 深度学习完成 — {total_hours:.1f}h / {max_hours}h — {len(completed)} 个任务")
    evolution_report = generate_evolution_report()
    print(f"\n{evolution_report}")
    print(f"{'#' * 60}")

    if progress_callback:
        progress_callback(summary)

        try:
            from scripts.critic_calibration import push_batch_calibration_summary
            push_batch_calibration_summary(reply_func=progress_callback)
        except:
            pass

        try:
            from scripts.strategic_questions import run_strategic_questions_pipeline
            research_summary = "\n".join([
                f"- {c.get('title', '')}: {c.get('report_len', 0)} 字报告"
                for c in completed[:5]
            ])
            run_strategic_questions_pipeline(
                research_summary=research_summary,
                research_topic=f"深度学习 {len(completed)} 个任务",
                auto_submit_to_thinking=True, urgency="normal")
        except:
            pass

        try:
            from scripts.architect_briefing import generate_briefing
            generate_briefing()
        except:
            pass

        generate_night_report(completed, progress_callback, None)

    return completed


# ============================================================
# __init__.py 入口
# ============================================================
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        md_path = sys.argv[1]
        task_ids = sys.argv[2:] if len(sys.argv) > 2 else None
        run_research_from_file(md_path, task_ids=task_ids)
    else:
        run_all()
