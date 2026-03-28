# feishu_sdk_client.py 拆分重构 — 另起炉灶 + 自动验证 + 一键切换

> **原则**：不碰原文件，全部新写，自动测试，一键切换
> **原文件**：scripts/feishu_sdk_client.py（3195 行，保持运行不动）
> **新入口**：scripts/feishu_sdk_client_v2.py（~200 行）
> **新模块**：scripts/feishu_handlers/（7 个模块）
> **测试**：scripts/test_feishu_v2.py（自动验证所有模块）

---

## 执行步骤

### Step 0：理解原文件结构

先分析原文件，搞清楚每个函数在哪里、被谁调用：

```bash
# 列出所有函数定义和行号
python -c "
lines = open('scripts/feishu_sdk_client.py', encoding='utf-8').readlines()
for i, line in enumerate(lines, 1):
    if line.strip().startswith('def ') or line.strip().startswith('async def '):
        print(f'{i}: {line.strip()[:80]}')
" > /tmp/feishu_functions.txt
cat /tmp/feishu_functions.txt

# 列出所有全局变量和 import
python -c "
lines = open('scripts/feishu_sdk_client.py', encoding='utf-8').readlines()
for i, line in enumerate(lines, 1):
    stripped = line.strip()
    if i <= 80 or (not stripped.startswith('#') and not stripped.startswith('def ') 
        and '=' in stripped and not stripped.startswith('if ') 
        and not stripped.startswith('elif ') and not stripped.startswith('for ')
        and not stripped.startswith('return ') and not stripped.startswith('print')
        and len(stripped) > 5 and i < 100):
        print(f'{i}: {line.rstrip()[:80]}')
" | head -50

# 列出所有 send_reply 的调用方式
grep -n "send_reply\|reply_target\|reply_type" scripts/feishu_sdk_client.py | head -30

# 列出所有 import
grep -n "^import\|^from" scripts/feishu_sdk_client.py | head -40
```

基于分析结果，按以下结构拆分。注意：原文件中的函数签名、变量名、调用方式必须完全保持一致。

---

### Step 1：创建 scripts/feishu_handlers/chat_helpers.py

这是所有其他模块的基础依赖——send_reply、日志、session_id 等通用工具。

从原文件中找到以下函数并复制到新文件：

```python
"""
@description: 飞书消息通用工具 - send_reply、日志、session 管理
@refactored_from: feishu_sdk_client.py
"""
import os
import sys
import json
import time
import re
from pathlib import Path
from datetime import datetime

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(str(PROJECT_ROOT / ".env"))

# === 从原文件中复制以下内容 ===

# 1. 日志相关
#    找到原文件中的 log() 函数、_LOG_FILE 变量
#    grep -n "def log\|_LOG_FILE\|日志" scripts/feishu_sdk_client.py

# 2. send_reply() 函数
#    这是最核心的函数，所有模块都依赖它
#    grep -n "def send_reply" scripts/feishu_sdk_client.py
#    完整复制该函数及其依赖（如 lark 的 reply/send 调用）

# 3. session_id / reply_target 提取
#    grep -n "def.*session\|get_session\|session_id" scripts/feishu_sdk_client.py

# 4. 对话记忆相关
#    grep -n "conversation_memory\|mem\." scripts/feishu_sdk_client.py | head -20
#    如果对话记忆是独立模块（src/utils/conversation_memory.py），只需要 import

# 5. 全局变量（如 APP_ID、lark client 等）
#    grep -n "APP_ID\|APP_SECRET\|lark_client\|wsClient\|cli" scripts/feishu_sdk_client.py | head -20

# 注意：send_reply 可能依赖 lark client 实例。
# 方案 A：在 chat_helpers 中创建 lark client（如果原文件在模块级创建）
# 方案 B：send_reply 接受 client 参数，由调用方传入
# 推荐方案 A（和原文件行为一致）

# === 导出接口 ===
# 确保以下函数/变量可以被其他模块 import：
# - send_reply(target, text, reply_type="chat_id")
# - log(msg)
# - get_session_id(open_id, chat_id)
# - APP_ID, APP_SECRET（如果其他模块需要）
# - lark client 实例（如果其他模块需要直接调用 lark API）
```

