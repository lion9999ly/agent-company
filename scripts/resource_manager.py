"""
@description: 本地资源自动管理 - 防止长时间运行导致电脑卡死
@dependencies: psutil (可选), pathlib, gc
@last_modified: 2026-03-24
"""
import gc
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


def cleanup_old_logs(days: int = 3):
    """清理超过 N 天的日志和临时文件"""
    count = 0
    cutoff = datetime.now() - timedelta(days=days)

    # 清理 .ai-state 下的旧报告（保留最近 3 天）
    for pattern in ["reports/*.md", "reports/*.json"]:
        for f in (PROJECT_ROOT / ".ai-state").glob(pattern):
            try:
                if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink()
                    count += 1
            except:
                continue

    # 清理旧的 alignment 报告（保留最近 5 份）
    reports_dir = PROJECT_ROOT / ".ai-state" / "reports"
    if reports_dir.exists():
        alignment_files = sorted(reports_dir.glob("alignment_*.md"), key=lambda x: x.stat().st_mtime, reverse=True)
        for f in alignment_files[5:]:
            try:
                f.unlink()
                count += 1
            except:
                continue

    # 清理 processed inbox（保留最近 20 个）
    processed_dir = PROJECT_ROOT / ".ai-state" / "inbox" / "processed"
    if processed_dir.exists():
        processed_files = sorted(processed_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
        for f in processed_files[20:]:
            try:
                f.unlink()
                count += 1
            except:
                continue

    return count


def cleanup_memory():
    """强制 Python 垃圾回收，释放内存"""
    collected = gc.collect()
    return collected


def get_system_status() -> dict:
    """获取系统资源状态"""
    status = {
        "python_memory_mb": 0,
        "disk_free_gb": 0,
        "pycache_count": 0,
        "kb_size_mb": 0,
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

    return status


def auto_cleanup():
    """自动清理一轮"""
    print(f"[ResourceMgr] 开始自动清理 ({datetime.now().strftime('%H:%M')})")

    cache_cleaned = cleanup_pycache()
    logs_cleaned = cleanup_old_logs()
    gc_collected = cleanup_memory()

    status = get_system_status()

    report = (
        f"[ResourceMgr] 清理完成:\n"
        f"  __pycache__: 清理 {cache_cleaned} 个\n"
        f"  旧文件: 清理 {logs_cleaned} 个\n"
        f"  GC: 回收 {gc_collected} 个对象\n"
        f"  内存: {status.get('memory_percent', '?')}%\n"
        f"  磁盘: {status.get('disk_free_gb', '?')} GB 可用\n"
        f"  知识库: {status.get('kb_size_mb', '?')} MB"
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