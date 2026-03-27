# 飞书机器人升级 — 从指令分发器到对话 Agent

> 生成时间: 2026-03-25
> 核心目标: 有记忆、懂意图、知道自己能干什么的对话 Agent
> 不影响已有功能：指令、深挖、研发任务、文档导入全部保留

---

## 架构设计

### 当前

```
用户消息 → 关键词匹配路由 → 执行对应功能 → 返回结果
（每条消息独立，无上下文）
```

### 升级后

```
用户消息 → 加载对话历史 → LLM 意图识别 → 路由
                                          ├─ 直接指令（"日报"/"知识库"）→ 原有逻辑
                                          ├─ 工具调用（出图/搜索/查知识库）→ 调用工具返回
                                          ├─ 研发任务（复杂问题需要多 Agent）→ LangGraph
                                          ├─ 继续上轮对话 → 带上下文回复
                                          └─ 普通对话 → 带知识库的智能回复
```

---

## Task 1: 对话记忆管理

### 1.1 创建 src/utils/conversation_memory.py

```python
"""
@description: 飞书对话记忆管理 - 维护每个用户/群的最近对话上下文
@dependencies: json, pathlib, datetime
@last_modified: 2026-03-25
"""
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional

MEMORY_DIR = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "conversations"


class ConversationMemory:
    """管理飞书对话的短期记忆"""
    
    def __init__(self, max_turns: int = 20, expire_minutes: int = 60):
        """
        max_turns: 保留最近多少轮对话
        expire_minutes: 超过多少分钟算过期（新对话）
        """
        self.max_turns = max_turns
        self.expire_minutes = expire_minutes
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    
    def _get_file(self, session_id: str) -> Path:
        """每个用户/群一个对话文件"""
        safe_id = "".join(c for c in session_id if c.isalnum() or c in "_-")
        return MEMORY_DIR / f"{safe_id}.json"
    
    def _load(self, session_id: str) -> dict:
        f = self._get_file(session_id)
        if not f.exists():
            return {"messages": [], "updated": None, "context": {}}
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            # 检查是否过期
            updated = data.get("updated")
            if updated:
                last_time = datetime.fromisoformat(updated)
                if datetime.now() - last_time > timedelta(minutes=self.expire_minutes):
                    # 过期了，开新对话但保留上一轮摘要
                    old_summary = self._summarize_old(data.get("messages", []))
                    return {
                        "messages": [],
                        "updated": None,
                        "context": {"previous_session_summary": old_summary}
                    }
            return data
        except:
            return {"messages": [], "updated": None, "context": {}}
    
    def _save(self, session_id: str, data: dict):
        data["updated"] = datetime.now().isoformat()
        self._get_file(session_id).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    
    def _summarize_old(self, messages: list) -> str:
        """简单摘要过期的对话历史"""
        if not messages:
            return ""
        user_msgs = [m["content"][:100] for m in messages if m["role"] == "user"][-5:]
        return f"上一轮对话涉及: {'; '.join(user_msgs)}"
    
    def add_user_message(self, session_id: str, content: str):
        """记录用户消息"""
        data = self._load(session_id)
        data["messages"].append({
            "role": "user",
            "content": content,
            "time": datetime.now().isoformat()
        })
        # 保持最大轮次
        data["messages"] = data["messages"][-self.max_turns * 2:]
        self._save(session_id, data)
    
    def add_bot_message(self, session_id: str, content: str, action: str = "reply"):
        """记录机器人回复"""
        data = self._load(session_id)
        data["messages"].append({
            "role": "assistant",
            "content": content[:2000],  # 限制长度
            "action": action,
            "time": datetime.now().isoformat()
        })
        data["messages"] = data["messages"][-self.max_turns * 2:]
        self._save(session_id, data)
    
    def set_context(self, session_id: str, key: str, value):
        """设置对话上下文变量（如：等待图片prompt、等待确认等）"""
        data = self._load(session_id)
        data.setdefault("context", {})[key] = value
        self._save(session_id, data)
    
    def get_context(self, session_id: str, key: str, default=None):
        """获取对话上下文变量"""
        data = self._load(session_id)
        return data.get("context", {}).get(key, default)
    
    def clear_context(self, session_id: str, key: str = None):
        """清除上下文变量"""
        data = self._load(session_id)
        if key:
            data.get("context", {}).pop(key, None)
        else:
            data["context"] = {}
        self._save(session_id, data)
    
    def get_history_for_prompt(self, session_id: str, max_chars: int = 4000) -> str:
        """获取格式化的对话历史，用于注入 LLM prompt"""
        data = self._load(session_id)
        messages = data.get("messages", [])
        prev_summary = data.get("context", {}).get("previous_session_summary", "")
        
        if not messages and not prev_summary:
            return ""
        
        parts = []
        if prev_summary:
            parts.append(f"[上轮对话摘要] {prev_summary}")
        
        total_chars = 0
        # 从最近的开始，往前取
        for msg in reversed(messages):
            role = "用户" if msg["role"] == "user" else "助手"
            content = msg["content"][:500]
            line = f"{role}: {content}"
            if total_chars + len(line) > max_chars:
                break
            parts.insert(-1 if prev_summary else 0, line)  # 插到摘要之后
            total_chars += len(line)
        
        # 正序排列
        return "\n".join(parts)
    
    def get_last_bot_action(self, session_id: str) -> Optional[str]:
        """获取机器人上一次的动作类型"""
        data = self._load(session_id)
        for msg in reversed(data.get("messages", [])):
            if msg["role"] == "assistant":
                return msg.get("action", "reply")
        return None


_memory = None

def get_conversation_memory() -> ConversationMemory:
    global _memory
    if _memory is None:
        _memory = ConversationMemory()
    return _memory
```