---

### Step 2：创建 scripts/feishu_handlers/file_sender.py

文件上传和发送到飞书。structured_doc.py 中已经有一份 _send_file_to_feishu，可以复用或统一。

```python
"""
@description: 飞书文件上传与发送
@refactored_from: feishu_sdk_client.py + structured_doc.py
"""
import requests
from pathlib import Path
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def send_file_to_feishu(target_id, file_path, id_type="chat_id"):
    """用 requests 直接调飞书 HTTP API 发送文件"""
    # 从 structured_doc.py 的 _send_file_to_feishu 复制完整实现
    # 或从原文件中找到文件发送逻辑
    # grep -n "def.*send.*file\|upload.*file\|file_key" scripts/feishu_sdk_client.py
    # grep -n "def _send_file_to_feishu" scripts/feishu_handlers/structured_doc.py
    
    # 统一为一份实现，structured_doc.py 中的 _send_file_to_feishu 改为 import 这个
    pass


def send_image_to_feishu(target_id, image_path, id_type="chat_id"):
    """发送图片到飞书"""
    # 如果原文件有图片发送逻辑，复制过来
    # grep -n "image_key\|send.*image\|upload.*image" scripts/feishu_sdk_client.py
    pass
```

---

### Step 3：创建 scripts/feishu_handlers/commands.py

所有精确指令处理：评价（A/B/C/D）、设置目标、进化记录、审批、触发学习等。

```python
"""
@description: 飞书精确指令处理 - 评价/目标/进化/审批/学习触发
@refactored_from: feishu_sdk_client.py
"""
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 从原文件中找到所有精确指令处理：
# grep -n "精确指令\|评价\|设置目标\|进化\|审批\|触发学习\|评分\|打分\|rating" scripts/feishu_sdk_client.py | head -30
# grep -n "'A'\|'B'\|'C'\|'D'\|评价指令\|handle.*rating\|handle.*eval" scripts/feishu_sdk_client.py | head -20
# grep -n "进化记录\|evolution\|experience_card" scripts/feishu_sdk_client.py | head -20

def handle_command(text, reply_target, reply_type, open_id, chat_id, send_reply):
    """
    处理精确指令。返回 True 表示已处理，False 表示不是精确指令。
    
    支持的指令：
    - A/B/C/D 评价
    - 设置目标 XXX
    - 进化记录
    - 审批 XXX
    - 触发学习
    - 知识库统计
    - 系统状态
    - 等等
    """
    text_stripped = text.strip()
    
    # === 评价处理 ===
    # 从原文件复制评价检测和处理逻辑
    # 注意：之前有个 bug 是"AR1和AR2"被当成 A 评价，已修复为精确匹配单字母
    
    # === 设置目标 ===
    # grep -n "设置目标\|product_goal" scripts/feishu_sdk_client.py
    
    # === 进化记录 ===
    # grep -n "进化记录\|evolution" scripts/feishu_sdk_client.py
    
    # === 审批 ===
    # grep -n "审批\|approve\|reject" scripts/feishu_sdk_client.py
    
    # === 触发学习 ===
    # grep -n "触发学习\|start.*learn\|learning" scripts/feishu_sdk_client.py
    
    # === 知识库统计 ===
    # grep -n "知识库统计\|kb.*stat\|knowledge.*stat" scripts/feishu_sdk_client.py
    
    # 不是精确指令
    return False
```

---

### Step 4：创建 scripts/feishu_handlers/image_handler.py

图片消息和语音消息处理。

```python
"""
@description: 飞书图片/语音/文件消息处理
@refactored_from: feishu_sdk_client.py
"""
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 从原文件找到图片处理逻辑：
# grep -n "def.*image\|def.*handle.*photo\|def.*handle.*voice\|msg_type.*image\|msg_type.*audio" scripts/feishu_sdk_client.py | head -20
# grep -n "ocr\|transcrib\|语音转文字\|图片描述" scripts/feishu_sdk_client.py | head -20

def handle_image_message(event, send_reply):
    """处理图片消息"""
    # 从原文件复制图片处理逻辑
    # 包括：下载图片 → OCR/描述 → 入知识库（可选）
    pass


def handle_audio_message(event, send_reply):
    """处理语音消息"""
    # 从原文件复制语音处理逻辑
    # 包括：语音转文字 → 当作文本处理
    pass


def handle_file_message(event, send_reply):
    """处理文件消息（用户发送的文件）"""
    # 如果原文件有处理用户上传文件的逻辑
    pass
```

