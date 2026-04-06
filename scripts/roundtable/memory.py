"""
@description: 决策备忘录读写管理
@dependencies: pathlib, datetime, json
@last_modified: 2026-04-06
"""
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
import json


MEMO_DIR = Path(".ai-state/decision_memos")


def _ensure_memo_dir():
    """确保备忘录目录存在"""
    MEMO_DIR.mkdir(parents=True, exist_ok=True)


def create_decision_memo(topic: str, conclusion: str, supporting_claims: List[str],
                         rejected_alternatives: List[str] = None,
                         pending_confirmations: List[str] = None,
                         status: str = "待确认") -> str:
    """创建决策备忘录

    Args:
        topic: 议题名称
        conclusion: 结论摘要（一段话）
        supporting_claims: 支撑依据列表（带置信度标注）
        rejected_alternatives: 否决的替代方案
        pending_confirmations: 待确认事项
        status: 状态（已确认/待确认）

    Returns:
        备忘录文件路径
    """
    _ensure_memo_dir()

    safe_topic = "".join(c for c in topic[:30] if c.isalnum() or c in "_ -").strip()
    filename = f"{safe_topic}.md"
    filepath = MEMO_DIR / filename

    # 构建备忘录内容
    lines = [
        f"# 决策备忘录：{topic}",
        f"更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"状态：{status}",
        "",
        "## 结论",
        conclusion,
        "",
        "## 支撑依据",
    ]
    for i, claim in enumerate(supporting_claims, 1):
        lines.append(f"{i}. {claim}")

    if rejected_alternatives:
        lines.append("")
        lines.append("## 否决的替代方案")
        for alt in rejected_alternatives:
            lines.append(f"- {alt}")

    if pending_confirmations:
        lines.append("")
        lines.append("## 待确认")
        for item in pending_confirmations:
            lines.append(f"- {item}")

    # 写入文件
    filepath.write_text("\n".join(lines), encoding="utf-8")
    return str(filepath)


def read_decision_memo(topic: str) -> Optional[Dict[str, Any]]:
    """读取决策备忘录

    Returns:
        解析后的备忘录内容，如果不存在返回 None
    """
    _ensure_memo_dir()

    safe_topic = "".join(c for c in topic[:30] if c.isalnum() or c in "_ -").strip()
    filepath = MEMO_DIR / f"{safe_topic}.md"

    if not filepath.exists():
        return None

    content = filepath.read_text(encoding="utf-8")

    # 简单解析（Markdown 格式）
    result = {
        "topic": topic,
        "path": str(filepath),
        "raw_content": content,
    }

    # 提取状态
    for line in content.split("\n"):
        if line.startswith("状态："):
            result["status"] = line.replace("状态：", "").strip()
        if line.startswith("更新时间："):
            result["updated_at"] = line.replace("更新时间：", "").strip()

    return result


def update_decision_memo(topic: str, updates: Dict[str, Any]) -> str:
    """更新决策备忘录

    Args:
        topic: 议题名称
        updates: 更新内容 {"conclusion": "...", "status": "已确认", ...}

    Returns:
        更新后的文件路径
    """
    existing = read_decision_memo(topic)
    if not existing:
        # 不存在则创建
        return create_decision_memo(
            topic=topic,
            conclusion=updates.get("conclusion", ""),
            supporting_claims=updates.get("supporting_claims", []),
            rejected_alternatives=updates.get("rejected_alternatives", []),
            pending_confirmations=updates.get("pending_confirmations", []),
            status=updates.get("status", "待确认"),
        )

    # 存在则更新
    filepath = Path(existing["path"])
    content = existing["raw_content"]

    # 更新时间戳
    new_time = f"更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    content = content.replace(existing.get("updated_at", ""), new_time)

    # 更新状态
    if "status" in updates:
        old_status = existing.get("status", "待确认")
        new_status_line = f"状态：{updates['status']}"
        content = content.replace(f"状态：{old_status}", new_status_line)

    # 更新结论
    if "conclusion" in updates:
        lines = content.split("\n")
        new_lines = []
        in_conclusion = False
        for line in lines:
            if line == "## 结论":
                in_conclusion = True
                new_lines.append(line)
                continue
            if in_conclusion and line.startswith("##"):
                in_conclusion = False
            if in_conclusion:
                continue  # 跳过旧结论
            new_lines.append(line)
        # 在"## 结论"后插入新结论
        for i, line in enumerate(new_lines):
            if line == "## 结论":
                new_lines.insert(i + 1, updates["conclusion"])
                break
        content = "\n".join(new_lines)

    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


def list_decision_memos() -> List[Dict[str, Any]]:
    """列出所有决策备忘录"""
    _ensure_memo_dir()

    memos = []
    for md_file in MEMO_DIR.glob("*.md"):
        topic = md_file.stem
        memo = read_decision_memo(topic)
        if memo:
            memos.append({
                "topic": topic,
                "status": memo.get("status", "未知"),
                "updated_at": memo.get("updated_at", "未知"),
                "path": str(md_file),
            })
    return memos


def format_memos_for_context(topics: List[str] = None) -> str:
    """格式化备忘录用于上下文注入

    Args:
        topics: 指定议题列表，如果为 None 则返回所有

    Returns:
        格式化后的文本
    """
    _ensure_memo_dir()

    if topics:
        memos = [read_decision_memo(t) for t in topics]
        memos = [m for m in memos if m]
    else:
        memos = list_decision_memos()
        memos = [{"topic": m["topic"], "raw_content": read_decision_memo(m["topic"])["raw_content"]}
                 for m in memos]

    if not memos:
        return ""

    lines = ["## 已有决策备忘录"]
    for memo in memos:
        lines.append(f"\n### {memo.get('topic', '未知议题')}")
        # 只提取结论部分（不包含整个文档）
        content = memo.get("raw_content", "")
        in_conclusion = False
        for line in content.split("\n"):
            if line == "## 结论":
                in_conclusion = True
                continue
            if in_conclusion and line.startswith("##"):
                break
            if in_conclusion and line.strip():
                lines.append(line)
                break  # 只取结论第一段

    return "\n".join(lines)