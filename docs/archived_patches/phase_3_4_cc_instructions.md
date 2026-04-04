# Phase 3 + Phase 4 — CC 一次性执行指令

> 目标：6 个子任务，涉及 4 个文件的修改 + 1 个新依赖安装
> 预计耗时：CC 执行 20-30 分钟
> 验证：每个子任务改完后跑对应的验证命令

---

## 总览

| Phase | 子任务 | 改动文件 | 核心内容 |
|-------|--------|----------|----------|
| 3.1 | 知识库写入门控 | `src/tools/knowledge_base.py` | add_knowledge 增加 guardrail |
| 3.2 | 评价→规则闭环 | `scripts/feishu_sdk_client.py` | D 评价自动生成 check_rule |
| 3.3 | Post 消息路由补全 | `scripts/feishu_sdk_client.py` | post 兜底加意图识别 |
| 3.4 | 热更新 | `scripts/feishu_sdk_client.py` | watchdog 文件监听 + reload |
| 4.1 | Checkpoint 持久化 | `src/graph/router.py` | LangGraph SqliteSaver |
| 4.2 | 恢复指令 | `scripts/feishu_sdk_client.py` | 飞书 "恢复任务" 指令 |

---

## Phase 3.1 — 知识库写入门控

### 文件：`src/tools/knowledge_base.py`

### 改动：修改 `add_knowledge` 函数，增加 guardrail 层

在 `add_knowledge` 函数开头（hash 去重逻辑之前），插入以下门控逻辑：

```python
def add_knowledge(title: str, domain: str, content: str, tags: List[str],
                  source: str = "auto", confidence: str = "medium",
                  caller: str = "auto") -> str:
    """添加新的知识条目

    Args:
        caller: 调用来源，影响 confidence 上限
            - "user_share" / "doc_import" / "user_upload": 允许 high
            - "self_learning" / "auto" / "llm_generate": 上限 medium
            - "product_decision": 允许 authoritative
    """
    import random

    # === Guardrail 1: 内容最小长度 ===
    if len(content.strip()) < 30:
        print(f"[KB_GUARD] 拒绝入库: content 太短 ({len(content.strip())} 字) — {title[:40]}")
        return None

    # === Guardrail 2: confidence 上限 ===
    TRUSTED_CALLERS = {"user_share", "doc_import", "user_upload", "product_decision",
                       "user_feedback_analysis", "critic_rule"}
    if caller not in TRUSTED_CALLERS:
        if confidence == "high":
            confidence = "medium"
            print(f"[KB_GUARD] confidence 降级: {caller} 不允许标 high — {title[:40]}")
        if confidence == "authoritative":
            confidence = "medium"
            print(f"[KB_GUARD] confidence 降级: {caller} 不允许标 authoritative — {title[:40]}")

    # === Guardrail 3: 单日写入限流 ===
    domain = _normalize_domain(domain)
    domain_dir = KB_ROOT / domain
    if domain_dir.exists():
        from datetime import date
        today_str = date.today().strftime("%Y%m%d")
        today_count = sum(1 for f in domain_dir.glob(f"{today_str}_*.json"))
        if today_count >= 100:
            print(f"[KB_GUARD] 单日限流: {domain} 今日已写 {today_count} 条，拒绝 — {title[:40]}")
            return None

    # === 原有逻辑（hash 去重 + 写入）===
    # ... 以下保持不变 ...
```

注意：函数签名新增了 `caller: str = "auto"` 参数，默认值 `"auto"` 保证向后兼容，已有的调用点不需要全部改。

### 额外改动：关键调用点传入 caller

在 `feishu_sdk_client.py` 中搜索所有 `add_knowledge(` 调用，找到以下几处，加上 caller 参数：

1. `handle_share_content` 中的用户分享入库（约 2 处）→ 加 `caller="user_share"`
2. `_import_article_to_kb` 中的文章导入 → 加 `caller="user_share"`
3. `handle_image_message` 中的图片入库 → 加 `caller="user_share"`
4. `handle_rating` 中 D 评价教训入库 → 加 `caller="user_feedback_analysis"`
5. `handle_rating` 中 A 评价成功模式入库 → 加 `caller="user_feedback_analysis"`

