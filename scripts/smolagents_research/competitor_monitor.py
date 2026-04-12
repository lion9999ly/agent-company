"""
@description: 竞品监控系统 - 6维度监控智能骑行头盔市场
@dependencies: smolagents, litellm, tavily_search_tool, feishu_output
@last_modified: 2026-04-12

监控维度：
1. 直接竞品：Shoei GT-Air 3 Smart, EyeLights, MOTOEYE, 洛克兄弟骑光Air, iC-R, EyeRide
2. 光学供应商：JBD, SeeYA, 京东方微显示, 水晶光电
3. ADAS向两轮迁移：Bosch两轮, Continental, 两轮ADAS法规
4. 骑行生态：摩托车市场趋势, 骑行App, Mesh通讯, 行车记录仪
5. 融资动态：智能硬件赛道融资
6. 法规认证：ECE 22.06, GB 811电子集成规定

所有搜索词必须带2026年份限定。
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# smolagents imports
from smolagents import CodeAgent, LiteLLMModel

# 导入自定义工具（使用相对路径）
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# 尝试两种导入方式
try:
    from tavily_search_tool import TavilySearchTool
except ImportError:
    from scripts.smolagents_research.tavily_search_tool import TavilySearchTool


# ============================================================
# 监控维度配置（所有搜索词带2026年份）
# ============================================================

MONITOR_DIMENSIONS = {
    "direct_competitors": {
        "name": "直接竞品",
        "queries": [
            "Shoei GT-Air 3 Smart HUD helmet 2026",
            "EyeLights motorcycle HUD 2026 features",
            "MOTOEYE helmet display system 2026",
            "洛克兄弟骑光Air 2026 智能头盔",
            "iC-R intelligent helmet 2026",
            "EyeRide motorcycle smart helmet 2026",
        ]
    },
    "optical_suppliers": {
        "name": "光学供应商",
        "queries": [
            "JBD microLED display motorcycle 2026",
            "SeeYA optical motorcycle HUD 2026",
            "京东方微显示 2026 摩托车头盔",
            "水晶光电 2026 头盔显示",
        ]
    },
    "adas_migration": {
        "name": "ADAS向两轮迁移",
        "queries": [
            "Bosch motorcycle ADAS 2026 safety",
            "Continental two-wheel ADAS 2026",
            "两轮ADAS法规 2026 欧洲",
            "motorcycle collision warning system 2026",
        ]
    },
    "riding_ecosystem": {
        "name": "骑行生态",
        "queries": [
            "摩托车市场趋势 2026 全球",
            "骑行App 2026 摩托车导航",
            "Mesh通讯摩托车 2026 Cardin",
            "行车记录仪摩托车 2026 智能",
        ]
    },
    "funding_dynamic": {
        "name": "融资动态",
        "queries": [
            "智能硬件赛道融资 2026 摩托车",
            "smart helmet startup funding 2026",
            "motorcycle tech venture capital 2026",
        ]
    },
    "regulations": {
        "name": "法规认证",
        "queries": [
            "ECE 22.06 helmet standard 2026",
            "GB 811 电子集成规定 2026 头盔",
            "helmet electronic integration regulation 2026",
        ]
    }
}


# ============================================================
# LiteLLM 模型配置
# ============================================================

def get_model_config(provider: str = "azure_norway") -> Dict[str, Any]:
    """获取 LiteLLM 模型配置"""

    configs = {
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
    }

    config = configs.get(provider)
    if not config or not config.get("api_key"):
        raise ValueError(f"API key not configured for provider: {provider}")

    return config


def create_summary_model(provider: str = "azure_norway") -> LiteLLMModel:
    """创建摘要模型（LiteLLM）"""
    config = get_model_config(provider)

    return LiteLLMModel(
        model_id=config["model"],
        api_key=config["api_key"],
        api_base=config.get("api_base"),
        custom_role_conversions={
            "tool-call": "assistant",
            "tool-response": "user",
        },
    )


# ============================================================
# 搜索与摘要
# ============================================================

def search_dimension(
    tavily_tool: TavilySearchTool,
    dimension_key: str,
    max_results_per_query: int = 3
) -> Dict[str, Any]:
    """搜索单个维度的所有查询

    Args:
        tavily_tool: Tavily 搜索工具
        dimension_key: 维度键名
        max_results_per_query: 每个查询的最大结果数

    Returns:
        维度搜索结果
    """

    dimension = MONITOR_DIMENSIONS[dimension_key]
    queries = dimension["queries"]

    all_results = []
    errors = []

    for query in queries:
        try:
            print(f"  [搜索] {query}")
            result = tavily_tool.forward(
                query=query,
                search_depth="basic",
                max_results=max_results_per_query,
                include_raw_content=False
            )
            all_results.append({
                "query": query,
                "result": result,
                "success": True
            })
        except Exception as e:
            errors.append({
                "query": query,
                "error": str(e),
                "success": False
            })

    return {
        "dimension": dimension["name"],
        "key": dimension_key,
        "results": all_results,
        "errors": errors,
        "total_queries": len(queries),
        "successful_queries": len(all_results),
    }


def summarize_dimension(
    model: LiteLLMModel,
    dimension_data: Dict[str, Any]
) -> str:
    """使用 LiteLLM 摘要单个维度

    Args:
        model: LiteLLM 模型
        dimension_data: 维度搜索结果

    Returns:
        维度摘要（≤200字）
    """

    # 合并搜索结果
    combined_results = "\n\n".join([
        r["result"] for r in dimension_data["results"] if r["success"]
    ])

    if not combined_results:
        return f"[{dimension_data['dimension']}] 无有效搜索结果"

    # LiteLLM 摘要提示
    prompt = f"""请将以下搜索结果摘要为≤200字的中文报告，突出关键动态和数字：

