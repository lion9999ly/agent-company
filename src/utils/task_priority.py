"""
@description: 任务优先级管理 - 用户实时任务优先，后台任务让路
@dependencies: 无
@last_modified: 2026-03-25
"""
import threading
import time


class TaskPriorityManager:
    """简单的优先级管理：P0 进来时 P2 暂停"""

    def __init__(self):
        self._p0_active = threading.Event()
        self._p0_active.clear()  # 默认没有 P0 任务
        self._p0_count = 0
        self._lock = threading.Lock()

    def p0_start(self):
        """用户实时任务开始"""
        with self._lock:
            self._p0_count += 1
            self._p0_active.set()

    def p0_end(self):
        """用户实时任务结束"""
        with self._lock:
            self._p0_count = max(0, self._p0_count - 1)
            if self._p0_count == 0:
                self._p0_active.clear()

    def wait_if_p0_active(self, timeout: float = 30):
        """P2 任务调用：如果有 P0 任务在跑，等待直到 P0 完成

        返回 True 表示等过了（有 P0 任务），False 表示没等
        """
        if self._p0_active.is_set():
            print(f"[Priority] P2 任务让路，等待 P0 完成...")
            # 等 P0 完成，最多等 timeout 秒
            start = time.time()
            while self._p0_active.is_set() and time.time() - start < timeout:
                time.sleep(2)
            if self._p0_active.is_set():
                print(f"[Priority] P0 仍在执行，P2 继续（已等 {timeout}s）")
            else:
                print(f"[Priority] P0 完成，P2 继续")
            return True
        return False

    @property
    def is_p0_active(self) -> bool:
        return self._p0_active.is_set()


_manager = None


def get_priority_manager() -> TaskPriorityManager:
    global _manager
    if _manager is None:
        _manager = TaskPriorityManager()
    return _manager