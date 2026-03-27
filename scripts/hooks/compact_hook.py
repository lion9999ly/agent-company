"""
@description: 上下文压缩Hook - PreCompact/PostCompact事件处理
@dependencies: sys, json, datetime, shutil
@last_modified: 2026-03-17

触发时机:
- PreCompact: 压缩发生前
- PostCompact: 压缩完成后

核心功能:
1. 压缩前：创建检查点，保存关键上下文到分层记忆
2. 压缩后：注入恢复上下文，确保连续性

安全性说明:
- 检查点文件存储在 .ai-state/ 目录下，该目录应加入 .gitignore
- 文件权限: 仅当前用户可读写 (0o600)
- 路径验证: 所有文件操作使用相对于项目根目录的安全路径
- 回滚机制: 创建失败时自动清理部分状态

使用: 通过 stdin 接收 JSON，自动处理
"""

import sys
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

# 添加项目根目录到 Python 路径
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# 安全常量
AI_STATE_DIR = Path(".ai-state")
CHECKPOINT_DIR = AI_STATE_DIR / "layered_memory" / "checkpoints"
RECOVERY_FILE = AI_STATE_DIR / "compact_recovery_context.md"
LONGTERM_DIR = AI_STATE_DIR / "layered_memory" / "longterm"

# 临时文件后缀，用于回滚识别
TEMP_SUFFIX = ".tmp"


