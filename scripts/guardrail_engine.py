"""决策护栏引擎 — 检测触发条件并执行预设行动
@description: 检测文本中的触发条件并执行预设行动
@dependencies: 无
@last_modified: 2026-04-04
"""
import yaml, re, json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
GUARDRAILS_PATH = PROJECT_ROOT / ".ai-state" / "decision_guardrails.yaml"


def load_guardrails() -> list:
    """加载护栏规则"""
    if GUARDRAILS_PATH.exists():
        data = yaml.safe_load(GUARDRAILS_PATH.read_text(encoding='utf-8'))
        return data.get("guardrails", [])
    return []


def check_guardrails(text: str, source: str = "deep_research") -> list:
    """检查文本是否触发任何护栏规则

    Args:
        text: 待检查的文本
        source: 来源标识（deep_research, external_monitor, feishu）

    Returns:
        触发的护栏列表
    """
    guardrails = load_guardrails()
    triggered = []

    for g in guardrails:
        trigger = g.get("trigger", "")
        if not trigger:
            continue

        # 构建正则表达式
        # 将 AND/OR 转换为正则逻辑
        pattern = trigger
        pattern = pattern.replace(" AND ", ".*")
        pattern = pattern.replace(" OR ", "|")
        pattern = pattern.replace("(", "")
        pattern = pattern.replace(")", "")

        try:
            if re.search(pattern, text, re.IGNORECASE):
                triggered.append({
                    "id": g.get("id"),
                    "action": g.get("action"),
                    "task": g.get("task"),
                    "notify": g.get("notify", False),
                    "priority": g.get("priority", "normal"),
                    "source": source,
                    "timestamp": time.strftime('%Y-%m-%d %H:%M'),
                })
        except re.error:
            # 正则表达式错误，跳过
            continue

    return triggered


def execute_guardrail_action(triggered: dict, send_reply=None, reply_target=None):
    """执行护栏行动"""
    action = triggered.get("action")

    if action == "notify_only":
        if send_reply and reply_target and triggered.get("notify"):
            msg = f"⚠️ 护栏触发: {triggered.get('id')}\n请关注: {triggered.get('task', {}).get('title', '未知事件')}"
            send_reply(reply_target, msg)

    elif action == "auto_add_task":
        # 自动添加任务到研究池
        task = triggered.get("task", {})
        _add_research_task(task)
        if send_reply and reply_target and triggered.get("notify"):
            msg = f"⚠️ 护栏触发: {triggered.get('id')}\n已自动添加任务: {task.get('title', '未知')}"
            send_reply(reply_target, msg)

    elif action == "auto_deep_drill":
        topic = triggered.get("topic", "未知主题")
        _trigger_deep_drill(topic)
        if send_reply and reply_target and triggered.get("notify"):
            msg = f"⚠️ 护栏触发: {triggered.get('id')}\n已启动深度分析: {topic}"
            send_reply(reply_target, msg)


def _add_research_task(task: dict):
    """添加任务到研究池"""
    task_pool_path = PROJECT_ROOT / ".ai-state" / "research_task_pool.yaml"
    task_pool_path.parent.mkdir(parents=True, exist_ok=True)

    if task_pool_path.exists():
        data = yaml.safe_load(task_pool_path.read_text(encoding='utf-8')) or {"tasks": []}
    else:
        data = {"tasks": []}

    task["status"] = "pending"
    task["created_at"] = time.strftime('%Y-%m-%d %H:%M')
    task["source"] = "guardrail"

    data["tasks"].append(task)
    task_pool_path.write_text(yaml.dump(data, allow_unicode=True), encoding='utf-8')


def _trigger_deep_drill(topic: str):
    """触发深度钻探"""
    # 记录触发
    log_path = PROJECT_ROOT / ".ai-state" / "guardrail_triggers.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "topic": topic,
        "triggered_at": time.strftime('%Y-%m-%d %H:%M'),
    }
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    # 测试
    test_text = "歌尔的产线变动可能导致产能风险"
    triggered = check_guardrails(test_text)
    print(f"触发 {len(triggered)} 条护栏")
    for t in triggered:
        print(f"  - {t.get('id')}: {t.get('action')}")