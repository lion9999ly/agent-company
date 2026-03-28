"""
@description: 独立健康监控进程 - 监控主服务状态，异常时报警+自动重启
@dependencies: requests, subprocess, pathlib, datetime
@last_modified: 2026-03-21
"""
import os
import sys
import time
import json
import subprocess
import requests
from pathlib import Path
from datetime import datetime, timedelta

# 配置
WEBHOOK_URL = os.environ.get("FEISHU_WEBHOOK_URL",
    "https://open.feishu.cn/open-apis/bot/v2/hook/b3ecb9ca-53d3-4b9d-bc81-1f15bf9e402d")
PROJECT_ROOT = Path(__file__).parent.parent
HEARTBEAT_PATH = PROJECT_ROOT / ".ai-state" / "heartbeat.txt"
MAIN_SCRIPT = PROJECT_ROOT / "scripts" / "feishu_sdk_client.py"
CHECK_INTERVAL = 60          # 检查间隔（秒）
HEARTBEAT_TIMEOUT = 600      # 心跳超时（秒），10分钟无心跳视为异常
PYTHON_PATH = sys.executable


def send_webhook(title: str, content: str):
    """通过飞书 webhook 发送报警消息"""
    try:
        payload = {
            "msg_type": "text",
            "content": {"text": f"🚨 [{title}]\n{content}\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
        }
        requests.post(WEBHOOK_URL, json=payload, timeout=10)
        print(f"[Watchdog] 报警已发送: {title}")
    except Exception as e:
        print(f"[Watchdog] 报警发送失败: {e}")


def is_main_service_running() -> bool:
    """检查主服务进程是否存活"""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"],
                capture_output=True, text=True, timeout=10
            )
            return check_heartbeat_alive()
        else:
            result = subprocess.run(
                ["pgrep", "-f", "feishu_sdk_client"],
                capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
    except Exception:
        return False


def check_heartbeat_alive() -> bool:
    """检查心跳文件是否在超时范围内"""
    if not HEARTBEAT_PATH.exists():
        return False
    try:
        last_beat = datetime.fromisoformat(HEARTBEAT_PATH.read_text(encoding="utf-8").strip())
        age = (datetime.now() - last_beat).total_seconds()
        return age < HEARTBEAT_TIMEOUT
    except Exception:
        return False


def restart_main_service() -> bool:
    """重启主服务"""
    print(f"[Watchdog] 正在重启主服务...")
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/FI", "WINDOWTITLE eq feishu_sdk*"],
                capture_output=True, timeout=10
            )
            time.sleep(2)

        env = os.environ.copy()
        subprocess.Popen(
            [PYTHON_PATH, str(MAIN_SCRIPT)],
            cwd=str(PROJECT_ROOT),
            env=env,
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        )
        print(f"[Watchdog] 主服务已重启")
        return True
    except Exception as e:
        print(f"[Watchdog] 重启失败: {e}")
        return False


def run_watchdog():
    """主循环"""
    print("=" * 50)
    print("Watchdog 健康监控")
    print("=" * 50)
    print(f"  检查间隔: {CHECK_INTERVAL}s")
    print(f"  心跳超时: {HEARTBEAT_TIMEOUT}s")
    print(f"  Webhook: {WEBHOOK_URL[:50]}...")
    print(f"  主服务: {MAIN_SCRIPT}")
    print("=" * 50)

    consecutive_failures = 0

    while True:
        try:
            alive = check_heartbeat_alive()

            if alive:
                if consecutive_failures > 0:
                    print(f"[Watchdog] 服务已恢复正常")
                    send_webhook("服务恢复", f"主服务已恢复正常运行\n之前连续 {consecutive_failures} 次检测失败")
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                print(f"[Watchdog] 检测异常（连续 {consecutive_failures} 次）")

                if consecutive_failures == 1:
                    hb_info = "心跳文件不存在"
                    if HEARTBEAT_PATH.exists():
                        try:
                            last_beat = HEARTBEAT_PATH.read_text(encoding="utf-8").strip()
                            hb_info = f"最后心跳: {last_beat}"
                        except Exception:
                            pass
                    send_webhook("服务异常", f"主服务心跳超时\n{hb_info}")

                if consecutive_failures == 3:
                    send_webhook("自动重启", "连续 3 次检测异常，正在自动重启主服务...")
                    success = restart_main_service()
                    if success:
                        send_webhook("重启完成", "主服务已重启，等待恢复...")
                        time.sleep(30)
                    else:
                        send_webhook("重启失败", "自动重启失败，请手动检查！")

                if consecutive_failures >= 10 and consecutive_failures % 5 == 0:
                    send_webhook("持续异常", f"已连续 {consecutive_failures} 次检测失败，服务可能无法自动恢复，请手动介入！")

        except Exception as e:
            print(f"[Watchdog] 检查异常: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run_watchdog()