"""Claude 思考层 — 通过飞书人工中转实现战略判断
@description: 系统遇到需要战略判断的问题时，推送到飞书让 Leo 转给 Claude
@dependencies: feishu_sdk_client
@last_modified: 2026-04-05
"""
import json
import time
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
THINKING_DIR = PROJECT_ROOT / ".ai-state" / "thinking_requests"
THINKING_DIR.mkdir(parents=True, exist_ok=True)

# 未来直接 API 调用开关
DIRECT_API_ENABLED = False  # 将来解决认证后改为 True

LEO_OPEN_ID = "ou_8e5e4f183e9eca4241378e96bac3a751"


def request_claude_thinking(question: str, context: str = "",
                            urgency: str = "normal",
                            callback_action: str = None,
                            send_reply=None, reply_target=None) -> str:
    """向 Claude 思考层提出问题

    流程：
    1. 生成格式化的问题，保存到文件
    2. 推送到飞书，Leo 复制给 Claude
    3. Leo 把 Claude 的回答粘贴回飞书
    4. 系统读取回答，执行 callback_action

    Args:
        question: 需要 Claude 判断的问题
        context: 相关上下文（报告摘要、数据等）
        urgency: "critical" / "normal" / "low"
        callback_action: 收到回答后要执行的动作标识
        send_reply: 飞书发送函数
        reply_target: 飞书发送目标

    Returns:
        request_id
    """
    request_id = f"think_{int(time.time())}"

    if DIRECT_API_ENABLED:
        return _call_claude_api_direct(question, context, request_id)
    else:
        return _request_via_feishu(question, context, urgency, callback_action,
                                   send_reply, reply_target, request_id)


def _request_via_feishu(question: str, context: str, urgency: str,
                        callback_action: str, send_reply, reply_target,
                        request_id: str) -> str:
    """人工中转方案：通过飞书推送问题"""

    # 构造给 Claude 的完整 prompt
    prompt = f"""## 来自 agent_company 的战略问题

**问题：** {question}

**上下文：**
{context[:3000]}

**产品锚点：**
"""
    # 读取 product_anchor
    anchor_path = PROJECT_ROOT / ".ai-state" / "product_anchor.md"
    if anchor_path.exists():
        prompt += anchor_path.read_text(encoding='utf-8')[:2000]

    prompt += f"""

请给出你的判断和建议。如果需要更多信息，说明需要什么。
回答末尾请加上标记：[THINK_ID:{request_id}]"""

    # 保存请求
    request_data = {
        "id": request_id,
        "question": question,
        "context": context[:1000],
        "urgency": urgency,
        "callback_action": callback_action,
        "status": "pending",
        "created_at": time.strftime('%Y-%m-%d %H:%M'),
        "prompt": prompt
    }
    request_path = THINKING_DIR / f"{request_id}.json"
    request_path.write_text(json.dumps(request_data, ensure_ascii=False, indent=2), encoding='utf-8')

    # 推送到飞书
    urgency_icon = {"critical": "🔴", "normal": "🟡", "low": "🟢"}
    feishu_msg = f"""{urgency_icon.get(urgency, '🟡')} 需要架构师判断

{question}

📋 请将以下内容复制给 Claude：
---
{prompt}
---

收到 Claude 回答后，回复：
思考回复:{request_id} Claude的回答内容"""

    if send_reply and reply_target:
        send_reply(reply_target, feishu_msg)
    else:
        # 默认发送给 Leo
        try:
            from scripts.feishu_sdk_client import send_reply as feishu_send
            feishu_send(LEO_OPEN_ID, feishu_msg, id_type="open_id")
        except Exception as e:
            print(f"[ThinkingLayer] 飞书发送失败: {e}")

    print(f"[ThinkingLayer] 已提交问题 {request_id}: {question[:50]}")
    return request_id


def _call_claude_api_direct(question: str, context: str, request_id: str) -> str:
    """直接调用 Claude API（未来实现）"""
    # TODO: 实现 Claude API 直接调用
    print(f"[ThinkingLayer] DIRECT_API_ENABLED 但尚未实现")
    return request_id


def process_claude_response(request_id: str, response: str) -> dict:
    """处理 Claude 的回答

    Args:
        request_id: 请求 ID
        response: Claude 的回答内容

    Returns:
        {"success": True/False, ...}
    """
    request_path = THINKING_DIR / f"{request_id}.json"
    if not request_path.exists():
        return {"success": False, "error": f"请求 {request_id} 不存在"}

    request_data = json.loads(request_path.read_text(encoding='utf-8'))
    request_data["status"] = "answered"
    request_data["response"] = response
    request_data["answered_at"] = time.strftime('%Y-%m-%d %H:%M')
    request_path.write_text(json.dumps(request_data, ensure_ascii=False, indent=2), encoding='utf-8')

    # 保存到思考历史（供未来 product_anchor 更新参考）
    history_path = PROJECT_ROOT / ".ai-state" / "thinking_history.jsonl"
    with open(history_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps({
            "id": request_id,
            "question": request_data["question"],
            "response": response[:2000],
            "timestamp": time.strftime('%Y-%m-%d %H:%M')
        }, ensure_ascii=False) + "\n")

    print(f"[ThinkingLayer] 收到回答 {request_id}")

    # 执行回调
    callback = request_data.get("callback_action")
    if callback:
        _execute_callback(callback, response, request_data)

    return {"success": True, "request_id": request_id}


def get_pending_requests() -> list:
    """获取待回答的问题"""
    pending = []
    for f in THINKING_DIR.glob("think_*.json"):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            if data.get("status") == "pending":
                pending.append(data)
        except:
            pass
    return sorted(pending, key=lambda x: x.get("created_at", ""), reverse=True)


def get_request(request_id: str) -> dict:
    """获取单个请求"""
    request_path = THINKING_DIR / f"{request_id}.json"
    if request_path.exists():
        return json.loads(request_path.read_text(encoding='utf-8'))
    return None


def _execute_callback(action: str, response: str, request_data: dict):
    """根据 Claude 回答执行后续动作"""
    if action == "update_product_anchor":
        # 更新产品锚点
        _update_product_anchor(response)
    elif action == "adjust_task_priority":
        print(f"[ThinkingLayer] TODO: 根据 Claude 回答调整任务优先级")
    elif action == "generate_decision":
        print(f"[ThinkingLayer] TODO: 根据 Claude 回答生成决策记录")


def _update_product_anchor(response: str):
    """根据 Claude 回答更新产品锚点"""
    anchor_path = PROJECT_ROOT / ".ai-state" / "product_anchor.md"
    if anchor_path.exists():
        content = anchor_path.read_text(encoding='utf-8')
        # 在文件末尾追加 Claude 的建议
        update = f"\n\n## Claude 建议 ({datetime.now().strftime('%Y-%m-%d')})\n{response[:1000]}"
        anchor_path.write_text(content + update, encoding='utf-8')
        print(f"[ThinkingLayer] 已更新 product_anchor.md")


if __name__ == "__main__":
    # 测试
    rid = request_claude_thinking(
        question="V1 应该选择 OLED 还是 MicroLED 光学方案？",
        context="成本差 2x，OLED 更成熟，MicroLED 更适合户外",
        urgency="normal"
    )
    print(f"Request ID: {rid}")

    pending = get_pending_requests()
    print(f"Pending: {len(pending)}")