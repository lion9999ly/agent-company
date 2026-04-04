"""自愈系统主编排器 — 测试 + 修复 + 通知
@description: 串联测试套件、自动修复和通知的完整闭环
@dependencies: test_suite, auto_fixer
@last_modified: 2026-04-04
"""
import json, time, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def run_self_heal_cycle(send_reply=None, reply_target=None):
    """运行一轮自愈循环: 测试 → 修复 → 验证 → 通知

    Args:
        send_reply: 飞书回复函数（可选）
        reply_target: 飞书回复目标（可选）

    Returns:
        自愈结果
    """
    print("\n" + "=" * 50)
    print(f"[SelfHeal] 开始自愈循环 {time.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    # Step 1: 运行测试
    from scripts.test_suite import run_all_tests
    results = run_all_tests()
    summary = results["summary"]

    print(f"\n[SelfHeal] 测试结果: {summary['passed']}/{summary['total']} 通过")

    if summary["failed"] == 0:
        msg = f"✅ 系统自检通过 ({summary['total']}/{summary['total']})"
        print(f"[SelfHeal] {msg}")
        if send_reply and reply_target:
            send_reply(reply_target, msg)
        return {"status": "healthy", "tests": summary}

    # Step 2: 自动修复
    print(f"\n[SelfHeal] {summary['failed']} 项失败，启动自动修复...")

    from scripts.auto_fixer import auto_fix_failures
    fix_result = auto_fix_failures(summary["failed_items"], max_rounds=3)

    # Step 3: 生成报告
    fixed_count = len(fix_result["fixed"])
    unfixed_count = len(fix_result["unfixed"])

    report_lines = [f"🔧 系统自愈报告 {time.strftime('%Y-%m-%d %H:%M')}\n"]
    report_lines.append(f"测试: {summary['total']} 项，通过 {summary['passed']}，失败 {summary['failed']}")

    if fixed_count > 0:
        report_lines.append(f"\n✅ 自动修复 {fixed_count} 项:")
        for f in fix_result["fixed"]:
            report_lines.append(f"  • {f['item']}（{f['rounds']} 轮修复）")

    if unfixed_count > 0:
        report_lines.append(f"\n⚠️ 无法自动修复 {unfixed_count} 项（已写入 bug_report.md）:")
        for u in fix_result["unfixed"]:
            report_lines.append(f"  • {u['name']}: {u.get('error', '')[:50]}")

    report = "\n".join(report_lines)
    print(f"\n{report}")

    # Step 4: 推送飞书通知
    if send_reply and reply_target:
        send_reply(reply_target, report)

    # Step 5: 保存报告到 system_log
    log_path = PROJECT_ROOT / ".ai-state" / "self_heal_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps({
            "timestamp": time.strftime('%Y-%m-%d %H:%M'),
            "tests_total": summary["total"],
            "tests_passed": summary["passed"],
            "auto_fixed": [f["item"] for f in fix_result["fixed"]],
            "unfixed": [u["name"] for u in fix_result["unfixed"]],
        }, ensure_ascii=False) + "\n")

    return {
        "status": "healed" if unfixed_count == 0 else "needs_human",
        "tests": summary,
        "fixed": fix_result["fixed"],
        "unfixed": fix_result["unfixed"],
    }


def run_quick_health_check() -> dict:
    """快速健康检查（只跑硬测试）"""
    from scripts.test_suite import run_hard_tests
    results = run_hard_tests()

    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")

    return {
        "passed": passed,
        "failed": failed,
        "total": len(results),
        "status": "healthy" if failed == 0 else "unhealthy",
    }


def get_last_heal_result() -> dict:
    """获取最近的自愈结果"""
    log_path = PROJECT_ROOT / ".ai-state" / "self_heal_log.jsonl"
    if not log_path.exists():
        return {}
    lines = log_path.read_text(encoding='utf-8').strip().split('\n')
    if lines:
        try:
            return json.loads(lines[-1])
        except json.JSONDecodeError:
            return {}
    return {}


if __name__ == "__main__":
    run_self_heal_cycle()