维度：{dimension_data['dimension']}

搜索结果：
{combined_results[:3000]}

要求：
1. 只提取与该维度相关的关键信息
2. 保留数字（融资金额、市场份额、产品参数等）
3. 忽略无关广告或推广内容
4. 如果没有有价值的信息，返回"[无重要动态]"
"""

    try:
        # 直接调用模型（不使用 CodeAgent）
        from litellm import completion

        config = get_model_config("azure_norway")

        response = completion(
            model=config["model"],
            api_key=config["api_key"],
            api_base=config.get("api_base"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3,
        )

        summary = response.choices[0].message.content.strip()
        return summary

    except Exception as e:
        return f"[摘要失败: {str(e)}]"


# ============================================================
# 报告生成
# ============================================================

def generate_report(
    provider: str = "azure_norway",
    max_results_per_query: int = 3
) -> Dict[str, Any]:
    """生成完整的竞品监控报告

    Args:
        provider: LiteLLM provider
        max_results_per_query: 每个查询的最大结果数

    Returns:
        完整报告数据
    """

    print("=" * 60)
    print("竞品监控系统启动")
    print("=" * 60)

    # 初始化工具
    tavily_tool = TavilySearchTool()
    try:
        tavily_tool.setup()
    except ValueError as e:
        print(f"[错误] Tavily 未配置: {e}")
        return {
            "success": False,
            "error": f"Tavily API key not configured: {e}",
            "timestamp": datetime.now().isoformat(),
        }

    # 初始化 LiteLLM 模型
    model = create_summary_model(provider)

    # 搜索所有维度
    report_data = {
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y%m%d"),
        "dimensions": {},
        "summary": "",
        "success": True,
    }

    start_time = datetime.now()

    for dimension_key in MONITOR_DIMENSIONS:
        print(f"\n[{MONITOR_DIMENSIONS[dimension_key]['name']}]")

        # 搜索
        dimension_data = search_dimension(
            tavily_tool,
            dimension_key,
            max_results_per_query
        )

        # 摘要
        summary = summarize_dimension(model, dimension_data)

        report_data["dimensions"][dimension_key] = {
            "name": dimension_data["dimension"],
            "summary": summary,
            "query_count": dimension_data["total_queries"],
            "success_count": dimension_data["successful_queries"],
            "raw_results": dimension_data["results"],
            "errors": dimension_data["errors"],
        }

    elapsed = (datetime.now() - start_time).total_seconds()
    report_data["elapsed_seconds"] = elapsed

    # 生成总摘要（≤500字）
    all_summaries = "\n".join([
        f"- {d['name']}: {d['summary']}"
        for d in report_data["dimensions"].values()
    ])

    total_summary_prompt = f"""请将以下各维度摘要整合为≤500字的整体摘要：

{all_summaries}

