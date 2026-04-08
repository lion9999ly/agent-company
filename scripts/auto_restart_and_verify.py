"""
@description: 自动验证脚本 - 重启 SDK + 直接调用底层函数验证 + 飞书通知
@dependencies: pathlib, json, model_gateway, roundtable, subprocess, requests
@last_modified: 2026-04-08

流程：
    1. 停止 feishu_sdk_client_v2.py 进程
    2. 重新启动 SDK（后台）
    3. 等待连接就绪（检测日志）
    4. 执行验证
    5. 发送报告到飞书

用法：
    python scripts/auto_restart_and_verify.py           # 完整流程
    python scripts/auto_restart_and_verify.py --no-push  # 不发送飞书
    python scripts/auto_restart_and_verify.py --verify-only  # 只验证不重启
"""
import os
import sys
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

APP_ID = os.getenv("FEISHU_APP_ID", "")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
LEO_OPEN_ID = "ou_8e5e4f183e9eca4241378e96bac3a751"

SDK_SCRIPT = "scripts/feishu_sdk_client_v2.py"
SDK_LOG = PROJECT_ROOT / ".ai-state" / "feishu_debug.log"
PID_FILE = PROJECT_ROOT / ".ai-state" / "sdk.pid"


class VerifyResult:
    """验证结果"""
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.error = None
        self.details = []

    def success(self, detail: str = ""):
        self.passed = True
        if detail:
            self.details.append(detail)

    def fail(self, error: str):
        self.passed = False
        self.error = error


def stop_sdk():
    """停止 SDK 进程"""
    print("\n[1/3] 停止 SDK 进程...")

    # 尝试从 PID 文件读取
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True, timeout=10)
            print(f"  [OK] 已停止 SDK 进程 PID: {pid}")
            PID_FILE.unlink()
            time.sleep(2)
            return True
        except:
            pass

    # 查找运行中的 SDK 进程（通过命令行参数识别）
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] == 'python.exe':
                    cmdline = ' '.join(proc.info.get('cmdline', []))
                    if 'feishu_sdk_client' in cmdline:
                        proc.kill()
                        print(f"  [OK] 已停止 SDK 进程 PID: {proc.info['pid']}")
            except:
                continue
        time.sleep(2)
        return True
    except ImportError:
        pass

    print("  [INFO] 未找到运行中的 SDK 进程")
    return True


