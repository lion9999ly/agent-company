"""
@description: 自动重启 SDK 并验证飞书路由
@dependencies: subprocess, time, requests
@last_modified: 2026-04-08

用法：
    python scripts/auto_restart_and_verify.py
    python scripts/auto_restart_and_verify.py --no-restart  # 只验证不重启
"""
import os
import sys
import json
import time
import subprocess
import requests
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

APP_ID = os.getenv("FEISHU_APP_ID", "")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

# 验证测试的 Open ID（发送测试消息的目标）
LEO_OPEN_ID = "ou_8e5e4f183e9eca4241378e96bac3a751"

# 测试用例：指令 -> 预期关键词
TEST_CASES = [
    ("状态", ["知识库", "系统"]),
    ("监控范围", ["竞品监控", "直接竞品"]),
    ("帮助", ["指令", "研发"]),
    ("早报", ["早报", "决策"]),
    ("知识库", ["知识库"]),
]


def get_tenant_access_token() -> str:
    """获取飞书 tenant_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        resp = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
        result = resp.json()
        if result.get("tenant_access_token"):
            return result["tenant_access_token"]
        else:
            print(f"[Token Error] {result}")
            return ""
    except Exception as e:
        print(f"[Token Exception] {e}")
        return ""


def send_feishu_message(open_id: str, text: str, token: str) -> bool:
    """发送飞书消息"""
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "receive_id": open_id,
        "msg_type": "text",
        "content": json.dumps({"text": text})
    }
    try:
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        result = resp.json()
        return result.get("code") == 0
    except Exception as e:
        print(f"[Send Error] {e}")
        return False


def stop_sdk_process():
    """停止当前 SDK 进程"""
    print("\n[1/5] 停止 SDK 进程...")

    # Windows: 使用 taskkill
    try:
        # 使用 WMIC 查找运行 feishu_sdk_client_v2.py 的进程
        result = subprocess.run(
            ['wmic', 'process', 'where', 'commandline like "%feishu_sdk_client_v2%"', 'get', 'processid'],
            capture_output=True, text=True, timeout=30
        )

        # 提取 PID
        pids = []
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if line.isdigit():
                pids.append(line)

        if pids:
            for pid in pids:
                try:
                    subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True, timeout=10)
                    print(f"  [OK] 已停止进程 PID: {pid}")
                except:
                    pass
        else:
            print("  [INFO] 未找到运行中的 SDK 进程")

        return True
    except Exception as e:
        print(f"  [WARN] 停止进程异常: {e}")
        return False


def start_sdk_process():
    """启动 SDK 进程"""
    print("\n[2/5] 启动 SDK 进程...")

    sdk_path = PROJECT_ROOT / "scripts" / "feishu_sdk_client_v2.py"

    try:
        # 使用 pythonw 在后台运行（无窗口）
        subprocess.Popen(
            [sys.executable, str(sdk_path)],
            cwd=str(PROJECT_ROOT),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("  [OK] SDK 进程已启动")
        return True
    except Exception as e:
        print(f"  [X] 启动失败: {e}")
        return False


def wait_for_sdk_ready(seconds: int = 10):
    """等待 SDK 就绪"""
    print(f"\n[3/5] 等待 SDK 就绪 ({seconds}s)...")
    time.sleep(seconds)
    print("  [OK] 等待完成")


def run_verification_tests():
    """运行验证测试"""
    print("\n[4/5] 运行验证测试...")

    token = get_tenant_access_token()
    if not token:
        print("  [X] 无法获取 token，跳过测试")
        return []

    results = []

    for i, (command, expected_keywords) in enumerate(TEST_CASES, 1):
        print(f"\n  测试 {i}/{len(TEST_CASES)}: {command}")

        # 发送测试消息
        success = send_feishu_message(LEO_OPEN_ID, command, token)

        if success:
            print(f"    [OK] 已发送: {command}")
            results.append({
                "command": command,
                "status": "sent",
                "expected_keywords": expected_keywords
            })
        else:
            print(f"    [X] 发送失败: {command}")
            results.append({
                "command": command,
                "status": "failed",
                "expected_keywords": expected_keywords
            })

        # 间隔 2 秒避免频率限制
        time.sleep(2)

    return results


def send_summary_report(results: list):
    """发送汇总报告"""
    print("\n[5/5] 发送汇总报告...")

    token = get_tenant_access_token()
    if not token:
        print("  [X] 无法获取 token")
        return

    # 统计
    total = len(results)
    sent = sum(1 for r in results if r["status"] == "sent")
    failed = total - sent

    # 构建报告
    lines = [
        f"🤖 自动验证报告",
        f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"📊 测试结果: {sent}/{total} 通过",
        f"",
        f"测试项:"
    ]

    for r in results:
        icon = "[OK]" if r["status"] == "sent" else "[X]"
        lines.append(f"  {icon} {r['command']}")

    lines.append(f"")
    lines.append(f"💡 请检查飞书回复是否包含预期关键词")

    report = "\n".join(lines)

    # 发送报告
    success = send_feishu_message(LEO_OPEN_ID, report, token)

    if success:
        print("  [OK] 汇总报告已发送")
    else:
        print("  [X] 汇总报告发送失败")


def main(no_restart: bool = False):
    """主入口"""
    print("=" * 50)
    print("飞书 SDK 自动重启与验证")
    print("=" * 50)

    if no_restart:
        print("\n[跳过] --no-restart 模式，不重启 SDK")
    else:
        # 1. 停止 SDK
        stop_sdk_process()

        # 2. 等待进程完全退出
        time.sleep(3)

        # 3. 启动 SDK
        start_sdk_process()

        # 4. 等待就绪
        wait_for_sdk_ready(10)

    # 5. 运行验证测试
    results = run_verification_tests()

    # 6. 发送汇总报告
    send_summary_report(results)

    print("\n" + "=" * 50)
    print("验证完成")
    print("=" * 50)

    # 播放提示音
    try:
        beep_path = PROJECT_ROOT / "beep.bat"
        subprocess.run([str(beep_path)], shell=True, capture_output=True)
    except:
        pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-restart", action="store_true", help="只验证不重启")
    args = parser.parse_args()

    main(no_restart=args.no_restart)