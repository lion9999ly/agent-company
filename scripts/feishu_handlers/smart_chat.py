"""
@description: 智能对话处理器 - 意图识别、智能路由、教练模式、研发任务
@dependencies: model_gateway, knowledge_base, rd_task
@last_modified: 2026-04-08
"""
import re
import json
import threading
import base64
import time
from pathlib import Path
from datetime import datetime
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 教练模式状态
_coach_mode = {}

# Demo 会话状态
_demo_sessions = {}

# Demo 待确认问题
_demo_pending_questions = {}

# 记录最近一次 KB 回答（用于反馈）
_last_kb_answer = {}


def try_handle(text_stripped: str, reply_target: str, reply_type: str,
               open_id: str, chat_id: str, send_reply: Callable) -> bool:
    """智能对话相关指令路由

    Returns:
        bool: 是否处理了该消息
    """
    # 教练模式
    if text_stripped in ("教练模式", "帮我理清思路", "coach", "coaching"):
        _coach_mode[open_id or "default"] = True
        send_reply(reply_target, "已进入教练模式。我只问问题，不给答案。\n说\"退出教练\"结束。\n\n你目前最纠结的决策是什么？")
        return True

    if text_stripped in ("退出教练", "exit coach"):
        _coach_mode.pop(open_id or "default", None)
        send_reply(reply_target, "✅ 已退出教练模式。")
        return True

    # 教练模式回复处理
    if _coach_mode.get(open_id or "default"):
        _handle_coach_response(text_stripped, reply_target, send_reply)
        return True

    # 研发任务
    from scripts.feishu_handlers.rd_task import is_rd_task, is_rd_task_running
    if is_rd_task(text_stripped):
        if is_rd_task_running():
            send_reply(reply_target, "⏳ 上一个研发任务还在执行中，请稍后再试")
        else:
            from scripts.feishu_handlers.rd_task import run_rd_task_background
            send_reply(reply_target, "🚀 检测到研发任务，启动多Agent工作流...")
            threading.Thread(
                target=run_rd_task_background,
                args=(text_stripped, reply_target, reply_type, open_id, chat_id, send_reply),
                daemon=True
            ).start()
        return True

    return False


def handle_intent_route(text: str, open_id: str, chat_id: str, reply_target: str,
                        reply_type: str, send_reply: Callable, session_id: str = None, mem=None):
    """意图智能路由（兜底）"""
    intent = _classify_intent(text)

    if intent == "decision_brief":
        _handle_decision_brief("", reply_target, send_reply)
    elif intent == "negotiation":
        _handle_negotiation_brief("", reply_target, send_reply)
    elif intent == "knowledge_query":
        _handle_fast_query(text, reply_target, send_reply)
    elif intent == "coach":
        _coach_mode[open_id or "default"] = True
        send_reply(reply_target, "🧠 已进入教练模式。你目前最纠结的决策是什么？")
    elif intent == "status":
        from scripts.feishu_handlers.text_router import _handle_dashboard
        _handle_dashboard(reply_target, send_reply)
    else:
        # 兜底：智能对话
        _smart_route_and_reply(text, open_id, chat_id, reply_target, reply_type, send_reply, session_id, mem)


def handle_answer_feedback(text: str, open_id: str, reply_target: str, send_reply: Callable):
    """处理回答反馈（👍/👎）"""
    last_answer = _last_kb_answer.get(open_id or "default")
    if not last_answer:
        send_reply(reply_target, "⚠️ 没有可评价的回答")
        return

    feedback = "positive" if "👍" in text else "negative" if "👎" in text else None
    if not feedback:
        return

    try:
        from src.tools.knowledge_base import record_answer_feedback
        record_answer_feedback(
            question=last_answer.get("question", ""),
            kb_entry_ids=last_answer.get("kb_entries", []),
            feedback=feedback,
            user_id=open_id
        )
        del _last_kb_answer[open_id or "default"]
        send_reply(reply_target, "✅ 已记录你的反馈，感谢！")
    except Exception as e:
        send_reply(reply_target, f"⚠️ 反馈记录失败: {str(e)[:50]}")