### 验证

```bash
python -c "
from src.utils.conversation_memory import get_conversation_memory
mem = get_conversation_memory()
mem.add_user_message('test_user', '你好')
mem.add_bot_message('test_user', '你好！有什么可以帮你？')
mem.add_user_message('test_user', '帮我出张图')
history = mem.get_history_for_prompt('test_user')
print(f'对话历史:\n{history}')
# 清理
from pathlib import Path
Path('.ai-state/conversations/test_user.json').unlink(missing_ok=True)
print('✅ Task 1 完成')
"
```

---

## Task 2: 能力自知 — 机器人知道自己能干什么

### 2.1 创建 src/utils/capability_registry.py

```python
"""
@description: Agent 能力注册表 - 机器人知道自己能干什么
@dependencies: None
@last_modified: 2026-03-25
"""

# 机器人的所有能力，用于意图识别和自我介绍
CAPABILITIES = {
    "image_generation": {
        "name": "AI 图像生成",
        "description": "根据文字描述生成概念渲染图、产品效果图",
        "trigger_keywords": ["出图", "生成图", "画", "渲染", "效果图", "概念图", "imagen"],
        "usage": "发送图片描述文字，我会生成图片",
        "tool": "image_generation",
        "needs_input": "图片描述文字（prompt）",
    },
    "image_understanding": {
        "name": "图片理解",
        "description": "识别和分析图片内容，包括产品图、技术图纸、竞品照片",
        "trigger_keywords": ["识别", "看图", "分析图片", "这是什么"],
        "usage": "直接发图片给我",
        "tool": "gemini_vision",
        "needs_input": "图片",
    },
    "knowledge_search": {
        "name": "知识库查询",
        "description": f"搜索项目知识库，当前有 2400+ 条技术档案、竞品分析、标准法规",
        "trigger_keywords": ["知识库", "查一下", "找一下", "有没有关于"],
        "usage": "直接问技术问题，我会从知识库找答案",
        "tool": "knowledge_search",
        "needs_input": "查询问题",
    },
    "deep_research": {
        "name": "深度研究",
        "description": "多 Agent 协作的深度研究，CTO+CMO+CDO 三个视角分析",
        "trigger_keywords": ["研究", "深入分析", "研发任务", "方案评估"],
        "usage": "发送研究问题，如'研究 AR1 vs AR2 在头盔场景的对比'",
        "tool": "langgraph",
        "needs_input": "研究问题",
    },
    "deep_dive": {
        "name": "知识图谱深挖",
        "description": "对某个技术领域进行系统性深挖，发现完整产品家族",
        "trigger_keywords": ["深挖", "知识图谱", "展开", "系统性"],
        "usage": "发送'深挖'自动选择薄弱方向，或'深挖 电池BMS方案'指定方向",
        "tool": "kg_expand",
        "needs_input": "可选的方向指定",
    },
    "document_import": {
        "name": "文档导入",
        "description": "导入 PPT/PDF/Word/Excel 到知识库，支持图片理解",
        "trigger_keywords": ["导入", "学习这个", "导入文档"],
        "usage": "发送文件或长文，自动导入知识库",
        "tool": "doc_import",
        "needs_input": "文档文件或长文本",
    },
    "daily_report": {
        "name": "日报与审计",
        "description": "查看知识库状态、学习进度、Token 用量、质量审计",
        "trigger_keywords": ["日报", "审计", "token", "用量", "知识库"],
        "usage": "发送'日报'、'审计'、'知识库'等指令",
        "tool": "report",
        "needs_input": "无",
    },
}


def get_capabilities_summary() -> str:
    """生成能力摘要，用于注入 LLM prompt"""
    lines = ["## 我的能力清单\n"]
    for key, cap in CAPABILITIES.items():
        lines.append(f"- **{cap['name']}**: {cap['description']}")
        lines.append(f"  用法: {cap['usage']}")
    return "\n".join(lines)


def get_capabilities_for_intent() -> str:
    """生成用于意图识别的能力描述（更精简）"""
    items = []
    for key, cap in CAPABILITIES.items():
        items.append(f"{key}: {cap['name']} — {cap['description'][:50]}")
    return "\n".join(items)
```

