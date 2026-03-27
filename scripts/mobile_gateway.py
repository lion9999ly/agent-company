"""
@description: 移动端交互网关 - 支持飞书/Telegram双向交互，语音/图片输入
@dependencies: flask, requests
@last_modified: 2026-03-17

功能特性:
1. 飞书机器人 - 文本/语音/图片输入
2. Telegram Bot - 文本/语音/图片输入
3. 语音转文字 (ASR)
4. 图片理解 (Vision)
5. 任务执行结果推送

使用方法:
    python scripts/mobile_gateway.py --port 8080

配置:
    1. 飞书机器人: 在飞书开放平台创建企业自建应用
    2. Telegram Bot: 通过 @BotFather 创建机器人
"""

import os
import sys
import json
import hmac
import hashlib
import argparse
import threading
import time
import base64
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from queue import Queue
import logging

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MobileGateway")

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from flask import Flask, request, jsonify
    import requests
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False
    logger.error("请安装依赖: pip install flask requests")


class MessageChannel(Enum):
    """消息渠道"""
    FEISHU = "feishu"
    TELEGRAM = "telegram"
    WECHAT = "wechat"
    LOCAL = "local"


class MessageType(Enum):
    """消息类型"""
    TEXT = "text"
    VOICE = "voice"
    IMAGE = "image"
    FILE = "file"


@dataclass
class MobileMessage:
    """移动端消息结构"""
    message_id: str
    channel: MessageChannel
    message_type: MessageType
    content: str  # 文本内容或文件URL
    user_id: str
    user_name: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    raw_data: Dict = field(default_factory=dict)
    media_url: str = ""  # 媒体文件URL

    def to_dict(self) -> Dict:
        return {
            "message_id": self.message_id,
            "channel": self.channel.value,
            "message_type": self.message_type.value,
            "content": self.content,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "timestamp": self.timestamp.isoformat(),
            "media_url": self.media_url
        }


@dataclass
class TaskResult:
    """任务执行结果"""
    task_id: str
    status: str  # pending, running, completed, failed
    message: str
    result: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "message": self.message,
            "result": self.result,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }


class FeishuBot:
    """飞书机器人"""

    def __init__(self, app_id: str = None, app_secret: str = None):
        self.app_id = app_id or os.getenv("FEISHU_APP_ID", "")
        self.app_secret = app_secret or os.getenv("FEISHU_APP_SECRET", "")
        self.verify_token = os.getenv("FEISHU_VERIFY_TOKEN", "")
        self.base_url = "https://open.feishu.cn/open-apis"
        self.access_token = None
        self.token_expires = 0

    def get_tenant_access_token(self) -> str:
        """获取 tenant_access_token"""
        if self.access_token and time.time() < self.token_expires:
            return self.access_token

        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        data = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }

        try:
            response = requests.post(url, json=data, timeout=10)
            result = response.json()
            if result.get("code") == 0:
                self.access_token = result["tenant_access_token"]
                self.token_expires = time.time() + result["expire"] - 300
                return self.access_token
            else:
                logger.error(f"获取飞书token失败: {result}")
                return ""
        except Exception as e:
            logger.error(f"获取飞书token异常: {e}")
            return ""

    def verify_signature(self, timestamp: str, nonce: str, body: str, signature: str) -> bool:
        """验证飞书签名"""
        if not self.app_secret:
            return True  # 未配置则跳过验证

        token = self.verify_token
        sign_base = timestamp + nonce + token + body
        expected_sig = hashlib.sha256(sign_base.encode()).hexdigest()
        return expected_sig == signature

    def parse_message(self, data: Dict) -> Optional[MobileMessage]:
        """解析飞书消息"""
        try:
            event = data.get("event", {})
            message = event.get("message", {})
            msg_type = message.get("msg_type", "text")
            content = json.loads(message.get("content", "{}"))

            # 确定消息类型
            if msg_type == "text":
                text_content = content.get("text", "")
                return MobileMessage(
                    message_id=message.get("message_id", ""),
                    channel=MessageChannel.FEISHU,
                    message_type=MessageType.TEXT,
                    content=text_content,
                    user_id=event.get("sender", {}).get("sender_id", {}).get("user_id", ""),
                    user_name=event.get("sender", {}).get("sender_id", {}).get("open_id", ""),
                    raw_data=data
                )
            elif msg_type == "audio":
                # 语音消息
                file_key = content.get("file_key", "")
                return MobileMessage(
                    message_id=message.get("message_id", ""),
                    channel=MessageChannel.FEISHU,
                    message_type=MessageType.VOICE,
                    content="",  # 待ASR转录
                    user_id=event.get("sender", {}).get("sender_id", {}).get("user_id", ""),
                    media_url=file_key,  # 语音文件key
                    raw_data=data
                )
            elif msg_type == "image":
                # 图片消息
                image_key = content.get("image_key", "")
                return MobileMessage(
                    message_id=message.get("message_id", ""),
                    channel=MessageChannel.FEISHU,
                    message_type=MessageType.IMAGE,
                    content="",
                    user_id=event.get("sender", {}).get("sender_id", {}).get("user_id", ""),
                    media_url=image_key,
                    raw_data=data
                )
            else:
                logger.warning(f"不支持的消息类型: {msg_type}")
                return None
        except Exception as e:
            logger.error(f"解析飞书消息失败: {e}")
            return None

    def send_message(self, receive_id: str, msg_type: str, content: str, receive_id_type: str = "user_id") -> bool:
        """发送飞书消息"""
        token = self.get_tenant_access_token()
        if not token:
            return False

        url = f"{self.base_url}/im/v1/messages?receive_id_type={receive_id_type}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        data = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": json.dumps({"text": content}) if msg_type == "text" else content
        }

        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            result = response.json()
            return result.get("code") == 0
        except Exception as e:
            logger.error(f"发送飞书消息失败: {e}")
            return False

    def download_file(self, file_key: str, file_type: str = "image") -> Optional[bytes]:
        """下载飞书文件"""
        token = self.get_tenant_access_token()
        if not token:
            return None

        url = f"{self.base_url}/im/v1/{file_type}s/{file_key}/get"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                return response.content
        except Exception as e:
            logger.error(f"下载飞书文件失败: {e}")
        return None


