"""
@description: 长任务进度心跳 — 统一接口，支持日志+飞书推送
@dependencies: pathlib, datetime, json
@last_modified: 2026-03-26

用法:
    from src.utils.progress_heartbeat import ProgressHeartbeat

    hb = ProgressHeartbeat("知识图谱扩展", total=100, feishu_callback=send_reply_fn)
    for i, item in enumerate(items):
        process(item)
        hb.tick(detail=f"处理: {item['title'][:30]}")
    hb.finish("扩展完成")
"""

import time
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable

ROOT = Path(__file__).resolve().parent.parent.parent
HEARTBEAT_DIR = ROOT / ".ai-state"


class ProgressHeartbeat:
    """长任务进度心跳

    - 每条打日志
    - 每 log_interval 条打详细日志
    - 每 feishu_interval 条（或每 feishu_time_interval 秒）推飞书
    - 自动写磁盘心跳文件（供 watchdog 检测）
    """

    def __init__(
        self,
        task_name: str,
        total: int = 0,
        feishu_callback: Optional[Callable[[str], None]] = None,
        log_interval: int = 10,
        feishu_interval: int = 50,
        feishu_time_interval: int = 300,  # 至少每 5 分钟推一次飞书
    ):
        self.task_name = task_name
        self.total = total
        self.feishu_callback = feishu_callback
        self.log_interval = log_interval
        self.feishu_interval = feishu_interval
        self.feishu_time_interval = feishu_time_interval

        self.current = 0
        self.start_time = time.time()
        self.last_feishu_time = time.time()
        self.errors = 0

        # 写入心跳文件
        self._heartbeat_file = HEARTBEAT_DIR / "long_task_heartbeat.json"
        self._write_heartbeat("started")

        # 初始飞书通知
        progress_str = f"/{total}" if total > 0 else ""
        self._feishu(f"⏳ [{task_name}] 开始执行 (共 {total} 项)" if total > 0
                     else f"⏳ [{task_name}] 开始执行")

        print(f"[Heartbeat] {task_name} 开始, total={total}")

    def tick(self, detail: str = "", success: bool = True):
        """每处理一条调用一次"""
        self.current += 1
        if not success:
            self.errors += 1

        elapsed = time.time() - self.start_time
        progress_pct = f" ({self.current * 100 // self.total}%)" if self.total > 0 else ""

        # 每条简短日志
        status = "✓" if success else "✗"
        print(f"  [{self.task_name}] [{self.current}/{self.total}]{progress_pct} {status} {detail[:60]}")

        # 每 log_interval 条详细日志
        if self.current % self.log_interval == 0:
            speed = self.current / elapsed if elapsed > 0 else 0
            eta = (self.total - self.current) / speed if speed > 0 and self.total > 0 else 0
            print(f"  [{self.task_name}] 进度: {self.current}/{self.total}{progress_pct}"
                  f" | 速度: {speed:.1f}/s | ETA: {eta / 60:.1f}min | 错误: {self.errors}")

        # 飞书推送：按条数或时间
        time_since_last = time.time() - self.last_feishu_time
        should_push = (
            (self.feishu_interval > 0 and self.current % self.feishu_interval == 0) or
            (time_since_last >= self.feishu_time_interval)
        )

        if should_push:
            speed = self.current / elapsed if elapsed > 0 else 0
            eta = (self.total - self.current) / speed if speed > 0 and self.total > 0 else 0
            eta_str = f"，预计还需 {eta / 60:.0f} 分钟" if eta > 0 else ""
            error_str = f"，{self.errors} 个失败" if self.errors > 0 else ""
            self._feishu(
                f"📊 [{self.task_name}] {self.current}/{self.total}{progress_pct}"
                f"{eta_str}{error_str}"
            )
            self.last_feishu_time = time.time()

        # 更新心跳文件
        self._write_heartbeat("running")

    def finish(self, summary: str = ""):
        """任务完成"""
        elapsed = time.time() - self.start_time
        elapsed_min = elapsed / 60

        msg = (
            f"✅ [{self.task_name}] 完成\n"
            f"处理: {self.current}/{self.total} | 耗时: {elapsed_min:.1f}min"
        )
        if self.errors > 0:
            msg += f" | 失败: {self.errors}"
        if summary:
            msg += f"\n{summary}"

        print(f"[Heartbeat] {msg}")
        self._feishu(msg)
        self._write_heartbeat("completed")

    def error(self, error_msg: str):
        """任务异常终止"""
        elapsed = time.time() - self.start_time
        msg = (
            f"❌ [{self.task_name}] 异常终止\n"
            f"进度: {self.current}/{self.total} | 耗时: {elapsed / 60:.1f}min\n"
            f"错误: {error_msg[:200]}"
        )
        print(f"[Heartbeat] {msg}")
        self._feishu(msg)
        self._write_heartbeat("error")

    def _feishu(self, msg: str):
        """推送飞书（如果有 callback）"""
        if self.feishu_callback:
            try:
                self.feishu_callback(msg)
            except Exception as e:
                print(f"[Heartbeat] 飞书推送失败: {e}")

    def _write_heartbeat(self, status: str):
        """写入心跳文件"""
        try:
            data = {
                "task_name": self.task_name,
                "status": status,
                "current": self.current,
                "total": self.total,
                "errors": self.errors,
                "elapsed_sec": int(time.time() - self.start_time),
                "updated_at": datetime.now().isoformat(),
            }
            self._heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
            self._heartbeat_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