---

## Task 3: LLM 意图识别 + 对话路由

### 3.1 创建 src/utils/intent_router.py

```python
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
        f"1. 如果用户在问我'能不能做 XX'→ 对照能力清单回答，intent=chat\n"
        f"2. 如果用户明确想用某个工具（出图、查资料、研究）→ intent=tool_call, tool=对应工具\n"
        f"3. 如果用户发的是一个需要多 Agent 深度分析的复杂问题 → intent=research\n"
        f"4. 如果用户在继续上一轮对话（补充信息、回答追问）→ intent=continue_previous\n"
        f"5. 如果只是普通聊天/闲聊 → intent=chat\n"
        f"6. 如果用户的消息看起来像是给某个工具的输入（比如上一轮说要出图，这一轮发了 prompt）→ intent=tool_call\n\n"
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
```

---

## Task 4: 重写飞书消息路由（核心改动）

### 4.1 在 feishu_sdk_client.py 的 handle_message 中，替换现有的文本路由逻辑

**不改已有的精确指令匹配**（"日报"/"知识库"/"审计"等），只改 fallback 分支。

找到当前文本处理的 else 分支（所有精确指令都不匹配时的 fallback），替换为：

```python
    # ============================================
    # 非精确指令 → LLM 意图识别 + 智能路由
    # ============================================
    else:
        from src.utils.conversation_memory import get_conversation_memory
        from src.utils.capability_registry import get_capabilities_for_intent, get_capabilities_summary, CAPABILITIES
        from src.utils.intent_router import classify_intent
        from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt, KB_ROOT
        
        mem = get_conversation_memory()
        session_id = chat_id if chat_type == "group" else open_id
        
        # 记录用户消息
        mem.add_user_message(session_id, text)
        
        # 获取对话历史
        history = mem.get_history_for_prompt(session_id)
        
        # 检查是否有等待中的上下文（如：上轮说要出图，等 prompt）
        pending_tool = mem.get_context(session_id, "pending_tool")
        
        if pending_tool:
            # 有等待中的工具调用 → 直接执行
            intent_result = {
                "intent": "tool_call",
                "tool": pending_tool,
                "needs_more_input": False,
                "reasoning": "用户提供了上轮等待的输入"
            }
            mem.clear_context(session_id, "pending_tool")
        else:
            # LLM 意图识别
            caps_desc = get_capabilities_for_intent()
            intent_result = classify_intent(text, history, caps_desc, gateway)
        
        intent = intent_result.get("intent", "chat")
        tool = intent_result.get("tool", "none")
        needs_more = intent_result.get("needs_more_input", False)
        
        print(f"[Intent] {intent}, tool={tool}, needs_more={needs_more}, reason={intent_result.get('reasoning', '')[:60]}")
        
        # === 路由执行 ===
        
        if intent == "tool_call" and tool == "image_generation":
            if needs_more:
                mem.set_context(session_id, "pending_tool", "image_generation")
                reply_text = intent_result.get("what_to_ask", "请发送你想生成的图片描述（prompt），越详细越好。")
                send_reply(reply_target, reply_text, reply_type)
                mem.add_bot_message(session_id, reply_text, "ask_input")
            else:
                send_reply(reply_target, "🎨 正在生成图片...", reply_type)
                from src.tools.tool_registry import get_tool_registry
                _registry = get_tool_registry()
                img_result = _registry.call("image_generation", text)
                if img_result.get("success") and img_result.get("image_base64"):
                    # 发送图片到飞书
                    import base64
                    img_bytes = base64.b64decode(img_result["image_base64"])
                    _send_image_reply(reply_target, img_bytes, reply_type)
                    reply_text = "图片已生成。要调整什么地方吗？"
                    send_reply(reply_target, reply_text, reply_type)
                    mem.set_context(session_id, "last_image_prompt", text)
                else:
                    reply_text = f"图片生成失败: {img_result.get('error', '未知错误')[:200]}"
                    send_reply(reply_target, reply_text, reply_type)
                mem.add_bot_message(session_id, reply_text, "image_generation")
        
        elif intent == "tool_call" and tool == "knowledge_search":
            kb_entries = search_knowledge(text, limit=8)
            if kb_entries:
                kb_text = format_knowledge_for_prompt(kb_entries)
                # 用 LLM 基于知识库回答
                answer_prompt = (
                    f"基于以下知识库内容，回答用户的问题。引用具体数据。\n\n"
                    f"{kb_text[:4000]}\n\n"
                    f"用户问题：{text}"
                )
                answer_result = gateway.call_azure_openai("cpo", answer_prompt,
                    "简洁专业地回答，引用具体数据。", "kb_answer")
                reply_text = answer_result.get("response", "查询失败") if answer_result.get("success") else "查询失败"
            else:
                reply_text = f"知识库中暂无关于「{text[:20]}」的信息。要我发起一次深度研究吗？"
                mem.set_context(session_id, "pending_research_topic", text)
            send_reply(reply_target, reply_text, reply_type)
            mem.add_bot_message(session_id, reply_text, "knowledge_search")
        
        elif intent == "research":
            # 触发研发任务（LangGraph）
            send_reply(reply_target, f"🔬 检测到研发任务，启动多 Agent 工作流...", reply_type)
            mem.add_bot_message(session_id, "启动研发任务", "research")
            # 调用已有的 LangGraph 逻辑
            _handle_research_task(text, open_id, chat_id, reply_target, reply_type, message_id)
        
        elif intent == "chat":
            # 智能对话：带知识库 + 能力清单 + 对话历史
            kb_entries = search_knowledge(text, limit=5)
            kb_context = format_knowledge_for_prompt(kb_entries) if kb_entries else ""
            
            # 读取产品锚点
            product_anchor = ""
            import json as _json
            for f in KB_ROOT.rglob("*.json"):
                try:
                    data = _json.loads(f.read_text(encoding="utf-8"))
                    tags = data.get("tags", [])
                    if "internal" in tags and ("prd" in tags or "product_definition" in tags):
                        product_anchor = data.get("content", "")[:800]
                        break
                except:
                    continue
            
            caps_summary = get_capabilities_summary()
            
            chat_prompt = (
                f"你是智能摩托车全盔项目的 AI 合伙人「Leo's Agent」。\n\n"
                f"## 对话历史\n{history}\n\n"
                f"## 我的能力\n{caps_summary}\n\n"
            )
            if product_anchor:
                chat_prompt += f"## 产品定义\n{product_anchor[:500]}\n\n"
            if kb_context:
                chat_prompt += f"## 相关知识\n{kb_context[:2000]}\n\n"
            chat_prompt += f"## 用户消息\n{text}\n\n"
            chat_prompt += (
                f"## 回复要求\n"
                f"- 像合伙人之间对话，简洁有力，不像客服\n"
                f"- 如果用户问你能不能做什么，对照能力清单诚实回答\n"
                f"- 如果和项目相关，引用知识库中的具体数据\n"
                f"- 如果你觉得用户的问题值得深入研究，主动建议\n"
                f"- 保持上下文连贯，不要每次都像新对话\n"
            )
            
            result = gateway.call_azure_openai("cpo", chat_prompt,
                "你是项目合伙人Leo's Agent。", "smart_chat")
            reply_text = result.get("response", "抱歉，我没理解。能换个方式说吗？") if result.get("success") else "服务暂时不可用"
            send_reply(reply_target, reply_text, reply_type)
            mem.add_bot_message(session_id, reply_text, "chat")
        
        else:
            # 兜底
            send_reply(reply_target, "收到，但我不太确定你想让我做什么。可以说得更具体一些吗？", reply_type)
```

