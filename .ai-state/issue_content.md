## 诊断文件汇总

### 1. scripts/feishu_sdk_client_v2.py - 消息处理入口 (USE_AGENT_MODE 判断部分)

```python
# Lines 56-155

def handle_message(event):
    """处理收到的消息 - v2 模块化版本"""
    try:
        print(f"\n{'='*50}")
        print(f"收到消息!")

        message = event.event.message
        sender = event.event.sender

        # 获取基础信息
        msg_id = message.message_id
        msg_type = message.message_type
        chat_id = message.chat_id

        # 消息去重
        if msg_id in _processed_msgs:
            print(f"[Skip] 重复消息: {msg_id}")
            return
        _processed_msgs.add(msg_id)
        if len(_processed_msgs) > _MAX_MSG_CACHE:
            _processed_msgs.clear()

        # 过滤机器人自己的消息
        sender_type = getattr(sender, 'sender_type', '')
        if sender_type == 'app':
            print(f"[Skip] 机器人自己的消息")
            return

        open_id = sender.sender_id.open_id if sender.sender_id else ""
        content = json.loads(message.content) if message.content else {}

        print(f"  msg_type={msg_type}, content_len={len(str(content))}")
        print(f"  Open ID: {open_id}")
        print(f"  Chat ID: {chat_id}")

        # 判断群聊/私聊
        chat_type = message.chat_type if hasattr(message, 'chat_type') else ""
        is_group = chat_type == "group"

        # 群聊需要 @机器人
        if is_group:
            mentions = message.mentions if hasattr(message, 'mentions') else []
            is_mentioned = bool(mentions)
            if not is_mentioned:
                return
            print(f"  [群聊] 检测到 @")

        # 确定回复目标
        reply_target = chat_id if is_group else open_id
        reply_type = "chat_id" if is_group else "open_id"

        # 设置回复上下文
        set_reply_context(reply_target, reply_type)

        # 获取 session_id（用于对话记忆）
        session_id = get_session_id(open_id, chat_id)

        # === 按消息类型分发 ===
        if msg_type == "text":
            text = content.get("text", "")

            # 群聊清理 @mention
            if is_group and hasattr(message, 'mentions') and message.mentions:
                for mention in message.mentions:
                    if hasattr(mention, 'key'):
                        text = text.replace(mention.key, "").strip()
                # 额外清理 @xxx 格式
                text = __import__('re').sub(r'@[^\s]+\s*', '', text).strip()

            print(f"  消息类型: text, 内容: {text[:50]}...")

            # === v2.1: 使用 Agent 模式（飞书 → Claude Code CLI）===
            print(f"  [DEBUG] USE_AGENT_MODE={USE_AGENT_MODE}")
            if USE_AGENT_MODE:
                try:
                    from scripts.agent import handle_message as agent_handle_message
                    print(f"  [Agent模式] 调用 agent.handle_message(text, chat_id={chat_id}, open_id={open_id})")
                    agent_handle_message(text, chat_id, open_id)
                    print(f"  [Agent模式] agent.handle_message 返回")
                except Exception as e:
                    import traceback
                    print(f"  [Agent模式失败] {e}")
                    traceback.print_exc()
                    print(f"  [降级] 使用旧路由器")
                    route_text_message(...)
            else:
                # 旧路由器
                print(f"  [旧路由器] USE_AGENT_MODE=False")
                route_text_message(...)
```

---

### 2. .git/hooks/post-commit

