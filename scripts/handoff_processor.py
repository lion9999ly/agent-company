"""Handoff 处理器 — 读取 claude.ai 生成的 handoff 文件
@description: 扫描并处理 claude.ai 会话产生的 handoff 文件
@dependencies: claude_cli_helper
@last_modified: 2026-04-05
"""
import json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
HANDOFF_DIR = PROJECT_ROOT / ".ai-state" / "handoffs"
HANDOFF_DIR.mkdir(parents=True, exist_ok=True)


def scan_unprocessed() -> list:
    """扫描未处理的 handoff 文件"""
    unprocessed = []
    for f in sorted(HANDOFF_DIR.glob("handoff_*.md")):
        meta = f.with_suffix('.processed')
        if not meta.exists():
            unprocessed.append(f)
    # 也支持 test_ 开头的测试文件
    for f in sorted(HANDOFF_DIR.glob("test_*.md")):
        meta = f.with_suffix('.processed')
        if not meta.exists():
            unprocessed.append(f)
    return unprocessed


def mark_processed(handoff_path: Path):
    """标记 handoff 为已处理"""
    meta = handoff_path.with_suffix('.processed')
    meta.write_text(time.strftime('%Y-%m-%d %H:%M'), encoding='utf-8')


def get_pending_tasks(handoff_path: Path) -> list:
    """从 handoff 文件中提取待执行任务"""
    content = handoff_path.read_text(encoding='utf-8')
    # 简单解析：提取 CC 提示词块
    tasks = []
    import re
    blocks = re.findall(r'```\n(.*?)```', content, re.DOTALL)
    for block in blocks:
        if 'git' in block or 'commit' in block:
            tasks.append(block.strip())
    return tasks


def execute_handoff(handoff_path: Path) -> dict:
    """执行 handoff 文件中的任务

    Args:
        handoff_path: handoff 文件路径

    Returns:
        执行结果
    """
    try:
        from scripts.claude_cli_helper import call_claude_cli, is_claude_cli_available
    except ImportError:
        print(f"[Handoff] claude_cli_helper 不可用")
        mark_processed(handoff_path)
        return {"success": False, "reason": "claude_cli_helper not available"}

    content = handoff_path.read_text(encoding='utf-8')
    print(f"[Handoff] 执行: {handoff_path.name}")

    if is_claude_cli_available():
        result = call_claude_cli(
            f"读取以下 handoff 内容，按顺序执行其中的待办任务：\n\n{content[:4000]}",
            timeout=180,
            cwd=str(PROJECT_ROOT)
        )

        if result:
            mark_processed(handoff_path)
            print(f"[Handoff] 完成: {handoff_path.name}")
            return {"success": True, "output": result[:500]}
        else:
            print(f"[Handoff] CLI 返回空")
            mark_processed(handoff_path)
            return {"success": False, "reason": "CLI returned empty"}
    else:
        print(f"[Handoff] CLI 不可用，仅标记已读")
        mark_processed(handoff_path)
        return {"success": False, "reason": "CLI unavailable"}


def process_all_handoffs():
    """处理所有未处理的 handoff 文件"""
    unprocessed = scan_unprocessed()
    results = []
    for handoff_path in unprocessed:
        tasks = get_pending_tasks(handoff_path)
        for task in tasks:
            results.append({"file": str(handoff_path), "task": task[:100]})
        mark_processed(handoff_path)
    return results


if __name__ == "__main__":
    pending = scan_unprocessed()
    print(f"发现 {len(pending)} 个未处理的 handoff 文件")
    for f in pending:
        print(f"  - {f.name}")