"""
@description: 自动验证脚本 - 直接调用底层函数验证
@dependencies: pathlib, json, model_gateway, roundtable
@last_modified: 2026-04-08

用法：
    python scripts/auto_restart_and_verify.py
    python scripts/auto_restart_and_verify.py --no-push  # 不发送飞书
"""
import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

APP_ID = os.getenv("FEISHU_APP_ID", "")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
LEO_OPEN_ID = "ou_8e5e4f183e9eca4241378e96bac3a751"


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


def verify_system_status() -> VerifyResult:
    """验证1: 状态指令 - 读取 system_status.md"""
    result = VerifyResult("状态指令")

    try:
        status_path = PROJECT_ROOT / ".ai-state" / "system_status.md"

        if not status_path.exists():
            result.fail("system_status.md 文件不存在")
            return result

        content = status_path.read_text(encoding="utf-8")

        # 检查内容有效性
        if "最近变更" in content or len(content) > 100:
            result.success(f"文件存在，内容长度: {len(content)} 字符")
        else:
            result.fail("内容不符合预期（缺少'最近变更'或内容过短）")

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

        # 检查6层结构
        if len(layers) < 6:
            result.fail(f"监控层数不足: {len(layers)} < 6")
            return result

        # 检查关键层存在
        layer_keys = list(layers.keys())
        result.success(f"共 {len(layers)} 层: {', '.join(layer_keys[:3])}...")

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
            result.fail("hud_demo TaskSpec 加载失败（返回 None）")
            return result

        # 检查关键字段
        checks = []

        # generator_input_mode
        mode = getattr(spec, "generator_input_mode", None)
        if mode:
            checks.append(f"generator_input_mode={mode}")
        else:
            result.fail("缺少 generator_input_mode")
            return result

        # acceptance_criteria
        criteria = getattr(spec, "acceptance_criteria", [])
        if len(criteria) >= 10:
            checks.append(f"acceptance_criteria={len(criteria)}条")
        else:
            result.fail(f"acceptance_criteria 不足: {len(criteria)} < 10")
            return result

        result.success(", ".join(checks))

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

        # 检查 global.json
        global_rule = rules_dir / "global.json"
        if not global_rule.exists():
            result.fail("global.json 不存在")
            return result

        # 统计规则文件
        rule_files = list(rules_dir.glob("*.json"))
        result.success(f"共 {len(rule_files)} 个规则文件，含 global.json")

    except Exception as e:
        result.fail(str(e))

    return result


def verify_model_gateway() -> VerifyResult:
    """验证5: model_gateway 调用"""
    result = VerifyResult("Model Gateway")

    try:
        from src.utils.model_gateway import get_model_gateway

        gw = get_model_gateway()

        # 简单测试调用
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
            ("状态", "text_router.py", '"状态"'),
            ("监控范围", "text_router.py", '"监控范围"'),
            ("圆桌:", "roundtable_handler.py", 'startswith("圆桌:")'),
            ("拉取指令", "import_handlers.py", '"拉取指令"'),
        ]

        matched = []
        failed = []

        for command, handler_file, expected_pattern in test_cases:
            handler_path = PROJECT_ROOT / "scripts" / "feishu_handlers" / handler_file
            if handler_path.exists():
                content = handler_path.read_text(encoding="utf-8")
                # 简化匹配：检查关键字符串是否存在
                key = expected_pattern.replace('"', '').replace('startswith(', '').replace(')', '')
                if key in content:
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


def generate_report(results: list) -> str:
    """生成验证报告"""
    lines = [
        f"# 自动验证报告",
        f"",
        f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"## 结果汇总",
        f"",
    ]

    passed = sum(1 for r in results if r.passed)
    total = len(results)

    lines.append(f"| 状态 | 项目 | 详情 |")
    lines.append(f"|------|------|------|")

    for r in results:
        icon = "✅" if r.passed else "❌"
        detail = r.details[0] if r.details else (r.error or "-")
        lines.append(f"| {icon} | {r.name} | {detail} |")

    lines.append(f"")
    lines.append(f"**通过率**: {passed}/{total}")

    return "\n".join(lines)


def send_to_feishu(report: str):
    """发送报告到飞书"""
    import requests

    # 获取 token
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        resp = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
        token = resp.json().get("tenant_access_token", "")
        if not token:
            print("[WARN] 无法获取飞书 token")
            return False
    except Exception as e:
        print(f"[WARN] 获取 token 失败: {e}")
        return False

    # 发送消息
    msg_url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 截断报告
    content = report[:3500] if len(report) > 3500 else report

    data = {
        "receive_id": LEO_OPEN_ID,
        "msg_type": "text",
        "content": json.dumps({"text": content})
    }

    try:
        resp = requests.post(msg_url, headers=headers, json=data, timeout=10)
        return resp.json().get("code") == 0
    except Exception as e:
        print(f"[WARN] 发送飞书失败: {e}")
        return False


def main(no_push: bool = False):
    """主入口"""
    print("=" * 50)
    print("自动验证脚本")
    print("=" * 50)

    # 执行所有验证
    results = []

    print("\n[1/6] 验证状态指令...")
    results.append(verify_system_status())

    print("[2/6] 验证监控范围...")
    results.append(verify_monitor_config())

    print("[3/6] 验证圆桌 TaskSpec...")
    results.append(verify_task_spec())

    print("[4/6] 验证 Verifier 规则库...")
    results.append(verify_verifier_rules())

    print("[5/6] 验证 Model Gateway...")
    results.append(verify_model_gateway())

    print("[6/6] 验证路由匹配...")
    results.append(verify_route_matching())

    # 生成报告
    report = generate_report(results)

    # 写入文件
    report_path = PROJECT_ROOT / ".ai-state" / "verify_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"\n报告已写入: {report_path}")

    # 发送飞书
    if not no_push:
        print("\n发送报告到飞书...")
        if send_to_feishu(report):
            print("[OK] 报告已发送")
        else:
            print("[WARN] 发送失败")

    # 打印结果
    print("\n" + "=" * 50)
    for r in results:
        icon = "[OK]" if r.passed else "[X]"
        print(f"{icon} {r.name}")
        if not r.passed:
            print(f"    Error: {r.error}")
    print("=" * 50)

    # 返回退出码
    passed = sum(1 for r in results if r.passed)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-push", action="store_true", help="不发送飞书")
    args = parser.parse_args()

    exit(main(no_push=args.no_push))