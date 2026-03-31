"""
@description: 自学习 30min 周期 — 轻量增量知识补充
@dependencies: src.utils.model_gateway, src.tools.knowledge_base
@last_modified: 2026-03-31

设计:
- 每 30 分钟自动触发
- 只跑 Layer 1（搜索）+ Layer 2（提炼）+ 直接入库
- 不走 Agent 分析，不生成报告
- 相当于"知识库的 heartbeat"
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


def _find_kb_gaps() -> list:
    """分析知识库缺口，返回需要补充的搜索词列表

    策略:
    1. 域分布不均: 哪个 domain 条目最少？
    2. 时效性: 哪些条目超过 30 天未更新？
    3. 产品锚点覆盖: PRD 中提到的模块，KB 有没有对应知识？
    4. 低 confidence 高频引用: 被多次引用但 confidence 只有 medium/low 的条目
    """
    gaps = []

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
        "DOT", "ECE", "SNELL", "安全认证"
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
    return gaps[:8]


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

        time.sleep(3)

    print(f"[AutoLearn] 完成: +{added_total} 条知识")
    print(f"{'='*40}")

    if progress_callback:
        progress_callback(f"✅ 自学习完成: +{added_total} 条知识")

    return f"完成: +{added_total} 条知识"


def start_auto_learn_scheduler(interval_minutes: float = 30, progress_callback=None):
    """启动自学习定时调度器

    使用 threading.Timer 循环
    """
    import threading

    def _schedule_next():
        auto_learn_cycle(progress_callback)
        # 安排下一次
        timer = threading.Timer(interval_minutes * 60, _schedule_next)
        timer.daemon = True
        timer.start()

    print(f"[AutoLearn] 启动 {interval_minutes}min 周期调度器")
    _schedule_next()


if __name__ == "__main__":
    # 手动触发一次
    result = auto_learn_cycle()
    print(f"\n结果: {result}")