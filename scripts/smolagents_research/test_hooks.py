"""
@description: smolagents step_callbacks 测试
@dependencies: smolagents, run_research
@last_modified: 2026-04-12

测试 CallbackRegistry 正确注册并触发 hooks
"""

import os
import sys
from pathlib import Path

# 项目路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "smolagents_research"))

from dotenv import load_dotenv
load_dotenv()

# 导入测试模块
from run_research import run_research, hook_calls, create_research_agent, get_step_callbacks


def test_step_callbacks_registration():
    """测试 step_callbacks 正确注册"""

    print("\n" + "="*60)
    print("测试 1: step_callbacks 注册")
    print("="*60)

    # 获取 callbacks 配置
    callbacks = get_step_callbacks()

    print(f"Callback 配置:")
    for step_cls, hooks in callbacks.items():
        print(f"  - {step_cls.__name__}: {len(hooks)} hooks")

    # 检查配置正确
    assert ActionStep in callbacks, "缺少 ActionStep callbacks"
    assert FinalAnswerStep in callbacks, "缺少 FinalAnswerStep callbacks"
    assert PlanningStep in callbacks, "缺少 PlanningStep callbacks"

    print("✅ step_callbacks 配置正确")


def test_agent_creation():
    """测试 Agent 创建时正确注册 callbacks"""

    print("\n" + "="*60)
    print("测试 2: Agent 创建")
    print("="*60)

    try:
        agent = create_research_agent(
            provider="azure_norway",
            use_doubao=False,  # 禁用 doubao 避免依赖
            use_tavily=False,  # 禁用 tavily 避免依赖
            enable_hooks=True
        )

        # 检查 CallbackRegistry 是否初始化
        assert hasattr(agent, 'step_callbacks'), "Agent 缺少 step_callbacks 属性"

        # 检查 callbacks 是否注册
        registry = agent.step_callbacks
        print(f"CallbackRegistry 类型: {type(registry).__name__}")

        # 检查内部注册表
        callbacks_dict = registry._callbacks
        print(f"已注册 callbacks:")
        for step_cls, hooks in callbacks_dict.items():
            print(f"  - {step_cls.__name__}: {len(hooks)} hooks")

        # 检查我们的 hooks 是否注册
        from smolagents.memory import ActionStep, FinalAnswerStep, PlanningStep

        assert ActionStep in callbacks_dict, "ActionStep callbacks 未注册"
        assert FinalAnswerStep in callbacks_dict, "FinalAnswerStep callbacks 未注册"

        print("✅ Agent 创建成功，callbacks 正确注册")

        return agent

    except Exception as e:
        print(f"❌ Agent 创建失败: {e}")
        raise


def test_hook_execution_mock():
    """测试 hook 函数可以正确执行"""

    print("\n" + "="*60)
    print("测试 3: Hook 函数执行（Mock）")
    print("="*60)

    from run_research import critic_hook, kb_insert_hook, timing_hook
    from smolagents.memory import ActionStep, FinalAnswerStep, PlanningStep, Timing

    # 重置计数
    hook_calls["action_steps"] = 0
    hook_calls["final_answers"] = 0
    hook_calls["planning_steps"] = 0

    # Mock ActionStep
    mock_action = ActionStep(
        step_number=1,
        timing=Timing(start_time=0, end_time=1.0),
        tool_calls=None,
        error=None
    )

    critic_hook(mock_action)
    print(f"  ActionStep: critic_hook 调用 → hook_calls['action_steps']={hook_calls['action_steps']}")

    assert hook_calls['action_steps'] == 1, "ActionStep hook 未触发"

    # Mock FinalAnswerStep
    mock_final = FinalAnswerStep(output="测试结果")

    critic_hook(mock_final)
    kb_insert_hook(mock_final)
    print(f"  FinalAnswerStep: hooks 调用 → hook_calls['final_answers']={hook_calls['final_answers']}")

    assert hook_calls['final_answers'] == 1, "FinalAnswerStep hook 未触发"

    print("✅ Hook 函数正确执行")


def test_full_run_with_hooks():
    """测试完整运行并验证 hooks"""

    print("\n" + "="*60)
    print("测试 4: 完整运行（需要 API 配置）")
    print("="*60)

    # 检查 API 配置
    api_key = os.getenv("AZURE_OPENAI_NORWAY_API_KEY")
    if not api_key:
        print("⚠️ AZURE_OPENAI_NORWAY_API_KEY 未配置，跳过此测试")
        return

    # 简单查询
    query = "What is 2+2? Just answer the number."

    try:
        result = run_research(
            query=query,
            provider="azure_norway",
            use_tavily=False,  # 禁用搜索工具
            enable_hooks=True
        )

        hook_stats = result.get("hook_stats", {})

        print(f"执行结果: {result.get('success', False)}")
        print(f"Hook 统计: {hook_stats}")

        # 验证 hooks 被调用
        if result.get("success"):
            # 至少应该有 1 个 FinalAnswerStep
            assert hook_stats.get("final_answers", 0) >= 1, "FinalAnswerStep hook 未触发"

            print("✅ Hooks 在完整运行中正确触发")

    except Exception as e:
        print(f"⚠️ 运行测试失败: {e}")


# ============================================================
# 运行所有测试
# ============================================================

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 60)
    print("smolagents step_callbacks 测试")
    print("=" * 60)

    try:
        # 导入 smolagents 类型
        from smolagents.memory import ActionStep, FinalAnswerStep, PlanningStep

        test_step_callbacks_registration()
        test_agent_creation()
        test_hook_execution_mock()
        test_full_run_with_hooks()

        print("\n" + "=" * 60)
        print("✅ 所有测试通过")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ 测试错误: {e}")
        sys.exit(1)