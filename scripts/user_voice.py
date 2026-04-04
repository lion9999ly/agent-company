"""用户声音采集 — 从骑行社区提取用户痛点和需求
@description: 搜索骑行社区，提取用户痛点、需求和吐槽
@dependencies: model_gateway
@last_modified: 2026-04-04
"""
import json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def collect_user_voice(gateway, progress_callback=None) -> str:
    """搜索骑行社区，提取用户声音"""
    queries = [
        "骑行头盔 吐槽 不满 小红书",
        "智能头盔 用户评价 问题 B站",
        "Cardo Sena 用户体验 知乎",
        "摩托车骑行 最烦的事 论坛",
        "motorcycle helmet complaint user review",
    ]

    findings = []

    for i, query in enumerate(queries):
        if progress_callback:
            progress_callback(f"搜索: {query}")

        result = gateway.call("doubao_seed_pro", query,
                              "提取用户吐槽、痛点、不满、期望改进的点。只关注负面反馈和需求。",
                              "user_voice")
        if result.get("success") and len(result.get("response", "")) > 50:
            findings.append({
                "query": query,
                "voices": result["response"][:800],
            })

    # 汇总分析
    if findings:
        summary_prompt = (
            f"以下是从多个渠道收集的用户声音，请汇总分析:\n\n"
            f"{json.dumps(findings, ensure_ascii=False, indent=2)}\n\n"
            f"输出:\n"
            f"1. 痛点 Top 5\n"
            f"2. 功能需求 Top 5\n"
            f"3. 情感关键词"
        )
        summary_result = gateway.call("gpt_5_3", summary_prompt,
                                       "你是用户研究员，专注提取有价值的需求信号。",
                                       "user_voice_summary")
        return summary_result.get("response", "") if summary_result.get("success") else "汇总失败"

    return "未收集到用户声音"


def save_user_voice_report(report: str) -> str:
    """保存用户声音报告"""
    output_path = PROJECT_ROOT / ".ai-state" / "exports" / "user_voice_report.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    content = f"""# 用户声音报告

> 采集时间: {time.strftime('%Y-%m-%d %H:%M')}

{report}
"""
    output_path.write_text(content, encoding='utf-8')
    return str(output_path)


if __name__ == "__main__":
    print("用户声音采集器已就绪")