"""
@description: LLM 意图识别与对话路由
@dependencies: src.utils.model_gateway, src.utils.conversation_memory, src.utils.capability_registry
@last_modified: 2026-03-25
"""
import json
import re
from typing import Dict, Any


def classify_intent(text: str, history: str, capabilities_desc: str, gateway) -> Dict[str, Any]:
    """
    用 LLM 识别用户意图。

    返回：
    {
        "intent": "chat|tool_call|research|command|continue_previous",
        "tool": "image_generation|knowledge_search|...|none",
        "needs_more_input": true/false,
        "what_to_ask": "需要用户补充什么",
        "direct_response": "如果可以直接回答就填这里",
        "reasoning": "判断理由"
    }
    """
    prompt = (
        f"你是智能摩托车全盔项目的 AI 助手。根据对话历史和用户最新消息，判断用户意图。\n\n"
        f"## 对话历史\n{history if history else '（新对话，无历史）'}\n\n"
        f"## 用户最新消息\n{text}\n\n"
        f"## 我的能力\n{capabilities_desc}\n\n"
        f"## 判断规则\n"
        f"1. 如果用户在问我'能不能做 XX'-> 对照能力清单回答，intent=chat\n"
        f"2. 如果用户明确想用某个工具（出图、查资料、研究）-> intent=tool_call, tool=对应工具\n"
        f"3. 如果用户发的是一个需要多 Agent 深度分析的复杂问题 -> intent=research\n"
        f"4. 如果用户在继续上一轮对话（补充信息、回答追问）-> intent=continue_previous\n"
        f"5. 如果只是普通聊天/闲聊 -> intent=chat\n"
        f"6. 如果用户的消息看起来像是给某个工具的输入（比如上一轮说要出图，这一轮发了 prompt）-> intent=tool_call\n\n"
        f"## 输出格式（只输出 JSON）\n"
        f'{{"intent": "chat|tool_call|research|continue_previous", '
        f'"tool": "image_generation|knowledge_search|deep_research|deep_dive|none", '
        f'"needs_more_input": true或false, '
        f'"what_to_ask": "如果需要更多输入，问什么", '
        f'"reasoning": "一句话判断理由"}}'
    )

    result = gateway.call_azure_openai("cpo", prompt,
        "只输出 JSON，不要有其他内容。", "intent_classify")

    if not result.get("success"):
        # 降级：默认当作普通对话
        return {"intent": "chat", "tool": "none", "needs_more_input": False, "reasoning": "LLM调用失败，降级"}

    try:
        resp = result["response"].strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        return json.loads(resp)
    except:
        return {"intent": "chat", "tool": "none", "needs_more_input": False, "reasoning": "JSON解析失败，降级"}