class TelegramBot:
    """Telegram机器人"""

    def __init__(self, token: str = None):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    def set_webhook(self, webhook_url: str) -> bool:
        """设置Webhook"""
        url = f"{self.base_url}/setWebhook"
        data = {"url": webhook_url}
        try:
            response = requests.post(url, json=data, timeout=10)
            result = response.json()
            return result.get("ok", False)
        except Exception as e:
            logger.error(f"设置Telegram webhook失败: {e}")
            return False

    def parse_message(self, data: Dict) -> Optional[MobileMessage]:
        """解析Telegram消息"""
        try:
            message = data.get("message", {})
            from_user = message.get("from", {})

            if "text" in message:
                return MobileMessage(
                    message_id=str(message.get("message_id", "")),
                    channel=MessageChannel.TELEGRAM,
                    message_type=MessageType.TEXT,
                    content=message["text"],
                    user_id=str(from_user.get("id", "")),
                    user_name=from_user.get("username", ""),
                    raw_data=data
                )
            elif "voice" in message:
                voice = message["voice"]
                file_id = voice.get("file_id", "")
                return MobileMessage(
                    message_id=str(message.get("message_id", "")),
                    channel=MessageChannel.TELEGRAM,
                    message_type=MessageType.VOICE,
                    content="",
                    user_id=str(from_user.get("id", "")),
                    user_name=from_user.get("username", ""),
                    media_url=file_id,
                    raw_data=data
                )
            elif "photo" in message:
                photo = message["photo"][-1]  # 取最大尺寸
                file_id = photo.get("file_id", "")
                return MobileMessage(
                    message_id=str(message.get("message_id", "")),
                    channel=MessageChannel.TELEGRAM,
                    message_type=MessageType.IMAGE,
                    content="",
                    user_id=str(from_user.get("id", "")),
                    user_name=from_user.get("username", ""),
                    media_url=file_id,
                    raw_data=data
                )
            else:
                return None
        except Exception as e:
            logger.error(f"解析Telegram消息失败: {e}")
            return None

    def send_message(self, chat_id: str, text: str, parse_mode: str = "Markdown") -> bool:
        """发送Telegram消息"""
        url = f"{self.base_url}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        try:
            response = requests.post(url, json=data, timeout=10)
            result = response.json()
            return result.get("ok", False)
        except Exception as e:
            logger.error(f"发送Telegram消息失败: {e}")
            return False

    def download_file(self, file_id: str) -> Optional[bytes]:
        """下载Telegram文件"""
        # 先获取文件路径
        url = f"{self.base_url}/getFile"
        try:
            response = requests.get(url, params={"file_id": file_id}, timeout=10)
            result = response.json()
            if result.get("ok"):
                file_path = result["result"]["file_path"]
                download_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
                response = requests.get(download_url, timeout=30)
                if response.status_code == 200:
                    return response.content
        except Exception as e:
            logger.error(f"下载Telegram文件失败: {e}")
        return None