```bash
#!/bin/bash
# Git post-commit hook: 重启 SDK + 验证

echo "=========================================="
echo "Post-commit: 重启 SDK 并验证"
echo "=========================================="

cd "$(git rev-parse --show-toplevel)"
STATUS_FILE=".ai-state/system_status.md"
LEO_OPEN_ID="ou_8e5e4f183e9eca4241378e96bac3a751"

# 1. 更新 system_status.md
echo "[1/4] 更新系统状态..."
# ...

# 2. 重启 SDK
echo "[2/4] 重启 SDK..."
cmd //c scripts\\stop_sdk.bat 2>/dev/null
sleep 2
cmd //c scripts\\start_sdk.bat 2>/dev/null

# 3. 验证
echo "[3/4] 运行验证..."
python scripts/auto_restart_and_verify.py --verify-only --no-push 2>/dev/null

# 4. 发飞书通知
echo "[4/4] 发送飞书通知..."
lark-cli im +messages-send --receive-id "$LEO_OPEN_ID" --receive-type "open_id" --msg-type "text" --content "{\"text\":\"✅ Post-commit 完成\"}" --as bot

echo "Post-commit 完成"
```

---

### 3. scripts/start_sdk.bat

```batch
@echo off
chcp 65001 >nul 2>&1
cd /d D:\Users\uih00653\my_agent_company\pythonProject1

set PID_FILE=.ai-state\sdk.pid
set LOG_FILE=.ai-state\feishu_sdk.log

echo 启动 SDK...

REM 停止旧进程
if exist "%PID_FILE%" (
    set /p OLD_PID=<"%PID_FILE%"
    taskkill /PID %OLD_PID% /F >nul 2>&1
)

REM 清空日志
echo [%date% %time%] SDK 启动中... > "%LOG_FILE%"

REM 启动后台进程
start /B "" ".venv\Scripts\pythonw.exe" "scripts\feishu_sdk_client_v2.py" >> "%LOG_FILE%" 2>&1

echo 完成
```

---

### 4. scripts/start_sdk.vbs

```vbs
Set ws = CreateObject("WScript.Shell")
ws.CurrentDirectory = "D:\Users\uih00653\my_agent_company\pythonProject1"
ws.Run "cmd /c .venv\Scripts\pythonw.exe scripts\feishu_sdk_client_v2.py >> .ai-state\feishu_sdk.log 2>&1", 0, False
```

---

### 5. scripts/auto_learn.py - _load_covered_topics() 和 _find_kb_gaps()

详见代码文件，核心逻辑：
- `_load_covered_topics()`: 加载已覆盖搜索词，7天过期
- `_find_kb_gaps()`: 从决策树 + 任务池 + 域分布 + 时效性 + 产品锚点获取缺口

---

### 6. .ai-state/competitor_monitor_config.json

6 层监控配置：
- direct_competitors: Shoei Smart, 洛克兄弟, MOTOEYE, EyeLights, iC-R, Sena, Cardo
- tech_supply_chain: JBD, Sony ECX, 京东方, FreeForm, 光波导
- riding_ecosystem: 摩托车市场, 摩旅用户, 政策
- adjacent_tech: 汽车HUD, 车载语音, 端侧AI, Mesh通讯
- regulations: ECE 22.06, GB 811, HUD合法性
- cross_reference: 滑雪头盔, 自行车头盔, Bosch两轮

---

### 7. .ai-state/research_task_pool.yaml

12 个研究任务，其中 2 个已完成，10 个待执行。

---

### 8. .ai-state/product_decision_tree.yaml

9 个决策项：
- v1_display (open, priority 1): OLED vs MicroLED
- v1_soc (decided): Qualcomm AR1 Gen 1
- v1_intercom (open, priority 1): Mesh 自研 vs Cardo DMC
- v1_audio (open, priority 2): 骨传导 vs 动圈
- ... 更多

---

### 9. 最新 50 行日志

```
[Lark] [2026-04-09 08:49:59] [INFO] connected to wss://msg-frontier.feishu.cn/ws/v2
[Lark] [2026-04-09 08:49:59] [DEBUG] ping success
[Lark] [2026-04-09 08:49:59] [DEBUG] receive pong
... (心跳正常，无错误)
```

---

### 10. roundtable_runs/HUDDemo生成_20260408_154038/

```
convergence_trace.jsonl
crystal_context_summary.md
generator_input_actual.md
input_task_spec.json
phase2_proposal_full.md
phase4_critic_final.md
```

---

*由 Claude Code 自动生成*