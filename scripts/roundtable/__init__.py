"""
@description: 圆桌系统公开接口
@dependencies: task_spec, crystallizer, roundtable, generator, verifier, memory, meta_cognition, resilience
@last_modified: 2026-04-07
"""

import asyncio
from pathlib import Path
from typing import Optional

from scripts.roundtable.task_spec import TaskSpec, load_task_spec
from scripts.roundtable.crystallizer import Crystallizer
from scripts.roundtable.roundtable import Roundtable, RoundtableResult
from scripts.roundtable.generator import Generator
from scripts.roundtable.verifier import Verifier, VerifyResult
from scripts.roundtable.meta_cognition import MetaCognition
from scripts.roundtable.resilience import Resilience, ParkedException


async def run_task(task: TaskSpec, gw=None, kb=None, feishu=None) -> str:
    """一个任务的完整生命周期

    流程：
    0. 知识结晶 — 准备上下文
    1. 议题审查
    2. 圆桌讨论
    3. 生成
    4. 审查闭环（迭代）
    5. 输出
    6. 知识回写
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

    # 2. 圆桌讨论
    result = await rt.discuss(task, context)
    await _notify(f"🔵 圆桌收敛，共 {result.rounds} 轮")

    # 3. 生成
    gen = Generator(gw)
    output = await gen.generate(task, result)

    # 4. 审查闭环
    ver = Verifier(gw)
    iteration = 0

    while iteration < task.max_iterations:
        vr = await ver.verify(task, output)
        if vr.passed:
            await _notify(f"✅ 审查通过")
            break

        if vr.stuck:
            await _notify(f"⚠️ 能力瓶颈：{vr.stuck_issues}，尝试升级...")
            output = await gen.escalate(output, vr.stuck_issues, result)
            continue

        iteration += 1
        await _notify(f"🔄 审查第{iteration}轮，{len(vr.issues)}个缺陷，修复中...")
        output = await gen.fix(output, [i.description for i in vr.issues], result)

    # 5. 输出
    Path(task.output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(task.output_path).write_text(output, encoding="utf-8")

    # 6. 知识回写
    await crystallizer.crystallize_learnings(task, result)

    await _notify(f"🎯 任务完成：{task.output_path}")

    return output


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