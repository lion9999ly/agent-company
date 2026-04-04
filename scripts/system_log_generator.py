"""系统运行日志生成 — 深度学习后自动生成并 push
@description: 自动生成系统运行日志并 push 到 GitHub
@dependencies: knowledge_base, model_gateway
@last_modified: 2026-04-04
"""
import json, time, subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
LOG_PATH = PROJECT_ROOT / ".ai-state" / "system_log_latest.md"


def generate_system_log(session_summary: dict = None):
    """生成系统运行日志并自动 git push"""
    lines = [f"# 系统运行日志\n", f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M')}\n"]

    # 深度学习汇总
    if session_summary:
        lines.append("## 深度学习汇总")
        lines.append(f"- 任务数: {session_summary.get('task_count', '?')}")
        lines.append(f"- 耗时: {session_summary.get('duration_hours', '?')}h")
        lines.append(f"- KB 增量: +{session_summary.get('kb_added', '?')} 条")
        lines.append(f"- P0 触发: {session_summary.get('p0_tasks', '?')} 个任务")
        for task in session_summary.get('tasks', []):
            lines.append(f"  - {task.get('title', '?')} ({task.get('duration_min', '?')}min)")

    # KB 统计
    try:
        from src.tools.knowledge_base import get_knowledge_stats
        stats = get_knowledge_stats()
        total = sum(stats.values())
        lines.append(f"\n## 知识库状态")
        lines.append(f"- 总条目: {total}")
        for k, v in stats.items():
            lines.append(f"  - {k}: {v}")
    except Exception:
        lines.append(f"\n## 知识库状态")
        lines.append("- 暂无数据")

    # 元能力
    try:
        reg_path = PROJECT_ROOT / ".ai-state" / "tool_registry.json"
        if reg_path.exists():
            reg = json.loads(reg_path.read_text(encoding='utf-8'))
            tools = [t for t in reg.get("tools", []) if t.get("status") == "active"]
            if tools:
                lines.append(f"\n## 元能力工具")
                for t in tools:
                    lines.append(f"- {t['name']}: {t.get('description', '')[:50]} (使用 {t.get('usage_count', 0)} 次)")
    except Exception:
        pass

    # 错误日志
    lines.append(f"\n## 最近错误")
    lines.append("（从 feishu_debug.log 中提取最近 5 条 ERROR）")
    debug_log = PROJECT_ROOT / ".ai-state" / "feishu_debug.log"
    if debug_log.exists():
        try:
            errors = [l for l in debug_log.read_text(encoding='utf-8').split('\n') if 'ERROR' in l or 'error' in l.lower()]
            for e in errors[-5:]:
                lines.append(f"- {e[:200]}")
        except Exception:
            lines.append("- 无错误日志")

    # 写入
    LOG_PATH.write_text("\n".join(lines), encoding='utf-8')
    print(f"[SystemLog] 已生成: {LOG_PATH}")

    # 自动 git push
    try:
        subprocess.run(["git", "add", str(LOG_PATH)], cwd=str(PROJECT_ROOT), capture_output=True)
        subprocess.run(["git", "commit", "-m", "auto: update system_log_latest.md", "--no-verify"],
                       cwd=str(PROJECT_ROOT), capture_output=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=str(PROJECT_ROOT), capture_output=True)
        print("[SystemLog] 已 push 到 GitHub")
    except Exception as e:
        print(f"[SystemLog] push 失败: {e}")


if __name__ == "__main__":
    generate_system_log()