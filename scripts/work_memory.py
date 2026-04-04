"""工作记忆 — 记录对话中的关键结论和决策
@description: 从对话文本中提取决策信号并保存供后续参考
@dependencies: 无
@last_modified: 2026-04-04
"""
import json, re, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = PROJECT_ROOT / ".ai-state" / "work_memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def extract_decisions_from_text(text: str) -> list:
    """从对话文本中提取决策信号"""
    signals = [
        r"决定了[：:]\s*(.+)",
        r"结论[是为：:]\s*(.+)",
        r"否决了?\s*(.+)",
        r"确认[：:]\s*(.+)",
        r"选择了?\s*(.+?)(?:方案|路线)",
    ]
    decisions = []
    for pattern in signals:
        for match in re.finditer(pattern, text):
            decisions.append({
                "decision": match.group(1).strip()[:200],
                "timestamp": time.strftime('%Y-%m-%d %H:%M'),
                "source": "feishu_conversation"
            })
    return decisions


def save_work_memory(decisions: list):
    """保存工作记忆"""
    if not decisions:
        return
    log_file = MEMORY_DIR / "decisions.jsonl"
    with open(log_file, 'a', encoding='utf-8') as f:
        for d in decisions:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


def get_relevant_memories(query: str, limit: int = 5) -> str:
    """检索与当前问题相关的工作记忆"""
    log_file = MEMORY_DIR / "decisions.jsonl"
    if not log_file.exists():
        return ""
    keywords = set(re.findall(r'[\u4e00-\u9fff]{2,4}|[A-Z][a-z]+', query))
    results = []
    for line in log_file.read_text(encoding='utf-8').strip().split('\n'):
        try:
            d = json.loads(line)
            overlap = sum(1 for kw in keywords if kw in d.get("decision", ""))
            if overlap > 0:
                results.append((overlap, d))
        except Exception:
            continue
    results.sort(reverse=True)
    if not results:
        return ""
    text = "\n## 相关工作记忆\n"
    for _, d in results[:limit]:
        text += f"- [{d.get('timestamp', '')}] {d['decision']}\n"
    return text


def get_all_decisions() -> list:
    """获取所有工作记忆"""
    log_file = MEMORY_DIR / "decisions.jsonl"
    if not log_file.exists():
        return []
    decisions = []
    for line in log_file.read_text(encoding='utf-8').strip().split('\n'):
        try:
            d = json.loads(line)
            decisions.append(d)
        except Exception:
            continue
    return decisions


if __name__ == "__main__":
    test_text = "决定了：采用 OLED 方案。结论是成本可控。"
    decisions = extract_decisions_from_text(test_text)
    print(f"提取到 {len(decisions)} 条决策")