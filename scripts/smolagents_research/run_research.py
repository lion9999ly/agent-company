"""
@description: smolagents 深度研究入口 - 替换搜索层
@dependencies: smolagents, litellm, doubao_search_tool, tavily_search_tool
@last_modified: 2026-04-12

功能：
- LiteLLMModel 对接 Azure/Volcengine/Gemini
- 注册 DoubaoSearchTool 和 TavilySearchTool
- step_callbacks 预留 critic_hook 和 kb_insert_hook
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# smolagents imports
from smolagents import CodeAgent, LiteLLMModel, Tool, ActionStep

# 导入自定义工具
sys.path.insert(0, str(Path(__file__).resolve().parent))
from doubao_search_tool import DoubaoSearchTool
from tavily_search_tool import TavilySearchTool


# ============================================================
# 后处理 Hooks（预留）
# ============================================================

def critic_hook(memory_step: ActionStep, agent=None) -> Optional[str]:
    """Critic 评审 hook - 预留

    在最终答案生成后执行评审：
    - P0: 阻塞输出
    - P1: 记录问题
    - P2: 可忽略
    """
    if memory_step.is_final_answer:
        # TODO: 对接 scripts/deep_research/critic.py
        output = memory_step.model_output if memory_step.model_output else ""
        print(f"[Critic Hook] 预留 - 输出长度: {len(str(output))}")
        # return "P0 问题: ..."  # 返回字符串会阻塞
    return None


def kb_insert_hook(memory_step: ActionStep, agent=None) -> None:
    """KB 入库 hook - 预留

    将研究结果入库到 knowledge_base
    """
    if memory_step.is_final_answer:
        # TODO: 对接 scripts/deep_research/kb_manager.py
        output = memory_step.model_output if memory_step.model_output else ""
        print(f"[KB Hook] 预留 - 可入库内容长度: {len(str(output))}")


# ============================================================
# Agent 配置
# ============================================================

def create_research_agent(
    model_name: str = "gpt_4o",
    provider: str = "azure_norway",
    use_doubao: bool = True,
    use_tavily: bool = True
) -> CodeAgent:
    """创建研究 Agent

    Args:
        model_name: 模型名称（映射到 LiteLLM）
        provider: Provider 名称
        use_doubao: 是否启用豆包搜索
        use_tavily: 是否启用 Tavily 搜索

    Returns:
        配置好的 CodeAgent
    """

    # LiteLLM 模型配置
    model_config = get_model_config(provider)

    model = LiteLLMModel(
        model_id=model_config["model"],
        api_key=model_config["api_key"],
        api_base=model_config.get("api_base"),
        custom_role_conversions={
            "tool-call": "assistant",
            "tool-response": "user",
        },
    )

    # 注册工具
    tools = []
    if use_doubao:
        doubao_tool = DoubaoSearchTool()
        doubao_tool.setup()
        tools.append(doubao_tool)

    if use_tavily:
        tavily_tool = TavilySearchTool()
        try:
            tavily_tool.setup()
            tools.append(tavily_tool)
        except ValueError as e:
            print(f"[Warning] Tavily 未配置: {e}")

    # 创建 Agent（不使用 step_callbacks，先确保基本功能）
    agent = CodeAgent(
        tools=tools,
        model=model,
        max_steps=10,
        additional_authorized_imports=["requests", "os", "json"],
    )

    # 预留: 通过 CallbackRegistry 注册回调
    # agent.step_callbacks = [critic_hook, kb_insert_hook]

    return agent


def get_model_config(provider: str) -> Dict[str, Any]:
    """获取模型配置（从环境变量）"""

    configs = {
        "azure": {
            "model": "azure/gpt-4o",
            "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
            "api_base": os.getenv("AZURE_OPENAI_ENDPOINT"),
        },
        "azure_norway": {
            "model": "azure/gpt-4o",
            "api_key": os.getenv("AZURE_OPENAI_NORWAY_API_KEY"),
            "api_base": os.getenv("AZURE_OPENAI_NORWAY_ENDPOINT"),
        },
        "volcengine": {
            "model": "openai/doubao-seed-2-0-pro-260215",
            "api_key": os.getenv("ARK_API_KEY"),
            "api_base": "https://ark.cn-beijing.volces.com/api/v3",
        },
        "gemini": {
            "model": "gemini/gemini-2.5-flash",
            "api_key": os.getenv("GEMINI_API_KEY"),
        },
    }

    if provider not in configs:
        raise ValueError(f"Unknown provider: {provider}")

    config = configs[provider]
    if not config.get("api_key"):
        raise ValueError(f"API key not configured for provider: {provider}")

    return config


# ============================================================
# 运行函数
# ============================================================

def run_research(
    query: str,
    model_name: str = "gpt_4o",
    provider: str = "azure_norway",
    use_tavily: bool = True
) -> Dict[str, Any]:
    """运行研究任务

    Args:
        query: 研究查询
        model_name: 模型名称
        provider: Provider 名称
        use_tavily: 是否使用 Tavily

    Returns:
        研究结果
    """

    print(f"[Research] 创建 Agent: provider={provider}, model={model_name}")
    agent = create_research_agent(
        model_name=model_name,
        provider=provider,
        use_tavily=use_tavily
    )

    print(f"[Research] 执行查询: {query[:100]}...")
    start_time = datetime.now()

    try:
        result = agent.run(query)

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"[Research] 完成: 耗时 {elapsed:.1f}s")

        return {
            "success": True,
            "query": query,
            "result": result,
            "elapsed_seconds": elapsed,
            "model": model_name,
            "provider": provider,
        }

    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"[Research] 失败: {str(e)}")

        return {
            "success": False,
            "query": query,
            "error": str(e),
            "elapsed_seconds": elapsed,
            "model": model_name,
            "provider": provider,
        }


# ============================================================
# CLI 入口
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="smolagents 深度研究")
    parser.add_argument("query", help="研究查询")
    parser.add_argument("--provider", default="azure_norway", help="Provider: azure, azure_norway, volcengine, gemini")
    parser.add_argument("--model", default="gpt_4o", help="模型名称")
    parser.add_argument("--no-tavily", action="store_true", help="禁用 Tavily")
    parser.add_argument("--output", help="输出文件路径")

    args = parser.parse_args()

    # 运行研究
    result = run_research(
        query=args.query,
        model_name=args.model,
        provider=args.provider,
        use_tavily=not args.no_tavily
    )

    # 输出结果
    if args.output:
        import json
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"结果已保存: {args.output}")
    else:
        print("\n" + "="*60)
        print("研究结果")
        print("="*60)
        if result["success"]:
            print(result["result"])
        else:
            print(f"错误: {result['error']}")