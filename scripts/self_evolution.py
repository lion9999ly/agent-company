"""
@description: 自进化引擎 - 定期复盘经验卡片，生成改进提案并执行
@dependencies: json, pathlib, src.utils.model_gateway, src.tools.knowledge_base
@last_modified: 2026-03-21
"""
import sys
import json
import re
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.model_gateway import get_model_gateway
from src.tools.knowledge_base import add_knowledge, search_knowledge, get_knowledge_stats
from src.tools.tool_registry import get_tool_registry

MEMORY_DIR = Path(__file__).parent.parent / ".ai-state" / "memory"
EVOLUTION_DIR = Path(__file__).parent.parent / ".ai-state" / "evolution"
PROMPTS_PATH = Path(__file__).parent.parent / "src" / "config" / "agent_prompts.yaml"
TOPICS_PATH = Path(__file__).parent.parent / ".ai-state" / "knowledge" / "learning_topics.json"


def _load_recent_cards(limit: int = 10) -> list:
    """加载最近的经验卡片"""
    if not MEMORY_DIR.exists():
        return []
    files = sorted(MEMORY_DIR.glob("*.json"), reverse=True)[:limit]
    cards = []
    for f in files:
        try:
            cards.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return cards


def _analyze_cards(cards: list) -> dict:
    """分析经验卡片，提取统计数据"""
    stats = {
        "total": len(cards),
        "critic_pass_first_try": 0,
        "critic_reject_count": 0,
        "user_ratings": {"A": 0, "B": 0, "C": 0, "D": 0, "none": 0},
        "user_feedback": [],
        "knowledge_gaps": [],
        "roles_frequency": {},
        "avg_critic_rounds": 0,
        "synthesis_conflicts_total": 0,
    }

    total_rounds = 0
    for card in cards:
        # Critic 统计
        rounds = card.get("critic_rounds", 1)
        total_rounds += rounds
        if rounds <= 1:
            stats["critic_pass_first_try"] += 1
        else:
            stats["critic_reject_count"] += (rounds - 1)

        # 用户评价
        rating = card.get("user_rating")
        if rating in ("A", "B", "C", "D"):
            stats["user_ratings"][rating] += 1
        else:
            stats["user_ratings"]["none"] += 1

        # 用户反馈
        feedback = card.get("user_feedback")
        if feedback:
            stats["user_feedback"].append(feedback)

        # 知识缺口
        gaps = card.get("knowledge_gaps", [])
        stats["knowledge_gaps"].extend(gaps)

        # 角色频率
        roles = card.get("roles_assigned", [])
        for r in roles:
            if isinstance(r, str):
                stats["roles_frequency"][r] = stats["roles_frequency"].get(r, 0) + 1

        # 矛盾数
        stats["synthesis_conflicts_total"] += card.get("synthesis_conflicts", 0)

    if cards:
        stats["avg_critic_rounds"] = round(total_rounds / len(cards), 1)

    return stats


