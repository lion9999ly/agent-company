"""
@description: 文本消息路由 - 精确指令 → 快速通道 → 意图识别 → R&D → 智能对话
@refactored_from: feishu_sdk_client.py
@last_modified: 2026-03-28
"""
import re
import json
import threading
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def route_text_message(text: str, reply_target: str, reply_type: str, open_id: str, chat_id: str,
                       send_reply, session_id: str = None, mem=None):
    """
    文本消息路由主入口。

    路由优先级（从高到低）：
    1. 精确指令（评价/设置目标/进化记录/审批等）
    2. 结构化文档快速通道（PRD/清单/表格）
    3. URL 分享处理
    4. 长文章导入知识库
    5. 研发任务（LangGraph 多 Agent）
    6. 意图识别 → 智能路由
    7. 兜底：智能对话（GPT 直连 + 知识库上下文）
    """
    from scripts.feishu_handlers.chat_helpers import log
    from scripts.feishu_handlers.commands import handle_command
    from scripts.feishu_handlers.rd_task import is_rd_task, run_rd_task_background, is_rd_task_running

    text_stripped = text.strip()
    text_upper = text_stripped.upper()

    log(f"text 路由, 长度={len(text)}")

    # === 1. 精确指令 ===
    if handle_command(text_stripped, reply_target, reply_type, open_id, chat_id, send_reply):
        return

    # === 2. 帮助 ===
    if text_stripped in ("帮助", "help", "?", "？", "能力", "你能做什么"):
        try:
            from src.utils.capability_registry import get_capabilities_summary
            send_reply(reply_target, get_capabilities_summary())
        except:
            send_reply(reply_target, "我是智能骑行头盔研发助手，可以帮你做竞品分析、技术方案、市场策略等。")
        return

    # === 3. 学习相关指令 ===
    if text_stripped in ("学习", "每日学习", "daily learning"):
        _handle_daily_learning(reply_target, send_reply)
        return

    if text_stripped in ("重置学习", "reset learning", "重学"):
        _handle_reset_learning(reply_target, send_reply)
        return

    if text_stripped in ("深度学习", "夜间学习", "night learning"):
        _handle_night_learning(reply_target, send_reply)
        return

    if text_stripped in ("对齐", "对齐报告", "alignment"):
        _handle_alignment(reply_target, send_reply)
        return

    # === 4. 关注主题 ===
    if text_stripped.startswith("关注 ") or text_stripped.startswith("关注："):
        _handle_add_topic(text_stripped, reply_target, send_reply)
        return

    # === 5. 导入文档 ===
    if text_stripped in ("导入文档", "导入", "import"):
        _handle_import_docs(reply_target, send_reply)
        return

    # === 6. 结构化文档快速通道 ===
    try:
        from scripts.feishu_handlers.structured_doc import try_structured_doc_fast_track
        if try_structured_doc_fast_track(text_stripped, reply_target, reply_type, open_id, chat_id, send_reply):
            return
    except ImportError:
        pass

    # === 7. 研发任务 ===
    if is_rd_task(text_stripped):
        if is_rd_task_running():
            send_reply(reply_target, "⏳ 上一个研发任务还在执行中，请稍后再试")
        else:
            send_reply(reply_target, "🚀 检测到研发任务，启动多Agent工作流...")
            threading.Thread(
                target=run_rd_task_background,
                args=(text_stripped, reply_target, reply_type, open_id, chat_id, send_reply),
                daemon=True
            ).start()
        return

    # === 8. URL 分享处理 ===
    if _has_shareable_url(text_stripped):
        _handle_share_url(text_stripped, open_id, reply_target, reply_type, send_reply)
        return

    # === 9. 长文章导入 ===
    if _is_likely_article(text_stripped):
        _handle_article_import(text_stripped, open_id, reply_target, send_reply)
        return

    # === 10. 兜底：智能对话 ===
    _smart_route_and_reply(text_stripped, open_id, chat_id, reply_target, reply_type, send_reply, session_id, mem)


def _has_shareable_url(text: str) -> bool:
    """检查文本中是否包含可分享的 URL"""
    url_patterns = [
        r'https?://[^\s]+',
    ]
    return bool(re.search('|'.join(url_patterns), text))


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


