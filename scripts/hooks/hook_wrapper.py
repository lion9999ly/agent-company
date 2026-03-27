"""
@description: Hook Wrapper - 解析stdin并调用实际hook脚本
@dependencies: sys, json
@last_modified: 2026-03-17

用于Claude Code Hook系统，接收JSON stdin，提取参数，调用实际hook
"""

import sys
import json
import subprocess
from pathlib import Path


def main():
    # 读取stdin JSON
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("[HOOK WRAPPER] Invalid JSON input")
        sys.exit(0)  # 不阻断，静默失败

    # 提取文件路径
    file_path = (
        data.get("tool_response", {}).get("filePath") or
        data.get("tool_input", {}).get("file_path", "")
    )

    if not file_path:
        print("[HOOK WRAPPER] No file path found in input")
        sys.exit(0)

    # 调用实际的post_write_hook
    script_dir = Path(__file__).parent
    hook_script = script_dir / "post_write_hook.py"

    try:
        result = subprocess.run(
            ["python", str(hook_script), "--file", file_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        # 输出hook结果
        if result.stdout:
            print(result.stdout)
        if result.returncode != 0:
            print(f"[HOOK WRAPPER] Hook exited with code {result.returncode}")
            sys.exit(result.returncode)
    except subprocess.TimeoutExpired:
        print("[HOOK WRAPPER] Hook timeout")
    except Exception as e:
        print(f"[HOOK WRAPPER] Error: {e}")


if __name__ == "__main__":
    main()