### 4.2 提取研发任务触发为独立函数

把当前代码中触发 LangGraph 的逻辑提取成 `_handle_research_task` 函数，避免重复代码：

```python
def _handle_research_task(text, open_id, chat_id, reply_target, reply_type, message_id):
    """触发 LangGraph 研发任务（从已有逻辑中提取）"""
    # ... 现有的 LangGraph 调用逻辑搬过来 ...
```

### 4.3 图片发送辅助函数

```python
def _send_image_reply(target_id, image_bytes: bytes, id_type: str = "open_id"):
    """发送图片到飞书"""
    # 先上传图片到飞书获取 image_key
    # 然后用 image_key 发消息
    # 具体 API: POST /open-apis/im/v1/images (上传)
    # 然后 POST /open-apis/im/v1/messages (发送 image 类型消息)
    
    import requests
    # 上传图片
    upload_url = "https://open.feishu.cn/open-apis/im/v1/images"
    # 需要 tenant_access_token，从现有的飞书 SDK 中获取
    # ... 参考已有的飞书图片上传逻辑 ...
    pass  # CC 根据已有的飞书 SDK 实现这个函数
```

---

## Task 5: 对话记忆自动清理

在 resource_manager.py 的 auto_cleanup 中添加：

```python
def cleanup_conversations():
    """清理过期的对话记忆文件"""
    conv_dir = PROJECT_ROOT / ".ai-state" / "conversations"
    if not conv_dir.exists():
        return 0
    count = 0
    cutoff = datetime.now() - timedelta(days=3)
    for f in conv_dir.glob("*.json"):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
                count += 1
        except:
            continue
    return count
```