---

### Step 5：创建 scripts/feishu_handlers/rd_task.py

研发任务（LangGraph 多 Agent 调用）。这是最复杂的模块。

```python
"""
@description: 研发任务处理 - LangGraph 多 Agent 调用 + 后台线程
@refactored_from: feishu_sdk_client.py
"""
import threading
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 从原文件找到研发任务相关逻辑：
# grep -n "def is_rd_task\|def.*rd_task\|def.*langgraph\|def.*research\|_rd_lock\|rd_task_running" scripts/feishu_sdk_client.py | head -20
# grep -n "LangGraph\|run_graph\|invoke_graph\|graph\." scripts/feishu_sdk_client.py | head -20
# grep -n "_last_rd\|experience_card\|经验卡片" scripts/feishu_sdk_client.py | head -20

# 并发锁（从原文件复制）
_rd_lock = threading.Lock()
_rd_task_running = False

def is_rd_task(text: str) -> bool:
    """判断是否为需要多Agent协作的研发任务"""
    # 从原文件复制 is_rd_task 函数
    # grep -n "def is_rd_task" scripts/feishu_sdk_client.py
    pass


def run_rd_task_background(text, reply_target, reply_type, open_id, chat_id, send_reply):
    """后台线程执行研发任务"""
    # 从原文件复制后台研发任务逻辑
    # 包括：
    # 1. 检查并发锁
    # 2. 启动后台线程
    # 3. 调用 LangGraph
    # 4. 发送结果（_send_rd_result）
    # 5. 保存经验卡片
    
    # grep -n "def.*background\|def.*_run_rd\|threading.Thread" scripts/feishu_sdk_client.py | head -10
    pass


def _send_rd_result(text, result, reply_target, reply_type, send_reply):
    """发送研发任务结果"""
    # 从原文件复制
    # grep -n "def.*_send_rd_result\|def.*send.*result" scripts/feishu_sdk_client.py
    pass
```

---

### Step 6：创建 scripts/feishu_handlers/text_router.py

文本消息路由主逻辑——这是核心，把消息分发到各个处理器。

```python
"""
@description: 文本消息路由 - 精确指令 → 快速通道 → 意图识别 → R&D → 智能对话
@refactored_from: feishu_sdk_client.py
"""
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.feishu_handlers.commands import handle_command
from scripts.feishu_handlers.structured_doc import try_structured_doc_fast_track
from scripts.feishu_handlers.rd_task import is_rd_task, run_rd_task_background

# 从原文件找到文本路由主逻辑：
# grep -n "def.*handle_text\|def.*route_text\|text 路由\|msg_type.*text" scripts/feishu_sdk_client.py | head -20
# grep -n "意图识别\|intent\|_has_shareable_url\|is_article" scripts/feishu_sdk_client.py | head -20

def route_text_message(text, reply_target, reply_type, open_id, chat_id, 
                        send_reply, session_id=None, mem=None):
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
    
    # === 1. 精确指令 ===
    if handle_command(text, reply_target, reply_type, open_id, chat_id, send_reply):
        return
    
    # === 2. 结构化文档快速通道 ===
    if try_structured_doc_fast_track(text, reply_target, reply_type, open_id, chat_id, send_reply):
        return
    
    # === 3. URL 分享处理 ===
    # 从原文件复制 _has_shareable_url 逻辑
    # grep -n "_has_shareable_url\|分享.*url\|http" scripts/feishu_sdk_client.py
    
    # === 4. 长文章导入 ===
    # 从原文件复制 is_article_import 逻辑
    # grep -n "is_article\|长文章\|导入知识库\|import.*article" scripts/feishu_sdk_client.py
    
    # === 5. 研发任务 ===
    if is_rd_task(text):
        run_rd_task_background(text, reply_target, reply_type, open_id, chat_id, send_reply)
        return
    
    # === 6. 意图识别 ===
    # 从原文件复制意图识别逻辑
    # grep -n "intent_router\|意图\|IntentRouter" scripts/feishu_sdk_client.py
    
    # === 7. 兜底：智能对话 ===
    # 从原文件复制智能对话逻辑
    # grep -n "def.*smart_chat\|def.*chat_with_kb\|非研发任务\|智能对话" scripts/feishu_sdk_client.py
    pass
```

