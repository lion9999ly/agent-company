"""
@description: 搜索层对比测试 - 旧管道 vs 新管道（smolagents）
@dependencies: smolagents, tavily_search_tool, doubao_search_tool, model_gateway
@last_modified: 2026-04-12

测试目标：
1. 对比搜索结果质量（字数、结构化程度、信息密度）
2. 对比耗时
3. 验证 smolagents 工具接入是否正常
"""

import sys
import time
import json
from pathlib import Path

# 添加项目根目录到 Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# === 新管道：smolagents 工具 ===
from scripts.smolagents_research.tavily_search_tool import TavilySearchTool
from scripts.smolagents_research.doubao_search_tool import DoubaoSearchTool

# === 旧管道：直接 API 调用 ===
from scripts.litellm_gateway import call_for_search
from scripts.deep_research.models import call_model


def test_tavily_old(query: str) -> dict:
    """旧管道 Tavily 搜索"""
    start = time.time()
    try:
        result = call_for_search(query, engine='tavily')
        elapsed = time.time() - start
        if result and result.get('success'):
            response = result.get('response', '')
            return {
                "method": "old_tavily",
                "success": True,
                "response": response,
                "chars": len(response),
                "elapsed_sec": elapsed,
                "has_structure": "## " in response or "**" in response
            }
        return {
            "method": "old_tavily",
            "success": False,
            "error": str(result),
            "elapsed_sec": elapsed
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "method": "old_tavily",
            "success": False,
            "error": str(e),
            "elapsed_sec": elapsed
        }


def test_tavily_new(query: str) -> dict:
    """新管道 smolagents Tavily 搜索"""
    start = time.time()
    try:
        tool = TavilySearchTool()
        result = tool.forward(
            query=query,
            search_depth="advanced",
            max_results=5,
            include_raw_content=False
        )
        elapsed = time.time() - start
        if result and len(result) > 50:
            return {
                "method": "new_tavily_smolagents",
                "success": True,
                "response": result,
                "chars": len(result),
                "elapsed_sec": elapsed,
                "has_structure": "## " in result or "**" in result
            }
        return {
            "method": "new_tavily_smolagents",
            "success": False,
            "error": "result too short or empty",
            "elapsed_sec": elapsed
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "method": "new_tavily_smolagents",
            "success": False,
            "error": str(e),
            "elapsed_sec": elapsed
        }


def test_doubao_old(query: str) -> dict:
    """旧管道 doubao 搜索"""
    start = time.time()
    try:
        result = call_model('doubao_seed_pro', query,
            system_prompt="你是一个搜索助手。请搜索并返回相关信息。",
            task_type='search')
        elapsed = time.time() - start
        if result and result.get('success'):
            response = result.get('response', '')
            return {
                "method": "old_doubao",
                "success": True,
                "response": response,
                "chars": len(response),
                "elapsed_sec": elapsed,
                "has_structure": "## " in response or "**" in response
            }
        return {
            "method": "old_doubao",
            "success": False,
            "error": str(result),
            "elapsed_sec": elapsed
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "method": "old_doubao",
            "success": False,
            "error": str(e),
            "elapsed_sec": elapsed
        }


def test_doubao_new(query: str) -> dict:
    """新管道 smolagents doubao 搜索"""
    start = time.time()
    try:
        tool = DoubaoSearchTool()
        result = tool.forward(query=query, num_results=5)
        elapsed = time.time() - start
        if result and len(result) > 50:
            return {
                "method": "new_doubao_smolagents",
                "success": True,
                "response": result,
                "chars": len(result),
                "elapsed_sec": elapsed,
                "has_structure": "## " in result or "**" in result
            }
        return {
            "method": "new_doubao_smolagents",
            "success": False,
            "error": "result too short or empty",
            "elapsed_sec": elapsed
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "method": "new_doubao_smolagents",
            "success": False,
            "error": str(e),
            "elapsed_sec": elapsed
        }