在 `daily_learning.py` 中搜索 `add_knowledge(` → 加 `caller="self_learning"`
在 `knowledge_graph_expander.py` 中搜索 `add_knowledge(` → 加 `caller="auto"`
在 `overnight_kb_overhaul.py` 中搜索 `add_knowledge(` → 加 `caller="auto"`

如果某个文件中 `add_knowledge` 调用太多不好逐个改，可以在该文件开头 monkey-patch 一个默认值：
```python
# 不推荐，但紧急时可用
import functools
from src.tools.knowledge_base import add_knowledge as _add_knowledge
add_knowledge = functools.partial(_add_knowledge, caller="self_learning")
```

### 验证
```bash
python -c "
from src.tools.knowledge_base import add_knowledge
# 测试 1: 太短拒绝
r1 = add_knowledge('test', 'lessons', 'short', ['test'], caller='auto')
print(f'短内容: {r1}')  # 应为 None

# 测试 2: auto caller 不允许 high
r2 = add_knowledge('test guardrail', 'lessons', 'x' * 50, ['test'], confidence='high', caller='auto')
print(f'auto+high: confidence 应被降为 medium')

# 测试 3: user_share 允许 high
r3 = add_knowledge('test guardrail ok', 'lessons', 'x' * 50, ['test'], confidence='high', caller='user_share')
print(f'user_share+high: {r3}')  # 应成功
"
```

测试完后删除测试条目。

---

## Phase 3.2 — 评价→规则闭环（Hashimoto 核心）

### 文件：`scripts/feishu_sdk_client.py`

### 改动：修改 `handle_rating` 函数中 C/D 评价的 `_analyze_failure` 内部函数

找到 `handle_rating` 函数中的 `_analyze_failure` 定义（约第 261 行），修改 analysis_prompt 和后续逻辑：

当前代码：
```python
def _analyze_failure():
    try:
        from src.utils.model_gateway import get_model_gateway
        from src.tools.knowledge_base import add_knowledge

        gw = get_model_gateway()
        task_goal = data.get("task_goal", "")
        synthesis = data.get("synthesis_output", "")
        user_feedback = feedback if feedback else f"用户评价{rating}"

        analysis_prompt = (
            f"一个研发任务收到了差评（{rating}）。请分析失败原因并提取教训。\n\n"
            f"## 任务目标\n{task_goal}\n\n"
            f"## Agent 输出（摘要）\n{synthesis[:2000]}\n\n"
            f"## 用户反馈\n{user_feedback}\n\n"
            f"请输出：\n"
            f"1. 失败根因（一句话）\n"
            f"2. Agent 哪个环节出了问题（CPO规划/CTO技术/CMO市场/Critic评审/知识库不足）\n"
            f"3. 下次遇到类似任务应该怎么做\n"
            f"4. 需要补充什么知识\n"
            f"控制在 300 字以内。"
        )

        result = gw.call_azure_openai("cpo", analysis_prompt, "你是质量分析师。", "failure_analysis")

        if result.get("success"):
            add_knowledge(
                title=f"[教训] {task_goal[:40]}（评价{rating}）",
                domain="lessons",
                content=result["response"],
                tags=["evolution", "failure", f"rating_{rating.lower()}"],
                source="user_feedback_analysis",
                confidence="high"
            )
            print(f"[Evolution] 差评分析完成，已写入知识库")
            send_reply(reply_target, f"🔍 已分析任务失败原因并记录为经验教训，下次类似任务会注意。")
    except Exception as e:
        print(f"[Evolution] 差评分析失败: {e}")
```