---

### Step 7：创建 scripts/feishu_sdk_client_v2.py

新入口文件，只做启动和消息分发。

```python
"""
@description: 飞书长连接客户端 v2 - 模块化重构版
@dependencies: lark-oapi, scripts/feishu_handlers/*
@last_modified: 2026-03-28

使用方法：
    python scripts/feishu_sdk_client_v2.py
"""
import os
import sys
import json
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

# 强制刷新日志
try:
    sys.stdout.reconfigure(line_buffering=True)
except:
    import functools
    print = functools.partial(print, flush=True)

# === lark SDK 初始化 ===
try:
    import lark_oapi as lark
except ImportError:
    print("请安装: pip install lark-oapi")
    sys.exit(1)

# === 导入各模块 ===
from scripts.feishu_handlers.chat_helpers import send_reply, log, get_session_id
from scripts.feishu_handlers.text_router import route_text_message
from scripts.feishu_handlers.image_handler import handle_image_message, handle_audio_message, handle_file_message

# === 配置 ===
APP_ID = os.getenv("FEISHU_APP_ID", "")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

# === 消息去重 ===
_processed_msgs = set()
_MAX_MSG_CACHE = 500

# === 消息处理主入口 ===
def handle_message(event):
    """处理收到的消息 - v2 模块化版本"""
    try:
        print(f"\n{'='*50}")
        print(f"收到消息!")
        
        message = event.event.message
        sender = event.event.sender
        
        # 获取基础信息
        msg_id = message.message_id
        msg_type = message.msg_type
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
            print("[Skip] 机器人自己的消息")
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
        
        # 获取 session_id（用于对话记忆）
        session_id = get_session_id(open_id, chat_id)
        
        # === 按消息类型分发 ===
        if msg_type == "text":
            text = content.get("text", "")
            
            # 群聊清理 @mention
            if is_group and mentions:
                for mention in mentions:
                    if hasattr(mention, 'key'):
                        text = text.replace(mention.key, "").strip()
            
            print(f"  消息类型: text, 内容: {text[:50]}...")
            
            # 交给文本路由器
            route_text_message(
                text=text,
                reply_target=reply_target,
                reply_type=reply_type,
                open_id=open_id,
                chat_id=chat_id,
                send_reply=send_reply,
                session_id=session_id
            )
            
        elif msg_type == "image":
            print(f"  消息类型: image")
            handle_image_message(event, send_reply)
            
        elif msg_type == "audio":
            print(f"  消息类型: audio")
            handle_audio_message(event, send_reply)
            
        elif msg_type == "file":
            print(f"  消息类型: file")
            handle_file_message(event, send_reply)
            
        else:
            print(f"  未支持的消息类型: {msg_type}")
            
    except Exception as e:
        print(f"[Error] handle_message: {e}")
        import traceback
        traceback.print_exc()


# === 启动服务 ===
def main():
    """启动飞书长连接客户端"""
    print(f"{'#'*60}")
    print(f"# 飞书长连接客户端 v2 启动")
    print(f"# APP_ID: {APP_ID[:10]}...")
    print(f"# 模块化架构")
    print(f"{'#'*60}")
    
    # 注册消息处理器
    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(handle_message) \
        .build()
    
    # 创建长连接客户端
    # 注意：原文件中可能用的是 ws 客户端，复制相同的连接方式
    # grep -n "wsClient\|ws_client\|WebSocket\|long_conn\|cli\." scripts/feishu_sdk_client.py | head -10
    
    cli = lark.ws.Client(
        APP_ID,
        APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.DEBUG
    )
    
    print("服务启动，等待消息...")
    cli.start()


if __name__ == "__main__":
    main()
```

---

### Step 8：创建 scripts/test_feishu_v2.py

自动化测试脚本，验证所有模块。

