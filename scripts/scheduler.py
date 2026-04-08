"""
@description: 独立定时任务调度器 - 与飞书 bot 进程分离
@dependencies: schedule, subprocess, agent
@last_modified: 2026-04-08

定时任务：
    01:00 - 深度学习（7h 窗口）
    06:00 - 竞品监控
    07:00 - 每日简报

运行方式：
    python scripts/scheduler.py          # 直接运行
    python scripts/scheduler.py --test   # 测试模式（立即执行一次）
"""
import os
import sys
import subprocess
import time
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

# 飞书 CLI
from scripts.feishu_output import LARK_CLI

LEO_CHAT_ID = os.getenv("LEO_CHAT_ID", "oc_43bca641a75a5beed8215541845c7b73")


def cli_send_message(text: str, chat_id: str = None) -> bool:
    """发送飞书消息"""
    target = chat_id or LEO_CHAT_ID
    try:
        result = subprocess.run(
            [LARK_CLI, "im", "+messages-send",
             "--chat-id", target, "--text", text, "--as", "bot"],
            capture_output=True, text=True, timeout=15
        )
        return result.returncode == 0
    except:
        return False


def trigger_deep_learning():
    """01:00 深度学习"""
    print(f"\n[{datetime.now()}] 深度学习启动...")
    cli_send_message("🌙 深度学习启动（预计 7 小时）")

    try:
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "tonight_deep_research.py")],
            cwd=str(PROJECT_ROOT),
            timeout=8 * 3600,  # 8小时超时
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            cli_send_message(f"✅ 深度学习完成\n{result.stdout[:500] if result.stdout else ''}")
        else:
            cli_send_message(f"⚠️ 深度学习失败: {result.stderr[:200] if result.stderr else 'unknown'}")
    except subprocess.TimeoutExpired:
        cli_send_message("⚠️ 深度学习超时（8h）")
    except Exception as e:
        cli_send_message(f"⚠️ 深度学习异常: {str(e)[:100]}")


def trigger_competitor_monitor():
    """06:00 竞品监控"""
    print(f"\n[{datetime.now()}] 竞品监控启动...")
    cli_send_message("🔍 竞品监控启动...")

    try:
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "competitor_monitor.py")],
            cwd=str(PROJECT_ROOT),
            timeout=30 * 60,  # 30分钟超时
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            # 结果由 competitor_monitor.py 自己发送飞书
            print(f"[Monitor] 完成")
        else:
            cli_send_message(f"⚠️ 竞品监控失败: {result.stderr[:200] if result.stderr else 'unknown'}")
    except Exception as e:
        cli_send_message(f"⚠️ 竞品监控异常: {str(e)[:100]}")


def trigger_daily_report():
    """07:00 每日简报"""
    print(f"\n[{datetime.now()}] 每日简报生成...")

    try:
        # 读取 system_status.md
        status_path = PROJECT_ROOT / ".ai-state" / "system_status.md"
        if status_path.exists():
            content = status_path.read_text(encoding="utf-8")
            # 提取关键信息生成简报
            lines = content.split("\n")
            brief_lines = []
            for line in lines[:20]:
                if line.startswith("#") or line.startswith("##") or line.startswith("-"):
                    brief_lines.append(line)

            brief = "\n".join(brief_lines[:15])
            cli_send_message(f"📅 每日简报 {datetime.now().strftime('%Y-%m-%d')}\n\n{brief}")
        else:
            cli_send_message("⚠️ 无法生成简报：system_status.md 不存在")
    except Exception as e:
        cli_send_message(f"⚠️ 简报生成异常: {str(e)[:100]}")


def trigger_auto_learn():
    """30分钟自学习（可选，每小时触发一次）"""
    print(f"\n[{datetime.now()}] 自学习触发...")
    try:
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "auto_learn.py")],
            cwd=str(PROJECT_ROOT),
            timeout=45 * 60,
            capture_output=True,
            text=True
        )
    except Exception as e:
        print(f"[AutoLearn] 异常: {e}")


# ============================================================
# 调度器
# ============================================================

try:
    import schedule
    HAS_SCHEDULE = True
except ImportError:
    HAS_SCHEDULE = False
    print("[Scheduler] schedule 模块未安装，使用简单轮询")


def run_scheduler():
    """运行调度器"""
    if HAS_SCHEDULE:
        # 使用 schedule 库
        schedule.every().day.at("01:00").do(trigger_deep_learning)
        schedule.every().day.at("06:00").do(trigger_competitor_monitor)
        schedule.every().day.at("07:00").do(trigger_daily_report)
        # 每小时自学习（可选）
        # schedule.every().hour.at(":00").do(trigger_auto_learn)

        print(f"[Scheduler] 定时任务已注册:")
        print("  - 01:00 深度学习")
        print("  - 06:00 竞品监控")
        print("  - 07:00 每日简报")

        while True:
            schedule.run_pending()
            time.sleep(60)

    else:
        # 简单轮询（无 schedule 库）
        print("[Scheduler] 使用简单轮询模式")

        # 记录上次执行时间
        last_runs = {}

        while True:
            now = datetime.now()
            hour = now.hour
            minute = now.minute
            date_str = now.strftime("%Y-%m-%d")

            # 01:00 深度学习
            if hour == 1 and minute < 5:
                if last_runs.get("deep_learning") != date_str:
                    last_runs["deep_learning"] = date_str
                    trigger_deep_learning()

            # 06:00 竞品监控
            if hour == 6 and minute < 5:
                if last_runs.get("competitor") != date_str:
                    last_runs["competitor"] = date_str
                    trigger_competitor_monitor()

            # 07:00 每日简报
            if hour == 7 and minute < 5:
                if last_runs.get("report") != date_str:
                    last_runs["report"] = date_str
                    trigger_daily_report()

            time.sleep(300)  # 5分钟检查一次


def test_all():
    """测试模式：立即执行所有任务一次"""
    print("[Scheduler] 测试模式：立即执行所有任务")
    trigger_competitor_monitor()
    trigger_daily_report()
    # 深度学习太长，测试模式跳过
    print("[Scheduler] 测试完成（深度学习已跳过）")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="测试模式")
    args = parser.parse_args()

    if args.test:
        test_all()
    else:
        print("=" * 50)
        print("定时任务调度器")
        print("=" * 50)
        run_scheduler()