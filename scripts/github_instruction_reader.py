"""
@description: 从 GitHub Issue 读取 Claude Chat 指令并执行
@dependencies: requests, python-dotenv, subprocess
@last_modified: 2026-04-07

Issue body 接入 CC agent 模式：
- 优先：调用 claude CLI（有完整文件系统访问能力）
- 备选：调用最强模型 gpt_5_4（注入项目上下文）
"""
import os
import json
import requests
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

# 加载 .env
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# GitHub 配置（复用已有的 push token）
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO = "lion9999ly/agent-company"
API_BASE = f"https://api.github.com/repos/{REPO}"
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "agent-company-cc"
}

# 指令标签（可选，如果没有就读取所有 open issue）
INSTRUCTION_LABEL = "cc-instruction"


def fetch_latest_instruction(issue_number: int = None) -> dict:
    """
    读取最新的指令 Issue.

    Args:
        issue_number: 指定 Issue 编号。None 则读取最新的 open issue。

    Returns:
        {"success": True, "number": 2, "title": "...", "body": "...", "url": "..."}
        或
        {"success": False, "error": "..."}
    """
    try:
        if issue_number:
            url = f"{API_BASE}/issues/{issue_number}"
            resp = requests.get(url, headers=HEADERS, timeout=15)
        else:
            # 读取最新的 open issue（按创建时间倒序）
            url = f"{API_BASE}/issues"
            params = {"state": "open", "sort": "created", "direction": "desc", "per_page": 1}
            resp = requests.get(url, headers=HEADERS, params=params, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            # 列表接口返回数组，单 issue 接口返回对象
            issue = data[0] if isinstance(data, list) else data
            if isinstance(data, list) and len(data) == 0:
                return {"success": False, "error": "没有 open 的 Issue"}

            return {
                "success": True,
                "number": issue["number"],
                "title": issue["title"],
                "body": issue.get("body", ""),
                "url": issue["html_url"],
                "created_at": issue["created_at"]
            }
        else:
            return {"success": False, "error": f"GitHub API {resp.status_code}: {resp.text[:200]}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


def reply_to_issue(issue_number: int, comment: str) -> bool:
    """在 Issue 下评论执行结果"""
    try:
        url = f"{API_BASE}/issues/{issue_number}/comments"
        resp = requests.post(url, headers=HEADERS, json={"body": comment}, timeout=15)
        return resp.status_code == 201
    except:
        return False


def close_issue(issue_number: int) -> bool:
    """关闭已完成的 Issue"""
    try:
        url = f"{API_BASE}/issues/{issue_number}"
        resp = requests.patch(url, headers=HEADERS, json={"state": "closed"}, timeout=15)
        return resp.status_code == 200
    except:
        return False


def save_instruction_locally(issue_data: dict) -> str:
    """
    将 Issue 内容保存到本地，供 CC 读取执行。

    保存到 .ai-state/claude_chat_instructions/issue_{number}.md
    """
    instructions_dir = PROJECT_ROOT / ".ai-state" / "claude_chat_instructions"
    instructions_dir.mkdir(parents=True, exist_ok=True)

    filename = f"issue_{issue_data['number']}.md"
    filepath = instructions_dir / filename

    content = f"""# {issue_data['title']}
> Issue #{issue_data['number']} | {issue_data['created_at']}
> {issue_data['url']}

{issue_data['body']}
"""
    filepath.write_text(content, encoding="utf-8")

    # 同时写一个 latest.md 软链/副本
    latest_path = instructions_dir / "latest.md"
    latest_path.write_text(content, encoding="utf-8")

    return str(filepath)


# === 飞书指令入口 ===
def handle_fetch_instruction(text: str, reply_target: str, send_reply,
                              reply_type: str = None, open_id: str = None, chat_id: str = None):
    """
    处理飞书指令：
    - "拉取指令" → 读取最新 open issue
    - "执行 issue#2" 或 "执行 issue 2" → 读取指定 issue

    Issue body 接入 CC agent 模式（有完整文件系统访问能力）
    """
    import re
    import shutil

    # 解析 issue 编号
    issue_number = None
    match = re.search(r'issue\s*#?\s*(\d+)', text, re.IGNORECASE)
    if match:
        issue_number = int(match.group(1))

    send_reply(reply_target, f"📥 正在从 GitHub 读取指令{'（Issue #' + str(issue_number) + '）' if issue_number else '（最新）'}...")

    result = fetch_latest_instruction(issue_number)

    if not result["success"]:
        send_reply(reply_target, f"❌ 读取失败：{result['error']}")
        return None

    # 保存到本地
    local_path = save_instruction_locally(result)

    # 飞书展示指令摘要
    body = result["body"]
    body_preview = body[:200]
    if len(body) > 200:
        body_preview += "..."

    send_reply(reply_target, f"""📋 开始执行 Issue #{result['number']}
标题：{result['title']}
内容：{body_preview}
---""")

    if not body or not body.strip():
        send_reply(reply_target, "⚠️ Issue 内容为空，无指令可执行")
        reply_to_issue(result["number"], "⚠️ Issue 内容为空")
        return result

    # === 方案1：调用 CC agent 模式（优先）===
    # Windows 上需要找到 .cmd 文件
    import platform
    is_windows = platform.system() == "Windows"

    claude_path = shutil.which("claude")
    if is_windows and not claude_path:
        # 尝试 .cmd 扩展名
        claude_path = shutil.which("claude.cmd")

    if claude_path:
        try:
            send_reply(reply_target, "🤖 CC Agent 模式启动...")

            # Windows 上 .cmd 文件需要通过 shell 执行
            if is_windows:
                # 使用 stdin 传递 prompt，避免命令行特殊字符问题
                cmd_str = f'"{claude_path}"'
                process = subprocess.Popen(
                    cmd_str,
                    cwd=str(PROJECT_ROOT),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    shell=True
                )
                # 通过 stdin 发送指令
                stdout, stderr = process.communicate(input=body.strip(), timeout=300)
            else:
                process = subprocess.Popen(
                    [claude_path],
                    cwd=str(PROJECT_ROOT),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace"
                )
                stdout, stderr = process.communicate(input=body.strip(), timeout=300)

            # 发送结果到飞书（截取前 3000 字）
            if stdout:
                output = stdout.strip()
                if len(output) > 3000:
                    output = output[:3000] + "\n... (已截断)"
                send_reply(reply_target, f"📤 执行结果：\n{output}")
            else:
                send_reply(reply_target, f"⚠️ 无输出")

            if stderr:
                send_reply(reply_target, f"⚠️ 错误信息：{stderr[:500]}")

            # 在 Issue 下评论
            comment = f"✅ 指令已执行（CC Agent 模式）\n\n**执行时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n**结果摘要**:\n```\n{(stdout or '无输出')[:500]}\n```"
            reply_to_issue(result["number"], comment)
            send_reply(reply_target, f"✅ Issue #{result['number']} 执行完成")

            return result

        except subprocess.TimeoutExpired:
            process.kill()
            send_reply(reply_target, "⏱️ 执行超时（5分钟），已终止")
            reply_to_issue(result["number"], "⏱️ 执行超时")
            return result
        except Exception as e:
            send_reply(reply_target, f"⚠️ CC Agent 调用失败: {str(e)[:100]}，尝试备选方案...")

    # === 方案2：备选 - 调用最强模型 ===
    try:
        send_reply(reply_target, "🤖 备选方案：调用 GPT-5.4 执行...")

        from scripts.litellm_gateway import get_model_gateway
        gw = get_model_gateway()

        system_prompt = f"""你是一个有完整文件系统访问能力的 AI 助手。
项目根目录: {PROJECT_ROOT}

你有权限：
- 读取任何文件
- 修改代码文件
- 执行 bash 命令（通过输出命令让调用方执行）

请直接执行用户请求的任务。如果需要修改文件，直接输出修改后的完整内容。"""

        model_result = gw.call(
            model_name="gpt_5_4",
            prompt=body.strip(),
            system_prompt=system_prompt,
            task_type="agent"
        )

        if model_result.get("success"):
            response = model_result.get("response", "")
            if len(response) > 3000:
                response = response[:3000] + "\n... (已截断)"
            send_reply(reply_target, f"📤 执行结果：\n{response}")
            reply_to_issue(result["number"], f"✅ 指令已执行（GPT-5.4 模式）\n\n```\n{response[:500]}\n```")
            send_reply(reply_target, f"✅ Issue #{result['number']} 执行完成")
        else:
            error = model_result.get("error", "未知错误")
            send_reply(reply_target, f"❌ 模型调用失败: {error}")
            reply_to_issue(result["number"], f"❌ 执行失败\n\n{error}")

    except Exception as e:
        send_reply(reply_target, f"❌ 执行失败: {str(e)[:200]}")
        reply_to_issue(result["number"], f"❌ 执行失败\n\n```\n{str(e)[:500]}\n```")

    return result


# === 测试 ===
if __name__ == "__main__":
    # 快速验证 API 连通性
    print("Testing GitHub Issue API...")
    print(f"GITHUB_TOKEN: {'SET' if GITHUB_TOKEN else 'NOT SET'}")

    # 测试读取
    result = fetch_latest_instruction(2)
    if result["success"]:
        print(f"[OK] Issue #{result['number']}: {result['title']}")
        print(f"   Body: {result['body'][:100]}")
    else:
        print(f"[FAIL] {result['error']}")

    # 如果 token 可用，测试评论
    if GITHUB_TOKEN and result.get("success"):
        # 注意：这会真的在 Issue 下评论，测试时谨慎
        # success = reply_to_issue(result["number"], "[CC Test] GitHub Issue channel verified")
        # print(f"Comment: {'OK' if success else 'FAIL'}")
        pass