```python
"""
@description: feishu_sdk_client_v2 模块化重构验证测试
"""
import sys
import importlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def run_tests():
    print("=" * 60)
    print("feishu_sdk_client_v2 模块化验证")
    print("=" * 60)
    
    passed = 0
    failed = 0
    errors = []
    
    # === 模块导入测试 ===
    module_tests = [
        ("scripts.feishu_handlers.chat_helpers", 
         ["send_reply", "log"]),
        
        ("scripts.feishu_handlers.file_sender", 
         ["send_file_to_feishu"]),
        
        ("scripts.feishu_handlers.commands", 
         ["handle_command"]),
        
        ("scripts.feishu_handlers.image_handler", 
         ["handle_image_message", "handle_audio_message"]),
        
        ("scripts.feishu_handlers.rd_task", 
         ["is_rd_task", "run_rd_task_background"]),
        
        ("scripts.feishu_handlers.text_router", 
         ["route_text_message"]),
        
        ("scripts.feishu_handlers.structured_doc", 
         ["try_structured_doc_fast_track"]),
    ]
    
    for module_path, functions in module_tests:
        try:
            mod = importlib.import_module(module_path)
            missing = [f for f in functions if not hasattr(mod, f)]
            if missing:
                errors.append(f"❌ {module_path}: 缺少函数 {missing}")
                failed += 1
            else:
                print(f"  ✅ {module_path}: {len(functions)} 个函数")
                passed += 1
        except Exception as e:
            errors.append(f"❌ {module_path}: 导入失败 - {e}")
            failed += 1
    
    # === 入口文件测试 ===
    try:
        from scripts.feishu_sdk_client_v2 import handle_message, main
        print(f"  ✅ feishu_sdk_client_v2: handle_message + main")
        passed += 1
    except Exception as e:
        errors.append(f"❌ feishu_sdk_client_v2: {e}")
        failed += 1
    
    # === 功能逻辑测试 ===
    print(f"\n--- 功能逻辑测试 ---")
    
    # 测试 is_rd_task
    try:
        from scripts.feishu_handlers.rd_task import is_rd_task
        assert is_rd_task("请研究一下HUD芯片方案") == True, "长文本应该是研发任务"
        assert is_rd_task("你好") == False, "短文本不应该是研发任务"
        print(f"  ✅ is_rd_task: 逻辑正确")
        passed += 1
    except Exception as e:
        errors.append(f"❌ is_rd_task: {e}")
        failed += 1
    
    # 测试 handle_command 不拦截普通消息
    try:
        from scripts.feishu_handlers.commands import handle_command
        # 用一个 mock send_reply
        called = []
        def mock_reply(target, text, rtype="chat_id"):
            called.append(text)
        
        result = handle_command("你好，帮我查下天气", "test", "chat_id", "ou_test", "oc_test", mock_reply)
        assert result == False, "普通消息不应该被精确指令拦截"
        print(f"  ✅ handle_command: 不拦截普通消息")
        passed += 1
    except Exception as e:
        errors.append(f"❌ handle_command: {e}")
        failed += 1
    
    # 测试 structured_doc 关键词检测
    try:
        from scripts.feishu_handlers.structured_doc import try_structured_doc_fast_track
        # 不实际执行，只验证函数存在且可调用
        print(f"  ✅ structured_doc: try_structured_doc_fast_track 可调用")
        passed += 1
    except Exception as e:
        errors.append(f"❌ structured_doc: {e}")
        failed += 1
    
    # === 交叉依赖测试 ===
    print(f"\n--- 交叉依赖测试 ---")
    
    # text_router 能调用 commands
    try:
        from scripts.feishu_handlers import text_router
        assert hasattr(text_router, 'route_text_message')
        # 确认内部 import 不报错
        print(f"  ✅ text_router → commands: 依赖正常")
        passed += 1
    except Exception as e:
        errors.append(f"❌ text_router → commands: {e}")
        failed += 1
    
    # === 原文件对比测试 ===
    print(f"\n--- 原文件完整性对比 ---")
    
    try:
        # 确认原文件中的关键函数在新模块中都有对应
        old_lines = open('scripts/feishu_sdk_client.py', encoding='utf-8').readlines()
        old_functions = set()
        for line in old_lines:
            if line.strip().startswith('def '):
                func_name = line.strip().split('(')[0].replace('def ', '')
                old_functions.add(func_name)
        
        # 检查关键函数是否在新模块中存在
        critical_functions = {
            'send_reply': 'chat_helpers',
            'is_rd_task': 'rd_task',
            'handle_message': 'feishu_sdk_client_v2（入口）',
        }
        
        for func, expected_module in critical_functions.items():
            found = False
            for mod_path, _ in module_tests:
                try:
                    mod = importlib.import_module(mod_path)
                    if hasattr(mod, func):
                        found = True
                        break
                except:
                    continue
            
            if not found:
                try:
                    from scripts import feishu_sdk_client_v2
                    if hasattr(feishu_sdk_client_v2, func):
                        found = True
                except:
                    pass
            
            if found:
                print(f"  ✅ {func} → {expected_module}")
            else:
                errors.append(f"  ❌ {func} 在新模块中未找到（应在 {expected_module}）")
                failed += 1
        
        print(f"\n  原文件函数数: {len(old_functions)}")
        passed += 1
    except Exception as e:
        errors.append(f"❌ 对比测试: {e}")
        failed += 1
    
    # === 总结 ===
    print(f"\n{'='*60}")
    print(f"测试结果: ✅ {passed} 通过 | ❌ {failed} 失败")
    
    if errors:
        print(f"\n失败详情:")
        for e in errors:
            print(f"  {e}")
    
    if failed == 0:
        print(f"\n🎉 全部通过！可以切换到 v2：")
        print(f"   1. 停止旧服务: Ctrl+C")
        print(f"   2. 启动新服务: python scripts/feishu_sdk_client_v2.py")
        print(f"   3. 飞书发一条测试消息验证")
        print(f"   4. 确认无误后归档旧文件: mv scripts/feishu_sdk_client.py scripts/feishu_sdk_client_v1_backup.py")
    else:
        print(f"\n⚠️ 有 {failed} 个测试失败，请修复后重新运行测试")
    
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
```

