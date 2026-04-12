"""
@description: smolagents 深度研究端到端测试
@last_modified: 2026-04-12

测试目标：
- Tavily 搜索 "SeeYA 0.49 OLED microdisplay specifications"
- 验证 Tool 注册正确
- 验证 Agent 能调用搜索并返回结果
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Windows UTF-8 输出
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# 添加项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

# 导入 smolagents 模块
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_research import create_research_agent, get_model_config


def test_tavily_search_tool():
    """测试 TavilySearchTool 直接调用"""
    print("\n=== [1] 测试 TavilySearchTool 直接调用 ===")

    from tavily_search_tool import TavilySearchTool

    tool = TavilySearchTool()
    try:
        tool.setup()
        print(f"  Tool Name: {tool.name}")
        print(f"  Description: {tool.description}")
        print(f"  Initialized: {tool.is_initialized}")

        # 执行搜索
        query = "SeeYA 0.49 OLED microdisplay specifications"
        print(f"\n  Query: {query}")
        result = tool.forward(query, max_results=3)

        print(f"\n  Result (前500字):\n{result[:500]}...")
        return {"success": True, "result": result}

    except ValueError as e:
        print(f"  Error: {e}")
        print("  Tavily API Key 未配置，跳过此测试")
        return {"success": False, "error": str(e), "skipped": True}


def test_agent_with_tavily():
    """测试 Agent 调用 Tavily 搜索"""
    print("\n=== [2] 测试 Agent 端到端调用 ===")

    # 检查环境变量
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        print("  TAVILY_API_KEY 未配置，跳过端到端测试")
        return {"success": False, "error": "TAVILY_API_KEY not set", "skipped": True}

    try:
        # 创建 Agent
        print("  创建 Agent...")
        agent = create_research_agent(
            model_name="gpt_4o",
            provider="azure_norway",
            use_tavily=True
        )

        print(f"  Agent Tools: {list(agent.tools.keys())}")

        # 运行研究
        query = "SeeYA 0.49 OLED microdisplay specifications"
        print(f"\n  Query: {query}")
        print("  执行中...")

        start = datetime.now()
        result = agent.run(query)
        elapsed = (datetime.now() - start).total_seconds()

        print(f"\n  耗时: {elapsed:.1f}s")

        # 处理结果（可能是字典）
        if isinstance(result, dict):
            import json
            result_str = json.dumps(result, indent=2, ensure_ascii=False)
            print(f"  Result:\n{result_str[:1000]}...")
        else:
            print(f"  Result:\n{str(result)[:1000]}...")

        return {
            "success": True,
            "result": result,
            "elapsed": elapsed,
        }

    except Exception as e:
        print(f"  Error: {e}")
        return {"success": False, "error": str(e)}


def test_model_config():
    """测试模型配置"""
    print("\n=== [3] 测试模型配置 ===")

    providers = ["azure_norway", "volcengine", "gemini"]

    for provider in providers:
        print(f"\n  Provider: {provider}")
        try:
            config = get_model_config(provider)
            print(f"    Model: {config['model']}")
            print(f"    API Key: {'✓' if config.get('api_key') else '✗'}")
            print(f"    API Base: {config.get('api_base', 'N/A')}")
        except ValueError as e:
            print(f"    Error: {e}")

    return {"success": True}


def run_all_tests():
    """运行所有测试"""
    print("="*60)
    print("smolagents 深度研究端到端测试")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    results = {
        "timestamp": datetime.now().isoformat(),
        "tests": {}
    }

    # 1. 测试 Tool 直接调用
    results["tests"]["tavily_tool"] = test_tavily_search_tool()

    # 2. 测试 Agent 端到端
    results["tests"]["agent_e2e"] = test_agent_with_tavily()

    # 3. 测试模型配置
    results["tests"]["model_config"] = test_model_config()

    # 汇总
    print("\n" + "="*60)
    print("测试汇总")
    print("="*60)

    passed = 0
    skipped = 0
    for name, result in results["tests"].items():
        if result.get("skipped"):
            status = "⚠ SKIP"
            skipped += 1
        elif result.get("success"):
            status = "✓ PASS"
            passed += 1
        else:
            status = "✗ FAIL"
        print(f"  {name}: {status}")

    print(f"\n通过: {passed}, 跳过: {skipped}, 失败: {len(results['tests']) - passed - skipped}")

    # 保存报告
    report_path = PROJECT_ROOT / ".ai-state" / "smolagents_test_report.json"
    import json
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n报告已保存: {report_path}")

    return results


if __name__ == "__main__":
    run_all_tests()