替换为：
```python
def _analyze_failure():
    try:
        from src.utils.model_gateway import get_model_gateway
        from src.tools.knowledge_base import add_knowledge
        from src.utils.critic_rules import add_critic_rule

        gw = get_model_gateway()
        task_goal = data.get("task_goal", "")
        synthesis = data.get("synthesis_output", "")
        user_feedback = feedback if feedback else f"用户评价{rating}"

        analysis_prompt = (
            f"一个研发任务收到了差评（{rating}）。请分析失败原因并提取教训和检查规则。\n\n"
            f"## 任务目标\n{task_goal}\n\n"
            f"## Agent 输出（摘要）\n{synthesis[:2000]}\n\n"
            f"## 用户反馈\n{user_feedback}\n\n"
            f"请输出两部分：\n\n"
            f"## PART 1: 失败分析（自然语言）\n"
            f"1. 失败根因（一句话）\n"
            f"2. Agent 哪个环节出了问题（CPO规划/CTO技术/CMO市场/Critic评审/知识库不足）\n"
            f"3. 下次遇到类似任务应该怎么做\n"
            f"4. 需要补充什么知识\n"
            f"控制在 300 字以内。\n\n"
            f"## PART 2: 检查规则（JSON 格式，单独一行）\n"
            f"基于这次失败，生成一条 Critic 评审必须检查的规则。\n"
            f"格式：CHECK_RULE_JSON:{{\"check_description\": \"具体描述下次 Critic 应该检查什么\", \"trigger_context\": \"什么类型的任务应该触发这条规则\"}}\n"
            f"规则要具体可执行，不要泛泛的'要更仔细'。\n"
            f"示例：CHECK_RULE_JSON:{{\"check_description\": \"mesh 相关任务必须先分析 Cardo DMC 方案可行性，不能直接跳到放弃 Mesh\", \"trigger_context\": \"mesh 对讲 intercom 通讯\"}}"
        )

        result = gw.call_azure_openai("cpo", analysis_prompt, "你是质量分析师。输出失败分析和一条检查规则。", "failure_analysis")

        if result.get("success"):
            response_text = result["response"]

            # 写入教训（原有逻辑）
            add_knowledge(
                title=f"[教训] {task_goal[:40]}（评价{rating}）",
                domain="lessons",
                content=response_text,
                tags=["evolution", "failure", f"rating_{rating.lower()}"],
                source="user_feedback_analysis",
                confidence="high",
                caller="user_feedback_analysis"
            )
            print(f"[Evolution] 差评分析完成，已写入知识库")

            # === 新增：提取并写入检查规则 ===
            import re
            rule_match = re.search(r'CHECK_RULE_JSON:\s*(\{.*?\})', response_text, re.DOTALL)
            if rule_match:
                try:
                    import json as _json
                    rule_data = _json.loads(rule_match.group(1))
                    rule_path = add_critic_rule(
                        check_description=rule_data.get("check_description", ""),
                        trigger_context=rule_data.get("trigger_context", ""),
                        severity="must_check",
                        source="user_rating_D" if rating == "D" else "user_rating_C",
                        source_task_id=_last_task_memory.get("task_id", "")
                    )
                    if rule_path:
                        print(f"[Evolution] 检查规则已生成: {rule_data.get('check_description', '')[:60]}")
                        send_reply(reply_target, f"📋 已从评价中提取检查规则，Critic 下次会自动检查。")
                    else:
                        print(f"[Evolution] 规则已存在或达上限，跳过")
                except Exception as rule_err:
                    print(f"[Evolution] 规则解析失败: {rule_err}")
            else:
                print(f"[Evolution] LLM 未输出 CHECK_RULE_JSON，跳过规则生成")

            send_reply(reply_target, f"🔍 已分析任务失败原因并记录为经验教训，下次类似任务会注意。")
    except Exception as e:
        print(f"[Evolution] 差评分析失败: {e}")
        import traceback
        print(traceback.format_exc())
```

### 同样改造 A 评价的 `_extract_success`

找到 `_extract_success` 函数（约第 307 行），在成功模式入库后增加规则生成：

在 `add_knowledge(...)` 调用之后，追加：
```python
                        # === 新增：从成功模式提取推荐做法规则 ===
                        try:
                            from src.utils.critic_rules import add_critic_rule
                            # 用 LLM 从成功模式中提取规则
                            rule_prompt = (
                                f"以下是一个成功任务的分析。请提取一条 Critic 评审的推荐做法规则。\n\n"
                                f"## 任务目标\n{task_goal}\n\n"
                                f"## 成功分析\n{result['response'][:1000]}\n\n"
                                f"输出一行 JSON：CHECK_RULE_JSON:{{\"check_description\": \"推荐做法\", \"trigger_context\": \"触发场景\"}}"
                            )
                            rule_result = gw.call_azure_openai("cpo", rule_prompt, "只输出一行 CHECK_RULE_JSON。", "success_rule")
                            if rule_result.get("success"):
                                import re
                                rule_match = re.search(r'CHECK_RULE_JSON:\s*(\{.*?\})', rule_result["response"], re.DOTALL)
                                if rule_match:
                                    import json as _json
                                    rule_data = _json.loads(rule_match.group(1))
                                    add_critic_rule(
                                        check_description=rule_data.get("check_description", ""),
                                        trigger_context=rule_data.get("trigger_context", ""),
                                        severity="should_check",
                                        source="user_rating_A",
                                        source_task_id=_last_task_memory.get("task_id", "")
                                    )
                        except Exception as rule_err:
                            print(f"[Evolution] A评价规则提取失败: {rule_err}")
```

