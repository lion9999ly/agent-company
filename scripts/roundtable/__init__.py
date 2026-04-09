"""
@description: 圆桌系统公开接口
@dependencies: task_spec, crystallizer, roundtable, generator, verifier, memory, meta_cognition, resilience
@last_modified: 2026-04-07
"""

import asyncio
import time
import hashlib
import json
from pathlib import Path
from typing import Optional

from scripts.roundtable.task_spec import TaskSpec, load_task_spec
from scripts.roundtable.crystallizer import Crystallizer
from scripts.roundtable.roundtable import Roundtable, RoundtableResult
from scripts.roundtable.generator import Generator
from scripts.roundtable.verifier import Verifier, VerifyResult
from scripts.roundtable.meta_cognition import MetaCognition
from scripts.roundtable.resilience import Resilience, ParkedException


async def run_task(task: TaskSpec, gw=None, kb=None, feishu=None) -> dict:
    """一个任务的完整生命周期

    流程：
    0. 知识结晶 — 准备上下文
    1. 议题审查
    2. 圆桌讨论
    3. 生成
    4. 审查闭环（迭代）
    5. 输出
    6. 知识回写

    Returns:
        dict: {
            "output": str,           # 生成的 HTML 内容
            "output_path": str,      # 本地文件路径
            "executive_summary": str, # 执行摘要
            "rounds": int,           # 迭代轮数
            "full_log_path": str,    # 讨论记录路径
            "verify_summary": str,   # 验收通过情况
        }
    """
    # 兼容同步/异步 notify 的包装函数
    async def _notify(msg):
        """飞书通知包装器，兼容同步和异步 notify 函数"""
        if not feishu:
            return
        try:
            result = feishu.notify(msg)
            # 如果返回的是协程对象，需要 await
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            print(f"[Roundtable] 通知失败: {e}")

    # 0. 知识结晶 — 准备上下文
    crystallizer = Crystallizer(gw, kb)
    context = await crystallizer.prepare_context(task)
    await _notify(f"📚 知识准备完成")

    # 1. 议题审查
    rt = Roundtable(gw, feishu)
    task = await rt.pre_check_task_spec(task, context)

    # #2 TaskSpec 有问题时等待用户确认
    if hasattr(task, '_review_issues') and task._review_issues:
        # 写等待文件
        topic_hash = hashlib.md5(task.topic.encode()).hexdigest()[:8]
        waiting_file = Path(".ai-state") / f"taskspec_waiting_{topic_hash}.txt"
        waiting_file.write_text(json.dumps(task._review_issues, ensure_ascii=False), encoding="utf-8")

        await _notify(f"⚠️ TaskSpec 审查发现问题，请在飞书回复「确认」继续或「跳过」跳过审查")

        # 轮询等待确认文件（超时 5 分钟）
        confirm_file = Path(".ai-state") / f"taskspec_confirm_{topic_hash}.txt"
        timeout = 300  # 5 分钟
        start = time.time()
        while time.time() - start < timeout:
            if confirm_file.exists():
                action = confirm_file.read_text(encoding="utf-8").strip()
                confirm_file.unlink()
                print(f"[Roundtable] TaskSpec 用户确认: {action}")
                await _notify(f"✅ 收到「{action}」，继续执行")
                break
            await asyncio.sleep(2)
        else:
            # 超时自动跳过
            if waiting_file.exists():
                waiting_file.unlink()
            print(f"[Roundtable] TaskSpec 确认超时，自动跳过")
            await _notify(f"⏰ TaskSpec 确认超时（5分钟），自动继续")

    # 2. 圆桌讨论
    result = await rt.discuss(task, context)
    await _notify(f"🔵 圆桌收敛，共 {result.rounds} 轮")

    # 3. 生成
    gen = Generator(gw)
    output = await gen.generate(task, result)

    # 4. 审查闭环
    ver = Verifier(gw)
    iteration = 0
    verify_summary = ""

    try:
        while iteration < task.max_iterations:
            vr = await ver.verify(task, output)
            if vr.passed:
                await _notify(f"✅ 审查通过")
                verify_summary = _format_verify_summary(vr)
                break

            if vr.stuck:
                await _notify(f"⚠️ 能力瓶颈：{vr.stuck_issues}，尝试升级...")
                output = await gen.escalate(output, vr.stuck_issues, result)
                continue

            iteration += 1
            await _notify(f"🔄 审查第{iteration}轮，{len(vr.issues)}个缺陷，修复中...")
            output = await gen.fix(output, [i.description for i in vr.issues], result)
    except Exception as e:
        print(f"[Roundtable] 审查闭环异常: {type(e).__name__}: {e}")
        verify_summary = f"审查异常中断: {e}"
        await _notify(f"⚠️ 审查闭环异常: {type(e).__name__}，跳过审查继续输出")

    # 5. 输出（P1 #3: 添加时间戳）
    from datetime import datetime
    import shutil

    output_dir = Path(task.output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # 生成带时间戳的文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = Path(task.output_path).stem
    ext = Path(task.output_path).suffix
    timestamped_path = output_dir / f"{base_name}_{timestamp}{ext}"

    # 写入带时间戳的文件
    timestamped_path.write_text(output, encoding="utf-8")
    print(f"[Roundtable] 输出文件: {timestamped_path}")

    # 同时创建 latest 版本（复制）
    latest_path = output_dir / f"{base_name}_latest{ext}"
    shutil.copy2(timestamped_path, latest_path)
    print(f"[Roundtable] Latest 版本: {latest_path}")

    # 更新返回路径为带时间戳版本
    actual_output_path = str(timestamped_path)

    # 6. 知识回写
    await crystallizer.crystallize_learnings(task, result)

    await _notify(f"🎯 任务完成：{actual_output_path}")

    # 7. 生成飞书云文档（P0 #1 修复 - 第二轮）
    print("[云文档] 开始生成")
    doc_url = None
    try:
        from scripts.feishu_output import update_doc
        print(f"[云文档] update_doc 已导入，准备调用")
        # 组装云文档内容
        doc_content = f"""# {task.topic}

## 执行摘要
{result.executive_summary}

## 迭代轮数
{result.rounds} 轮

## 验收结果
{verify_summary or '已完成'}

## 本地文件
{actual_output_path}

---
*由圆桌系统自动生成*
"""
        print(f"[云文档] 内容长度: {len(doc_content)} 字符")
        doc_url = update_doc(f"圆桌: {task.topic}", doc_content)
        print(f"[云文档] update_doc 返回: {doc_url}")
        if doc_url:
            print(f"[云文档] 生成成功: {doc_url}")
            await _notify(f"📄 云文档: {doc_url}")
        else:
            print(f"[云文档] 生成失败: update_doc 返回空")
    except ImportError as e:
        print(f"[云文档] 导入失败: {e}")
    except Exception as e:
        print(f"[云文档] 生成异常: {type(e).__name__}: {e}")

    # #9: 自动创建 GitHub Issue 并更新 inbox
    issue_url = None
    try:
        import subprocess
        from datetime import datetime

        # 生成摘要内容
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        passed_str = '通过' if verify_summary and '通过' in verify_summary else '待改进'
        issue_body = f"""## 圆桌结果

- **议题**: {task.topic}
- **结果**: {passed_str}
- **迭代轮数**: {result.rounds}
- **执行摘要**:
{result.executive_summary[:500]}

## 产出文件
- `{actual_output_path}`

---
*由圆桌系统自动生成*
"""
        issue_title = f"[圆桌] {task.topic[:30]} - {datetime.now().strftime('%Y-%m-%d')}"

        # 使用 gh CLI 创建 Issue
        result_gh = subprocess.run(
            ["gh", "issue", "create",
             "--title", issue_title,
             "--body", issue_body,
             "--label", "roundtable"],
            cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=30
        )

        if result_gh.returncode == 0:
            issue_url = result_gh.stdout.strip()
            print(f"[Issue] 创建成功: {issue_url}")
            await _notify(f"📋 GitHub Issue: {issue_url}")
        else:
            print(f"[Issue] 创建失败: {result_gh.stderr[:100]}")
    except FileNotFoundError:
        print("[Issue] gh CLI 未安装，跳过")
    except Exception as e:
        print(f"[Issue] 创建异常: {e}")

    # 更新 claude_chat_inbox.md 并 push
    try:
        from pathlib import Path as PPath
        inbox_path = PPath(".ai-state/claude_chat_inbox.md")
        inbox_content = ""
        if inbox_path.exists():
            inbox_content = inbox_path.read_text(encoding="utf-8")

        # 追加新摘要
        new_entry = f"""
---

## [圆桌] {task.topic[:30]} - {datetime.now().strftime('%Y-%m-%d %H:%M')}

- **结果**: {passed_str}
- **关键数据**: 迭代 {result.rounds} 轮
- **产出文件**: `{actual_output_path}`
"""
        if issue_url:
            new_entry += f"- **GitHub Issue**: {issue_url}\n"

        inbox_path.write_text(inbox_content + new_entry, encoding="utf-8")
        print(f"[Inbox] 已更新")

        # git add + commit + push
        subprocess.run(["git", "add", str(inbox_path)], cwd=str(PROJECT_ROOT), capture_output=True)
        subprocess.run(["git", "commit", "-m", f"docs: 圆桌完成 - {task.topic[:20]}"], cwd=str(PROJECT_ROOT), capture_output=True)
        push_result = subprocess.run(["git", "push", "origin", "main"], cwd=str(PROJECT_ROOT), capture_output=True, text=True)
        if push_result.returncode == 0:
            print(f"[Inbox] 已推送到 GitHub")
        else:
            print(f"[Inbox] 推送失败: {push_result.stderr[:100]}")
    except Exception as e:
        print(f"[Inbox] 更新异常: {e}")

    # 返回完整结果（供飞书输出使用）
    return {
        "output": output,
        "output_path": actual_output_path,
        "executive_summary": result.executive_summary,
        "rounds": result.rounds,
        "full_log_path": result.full_log_path,
        "verify_summary": verify_summary,
        "topic": task.topic,
    }


def _format_verify_summary(vr) -> str:
    """格式化验收结果摘要"""
    lines = []
    if hasattr(vr, 'acceptance_results') and vr.acceptance_results:
        for item in vr.acceptance_results:
            lines.append(f"- {item}")
    if hasattr(vr, 'passed') and vr.passed:
        lines.append(f"\n**通过**: ✅")
    elif hasattr(vr, 'issues') and vr.issues:
        lines.append(f"\n**问题数**: {len(vr.issues)}")
    return "\n".join(lines) if lines else "审查通过"


def run_task_by_topic(topic: str, gw=None, kb=None, feishu=None):
    """通过议题名运行预定义任务

    TaskSpec 存放位置：.ai-state/task_specs/{topic}.json
    """
    task = load_task_spec(topic)
    if not task:
        return None
    return run_task(task, gw, kb, feishu)


__all__ = [
    "run_task",
    "run_task_by_topic",
    "TaskSpec",
    "load_task_spec",
    "Crystallizer",
    "Roundtable",
    "RoundtableResult",
    "Generator",
    "Verifier",
    "VerifyResult",
    "MetaCognition",
    "Resilience",
    "ParkedException",
]