def _ensure_secure_dir(path: Path) -> bool:
    """
    安全创建目录，设置适当权限

    Args:
        path: 目录路径

    Returns:
        是否成功
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        # Windows 不支持 chmod，但 Unix 系统需要设置
        if sys.platform != "win32":
            path.chmod(0o700)
        return True
    except Exception as e:
        print(f"[SECURITY] Failed to create secure directory: {e}")
        return False


def _write_secure_file(path: Path, content: str) -> bool:
    """
    安全写入文件，确保原子性

    Args:
        path: 文件路径
        content: 文件内容

    Returns:
        是否成功
    """
    temp_path = path.with_suffix(path.suffix + TEMP_SUFFIX)
    try:
        # 先写入临时文件
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # 原子性重命名 (Windows 需要)
        temp_path.replace(path)

        # 设置权限 (Unix)
        if sys.platform != "win32":
            path.chmod(0o600)

        return True
    except Exception as e:
        print(f"[SECURITY] Failed to write secure file: {e}")
        # 清理临时文件
        if temp_path.exists():
            temp_path.unlink()
        return False


def _cleanup_partial_state(files: List[Path], dirs: List[Path] = None) -> None:
    """
    回滚清理部分状态

    Args:
        files: 需要删除的文件列表
        dirs: 需要删除的目录列表（可选）
    """
    for f in files:
        try:
            if f.exists():
                f.unlink()
                print(f"[ROLLBACK] Cleaned up: {f}")
        except Exception as e:
            print(f"[ROLLBACK] Failed to cleanup {f}: {e}")

    if dirs:
        for d in reversed(dirs):  # 从最深层开始删除
            try:
                if d.exists() and d.is_dir() and not list(d.iterdir()):
                    d.rmdir()
                    print(f"[ROLLBACK] Removed empty dir: {d}")
            except Exception as e:
                print(f"[ROLLBACK] Failed to remove dir {d}: {e}")


class CompactHookError(Exception):
    """Compact Hook 异常基类"""
    pass


class CheckpointCreationError(CompactHookError):
    """检查点创建失败"""
    pass


class ContextRecoveryError(CompactHookError):
    """上下文恢复失败"""
    pass


def handle_pre_compact(data: dict) -> dict:
    """
    处理压缩前事件

    Args:
        data: Hook输入数据

    Returns:
        Hook输出 (包含 systemMessage, continue, hookSpecificOutput)

    Raises:
        不会抛出异常 - 所有错误都优雅降级处理
    """
    print("=" * 60)
    print("[PRE-COMPACT HOOK] Context preservation started")
    print("=" * 60)

    result = {
        "timestamp": datetime.now().isoformat(),
        "action": "pre_compact",
        "checkpoint_created": False,
        "context_saved": False,
        "rollback_needed": False
    }

    # 回滚跟踪
    created_files: List[Path] = []
    created_dirs: List[Path] = []

    try:
        from src.tools.layered_memory import get_layered_memory
        mem = get_layered_memory()

        # 1. 创建检查点
        print("\n[1/3] Creating checkpoint before compaction...")
        try:
            checkpoint = mem.create_checkpoint(
                summary="Pre-compact automatic checkpoint",
                token_count=0  # 实际token数无法获取
            )
            result["checkpoint_created"] = True
            result["checkpoint_id"] = checkpoint.checkpoint_id
            print(f"  Checkpoint: {checkpoint.checkpoint_id}")
            print(f"  Key decisions preserved: {len(checkpoint.key_decisions)}")
            print(f"  Pending todos preserved: {len(checkpoint.pending_todos)}")
        except Exception as e:
            raise CheckpointCreationError(f"Failed to create checkpoint: {e}")

        # 2. 提升重要记忆到长期记忆
        print("\n[2/3] Promoting important memories to long-term...")
        summary = mem.get_session_summary()
        promoted = 0

        # 确保长期记忆目录存在
        longterm_dir = Path(mem.longterm_dir) if isinstance(mem.longterm_dir, str) else mem.longterm_dir
        if not _ensure_secure_dir(longterm_dir):
            print("[WARN] Could not create longterm directory, skipping promotion")
        else:
            created_dirs.append(longterm_dir)

            for item in summary.get("key_items", []):
                if item.get("importance", 0) >= 8:
                    # 记录到长期记忆目录
                    longterm_file = longterm_dir / f"preserved_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
                    content = json.dumps({
                        "preserved_at": datetime.now().isoformat(),
                        "item": item,
                        "source": "pre_compact_hook"
                    }, ensure_ascii=False, indent=2)

                    if _write_secure_file(longterm_file, content):
                        created_files.append(longterm_file)
                        promoted += 1
                    else:
                        print(f"[WARN] Failed to preserve item: {item.get('content', 'unknown')[:50]}")

        result["promoted_items"] = promoted
        print(f"  Promoted {promoted} high-importance items")

        # 3. 生成恢复上下文
        print("\n[3/3] Generating recovery context...")
        try:
            recovery_context = mem.generate_session_summary_for_llm()

            # 保存恢复上下文
            recovery_path = RECOVERY_FILE
            if not _ensure_secure_dir(recovery_path.parent):
                raise IOError("Could not create .ai-state directory")

            if _write_secure_file(recovery_path, recovery_context):
                created_files.append(recovery_path)
                result["context_saved"] = True
                print(f"[OK] Recovery context saved to {recovery_path}")
            else:
                raise IOError("Failed to write recovery context")

        except Exception as e:
            print(f"[WARN] Could not save recovery context: {e}")
            # 不是致命错误，继续

    except ImportError as e:
        print(f"[WARN] Layered memory not available: {e}")
        result["error"] = str(e)
        result["fallback_mode"] = True

    except CheckpointCreationError as e:
        print(f"[ERROR] Checkpoint creation failed: {e}")
        result["error"] = str(e)
        result["checkpoint_created"] = False
        # 回滚部分状态
        if created_files or created_dirs:
            print("[ROLLBACK] Cleaning up partial state...")
            _cleanup_partial_state(created_files, created_dirs)

    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        result["error"] = str(e)
        # 回滚
        if created_files or created_dirs:
            print("[ROLLBACK] Cleaning up partial state due to error...")
            _cleanup_partial_state(created_files, created_dirs)

    print("\n" + "=" * 60)

    # 始终返回 continue=True，不阻断压缩流程
    # 即使失败，压缩也会继续，只是没有上下文保护
    return {
        "systemMessage": f"[Pre-Compact] 已创建检查点 {result.get('checkpoint_id', 'N/A')}，关键上下文已保存。",
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "PreCompact",
            "additionalContext": f"""

