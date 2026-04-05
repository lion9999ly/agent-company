"""战略问题生成器 — 深度学习完成后自动生成战略问题
@description: 读取 product_anchor.md 中的未决决策，结合研究发现，生成 3-5 个战略问题
@dependencies: model_gateway, feishu_sdk_client
@last_modified: 2026-04-05
"""
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
PRODUCT_ANCHOR_PATH = PROJECT_ROOT / ".ai-state" / "product_anchor.md"
LEO_OPEN_ID = "ou_8e5e4f183e9eca4241378e96bac3a751"


def generate_strategic_questions(research_summary: str = "", research_topic: str = "") -> list:
    """生成战略问题

    Args:
        research_summary: 本次研究摘要
        research_topic: 研究主题

    Returns:
        战略问题列表
    """
    # 读取产品锚点
    anchor_content = ""
    if PRODUCT_ANCHOR_PATH.exists():
        anchor_content = PRODUCT_ANCHOR_PATH.read_text(encoding='utf-8')

    # 提取未决决策
    unresolved = []
    if "## 未决决策" in anchor_content:
        section = anchor_content.split("## 未决决策")[1].split("##")[0]
        unresolved = [line.strip("- ").strip() for line in section.split("\n") if line.strip().startswith("-")]

    # 使用 gpt_5_4 生成战略问题
    prompt = f"""基于以下信息，生成 3-5 个关键战略问题，每个问题应该：
1. 与未决决策直接相关
2. 结合最新研究发现
3. 具有决策紧迫性

## 产品锚点
{anchor_content[:2000]}

## 最新研究发现
主题: {research_topic}
摘要: {research_summary[:1500]}

## 输出格式
每个问题一行，格式：
Q: [问题]
背景: [为什么重要]
建议行动: [下一步做什么]
"""

    try:
        from src.utils.model_gateway import get_model_gateway
        gw = get_model_gateway()

        result = gw.call("gpt_5_4", prompt,
            "你是产品战略顾问，擅长提出有洞察力的战略问题。",
            task_type="strategic_questions")

        if result.get("success"):
            # 解析问题
            text = result["response"]
            questions = []

            current_q = {}
            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("Q:"):
                    if current_q:
                        questions.append(current_q)
                    current_q = {"question": line[2:].strip(), "background": "", "action": ""}
                elif line.startswith("背景:"):
                    current_q["background"] = line[3:].strip()
                elif line.startswith("建议行动:"):
                    current_q["action"] = line[5:].strip()

            if current_q:
                questions.append(current_q)

            return questions

    except Exception as e:
        print(f"[StrategicQuestions] 生成失败: {e}")

    return []


def send_strategic_questions(questions: list, research_topic: str = ""):
    """发送战略问题到飞书"""
    if not questions:
        return

    try:
        from scripts.feishu_sdk_client import send_reply

        lines = [f"【战略问题】{datetime.now().strftime('%Y-%m-%d')}"]
        if research_topic:
            lines.append(f"研究主题: {research_topic}")
        lines.append("")

        for i, q in enumerate(questions[:5], 1):
            lines.append(f"### Q{i}: {q.get('question', '')}")
            if q.get("background"):
                lines.append(f"背景: {q['background']}")
            if q.get("action"):
                lines.append(f"建议行动: {q['action']}")
            lines.append("")

        lines.append("---")
        lines.append("由 AI Agent Company 自动生成")

        send_reply(LEO_OPEN_ID, "\n".join(lines), id_type="open_id")
        print(f"[StrategicQuestions] 已发送 {len(questions)} 个问题")

    except Exception as e:
        print(f"[StrategicQuestions] 发送失败: {e}")


def run_strategic_questions_pipeline(research_summary: str = "", research_topic: str = ""):
    """完整流程：生成 + 发送"""
    questions = generate_strategic_questions(research_summary, research_topic)
    if questions:
        send_strategic_questions(questions, research_topic)
        # 保存记录
        record_path = PROJECT_ROOT / ".ai-state" / "strategic_questions_log.jsonl"
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now().isoformat(),
            "research_topic": research_topic,
            "questions": questions
        }
        with open(record_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return questions


if __name__ == "__main__":
    # 测试
    questions = generate_strategic_questions(
        research_summary="Sena 和 Cardo 的 Mesh 技术已经很成熟，但都没有 HUD 集成。",
        research_topic="竞品 Mesh 对讲技术分析"
    )
    for q in questions:
        print(f"Q: {q.get('question', '')}")
        print(f"  背景: {q.get('background', '')}")
        print(f"  行动: {q.get('action', '')}")
        print()