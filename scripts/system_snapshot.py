"""系统快照生成器 — 生成系统状态快照
@description: 生成系统状态快照到 .ai-state/system_snapshot.md
@dependencies: knowledge_base, model_gateway
@last_modified: 2026-04-05
"""
import os
import json
import time
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
SNAPSHOT_PATH = PROJECT_ROOT / ".ai-state" / "system_snapshot.md"


def get_git_status() -> dict:
    """获取 Git 状态"""
    import subprocess
    try:
        # 当前分支
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            cwd=str(PROJECT_ROOT), stderr=subprocess.DEVNULL
        ).decode().strip()

        # 最近提交
        last_commit = subprocess.check_output(
            ["git", "log", "-1", "--oneline"],
            cwd=str(PROJECT_ROOT), stderr=subprocess.DEVNULL
        ).decode().strip()

        # 未提交文件数
        status = subprocess.check_output(
            ["git", "status", "--short"],
            cwd=str(PROJECT_ROOT), stderr=subprocess.DEVNULL
        ).decode().strip()
        uncommitted = len([l for l in status.split("\n") if l.strip()])

        return {
            "branch": branch,
            "last_commit": last_commit,
            "uncommitted_files": uncommitted
        }
    except Exception as e:
        return {"error": str(e)}


def get_kb_stats() -> dict:
    """获取知识库统计"""
    kb_dir = PROJECT_ROOT / ".ai-state" / "knowledge"
    stats = {"total_files": 0, "total_size_mb": 0, "by_category": {}}

    if kb_dir.exists():
        for category_dir in kb_dir.iterdir():
            if category_dir.is_dir():
                files = list(category_dir.glob("*.json"))
                size = sum(f.stat().st_size for f in files if f.is_file())
                stats["by_category"][category_dir.name] = {
                    "files": len(files),
                    "size_kb": size // 1024
                }
                stats["total_files"] += len(files)
                stats["total_size_mb"] += size / (1024 * 1024)

    return stats


def get_model_status() -> dict:
    """获取模型状态"""
    try:
        from scripts.litellm_gateway import get_model_gateway
        gw = get_model_gateway()
        enabled = [name for name, cfg in gw.models.items() if cfg.enabled]
        return {
            "total_models": len(gw.models),
            "enabled_models": len(enabled),
            "enabled_list": enabled[:10]  # 只显示前10个
        }
    except Exception as e:
        return {"error": str(e)}


def get_recent_logs() -> dict:
    """获取最近日志"""
    logs = {}

    # auto_fix_log
    fix_log = PROJECT_ROOT / ".ai-state" / "auto_fix_log.jsonl"
    if fix_log.exists():
        try:
            lines = fix_log.read_text(encoding='utf-8').strip().split("\n")
            logs["auto_fix_count"] = len(lines)
            if lines:
                last = json.loads(lines[-1])
                logs["last_fix_time"] = last.get("timestamp", "unknown")
        except:
            pass

    # integration_test_log
    test_log = PROJECT_ROOT / ".ai-state" / "integration_test_log.jsonl"
    if test_log.exists():
        try:
            lines = test_log.read_text(encoding='utf-8').strip().split("\n")
            passed = sum(1 for l in lines if '"passed": true' in l)
            logs["integration_tests"] = f"{passed}/{len(lines)} passed"
        except:
            pass

    return logs


def generate_snapshot() -> str:
    """生成系统快照"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    git_status = get_git_status()
    kb_stats = get_kb_stats()
    model_status = get_model_status()
    recent_logs = get_recent_logs()

    lines = [
        f"# 系统快照 — {now}",
        "",
        "## Git 状态",
        f"- 分支: `{git_status.get('branch', 'unknown')}`",
        f"- 最近提交: {git_status.get('last_commit', 'unknown')}",
        f"- 未提交文件: {git_status.get('uncommitted_files', 0)}",
        "",
        "## 知识库统计",
        f"- 总文件数: {kb_stats['total_files']}",
        f"- 总大小: {kb_stats['total_size_mb']:.2f} MB",
        "",
        "### 分类统计",
    ]

    for cat, data in kb_stats["by_category"].items():
        lines.append(f"- {cat}: {data['files']} 文件, {data['size_kb']} KB")

    lines.extend([
        "",
        "## 模型状态",
        f"- 已注册: {model_status.get('total_models', 0)}",
        f"- 已启用: {model_status.get('enabled_models', 0)}",
        f"- 启用列表: {', '.join(model_status.get('enabled_list', []))}",
        "",
        "## 最近活动",
    ])

    for key, val in recent_logs.items():
        lines.append(f"- {key}: {val}")

    lines.extend([
        "",
        "---",
        f"*快照生成时间: {now}*"
    ])

    return "\n".join(lines)


def save_snapshot():
    """保存快照到文件"""
    content = generate_snapshot()
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(content, encoding='utf-8')
    print(f"[Snapshot] 已保存到 {SNAPSHOT_PATH}")
    return content


if __name__ == "__main__":
    content = save_snapshot()
    print(content)