def _classify_intent(text: str) -> str:
    """用 gemini_2_5_flash 分类用户意图"""
    from scripts.litellm_gateway import get_model_gateway
    gw = get_model_gateway()
    result = gw.call("gemini_2_5_flash",
        f"用户说: {text}\n\n"
        f"判断意图类别（只输出类别名，不要解释）:\n"
        f"research_task — 需要多Agent协作的研发分析\n"
        f"decision_brief — 想看某个决策的简报\n"
        f"negotiation — 谈判准备\n"
        f"knowledge_query — 查询知识库（简单问题）\n"
        f"deep_drill — 想深入研究某个话题\n"
        f"coach — 想理清思路，需要教练式提问\n"
        f"product_vision — 想看产品愿景或场景描述\n"
        f"status — 想看系统状态\n"
        f"chat — 普通闲聊或简单问题\n",
        task_type="intent_classify")
    if result.get("success"):
        return result["response"].strip().split("\n")[0].strip()
    return "chat"


def _handle_coach_response(text: str, reply_target: str, send_reply: Callable):
    """教练模式回复——只问问题，不给答案"""
    from scripts.litellm_gateway import get_model_gateway
    from src.tools.knowledge_base import search_knowledge
    gw = get_model_gateway()

    kb = search_knowledge(text, limit=5)
    kb_text = "\n".join([f"- {r.get('title','')}: {r.get('content','')[:150]}" for r in kb])

    result = gw.call("gpt_5_4",
        f"用户说: {text}\n\n"
        f"相关知识:\n{kb_text}\n\n"
        f"你是一个苏格拉底式教练。规则:\n"
        f"1. 绝对不给答案或建议\n"
        f"2. 只问一个尖锐的问题，挑战用户的假设或暴露盲区\n"
        f"3. 问题要基于数据（引用知识库中的信息）\n"
        f"4. 保持友善但犀利",
        "你是产品教练，只问问题不给答案。", "coach")
    if result.get("success"):
        send_reply(reply_target, result["response"])
    else:
        send_reply(reply_target, "你这个问题很有意思——你觉得最大的风险是什么？")


def _handle_fast_query(text: str, reply_target: str, send_reply: Callable):
    """简单问答快速通道"""
    try:
        from scripts.litellm_gateway import get_model_gateway
        from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt
        gw = get_model_gateway()

        kb_entries = search_knowledge(text, limit=5)
        kb_context = format_knowledge_for_prompt(kb_entries) if kb_entries else ""

        prompt = text
        if kb_context:
            prompt = f"相关知识：\n{kb_context[:1500]}\n\n用户问题：{text}"

        result = gw.call("gemini_2_5_flash", prompt, "", "chat")
        if result.get("success"):
            send_reply(reply_target, result["response"])
        else:
            send_reply(reply_target, "抱歉，我暂时无法回答这个问题。")
    except Exception as e:
        from scripts.feishu_handlers.chat_helpers import _safe_reply_error
        _safe_reply_error(send_reply, reply_target, "智能对话", e)


