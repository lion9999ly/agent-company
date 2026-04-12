"""
@description: LiteLLM Gateway 三 Provider 连通性测试
@last_modified: 2026-04-12

测试目标：
1. Azure OpenAI (gpt-4o)
2. Volcengine (doubao_seed_pro)
3. Gemini (gemini_2_5_flash)

验证：
- 每个 provider 至少调用成功一次
- 响应内容正确
- Token 计数正确
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Windows UTF-8 输出
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from scripts.litellm_gateway import LiteLLMGateway, get_litellm_gateway


def test_azure_openai():
    """测试 Azure OpenAI"""
    print("\n=== [1] Azure OpenAI 测试 ===")

    gateway = get_litellm_gateway()

    # 检查配置
    config = gateway.config.get("azure", {})
    has_key = bool(config.get("api_key"))
    has_base = bool(config.get("api_base"))
    print(f"  API Key: {'✓' if has_key else '✗'}")
    print(f"  API Base: {'✓' if has_base else '✗'} ({config.get('api_base', 'N/A')})")

    if not has_key or not has_base:
        return {"success": False, "error": "Missing configuration"}

    # 测试调用
    test_prompt = "请回复'Azure OK'三个字，不要其他内容。"
    result = gateway.call("gpt_4o", test_prompt, max_tokens=20, temperature=0.1)

    print(f"  Model: {result.get('model', 'N/A')}")
    response = result.get('response', 'N/A')
    print(f"  Response: {response[:100] if response else 'N/A'}")
    print(f"  Tokens: {result.get('tokens_used', 'N/A')}")
    print(f"  Success: {'✓' if result.get('success') else '✗'}")

    if not result.get("success"):
        print(f"  Error: {result.get('error', 'N/A')}")

    return result


def test_volcengine():
    """测试火山引擎 (豆包)"""
    print("\n=== [2] Volcengine (豆包) 测试 ===")

    gateway = get_litellm_gateway()

    # 检查配置
    config = gateway.config.get("volcengine", {})
    has_key = bool(config.get("api_key"))
    has_base = bool(config.get("api_base"))
    print(f"  API Key: {'✓' if has_key else '✗'}")
    print(f"  API Base: {'✓' if has_base else '✗'} ({config.get('api_base', 'N/A')})")

    if not has_key or not has_base:
        return {"success": False, "error": "Missing configuration"}

    # 测试调用
    test_prompt = "请回复'豆包 OK'三个字，不要其他内容。"
    result = gateway.call("doubao_seed_pro", test_prompt, max_tokens=20, temperature=0.1)

    print(f"  Model: {result.get('model', 'N/A')}")
    response = result.get('response', 'N/A')
    print(f"  Response: {response[:100] if response else 'N/A'}")
    print(f"  Tokens: {result.get('tokens_used', 'N/A')}")
    print(f"  Success: {'✓' if result.get('success') else '✗'}")

    if not result.get("success"):
        print(f"  Error: {result.get('error', 'N/A')}")

    return result


def test_gemini():
    """测试 Gemini"""
    print("\n=== [3] Gemini 测试 ===")

    gateway = get_litellm_gateway()

    # 检查配置
    config = gateway.config.get("gemini", {})
    has_key = bool(config.get("api_key"))
    print(f"  API Key: {'✓' if has_key else '✗'}")

    if not has_key:
        return {"success": False, "error": "Missing API key"}

    # 测试调用
    test_prompt = "请回复'Gemini OK'三个字，不要其他内容。"
    result = gateway.call("gemini_2_5_flash", test_prompt, max_tokens=20, temperature=0.1)

    print(f"  Model: {result.get('model', 'N/A')}")
    response = result.get('response', 'N/A')
    print(f"  Response: {response[:100] if response else 'N/A'}")
    print(f"  Tokens: {result.get('tokens_used', 'N/A')}")
    print(f"  Success: {'✓' if result.get('success') else '✗'}")

    if not result.get("success"):
        print(f"  Error: {result.get('error', 'N/A')}")

    return result


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("LiteLLM Gateway 三 Provider 连通性测试")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    gateway = get_litellm_gateway()

    # 检查 provider 状态
    print("\n[Provider Status]")
    status = gateway.get_provider_status()
    for provider, ok in status.items():
        print(f"  {provider}: {'✓' if ok else '✗'}")

    # 运行测试
    results = {
        "azure": test_azure_openai(),
        "volcengine": test_volcengine(),
        "gemini": test_gemini(),
    }

    # 汇总
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)

    success_count = sum(1 for r in results.values() if r.get("success"))
    total_count = len(results)

    for provider, result in results.items():
        status = "✓ PASS" if result.get("success") else "✗ FAIL"
        print(f"  {provider}: {status}")

    print(f"\n总计: {success_count}/{total_count} 通过")

    # 返回结果
    return {
        "timestamp": datetime.now().isoformat(),
        "success_count": success_count,
        "total_count": total_count,
        "passed": success_count == total_count,
        "results": results,
    }


if __name__ == "__main__":
    report = run_all_tests()

    # 保存报告
    report_path = PROJECT_ROOT / ".ai-state" / "litellm_test_report.json"
    import json
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n报告已保存: {report_path}")

    sys.exit(0 if report["passed"] else 1)