"""
@description: 任务完成通知工具 - 播放提示音
@dependencies: 无（使用 Windows 内置 winsound）
@last_modified: 2026-03-25
"""
import sys
import threading

# 线程局部存储：每个线程独立的静默标志
_thread_local = threading.local()


def set_silent(mode: bool = True):
    """设置当前线程的静默模式

    Args:
        mode: True 禁用提示音，False 启用提示音
    """
    _thread_local.silent = mode


def is_silent() -> bool:
    """返回当前线程是否静默模式"""
    return getattr(_thread_local, 'silent', False)


def notify(sound_type: str = "success"):
    """播放任务完成提示音

    仅在 PyCharm terminal 直接执行的任务中播放，
    飞书后台线程任务不播放。

    Args:
        sound_type: "success" | "error" | "warning"
    """
    # 线程局部静默模式下不播放
    if is_silent():
        return

    # 额外检查：如果调用栈中包含 feishu_sdk_client，也不播放
    # 这是为了捕获那些忘记设置静默模式的后台线程
    import inspect
    for frame_info in inspect.stack():
        if 'feishu_sdk_client' in frame_info.filename:
            return

    if sys.platform != "win32":
        return  # 仅支持 Windows

    try:
        import winsound

        if sound_type == "success":
            # 两声短促上扬音（任务成功）
            winsound.Beep(800, 150)
            winsound.Beep(1000, 200)
        elif sound_type == "error":
            # 一声低沉长音（失败）
            winsound.Beep(400, 500)
        elif sound_type == "warning":
            # 两声中音（警告）
            winsound.Beep(600, 200)
            winsound.Beep(600, 200)
    except Exception:
        pass  # 静默失败，不影响主流程


if __name__ == "__main__":
    # 测试
    print("Testing success sound...")
    notify("success")
    import time
    time.sleep(1)
    print("Testing error sound...")
    notify("error")
    time.sleep(1)
    print("Testing warning sound...")
    notify("warning")