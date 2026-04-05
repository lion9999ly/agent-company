"""竞品监控器 — 每天搜索竞品关键词，有新内容推送飞书
@description: 定时监控竞品动态，发现新内容时推送通知
@dependencies: model_gateway, feishu_sdk_client
@last_modified: 2026-04-05
"""
import json
import time
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
MONITOR_STATE_PATH = PROJECT_ROOT / ".ai-state" / "competitor_monitor_state.json"
LEO_OPEN_ID = "ou_8e5e4f183e9eca4241378e96bac3a751"

# 监控的竞品关键词
COMPETITOR_KEYWORDS = [
    "Sena智能头盔",
    "Cardo Packtalk",
    "Livall智能头盔",
    "Forcite MK1S",
    "智能骑行头盔 HUD",
    "Mesh对讲头盔",
    "歌尔股份 AR眼镜",
    "JBD MicroLED",
]


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


def search_keyword(keyword: str) -> list:
    """搜索单个关键词"""
    try:
        from src.utils.model_gateway import get_model_gateway
        gw = get_model_gateway()

        # 使用 o3_deep_research 或 doubao 进行搜索
        result = gw.call("doubao_seed_pro",
            f"搜索并总结关于'{keyword}'的最新动态（最近30天）。"
            f"如果有新产品发布、功能更新、市场活动，列出要点。"
            f"如果没有明显新动态，回复'无重要新动态'。",
            task_type="competitor_monitor"
        )

        if result.get("success"):
            return [{
                "keyword": keyword,
                "summary": result["response"][:500],
                "timestamp": datetime.now().isoformat()
            }]
    except Exception as e:
        print(f"[Monitor] 搜索 {keyword} 失败: {e}")

    return []


def run_competitor_monitor():
    """运行竞品监控"""
    print(f"[Monitor] 开始竞品监控...")

    state = load_monitor_state()
    new_findings = []

    for keyword in COMPETITOR_KEYWORDS:
        print(f"[Monitor] 检查: {keyword}")
        results = search_keyword(keyword)

        for item in results:
            item_key = f"{keyword}_{item.get('summary', '')[:50]}"

            # 检查是否是新的
            if item_key not in state.get("seen_items", []):
                new_findings.append(item)
                state["seen_items"].append(item_key)

        time.sleep(1)  # 避免频率限制

    state["last_check"] = datetime.now().isoformat()
    save_monitor_state(state)

    # 如果有新发现，推送飞书
    if new_findings:
        print(f"[Monitor] 发现 {len(new_findings)} 条新动态，推送飞书...")
        _send_feishu_notification(new_findings)
    else:
        print(f"[Monitor] 无新发现")

    return new_findings


def _send_feishu_notification(findings: list):
    """发送飞书通知"""
    try:
        from scripts.feishu_sdk_client import send_reply

        lines = [f"【竞品监控日报】{datetime.now().strftime('%Y-%m-%d')}"]
        lines.append(f"\n发现 {len(findings)} 条新动态:\n")

        for i, item in enumerate(findings[:5], 1):
            lines.append(f"{i}. **{item['keyword']}**")
            lines.append(f"   {item['summary'][:200]}...")
            lines.append("")

        lines.append("\n---\n*由自动监控系统生成*")

        send_reply(LEO_OPEN_ID, "\n".join(lines), id_type="open_id")

    except Exception as e:
        print(f"[Monitor] 飞书推送失败: {e}")


if __name__ == "__main__":
    run_competitor_monitor()