同时给 A 评价的 `add_knowledge` 加 `caller="user_feedback_analysis"`。

### 新增飞书指令："规则库" / "检查规则"

在 `handle_message` 的 text 消息精确指令区（约知识库指令附近），添加：

```python
elif text.strip() in ("规则库", "检查规则", "critic rules", "rules"):
    from src.utils.critic_rules import get_rules_summary
    send_reply(reply_target, get_rules_summary(), reply_type)
```

---

## Phase 3.3 — Post 消息路由补全

### 文件：`scripts/feishu_sdk_client.py`

### 改动：Post 消息的 else 兜底分支（约第 2150-2170 行）

找到 `elif msg_type == "post":` 块的最后一个 `else:` 分支，当前是简化版智能对话。
把这个 else 块替换为和 text 消息一样的完整路由。

最干净的做法是**提取公共函数**：

在 `handle_message` 函数之前，新增：

```python
def _smart_route_and_reply(text: str, open_id: str, chat_id: str, chat_type: str,
                            reply_target: str, reply_type: str):
    """非精确指令的智能路由（text 和 post 消息共用）"""
    from src.utils.conversation_memory import get_conversation_memory
    from src.utils.capability_registry import get_capabilities_for_intent, get_capabilities_summary, CAPABILITIES
    from src.utils.intent_router import classify_intent
    from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt, KB_ROOT

    gateway = get_model_gateway()
    mem = get_conversation_memory()
    session_id = chat_id if chat_type == "group" else open_id

    mem.add_user_message(session_id, text)
    history = mem.get_history_for_prompt(session_id)

    pending_tool = mem.get_context(session_id, "pending_tool")

    if pending_tool:
        intent_result = {
            "intent": "tool_call", "tool": pending_tool,
            "needs_more_input": False, "reasoning": "用户提供了上轮等待的输入"
        }
        mem.clear_context(session_id, "pending_tool")
    else:
        caps_desc = get_capabilities_for_intent()
        intent_result = classify_intent(text, history, caps_desc, gateway)

    intent = intent_result.get("intent", "chat")
    tool = intent_result.get("tool", "none")
    needs_more = intent_result.get("needs_more_input", False)

    log(f"[Intent] {intent}, tool={tool}, needs_more={needs_more}")

    kb_entries = search_knowledge(text, limit=8)
    kb_context = format_knowledge_for_prompt(kb_entries) if kb_entries else ""

    # 知识库强匹配 override
    if kb_entries and intent != "tool_call":
        has_strong_match = any(
            "技术档案" in e.get("title", "") or
            "decision_tree" in str(e.get("tags", [])) or
            "anchor" in str(e.get("tags", [])) or
            "芯片" in e.get("title", "") or
            "AR1" in str(e.get("content", "")) or
            "AR2" in str(e.get("content", ""))
            for e in kb_entries
        )
        if has_strong_match:
            intent = "knowledge_search"
            log(f"[Intent Override] 知识库强匹配，切换到 knowledge_search")

    # === 路由执行（和 text 消息完全相同的逻辑） ===
    # 注意：以下直接复用 handle_message 中 text 消息的各个分支
    # 为避免代码重复太多，这里只处理 chat 和 knowledge_search 两个最常见的 intent
    # tool_call 和 research 在 post 消息中较少触发

    if intent == "tool_call" and tool == "image_generation":
        if needs_more:
            mem.set_context(session_id, "pending_tool", "image_generation")
            reply_text = intent_result.get("what_to_ask", "请发送图片描述（prompt）。")
            send_reply(reply_target, reply_text, reply_type)
            mem.add_bot_message(session_id, reply_text, "ask_input")
        else:
            send_reply(reply_target, "正在生成图片...", reply_type)
            from src.tools.tool_registry import get_tool_registry
            import base64
            img_result = get_tool_registry().call("image_generation", text)
            if img_result.get("success") and img_result.get("image_base64"):
                img_bytes = base64.b64decode(img_result["image_base64"])
                send_image_reply(reply_target, img_bytes, reply_type)
                reply_text = "图片已生成。要调整什么地方吗？"
            else:
                reply_text = f"图片生成失败: {img_result.get('error', '未知')[:200]}"
            send_reply(reply_target, reply_text, reply_type)
            mem.add_bot_message(session_id, reply_text, "image_generation")

    elif intent in ("tool_call", "knowledge_search") and (tool == "knowledge_search" or intent == "knowledge_search"):
        send_reply(reply_target, "正在查阅知识库...", reply_type)

        def _kb_bg():
            try:
                if kb_entries:
                    answer_prompt = (
                        f"基于以下知识库内容回答用户问题。引用具体数据。\n"
                        f"speculative 条目引用时标注'这是推测'。\n\n"
                        f"{kb_context[:4000]}\n\n用户问题：{text}\n\n"
                        f"回复 300-500 字，口语化，像微信聊天。"
                    )
                    answer_result = gateway.call_azure_openai("cpo", answer_prompt,
                        "你是项目合伙人。简洁回答，引用数据。", "kb_answer")
                    reply_text = answer_result.get("response", "") if answer_result.get("success") else "查询失败"
                    if not reply_text:
                        reply_text = f"知识库中暂无「{text[:20]}」相关信息。要深入研究吗？"
                else:
                    reply_text = f"知识库中暂无「{text[:20]}」相关信息。要深入研究吗？"
                    mem.set_context(session_id, "pending_research_topic", text)
                send_reply(reply_target, reply_text, reply_type)
                mem.add_bot_message(session_id, reply_text, "knowledge_search")
            except Exception as e:
                send_reply(reply_target, f"查询出错: {str(e)[:100]}", reply_type)

        threading.Thread(target=_kb_bg, daemon=True).start()

    elif intent == "research":
        if _rd_task_running:
            send_reply(reply_target, "上一个研发任务还在执行中", reply_type)
        else:
            send_reply(reply_target, "检测到研发任务，启动多 Agent 工作流...", reply_type)
            mem.add_bot_message(session_id, "启动研发任务", "research")
            threading.Thread(
                target=_run_rd_task_background,
                args=(text, open_id, reply_target, reply_type),
                daemon=True
            ).start()

    else:
        # chat 兜底
        send_reply(reply_target, "思考中...", reply_type)

        def _chat_bg():
            try:
                caps_summary = get_capabilities_summary()
                chat_prompt = (
                    f"你是智能摩托车全盔项目的 AI 合伙人。\n\n"
                    f"## 对话历史\n{history}\n\n"
                    f"## 我的能力\n{caps_summary}\n\n"
                )
                if kb_context:
                    chat_prompt += f"## 相关知识\n{kb_context[:3000]}\n\n"
                chat_prompt += f"## 用户消息\n{text}\n\n简洁专业地回答，300-500字。"

                result = gateway.call_azure_openai("cpo", chat_prompt,
                    "你是项目合伙人Leo's Agent。回复简洁有力，像面对面说话。", "smart_chat")
                reply_text = result.get("response", "抱歉，我没理解。") if result.get("success") else "服务暂时不可用"
                send_reply(reply_target, reply_text, reply_type)
                mem.add_bot_message(session_id, reply_text, "chat")
            except Exception as e:
                send_reply(reply_target, f"回复出错: {str(e)[:100]}", reply_type)

        threading.Thread(target=_chat_bg, daemon=True).start()
```

