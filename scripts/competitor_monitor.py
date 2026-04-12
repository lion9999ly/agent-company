"""竞品监控器 — 每天搜索竞品关键词，有新内容推送飞书
@description: 定时监控竞品动态，发现新内容时写入飞书多维表格
@dependencies: model_gateway, feishu_sdk_client, feishu_output
@last_modified: 2026-04-09
"""
import json
import time
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
MONITOR_STATE_PATH = PROJECT_ROOT / ".ai-state" / "competitor_monitor_state.json"
CONFIG_PATH = PROJECT_ROOT / ".ai-state" / "competitor_monitor_config.json"
LEO_OPEN_ID = "ou_8e5e4f183e9eca4241378e96bac3a751"


def _load_monitor_config() -> dict:
    """加载监控配置"""
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        except Exception as e:
            print(f"[Monitor] 配置加载失败: {e}")
    return {}


def _get_search_keywords() -> list:
    """从配置获取搜索关键词（动态化）"""
    config = _load_monitor_config()
    keywords = []

    # 从 monitor_layers 提取所有 search_keywords
    layers = config.get("monitor_layers", {})
    for layer_name, layer_data in layers.items():
        layer_keywords = layer_data.get("search_keywords", [])
        keywords.extend(layer_keywords)

    # 如果配置为空或加载失败，使用默认列表
    if not keywords:
        keywords = [
            "Sena智能头盔",
            "Cardo Packtalk",
            "Livall智能头盔",
            "Forcite MK1S",
            "智能骑行头盔 HUD",
            "Mesh对讲头盔",
            "歌尔股份 AR眼镜",
            "JBD MicroLED",
        ]

    return keywords

# 多维表格配置（首次创建后记录）
BITABLE_CONFIG = {
    "name": "竞品监控",
    "default_table_id": "tblXXXXXX",  # 需在首次创建后填入
}


def load_monitor_state() -> dict:
    """加载监控状态"""
    if MONITOR_STATE_PATH.exists():
        try:
            return json.loads(MONITOR_STATE_PATH.read_text(encoding='utf-8'))
        except:
            pass
    return {"last_check": "", "seen_items": [], "last_results": {}}


def save_monitor_state(state: dict):
    """保存监控状态"""
    MONITOR_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    MONITOR_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def search_keyword(keyword: str, config: dict = None) -> list:
    """搜索单个关键词"""
    try:
        from scripts.litellm_gateway import get_model_gateway
        gw = get_model_gateway()

        # 获取时间过滤配置
        time_filters = (config or {}).get("time_filters", {})
        year_hint = " 2026" if time_filters.get("current_year") else ""

        # 使用 o3_deep_research 或 doubao 进行搜索
        result = gw.call("doubao_seed_pro",
            f"搜索并总结关于'{keyword}'的最新动态{year_hint}（最近30天）。"
            f"如果有新产品发布、功能更新、市场活动，列出要点。"
            f"如果没有明显新动态，回复'无重要新动态'。",
            task_type="competitor_monitor"
        )

        if result.get("success"):
            summary = result["response"][:500]

            # 检查通知规则：无重要新动态不推送
            output_rules = (config or {}).get("output_rules", {})
            if output_rules.get("no_update_no_push") and "无重要新动态" in summary:
                print(f"[Monitor] {keyword}: 无重要新动态，跳过")
                return []

            return [{
                "keyword": keyword,
                "summary": summary,
                "timestamp": datetime.now().isoformat()
            }]
    except Exception as e:
        print(f"[Monitor] 搜索 {keyword} 失败: {e}")

    return []


def _analyze_impact(keyword: str, summary: str, config: dict) -> str:
    """研判竞品动态影响级别（high/medium/low）

    Args:
        keyword: 搜索关键词
        summary: 动态摘要
        config: 监控配置

    Returns:
        str: "high", "medium", "low" 或 "none"
    """
    impact_config = config.get("impact_analysis", {})
    if not impact_config.get("enabled", False):
        return "none"  # 未启用研判层

    try:
        from scripts.litellm_gateway import get_model_gateway
        gw = get_model_gateway()

        prompt = f"""分析以下竞品动态的影响级别：

关键词：{keyword}
动态摘要：{summary[:500]}

判断标准：
- high: 产品发布、重大功能更新、融资并购、核心专利公开
- medium: 功能迭代、市场活动、渠道扩展
- low: 日常运营、媒体报道、社交媒体内容

只输出一个词：high / medium / low"""

        result = gw.call("doubao_seed_pro", prompt, task_type="impact_analysis")
        if result.get("success"):
            response = result["response"].strip().lower()
            if response in ("high", "medium", "low"):
                return response
    except Exception as e:
        print(f"[Monitor] 影响研判失败: {e}")

    return "medium"  # 默认中等


