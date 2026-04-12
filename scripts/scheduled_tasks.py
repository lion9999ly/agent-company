"""
@description: 定时任务调度系统
@dependencies: schedule, smolagents_research/run_research, competitor_monitor
@last_modified: 2026-04-12

任务：
- 00:00 深度学习（从 research_queue.json 读取主题）
- 06:00 竞品监控（调用 competitor_monitor.py）
- 07:00 系统日报（汇总昨日执行记录+KB新增+Git commits）

飞书推送：
- 每个任务只推开始+完成+异常三条消息
- 通过 curl localhost:9100 转发
"""

import os
import sys
import json
import time
import subprocess
import schedule
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

# 项目路径配置
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = PROJECT_ROOT / ".ai-state"
REPORTS_DIR = STATE_DIR / "reports"
RESEARCH_QUEUE_FILE = STATE_DIR / "research_queue.json"
EXECUTION_LOG_FILE = STATE_DIR / "execution_log.jsonl"

# 飞书推送配置
FEISHU_CHAT_ID = os.getenv("FEISHU_CHAT_ID", "")
METABOT_PORT = 9100


# ============================================================
# 飞书推送（通过 MetaBot 转发）
# ============================================================

def send_feishu_message(message: str, chat_id: str = None) -> bool:
    """通过 MetaBot (localhost:9100) 发送飞书消息

    Args:
        message: 消息内容
        chat_id: 飞书 chat_id

    Returns:
        是否发送成功
    """

    if chat_id is None:
        chat_id = FEISHU_CHAT_ID

    if not chat_id:
        print("[Warning] FEISHU_CHAT_ID 未配置，跳过飞书推送")
        return False

    try:
        # 通过 MetaBot 转发（localhost:9100）
        result = subprocess.run(
            ["curl", "-X", "POST",
             f"http://localhost:{METABOT_PORT}/send_message",
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"chat_id": chat_id, "message": message}),
             "--max-time", "10"],
            capture_output=True,
            text=True,
            timeout=15
        )

        if result.returncode == 0 and "success" in result.stdout.lower():
            return True
        else:
            # Fallback: 直接用 lark-cli
            result = subprocess.run(
                ["lark-cli", "im", "+messages-send",
                 "--chat-id", chat_id,
                 "--text", message,
                 "--as", "bot"],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0

    except subprocess.TimeoutExpired:
        print("[Warning] MetaBot 转发超时")
        return False
    except Exception as e:
        print(f"[Error] 飞书推送失败: {e}")
        return False


def notify_task_start(task_name: str) -> None:
    """通知任务开始"""
    message = f"🚀 [{task_name}] 开始执行 - {datetime.now().strftime('%H:%M:%S')}"
    print(message)
    send_feishu_message(message)


def notify_task_complete(task_name: str, summary: str) -> None:
    """通知任务完成"""
    # 摘要限制 500 字
    if len(summary) > 500:
        summary = summary[:497] + "..."

    message = f"✅ [{task_name}] 完成 - {datetime.now().strftime('%H:%M:%S')}\n\n{summary}"
    print(message)
    send_feishu_message(message)


def notify_task_error(task_name: str, error: str) -> None:
    """通知任务异常"""
    message = f"❌ [{task_name}] 异常 - {datetime.now().strftime('%H:%M:%S')}\n\n错误: {error}"
    print(message)
    send_feishu_message(message)


# ============================================================
# 任务执行日志
# ============================================================

def log_execution(task_name: str, status: str, details: Dict[str, Any]) -> None:
    """记录任务执行日志

    Args:
        task_name: 任务名称
        status: 状态 (started, completed, error)
        details: 详情
    """

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "task": task_name,
        "status": status,
        "details": details
    }

    # 追加写入日志文件
    EXECUTION_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(EXECUTION_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")


# ============================================================
# 任务 1: 深度学习 (00:00)
# ============================================================

def load_research_queue() -> List[Dict[str, Any]]:
    """加载研究队列"""

    if not RESEARCH_QUEUE_FILE.exists():
        print(f"[Warning] 研究队列不存在: {RESEARCH_QUEUE_FILE}")
        return []

    with open(RESEARCH_QUEUE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("queue", [])


def save_research_queue(queue: List[Dict[str, Any]]) -> None:
    """保存研究队列"""

    data = {
        "last_updated": datetime.now().isoformat(),
        "queue": queue
    }

    with open(RESEARCH_QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_next_research_topic() -> Optional[Dict[str, Any]]:
    """获取下一个待研究主题"""

    queue = load_research_queue()

    for item in queue:
        if item.get("status") == "pending":
            return item

    return None


def mark_research_completed(topic_id: str, result_summary: str) -> None:
    """标记研究主题为已完成"""

    queue = load_research_queue()

    for item in queue:
        if item.get("id") == topic_id:
            item["status"] = "completed"
            item["completed_at"] = datetime.now().isoformat()
            item["result_summary"] = result_summary
            break

    save_research_queue(queue)


def task_deep_research() -> None:
    """深度学习任务 (00:00)

    从 research_queue.json 读取主题，调用 smolagents 研究管道
    """

    task_name = "深度学习"

    notify_task_start(task_name)
    log_execution(task_name, "started", {"time": "00:00"})

    try:
        # 获取下一个主题
        topic = get_next_research_topic()

        if not topic:
            summary = "研究队列已空，无待执行主题"
            notify_task_complete(task_name, summary)
            log_execution(task_name, "completed", {"reason": "queue_empty"})
            return

        topic_id = topic.get("id")
        query = topic.get("query")

        print(f"[Deep Research] 主题: {query}")

        # 导入研究模块
        sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "smolagents_research"))
        from run_research import run_research

        # 执行研究
        result = run_research(
            query=query,
            provider="azure_norway",
            use_tavily=True
        )

        if result.get("success"):
            # 保存结果
            result_file = REPORTS_DIR / f"research_{topic_id}_{datetime.now().strftime('%Y%m%d')}.json"
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)

            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            # 标记完成
            summary = f"主题 [{topic.get('name', topic_id)}] 已完成\n结果保存: {result_file}"
            mark_research_completed(topic_id, summary[:200])

            notify_task_complete(task_name, summary)
            log_execution(task_name, "completed", {
                "topic_id": topic_id,
                "result_file": str(result_file),
                "elapsed": result.get("elapsed_seconds", 0)
            })

        else:
            error = result.get("error", "Unknown error")
            notify_task_error(task_name, error)
            log_execution(task_name, "error", {
                "topic_id": topic_id,
                "error": error
            })

    except Exception as e:
        notify_task_error(task_name, str(e))
        log_execution(task_name, "error", {"exception": str(e)})