def run_review(progress_callback=None) -> str:
    """执行团队复盘，生成改进报告和提案"""
    EVOLUTION_DIR.mkdir(parents=True, exist_ok=True)

    cards = _load_recent_cards(10)
    if len(cards) < 3:
        return "[Review] 经验卡片不足 3 条，暂不复盘"

    stats = _analyze_cards(cards)
    kb_stats = get_knowledge_stats()

    if progress_callback:
        progress_callback("[Review] 分析经验卡片中...")

    # 构建 LLM prompt
    gateway = get_model_gateway()
    prompt = (
        f"你是智能骑行头盔研发中心的 CPO Echo，正在做团队定期复盘。\n\n"
        f"## 经验卡片统计（最近 {stats['total']} 个任务）\n"
        f"- Critic 首次 PASS 率：{stats['critic_pass_first_try']}/{stats['total']}\n"
        f"- 平均 Critic 轮数：{stats['avg_critic_rounds']}\n"
        f"- 用户评价分布：A={stats['user_ratings']['A']} B={stats['user_ratings']['B']} "
        f"C={stats['user_ratings']['C']} D={stats['user_ratings']['D']} 未评={stats['user_ratings']['none']}\n"
        f"- 用户反馈：{stats['user_feedback']}\n"
        f"- 角色分配频率：{stats['roles_frequency']}\n"
        f"- 整合矛盾总数：{stats['synthesis_conflicts_total']}\n"
        f"- 知识库现状：{kb_stats}，总计 {sum(kb_stats.values())} 条\n\n"
        f"## 最近任务目标\n"
    )
    for card in cards[:5]:
        goal = card.get("task_goal", "")[:80]
        rating = card.get("user_rating", "未评")
        prompt += f"- {goal} [评价:{rating}]\n"

    prompt += (
        f"\n## 你的任务\n"
        f"基于以上数据，生成团队改进报告。严格按以下 JSON 格式回复：\n"
        f'{{"report": "200字以内的团队表现总结", '
        f'"improvements": ['
        f'{{"type": "knowledge|topic|prompt|config", '
        f'"risk": "low|medium", '
        f'"description": "具体改进描述", '
        f'"action": "具体执行动作"}}, ...], '
        f'"strengths": ["团队做得好的点1", "点2"]}}\n\n'
        f"改进类型说明：\n"
        f"- knowledge: 知识库补充（低风险，可自动执行）\n"
        f"- topic: 学习主题新增（低风险，可自动执行）\n"
        f"- prompt: Agent prompt 调整（中风险，需审批）\n"
        f"- config: 系统配置调整（中风险，需审批）\n"
    )

    result = gateway.call_azure_openai(
        "cpo", prompt,
        "你是研发团队的 CPO。只输出 JSON，不要有其他内容。基于数据给出务实的改进建议。",
        "self_review"
    )

    if not result.get("success"):
        return f"[Review] LLM 调用失败: {result.get('error')}"

    # 解析 JSON
    response = result["response"].strip()
    response = re.sub(r'^```json\s*', '', response)
    response = re.sub(r'\s*```$', '', response)

    try:
        review_data = json.loads(response)
    except Exception as e:
        return f"[Review] JSON 解析失败: {e}\n原始: {response[:300]}"

    if progress_callback:
        progress_callback("[Review] 执行低风险改进中...")

    # 执行低风险改进
    auto_executed = []
    need_approval = []

    for imp in review_data.get("improvements", []):
        imp_type = imp.get("type", "")
        risk = imp.get("risk", "medium")
        desc = imp.get("description", "")
        action = imp.get("action", "")

        if risk == "low" and imp_type == "knowledge":
            # 自动补充知识
            registry = get_tool_registry()
            search_result = registry.call("deep_research", action)
            if search_result.get("success") and len(search_result.get("data", "")) > 50:
                add_knowledge(
                    title=desc[:50],
                    domain="lessons",
                    content=search_result["data"][:800],
                    tags=["auto_evolution"],
                    source="self_evolution",
                    confidence="medium"
                )
                auto_executed.append(desc)

        elif risk == "low" and imp_type == "topic":
            # 自动添加学习主题
            if TOPICS_PATH.exists():
                topics_data = json.loads(TOPICS_PATH.read_text(encoding="utf-8"))
                topics_data["topics"].append({
                    "query": action,
                    "domain": "lessons",
                    "tags": ["auto_evolution"]
                })
                topics_data["updated_at"] = datetime.now().strftime("%Y-%m-%d")
                TOPICS_PATH.write_text(json.dumps(topics_data, ensure_ascii=False, indent=2), encoding="utf-8")
                auto_executed.append(desc)

        elif risk == "medium":
            need_approval.append(imp)

    # 保存复盘记录
    review_record = {
        "timestamp": datetime.now().isoformat(),
        "stats": stats,
        "review": review_data,
        "auto_executed": auto_executed,
        "need_approval": need_approval
    }
    record_path = EVOLUTION_DIR / f"review_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    record_path.write_text(json.dumps(review_record, ensure_ascii=False, indent=2), encoding="utf-8")

    # 生成报告
    report_lines = ["[Team Review] 团队复盘报告"]
    report_lines.append(f"\n{review_data.get('report', '')}")

    strengths = review_data.get("strengths", [])
    if strengths:
        report_lines.append(f"\n[Strengths]")
        for s in strengths:
            report_lines.append(f"  + {s}")

    if auto_executed:
        report_lines.append(f"\n[Auto Executed] ({len(auto_executed)} items)")
        for a in auto_executed:
            report_lines.append(f"  -> {a}")

    if need_approval:
        report_lines.append(f"\n[Need Approval] ({len(need_approval)} items)")
        for n in need_approval:
            report_lines.append(f"  ? [{n['type']}] {n['description']}")
            report_lines.append(f"    Action: {n['action']}")

    kb_new = get_knowledge_stats()
    report_lines.append(f"\n[Knowledge] {kb_new}")

    report = "\n".join(report_lines)
    print(report)
    return report


def check_and_trigger(current_card_count: int) -> bool:
    """检查是否应该触发复盘（每 5 个任务一次）"""
    if current_card_count < 3:
        return False
    if current_card_count % 5 == 0:
        return True
    return False


if __name__ == "__main__":
    report = run_review()
    print(report)