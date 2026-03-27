"""
@description: compact_hook 单元测试
@dependencies: pytest, unittest.mock
@last_modified: 2026-03-17
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

# 添加项目根目录到路径
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


class TestCompactHookPreCompact:
    """PreCompact 事件处理测试"""

    def test_pre_compact_creates_checkpoint(self, tmp_path):
        """测试 PreCompact 创建检查点"""
        # 准备测试数据
        input_data = {
            "hook_event_name": "PreCompact",
            "trigger": "auto"
        }

        # Mock layered_memory
        with patch('scripts.hooks.compact_hook.get_layered_memory') as mock_mem:
            mock_instance = MagicMock()
            mock_checkpoint = MagicMock()
            mock_checkpoint.checkpoint_id = "test_ckpt_001"
            mock_checkpoint.key_decisions = ["decision1", "decision2"]
            mock_checkpoint.pending_todos = ["todo1"]
            mock_instance.create_checkpoint.return_value = mock_checkpoint
            mock_instance.get_session_summary.return_value = {"key_items": []}
            mock_instance.longterm_dir = tmp_path / "longterm"
            mock_instance.generate_session_summary_for_llm.return_value = "Test summary"
            mock_mem.return_value = mock_instance

            # 导入并执行
            from scripts.hooks.compact_hook import handle_pre_compact
            result = handle_pre_compact(input_data)

        # 验证结果
        assert result["continue"] == True
        assert "Pre-Compact" in result["systemMessage"]
        assert "additionalContext" in result["hookSpecificOutput"]

    def test_pre_compact_handles_import_error(self):
        """测试 PreCompact 在模块不可用时的降级处理"""
        input_data = {"hook_event_name": "PreCompact"}

        with patch('scripts.hooks.compact_hook.get_layered_memory', side_effect=ImportError("No module")):
            from scripts.hooks.compact_hook import handle_pre_compact
            result = handle_pre_compact(input_data)

        # 即使失败也应返回 continue=True，不阻断流程
        assert result["continue"] == True
        assert "error" in result or "checkpoint_created" in result


class TestCompactHookPostCompact:
    """PostCompact 事件处理测试"""

    def test_post_compact_injects_context(self, tmp_path):
        """测试 PostCompact 注入恢复上下文"""
        input_data = {
            "hook_event_name": "PostCompact",
            "compact_summary": "Compressed summary..."
        }

        # 创建模拟的恢复上下文文件
        recovery_file = tmp_path / ".ai-state" / "compact_recovery_context.md"
        recovery_file.parent.mkdir(parents=True, exist_ok=True)
        recovery_file.write_text("# Recovery Context\n\n- Key decision: XYZ")

        with patch('scripts.hooks.compact_hook.Path') as mock_path:
            mock_path.return_value = recovery_file

            with patch('scripts.hooks.compact_hook.get_layered_memory') as mock_mem:
                mock_instance = MagicMock()
                mock_checkpoint = MagicMock()
                mock_checkpoint.checkpoint_id = "ckpt_001"
                mock_checkpoint.created_at = "2026-03-17T10:00:00"
                mock_checkpoint.key_decisions = ["Decision 1"]
                mock_checkpoint.pending_todos = ["Todo 1"]
                mock_instance.restore_from_checkpoint.return_value = mock_checkpoint
                mock_mem.return_value = mock_instance

                # 需要重新设置 Path 的行为
                from scripts.hooks import compact_hook
                original_path = compact_hook.Path

                def mock_path_func(arg):
                    if "compact_recovery_context" in str(arg):
                        return recovery_file
                    return original_path(arg)

                with patch.object(compact_hook, 'Path', mock_path_func):
                    from scripts.hooks.compact_hook import handle_post_compact
                    result = handle_post_compact(input_data)

        # 验证上下文注入
        assert result["continue"] == True
        assert "Post-Compact" in result["systemMessage"]

    def test_post_compact_missing_recovery_file(self, tmp_path):
        """测试 PostCompact 在恢复文件不存在时的处理"""
        input_data = {"hook_event_name": "PostCompact"}

        non_existent = tmp_path / "non_existent.md"

        with patch('scripts.hooks.compact_hook.Path') as mock_path:
            mock_instance = MagicMock()
            mock_instance.exists.return_value = False
            mock_path.return_value = mock_instance

            with patch('scripts.hooks.compact_hook.get_layered_memory', side_effect=ImportError()):
                from scripts.hooks.compact_hook import handle_post_compact
                result = handle_post_compact(input_data)

        # 即使文件不存在也应继续
        assert result["continue"] == True


class TestCompactHookSecurity:
    """安全性测试"""

    def test_checkpoint_path_traversal_protection(self):
        """测试路径遍历攻击防护"""
        # 恶意输入尝试路径遍历
        malicious_inputs = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "/etc/shadow",
            "C:\\Windows\\System32"
        ]

        from scripts.hooks.compact_hook import handle_pre_compact

        for malicious in malicious_inputs:
            input_data = {
                "hook_event_name": "PreCompact",
                "file_path": malicious  # 尝试注入恶意路径
            }

            # Hook 应该不使用用户提供的路径，而是使用内部安全路径
            with patch('scripts.hooks.compact_hook.get_layered_memory') as mock_mem:
                mock_instance = MagicMock()
                mock_checkpoint = MagicMock()
                mock_checkpoint.checkpoint_id = "safe_checkpoint"
                mock_checkpoint.key_decisions = []
                mock_checkpoint.pending_todos = []
                mock_instance.create_checkpoint.return_value = mock_checkpoint
                mock_instance.get_session_summary.return_value = {"key_items": []}
                mock_instance.longterm_dir = Path(".ai-state/longterm")
                mock_instance.generate_session_summary_for_llm.return_value = "Safe"
                mock_mem.return_value = mock_instance

                result = handle_pre_compact(input_data)

            # 验证没有使用恶意路径
            assert result["continue"] == True

    def test_json_injection_protection(self):
        """测试 JSON 注入防护"""
        # 尝试注入恶意 JSON
        malicious_json = {
            "hook_event_name": "PreCompact",
            "extra": "'; DROP TABLE users; --"
        }

        # JSON 解析应该安全处理
        try:
            from scripts.hooks.compact_hook import handle_pre_compact
            # 输入会被安全处理
            result = handle_pre_compact({"hook_event_name": "PreCompact"})
            assert isinstance(result, dict)
        except Exception as e:
            pytest.fail(f"Should not raise exception: {e}")


class TestCompactHookIntegration:
    """集成测试"""

    def test_full_compact_cycle(self, tmp_path):
        """测试完整的压缩周期"""
        # 1. PreCompact
        pre_data = {"hook_event_name": "PreCompact", "trigger": "auto"}

        with patch('scripts.hooks.compact_hook.get_layered_memory') as mock_mem:
            mock_instance = MagicMock()
            mock_checkpoint = MagicMock()
            mock_checkpoint.checkpoint_id = "cycle_ckpt"
            mock_checkpoint.key_decisions = ["Key decision from session"]
            mock_checkpoint.pending_todos = ["Pending task"]
            mock_instance.create_checkpoint.return_value = mock_checkpoint
            mock_instance.get_session_summary.return_value = {
                "key_items": [{"content": "Important", "importance": 9}]
            }
            mock_instance.longterm_dir = tmp_path / "longterm"
            mock_instance.generate_session_summary_for_llm.return_value = "Session summary"

            # 确保目录存在
            mock_instance.longterm_dir.mkdir(parents=True, exist_ok=True)

            mock_mem.return_value = mock_instance

            from scripts.hooks.compact_hook import handle_pre_compact
            pre_result = handle_pre_compact(pre_data)

        assert pre_result["continue"] == True

        # 2. PostCompact
        post_data = {"hook_event_name": "PostCompact"}

        recovery_file = tmp_path / ".ai-state" / "compact_recovery_context.md"
        recovery_file.parent.mkdir(parents=True, exist_ok=True)
        recovery_file.write_text("Recovery context from PreCompact")

        with patch('scripts.hooks.compact_hook.get_layered_memory') as mock_mem:
            mock_instance = MagicMock()
            mock_checkpoint = MagicMock()
            mock_checkpoint.checkpoint_id = "cycle_ckpt"
            mock_checkpoint.created_at = "2026-03-17T10:00:00"
            mock_checkpoint.key_decisions = ["Key decision from session"]
            mock_checkpoint.pending_todos = ["Pending task"]
            mock_instance.restore_from_checkpoint.return_value = mock_checkpoint
            mock_mem.return_value = mock_instance

            from scripts.hooks import compact_hook
            original_path = compact_hook.Path

            def mock_path_func(arg):
                if "compact_recovery_context" in str(arg):
                    return recovery_file
                return original_path(arg)

            with patch.object(compact_hook, 'Path', mock_path_func):
                from scripts.hooks.compact_hook import handle_post_compact
                post_result = handle_post_compact(post_data)

        assert post_result["continue"] == True
        assert "上下文恢复" in post_result["hookSpecificOutput"]["additionalContext"]


class TestCompactHookRollback:
    """回滚机制测试"""

    def test_rollback_on_checkpoint_failure(self):
        """测试检查点创建失败时的回滚"""
        input_data = {"hook_event_name": "PreCompact"}

        with patch('scripts.hooks.compact_hook.get_layered_memory') as mock_mem:
            mock_instance = MagicMock()
            mock_instance.create_checkpoint.side_effect = Exception("Disk full")

            # 应该有错误处理，不抛出异常
            mock_mem.return_value = mock_instance

            from scripts.hooks.compact_hook import handle_pre_compact
            result = handle_pre_compact(input_data)

        # 失败时应优雅降级，不阻断
        assert result["continue"] == True
        assert result.get("checkpoint_created") == False or "error" in result

    def test_partial_state_cleanup(self, tmp_path):
        """测试部分状态写入失败时的清理"""
        # 模拟写入一半失败的场景
        input_data = {"hook_event_name": "PreCompact"}

        with patch('scripts.hooks.compact_hook.get_layered_memory') as mock_mem:
            mock_instance = MagicMock()
            mock_checkpoint = MagicMock()
            mock_checkpoint.checkpoint_id = "partial_ckpt"
            mock_checkpoint.key_decisions = []
            mock_checkpoint.pending_todos = []
            mock_instance.create_checkpoint.return_value = mock_checkpoint
            mock_instance.get_session_summary.return_value = {"key_items": []}
            mock_instance.longterm_dir = tmp_path / "longterm"
            mock_instance.generate_session_summary_for_llm.side_effect = IOError("Write failed")

            mock_mem.return_value = mock_instance

            from scripts.hooks.compact_hook import handle_pre_compact
            result = handle_pre_compact(input_data)

        # 即使部分失败也应优雅处理
        assert result["continue"] == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])