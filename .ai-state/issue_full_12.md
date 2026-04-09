# Day 17 系统全量审计 - scripts/feishu_handlers/import_handlers.py

```python
"""
@description: 导入相关处理器 - 文档导入、URL 分享、长文章入库、GitHub 指令
@dependencies: doc_importer, knowledge_base, github_instruction_reader
@last_modified: 2026-04-08
"""
import re
import json
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 全局任务运行状态（防止并发）
_long_task_running = False


def try_handle(text_stripped: str, reply_target: str, reply_type: str,
               open_id: str, chat_id: str, send_reply: Callable) -> bool:
    """导入相关指令路由

    Returns:
        bool: 是否处理了该消息
    """
    # 导入文档
    if text_stripped in ("导入文档", "导入", "import"):
        _handle_import_docs(reply_target, send_reply)
        return True

    # 参考文件（多文件研究任务）
    if "参考文件：" in text_stripped or "reference file:" in text_stripped.lower():
        _handle_reference_files(text_stripped, reply_target, send_reply)
        return True

    # GitHub 指令读取
    if text_stripped in ("拉取指令", "读取指令", "fetch instruction"):
        from scripts.github_instruction_reader import handle_fetch_instruction
        handle_fetch_instruction(text_stripped, reply_target, send_reply, reply_type, open_id, chat_id)
        return True

    if text_stripped.startswith("执行 issue") or text_stripped.startswith("执行issue"):
        from scripts.github_instruction_reader import handle_fetch_instruction
        handle_fetch_instruction(text_stripped, reply_target, send_reply, reply_type, open_id, chat_id)
        return True

    # 关注主题
    if text_stripped.startswith("关注 ") or text_stripped.startswith("关注："):
        _handle_add_topic(text_stripped, reply_target, send_reply)
        return True

    return False


def handle_url_share(text: str, open_id: str, reply_target: str, reply_type: str, send_reply: Callable) -> bool:
    """处理 URL 分享"""
    if _has_shareable_url(text):
        _handle_share_url(text, open_id, reply_target, reply_type, send_reply)
        return True
    return False


def handle_article_import(text: str, open_id: str, reply_target: str, send_reply: Callable) -> bool:
    """处理长文章导入"""
    if _is_likely_article(text):
        _handle_article_import(text, open_id, reply_target, send_reply)
        return True
    return False


def _has_shareable_url(text: str) -> bool:
    """检查文本中是否包含可分享的 URL"""
    return bool(re.search(r'https?://[^\s]+', text))


def _is_likely_article(text: str) -> bool:
    """判断是否为应该导入知识库的长文章"""
    text_len = len(text.strip())

    command_prefixes = ["研究", "分析一下", "帮我", "请", "设计", "方案", "@dev"]
    has_command = any(text.strip().startswith(p) for p in command_prefixes)

    if text_len < 500 or has_command:
        return False

    if text_len > 800:
        return True

    return False


def _handle_import_docs(reply_target: str, send_reply: Callable):
    """处理导入文档"""
    send_reply(reply_target, "📂 正在扫描文档收件箱...")

    try:
        from scripts.doc_importer import scan_and_import
        report = scan_and_import(progress_callback=lambda msg: send_reply(reply_target, msg))
        if report:
            send_reply(reply_target, report)
        else:
            send_reply(reply_target, "[Info] 收件箱为空，无文件需要处理。\n请把文件放入 .ai-state/inbox/ 目录")
    except Exception as e:
        from scripts.feishu_handlers.chat_helpers import _safe_reply_error
        _safe_reply_error(send_reply, reply_target, "导入文档", e)


def _handle_share_url(text: str, open_id: str, reply_target: str, reply_type: str, send_reply: Callable):
    """处理 URL 分享"""
    try:
        from scripts.feishu_sdk_client import handle_share_content
        handle_share_content(open_id, text=text, reply_target=reply_target, reply_type=reply_type)
    except:
        send_reply(reply_target, "🔗 检测到链接，但分享处理功能暂未导入。")


def _handle_article_import(text: str, open_id: str, reply_target: str, send_reply: Callable):
    """处理长文章导入"""
    send_reply(reply_target, f"📄 检测到长文（{len(text)}字），正在导入知识库...")

    try:
        from src.tools.knowledge_base import add_knowledge
        from src.utils.model_gateway import get_model_gateway

        gateway = get_model_gateway()
        summary_result = gateway.call_azure_openai(
            "cpo",
            f"请为以下文章生成标题和摘要（JSON格式）：\n{text[:3000]}\n\n输出: {{\"title\": \"标题\", \"summary\": \"200字摘要\"}}",
            "只输出 JSON。",
            "article_summary"
        )

        if summary_result.get("success"):
            resp = summary_result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            data = json.loads(resp)
            title = data.get("title", "用户分享文章")
            summary = data.get("summary", text[:500])
        else:
            title = "用户分享文章"
            summary = text[:500]

        add_knowledge(
            title=title,
            domain="lessons",
            content=summary,
            tags=["user_share", "article"],
            source="user_share:text",
            confidence="medium"
        )

        send_reply(reply_target, f"✅ 文章已入库：{title}")
    except Exception as e:
        from scripts.feishu_handlers.chat_helpers import _safe_reply_error
        _safe_reply_error(send_reply, reply_target, "导入文档", e)


def _handle_reference_files(text: str, reply_target: str, send_reply: Callable):
    """处理参考文件（多文件研究任务）

    支持格式：
    - 单行：参考文件：docs/tasks/xxx.md
    - 多行：参考文件：\n  A. docs/tasks/xxx.md\n  B. docs/specs/yyy.md
    """
    # 提取所有 .md 文件路径
    matches = re.findall(r'[\w./\\-]+\.md', text)
    if not matches:
        send_reply(reply_target, "格式错误。正确格式：参考文件：docs/tasks/xxx.md")
        return

    # 区分参考文件(docs/tasks/)和约束文件(docs/specs/)
    task_files = []
    constraint_files = []
    for raw_path in matches:
        if not raw_path.startswith('/') and not raw_path.startswith('D:'):
            full_path = str(PROJECT_ROOT / raw_path)
        else:
            full_path = raw_path

        if Path(full_path).exists():
            if 'docs/tasks/' in raw_path or 'docs\\tasks' in raw_path:
                task_files.append((raw_path, full_path))
            elif 'docs/specs/' in raw_path or 'docs\\specs' in raw_path:
                constraint_files.append((raw_path, full_path))
            else:
                task_files.append((raw_path, full_path))
        else:
            send_reply(reply_target, f"[Research] 文件不存在: {raw_path}")

    if not task_files:
        if constraint_files:
            send_reply(reply_target, "[Research] 仅收到约束文件，缺少研究任务文件(docs/tasks/)")
        return

    # 后台执行多文件研究
    def _run_multi_files():
        global _long_task_running
        _long_task_running = True
        try:
            from scripts.tonight_deep_research import run_research_from_file

            # 读取约束文件内容作为上下文注入
            constraint_context = ""
            for raw_path, full_path in constraint_files:
                constraint_context += f"\n\n---\n## 约束文件: {raw_path}\n\n"
                constraint_context += Path(full_path).read_text(encoding='utf-8')

            # 每个参考文件独立执行
            for idx, (raw_path, full_path) in enumerate(task_files, 1):
                send_reply(reply_target, f"🔍 [{idx}/{len(task_files)}] 开始研究: {Path(full_path).name}")
                report_path = run_research_from_file(
                    full_path,
                    progress_callback=lambda msg: send_reply(reply_target, msg),
                    constraint_context=constraint_context if constraint_context else None
                )
                if report_path:
                    send_reply(reply_target, f"✅ [{idx}/{len(task_files)}] 完成: {Path(full_path).name}\n报告: {report_path}")
                else:
                    send_reply(reply_target, f"[Research] {Path(full_path).name} 未解析到有效任务")
                time.sleep(2)
        except Exception as e:
            from scripts.feishu_handlers.chat_helpers import _safe_reply_error
            _safe_reply_error(send_reply, reply_target, "Research任务", e)
        finally:
            _long_task_running = False

    threading.Thread(target=_run_multi_files, daemon=True).start()
    msg = f"[Research] 启动 {len(task_files)} 个研究任务"
    if constraint_files:
        msg += f"，附带 {len(constraint_files)} 个约束文件"
    send_reply(reply_target, msg)


def _handle_add_topic(text: str, reply_target: str, send_reply: Callable):
    """添加关注主题"""
    topic_text = text.replace("关注 ", "").replace("关注：", "").strip()
    if not topic_text:
        send_reply(reply_target, "请输入关注的主题，如：关注 骑行头盔 AR导航")
        return

    topics_path = PROJECT_ROOT / ".ai-state" / "knowledge" / "learning_topics.json"
    if topics_path.exists():
        data = json.loads(topics_path.read_text(encoding="utf-8"))
    else:
        data = {"version": "1.0", "topics": []}

    data["topics"].append({"query": topic_text, "domain": "lessons", "tags": ["用户关注"]})
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d")
    topics_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    send_reply(reply_target, f"✅ 已添加学习关注：{topic_text}\n下次学习时会搜索此主题")
```