# ============================================================
# 任务 2: 竞品监控 (06:00)
# ============================================================

def task_competitor_monitor() -> None:
    """竞品监控任务 (06:00)

    调用 competitor_monitor.py
    """

    task_name = "竞品监控"

    notify_task_start(task_name)
    log_execution(task_name, "started", {"time": "06:00"})

    try:
        # 导入竞品监控模块
        sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "smolagents_research"))
        from competitor_monitor import run_competitor_monitor

        # 执行监控
        result = run_competitor_monitor(
            provider="azure_norway",
            max_results=3,
            push_feishu=False  # 由本脚本统一推送
        )

        if result.get("success"):
            summary = result.get("summary", "竞品监控完成")

            notify_task_complete(task_name, summary)
            log_execution(task_name, "completed", {
                "report_file": result.get("report_file"),
                "dimensions": len(result.get("dimensions", {})),
                "elapsed": result.get("elapsed_seconds", 0)
            })

        else:
            error = result.get("error", "Unknown error")
            notify_task_error(task_name, error)
            log_execution(task_name, "error", {"error": error})

    except Exception as e:
        notify_task_error(task_name, str(e))
        log_execution(task_name, "error", {"exception": str(e)})


# ============================================================
# 任务 3: 系统日报 (07:00)
# ============================================================

def get_yesterday_execution_logs() -> List[Dict[str, Any]]:
    """获取昨日执行日志"""

    if not EXECUTION_LOG_FILE.exists():
        return []

    yesterday = datetime.now() - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")

    logs = []
    with open(EXECUTION_LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if entry.get("timestamp", "").startswith(yesterday_str):
                    logs.append(entry)
            except json.JSONDecodeError:
                continue

    return logs


def get_yesterday_kb_additions() -> List[str]:
    """获取昨日 KB 新增"""

    kb_dir = PROJECT_ROOT / "knowledge_base"
    if not kb_dir.exists():
        return []

    yesterday = datetime.now() - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")

    additions = []
    for kb_file in kb_dir.glob("**/*.md"):
        # 检查文件修改时间
        mtime = datetime.fromtimestamp(kb_file.stat().st_mtime)
        if mtime.strftime("%Y-%m-%d") == yesterday_str:
            additions.append(str(kb_file.relative_to(kb_dir)))

    return additions


def get_yesterday_git_commits() -> List[Dict[str, str]]:
    """获取昨日 Git commits"""

    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--since=yesterday", "--until=today"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=10
        )

        commits = []
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split(" ", 1)
                commits.append({
                    "hash": parts[0] if parts else "",
                    "message": parts[1] if len(parts) > 1 else ""
                })

        return commits

    except Exception:
        return []


