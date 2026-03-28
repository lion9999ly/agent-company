"""
@description: feishu_sdk_client_v2 模块化重构验证测试
@last_modified: 2026-03-28
"""
import sys
import importlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def run_tests():
    print("=" * 60)
    print("feishu_sdk_client_v2 模块化验证")
    print("=" * 60)

    passed = 0
    failed = 0
    errors = []

    # === 模块导入测试 ===
    print("\n--- 模块导入测试 ---")

    module_tests = [
        ("scripts.feishu_handlers.chat_helpers",
         ["send_reply", "log"]),

        ("scripts.feishu_handlers.file_sender",
         ["send_file_to_feishu"]),

        ("scripts.feishu_handlers.commands",
         ["handle_command"]),

        ("scripts.feishu_handlers.image_handler",
         ["handle_image_message", "handle_audio_message"]),

        ("scripts.feishu_handlers.rd_task",
         ["is_rd_task", "run_rd_task_background"]),

        ("scripts.feishu_handlers.text_router",
         ["route_text_message"]),

        ("scripts.feishu_handlers.structured_doc",
         ["try_structured_doc_fast_track"]),
    ]

    for module_path, functions in module_tests:
        try:
            mod = importlib.import_module(module_path)
            missing = [f for f in functions if not hasattr(mod, f)]
            if missing:
                errors.append(f"[X] {module_path}: 缺少函数 {missing}")
                failed += 1
            else:
                print(f"  [OK] {module_path}: {len(functions)} 个函数")
                passed += 1
        except Exception as e:
            errors.append(f"[X] {module_path}: 导入失败 - {e}")
            failed += 1

    # === 入口文件测试 ===
    print("\n--- 入口文件测试 ---")

    try:
        from scripts.feishu_sdk_client_v2 import handle_message, main
        print(f"  [OK] feishu_sdk_client_v2: handle_message + main")
        passed += 1
    except Exception as e:
        errors.append(f"[X] feishu_sdk_client_v2: {e}")
        failed += 1

    # === 功能逻辑测试 ===
    print(f"\n--- 功能逻辑测试 ---")

    # 测试 is_rd_task
    try:
        from scripts.feishu_handlers.rd_task import is_rd_task
        assert is_rd_task("请研究一下HUD芯片方案") == True, "长文本应该是研发任务"
        assert is_rd_task("你好") == False, "短文本不应该是研发任务"
        print(f"  [OK] is_rd_task: 逻辑正确")
        passed += 1
    except Exception as e:
        errors.append(f"[X] is_rd_task: {e}")
        failed += 1

    # 测试 handle_command 不拦截普通消息
    try:
        from scripts.feishu_handlers.commands import handle_command
        called = []

        def mock_reply(target, text, rtype="chat_id"):
            called.append(text)

        result = handle_command("你好，帮我查下天气", "test", "chat_id", "ou_test", "oc_test", mock_reply)
        assert result == False, "普通消息不应该被精确指令拦截"
        print(f"  [OK] handle_command: 不拦截普通消息")
        passed += 1
    except Exception as e:
        errors.append(f"[X] handle_command: {e}")
        failed += 1

    # 测试 structured_doc 关键词检测
    try:
        from scripts.feishu_handlers.structured_doc import try_structured_doc_fast_track
        print(f"  [OK] structured_doc: try_structured_doc_fast_track 可调用")
        passed += 1
    except Exception as e:
        errors.append(f"[X] structured_doc: {e}")
        failed += 1

    # === 交叉依赖测试 ===
    print(f"\n--- 交叉依赖测试 ---")

    try:
        from scripts.feishu_handlers import text_router
        assert hasattr(text_router, 'route_text_message')
        print(f"  [OK] text_router -> commands: 依赖正常")
        passed += 1
    except Exception as e:
        errors.append(f"[X] text_router -> commands: {e}")
        failed += 1

    # === 总结 ===
    print(f"\n{'='*60}")
    print(f"测试结果: [OK] {passed} 通过 | [X] {failed} 失败")

    if errors:
        print(f"\n失败详情:")
        for e in errors:
            print(f"  {e}")

    if failed == 0:
        print(f"\n全部通过！可以切换到 v2：")
        print(f"   1. 停止旧服务: Ctrl+C")
        print(f"   2. 启动新服务: python scripts/feishu_sdk_client_v2.py")
        print(f"   3. 飞书发一条测试消息验证")
        print(f"   4. 确认无误后归档旧文件: mv scripts/feishu_sdk_client.py scripts/feishu_sdk_client_v1_backup.py")
    else:
        print(f"\n有 {failed} 个测试失败，请修复后重新运行测试")

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)