def _handle_decision_brief(decision_id: str, reply_target: str, send_reply: Callable):
    """生成决策简报"""
    send_reply(reply_target, f"📋 正在生成决策简报: {decision_id}...")

    def _run():
        try:
            import yaml as _yaml
            from scripts.litellm_gateway import get_model_gateway
            from src.tools.knowledge_base import search_knowledge
            gw = get_model_gateway()

            dt_path = PROJECT_ROOT / ".ai-state" / "product_decision_tree.yaml"
            decision = None
            if dt_path.exists():
                dt = _yaml.safe_load(dt_path.read_text(encoding='utf-8'))
                for d in dt.get("decisions", []):
                    if decision_id.lower() in d.get("id", "").lower() or decision_id in d.get("question", ""):
                        decision = d
                        break

            if not decision:
                send_reply(reply_target, f"⚠️ 未找到决策: {decision_id}")
                return

            kb_results = search_knowledge(decision["question"], limit=15)
            kb_text = "\n".join([f"- [{r.get('confidence','')}] {r.get('title','')}: {r.get('content','')[:200]}"
                                for r in kb_results])

            resolved = decision.get("resolved_knowledge", [])
            resolved_text = "\n".join([f"- {r.get('knowledge','')}" for r in resolved]) if resolved else "暂无"

            prompt = (
                f"生成决策简报。\n\n"
                f"## 决策问题\n{decision['question']}\n\n"
                f"## 已确认的知识\n{resolved_text}\n\n"
                f"## 相关知识库条目\n{kb_text}\n\n"
                f"## 仍缺的知识\n" +
                "\n".join([f"- {bk}" for bk in decision.get("blocking_knowledge", [])]) +
                f"\n\n## 要求\n"
                f"1. 列出所有可选方案\n"
                f"2. 标注数据来源的 confidence\n"
                f"3. 如果数据足够，给出推荐"
            )

            result = gw.call("gpt_5_4", prompt, "你是产品决策顾问。", "synthesis")
            if result.get("success"):
                send_reply(reply_target, result["response"])
            else:
                send_reply(reply_target, f"生成失败: {result.get('error', '')[:200]}")
        except Exception as e:
            from scripts.feishu_handlers.chat_helpers import _safe_reply_error
            _safe_reply_error(send_reply, reply_target, "内容生成", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_negotiation_brief(target_name: str, reply_target: str, send_reply: Callable):
    """生成谈判准备简报"""
    send_reply(reply_target, f"📋 正在生成谈判准备: {target_name}...")

    def _run():
        try:
            import yaml as _yaml
            from scripts.litellm_gateway import get_model_gateway
            from src.tools.knowledge_base import search_knowledge
            gw = get_model_gateway()

            kb_results = search_knowledge(f"{target_name} 产能 报价 供应商", limit=15)
            kb_text = "\n".join([f"- [{r.get('confidence','')}] {r.get('title','')}: {r.get('content','')[:200]}"
                                for r in kb_results])

            competitor_results = search_knowledge(f"{target_name} 竞品 替代供应商", limit=10)
            competitor_text = "\n".join([f"- {r.get('title','')}: {r.get('content','')[:150]}"
                                        for r in competitor_results])

            prompt = (
                f"生成谈判准备简报。\n\n"
                f"## 谈判对象\n{target_name}\n\n"
                f"## 对方信息\n{kb_text}\n\n"
                f"## 竞品/替代方案\n{competitor_text}\n\n"
                f"## 要求\n"
                f"1. 对方产能和报价分析\n"
                f"2. 竞品对比\n"
                f"3. BATNA\n"
                f"4. 谈判策略建议"
            )

            result = gw.call("gpt_5_4", prompt, "你是采购谈判顾问。", "synthesis")
            if result.get("success"):
                send_reply(reply_target, result["response"])
            else:
                send_reply(reply_target, f"生成失败: {result.get('error', '')[:200]}")
        except Exception as e:
            from scripts.feishu_handlers.chat_helpers import _safe_reply_error
            _safe_reply_error(send_reply, reply_target, "内容生成", e)

    threading.Thread(target=_run, daemon=True).start()


def _smart_route_and_reply(text: str, open_id: str, chat_id: str, reply_target: str, reply_type: str,
                           send_reply: Callable, session_id: str = None, mem=None):
    """智能路由和回复"""
    try:
        from scripts.litellm_gateway import get_model_gateway
        from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt

        kb_entries = search_knowledge(text, limit=5)
        kb_context = format_knowledge_for_prompt(kb_entries) if kb_entries else ""
        kb_used = bool(kb_context)

        prompt = text
        if kb_context:
            prompt = f"相关知识：\n{kb_context[:1500]}\n\n用户问题：{text}"

        gateway = get_model_gateway()
        result = gateway.call_azure_openai("cpo", prompt, "", "chat")

        if result.get("success"):
            reply_text = result["response"]
            if kb_used:
                reply_text += "\n\n📊 这个回答准确吗？回复 👍 或 👎"
            send_reply(reply_target, reply_text)
            _last_kb_answer[open_id or "default"] = {
                "question": text[:100],
                "kb_entries": [e.get("id", "") for e in (kb_entries or [])],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
        else:
            send_reply(reply_target, "抱歉，我暂时无法回答这个问题。")

    except Exception as e:
        from scripts.feishu_handlers.chat_helpers import _safe_reply_error
        _safe_reply_error(send_reply, reply_target, "智能对话", e)


def get_demo_sessions():
    """获取 Demo 会话状态"""
    return _demo_sessions


def get_coach_mode():
    """获取教练模式状态"""
    return _coach_mode