然后，把 post 消息的 else 兜底分支从原来的简化版替换为：
```python
else:
    _smart_route_and_reply(text, open_id, chat_id, chat_type, reply_target, reply_type)
```

同时，text 消息的 else 兜底分支（非精确指令→LLM 意图识别）也可以替换为调用同一个函数，
但这个改动面太大，建议先只改 post 的兜底，text 的保持现状（已经能工作），后续再统一。

---

## Phase 3.4 — 飞书热更新

### 文件：`scripts/feishu_sdk_client.py`

### 依赖安装
```bash
pip install watchdog
```

### 改动：在 `main()` 函数中，启动长连接之前，添加热更新线程

找到 `main()` 函数中 `# 启动长连接` 注释之前，添加：

```python
    # 启动热更新文件监听
    try:
        import importlib
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        SAFE_RELOAD_MODULES = {
            "intent_router": "src.utils.intent_router",
            "capability_registry": "src.utils.capability_registry",
            "critic_rules": "src.utils.critic_rules",
            "conversation_memory": "src.utils.conversation_memory",
        }

        class HotReloadHandler(FileSystemEventHandler):
            def __init__(self):
                self._last_reload = {}

            def on_modified(self, event):
                if not event.src_path.endswith(".py"):
                    return
                module_stem = Path(event.src_path).stem
                if module_stem not in SAFE_RELOAD_MODULES:
                    return

                # 防抖：同一文件 2 秒内不重复 reload
                import time as _time
                now = _time.time()
                last = self._last_reload.get(module_stem, 0)
                if now - last < 2:
                    return
                self._last_reload[module_stem] = now

                full_module = SAFE_RELOAD_MODULES[module_stem]
                try:
                    if full_module in sys.modules:
                        importlib.reload(sys.modules[full_module])
                        log(f"[HotReload] ✅ {module_stem} 已热更新")
                    else:
                        log(f"[HotReload] {module_stem} 未加载，跳过")
                except Exception as e:
                    log(f"[HotReload] ❌ {module_stem} 热更新失败: {e}")

        watch_path = str(Path(__file__).parent.parent / "src" / "utils")
        observer = Observer()
        observer.schedule(HotReloadHandler(), watch_path, recursive=False)
        observer.daemon = True
        observer.start()
        print(f"[HotReload] 文件监听已启动: {watch_path}")
        print(f"[HotReload] 安全模块: {list(SAFE_RELOAD_MODULES.keys())}")
    except ImportError:
        print("[HotReload] watchdog 未安装，跳过热更新 (pip install watchdog)")
    except Exception as e:
        print(f"[HotReload] 启动失败: {e}")
```

