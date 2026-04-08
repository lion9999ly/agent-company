"""
@description: 自学习 30min 周期 — 轻量增量知识补充
@dependencies: src.utils.model_gateway, src.tools.knowledge_base
@last_modified: 2026-04-07

设计:
- 每 30 分钟自动触发
- 只跑 Layer 1（搜索）+ Layer 2（提炼）+ 直接入库
- 不走 Agent 分析，不生成报告
- 相当于"知识库的 heartbeat"
- 已覆盖的搜索词不会重复搜索（7 天后过期重试）
"""
import json
import time
import re
import sys
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.model_gateway import get_model_gateway
from src.tools.knowledge_base import KB_ROOT, add_knowledge, get_knowledge_stats

gateway = get_model_gateway()

# 已覆盖搜索词记录（防止重复搜索）
COVERED_FILE = PROJECT_ROOT / ".ai-state" / "auto_learn_covered.json"
COVERED_EXPIRY_DAYS = 7  # 已覆盖记录 7 天后过期，允许重新搜索


def _load_covered_topics() -> dict:
    """加载已覆盖的搜索词"""
    if not COVERED_FILE.exists():
        return {}
    try:
        data = json.loads(COVERED_FILE.read_text(encoding="utf-8"))
        # 过滤过期记录
        cutoff = datetime.now() - timedelta(days=COVERED_EXPIRY_DAYS)
        filtered = {}
        for query, timestamp in data.items():
            try:
                if datetime.fromisoformat(timestamp) > cutoff:
                    filtered[query] = timestamp
            except:
                continue
        return filtered
    except:
        return {}


def _save_covered_topic(query: str):
    """保存已覆盖的搜索词"""
    covered = _load_covered_topics()
    covered[query] = datetime.now().isoformat()
    COVERED_FILE.parent.mkdir(parents=True, exist_ok=True)
    COVERED_FILE.write_text(json.dumps(covered, ensure_ascii=False, indent=2), encoding="utf-8")


def _calculate_time_weighted_priority(base_priority: int, deadline: str) -> float:
    """优先级 × 紧迫度系数

    Args:
        base_priority: 基础优先级 (1-3, 数字越小越优先)
        deadline: 截止日期 (YYYY-MM-DD)

    Returns:
        加权优先级 (数字越小越优先)
    """
    if not deadline:
        return float(base_priority)

    try:
        days_left = (datetime.strptime(deadline, "%Y-%m-%d") - datetime.now()).days
    except:
        return float(base_priority)

    if days_left <= 0:
        urgency = 5.0  # 已过期，最高紧迫
    elif days_left <= 7:
        urgency = 3.0
    elif days_left <= 30:
        urgency = 1.5
    else:
        urgency = 1.0

    return base_priority * urgency


