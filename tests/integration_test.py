"""集成测试 — 验证系统各组件可用性
@description: 测试模型网关、KB、学习系统、决策树、Claude CLI、降级链、图片生成
@dependencies: model_gateway, knowledge_base, claude_cli_helper
@last_modified: 2026-04-05
"""
import sys
import json
import os
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

TEST_RESULTS = []


def test_result(name: str, passed: bool, message: str = ""):
    """记录测试结果"""
    TEST_RESULTS.append({
        "name": name,
        "passed": passed,
        "message": message,
        "timestamp": datetime.now().isoformat()
    })
    status = "[PASS]" if passed else "[FAIL]"
    print(f"  {status} -- {name}")
    if message and not passed:
        print(f"       {message[:100]}")


def test_model_gateway():
    """测试模型网关调用"""
    print("\n=== 模型网关测试 ===")

    try:
        from scripts.litellm_gateway import get_model_gateway
        gw = get_model_gateway()
        test_result("gateway_import", True)

        # 测试 doubao_seed_lite（最稳定）
        result = gw.call("doubao_seed_lite", "回复: OK", task_type="integration_test")
        if result.get("success"):
            test_result("doubao_lite_call", True, result["response"][:50])
        else:
            test_result("doubao_lite_call", False, result.get("error", "unknown"))

        # 测试 gpt_4o_norway
        result = gw.call("gpt_4o_norway", "回复: OK", task_type="integration_test")
        if result.get("success"):
            test_result("gpt_4o_norway_call", True, result["response"][:50])
        else:
            test_result("gpt_4o_norway_call", False, result.get("error", "unknown"))

        # 测试 deepseek_v3_volcengine
        result = gw.call("deepseek_v3_volcengine", "回复: OK", task_type="integration_test")
        if result.get("success"):
            test_result("deepseek_v3_call", True, result["response"][:50])
        else:
            test_result("deepseek_v3_call", False, result.get("error", "unknown"))

    except Exception as e:
        test_result("model_gateway", False, str(e))


def test_knowledge_base():
    """测试 KB 读写"""
    print("\n=== 知识库测试 ===")

    try:
        from src.tools.knowledge_base import search_knowledge, add_knowledge
        test_result("kb_import", True)

        # 搜索测试
        results = search_knowledge("HUD", limit=3)
        test_result("kb_search", len(results) > 0, f"找到 {len(results)} 条")

    except Exception as e:
        test_result("knowledge_base", False, str(e))


def test_learning_system():
    """测试学习系统文件可写"""
    print("\n=== 学习系统测试 ===")

    try:
        learning_path = PROJECT_ROOT / ".ai-state" / "search_learning.jsonl"
        learning_path.parent.mkdir(parents=True, exist_ok=True)

        # 写入测试
        test_entry = {"test": "integration", "timestamp": datetime.now().isoformat()}
        with open(learning_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(test_entry, ensure_ascii=False) + "\n")

        test_result("learning_file_write", True)

    except Exception as e:
        test_result("learning_system", False, str(e))


def test_decision_tree():
    """测试决策树可读"""
    print("\n=== 决策树测试 ===")

    try:
        tree_path = PROJECT_ROOT / ".ai-state" / "product_decision_tree.yaml"
        if tree_path.exists():
            content = tree_path.read_text(encoding='utf-8')
            test_result("decision_tree_read", len(content) > 100, f"{len(content)} chars")
        else:
            test_result("decision_tree_read", False, "文件不存在")

    except Exception as e:
        test_result("decision_tree", False, str(e))


def test_claude_cli():
    """测试 Claude CLI"""
    print("\n=== Claude CLI 测试 ===")

    try:
        from scripts.claude_cli_helper import is_claude_cli_available, call_claude_cli
        available = is_claude_cli_available()
        test_result("claude_cli_available", available)

        if available:
            # 简单调用测试
            result = call_claude_cli("回复: OK", timeout=30)
            test_result("claude_cli_call", len(result) > 0, result[:50] if result else "无响应")

    except Exception as e:
        test_result("claude_cli", False, str(e))


def test_fallback_chains():
    """测试降级链"""
    print("\n=== 降级链测试 ===")

    try:
        from scripts.verify_fallback_chains import verify_all_chains
        success = verify_all_chains()
        test_result("fallback_chains", success)

    except Exception as e:
        test_result("fallback_chains", False, str(e))


def test_image_generation():
    """测试图片生成 (seedream)"""
    print("\n=== 图片生成测试 ===")

    try:
        from scripts.litellm_gateway import get_model_gateway
        gw = get_model_gateway()

        # 检查 seedream 是否在模型列表
        if "seedream_3_0" in gw.models:
            test_result("seedream_available", True)
            # 实际调用需要图片输入，这里只检查可用性
        else:
            test_result("seedream_available", False, "未注册")

    except Exception as e:
        test_result("image_generation", False, str(e))


def test_deepseek_r1():
    """测试 DeepSeek R1 (火山引擎)"""
    print("\n=== DeepSeek R1 测试 ===")

    try:
        from scripts.litellm_gateway import get_model_gateway
        gw = get_model_gateway()

        result = gw.call("deepseek_r1_volcengine", "1+1=?", task_type="integration_test")
        if result.get("success"):
            test_result("deepseek_r1_call", True, result["response"][:50])
        else:
            test_result("deepseek_r1_call", False, result.get("error", "unknown"))

    except Exception as e:
        test_result("deepseek_r1", False, str(e))


def run_all_tests():
    """运行所有集成测试"""
    print("=" * 50)
    print("集成测试 — 系统组件可用性验证")
    print("=" * 50)

    test_model_gateway()
    test_knowledge_base()
    test_learning_system()
    test_decision_tree()
    test_claude_cli()
    test_fallback_chains()
    test_image_generation()
    test_deepseek_r1()

    # 统计
    print("\n" + "=" * 50)
    passed = sum(1 for r in TEST_RESULTS if r["passed"])
    total = len(TEST_RESULTS)
    print(f"测试结果: {passed}/{total} 通过")

    # 写入日志
    log_path = PROJECT_ROOT / ".ai-state" / "integration_test_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        for r in TEST_RESULTS:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    if passed == total:
        print("[OK] 所有集成测试通过!")
        return True
    else:
        print(f"[WARN] {total - passed} 个测试失败")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)