### 验证
启动飞书服务后，修改 `src/utils/intent_router.py`（比如加一行注释），观察终端：
```
[HotReload] ✅ intent_router 已热更新
```

---

## Phase 4.1 — LangGraph Checkpoint 持久化

### 依赖安装
```bash
pip install langgraph-checkpoint-sqlite
```

如果上面的包不存在（langgraph 版本差异），尝试：
```bash
pip install langgraph[sqlite]
```

### 文件：`src/graph/router.py`

### 改动 1：在文件顶部 import 区域添加

```python
# Checkpoint 持久化
try:
    from langgraph.checkpoint.sqlite import SqliteSaver
    _checkpoint_db = ROOT_DIR / ".ai-state" / "langgraph_checkpoints.db"
    _checkpoint_db.parent.mkdir(parents=True, exist_ok=True)
    _checkpointer = SqliteSaver.from_conn_string(str(_checkpoint_db))
    HAS_CHECKPOINT = True
    print(f"[Checkpoint] SQLite 持久化已启用: {_checkpoint_db}")
except ImportError:
    _checkpointer = None
    HAS_CHECKPOINT = False
    print("[Checkpoint] langgraph-checkpoint-sqlite 未安装，checkpoint 禁用")
except Exception as e:
    _checkpointer = None
    HAS_CHECKPOINT = False
    print(f"[Checkpoint] 初始化失败: {e}，checkpoint 禁用")
```

### 改动 2：修改最后的 compile 调用

找到文件最后的 `app = workflow.compile()`（约第 1086 行），改为：

```python
if HAS_CHECKPOINT and _checkpointer:
    app = workflow.compile(checkpointer=_checkpointer)
    print("[LangGraph] 编译完成（带 checkpoint）")
else:
    app = workflow.compile()
    print("[LangGraph] 编译完成（无 checkpoint）")
```

### 文件：`scripts/feishu_sdk_client.py`

### 改动：`call_langgraph` 函数中 invoke/stream 调用传入 config

找到 `call_langgraph` 函数，在 `initial_state` 定义之后、调用 stream/invoke 之前，添加：

```python
    # Checkpoint config：用 task_id 作为 thread_id，支持断点续传
    checkpoint_config = {"configurable": {"thread_id": task_id}}
```

然后修改 stream 和 invoke 调用：
```python
        try:
            result = _stream_langgraph(langgraph_app, initial_state, reply_target, reply_type,
                                        config=checkpoint_config)
        except Exception as stream_err:
            print(f"[LangGraph] stream 模式失败，fallback invoke: {stream_err}")
            result = langgraph_app.invoke(initial_state, config=checkpoint_config)
```

