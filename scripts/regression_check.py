"""
@description: 回归验证脚本 - 读取 capability_registry.json，逐条验证功能完整性
@dependencies: json, importlib, sys
@last_modified: 2026-04-06

用法：
  python scripts/regression_check.py          # 全量检查
  python scripts/regression_check.py --quick   # 快速检查（只验证文件和函数存在性）
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_registry():
    """加载能力注册表"""
    reg_path = PROJECT_ROOT / ".ai-state" / "capability_registry.json"
    if not reg_path.exists():
        print(f"❌ 注册表不存在: {reg_path}")
        return None
    return json.loads(reg_path.read_text(encoding="utf-8"))


def check_feishu_commands(registry):
    """检查每个飞书指令的 handler 是否存在且可调用"""
    results = []
    router_file = PROJECT_ROOT / "scripts/feishu_handlers/text_router.py"
    router_content = router_file.read_text(encoding="utf-8") if router_file.exists() else ""

    for cmd_name, cmd_info in registry.get("feishu_commands", {}).items():
        handler_file = PROJECT_ROOT / cmd_info["handler_file"]
        status = "✅"
        issues = []

        # 检查 handler 文件存在
        if not handler_file.exists():
            status = "❌"
            issues.append(f"文件不存在: {cmd_info['handler_file']}")
        else:
            # 检查 handler 文件中包含 handler 函数
            content = handler_file.read_text(encoding="utf-8")
            func_name = cmd_info["handler_function"].split(".")[-1]
            if func_name not in content:
                # 对于模块导入的函数，检查是否在路由文件中
                if func_name not in router_content:
                    status = "❌"
                    issues.append(f"函数 {func_name} 未找到")

            # 检查 match_patterns 在路由文件中有对应匹配
            for pattern in cmd_info["match_patterns"]:
                if pattern not in router_content and pattern not in content:
                    status = "⚠️"
                    issues.append(f"路由模式 '{pattern}' 未找到")

        # 检查依赖文件
        for dep in cmd_info.get("depends_on", []):
            if dep and not (PROJECT_ROOT / dep).exists():
                status = "❌"
                issues.append(f"依赖文件不存在: {dep}")

        results.append((cmd_name, status, issues))
    return results


def check_internal_functions(registry):
    """检查内部功能的入口点和调用点"""
    results = []

    for func_name, func_info in registry.get("internal_functions", {}).items():
        status = "✅"
        issues = []

        # 检查入口点文件
        loc = PROJECT_ROOT / func_info["location"]
        if not loc.exists():
            status = "❌"
            issues.append(f"入口文件不存在: {func_info['location']}")
        else:
            content = loc.read_text(encoding="utf-8")
            if func_info["entry_point"] not in content:
                status = "❌"
                issues.append(f"入口函数 {func_info['entry_point']} 未找到")

        # 检查调用点
        for caller in func_info.get("callers", []):
            caller_path = PROJECT_ROOT / caller
            if not caller_path.exists():
                status = "⚠️"
                issues.append(f"调用方文件不存在: {caller}")
            else:
                caller_content = caller_path.read_text(encoding="utf-8")
                if func_info["entry_point"] not in caller_content:
                    status = "❌"
                    issues.append(f"调用方 {caller} 中未调用 {func_info['entry_point']}")

        results.append((func_name, status, issues))
    return results


def check_scheduled_tasks(registry):
    """检查定时任务"""
    results = []

    for task_name, task_info in registry.get("scheduled_tasks", {}).items():
        status = "✅"
        issues = []

        # 检查任务所在文件
        loc = PROJECT_ROOT / task_info["location"]
        if not loc.exists():
            status = "❌"
            issues.append(f"任务文件不存在: {task_info['location']}")
        else:
            content = loc.read_text(encoding="utf-8")
            if task_info["handler"] not in content:
                status = "❌"
                issues.append(f"任务处理器 {task_info['handler']} 未找到")

        # 检查依赖
        for dep in task_info.get("depends_on", []):
            if dep and not (PROJECT_ROOT / dep).exists():
                status = "⚠️"
                issues.append(f"依赖文件不存在: {dep}")

        results.append((task_name, status, issues))
    return results


def main():
    """主入口"""
    # 修复 Windows 控制台编码问题
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    registry = load_registry()
    if not registry:
        return 1

    print("=" * 60)
    print("功能回归验证报告")
    print(f"注册表版本: {registry.get('version', 'unknown')}")
    print("=" * 60)

    fail_count = 0

    # 飞书指令
    print("\n--- 飞书指令 ---")
    cmd_results = check_feishu_commands(registry)
    for name, status, issues in cmd_results:
        print(f"  {status} {name}")
        for issue in issues:
            print(f"      → {issue}")
            if status == "❌":
                fail_count += 1

    # 内部功能
    print("\n--- 内部功能 ---")
    func_results = check_internal_functions(registry)
    for name, status, issues in func_results:
        print(f"  {status} {name}")
        for issue in issues:
            print(f"      → {issue}")
            if status == "❌":
                fail_count += 1

    # 定时任务
    print("\n--- 定时任务 ---")
    task_results = check_scheduled_tasks(registry)
    for name, status, issues in task_results:
        print(f"  {status} {name}")
        for issue in issues:
            print(f"      → {issue}")
            if status == "❌":
                fail_count += 1

    # 废弃功能
    print("\n--- 废弃功能 ---")
    for name, info in registry.get("deprecated", {}).items():
        print(f"  ⊘ {name} — {info.get('reason', 'unknown')}")

    print("\n" + "=" * 60)
    if fail_count == 0:
        print("✅ 全部通过")
    else:
        print(f"❌ {fail_count} 个功能缺失，需要修复")
    print("=" * 60)

    return fail_count


if __name__ == "__main__":
    sys.exit(main())