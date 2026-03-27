from lark_oapi import WsClient, ImMessageReceiveV1, Logger, LogLevel
import json

# ！！！仅修改这里，填入你飞书应用的App ID和App Secret，不要加空格、不要写错
APP_ID = "你的App ID"
APP_SECRET = "你的App Secret"


# 事件处理函数：只要飞书推了事件，一定会打印日志，无任何过滤逻辑
def handle_event(event: ImMessageReceiveV1):
    print("\n" + "=" * 60)
    print(f"✅【成功收到飞书事件】事件ID：{event.event_id}")
    print(f"👤 发送人ID：{event.event.sender.sender_id.open_id}")
    print(f"📄 原始消息内容：{event.event.message.content}")

    # 解析用户发送的文本
    try:
        content_json = json.loads(event.event.message.content)
        user_text = content_json.get("text", "非文本消息")
        print(f"💬 用户发送的文本：{user_text}")
    except Exception as e:
        print(f"⚠️ 消息解析失败：{e}")
        user_text = "无法解析的消息"

    print("=" * 60 + "\n")


# 主程序启动
if __name__ == "__main__":
    # 开启DEBUG日志，所有连接细节全打印，方便排查
    debug_logger = Logger(level=LogLevel.DEBUG)
    # 创建长连接客户端
    ws_client = WsClient(APP_ID, APP_SECRET, logger=debug_logger)
    # 注册事件处理器，和飞书事件名100%匹配
    ws_client.register_event_handler(ImMessageReceiveV1, handle_event)
    # 启动服务
    print("🚀 飞书机器人调试服务启动，正在连接长连接...")
    ws_client.start()
    print("✅ 长连接已成功建立，等待飞书消息推送...")