"""
@description: 从 GitHub Issue 读取 Claude Chat 指令并执行
@dependencies: requests, python-dotenv
@last_modified: 2026-04-07
"""
import os
import json
import requests
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

    读取后直接执行 Issue body 中的指令，像收到飞书消息一样处理。
    """
    import re

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

    # 关键：把 Issue body 当作飞书消息重新路由执行
    if body and body.strip():
        try:
            from scripts.feishu_handlers.text_router import route_text_message
            # 调用路由处理 Issue body
            route_text_message(
                body.strip(),
                reply_target,
                reply_type or "chat_id",
                open_id or "",
                chat_id or reply_target,
                send_reply
            )
            # 执行完后在 Issue 下评论
            reply_to_issue(result["number"], f"✅ 指令已执行\n\n**标题**: {result['title']}\n\n**执行时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            send_reply(reply_target, f"✅ Issue #{result['number']} 执行完成")
        except Exception as e:
            error_msg = f"❌ 执行失败: {str(e)[:200]}"
            send_reply(reply_target, error_msg)
            reply_to_issue(result["number"], f"❌ 执行失败\n\n```\n{str(e)[:500]}\n```")
    else:
        send_reply(reply_target, "⚠️ Issue 内容为空，无指令可执行")
        reply_to_issue(result["number"], "⚠️ Issue 内容为空")

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