同时修改 `_stream_langgraph` 签名：
```python
def _stream_langgraph(app, initial_state: dict, reply_target: str = None,
                       reply_type: str = None, config: dict = None) -> dict:
    ...
    for event in app.stream(initial_state, stream_mode="updates", config=config):
        ...
```

### 验证
```bash
python -c "
from src.graph.router import app, HAS_CHECKPOINT
print(f'Checkpoint enabled: {HAS_CHECKPOINT}')
print(f'App checkpointer: {app.checkpointer is not None if hasattr(app, \"checkpointer\") else \"N/A\"}')
"
```

---

## Phase 4.2 — 飞书恢复任务指令

### 文件：`scripts/feishu_sdk_client.py`

### 改动：在 handle_message 的 text 精确指令区添加

```python
elif text.strip() in ("恢复任务", "resume", "恢复"):
    try:
        from src.graph.router import HAS_CHECKPOINT, _checkpoint_db
        if not HAS_CHECKPOINT:
            send_reply(reply_target, "断点续传未启用（缺少 langgraph-checkpoint-sqlite）", reply_type)
        else:
            import sqlite3
            conn = sqlite3.connect(str(_checkpoint_db))
            cursor = conn.execute(
                "SELECT DISTINCT thread_id FROM checkpoints ORDER BY created_at DESC LIMIT 5"
            )
            threads = [row[0] for row in cursor.fetchall()]
            conn.close()

            if not threads:
                send_reply(reply_target, "没有可恢复的任务", reply_type)
            else:
                lines = ["📋 最近的任务 checkpoint：\n"]
                for i, tid in enumerate(threads, 1):
                    lines.append(f"  {i}. {tid}")
                lines.append(f"\n发送「恢复 task_xxx」恢复指定任务")
                send_reply(reply_target, "\n".join(lines), reply_type)
    except Exception as e:
        send_reply(reply_target, f"检查 checkpoint 失败: {e}", reply_type)

elif text.strip().startswith("恢复 task_") or text.strip().startswith("resume task_"):
    task_id = text.strip().split()[-1]
    try:
        from src.graph.router import app as langgraph_app, HAS_CHECKPOINT
        if not HAS_CHECKPOINT:
            send_reply(reply_target, "断点续传未启用", reply_type)
        else:
            send_reply(reply_target, f"🔄 正在恢复任务 {task_id}...", reply_type)

            def _resume_bg():
                global _rd_task_running
                _rd_task_running = True
                try:
                    config = {"configurable": {"thread_id": task_id}}
                    result = langgraph_app.invoke(None, config=config)

                    if result:
                        execution = result.get("execution", {})
                        synthesis = execution.get("synthesis_output", "")
                        if synthesis:
                            send_reply(reply_target, f"✅ 任务 {task_id} 恢复完成\n\n{synthesis[:3000]}", reply_type)
                        else:
                            send_reply(reply_target, f"✅ 任务 {task_id} 恢复完成，但无输出", reply_type)
                    else:
                        send_reply(reply_target, f"任务 {task_id} 恢复失败：无结果", reply_type)
                except Exception as e:
                    send_reply(reply_target, f"❌ 恢复失败: {str(e)[:300]}", reply_type)
                finally:
                    _rd_task_running = False

            threading.Thread(target=_resume_bg, daemon=True).start()
    except Exception as e:
        send_reply(reply_target, f"恢复失败: {e}", reply_type)
```

---

## 最终验证清单

完成所有改动后，逐项验证：

```bash
# 1. knowledge_base guardrail
python -c "
from src.tools.knowledge_base import add_knowledge
r = add_knowledge('test', 'lessons', 'short', ['test'], caller='auto')
print(f'短内容拒绝: {r is None}')
"

# 2. critic_rules import
python -c "from src.utils.critic_rules import add_critic_rule, get_rules_summary; print('OK')"

# 3. router checkpoint
python -c "from src.graph.router import app, HAS_CHECKPOINT; print(f'Checkpoint: {HAS_CHECKPOINT}')"

# 4. feishu_sdk_client import（验证没有语法错误）
python -c "from scripts.feishu_sdk_client import handle_message; print('OK')"

# 5. watchdog 安装
python -c "from watchdog.observers import Observer; print('watchdog OK')"
```

全部 OK 后重启飞书服务测试。