在 `auto_cleanup` 函数中调用。

---

## Task 6: 飞书指令清单更新

在现有的精确指令匹配中，添加一个"帮助"指令：

```python
elif text.strip() in ("帮助", "help", "?", "？", "能力", "你能做什么"):
    from src.utils.capability_registry import get_capabilities_summary
    send_reply(reply_target, get_capabilities_summary(), reply_type)
```

---

## 验证

```bash
# 1. 所有新文件可导入
python -c "from src.utils.conversation_memory import get_conversation_memory; print('memory OK')"
python -c "from src.utils.capability_registry import CAPABILITIES, get_capabilities_summary; print('capability OK')"
python -c "from src.utils.intent_router import classify_intent; print('intent OK')"
python -c "from scripts.feishu_sdk_client import handle_message; print('feishu OK')"

# 2. 对话记忆测试
python -c "
from src.utils.conversation_memory import get_conversation_memory
mem = get_conversation_memory()
mem.add_user_message('test', '你能出图吗')
mem.add_bot_message('test', '可以，发 prompt 给我', 'ask_input')
mem.set_context('test', 'pending_tool', 'image_generation')
mem.add_user_message('test', '一个戴着碳纤维头盔的骑士')
pending = mem.get_context('test', 'pending_tool')
print(f'pending_tool: {pending}')
history = mem.get_history_for_prompt('test')
print(f'history:\n{history}')
from pathlib import Path
Path('.ai-state/conversations/test.json').unlink(missing_ok=True)
print('✅ 验证通过')
"

# 3. 重启服务后在飞书测试以下对话：
# "你能出图吗" → 应该回答能力说明
# "帮我生成一张摩托车头盔效果图" → 应该触发出图
# "你知道 AR1 和 AR2 的区别吗" → 应该查知识库回答
# "研究一下毫米波雷达在头盔上的可行性" → 应该触发研发任务
```

---

## 效果对比

| 场景 | 之前 | 之后 |
|------|------|------|
| "你能出图吗" | 裸 LLM 瞎答 | 对照能力清单回答，问要不要现在出图 |
| "帮我出张图" → "一个骑士..." | 第二条被当作新对话/研发任务 | 记住上轮在等 prompt，直接出图 |
| "AR1 和 AR2 区别" | 裸 LLM 编答案 | 搜知识库，引用技术档案数据回答 |
| "nano banana 能调用吗" | 空洞的客服式回答 | 对照能力清单，诚实说能或不能 |
| "研究一下散热方案" | 可能被路由到聊天 | LLM 判断为研究任务，触发 LangGraph |
| 同事在群里问问题 | 报错或不回答 | 正常回答，群聊对话独立记忆 |