def _find_kb_gaps() -> list:
    """分析知识库缺口，返回需要补充的搜索词列表

    策略:
    1. 优先从决策树的 blocking_knowledge 获取缺口
    2. 从 research_task_pool.yaml 获取未完成任务
    3. 域分布不均: 哪个 domain 条目最少？
    4. 时效性: 哪些条目超过 30 天未更新？
    5. 产品锚点覆盖: PRD 中提到的模块，KB 有没有对应知识？
    6. 竞品关键词补充

    已覆盖的搜索词会被跳过（7 天后过期重试）
    """
    gaps = []

    # 加载已覆盖的搜索词
    covered = _load_covered_topics()
    if covered:
        print(f"[AutoLearn] 已覆盖搜索词: {len(covered)} 个（7天内不重复）")

    # 0. 优先: 从决策树获取阻塞知识缺口
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
                        # 应用时间价值加权
                        deadline = d.get("deadline", "")
                        base_priority = d.get("priority", 2)
                        weighted_priority = _calculate_time_weighted_priority(base_priority, deadline)

                        gaps.append({
                            "type": "decision_blocking",
                            "domain": "components",
                            "query": bk,
                            "priority": weighted_priority,  # 使用加权优先级
                            "decision_id": d.get("id", ""),
                        })
        except Exception as e:
            print(f"[AutoLearn] 决策树读取失败: {e}")

    # 0.5 新增: 从 research_task_pool.yaml 获取未完成任务
    rtp_path = Path(__file__).parent.parent / ".ai-state" / "research_task_pool.yaml"
    if rtp_path.exists():
        try:
            import yaml as _yaml
            tasks = _yaml.safe_load(rtp_path.read_text(encoding='utf-8'))
            if tasks:
                for task in tasks:
                    if task.get("completed"):
                        continue
                    # 取第一个搜索词作为 query
                    searches = task.get("searches", [])
                    if searches:
                        for search in searches[:1]:  # 只取第一个
                            gaps.append({
                                "type": "research_pool",
                                "domain": "components",
                                "query": search,
                                "priority": task.get("priority", 2),
                                "task_id": task.get("id", ""),
                            })
        except Exception as e:
            print(f"[AutoLearn] research_task_pool 读取失败: {e}")

    # 1. 域分布
    stats = get_knowledge_stats()
    if stats:
        values = list(stats.values()) if isinstance(stats, dict) else []
        if values:
            min_val = min(values)
            max_val = max(values)
            if max_val > 0 and min_val < max_val * 0.3:
                # 找到最小值的 key
                if isinstance(stats, dict):
                    min_domain = min(stats, key=stats.get)
                    gaps.append({
                        "type": "domain_gap",
                        "domain": min_domain,
                        "query": f"智能骑行头盔 {min_domain} 最新技术 供应商 2026",
                        "priority": 1
                    })

    # 2. 时效性（超过 30 天的条目所在领域）
    stale_domains = set()
    cutoff = datetime.now() - timedelta(days=30)
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            created = data.get("created_at", "")
            if created:
                try:
                    if datetime.fromisoformat(created) < cutoff:
                        domain = data.get("domain", "general")
                        stale_domains.add(domain)
                except:
                    pass
        except:
            continue

    for domain in list(stale_domains)[:2]:
        gaps.append({
            "type": "stale",
            "domain": domain,
            "query": f"{domain} motorcycle helmet latest update 2026",
            "priority": 2
        })

    # 3. 产品锚点覆盖
    anchor_keywords = [
        "HUD", "光波导", "waveguide", "OLED", "Micro LED",
        "mesh intercom", "Cardo", "骨传导", "ANC",
        "Qualcomm AR1", "主SoC", "胎压", "TPMS",
        "DOT", "ECE", "SNELL", "安全认证",
        "lark-cli", "飞书 CLI",  # 新增：追踪飞书CLI能力
    ]
    for kw in anchor_keywords:
        # 检查 KB 中是否有足够条目
        count = 0
        for f in KB_ROOT.rglob("*.json"):
            try:
                content = f.read_text(encoding="utf-8")
                if kw.lower() in content.lower():
                    count += 1
            except:
                continue
        if count < 3:
            gaps.append({
                "type": "anchor_gap",
                "keyword": kw,
                "query": f"{kw} motorcycle helmet specs supplier price 2026",
                "priority": 1
            })

    # 按优先级排序，取 top 5-8
    gaps.sort(key=lambda x: x["priority"])

    # 过滤已覆盖的搜索词
    filtered_gaps = []
    skipped = 0
    for gap in gaps[:10]:  # 扩大到10个
        query = gap["query"]
        if query in covered:
            skipped += 1
            continue
        filtered_gaps.append(gap)

    if skipped > 0:
        print(f"[AutoLearn] 跳过 {skipped} 个已覆盖的搜索词")

    return filtered_gaps[:8]  # 返回最多8个


def _call_model(model_name: str, prompt: str, system_prompt: str = "", task_type: str = "auto_learn") -> dict:
    """调用模型（简化版）"""
    return gateway.call(model_name, prompt, system_prompt, task_type)


def _extract_structured_data(raw_text: str, topic: str) -> dict:
    """从文本中提取结构化数据"""
    extract_prompt = (
        f"从以下搜索结果中提取结构化数据点。\n"
        f"主题: {topic}\n\n"
        f"搜索结果:\n{raw_text[:2000]}\n\n"
        f"输出 JSON:\n"
        f'{{"topic": "主题", "product": "产品名(如有)", "key_specs": [{{"name": "参数名", "value": "值", "source": "来源"}}], '
        f'"suppliers": ["供应商"], "prices": ["价格信息"], "summary": "200字摘要"}}\n'
        f"只输出 JSON。"
    )

    result = _call_model("gemini_2_5_flash", extract_prompt, "只输出 JSON。", "data_extraction")
    if result.get("success"):
        try:
            resp = result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            return json.loads(resp)
        except:
            pass
    return None