class ASRService:
    """语音识别服务"""

    def __init__(self, provider: str = "google"):
        self.provider = provider
        # Google Speech-to-Text (免费额度)
        self.google_api_key = os.getenv("GOOGLE_API_KEY", "")
        # 阿里云语音识别
        self.ali_appkey = os.getenv("ALI_ASR_APPKEY", "")

    def transcribe(self, audio_data: bytes, language: str = "zh-CN") -> str:
        """语音转文字"""
        if self.provider == "google" and self.google_api_key:
            return self._transcribe_google(audio_data, language)
        elif self.provider == "ali" and self.ali_appkey:
            return self._transcribe_ali(audio_data, language)
        else:
            # 使用Gemini处理音频
            return self._transcribe_gemini(audio_data)

    def _transcribe_google(self, audio_data: bytes, language: str) -> str:
        """Google语音识别"""
        url = f"https://speech.googleapis.com/v1/speech:recognize?key={self.google_api_key}"
        audio_base64 = base64.b64encode(audio_data).decode()

        data = {
            "config": {
                "encoding": "OGG_OPUS",
                "languageCode": language,
                "enableAutomaticPunctuation": True
            },
            "audio": {"content": audio_base64}
        }

        try:
            response = requests.post(url, json=data, timeout=30)
            result = response.json()
            if "results" in result:
                return result["results"][0]["alternatives"][0]["transcript"]
        except Exception as e:
            logger.error(f"Google ASR失败: {e}")
        return ""

    def _transcribe_gemini(self, audio_data: bytes) -> str:
        """使用Gemini处理音频（简化版）"""
        # 这里可以调用Gemini的音频理解能力
        # 暂时返回提示
        return "[语音消息，请配置ASR服务进行转录]"

    def _transcribe_ali(self, audio_data: bytes, language: str) -> str:
        """阿里云语音识别"""
        # 实现阿里云ASR
        return "[阿里云ASR待实现]"


