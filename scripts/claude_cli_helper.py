"""Claude CLI 调用助手 — Windows .cmd 兼容
@description: 正确调用 Claude CLI（.cmd 文件需要 shell=True）
@dependencies: shutil, subprocess
@last_modified: 2026-04-05
"""
import subprocess
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def call_claude_cli(prompt: str, timeout: int = 120, cwd: str = None) -> str:
    """调用 Claude CLI（Max 订阅额度）

    Args:
        prompt: 发送给 Claude 的提示
        timeout: 超时秒数
        cwd: 工作目录

    Returns:
        Claude 的响应文本，失败返回空字符串
    """
    claude_path = shutil.which("claude")
    if not claude_path:
        print("[Claude CLI] 未找到 claude 命令")
        return ""

    work_dir = cwd or str(PROJECT_ROOT)

    # Windows 上 .cmd 文件需要 shell=True
    # 同时处理 prompt 中的特殊字符（引号等）
    escaped_prompt = prompt.replace('"', "'").replace("\n", " ")

    cmd_str = f'"{claude_path}" -p "{escaped_prompt}" --output-format text'

    try:
        r = subprocess.run(
            cmd_str,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=work_dir
        )
        if r.returncode == 0:
            print(f"[Claude CLI] OK, {len(r.stdout)} chars")
            return r.stdout.strip()
        else:
            print(f"[Claude CLI] 返回码 {r.returncode}: {r.stderr[:200]}")
            return ""
    except subprocess.TimeoutExpired:
        print(f"[Claude CLI] 超时 ({timeout}s)")
        return ""
    except Exception as e:
        print(f"[Claude CLI] 错误: {e}")
        return ""


def is_claude_cli_available() -> bool:
    """检查 Claude CLI 是否可用"""
    return shutil.which("claude") is not None


if __name__ == "__main__":
    # 测试
    print("=== Claude CLI 可用性检查 ===")
    print(f"可用: {is_claude_cli_available()}")
    print(f"路径: {shutil.which('claude')}")

    if len(sys.argv) > 1:
        test_prompt = sys.argv[1]
        print(f"\n=== 测试调用 ===")
        result = call_claude_cli(test_prompt)
        print(f"响应: {result[:500] if result else '无响应'}")