---

## 关键注意事项

### 对 CC 的要求：

1. **先分析原文件**：Step 0 的 grep 命令必须先执行，理解每个函数在哪里、被谁调用、依赖什么全局变量。不要凭猜测写代码。

2. **完整复制，不要改逻辑**：每个函数从原文件复制过来时，只改 import 路径，不要改任何业务逻辑。重构的目标是拆分，不是重写。

3. **保持函数签名一致**：send_reply、is_rd_task、handle_message 等函数的参数必须和原文件完全一致，否则调用方会报错。

4. **处理全局变量**：原文件中有些全局变量（如 _rd_lock、_last_rd_task_id、_processed_msgs）被多个函数共享。这些变量要放在对应模块的模块级别，并通过 import 共享。

5. **处理循环依赖**：如果 A 模块 import B，B 也 import A，会循环依赖。解决方式：
   - chat_helpers 不 import 任何其他 feishu_handlers 模块（它是最底层）
   - 其他模块可以 import chat_helpers
   - text_router import commands、rd_task、structured_doc（它是最顶层）
   - 依赖方向：chat_helpers ← file_sender ← commands ← rd_task ← text_router

6. **不要删除原文件**：feishu_sdk_client.py 保持不动。只是不再用它启动。

7. **structured_doc.py 中的 _send_file_to_feishu 改为 import**：
   ```python
   from scripts.feishu_handlers.file_sender import send_file_to_feishu as _send_file_to_feishu
   ```

---

## 验证流程

```bash
# 1. 运行自动测试
python scripts/test_feishu_v2.py

# 2. 如果全部通过，停旧服务
# （在运行旧服务的终端按 Ctrl+C）

# 3. 启动新服务
python scripts/feishu_sdk_client_v2.py

# 4. 在飞书发送测试消息：
#    - "你好" → 智能对话
#    - "A" → 评价处理
#    - "请输出头盔项目完整PRD..." → PRD 快速通道
#    - 发送一张图片 → 图片处理
#    - "帮我研究下HUD芯片方案" → 研发任务

# 5. 全部正常后归档旧文件
# mv scripts/feishu_sdk_client.py scripts/feishu_sdk_client_v1_backup.py
```
