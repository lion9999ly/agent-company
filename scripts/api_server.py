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


class RoundtableRequest(BaseModel):
    topic: str


class ResearchRequest(BaseModel):
    query: str


class AgentRequest(BaseModel):
    instruction: str


class ExecRequest(BaseModel):
    """直接执行端点请求模型"""
    prompt: str
    workingDirectory: Optional[str] = None
    timeoutSeconds: Optional[int] = 120


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
# 使用不同名称避免与 MetaBot 本地 Feishu bot 冲突
REGISTERED_BOTS = [
    BotInfo(
        name="agent-service",
        description="Agent Company 后端服务 - 圆桌讨论、深度研究、系统状态",
        specialties=["roundtable", "deep_research", "system_status"],
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


# === CC 直接调用的端点（不经过 MetaBot peer 转发） ===

@app.post("/roundtable")
async def roundtable_endpoint(request: RoundtableRequest):
    """
    圆桌讨论端点 - CC 直接调用

    Body: {"topic": "讨论主题"}
    """
    logger.info(f"Roundtable endpoint called: topic={request.topic}")

    # Placeholder - 实际实现待集成 scripts/roundtable/roundtable.py
    return JSONResponse(content={
        "status": "ok",
        "message": f"圆桌讨论路由已注册，主题: {request.topic}",
        "note": "功能待实现，需集成 scripts/roundtable/roundtable.py"
    })


@app.post("/research")
async def research_endpoint(request: ResearchRequest):
    """
    深度研究端点 - CC 直接调用

    Body: {"query": "研究查询"}
    """
    logger.info(f"Research endpoint called: query={request.query}")

    # Placeholder - 实际实现待集成 scripts/deep_research/pipeline.py
    return JSONResponse(content={
        "status": "ok",
        "message": f"深度研究路由已注册，查询: {request.query}",
        "note": "功能待实现，需集成 scripts/deep_research/pipeline.py"
    })


@app.post("/agent")
async def agent_endpoint(request: AgentRequest):
    """
    通用 Agent 端点 - CC 直接调用

    Body: {"instruction": "指令内容"}
    """
    logger.info(f"Agent endpoint called: instruction={request.instruction}")

    # Placeholder - 实际实现待定义
    return JSONResponse(content={
        "status": "ok",
        "message": f"Agent 路由已注册，指令: {request.instruction}",
        "note": "功能待实现"
    })


@app.post("/exec")
async def exec_endpoint(request: ExecRequest):
    """
    直接执行端点 - 绕过 MetaBot 审批层，直接调用 CC subprocess

    Body: {
        "prompt": "执行指令",
        "workingDirectory": "可选工作目录",
        "maxTurns": 10,
        "timeoutSeconds": 120
    }
    """
    import subprocess
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    logger.info(f"Exec endpoint called: prompt={request.prompt[:100]}...")

    # 确定工作目录
    work_dir = request.workingDirectory or WORK_DIR

    # Claude CLI 绝对路径（Windows 上需要 .cmd 扩展名）
    CLAUDE_CLI_PATH = os.getenv("CLAUDE_EXECUTABLE_PATH", "C:/Users/uih00653/nodejs/claude.cmd")

    # 构建 CC 命令（验证过的最小参数组合）
    claude_cmd = [
        CLAUDE_CLI_PATH,
        "-p", request.prompt,
        "--dangerously-skip-permissions",
    ]

    timeout_sec = request.timeoutSeconds or 120

    try:
        # 使用线程池执行 subprocess，避免阻塞
        def run_claude():
            logger.info(f"Executing: {claude_cmd}")
            result = subprocess.run(
                claude_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                cwd=work_dir,
                encoding="utf-8",
                shell=True,  # Windows 上执行 .cmd 文件需要 shell=True
            )
            return result

        # 在线程池中执行
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = await loop.run_in_executor(executor, run_claude)

        # 解析输出（纯文本格式）
        output_text = result.stdout.strip()
        error_text = result.stderr

        if result.returncode != 0:
            logger.error(f"CC execution failed: returncode={result.returncode}, stderr={error_text}")
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": f"Claude execution failed: {error_text}",
                    "returncode": result.returncode,
                }
            )

        logger.info(f"Exec completed successfully: result_length={len(output_text)}")

        return JSONResponse(content={
            "success": True,
            "result": output_text,
            "returncode": result.returncode,
        })

    except subprocess.TimeoutExpired:
        logger.error(f"CC execution timeout after {timeout_sec}s")
        return JSONResponse(
            status_code=504,
            content={
                "success": False,
                "error": f"Execution timeout after {timeout_sec} seconds",
            }
        )
    except Exception as e:
        logger.error(f"Exec endpoint error: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
            }
        )


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