def run_comparison_test(test_queries: list) -> dict:
    """运行完整对比测试"""
    results = {
        "test_time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "queries": test_queries,
        "tavily_comparison": [],
        "doubao_comparison": [],
        "summary": {}
    }

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"测试查询: {query}")
        print(f"{'='*60}")

        # Tavily 对比
        print("\n[Tavily] 旧管道测试...")
        old_tavily = test_tavily_old(query)
        print(f"  结果: {old_tavily.get('success', False)}, "
              f"字数: {old_tavily.get('chars', 0)}, "
              f"耗时: {old_tavily.get('elapsed_sec', 0):.2f}s")

        print("[Tavily] 新管道测试...")
        new_tavily = test_tavily_new(query)
        print(f"  结果: {new_tavily.get('success', False)}, "
              f"字数: {new_tavily.get('chars', 0)}, "
              f"耗时: {new_tavily.get('elapsed_sec', 0):.2f}s")

        results["tavily_comparison"].append({
            "query": query,
            "old": old_tavily,
            "new": new_tavily
        })

        # Doubao 对比（中文查询）
        if any('\u4e00' <= c <= '\u9fff' for c in query):
            print("\n[Doubao] 旧管道测试...")
            old_doubao = test_doubao_old(query)
            print(f"  结果: {old_doubao.get('success', False)}, "
                  f"字数: {old_doubao.get('chars', 0)}, "
                  f"耗时: {old_doubao.get('elapsed_sec', 0):.2f}s")

            print("[Doubao] 新管道测试...")
            new_doubao = test_doubao_new(query)
            print(f"  结果: {new_doubao.get('success', False)}, "
                  f"字数: {new_doubao.get('chars', 0)}, "
                  f"耗时: {new_doubao.get('elapsed_sec', 0):.2f}s")

            results["doubao_comparison"].append({
                "query": query,
                "old": old_doubao,
                "new": new_doubao
            })

    # 汇总
    tavily_old_success = sum(1 for r in results["tavily_comparison"] if r["old"].get("success"))
    tavily_new_success = sum(1 for r in results["tavily_comparison"] if r["new"].get("success"))
    tavily_old_chars = sum(r["old"].get("chars", 0) for r in results["tavily_comparison"] if r["old"].get("success"))
    tavily_new_chars = sum(r["new"].get("chars", 0) for r in results["tavily_comparison"] if r["new"].get("success"))
    tavily_old_time = sum(r["old"].get("elapsed_sec", 0) for r in results["tavily_comparison"])
    tavily_new_time = sum(r["new"].get("elapsed_sec", 0) for r in results["tavily_comparison"])

    doubao_old_success = sum(1 for r in results["doubao_comparison"] if r["old"].get("success"))
    doubao_new_success = sum(1 for r in results["doubao_comparison"] if r["new"].get("success"))
    doubao_old_chars = sum(r["old"].get("chars", 0) for r in results["doubao_comparison"] if r["old"].get("success"))
    doubao_new_chars = sum(r["new"].get("chars", 0) for r in results["doubao_comparison"] if r["new"].get("success"))
    doubao_old_time = sum(r["old"].get("elapsed_sec", 0) for r in results["doubao_comparison"])
    doubao_new_time = sum(r["new"].get("elapsed_sec", 0) for r in results["doubao_comparison"])

    results["summary"] = {
        "tavily": {
            "old_success_rate": f"{tavily_old_success}/{len(results['tavily_comparison'])}",
            "new_success_rate": f"{tavily_new_success}/{len(results['tavily_comparison'])}",
            "old_avg_chars": tavily_old_chars // max(tavily_old_success, 1),
            "new_avg_chars": tavily_new_chars // max(tavily_new_success, 1),
            "old_total_time": f"{tavily_old_time:.2f}s",
            "new_total_time": f"{tavily_new_time:.2f}s",
            "time_diff": f"{tavily_new_time - tavily_old_time:.2f}s"
        },
        "doubao": {
            "old_success_rate": f"{doubao_old_success}/{len(results['doubao_comparison'])}",
            "new_success_rate": f"{doubao_new_success}/{len(results['doubao_comparison'])}",
            "old_avg_chars": doubao_old_chars // max(doubao_old_success, 1),
            "new_avg_chars": doubao_new_chars // max(doubao_new_success, 1),
            "old_total_time": f"{doubao_old_time:.2f}s",
            "new_total_time": f"{doubao_new_time:.2f}s",
            "time_diff": f"{doubao_new_time - doubao_old_time:.2f}s"
        }
    }

    return results