class VisionService:
    """图像理解服务"""

    def __init__(self):
        self.gemini_api_key = os.getenv("GOOGLE_API_KEY", "AIzaSyCIpULNyI26SptD9OTfOXbfiK4uI9gqFXA")

    def analyze_image(self, image_data: bytes, prompt: str = "描述这张图片的内容") -> str:
        """分析图片内容"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.gemini_api_key}"

        image_base64 = base64.b64encode(image_data).decode()
        mime_type = self._detect_mime_type(image_data)

        data = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime_type, "data": image_base64}}
                ]
            }],
            "generationConfig": {"temperature": 0.1}
        }

        try:
            response = requests.post(url, json=data, timeout=60)
            result = response.json()
            if "candidates" in result:
                return result["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logger.error(f"图像分析失败: {e}")
        return "[图像分析失败]"

    def _detect_mime_type(self, data: bytes) -> str:
        """检测图片MIME类型"""
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        elif data[:2] == b'\xff\xd8':
            return "image/jpeg"
        elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            return "image/webp"
        return "image/jpeg"


class MobileGateway:
    """移动端交互网关"""

    def __init__(self, port: int = 8080):
        self.port = port
        self.app = Flask(__name__) if HAS_FLASK else None

        # 初始化各渠道
        self.feishu = FeishuBot()
        self.telegram = TelegramBot()
        self.asr = ASRService()
        self.vision = VisionService()

        # 任务队列和结果存储
        self.task_queue = Queue()
        self.task_results: Dict[str, TaskResult] = {}
        self.message_handlers: Dict[MessageChannel, Callable] = {}

        # 注册路由
        if self.app:
            self._register_routes()

    def _register_routes(self):
        """注册Flask路由"""
        @self.app.route('/health', methods=['GET'])
        def health():
            return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

        @self.app.route('/webhook/feishu', methods=['POST'])
        def feishu_webhook():
            return self._handle_feishu_webhook(request)

        @self.app.route('/webhook/telegram', methods=['POST'])
        def telegram_webhook():
            return self._handle_telegram_webhook(request)

        @self.app.route('/api/message', methods=['POST'])
        def api_message():
            return self._handle_api_message(request)

        @self.app.route('/api/task/<task_id>', methods=['GET'])
        def get_task(task_id):
            return self._handle_get_task(task_id)

        @self.app.route('/api/tasks', methods=['GET'])
        def list_tasks():
            return self._handle_list_tasks()

    def _handle_feishu_webhook(self, request) -> Dict:
        """处理飞书Webhook"""
        try:
            data = request.json

            # URL验证
            if data.get("type") == "url_verification":
                return jsonify({"challenge": data.get("challenge")})

            # 解析消息
            message = self.feishu.parse_message(data)
            if message:
                self._process_message(message)
                return jsonify({"code": 0, "msg": "success"})

            return jsonify({"code": 0, "msg": "ignored"})
        except Exception as e:
            logger.error(f"处理飞书webhook失败: {e}")
            return jsonify({"code": -1, "msg": str(e)})

    def _handle_telegram_webhook(self, request) -> Dict:
        """处理Telegram Webhook"""
        try:
            data = request.json
            message = self.telegram.parse_message(data)

            if message:
                self._process_message(message)
                return jsonify({"ok": True})

            return jsonify({"ok": True, "message": "ignored"})
        except Exception as e:
            logger.error(f"处理Telegram webhook失败: {e}")
            return jsonify({"ok": False, "error": str(e)})

    def _handle_api_message(self, request) -> Dict:
        """处理API消息（本地测试用）"""
        try:
            data = request.json
            message = MobileMessage(
                message_id=data.get("message_id", f"local_{time.time()}"),
                channel=MessageChannel.LOCAL,
                message_type=MessageType.TEXT,
                content=data.get("content", ""),
                user_id=data.get("user_id", "local_user"),
                raw_data=data
            )
            self._process_message(message)
            return jsonify({"status": "received", "message_id": message.message_id})
        except Exception as e:
            return jsonify({"error": str(e)})

    def _handle_get_task(self, task_id: str) -> Dict:
        """获取任务状态"""
        if task_id in self.task_results:
            return jsonify(self.task_results[task_id].to_dict())
        return jsonify({"error": "task not found"}), 404

    def _handle_list_tasks(self) -> Dict:
        """列出所有任务"""
        tasks = [t.to_dict() for t in self.task_results.values()]
        return jsonify({"tasks": tasks, "count": len(tasks)})

    def _process_message(self, message: MobileMessage):
        """处理消息"""
        logger.info(f"收到消息: {message.channel.value} - {message.message_type.value}")

        # 处理不同类型的消息
        if message.message_type == MessageType.TEXT:
            self._handle_text_message(message)
        elif message.message_type == MessageType.VOICE:
            self._handle_voice_message(message)
        elif message.message_type == MessageType.IMAGE:
            self._handle_image_message(message)

    def _handle_text_message(self, message: MobileMessage):
        """处理文本消息"""
        # 创建任务
        task_id = f"task_{int(time.time()*1000)}"
        task = TaskResult(
            task_id=task_id,
            status="pending",
            message=message.content
        )
        self.task_results[task_id] = task

        # 放入队列等待处理
        self.task_queue.put((task_id, message))

        # 立即回复确认
        self._reply(message, f"✅ 任务已接收\n📋 任务ID: {task_id}\n⏳ 正在处理...")

    def _handle_voice_message(self, message: MobileMessage):
        """处理语音消息"""
        task_id = f"task_{int(time.time()*1000)}"

        # 下载音频文件
        audio_data = None
        if message.channel == MessageChannel.FEISHU:
            audio_data = self.feishu.download_file(message.media_url, "file")
        elif message.channel == MessageChannel.TELEGRAM:
            audio_data = self.telegram.download_file(message.media_url)

        if audio_data:
            # 语音转文字
            self._reply(message, "🎤 正在识别语音...")
            text = self.asr.transcribe(audio_data)

            if text:
                message.content = text
                message.message_type = MessageType.TEXT
                self._reply(message, f"📝 识别结果: {text}")
                self._handle_text_message(message)
            else:
                self._reply(message, "❌ 语音识别失败")
        else:
            self._reply(message, "❌ 无法下载语音文件")

    def _handle_image_message(self, message: MobileMessage):
        """处理图片消息"""
        task_id = f"task_{int(time.time()*1000)}"

        # 下载图片
        image_data = None
        if message.channel == MessageChannel.FEISHU:
            image_data = self.feishu.download_file(message.media_url, "image")
        elif message.channel == MessageChannel.TELEGRAM:
            image_data = self.telegram.download_file(message.media_url)

        if image_data:
            # 图像理解
            self._reply(message, "🖼️ 正在分析图片...")
            analysis = self.vision.analyze_image(image_data)
            message.content = f"[用户发送图片]\n图片内容: {analysis}"
            message.message_type = MessageType.TEXT
            self._handle_text_message(message)
        else:
            self._reply(message, "❌ 无法下载图片")

    def _reply(self, message: MobileMessage, text: str):
        """回复消息"""
        if message.channel == MessageChannel.FEISHU:
            self.feishu.send_message(message.user_id, "text", text, "user_id")
        elif message.channel == MessageChannel.TELEGRAM:
            self.telegram.send_message(message.user_id, text)

    def register_handler(self, channel: MessageChannel, handler: Callable):
        """注册消息处理器"""
        self.message_handlers[channel] = handler

    def process_tasks(self):
        """处理任务队列（在后台线程运行）"""
        while True:
            try:
                task_id, message = self.task_queue.get(timeout=1)

                # 更新状态
                if task_id in self.task_results:
                    self.task_results[task_id].status = "running"

                # 调用注册的处理器
                handler = self.message_handlers.get(message.channel)
                if handler:
                    try:
                        result = handler(message)
                        if task_id in self.task_results:
                            self.task_results[task_id].status = "completed"
                            self.task_results[task_id].result = result
                            self.task_results[task_id].completed_at = datetime.now()
                        self._reply(message, f"✅ 任务完成\n\n{result[:2000]}")  # 限制长度
                    except Exception as e:
                        if task_id in self.task_results:
                            self.task_results[task_id].status = "failed"
                            self.task_results[task_id].result = str(e)
                        self._reply(message, f"❌ 任务失败: {e}")
                else:
                    # 模拟处理
                    if task_id in self.task_results:
                        self.task_results[task_id].status = "completed"
                        self.task_results[task_id].result = f"收到: {message.content}"
                        self.task_results[task_id].completed_at = datetime.now()
                    self._reply(message, f"✅ 已收到: {message.content}")

            except Exception as e:
                if "Empty" not in str(e):
                    logger.error(f"处理任务异常: {e}")

    def run(self):
        """启动服务"""
        if not HAS_FLASK:
            logger.error("Flask未安装，无法启动服务")
            return

        # 启动后台任务处理线程
        task_thread = threading.Thread(target=self.process_tasks, daemon=True)
        task_thread.start()

        logger.info(f"🚀 移动端网关启动: http://0.0.0.0:{self.port}")
        logger.info(f"📱 飞书Webhook: http://<your-ip>:{self.port}/webhook/feishu")
        logger.info(f"📱 Telegram Webhook: http://<your-ip>:{self.port}/webhook/telegram")

        self.app.run(host="0.0.0.0", port=self.port, debug=False)


def main():
    parser = argparse.ArgumentParser(description="移动端交互网关")
    parser.add_argument("--port", "-p", type=int, default=8080, help="服务端口")
    parser.add_argument("--setup-feishu", action="store_true", help="输出飞书配置指南")
    parser.add_argument("--setup-telegram", action="store_true", help="输出Telegram配置指南")
    parser.add_argument("--ngrok", action="store_true", help="启动ngrok内网穿透")

    args = parser.parse_args()

    if args.setup_feishu:
        print("""