要求：
1. 按重要性排序（竞品动态 > 融资 > 法规 > 生态）
2. 突出变化和新信息
3. 如果没有重要变化，简洁说明"本周无重大动态"
"""

    try:
        from litellm import completion
        config = get_model_config(provider)

        response = completion(
            model=config["model"],
            api_key=config["api_key"],
            api_base=config.get("api_base"),
            messages=[{"role": "user", "content": total_summary_prompt}],
            max_tokens=800,
            temperature=0.3,
        )

        report_data["summary"] = response.choices[0].message.content.strip()

    except Exception as e:
        report_data["summary"] = f"[总摘要生成失败: {str(e)}]"

    print(f"\n[完成] 耗时 {elapsed:.1f}s")
    return report_data


def save_report(report_data: Dict[str, Any], output_dir: str = None) -> str:
    """保存报告到 JSON 文件

    Args:
        report_data: 报告数据
        output_dir: 输出目录（默认 .ai-state/reports）

    Returns:
        报告文件路径
    """

    if output_dir is None:
        output_dir = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "reports"

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    date_str = report_data.get("date", datetime.now().strftime("%Y%m%d"))
    filename = f"competitor_{date_str}.json"
    filepath = output_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print(f"[保存] {filepath}")
    return str(filepath)


# ============================================================
# 飞书推送
# ============================================================

def push_to_feishu(report_data: Dict[str, Any], chat_id: str = None) -> bool:
    """推送摘要到飞书（只推摘要，不推过程）

    Args:
        report_data: 报告数据
        chat_id: 飞书 chat_id（默认从环境变量读取）

    Returns:
        是否推送成功
    """

    # 获取 chat_id
    if chat_id is None:
        chat_id = os.getenv("FEISHU_CHAT_ID")

    if not chat_id:
        print("[Warning] FEISHU_CHAT_ID 未配置，跳过飞书推送")
        return False

    # 构建摘要消息（≤500字）
    summary = report_data.get("summary", "")

    # 如果摘要超过500字，截断
    if len(summary) > 500:
        summary = summary[:497] + "..."

    message = f"""## 竞品监控日报 - {report_data.get('date', datetime.now().strftime('%Y%m%d'))}

{summary}

---
监控维度：{len(report_data.get('dimensions', {}))} | 耗时：{report_data.get('elapsed_seconds', 0):.1f}s
"""

    try:
        import subprocess
        result = subprocess.run(
            ["lark-cli", "im", "+messages-send",
             "--chat-id", chat_id,
             "--text", message,
             "--as", "bot"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            print("[飞书] 推送成功")
            return True
        else:
            print(f"[飞书] 推送失败: {result.stderr}")
            return False

    except Exception as e:
        print(f"[飞书] 推送出错: {str(e)}")
        return False


# ============================================================
# CLI 入口
# ============================================================

def run_competitor_monitor(
    provider: str = "azure_norway",
    max_results: int = 3,
    output_dir: str = None,
    push_feishu: bool = True,
    chat_id: str = None
) -> Dict[str, Any]:
    """运行竞品监控完整流程

    Args:
        provider: LiteLLM provider
        max_results: 每个查询的最大结果数
        output_dir: 输出目录
        push_feishu: 是否推送飞书
        chat_id: 飞书 chat_id

    Returns:
        报告数据
    """

    # 生成报告
    report_data = generate_report(provider, max_results)

    if not report_data.get("success"):
        return report_data

    # 保存报告
    filepath = save_report(report_data, output_dir)
    report_data["report_file"] = filepath

    # 飞书推送
    if push_feishu:
        push_success = push_to_feishu(report_data, chat_id)
        report_data["feishu_pushed"] = push_success

    return report_data


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="竞品监控系统")
    parser.add_argument("--provider", default="azure_norway", help="LiteLLM provider")
    parser.add_argument("--max-results", type=int, default=3, help="每个查询的最大结果数")
    parser.add_argument("--output-dir", help="输出目录")
    parser.add_argument("--no-feishu", action="store_true", help="禁用飞书推送")
    parser.add_argument("--chat-id", help="飞书 chat_id")

    args = parser.parse_args()

    # 运行监控
    result = run_competitor_monitor(
        provider=args.provider,
        max_results=args.max_results,
        output_dir=args.output_dir,
        push_feishu=not args.no_feishu,
        chat_id=args.chat_id
    )

    # 输出结果
    if result.get("success"):
        print("\n" + "=" * 60)
        print("竞品监控完成")
        print("=" * 60)
        print(f"报告文件: {result.get('report_file')}")
        print(f"飞书推送: {result.get('feishu_pushed', False)}")
        print(f"\n总摘要:\n{result.get('summary')}")
    else:
        print(f"\n[失败] {result.get('error')}")

    # 输出到 stdout（供其他脚本读取）
    print("\n[JSON Output]")
    print(json.dumps(result, indent=2, ensure_ascii=False))