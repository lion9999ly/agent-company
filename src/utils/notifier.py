"""
@description: 任务完成通知工具 - 播放提示音
@dependencies: 无（使用 Windows 内置 winsound）
@last_modified: 2026-03-25
"""
import sys


def notify(sound_type: str = "success"):
    """播放任务完成提示音

    Args:
        sound_type: "success" | "error" | "warning"
    """
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