def generate_report(results: dict) -> str:
    """生成测试报告"""
    report = []
    report.append("# 搜索层对比测试报告")
    report.append(f"\n测试时间: {results['test_time']}")
    report.append(f"\n测试查询数: {len(results['queries'])}")

    report.append("\n## 测试查询列表")
    for i, q in enumerate(results['queries'], 1):
        report.append(f"{i}. {q}")

    report.append("\n## Tavily 搜索对比")
    tavily_sum = results["summary"]["tavily"]
    report.append(f"\n| 指标 | 旧管道 | 新管道 | 差异 |")
    report.append(f"|------|--------|--------|------|")
    report.append(f"| 成功率 | {tavily_sum['old_success_rate']} | {tavily_sum['new_success_rate']} | - |")
    report.append(f"| 平均字数 | {tavily_sum['old_avg_chars']} | {tavily_sum['new_avg_chars']} | {tavily_sum['new_avg_chars'] - tavily_sum['old_avg_chars']} |")
    report.append(f"| 总耗时 | {tavily_sum['old_total_time']} | {tavily_sum['new_total_time']} | {tavily_sum['time_diff']} |")

    report.append("\n### Tavily 详细结果")
    for item in results["tavily_comparison"]:
        report.append(f"\n**查询: {item['query']}**")
        old = item['old']
        new = item['new']
        report.append(f"- 旧管道: success={old.get('success')}, chars={old.get('chars', 0)}, time={old.get('elapsed_sec', 0):.2f}s")
        report.append(f"- 新管道: success={new.get('success')}, chars={new.get('chars', 0)}, time={new.get('elapsed_sec', 0):.2f}s")
        if old.get('success') and new.get('success'):
            if old.get('chars', 0) > new.get('chars', 0):
                report.append(f"- 结论: 旧管道字数更多")
            elif new.get('chars', 0) > old.get('chars', 0):
                report.append(f"- 结论: 新管道字数更多")
            else:
                report.append(f"- 结论: 字数相近")

    if results["doubao_comparison"]:
        report.append("\n## Doubao 搜索对比")
        doubao_sum = results["summary"]["doubao"]
        report.append(f"\n| 指标 | 旧管道 | 新管道 | 差异 |")
        report.append(f"|------|--------|--------|------|")
        report.append(f"| 成功率 | {doubao_sum['old_success_rate']} | {doubao_sum['new_success_rate']} | - |")
        report.append(f"| 平均字数 | {doubao_sum['old_avg_chars']} | {doubao_sum['new_avg_chars']} | {doubao_sum['new_avg_chars'] - doubao_sum['old_avg_chars']} |")
        report.append(f"| 总耗时 | {doubao_sum['old_total_time']} | {doubao_sum['new_total_time']} | {doubao_sum['time_diff']} |")

        report.append("\n### Doubao 详细结果")
        for item in results["doubao_comparison"]:
            report.append(f"\n**查询: {item['query']}**")
            old = item['old']
            new = item['new']
            report.append(f"- 旧管道: success={old.get('success')}, chars={old.get('chars', 0)}, time={old.get('elapsed_sec', 0):.2f}s")
            report.append(f"- 新管道: success={new.get('success')}, chars={new.get('chars', 0)}, time={new.get('elapsed_sec', 0):.2f}s")

    report.append("\n## 结论")
    tavily_new_ok = tavily_sum['new_success_rate'].startswith(str(len(results['tavily_comparison'])))
    report.append(f"- Tavily 新管道可用: {tavily_new_ok}")
    if results["doubao_comparison"]:
        doubao_new_ok = doubao_sum['new_success_rate'].startswith(str(len(results['doubao_comparison'])))
        report.append(f"- Doubao 新管道可用: {doubao_new_ok}")

    report.append(f"\n## 建议")
    if tavily_new_ok:
        report.append("- Tavily smolagents 工具接入成功，可替代旧管道")
    else:
        report.append("- ⚠️ Tavily smolagents 工具存在问题，需排查")

    return "\n".join(report)


if __name__ == "__main__":
    # 测试查询
    test_queries = [
        "智能骑行头盔 AR显示技术 2026",
        "骨传导耳机 供应商 歌尔",
        "光波导显示 module specification",
    ]

    print("="*60)
    print("搜索层对比测试：旧管道 vs 新管道（smolagents）")
    print("="*60)

    results = run_comparison_test(test_queries)
    report = generate_report(results)

    # 保存结果
    output_dir = Path(__file__).resolve().parent.parent.parent / ".ai-state"
    output_file = output_dir / "search_layer_comparison.md"
    output_file.write_text(report, encoding="utf-8")
    print(f"\n报告已保存: {output_file}")

    # 也保存 JSON 结果
    json_file = output_dir / "search_layer_comparison.json"
    json_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON 已保存: {json_file}")

    print("\n" + report)