def _handle_daily_learning(reply_target: str, send_reply):
    """处理每日学习指令"""
    topics_path = PROJECT_ROOT / ".ai-state" / "knowledge" / "learning_topics.json"
    topic_count = 10
    if topics_path.exists():
        try:
            data = json.loads(topics_path.read_text(encoding="utf-8"))
            topic_count = len(data.get("topics", []))
        except:
            pass

    send_reply(reply_target, f"📚 正在执行每日学习（{topic_count}个主题，预计3-5分钟）...")

    def _run():
        try:
            from scripts.daily_learning import run_daily_learning
            report = run_daily_learning(progress_callback=lambda msg: send_reply(reply_target, msg))
            send_reply(reply_target, report)
        except Exception as e:
            send_reply(reply_target, f"学习执行失败: {e}")

    threading.Thread(target=_run, daemon=True).start()


def _handle_reset_learning(reply_target: str, send_reply):
    """重置学习覆盖记录"""
    try:
        covered_file = PROJECT_ROOT / ".ai-state" / "covered_topics.json"
        if covered_file.exists():
            covered_file.unlink()
        send_reply(reply_target, "✅ 已重置学习覆盖记录，下次学习将重新搜索所有固定主题")
    except Exception as e:
        send_reply(reply_target, f"重置失败: {e}")


def _handle_night_learning(reply_target: str, send_reply):
    """处理夜间深度学习"""
    send_reply(reply_target, "[NightLearn] 启动深度学习（三阶段：深化+拓展+跨界）...")

    def _run():
        try:
            from scripts.daily_learning import run_night_deep_learning
            report = run_night_deep_learning(progress_callback=lambda msg: send_reply(reply_target, msg))
            send_reply(reply_target, report)
        except Exception as e:
            send_reply(reply_target, f"夜间学习执行失败: {e}")

    threading.Thread(target=_run, daemon=True).start()


def _handle_alignment(reply_target: str, send_reply):
    """处理对齐报告"""
    send_reply(reply_target, "📊 正在生成对齐报告...")

    def _run():
        try:
            from scripts.daily_learning import generate_alignment_report
            report = generate_alignment_report()
            send_reply(reply_target, report)
        except Exception as e:
            send_reply(reply_target, f"对齐报告生成失败: {e}")

    threading.Thread(target=_run, daemon=True).start()


def _handle_add_topic(text: str, reply_target: str, send_reply):
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


def _handle_import_docs(reply_target: str, send_reply):
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
        send_reply(reply_target, f"导入失败: {e}")


def _handle_share_url(text: str, open_id: str, reply_target: str, reply_type: str, send_reply):
    """处理 URL 分享"""
    try:
        from scripts.feishu_sdk_client import handle_share_content
        handle_share_content(open_id, text=text, reply_target=reply_target, reply_type=reply_type)
    except:
        send_reply(reply_target, "🔗 检测到链接，但分享处理功能暂未导入。")


def _handle_article_import(text: str, open_id: str, reply_target: str, send_reply):
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
            import re
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
        send_reply(reply_target, f"导入失败: {e}")


def _smart_route_and_reply(text: str, open_id: str, chat_id: str, reply_target: str, reply_type: str,
                           send_reply, session_id: str = None, mem=None):
    """智能路由和回复"""
    try:
        from src.utils.model_gateway import get_model_gateway
        from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt

        # 搜索知识库
        kb_entries = search_knowledge(text, limit=5)
        kb_context = format_knowledge_for_prompt(kb_entries) if kb_entries else ""

        # 构建 prompt
        prompt = text
        if kb_context:
            prompt = f"相关知识：\n{kb_context[:1500]}\n\n用户问题：{text}"

        gateway = get_model_gateway()
        result = gateway.call_azure_openai("cpo", prompt, "", "chat")

        if result.get("success"):
            send_reply(reply_target, result["response"])
        else:
            send_reply(reply_target, "抱歉，我暂时无法回答这个问题。")

    except Exception as e:
        send_reply(reply_target, f"处理异常: {str(e)[:200]}")


# === 导出接口 ===
__all__ = [
    "route_text_message",
]