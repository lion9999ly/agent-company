"""
@description: 写入后Hook - 文件写入后自动质量检查和评审触发
@dependencies: sys, json, pathlib
@last_modified: 2026-03-17

触发条件: Write/Edit工具调用后
执行内容:
1. 检查是否为核心代码文件
2. 运行质量检查
3. 标记是否需要评审
4. 输出检查结果到stdout（Claude可见）

使用: python scripts/hooks/post_write_hook.py --file <path>
"""

import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

# 核心代码清单
CORE_FILES = [
    "src/schema/state.py",
    "src/graph/router.py",
    "src/graph/context_slicer.py",
    "src/config/agents.yaml",
    "src/config/model_registry.yaml",
    "src/security/instruction_guard.py",
    "src/security/kpi_trap_detector.py",
    "src/audit/behavior_logger.py",
    "scripts/doc_sync_validator.py",
    "src/tools/layered_memory.py",
    "src/tools/context_injector.py",
    "src/tools/session_manager.py",
]

# 需要评审的文件模式
REVIEW_PATTERNS = [
    "src/**/*.py",
    "scripts/**/*.py",
    ".ai-architecture/*.md",
]


def is_core_file(file_path: str) -> bool:
    """检查是否为核心文件"""
    path = Path(file_path)
    for core in CORE_FILES:
        if path.match(core):
            return True
    return False


def needs_review(file_path: str) -> bool:
    """检查是否需要评审"""
    path = Path(file_path)
    for pattern in REVIEW_PATTERNS:
        if path.match(pattern):
            return True
    return False


def run_quality_check(file_path: str) -> dict:
    """运行质量检查"""
    try:
        result = subprocess.run(
            ["python", "scripts/hooks/quality_check.py", "--file", file_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "errors": result.stderr
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def check_forbidden_patterns(file_path: str) -> list:
    """检查禁止的模式"""
    forbidden = []
    forbidden_patterns = [
        ("eval(", "禁止使用eval()"),
        ("exec(", "禁止使用exec()"),
        ("os.system(", "禁止使用os.system()"),
        ("subprocess.Popen(", "禁止使用subprocess.Popen()"),
        ("shell=True", "禁止使用shell=True"),
    ]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            for pattern, message in forbidden_patterns:
                if pattern in content:
                    forbidden.append(message)
    except Exception:
        pass

    return forbidden


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="File path to check")
    args = parser.parse_args()

    file_path = args.file
    result = {
        "timestamp": datetime.now().isoformat(),
        "file": file_path,
        "is_core": is_core_file(file_path),
        "needs_review": needs_review(file_path),
        "quality_check": None,
        "forbidden_patterns": [],
        "verdict": "OK"
    }

    # 检查禁止模式
    result["forbidden_patterns"] = check_forbidden_patterns(file_path)
    if result["forbidden_patterns"]:
        result["verdict"] = "BLOCK"
        print("[BLOCK] Forbidden patterns detected:")
        for p in result["forbidden_patterns"]:
            print(f"  - {p}")

    # 核心文件质量检查
    if result["is_core"]:
        print(f"[CORE FILE] {file_path}")
        result["quality_check"] = run_quality_check(file_path)
        if not result["quality_check"].get("success"):
            result["verdict"] = "WARN"
            print(f"[WARN] Quality check issues")

    # 标记需要评审
    if result["needs_review"]:
        print(f"[REVIEW REQUIRED] {file_path}")
        # 写入评审请求
        review_request = {
            "timestamp": result["timestamp"],
            "file": file_path,
            "reason": "core_file" if result["is_core"] else "pattern_match"
        }
        review_path = Path(".ai-state/review_request.json")
        review_path.parent.mkdir(parents=True, exist_ok=True)
        with open(review_path, 'w', encoding='utf-8') as f:
            json.dump(review_request, f, ensure_ascii=False, indent=2)

    # 输出结果
    print(f"[{result['verdict']}] Post-write check complete")

    # 保存日志
    log_path = Path(".ai-state/hooks/post_write_log.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")

    # 如果是BLOCK，返回非零退出码
    if result["verdict"] == "BLOCK":
        sys.exit(1)

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)