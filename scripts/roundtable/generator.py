"""
@description: 生成器 - 拿圆桌结论生成具体产物
@dependencies: model_gateway, task_spec, roundtable
@last_modified: 2026-04-06
"""
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass

from src.utils.model_gateway import get_model_gateway
from scripts.roundtable.task_spec import TaskSpec


@dataclass
class RoundtableResult:
    """圆桌结果（简化版，实际在 roundtable.py 定义）"""
    final_proposal: str
    executive_summary: str
    all_constraints: List[str]
    confidence_map: Dict[str, str]
    full_log_path: str
    rounds: int


class Generator:
    """生成器

    职责：
    - 拿圆桌收敛后的执行摘要，调最强模型生成产物
    - 根据缺陷清单定点修复
    """

    # 输出类型对应的模型
    OUTPUT_TYPE_MODEL = {
        "html": "gpt_5_4",
        "markdown": "gpt_5_4",
        "json": "gpt_5_4",
        "code": "gpt_5_4",
    }

    # 降级链
    FALLBACK_CHAIN = ["gpt_5_4", "gpt_4o_norway", "gpt_4o"]

    def __init__(self, gw=None):
        self.gw = gw or get_model_gateway()

    async def generate(self, task: TaskSpec, rt_result: RoundtableResult) -> str:
        """生成产物

        Args:
            task: TaskSpec
            rt_result: 圆桌收敛结果（执行摘要约 2000 字）

        Returns:
            生成的产物内容
        """
        model_name = self.OUTPUT_TYPE_MODEL.get(task.output_type, "gpt_5_4")

        prompt = f"""【执行摘要】
{rt_result.executive_summary}

【硬约束】
{chr(10).join(rt_result.all_constraints[:10])}

【验收标准】
{chr(10).join(task.acceptance_criteria)}

【输出要求】
输出类型：{task.output_type}
输出路径：{task.output_path}

请根据执行摘要生成完整产物。
如果是 HTML，确保：
- 单文件，无外部依赖
- 可直接双击打开运行
- 完整实现所有功能点

直接输出产物内容，不需要解释。
"""

        # 尝试主模型
        result = self.gw.call(
            model_name=model_name,
            prompt=prompt,
            system_prompt=f"你是专业的{task.output_type}生成器，直接输出内容，不解释。",
            task_type="generation",
        )

        if result.get("success"):
            return result.get("response", "")

        # 降级链
        for fallback in self.FALLBACK_CHAIN[1:]:
            if fallback != model_name:
                result = self.gw.call(
                    model_name=fallback,
                    prompt=prompt,
                    system_prompt=f"你是专业的{task.output_type}生成器。",
                    task_type="generation",
                )
                if result.get("success"):
                    return result.get("response", "")

        return ""

    async def fix(self, current_output: str, issues: List[str],
                  rt_result: RoundtableResult) -> str:
        """定点修复

        Args:
            current_output: 当前输出代码
            issues: 具体缺陷清单
            rt_result: 圆桌结果（用于理解原始意图）

        Returns:
            修复后的输出
        """
        prompt = f"""【当前输出】
{current_output[:3000]}

【缺陷清单】
{chr(10).join(issues)}

【原始意图（执行摘要）】
{rt_result.executive_summary[:1000]}

请根据缺陷清单定点修复输出。
只修复指出的问题，不要重写其他部分。
直接输出修复后的完整内容。
"""

        result = self.gw.call_with_fallback(
            primary="gpt_5_4",
            fallback="gpt_4o_norway",
            prompt=prompt,
            system_prompt="你是代码修复专家，只修复指定问题，保持其他部分不变。",
            task_type="generation",
        )

        if result.get("success"):
            return result.get("response", "")
        return current_output

    async def escalate(self, current_output: str, stuck_issues: List[str],
                       rt_result: RoundtableResult) -> str:
        """升级策略：换更强模型或拆解问题

        当同一问题连续两轮未修复时触发。
        """
        # 尝试最强模型
        prompt = f"""【当前输出存在问题，需要彻底重新思考】

【当前输出】
{current_output[:2000]}

【卡住的问题】
{chr(10).join(stuck_issues)}

【原始意图】
{rt_result.executive_summary}

请从根本上重新设计解决方案，不要只是修补。
"""

        # 使用最强推理模型
        result = self.gw.call(
            model_name="o3-deep-research",
            prompt=prompt,
            system_prompt="你是顶级架构师，需要从根本上解决问题。",
            task_type="deep_research",
        )

        if result.get("success"):
            return result.get("response", "")

        # 降级到 gpt_5_4
        return await self.fix(current_output, stuck_issues, rt_result)