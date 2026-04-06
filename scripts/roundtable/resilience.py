"""
@description: 韧性机制 — 诊断-修复-续跑，替代降级和中止
              三个原则：
              1. 平替不降级 — 换同级别模型，不降低质量预期
              2. 诊断先于修复 — 搞清楚为什么错，再决定怎么修
              3. 断点续跑不中止 — 某步走不通先跑其他步骤，回头处理
@dependencies: typing, asyncio
@last_modified: 2026-04-06
"""
import asyncio
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime


class ParkedException(Exception):
    """断点暂存异常

    调用方捕获后跳过当前步骤，继续其他步骤，稍后回来重试。
    """
    def __init__(self, key: str, context: dict):
        self.key = key
        self.context = context
        super().__init__(f"断点暂存: {key}")


class Resilience:
    """韧性机制

    不是 try-except-pass，是 try-diagnose-fix-retry。

    使用方式：
        result = await resilience.execute(
            fn=lambda: gw.call(model, prompt),
            context={"role": "CDO", "phase": "phase_1", "model": model}
        )
    """

    # 最大重试次数
    MAX_RETRIES = 5

    # 无限循环检测阈值
    LOOP_DETECTION_THRESHOLD = 10

    def __init__(self, gw=None, meta_cognition=None, feishu=None):
        """
        Args:
            gw: ModelGateway
            meta_cognition: MetaCognition 实例（用于根因诊断）
            feishu: 飞书通知
        """
        self.gw = gw
        self.meta = meta_cognition
        self.feishu = feishu
        self.attempt_history: Dict[str, List[dict]] = {}  # 跟踪每个环节的尝试历史

    async def _notify(self, msg: str):
        """发送通知"""
        if self.feishu and hasattr(self.feishu, 'notify'):
            await self.feishu.notify(msg)
        print(f"[Resilience] {msg}")

    async def execute(self, fn: Callable, context: dict) -> Any:
        """执行函数（带韧性包装）

        所有 LLM 调用和 Phase 执行都经过这一层。
        不是 try-except-pass，是 try-diagnose-fix-retry。

        Args:
            fn: async callable，实际要执行的函数
            context: dict，包含 role, phase, model, task 等信息

        Returns:
            fn 的成功结果

        Raises:
            ParkedException: 所有模型暂不可用时
        """
        role = context.get("role", "unknown")
        phase = context.get("phase", "unknown")
        key = f"{phase}:{role}"
        self.attempt_history[key] = []
        tried_models = set()

        while True:
            current_model = context.get("model", "unknown")

            # 检测无限循环
            if self._detect_infinite_loop(key):
                await self._notify(f"⚠️ 检测到可能的无限循环，上报人工")
                await self._escalate_to_leo(key, context, {
                    "diagnosis": "无限循环检测",
                    "details": f"尝试历史: {self.attempt_history[key][-5:]}"
                })
                raise ParkedException(key, context)

            # 尝试次数检查
            if len(self.attempt_history[key]) >= self.MAX_RETRIES:
                await self._notify(f"⚠️ {role} 达到最大重试次数，尝试思考通道诊断")
                if self.meta:
                    diagnosis = await self.meta.diagnose_system_issue(
                        str(self.attempt_history[key][-1]), phase, context
                    )
                    action = await self._apply_diagnosis(diagnosis, context)
                    if action == "retry":
                        self.attempt_history[key] = []  # 重置计数
                        continue
                raise ParkedException(key, context)

            try:
                # 执行函数
                if asyncio.iscoroutinefunction(fn):
                    result = await fn()
                else:
                    result = fn()

                # 检查输出质量
                quality = self._check_output_quality(result, context)
                if quality["ok"]:
                    return result

                # ── 输出质量不达标 ──
                self.attempt_history[key].append({
                    "type": "quality_fail",
                    "issues": quality["issues"],
                    "model": current_model,
                    "timestamp": datetime.now().isoformat()
                })

                # 第一次和第二次：反馈修正，同一模型重试
                quality_fails = [a for a in self.attempt_history[key] if a["type"] == "quality_fail"]
                if len(quality_fails) <= 2:
                    await self._notify(f"🔄 {role} 输出质量不达标，反馈修正中...")
                    result = await self._retry_with_feedback(fn, quality["issues"], context)
                    quality2 = self._check_output_quality(result, context)
                    if quality2["ok"]:
                        return result
                    self.attempt_history[key].append({
                        "type": "quality_fail_retry",
                        "issues": quality2["issues"],
                        "model": current_model
                    })

                # 反复出问题 → 换同级别模型
                peer = self._get_peer_model(current_model, tried_models)
                if peer:
                    context["model"] = peer
                    tried_models.add(current_model)
                    await self._notify(f"🔄 {role} 切换至同级别模型 {peer}（非降级）")
                    continue

                # 所有同级别模型都试过 → 思考通道诊断
                if self.meta:
                    diagnosis = await self.meta.diagnose_system_issue(
                        str(quality["issues"]), phase, context
                    )
                    action = await self._apply_diagnosis(diagnosis, context)
                    if action == "retry":
                        continue
                    elif action == "escalate":
                        await self._escalate_to_leo(key, context, diagnosis)
                        return await self._wait_and_retry(fn, context)

                raise ParkedException(key, context)

            except ParkedException:
                raise

            except Exception as e:
                self.attempt_history[key].append({
                    "type": "exception",
                    "error": str(e),
                    "model": current_model,
                    "timestamp": datetime.now().isoformat()
                })

                # ── 模型调用失败 ──
                if self._is_model_error(e):
                    peer = self._get_peer_model(current_model, tried_models)
                    if peer:
                        context["model"] = peer
                        tried_models.add(current_model)
                        await self._notify(f"⚡ {role} 模型异常，平替至 {peer}")
                        continue

                    # 所有模型不可用 → 暂存断点
                    await self._notify(f"⏸ {role} 所有模型暂不可用，暂存断点")
                    raise ParkedException(key, context)

                # ── 其他异常 → 思考通道诊断 ──
                if self.meta:
                    diagnosis = await self.meta.diagnose_system_issue(
                        str(e), phase, context
                    )
                    action = await self._apply_diagnosis(diagnosis, context)
                    if action == "retry":
                        continue
                    elif action == "escalate":
                        await self._escalate_to_leo(key, context, diagnosis)
                        return await self._wait_and_retry(fn, context)

                raise

    def _check_output_quality(self, result: Any, context: dict) -> dict:
        """检查输出质量（规则层，不调 LLM）

        检查项：
        - 结果不为空
        - 如果是圆桌 Phase 输出：是否包含置信度标注
        - 字数是否在合理范围内

        Returns:
            {"ok": bool, "issues": list[str]}
        """
        issues = []

        # 空检查
        if result is None:
            return {"ok": False, "issues": ["输出为空"]}

        if isinstance(result, dict):
            # 字典类型检查 success 字段
            if result.get("success") is False:
                error = result.get("error", "未知错误")
                return {"ok": False, "issues": [f"调用失败: {error}"]}

            # 检查 response 字段
            response = result.get("response", "")
            if not response or len(response.strip()) < 10:
                return {"ok": False, "issues": ["响应内容过短"]}

            content = response
        else:
            content = str(result)

        # 长度检查
        if len(content.strip()) < 20:
            issues.append("输出内容过短")

        # 最大长度检查（防止垃圾输出）
        if len(content) > 50000:
            issues.append("输出内容异常长，可能是垃圾输出")

        # 圆桌 Phase 输出格式检查
        phase = context.get("phase", "")
        if phase.startswith("phase_"):
            # 检查是否包含置信度标注
            if "[" in content and "·" in content:
                # 有置信度标注，格式正确
                pass
            else:
                issues.append("缺少置信度标注格式")

            # 检查是否包含结构化标题
            if "##" not in content:
                issues.append("缺少结构化输出格式")

        return {"ok": len(issues) == 0, "issues": issues}

    def _get_peer_model(self, current_model: str, tried_models: set) -> Optional[str]:
        """获取同级别备选模型（非降级）

        同级别映射（从 roles.PEER_MODELS 读取）

        如果当前模型的 peer 已经在本轮试过了 → 返回 None
        """
        from scripts.roundtable.roles import PEER_MODELS

        peers = PEER_MODELS.get(current_model, [])
        for peer in peers:
            if peer not in tried_models and peer != current_model:
                return peer

        return None

    async def _retry_with_feedback(self, fn: Callable, issues: List[str], context: dict) -> Any:
        """把质量问题反馈给同一模型重试

        注意：这需要修改原始 prompt，通过 context 传递
        """
        # 标记需要反馈修正
        context["quality_feedback"] = issues

        # 再次执行
        if asyncio.iscoroutinefunction(fn):
            return await fn()
        else:
            return fn()

    async def _apply_diagnosis(self, diagnosis: dict, context: dict) -> str:
        """根据思考通道的诊断结果执行修复

        Args:
            diagnosis: {"diagnosis": str, "action": str, "details": str}
            context: 执行上下文

        Returns:
            action 字符串
        """
        action = diagnosis.get("action", "retry")

        if action == "change_model":
            # 换到诊断建议的模型
            details = diagnosis.get("details", "")
            # 从 details 中提取模型名
            import re
            model_match = re.search(r'(gpt_\w+|gemini_\w+|deepseek_\w+|doubao_\w+)', details.lower())
            if model_match:
                suggested_model = model_match.group(1)
                context["model"] = suggested_model
                await self._notify(f"🔄 根据诊断切换模型: {suggested_model}")

        elif action == "modify_spec":
            # 标记需要修改 TaskSpec
            context["spec_needs_modification"] = diagnosis.get("details", "")
            await self._notify(f"⚠️ TaskSpec 可能需要修改: {diagnosis.get('diagnosis', '')}")

        elif action == "escalate":
            await self._notify(f"🔶 需要人工介入: {diagnosis.get('diagnosis', '')}")

        return action

    async def _escalate_to_leo(self, key: str, context: dict, diagnosis: dict):
        """上报 Leo

        打包完整诊断链路，不是简单说"出错了"。
        """
        attempts = self.attempt_history.get(key, [])

        msg = f"""🔶 圆桌系统在 {context.get('phase', 'unknown')} 环节遇到能力边界

角色：{context.get('role', 'unknown')}
问题：{diagnosis.get('diagnosis', '未知')}
已尝试：{len(attempts)} 次
思考通道诊断：{diagnosis.get('details', '无')}

建议：{diagnosis.get('action', '需人工判断')}

请回复处理意见。"""

        await self._notify(msg)

    async def _wait_and_retry(self, fn: Callable, context: dict) -> Any:
        """等待 Leo 通过飞书回复后重试

        简化实现：等待一段时间后自动重试
        """
        await self._notify("⏳ 等待人工回复中...（60秒后自动重试）")
        await asyncio.sleep(60)
        return await self.execute(fn, context)

    def _is_model_error(self, e: Exception) -> bool:
        """判断是否为模型调用层面的错误"""
        error_str = str(e).lower()
        model_error_keywords = [
            "404", "not found", "timeout", "timed out",
            "connection", "network", "unauthorized", "401",
            "rate limit", "429", "quota", "api key"
        ]
        return any(kw in error_str for kw in model_error_keywords)

    def _detect_infinite_loop(self, key: str) -> bool:
        """检测自身是否陷入无效循环

        规则：
        - 同一个 key 的尝试历史超过阈值
        - 且最近 5 次的错误类型相同
        """
        history = self.attempt_history.get(key, [])
        if len(history) < self.LOOP_DETECTION_THRESHOLD:
            return False

        # 检查最近 5 次
        recent = history[-5:]
        types = [h.get("type") for h in recent]
        if len(set(types)) == 1:
            # 全部相同类型
            return True

        return False

    def get_attempt_summary(self, key: str = None) -> dict:
        """获取尝试历史摘要"""
        if key:
            return {
                "key": key,
                "attempts": len(self.attempt_history.get(key, [])),
                "history": self.attempt_history.get(key, [])
            }
        return {
            "keys": list(self.attempt_history.keys()),
            "total_attempts": sum(len(v) for v in self.attempt_history.values())
        }