def start_sdk():
    """启动 SDK 进程"""
    print("\n[2/3] 启动 SDK 进程...")

    sdk_path = PROJECT_ROOT / SDK_SCRIPT

    if not sdk_path.exists():
        print(f"  [ERROR] SDK 脚本不存在: {sdk_path}")
        return False

    try:
        # 清空旧日志
        if SDK_LOG.exists():
            SDK_LOG.write_text("", encoding="utf-8")

        # 后台启动
        proc = subprocess.Popen(
            [sys.executable, str(sdk_path)],
            cwd=str(PROJECT_ROOT),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # 记录 PID
        PID_FILE.write_text(str(proc.pid))
        print(f"  [OK] SDK 进程已启动 PID: {proc.pid}")
        return True

    except Exception as e:
        print(f"  [ERROR] 启动失败: {e}")
        return False


def wait_for_sdk_ready(timeout: int = 30):
    """等待 SDK 连接就绪"""
    print(f"\n等待 SDK 就绪 (超时 {timeout}s)...")

    start_time = time.time()
    ready_keywords = ["服务启动", "等待消息", "Connected", "ready"]

    while time.time() - start_time < timeout:
        if SDK_LOG.exists():
            try:
                content = SDK_LOG.read_text(encoding="utf-8")
                for kw in ready_keywords:
                    if kw in content:
                        print(f"  [OK] SDK 已就绪 (检测到: {kw})")
                        return True
            except:
                pass

        time.sleep(1)
        print(".", end="", flush=True)

    print("\n  [WARN] SDK 就绪超时，继续验证...")
    return False


# ==================== 验证函数 ====================

def verify_system_status() -> VerifyResult:
    """验证1: 状态指令 - 读取 system_status.md"""
    result = VerifyResult("状态指令")

    try:
        status_path = PROJECT_ROOT / ".ai-state" / "system_status.md"

        if not status_path.exists():
            result.fail("system_status.md 文件不存在")
            return result

        content = status_path.read_text(encoding="utf-8")

        if "最近变更" in content or len(content) > 100:
            result.success(f"文件存在，内容长度: {len(content)} 字符")
        else:
            result.fail("内容不符合预期")

    except Exception as e:
        result.fail(str(e))

    return result


def verify_monitor_config() -> VerifyResult:
    """验证2: 监控范围 - 读取 competitor_monitor_config.json"""
    result = VerifyResult("监控范围")

    try:
        config_path = PROJECT_ROOT / ".ai-state" / "competitor_monitor_config.json"

        if not config_path.exists():
            result.fail("competitor_monitor_config.json 文件不存在")
            return result

        config = json.loads(config_path.read_text(encoding="utf-8"))
        layers = config.get("monitor_layers", config.get("layers", {}))

        if len(layers) < 6:
            result.fail(f"监控层数不足: {len(layers)} < 6")
            return result

        result.success(f"共 {len(layers)} 层")

    except Exception as e:
        result.fail(str(e))

    return result


def verify_task_spec() -> VerifyResult:
    """验证3: 圆桌 TaskSpec 加载"""
    result = VerifyResult("圆桌 TaskSpec")

    try:
        from scripts.roundtable.task_spec import load_task_spec

        spec = load_task_spec("hud_demo")

        if spec is None:
            result.fail("hud_demo TaskSpec 加载失败")
            return result

        mode = getattr(spec, "generator_input_mode", None)
        criteria = getattr(spec, "acceptance_criteria", [])

        if not mode:
            result.fail("缺少 generator_input_mode")
            return result

        if len(criteria) < 10:
            result.fail(f"acceptance_criteria 不足: {len(criteria)} < 10")
            return result

        result.success(f"generator_input_mode={mode}, criteria={len(criteria)}条")

    except ImportError as e:
        result.fail(f"导入失败: {e}")
    except Exception as e:
        result.fail(str(e))

    return result


def verify_verifier_rules() -> VerifyResult:
    """验证4: Verifier 规则库"""
    result = VerifyResult("Verifier 规则库")

    try:
        rules_dir = PROJECT_ROOT / ".ai-state" / "verifier_rules"

        if not rules_dir.exists():
            result.fail("verifier_rules 目录不存在")
            return result

        global_rule = rules_dir / "global.json"
        if not global_rule.exists():
            result.fail("global.json 不存在")
            return result

        rule_files = list(rules_dir.glob("*.json"))
        result.success(f"共 {len(rule_files)} 个规则文件")

    except Exception as e:
        result.fail(str(e))

    return result


def verify_model_gateway() -> VerifyResult:
    """验证5: model_gateway 调用"""
    result = VerifyResult("Model Gateway")

    try:
        from src.utils.model_gateway import get_model_gateway

        gw = get_model_gateway()
        test_result = gw.call("gpt_5_4", "回复OK", "测试连接", "test")

        if test_result.get("success"):
            response = test_result.get("response", "")[:50]
            result.success(f"调用成功，响应: {response}")
        else:
            error = test_result.get("error", "unknown")[:100]
            result.fail(f"调用失败: {error}")

    except ImportError as e:
        result.fail(f"导入失败: {e}")
    except Exception as e:
        result.fail(str(e))

    return result


def verify_route_matching() -> VerifyResult:
    """验证6: 飞书路由匹配"""
    result = VerifyResult("路由匹配")

    try:
        test_cases = [
            ("状态", "text_router.py", "状态"),
            ("监控范围", "text_router.py", "监控范围"),
            ("圆桌:", "roundtable_handler.py", "圆桌:"),
            ("拉取指令", "import_handlers.py", "拉取指令"),
        ]

        matched = []
        failed = []

        for command, handler_file, keyword in test_cases:
            handler_path = PROJECT_ROOT / "scripts" / "feishu_handlers" / handler_file
            if handler_path.exists():
                content = handler_path.read_text(encoding="utf-8")
                if keyword in content:
                    matched.append(command.rstrip(":"))
                else:
                    failed.append(f"{command.rstrip(':')}(路由缺失)")
            else:
                failed.append(f"{command.rstrip(':')}(文件缺失)")

        if failed:
            result.fail(f"匹配失败: {', '.join(failed)}")
        else:
            result.success(f"全部匹配: {', '.join(matched)}")

    except Exception as e:
        result.fail(str(e))

    return result


# ==================== 报告与通知 ====================

def generate_report(results: list, restart_ok: bool = True) -> str:
    """生成验证报告"""
    lines = [
        f"# 自动验证报告",
        f"",
        f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"**SDK 重启**: {'成功' if restart_ok else '失败'}",
        f"",
        f"## 验证结果",
        f"",
    ]

    passed = sum(1 for r in results if r.passed)
    total = len(results)

    lines.append(f"| 状态 | 项目 | 详情 |")
    lines.append(f"|:----:|------|------|")

    for r in results:
        icon = "[OK]" if r.passed else "[X]"
        detail = r.details[0] if r.details else (r.error or "-")
        if len(detail) > 50:
            detail = detail[:50] + "..."
        lines.append(f"| {icon} | {r.name} | {detail} |")

    lines.append(f"")
    lines.append(f"**通过率**: {passed}/{total}")

    return "\n".join(lines)


def send_to_feishu(report: str) -> bool:
    """发送报告到飞书（直接调用 API，不依赖 SDK）"""
    import requests

    token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        resp = requests.post(
            token_url,
            json={"app_id": APP_ID, "app_secret": APP_SECRET},
            timeout=10
        )
        token = resp.json().get("tenant_access_token", "")
        if not token:
            print("  [ERROR] 无法获取飞书 token")
            return False
    except Exception as e:
        print(f"  [ERROR] 获取 token 失败: {e}")
        return False

    msg_url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    content = report[:3500] if len(report) > 3500 else report

    data = {
        "receive_id": LEO_OPEN_ID,
        "msg_type": "text",
        "content": json.dumps({"text": content})
    }

    try:
        resp = requests.post(msg_url, headers=headers, json=data, timeout=10)
        result = resp.json()
        if result.get("code") == 0:
            print("  [OK] 报告已发送到飞书")
            return True
        else:
            print(f"  [ERROR] 发送失败: {result.get('msg', result)}")
            return False
    except Exception as e:
        print(f"  [ERROR] 发送飞书失败: {e}")
        return False


# ==================== 主流程 ====================

def run_verification():
    """执行验证"""
    results = []

    print("\n[1/6] 状态指令...")
    results.append(verify_system_status())

    print("[2/6] 监控范围...")
    results.append(verify_monitor_config())

    print("[3/6] 圆桌 TaskSpec...")
    results.append(verify_task_spec())

    print("[4/6] Verifier 规则库...")
    results.append(verify_verifier_rules())

    print("[5/6] Model Gateway...")
    results.append(verify_model_gateway())

    print("[6/6] 路由匹配...")
    results.append(verify_route_matching())

    return results


def main(verify_only: bool = False, no_push: bool = False):
    """主入口"""
    print("=" * 50)
    print("SDK 自动重启 + 验证")
    print("=" * 50)

    restart_ok = True

    if not verify_only:
        # 1. 停止 SDK
        stop_sdk()

        # 2. 启动 SDK
        if not start_sdk():
            print("[ERROR] 启动 SDK 失败")
            restart_ok = False

        # 3. 等待就绪
        if restart_ok:
            wait_for_sdk_ready(timeout=30)

    # 4. 执行验证
    print("\n" + "=" * 50)
    print("[3/3] 执行验证")
    print("=" * 50)

    results = run_verification()

    # 5. 生成报告
    report = generate_report(results, restart_ok)

    # 写入文件
    report_path = PROJECT_ROOT / ".ai-state" / "verify_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"\n报告已写入: {report_path}")

    # 6. 发送飞书
    if not no_push:
        print("\n发送报告到飞书...")
        send_to_feishu(report)

    # 打印结果
    print("\n" + "=" * 50)
    print("验证结果汇总")
    print("=" * 50)
    for r in results:
        icon = "[OK]" if r.passed else "[X]"
        print(f"{icon} {r.name}")
        if not r.passed:
            print(f"    Error: {r.error}")
    print("=" * 50)

    passed = sum(1 for r in results if r.passed)
    print(f"通过率: {passed}/{len(results)}")

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-push", action="store_true", help="不发送飞书")
    parser.add_argument("--verify-only", action="store_true", help="只验证不重启 SDK")
    args = parser.parse_args()

    exit(main(verify_only=args.verify_only, no_push=args.no_push))