[上下文压缩提示]
系统即将进行上下文压缩。已自动保存关键信息到检查点。
压缩后请参考 .ai-state/compact_recovery_context.md 恢复上下文。
检查点状态: {'✅ 已创建' if result['checkpoint_created'] else '⚠️ 创建失败'}
保存的项目: {result.get('promoted_items', 0)} 个高优先级记忆
"""
        }
    }


def handle_post_compact(data: dict) -> dict:
    """
    处理压缩后事件

    Args:
        data: Hook输入数据 (可能包含 compact_summary)

    Returns:
        Hook输出 (包含 systemMessage, continue, hookSpecificOutput)

    Raises:
        不会抛出异常 - 所有错误都优雅降级处理
    """
    print("=" * 60)
    print("[POST-COMPACT HOOK] Context recovery started")
    print("=" * 60)

    result = {
        "timestamp": datetime.now().isoformat(),
        "action": "post_compact",
        "context_injected": False,
        "checkpoint_restored": False
    }

    recovery_context = ""
    injection_context = ""

    try:
        # 1. 读取压缩摘要（如果有）
        compact_summary = data.get("compact_summary", "")
        if compact_summary:
            print(f"[INFO] Compact summary length: {len(compact_summary)} chars")

        # 2. 尝试加载恢复上下文
        print("\n[1/2] Loading recovery context...")
        recovery_path = RECOVERY_FILE

        if recovery_path.exists():
            try:
                with open(recovery_path, 'r', encoding='utf-8') as f:
                    recovery_context = f.read()
                print(f"  Loaded recovery context ({len(recovery_context)} chars)")
                result["context_injected"] = True

                # 成功加载后，可以选择删除或保留
                # 保留以便调试，可以手动清理
                result["recovery_file"] = str(recovery_path)

            except PermissionError:
                print("[WARN] Cannot read recovery file (permission denied)")
            except Exception as e:
                print(f"[WARN] Failed to read recovery file: {e}")
        else:
            print("  No recovery context file found")

        # 3. 尝试从检查点恢复
        print("\n[2/2] Restoring from checkpoint...")
        try:
            from src.tools.layered_memory import get_layered_memory
            mem = get_layered_memory()

            checkpoint = mem.restore_from_checkpoint()
            if checkpoint:
                print(f"  Restored from checkpoint: {checkpoint.checkpoint_id}")
                result["restored_checkpoint"] = checkpoint.checkpoint_id
                result["checkpoint_restored"] = True

                # 构建注入上下文
                injection_lines = [
                    "## 从检查点恢复的上下文",
                    "",
                    f"- **检查点ID**: `{checkpoint.checkpoint_id}`",
                    f"- **创建时间**: {checkpoint.created_at}",
                    "",
                    "### 关键决策",
                    "",
                ]

                if checkpoint.key_decisions:
                    for i, d in enumerate(checkpoint.key_decisions[:5], 1):
                        injection_lines.append(f"{i}. {d}")
                else:
                    injection_lines.append("_无记录的关键决策_")

                injection_lines.extend([
                    "",
                    "### 待办事项",
                    "",
                ])

                if checkpoint.pending_todos:
                    for t in checkpoint.pending_todos[:5]:
                        injection_lines.append(f"- [ ] {t}")
                else:
                    injection_lines.append("_无待办事项_")

                injection_context = "\n".join(injection_lines)
                result["injection_context"] = injection_context

            else:
                print("  No checkpoint available for restore")

        except ImportError:
            print("  Layered memory not available for checkpoint restore")
            result["fallback_mode"] = True

        except Exception as e:
            print(f"[WARN] Checkpoint restore failed: {e}")
            result["restore_error"] = str(e)

    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        result["error"] = str(e)

    print("\n" + "=" * 60)

    # 合并恢复上下文
    full_context = ""
    if recovery_context:
        full_context += recovery_context
    if injection_context:
        if full_context:
            full_context += "\n\n"
        full_context += injection_context

    # 构建状态摘要
    status_parts = []
    if result["context_injected"]:
        status_parts.append("✅ 上下文已注入")
    if result["checkpoint_restored"]:
        status_parts.append("✅ 检查点已恢复")
    if not status_parts:
        status_parts.append("⚠️ 无保存的上下文")

    status_line = " | ".join(status_parts)

    # 返回注入的上下文
    return {
        "systemMessage": f"[Post-Compact] 上下文压缩完成。{status_line}",
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "PostCompact",
            "additionalContext": f"""

---

## [上下文恢复 - 压缩后自动注入]

{status_line}

以下是从检查点恢复的关键上下文，请继续基于这些信息工作：

{full_context if full_context else "（无保存的上下文 - 这是一个新的会话或检查点创建失败）"}

---
"""
        }
    }


def main():
    """主函数"""
    # 读取stdin JSON
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("[COMPACT HOOK] Invalid JSON input")
        sys.exit(0)

    # 判断是Pre还是Post
    # Claude Code 会在不同时机调用
    hook_type = data.get("hook_event_name", "unknown")

    if "PreCompact" in hook_type or data.get("trigger") == "pre":
        output = handle_pre_compact(data)
    elif "PostCompact" in hook_type or data.get("trigger") == "post":
        output = handle_post_compact(data)
    else:
        # 默认当作PreCompact处理
        output = handle_pre_compact(data)

    # 输出JSON结果
    print("\n[HOOK OUTPUT]")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()