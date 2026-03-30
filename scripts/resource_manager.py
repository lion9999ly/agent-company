"""
@description: 本地资源自动管理 - 防止长时间运行导致电脑卡死
@dependencies: psutil (可选), pathlib, gc
@last_modified: 2026-03-25
"""
import gc
import json
import os
import sys
import shutil
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent


def cleanup_pycache():
    """清理所有 __pycache__ 目录"""
    count = 0
    for cache_dir in PROJECT_ROOT.rglob("__pycache__"):
        try:
            shutil.rmtree(cache_dir)
            count += 1
        except Exception:
            pass
    return count


def cleanup_old_reports(days: int = 7, keep_latest: int = 5):
    """清理旧报告：保留最近N天，更早的归档"""
    count = 0
    reports_dir = PROJECT_ROOT / ".ai-state" / "reports"
    if not reports_dir.exists():
        return count

    cutoff = datetime.now() - timedelta(days=days)
    archived_dir = reports_dir / "archived"
    archived_dir.mkdir(exist_ok=True)

    for f in reports_dir.iterdir():
        if f.is_file() and f.suffix in (".md", ".json"):
            try:
                if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    # 归档而不是删除
                    f.rename(archived_dir / f.name)
                    count += 1
            except Exception:
                continue

    # 归档目录最多保留 50 个文件
    archived_files = sorted(archived_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
    for f in archived_files[50:]:
        try:
            f.unlink()
        except Exception:
            pass

    return count


def cleanup_processed_inbox(keep_count: int = 20):
    """清理已处理的导入文件：保留最近N个，更早的删除"""
    count = 0
    processed_dir = PROJECT_ROOT / ".ai-state" / "inbox" / "processed"
    if not processed_dir.exists():
        return count

    # 按修改时间排序，保留最近的
    files = sorted(processed_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
    for f in files[keep_count:]:
        try:
            f.unlink()
            count += 1
        except Exception:
            continue

    return count


def cleanup_old_memory_cards(days: int = 30):
    """清理旧的经验卡片：超过N天且无评分的归档"""
    count = 0
    memory_dir = PROJECT_ROOT / ".ai-state" / "memory"
    if not memory_dir.exists():
        return count

    cutoff = datetime.now() - timedelta(days=days)
    archived_dir = memory_dir / "archived"
    archived_dir.mkdir(exist_ok=True)

    for f in memory_dir.glob("*.json"):
        try:
            # 检查是否有评分
            data = json.loads(f.read_text(encoding="utf-8"))
            has_rating = bool(data.get("user_rating"))

            # 检查是否超过30天
            is_old = datetime.fromtimestamp(f.stat().st_mtime) < cutoff

            if is_old and not has_rating:
                f.rename(archived_dir / f.name)
                count += 1
        except Exception:
            continue

    return count


def cleanup_flag_files(days: int = 3):
    """清理旧的 flag 文件：超过N天的删除"""
    count = 0
    cutoff = datetime.now() - timedelta(days=days)
    ai_state_dir = PROJECT_ROOT / ".ai-state"

    if not ai_state_dir.exists():
        return count

    for f in ai_state_dir.iterdir():
        if f.is_file() and (f.suffix == ".lock" or f.suffix == ".flag" or f.name.startswith("SYSTEM_")):
            try:
                if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink()
                    count += 1
            except Exception:
                continue

    return count


def cleanup_old_logs(days: int = 3):
    """清理超过 N 天的日志和临时文件"""
    count = 0
    cutoff = datetime.now() - timedelta(days=days)

    # 清理 .ai-state 下的旧日志
    for pattern in ["*.log", "*.jsonl"]:
        for f in (PROJECT_ROOT / ".ai-state").glob(pattern):
            try:
                if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink()
                    count += 1
            except Exception:
                continue

    return count


def cleanup_root_temp_files():
    """清理项目根目录下的临时文件（超过 24 小时的）"""
    count = 0
    cutoff = datetime.now() - timedelta(hours=24)

    # 临时文件模式：任务指令、测试文件、日志等
    temp_patterns = [
        "*_tasks_for_cc.md",
        "*_fixes.md",
        "*_optimizations.md",
        "hook_test.log",
        "run_import.py",
        "_kb_verify_output.txt",
        "output.log",
        "test_*.py",
        "auto_restart_cc.py",
        "day*_*.md",
        "overnight_*.md",
        "agent_deep_cognition.md",
        "autonomous_deep_dive.md",
        "large_file_*.md",
        # 大型安装包
        "claude-install-*.zip",
        "*-install-*.zip",
    ]

    for pattern in temp_patterns:
        for f in PROJECT_ROOT.glob(pattern):
            try:
                if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink()
                    count += 1
            except Exception:
                continue

    # 清理奇怪的命名文件（如 D:Users...hook_test.log）
    for f in PROJECT_ROOT.iterdir():
        if f.is_file() and ":" in f.name:
            try:
                f.unlink()
                count += 1
            except Exception:
                pass

    return count


def cleanup_memory():
    """强制 Python 垃圾回收，释放内存"""
    collected = gc.collect()
    return collected


def cleanup_conversations():
    """清理过期的对话记忆文件"""
    conv_dir = PROJECT_ROOT / ".ai-state" / "conversations"
    if not conv_dir.exists():
        return 0
    count = 0
    cutoff = datetime.now() - timedelta(days=3)
    for f in conv_dir.glob("*.json"):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
                count += 1
        except:
            continue
    return count


def get_system_status() -> dict:
    """获取系统资源状态"""
    status = {
        "python_memory_mb": 0,
        "disk_free_gb": 0,
        "pycache_count": 0,
        "kb_size_mb": 0,
        "processed_size_mb": 0,
    }

    # Python 进程内存
    try:
        import psutil
        process = psutil.Process(os.getpid())
        status["python_memory_mb"] = round(process.memory_info().rss / 1024 / 1024, 1)
        status["cpu_percent"] = psutil.cpu_percent(interval=1)
        status["memory_percent"] = psutil.virtual_memory().percent
    except ImportError:
        pass

    # 磁盘
    try:
        usage = shutil.disk_usage(PROJECT_ROOT)
        status["disk_free_gb"] = round(usage.free / 1024 / 1024 / 1024, 1)
    except:
        pass

    # __pycache__ 数量
    status["pycache_count"] = sum(1 for _ in PROJECT_ROOT.rglob("__pycache__"))

    # 知识库大小
    kb_root = PROJECT_ROOT / ".ai-state" / "knowledge"
    if kb_root.exists():
        total_size = sum(f.stat().st_size for f in kb_root.rglob("*.json"))
        status["kb_size_mb"] = round(total_size / 1024 / 1024, 1)

    # processed 文件大小
    processed_dir = PROJECT_ROOT / ".ai-state" / "inbox" / "processed"
    if processed_dir.exists():
        total_size = sum(f.stat().st_size for f in processed_dir.iterdir() if f.is_file())
        status["processed_size_mb"] = round(total_size / 1024 / 1024, 1)

    return status


def auto_cleanup():
    """自动清理一轮"""
    print(f"[ResourceMgr] 开始自动清理 ({datetime.now().strftime('%H:%M')})")

    cache_cleaned = cleanup_pycache()
    reports_archived = cleanup_old_reports()
    processed_cleaned = cleanup_processed_inbox()
    memory_archived = cleanup_old_memory_cards()
    flags_cleaned = cleanup_flag_files()
    logs_cleaned = cleanup_old_logs()
    root_cleaned = cleanup_root_temp_files()
    conv_cleaned = cleanup_conversations()
    gc_collected = cleanup_memory()

    status = get_system_status()

    report = (
        f"[ResourceMgr] 清理完成:\n"
        f"  __pycache__: 清理 {cache_cleaned} 个\n"
        f"  旧报告归档: {reports_archived} 个\n"
        f"  processed: 清理 {processed_cleaned} 个\n"
        f"  旧经验卡片归档: {memory_archived} 个\n"
        f"  flag 文件: 清理 {flags_cleaned} 个\n"
        f"  日志: 清理 {logs_cleaned} 个\n"
        f"  根目录临时: 清理 {root_cleaned} 个\n"
        f"  对话记忆: 清理 {conv_cleaned} 个\n"
        f"  GC: 回收 {gc_collected} 个对象\n"
        f"  内存: {status.get('memory_percent', '?')}%\n"
        f"  磁盘: {status.get('disk_free_gb', '?')} GB 可用\n"
        f"  知识库: {status.get('kb_size_mb', '?')} MB\n"
        f"  processed 目录: {status.get('processed_size_mb', '?')} MB"
    )
    print(report)
    return report


def start_resource_monitor(interval_hours: float = 2.0, feishu_notify=None):
    """启动定时资源监控线程"""
    def _monitor():
        while True:
            time.sleep(interval_hours * 3600)
            try:
                report = auto_cleanup()

                # 如果内存超过 80%，发警告
                status = get_system_status()
                mem_pct = status.get("memory_percent", 0)
                if mem_pct > 80 and feishu_notify:
                    feishu_notify(f"[WARNING] System memory {mem_pct}%, suggest closing unnecessary programs")

            except Exception as e:
                print(f"[ResourceMgr] Monitor failed: {e}")

    print(f"[ResourceMgr] Resource monitor started (cleanup every {interval_hours}h)")
    t = threading.Thread(target=_monitor, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    report = auto_cleanup()
    print("\nSystem status:")
    for k, v in get_system_status().items():
        print(f"  {k}: {v}")