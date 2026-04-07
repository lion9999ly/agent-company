"""
@description: 元认知层 — Claude 思考通道嵌入圆桌系统
              不参与打球，判断这场球赛打得对不对。
@dependencies: claude_bridge, asyncio, typing
@last_modified: 2026-04-07
"""
import asyncio
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime

# ============================================================
# ⚠️ 临时禁用 — 等待 CDP 桥接协议重新设计
# 启用条件：完成以下三项
#   1. 频率限制（每个任务最多调 3 次思考通道）
#   2. 内容去重（已推送过的不重复推）
#   3. 长度限制（≤1000 字摘要，不推全文）
# 启用前必须经 Leo 确认
# ============================================================
META_COGNITION_ENABLED = False


class MetaCognition:
    """元认知层

    Claude 思考通道不是圆桌中的一个角色，而是站在圆桌之外审视整盘棋的"元裁判"。
    它不参与方案设计、不参与审查，它判断的是："这场讨论本身在做对的事吗？"

    关键约束：
    - 不阻塞：每次调用设 60 秒超时，超时返回 None，流程继续
    - 不替代角色：只发现盲点和方向性问题
    - 不频繁调用：只在 Phase 之间的关键节点调用
    """

    def __init__(self, claude_bridge=None, feishu=None, log_dir: str = "roundtable_logs"):
        """
        Args:
            claude_bridge: scripts/claude_bridge.py 的调用接口
            feishu: 飞书通知
            log_dir: 日志目录
        """
        self.bridge = claude_bridge
        self.feishu = feishu
        self.log_dir = Path(log_dir)
        self._log_buffer: List[str] = []  # 累积日志

    def _get_bridge(self):
        """获取 claude_bridge 模块"""
        if self.bridge:
            return self.bridge
        # 延迟导入
        from scripts import claude_bridge
        return claude_bridge

    async def _call_thinking_channel(self, prompt: str, timeout: int = 60) -> Optional[str]:
        """调用思考通道（带超时）

        Args:
            prompt: 问题
            timeout: 超时时间（秒）

        Returns:
            回复内容，超时或失败返回 None
        """
        bridge = self._get_bridge()

        def _sync_call():
            try:
                return bridge.call_claude_via_cdp(prompt, timeout=timeout, inject_context=True)
            except Exception as e:
                print(f"[MetaCognition] 思考通道调用失败: {e}")
                return None

        # 异步包装
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _sync_call)
            return result
        except Exception as e:
            print(f"[MetaCognition] 异步调用异常: {e}")
            return None

    def _log(self, phase: str, question: str, answer: Optional[str]):
        """记录元认知调用日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n## [{timestamp}] {phase}\n**问题**: {question[:200]}\n**回复**: {answer or '(无响应/超时)'}\n"
        self._log_buffer.append(entry)

    def _save_log(self, task_topic: str):
        """保存累积的日志到文件"""
        if not self._log_buffer:
            return

        safe_topic = "".join(c for c in task_topic[:20] if c.isalnum() or c in "_-").strip()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.log_dir / f"{safe_topic}_meta_cognition.md"

        header = f"# 元认知层日志 — {task_topic}\n"
        content = header + "".join(self._log_buffer)

        log_path.write_text(content, encoding="utf-8")
        print(f"[MetaCognition] 日志已保存: {log_path}")

    async def check_blind_spots(self, phase_name: str, phase_outputs: dict) -> Optional[str]:
        """盲点检测

        每个 Phase 完成后调用。

        Args:
            phase_name: Phase 名称（如 "Phase 1: 独立思考"）
            phase_outputs: 各角色的输出（简化摘要）

        Returns:
            如果发现问题，返回问题描述（注入到下一个 Phase 的上下文）
            如果没问题或超时，返回 None
        """
        if not META_COGNITION_ENABLED:
            return None

        # 构建输出摘要
        summary_lines = []
        for role, output in phase_outputs.items():
            if isinstance(output, str):
                summary_lines.append(f"[{role}]: {output[:300]}")
            else:
                # Phase1Output 等对象
                constraints = getattr(output, 'constraints', [])
                if constraints:
                    summary_lines.append(f"[{role}]: 约束: {', '.join(constraints[:3])}")

        summary = "\n".join(summary_lines[:5])

        prompt = f"""这一轮讨论（{phase_name}），以下是各角色的输出：

{summary}

有没有被集体忽略的盲点？有没有在错误前提上推进？
如果没问题，回复"无问题"。
如果有问题，简要说明是什么问题，不超过200字。"""

        result = await self._call_thinking_channel(prompt, timeout=60)

        self._log(phase_name, prompt, result)

        if result and "无问题" not in result:
            return result

        return None

    async def review_executive_summary(self, summary: str, task_topic: str) -> Optional[str]:
        """执行摘要审查

        圆桌收敛后、Generator 生成前调用。

        Args:
            summary: 执行摘要
            task_topic: 任务议题

        Returns:
            如果有追问，返回追问内容
            如果批准或超时，返回 None
        """
        if not META_COGNITION_ENABLED:
            return None

        prompt = f"""以下是圆桌讨论收敛后的执行摘要，即将用于生成{task_topic}。

