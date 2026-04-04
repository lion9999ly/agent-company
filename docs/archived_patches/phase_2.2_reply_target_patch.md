# Phase 2.2 — reply_target 作用域根治

## 改动文件: scripts/feishu_sdk_client.py
## 问题: 后台线程函数引用 reply_target 但不是函数参数，依赖全局 _reply_context 或闭包捕获
## 风险: 两个用户同时发消息时回复串台
## 原则: 所有后台线程函数必须显式接收 reply_target 和 reply_type

---

### 改动 1: `_stream_langgraph`（约第 595 行）

**原代码:**
```python
def _stream_langgraph(app, initial_state: dict, open_id: str = None) -> dict:
    """LangGraph stream 模式执行，精简进度消息"""
    progress_map = {
        ...
    }
    sent_stages = set()
    final_state = None
    for event in app.stream(initial_state, stream_mode="updates"):
        for node_name, node_output in event.items():
            final_state = node_output if isinstance(node_output, dict) else final_state
            msg = progress_map.get(node_name)
            if open_id and msg and msg not in sent_stages:
                send_reply(reply_target, msg)  # ← BUG: reply_target 不是参数
                sent_stages.add(msg)
    return final_state
```

**改为:**
```python
def _stream_langgraph(app, initial_state: dict, reply_target: str = None, reply_type: str = None) -> dict:
    """LangGraph stream 模式执行，精简进度消息"""
    progress_map = {
        "cpo_plan": None,
        "cto_coder": "📖 研究中: 技术方案",
        "cmo_strategist": "📖 研究中: 市场策略",
        "cdo_designer": "📖 研究中: 设计方案",
        "state_merge": None,
        "cpo_synthesis": "📖 研究中: 方案整合",
        "cpo_critic": None,
        "memory_writer": None,
    }
    sent_stages = set()
    final_state = None
    for event in app.stream(initial_state, stream_mode="updates"):
        for node_name, node_output in event.items():
            final_state = node_output if isinstance(node_output, dict) else final_state
            msg = progress_map.get(node_name)
            if reply_target and msg and msg not in sent_stages:
                send_reply(reply_target, msg, reply_type)
                sent_stages.add(msg)
    return final_state
```

---

### 改动 2: `call_langgraph`（约第 621 行）

找到调用 `_stream_langgraph` 的地方，修改参数传递。

**原代码:**
```python
def call_langgraph(text: str, task_role: str = "cto", open_id: str = None) -> str:
    ...
        try:
            result = _stream_langgraph(langgraph_app, initial_state, open_id)
        except Exception as stream_err:
            ...
```

**改为:**
```python
def call_langgraph(text: str, task_role: str = "cto", reply_target: str = None, reply_type: str = None) -> str:
    ...
        try:
            result = _stream_langgraph(langgraph_app, initial_state, reply_target, reply_type)
        except Exception as stream_err:
            ...
```

同时，`call_langgraph` 内部所有使用 `open_id` 的地方改为使用 `reply_target`：
- 第 683 行附近 `_try_generate_design_image(..., open_id)` → 见改动 3

---

### 改动 3: `_try_generate_design_image`（约第 571 行）

**原代码:**
```python
def _try_generate_design_image(cdo_output: dict, open_id: str) -> None:
    ...
    send_reply(reply_target, "🖼️ 正在生成设计概念图...")  # ← BUG
    ...
    if result.get("success") and result.get("image_base64"):
        image_bytes = b64.b64decode(result["image_base64"])
        send_image_reply(open_id, image_bytes)
    else:
        send_reply(reply_target, f"[概念图生成失败: ...]")  # ← BUG
```

**改为:**
```python
def _try_generate_design_image(cdo_output: dict, reply_target: str, reply_type: str = None) -> None:
    """从 CDO 输出中提取 AI_IMAGE_PROMPT 并生成图片"""
    import base64 as b64
    design = cdo_output.get("execution", {}).get("cdo_output", {}).get("design_proposal", "")
    if "[AI_IMAGE_PROMPT]" not in design:
        return
    prompt_section = design.split("[AI_IMAGE_PROMPT]")[-1].strip()
    lines = [l.strip() for l in prompt_section.split("\n") if l.strip() and not l.strip().startswith("[")]
    if not lines:
        return
    first_prompt = lines[0].lstrip("1. ").lstrip("- ")
    if len(first_prompt) < 10:
        return
    send_reply(reply_target, "🖼️ 正在生成设计概念图...", reply_type)
    from src.tools.tool_registry import get_tool_registry
    result = get_tool_registry().call("image_generation", first_prompt)
    if result.get("success") and result.get("image_base64"):
        image_bytes = b64.b64decode(result["image_base64"])
        send_image_reply(reply_target, image_bytes, reply_type or "open_id")
    else:
        send_reply(reply_target, f"[概念图生成失败: {result.get('error', '未知')}]", reply_type)
```

