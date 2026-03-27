#!/usr/bin/env python3
"""
@description: 代码质量检查工具 - 独立运行的质量检查器
@dependencies: pathlib, json
@last_modified: 2026-03-16

用法:
    python scripts/hooks/quality_check.py --file <path>
    python scripts/hooks/quality_check.py --all
"""

import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict

# 导入共享的检查器
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from hooks.pre_tool_use import CodeChecker, MAX_FILE_LINES, MAX_FUNCTION_LINES, MAX_NESTING_DEPTH


def check_file(file_path: Path) -> Dict:
    """检查单个文件"""
    if not file_path.exists():
        return {"file": str(file_path), "error": "File not found"}

    content = file_path.read_text(encoding="utf-8")
    checker = CodeChecker(str(file_path), content)
    result = checker.check_all()

    return {
        "file": str(file_path.relative_to(PROJECT_ROOT)),
        "passed": result.passed,
        "violations": [
            {"type": v.type, "message": v.message, "line": v.line}
            for v in result.violations
        ],
        "warnings": [
            {"type": v.type, "message": v.message, "line": v.line}
            for v in result.warnings
        ]
    }


def check_all_python_files() -> List[Dict]:
    """检查所有 Python 文件"""
    results = []
    for py_file in PROJECT_ROOT.rglob("*.py"):
        # 排除虚拟环境
        if ".venv" in str(py_file) or "site-packages" in str(py_file):
            continue
        results.append(check_file(py_file))
    return results


def main():
    parser = argparse.ArgumentParser(description="代码质量检查工具")
    parser.add_argument("--file", help="检查指定文件")
    parser.add_argument("--all", action="store_true", help="检查所有 Python 文件")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    if args.file:
        result = check_file(Path(args.file))
        results = [result]
    elif args.all:
        results = check_all_python_files()
    else:
        parser.print_help()
        sys.exit(1)

    # 输出结果
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print("\n" + "="*60)
        print("代码质量检查报告")
        print("="*60)
        print(f"阈值: 文件≤{MAX_FILE_LINES}行, 函数≤{MAX_FUNCTION_LINES}行, 嵌套≤{MAX_NESTING_DEPTH}层")
        print("="*60)

        total_passed = 0
        total_failed = 0

        for r in results:
            if "error" in r:
                print(f"\n[ERROR] {r['file']}: {r['error']}")
                continue

            status = "PASS" if r["passed"] else "FAIL"
            if r["passed"]:
                total_passed += 1
                print(f"\n[{status}] {r['file']}")
            else:
                total_failed += 1
                print(f"\n[{status}] {r['file']}")
                for v in r["violations"]:
                    print(f"  BLOCKER: {v['type']} - {v['message']}")
                for w in r["warnings"]:
                    print(f"  WARNING: {w['type']} - {w['message']}")

        print("\n" + "="*60)
        print(f"总计: {total_passed} 通过, {total_failed} 失败")
        print("="*60)

    sys.exit(0 if all(r.get("passed", False) for r in results) else 1)


if __name__ == "__main__":
    main()