{summary[:1500]}

如果你是创始人 Leo，看到这份摘要，你会批准还是会追问什么？
如果批准，回复"批准"。
如果有疑问，说明追问什么，不超过200字。"""

        result = await self._call_thinking_channel(prompt, timeout=60)

        self._log("执行摘要审查", prompt, result)

        if result and "批准" not in result:
            return result

        return None

    async def final_quality_gate(self, output: str, task_topic: str) -> Optional[str]:
        """最终质量把关

        Verifier 通过后、最终输出前调用。

        Args:
            output: 最终输出（代码/文档摘要）
            task_topic: 任务议题

        Returns:
            如果有问题，返回问题描述
            如果通过或超时，返回 None
        """
        if not META_COGNITION_ENABLED:
            return None

        # 截取输出摘要
        output_summary = output[:2000] if len(output) > 2000 else output

        prompt = f"""以下是{task_topic}的最终输出（代码/文档摘要）。
Verifier 已通过所有验收标准。
但验收标准可能有遗漏——你作为最终把关，
这个输出拿去给投资人/供应商看，会不会丢人？
有没有验收标准没覆盖到但明显有问题的地方？

{output_summary}

如果没问题，回复"通过"。
如果有问题，说明是什么，不超过300字。"""

        result = await self._call_thinking_channel(prompt, timeout=60)

        self._log("最终质量把关", prompt, result)

        if result and "通过" not in result:
            return result

        return None

    async def judge_crystallization_level(self, new_conclusions: List[str], task_topic: str) -> Dict[str, str]:
        """判断结论结晶级别

        知识回写时调用。

        Args:
            new_conclusions: 新结论列表
            task_topic: 任务议题

        Returns:
            每条结论的级别映射 {"结论": "A/B/C"}
        """
        if not META_COGNITION_ENABLED:
            return {}

        conclusions_text = "\n".join(f"{i+1}. {c}" for i, c in enumerate(new_conclusions[:10]))

        prompt = f"""圆桌讨论{task_topic}产出了以下新结论。

{conclusions_text}

每条结论应该写入哪个级别？
A. 决策备忘录（decision_memo）— 具体议题的结论
B. 产品锚点（product_anchor）— 影响产品方向的重大决策
C. 不值得记录 — 过于细节或临时性的判断

逐条回复级别即可，格式如：1-A, 2-B, 3-C"""

        result = await self._call_thinking_channel(prompt, timeout=60)

        self._log("结晶级别判断", prompt, result)

        # 解析结果
        level_map = {}
        if result:
            import re
            matches = re.findall(r'(\d+)[\.\-:]?\s*([ABC])', result.upper())
            for idx, level in matches:
                idx = int(idx) - 1
                if 0 <= idx < len(new_conclusions):
                    level_map[new_conclusions[idx]] = level

        return level_map

    async def diagnose_system_issue(self, error: str, phase: str, context: dict) -> Dict[str, Any]:
        """诊断系统问题

        韧性机制调用。当系统在某个环节反复出错时，把完整的错误链路推给思考通道诊断。

        Args:
            error: 错误信息
            phase: 出错的 Phase
            context: 上下文信息（role, model, attempts 等）

        Returns:
            诊断结果 {"diagnosis": str, "action": str, "details": str}
        """
        if not META_COGNITION_ENABLED:
            return {
                "diagnosis": "元认知层已禁用",
                "action": "retry",
                "details": "META_COGNITION_ENABLED=False"
            }

        attempts = context.get("attempts", [])

        prompt = f"""圆桌系统在{phase}环节反复出错。
错误信息：{error}
已尝试的修复：{attempts}
请诊断根因，可能是：
1. 模型能力不足（建议换哪个模型）
2. prompt 有问题（建议怎么改）
3. TaskSpec 有问题（验收标准矛盾/遗漏）
4. 其他原因
给出诊断和建议的修复行动。"""

        result = await self._call_thinking_channel(prompt, timeout=60)

        self._log(f"系统诊断 - {phase}", prompt, result)

        # 默认返回值
        diagnosis_result = {
            "diagnosis": "思考通道无响应",
            "action": "retry",
            "details": result or "超时或失败"
        }

        if result:
            # 解析行动建议
            if "换模型" in result or "换更强" in result:
                diagnosis_result["action"] = "change_model"
            elif "验收标准" in result or "TaskSpec" in result:
                diagnosis_result["action"] = "modify_spec"
            elif "人工" in result or "Leo" in result:
                diagnosis_result["action"] = "escalate"
            elif "prompt" in result.lower():
                diagnosis_result["action"] = "retry"

            diagnosis_result["diagnosis"] = result[:500]
            diagnosis_result["details"] = result

        return diagnosis_result

    def finalize_logs(self, task_topic: str):
        """任务结束时保存所有日志"""
        self._save_log(task_topic)
        self._log_buffer = []  # 清空缓冲