---

### 改动 4: `_run_rd_task_background`（约第 734 行）

**原代码:**
```python
def _run_rd_task_background(text: str, open_id: str) -> None:
    """后台线程执行研发任务，不阻塞主线程"""
    global _rd_task_running
    try:
        _rd_task_running = True
        reply = call_langgraph(text, open_id=open_id)
        if reply:
            send_reply(reply_target, reply)  # ← BUG
        send_reply(reply_target, "📝 请评价本次方案：...")  # ← BUG
    except Exception as e:
        send_reply(reply_target, f"❌ 研发任务执行失败: ...")  # ← BUG
    finally:
        _rd_task_running = False
```

**改为:**
```python
def _run_rd_task_background(text: str, open_id: str, reply_target: str = None, reply_type: str = None) -> None:
    """后台线程执行研发任务，不阻塞主线程"""
    global _rd_task_running
    # 如果没传 reply_target，降级到 open_id（向后兼容）
    if reply_target is None:
        reply_target = open_id
    try:
        _rd_task_running = True
        reply = call_langgraph(text, reply_target=reply_target, reply_type=reply_type)
        if reply:
            send_reply(reply_target, reply, reply_type)
        send_reply(reply_target, "📝 请评价本次方案：\nA. 可直接使用\nB. 需要小改\nC. 方向对但不够深\nD. 方向有问题\n回复字母即可，C/D 请附原因", reply_type)
    except Exception as e:
        send_reply(reply_target, f"❌ 研发任务执行失败: {str(e)[:300]}", reply_type)
        print(f"[RD_TASK] 后台执行异常: {e}")
    finally:
        _rd_task_running = False
```

---

### 改动 5: `handle_message` 中所有调用后台线程的地方

搜索 `feishu_sdk_client.py` 中所有 `threading.Thread(target=_run_rd_task_background` 的调用，
把 `args=(text, open_id)` 改为 `args=(text, open_id, reply_target, reply_type)`。

共约 4-5 处，分别在：

**text 消息路由中的研发任务触发（约第 1670 行附近）:**
```python
# 原
threading.Thread(target=_run_rd_task_background, args=(text, open_id), daemon=True).start()
# 改
threading.Thread(target=_run_rd_task_background, args=(text, open_id, reply_target, reply_type), daemon=True).start()
```

**post 消息路由中的研发任务触发（约第 2100 行附近）:**
```python
# 同上
threading.Thread(target=_run_rd_task_background, args=(text, open_id, reply_target, reply_type), daemon=True).start()
```

**语音消息处理 handle_audio_message 中的研发任务触发:**
```python
# 同上
threading.Thread(target=_run_rd_task_background, args=(transcribed_text, open_id, reply_target, reply_type), daemon=True).start()
```

**意图识别 research 分支（约第 2130 行附近）:**
```python
# 同上
threading.Thread(target=_run_rd_task_background, args=(text, open_id, reply_target, reply_type), daemon=True).start()
```

---

### 改动 6: `call_langgraph` 内部的 `_try_generate_design_image` 调用

在 `call_langgraph` 函数内（约第 683 行），找到：
```python
if open_id and "[AI_IMAGE_PROMPT]" in str(final_output):
    _try_generate_design_image({"execution": {"cdo_output": {"design_proposal": final_output}}}, open_id)
```

**改为:**
```python
if reply_target and "[AI_IMAGE_PROMPT]" in str(final_output):
    _try_generate_design_image({"execution": {"cdo_output": {"design_proposal": final_output}}}, reply_target, reply_type)
```

---

## 验证方法

1. 全局搜索 `feishu_sdk_client.py` 中的 `reply_target`，确认所有使用点都来自函数参数，不再有裸引用
2. 全局搜索 `_reply_context`，确认只在 `handle_message` 的开头设置和 `send_reply` 的降级分支使用
3. 两个飞书账号同时给机器人发消息，确认回复不串台