========================================
飞书机器人配置指南
========================================

1. 打开飞书开放平台: https://open.feishu.cn
2. 创建企业自建应用
3. 在"凭证与基础信息"获取:
   - App ID
   - App Secret
4. 在"事件订阅"配置:
   - 请求地址: https://<your-domain>/webhook/feishu
   - 订阅事件: im.message.receive_v1
5. 在"权限管理"开通:
   - im:message:receive_as_bot
   - im:message:send
   - im:resource

环境变量配置:
   export FEISHU_APP_ID="cli_xxx"
   export FEISHU_APP_SECRET="xxx"
   export FEISHU_VERIFY_TOKEN="xxx"
""")
        return

    if args.setup_telegram:
        print("""
========================================
Telegram机器人配置指南
========================================

1. 在Telegram搜索 @BotFather
2. 发送 /newbot 创建新机器人
3. 按提示设置名称，获取 Bot Token
4. 发送消息给机器人启动对话
5. 获取Chat ID: 访问 https://api.telegram.org/bot<token>/getUpdates

环境变量配置:
   export TELEGRAM_BOT_TOKEN="123456:ABC-xxx"
   export TELEGRAM_CHAT_ID="123456789"

设置Webhook:
   curl -F "url=https://<your-domain>/webhook/telegram" \\
        https://api.telegram.org/bot<token>/setWebhook
""")
        return

    if args.ngrok:
        print("启动ngrok内网穿透...")
        import subprocess
        subprocess.Popen(["ngrok", "http", str(args.port)])
        print(f"请在ngrok控制台查看外网地址: http://127.0.0.1:4040")

    # 启动网关
    gateway = MobileGateway(port=args.port)
    gateway.run()


if __name__ == "__main__":
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
    main()