def auto_learn_cycle(progress_callback=None):
    """自学习 30min 周期

    只跑 Layer 1（搜索）+ Layer 2（提炼）+ 直接入库
    不走 Agent 分析，不生成报告
    """
    print(f"\n{'='*40}")
    print(f"[AutoLearn] {time.strftime('%H:%M')} 开始")

    if progress_callback:
        progress_callback("📚 自学习开始...")

    gaps = _find_kb_gaps()
    if not gaps:
        print("[AutoLearn] 无明显缺口，跳过")
        if progress_callback:
            progress_callback("✅ 自学习完成: 无缺口")
        return "无缺口，跳过"

    print(f"[AutoLearn] 发现 {len(gaps)} 个缺口")

    added_total = 0
    for gap in gaps:
        query = gap["query"]
        print(f"  搜索: {query[:50]}...")

        if progress_callback:
            progress_callback(f"🔍 {query[:30]}...")

        # Layer 1: 双搜索（但自学习用轻量模式，豆包为主，o3 只对 priority=1 启用）
        source_text = ""

        if gap["priority"] == 1:
            # 高优先级: 启用 o3
            o3_result = _call_model("o3_deep_research", query, task_type="auto_learn")
            if o3_result.get("success") and len(o3_result.get("response", "")) > 200:
                source_text += o3_result["response"][:2000]

        # 豆包始终启用
        doubao_result = _call_model("doubao_seed_pro", query,
                                    "搜索相关技术和市场信息，提取具体数据。",
                                    "auto_learn")
        if doubao_result.get("success") and len(doubao_result.get("response", "")) > 200:
            source_text += "\n" + doubao_result["response"][:2000]

        if not source_text:
            # 搜索无结果也标记为已处理
            _save_covered_topic(query)
            continue

        # Layer 2: 提炼
        extracted = _extract_structured_data(
            raw_text=source_text,
            topic=query
        )

        if extracted:
            # 直接入库（不经过 Agent 分析）
            title = extracted.get("product", extracted.get("topic", query[:40]))
            content = json.dumps(extracted, ensure_ascii=False, indent=2)

            if len(content) > 150:  # 质量门槛
                add_knowledge(
                    title=f"[AutoLearn] {title}",
                    domain=gap.get("domain", "components"),
                    content=content[:800],
                    tags=["auto_learn", gap.get("type", "general")],
                    source="auto_learn",
                    confidence="medium"  # 自学习产出标记为 medium
                )
                added_total += 1
                # 标记该搜索词为已覆盖
                _save_covered_topic(query)
                print(f"[AutoLearn] 已覆盖: {query[:40]}")
            else:
                # 内容质量不足也标记为已处理（避免重复搜索低质量结果）
                _save_covered_topic(query)
        else:
            # 提取失败也标记为已处理
            _save_covered_topic(query)

        time.sleep(3)

    print(f"[AutoLearn] 完成: +{added_total} 条知识")
    print(f"{'='*40}")

    if progress_callback:
        progress_callback(f"✅ 自学习完成: +{added_total} 条知识")

    return f"完成: +{added_total} 条知识"


def start_auto_learn_scheduler(interval_minutes: float = 30, progress_callback=None):
    """启动自学习定时调度器

    使用 threading.Timer 循环
    启动时不立即执行，等第一个周期到了再跑
    """
    import threading

    def _schedule_next():
        auto_learn_cycle(progress_callback)
        # 安排下一次
        timer = threading.Timer(interval_minutes * 60, _schedule_next)
        timer.daemon = True
        timer.start()

    print(f"[AutoLearn] 启动 {interval_minutes}min 周期调度器（首个周期将在 {interval_minutes} 分钟后执行）")
    # 先等待第一个周期，不立即执行
    timer = threading.Timer(interval_minutes * 60, _schedule_next)
    timer.daemon = True
    timer.start()


if __name__ == "__main__":
    # 手动触发一次
    result = auto_learn_cycle()
    print(f"\n结果: {result}")