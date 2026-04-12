"""
@description: MetaBot Peer 服务 - 接收飞书消息转发，执行圆桌/深度研究任务
@dependencies: FastAPI, uvicorn, requests
@last_modified: 2026-04-12
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

# === 配置 ===
PORT = 9300
METABOT_URL = "http://localhost:9100"
WORK_DIR = "D:/Users/uih00653/my_agent_company/pythonProject1"

# === 日志配置 ===
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("agent-peer")

# === FastAPI 应用 ===
app = FastAPI(title="Agent Company Peer", version="1.0.0")


# === 请求/响应模型 ===
class TalkRequest(BaseModel):
    botName: str
    chatId: str
    prompt: str
    sendCards: Optional[bool] = True


class TalkResponse(BaseModel):
    success: bool
    responseText: str
    costUsd: Optional[float] = None
    durationMs: Optional[int] = None
    error: Optional[str] = None


class BotInfo(BaseModel):
    name: str
    description: Optional[str] = None
    specialties: Optional[list[str]] = None
    platform: str = "web"
    workingDirectory: str


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    models: dict
    kb_count: int


# === 注册的 Bots ===
REGISTERED_BOTS = [
    BotInfo(
        name="hud-helmet-dev",
        description="智能骑行头盔研发助手 - 圆桌讨论、深度研究",
        specialties=["roundtable", "deep_research", "hud", "helmet"],
        platform="web",
        workingDirectory=WORK_DIR,
    ),
]


# === API 端点 ===

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """健康检查 - 返回模型可用性和 KB 条目数"""
    try:
        # 检查模型可用性
        models = check_model_availability()

        # 检查 KB 条目数
        kb_count = count_kb_entries()

        return HealthResponse(
            status="healthy",
            timestamp=datetime.now().isoformat(),
            models=models,
            kb_count=kb_count,
        )
    except Exception as e:
        logger.error(f"Health check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bots")
async def list_bots():
    """返回注册的 bots 列表 - PeerManager 会轮询此端点"""
    return JSONResponse(content={
        "bots": [bot.model_dump() for bot in REGISTERED_BOTS]
    })


@app.get("/api/skills")
async def list_skills():
    """返回 skills 列表 - 可选端点"""
    return JSONResponse(content={
        "skills": []
    })


@app.post("/api/talk", response_model=TalkResponse)
async def handle_talk(
    request: TalkRequest,
    x_metabot_origin: Optional[str] = Header(None),
):
    """
    接收 MetaBot 转发的飞书消息

    Headers:
        X-MetaBot-Origin: "peer" - 表示来自 MetaBot 转发

    Body:
        botName: 目标 bot 名称
        chatId: 飞书聊天 ID
        prompt: 用户消息内容
        sendCards: 是否发送卡片消息
    """
    logger.info(f"Received talk request: botName={request.botName}, chatId={request.chatId}, prompt={request.prompt[:50]}...")

    # 验证来源（防止循环转发）
    if x_metabot_origin != "peer":
        logger.warning(f"Request not from MetaBot peer: origin={x_metabot_origin}")

    # 检查 bot 是否注册
    bot_found = any(bot.name == request.botName for bot in REGISTERED_BOTS)
    if not bot_found:
        return TalkResponse(
            success=False,
            responseText="",
            error=f"Bot not found: {request.botName}"
        )

    # 解析消息内容，路由到不同处理逻辑
    prompt_lower = request.prompt.lower().strip()

    try:
        if prompt_lower.startswith("圆桌:") or prompt_lower.startswith("圆桌："):
            # 圆桌讨论
            result = handle_roundtable(request.prompt, request.chatId)
        elif prompt_lower.startswith("研究:") or prompt_lower.startswith("研究："):
            # 深度研究
            result = handle_deep_research(request.prompt, request.chatId)
        elif prompt_lower == "系统状态":
            # 系统状态查询
            result = handle_system_status()
        else:
            # 未识别的命令
            result = TalkResponse(
                success=False,
                responseText="",
                error="未识别的命令。可用命令: 圆桌:xxx, 研究:xxx, 系统状态"
            )

        # 如果执行成功，推送结果回飞书
        if result.success and request.sendCards:
            push_result_to_feishu(request.chatId, result.responseText)

        return result

    except Exception as e:
        logger.error(f"Handle talk error: {e}")
        return TalkResponse(
            success=False,
            responseText="",
            error=str(e)
        )


# === 命令处理函数 ===

def handle_roundtable(prompt: str, chat_id: str) -> TalkResponse:
    """处理圆桌讨论命令 - Placeholder"""
    # 提取主题
    topic = prompt.split(":", 1)[-1].strip() or prompt.split("：", 1)[-1].strip()
    logger.info(f"Roundtable placeholder: topic={topic}")

    return TalkResponse(
        success=True,
        responseText=f"[Placeholder] 圆桌讨论已启动，主题: {topic}\n\n完整实现待后续集成 roundtable.run_task()",
        durationMs=100
    )


def handle_deep_research(prompt: str, chat_id: str) -> TalkResponse:
    """处理深度研究命令 - Placeholder"""
    # 提取研究主题
    topic = prompt.split(":", 1)[-1].strip() or prompt.split("：", 1)[-1].strip()
    logger.info(f"Deep research placeholder: topic={topic}")

    return TalkResponse(
        success=True,
        responseText=f"[Placeholder] 深度研究已启动，主题: {topic}\n\n完整实现待后续集成 deep_research.pipeline.run()",
        durationMs=100
    )


def handle_system_status() -> TalkResponse:
    """返回系统状态"""
    try:
        models = check_model_availability()
        kb_count = count_kb_entries()

        status_text = f"""**系统状态报告**