def run_competitor_monitor():
    """运行竞品监控"""
    from scripts.feishu_handlers.notify_rules import should_notify

    print(f"[Monitor] 开始竞品监控...")

    # 加载配置
    config = _load_monitor_config()
    keywords = _get_search_keywords()
    print(f"[Monitor] 加载 {len(keywords)} 个搜索关键词")

    state = load_monitor_state()
    new_findings = []

    # 检查是否启用影响研判
    impact_enabled = config.get("impact_analysis", {}).get("enabled", False)
    if impact_enabled:
        print(f"[Monitor] 影响研判层已启用")

    for keyword in keywords:
        print(f"[Monitor] 检查: {keyword}")
        results = search_keyword(keyword, config)

        for item in results:
            item_key = f"{keyword}_{item.get('summary', '')[:50]}"

            # 检查是否是新的
            if item_key not in state.get("seen_items", []):
                # P2 #16: 影响研判
                if impact_enabled:
                    impact = _analyze_impact(keyword, item.get("summary", ""), config)
                    item["impact"] = impact
                    print(f"[Monitor] {keyword} 影响级别: {impact}")
                new_findings.append(item)
                state["seen_items"].append(item_key)

        time.sleep(1)  # 避免频率限制

    state["last_check"] = datetime.now().isoformat()
    save_monitor_state(state)

    # 按影响级别分流处理
    if new_findings:
        high_impact = [f for f in new_findings if f.get("impact") == "high"]
        if high_impact and impact_enabled:
            print(f"[Monitor] 🔴 高影响动态 {len(high_impact)} 条，优先推送")

        if should_notify("competitor_monitor", "has_update"):
            print(f"[Monitor] 发现 {len(new_findings)} 条新动态，推送飞书...")
            _send_feishu_notification(new_findings)
        else:
            print(f"[Monitor] 发现 {len(new_findings)} 条新动态，但通知已静默")
    else:
        if should_notify("competitor_monitor", "no_update"):
            print(f"[Monitor] 无新发现")
        else:
            print(f"[Monitor] 无新发现（静默）")

    return new_findings


def _send_feishu_notification(findings: list):
    """发送飞书通知 + 写入多维表格"""
    try:
        from scripts.feishu_output import get_or_create_bitable, add_bitable_record
        from scripts.feishu_handlers.chat_helpers import send_reply

        # 获取或创建多维表格
        app_token = get_or_create_bitable(BITABLE_CONFIG["name"])
        table_id = BITABLE_CONFIG.get("default_table_id", "tblXXXXXX")

        # 写入多维表格（如果有 app_token）
        records_added = 0
        if app_token and table_id != "tblXXXXXX":
            for item in findings:
                record = {
                    "日期": datetime.now().strftime("%Y-%m-%d"),
                    "关键词": item.get("keyword", ""),
                    "摘要": item.get("summary", "")[:500],
                    "时间戳": item.get("timestamp", ""),
                }
                if add_bitable_record(app_token, table_id, record):
                    records_added += 1

        # 发送飞书通知（简化版，引导到多维表格）
        lines = [f"🔔 竞品监控完成"]
        lines.append(f"\n发现 {len(findings)} 条新动态")

        if records_added > 0:
            lines.append(f"📊 已写入多维表格：{records_added} 条记录")
            # 如果有 bitable URL，可以加上
            bitable_url = _get_bitable_url(app_token)
            if bitable_url:
                lines.append(f"🔗 {bitable_url}")
        else:
            # 回退：直接显示摘要
            for i, item in enumerate(findings[:3], 1):
                lines.append(f"\n{i}. **{item['keyword']}**")
                lines.append(f"   {item['summary'][:150]}...")

        lines.append("\n---\n*由自动监控系统生成*")

        send_reply(LEO_OPEN_ID, "\n".join(lines), id_type="open_id")

    except Exception as e:
        print(f"[Monitor] 飞书推送失败: {e}")


def _get_bitable_url(app_token: str) -> str:
    """获取多维表格 URL"""
    if app_token:
        return f"https://feishu.cn/base/{app_token}"
    return ""


if __name__ == "__main__":
    run_competitor_monitor()