def task_system_report() -> None:
    """系统日报任务 (07:00)

    汇总：昨日执行记录 + KB新增 + Git commits
    """

    task_name = "系统日报"

    notify_task_start(task_name)
    log_execution(task_name, "started", {"time": "07:00"})

    try:
        # 收集数据
        execution_logs = get_yesterday_execution_logs()
        kb_additions = get_yesterday_kb_additions()
        git_commits = get_yesterday_git_commits()

        # 统计
        task_counts = {}
        for log in execution_logs:
            task = log.get("task", "unknown")
            status = log.get("status", "unknown")
            key = f"{task}:{status}"
            task_counts[key] = task_counts.get(key, 0) + 1

        # 构建报告
        report = {
            "date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
            "execution_summary": {
                "total_logs": len(execution_logs),
                "task_counts": task_counts,
            },
            "kb_additions": {
                "count": len(kb_additions),
                "files": kb_additions[:10]  # 只显示前 10 个
            },
            "git_commits": {
                "count": len(git_commits),
                "messages": [c["message"] for c in git_commits[:10]]
            }
        }

        # 保存报告
        report_file = REPORTS_DIR / f"daily_report_{report['date']}.json"
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # 构建摘要（≤500字）
        summary_lines = [
            f"📅 {report['date']} 系统日报",
            f"",
            f"**执行统计**: {report['execution_summary']['total_logs']} 条日志",
        ]

        for key, count in task_counts.items():
            summary_lines.append(f"- {key}: {count}")

        summary_lines.append(f"\n**KB新增**: {report['kb_additions']['count']} 个文件")
        summary_lines.append(f"\n**Git commits**: {report['git_commits']['count']} 个")

        summary = "\n".join(summary_lines)

        notify_task_complete(task_name, summary)
        log_execution(task_name, "completed", {
            "report_file": str(report_file),
            "execution_count": len(execution_logs),
            "kb_count": len(kb_additions),
            "git_count": len(git_commits)
        })

    except Exception as e:
        notify_task_error(task_name, str(e))
        log_execution(task_name, "error", {"exception": str(e)})


# ============================================================
# 调度配置
# ============================================================

def setup_schedule() -> None:
    """配置定时任务"""

    # 深度学习 - 00:00
    schedule.every().day.at("00:00").do(task_deep_research)

    # 竞品监控 - 06:00
    schedule.every().day.at("06:00").do(task_competitor_monitor)

    # 系统日报 - 07:00
    schedule.every().day.at("07:00").do(task_system_report)

    print("[Schedule] 定时任务已配置:")
    print("  - 00:00 深度学习")
    print("  - 06:00 竞品监控")
    print("  - 07:00 系统日报")


def run_scheduler() -> None:
    """运行调度器（主循环）"""

    print("=" * 60)
    print("定时任务调度系统启动")
    print("=" * 60)

    setup_schedule()

    while True:
        schedule.run_pending()
        time.sleep(60)  # 每分钟检查一次


# ============================================================
# CLI 入口
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="定时任务调度系统")
    parser.add_argument("--run-now", action="store_true", help="立即执行所有任务（测试）")
    parser.add_argument("--task", choices=["deep_research", "competitor_monitor", "system_report"],
                        help="立即执行指定任务")

    args = parser.parse_args()

    if args.run_now:
        print("[Test] 立即执行所有任务")
        task_deep_research()
        task_competitor_monitor()
        task_system_report()
        print("[Test] 完成")

    elif args.task:
        print(f"[Test] 立即执行: {args.task}")
        if args.task == "deep_research":
            task_deep_research()
        elif args.task == "competitor_monitor":
            task_competitor_monitor()
        elif args.task == "system_report":
            task_system_report()

    else:
        run_scheduler()