**模型可用性:**
- o3-deep-research: {models.get('o3-deep-research', 'unknown')}
- gpt_5_4: {models.get('gpt_5_4', 'unknown')}
- doubao_seed_pro: {models.get('doubao_seed_pro', 'unknown')}
- tavily: {models.get('tavily', 'unknown')}

**知识库:**
- KB 条目数: {kb_count}

**服务:**
- MetaBot Peer 服务: 运行中 (端口 {PORT})
- 工作目录: {WORK_DIR}

时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
        return TalkResponse(
            success=True,
            responseText=status_text,
            durationMs=200
        )
    except Exception as e:
        return TalkResponse(
            success=False,
            responseText="",
            error=f"获取系统状态失败: {e}"
        )


# === 辅助函数 ===

def check_model_availability() -> dict:
    """检查模型可用性"""
    models = {}

    # 检查环境变量中的模型配置
    model_registry_path = os.path.join(WORK_DIR, "src/config/model_registry.yaml")
    if os.path.exists(model_registry_path):
        try:
            import yaml
            with open(model_registry_path, "r", encoding="utf-8") as f:
                registry = yaml.safe_load(f)
                if registry and "models" in registry:
                    for model_name in ["o3-deep-research", "gpt_5_4", "doubao_seed_pro", "tavily"]:
                        if model_name in registry["models"]:
                            models[model_name] = "configured"
                        else:
                            models[model_name] = "not_configured"
        except Exception as e:
            logger.warning(f"Failed to read model registry: {e}")

    # 检查关键环境变量
    if os.getenv("ANTHROPIC_API_KEY"):
        models["anthropic"] = "env_set"
    if os.getenv("TAVILY_API_KEY"):
        models["tavily"] = "env_set"

    return models


def count_kb_entries() -> int:
    """统计 KB 条目数"""
    kb_dir = os.path.join(WORK_DIR, ".ai-state/knowledge")
    if not os.path.exists(kb_dir):
        return 0

    count = 0
    for root, dirs, files in os.walk(kb_dir):
        for file in files:
            if file.endswith(".json"):
                count += 1

    return count


def push_result_to_feishu(chat_id: str, result_text: str):
    """推送结果回飞书 - 调用 MetaBot 的 /api/talk"""
    try:
        # 调用 MetaBot 的 talk API，让 MetaBot 发消息回飞书
        payload = {
            "botName": "hud-helmet-dev",
            "chatId": chat_id,
            "prompt": result_text,
            "sendCards": True
        }

        resp = requests.post(
            f"{METABOT_URL}/api/talk",
            json=payload,
            timeout=30
        )

        if resp.status_code == 200:
            logger.info(f"Result pushed to Feishu: chatId={chat_id}")
        else:
            logger.warning(f"Push failed: status={resp.status_code}, body={resp.text}")

    except Exception as e:
        logger.error(f"Push to Feishu error: {e}")


# === 启动 ===

def main():
    """启动服务"""
    logger.info(f"Starting Agent Company Peer service on port {PORT}")
    logger.info(f"Working directory: {WORK_DIR}")
    logger.info(f"MetaBot URL: {METABOT_URL}")

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=PORT,
        log_level="info"
    )


if __name__ == "__main__":
    main()