"""
@description: 圆桌核心 - Phase 1-4 编排、碰撞检测、收敛逻辑
@dependencies: model_gateway, crystallizer, confidence, roles, task_spec, memory, meta_cognition, resilience
@last_modified: 2026-04-06
"""
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from src.utils.model_gateway import get_model_gateway
from scripts.roundtable.crystallizer import Crystallizer, CrystalContext
from scripts.roundtable.confidence import extract_all_claims, detect_conflict, resolve_conflict, validate_confidence_honesty
from scripts.roundtable.roles import get_role_model, get_role_prompt, ROLE_REGISTRY
from scripts.roundtable.task_spec import TaskSpec
from scripts.roundtable.memory import create_decision_memo
from scripts.roundtable.meta_cognition import MetaCognition
from scripts.roundtable.resilience import Resilience, ParkedException


@dataclass
class Phase1Output:
    """Phase 1 输出（独立思考）"""
    role: str
    constraints: List[str]      # 约束清单
    judgments: List[str]        # 关键判断
    uncertainties: List[str]    # 不确定项
    claims: List[Any]           # 解析后的 Claim 对象


@dataclass
class Phase3Output:
    """Phase 3 输出（定向审查）"""
    role: str
    passed: List[str]           # 通过的约束
    failed: List[str]           # 不通过的约束
    confidence_issues: List[str] # 置信度质疑
    suggestions: List[str]      # 修改建议


@dataclass
class CriticResult:
    """Critic 终审结果"""
    acceptance_results: List[str]  # 验收标准逐条结果
    confidence_issues: List[str]   # 置信度审查问题
    unresolved_conflicts: List[str] # 未解决分歧
    p0_issues: List[str]           # P0 问题（必须解决）
    p1_issues: List[str]           # P1 问题（建议优化）
    passed: bool                   # 是否通过


@dataclass
class RoundtableResult:
    """圆桌收敛结果"""
    final_proposal: str              # 收敛后的最终方案
    executive_summary: str           # 压缩后的执行摘要
    all_constraints: List[str]       # 所有已确认的约束
    confidence_map: Dict[str, str]   # 各决策点的置信度
    full_log_path: str               # 完整讨论记录路径
    rounds: int                      # 实际迭代轮数


class Roundtable:
    """圆桌核心引擎

    四层飞轮：
    Phase 1: 独立思考（并行）
    Phase 2: 方案生成（proposer 串行）
    Phase 3: 定向审查（reviewers 并行）
    Phase 4: Critic 终审

    增强机制：
    - MetaCognition: 元认知层，发现盲点和方向性问题
    - Resilience: 韧性机制，诊断-修复-续跑
    """

    def __init__(self, gw=None, feishu=None, log_dir: str = "roundtable_logs",
                 enable_meta: bool = True, enable_resilience: bool = True):
        self.gw = gw or get_model_gateway()
        self.feishu = feishu
        self.log_dir = Path(log_dir)
        self.enable_meta = enable_meta
        self.enable_resilience = enable_resilience

        # 初始化元认知层
        self.meta = MetaCognition(
            claude_bridge=None,  # 延迟导入
            feishu=feishu,
            log_dir=str(self.log_dir)
        ) if enable_meta else None

        # 初始化韧性机制
        self.resilience = Resilience(
            gw=self.gw,
            meta_cognition=self.meta,
            feishu=feishu
        ) if enable_resilience else None

    async def pre_check_task_spec(self, task: TaskSpec, context: CrystalContext) -> TaskSpec:
        """议题审查（圆桌启动前）

        Critic 审查 TaskSpec 本身：
        - 验收标准之间有没有矛盾？
        - 有没有明显遗漏？
        - 标准是否可验证？
        """
        prompt = f"""请审查以下任务规格：

议题：{task.topic}
目标：{task.goal}
验收标准：
{chr(10).join(f'{i+1}. {c}' for i, c in enumerate(task.acceptance_criteria))}

审查要点：
1. 验收标准之间是否有矛盾？
2. 是否有明显遗漏？
3. 每条标准是否可验证（不是模糊表述如"做得好看"）？

如果有问题，请列出具体问题和修改建议。
如果没有问题，回复"TaskSpec 审查通过"。"""

        result = self.gw.call(
            model_name=get_role_model("Critic"),
            prompt=prompt,
            system_prompt=get_role_prompt("Critic"),
            task_type="review",
        )

        if result.get("success"):
            response = result.get("response", "")
            if "审查通过" in response:
                return task
            # 有问题，记录但不自动修改（人工介入）
            self._log_phase("pre_check", "Critic", response)
            if self.feishu:
                self.feishu.notify(f"⚠️ TaskSpec 审查发现问题，请人工确认")

        return task

    async def discuss(self, task: TaskSpec, context: CrystalContext) -> RoundtableResult:
        """圆桌讨论主流程"""
        iteration = 0
        max_iterations = task.max_iterations

        # 创建本次讨论的日志目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_topic = "".join(c for c in task.topic[:20] if c.isalnum() or c in "_-").strip()
        self.current_log_dir = self.log_dir / f"{safe_topic}_{timestamp}"
        self.current_log_dir.mkdir(parents=True, exist_ok=True)

        # Phase 1: 独立思考
        phase1_outputs = await self._phase_1_independent(task, context)
        self._log_phase_outputs("phase1", phase1_outputs)

        # === 元认知层：Phase 1 后盲点检测 ===
        if self.meta:
            blind_spot = await self.meta.check_blind_spots("Phase 1: 独立思考", phase1_outputs)
            if blind_spot:
                context.meta_injection = f"[元认知提醒] {blind_spot}"
                if self.feishu:
                    self.feishu.notify(f"🧠 元认知层发现盲点：{blind_spot[:80]}...")

        while iteration < max_iterations:
            iteration += 1
            if self.feishu:
                self.feishu.notify(f"🔵 圆桌第 {iteration} 轮")

            # Phase 2: 方案生成
            proposal = await self._phase_2_propose(task, context, phase1_outputs)
            self._log_phase("phase2_proposal", task.proposer, proposal)

            # === 元认知层：Phase 2 后方向检查 ===
            if self.meta:
                direction_check = await self.meta.check_blind_spots("Phase 2: 方案生成", {"proposal": proposal})
                if direction_check:
                    context.meta_injection = f"[元认知提醒] {direction_check}"
                    if self.feishu:
                        self.feishu.notify(f"🧠 元认知层提醒：{direction_check[:80]}...")

            # Phase 3: 定向审查
            phase3_outputs = await self._phase_3_review(task, phase1_outputs, proposal)
            self._log_phase_outputs("phase3", phase3_outputs)

            # 碰撞检测
            had_collision = await self._check_collision_quality(phase1_outputs, phase3_outputs)

            # Phase 4: Critic 终审
            critic_result = await self._phase_4_critic(task, proposal, phase3_outputs, had_collision)
            self._log_phase("phase4_critic", "Critic", critic_result)

            # 收敛判断
            if critic_result.passed and not critic_result.p0_issues:
                # 全部通过，收敛
                exec_summary = await self._generate_executive_summary(proposal, phase3_outputs, phase1_outputs)

                # === 元认知层：执行摘要审查 ===
                if self.meta:
                    leo_check = await self.meta.review_executive_summary(exec_summary, task.topic)
                    if leo_check:
                        if self.feishu:
                            self.feishu.notify(f"🧠 Leo 视角追问：{leo_check[:100]}...")
                        # 补充回应（简化处理：记录到日志）
                        self._log_phase("meta_leo_check", "MetaCognition", f"追问: {leo_check}")

                result = RoundtableResult(
                    final_proposal=proposal,
                    executive_summary=exec_summary,
                    all_constraints=self._collect_constraints(phase1_outputs),
                    confidence_map=self._build_confidence_map(phase1_outputs, phase3_outputs),
                    full_log_path=str(self.current_log_dir),
                    rounds=iteration,
                )

                # 保存元认知日志
                if self.meta:
                    self.meta.finalize_logs(task.topic)

                return result

            # 有 P0 问题，迭代修复
            if critic_result.p0_issues:
                if self.feishu:
                    self.feishu.notify(f"🔄 发现 {len(critic_result.p0_issues)} 个 P0 问题，迭代修复")

                # 将 P0 问题反馈给 proposer，修改方案
                feedback = self._build_p0_feedback(critic_result, phase3_outputs)
                phase1_outputs = await self._phase_1_rethink(task, context, feedback, phase1_outputs)
                continue

            # 有未解决分歧
            if critic_result.unresolved_conflicts:
                if self.feishu:
                    self.feishu.notify(f"⚠️ 发现未解决分歧，需人工裁决")
                # 等待人工介入（简化处理：标记后继续）
                break

        # 达到最大轮数
        if self.feishu:
            self.feishu.notify(f"⚠️ 达到最大迭代轮数 {max_iterations}")

        exec_summary = await self._generate_executive_summary(proposal, phase3_outputs, phase1_outputs)

        # 保存元认知日志
        if self.meta:
            self.meta.finalize_logs(task.topic)

        return RoundtableResult(
            final_proposal=proposal,
            executive_summary=exec_summary,
            all_constraints=self._collect_constraints(phase1_outputs),
            confidence_map={},
            full_log_path=str(self.current_log_dir),
            rounds=iteration,
        )

    async def _phase_1_independent(self, task: TaskSpec, context: CrystalContext) -> Dict[str, Phase1Output]:
        """Phase 1: 独立思考（并行）

        所有角色并行，互相不可见。
        输出约束清单、关键判断、不确定项。

        支持韧性机制：通过 resilience.execute() 包装 LLM 调用
        支持断点续跑：捕获 ParkedException，稍后重试
        """
        all_roles = [task.proposer] + task.reviewers
        outputs = {}
        parked = []  # 断点暂存的角色

        async def think(role: str) -> Phase1Output:
            role_context = context.role_slices.get(role, "")
            role_prompt = get_role_prompt(role, task.role_prompts.get(role, ""))
            model = get_role_model(role)

            # 注入元认知提醒（如果有）
            meta_injection = getattr(context, 'meta_injection', '')
            if meta_injection:
                role_context = f"{role_context}\n\n{meta_injection}"

            prompt = f"""{role_context}

【任务】
议题：{task.topic}
目标：{task.goal}

请独立思考，输出以下结构化内容：

## 约束清单（每条一句话 + 置信度标注）
1. [事实/判断/偏好·高/中/低] ...
2. ...

## 关键判断（最多3条，结论先行）
1. ...
2. ...

## 我不确定的（最多2条）
1. ...
"""

            # 通过韧性机制调用 LLM
            async def _call_llm():
                return self.gw.call(
                    model_name=model,
                    prompt=prompt,
                    system_prompt=role_prompt,
                    task_type="reasoning",
                )

            if self.resilience:
                result = await self.resilience.execute(
                    fn=_call_llm,
                    context={"role": role, "phase": "phase_1", "model": model, "task": task.topic}
                )
            else:
                result = await _call_llm()

            if result.get("success"):
                response = result.get("response", "")
                # 解析结构化输出
                constraints = self._extract_section(response, "约束清单")
                judgments = self._extract_section(response, "关键判断")
                uncertainties = self._extract_section(response, "不确定")
                claims = extract_all_claims(response, role)

                return Phase1Output(
                    role=role,
                    constraints=constraints,
                    judgments=judgments,
                    uncertainties=uncertainties,
                    claims=claims,
                )

            return Phase1Output(role=role, constraints=[], judgments=[], uncertainties=[], claims=[])

        # 并行执行（带断点续跑）
        tasks = [think(role) for role in all_roles]

        for i, role in enumerate(all_roles):
            try:
                outputs[role] = await tasks[i]
            except ParkedException as e:
                parked.append((role, e))
                if self.feishu:
                    self.feishu.notify(f"⏸ {role} 暂存，等待模型恢复")

        # 断点续跑：等待一段时间后重试暂存的角色
        if parked:
            await asyncio.sleep(120)  # 等待 2 分钟
            for role, pe in parked:
                try:
                    outputs[role] = await think(role)
                    if self.feishu:
                        self.feishu.notify(f"✅ {role} 已恢复")
                except ParkedException:
                    if self.feishu:
                        self.feishu.notify(f"⚠️ {role} 仍不可用，用已有信息继续")

        return outputs

    async def _phase_2_propose(self, task: TaskSpec, context: CrystalContext,
                               phase1_outputs: Dict[str, Phase1Output]) -> str:
        """Phase 2: 方案生成（proposer 串行）

        Phase 1 三份输出同时公开给 proposer。
        proposer 出具体方案，每个决策点标注回应的约束。

        支持韧性机制：通过 resilience.execute() 包装 LLM 调用
        """
        proposer = task.proposer
        proposer_context = context.role_slices.get(proposer, "")
        model = get_role_model(proposer)

        # 注入元认知提醒（如果有）
        meta_injection = getattr(context, 'meta_injection', '')
        if meta_injection:
            proposer_context = f"{proposer_context}\n\n{meta_injection}"

        # 收集所有角色的约束清单
        all_constraints = []
        for role, output in phase1_outputs.items():
            for c in output.constraints:
                all_constraints.append(f"[{role}] {c}")

        prompt = f"""{proposer_context}

【所有角色的约束清单】
{chr(10).join(all_constraints)}

【任务】
议题：{task.topic}
目标：{task.goal}

请基于所有约束的交集，输出具体方案。
方案中每个决策点必须标注回应了哪条约束。

## 方案描述
（具体方案内容，约 800 字）

## 决策点回应
- 决策1 → 回应约束：[xxx]（置信度：[判断·中]）
- 决策2 → 回应约束：[xxx]（置信度：[判断·高]）

## 自评：最大风险
（方案最大的风险点）
"""

        # 通过韧性机制调用 LLM
        async def _call_llm():
            return self.gw.call(
                model_name=model,
                prompt=prompt,
                system_prompt=get_role_prompt(proposer, task.role_prompts.get(proposer, "")),
                task_type="reasoning",
            )

        if self.resilience:
            result = await self.resilience.execute(
                fn=_call_llm,
                context={"role": proposer, "phase": "phase_2", "model": model, "task": task.topic}
            )
        else:
            result = await _call_llm()

        if result.get("success"):
            return result.get("response", "")
        return ""

    async def _phase_3_review(self, task: TaskSpec,
                              phase1_outputs: Dict[str, Phase1Output],
                              proposal: str) -> Dict[str, Phase3Output]:
        """Phase 3: 定向审查（reviewers 并行）

        每个 reviewer 并行，只审自己擅长的维度。

        支持韧性机制：通过 resilience.execute() 包装 LLM 调用
        """
        outputs = {}

        async def review(role: str) -> Phase3Output:
            my_constraints = phase1_outputs.get(role, Phase1Output(role=role))
            role_prompt = get_role_prompt(role, task.role_prompts.get(role, ""))
            model = get_role_model(role)

            prompt = f"""【你的约束清单】
{chr(10).join(my_constraints.constraints)}

【proposer 的方案】
{proposal}

【任务】
请审查方案：
1. 你的约束，方案满足了吗？哪些没满足？
2. 如果有更好的建议，给出替代方案。
3. 可以挑战 proposer 的置信度标注。

## 通过 ✅
1. 约束X — 满足

## 不通过 ❌
1. 约束Y — 不满足，原因：..., 建议修改：...

## 置信度质疑（如有）
1. proposer 标注[判断·高]但我认为是[判断·低]，理由：...
"""

            # 通过韧性机制调用 LLM
            async def _call_llm():
                return self.gw.call(
                    model_name=model,
                    prompt=prompt,
                    system_prompt=role_prompt,
                    task_type="review",
                )

            if self.resilience:
                result = await self.resilience.execute(
                    fn=_call_llm,
                    context={"role": role, "phase": "phase_3", "model": model, "task": task.topic}
                )
            else:
                result = await _call_llm()

            if result.get("success"):
                response = result.get("response", "")
                passed = self._extract_section(response, "通过")
                failed = self._extract_section(response, "不通过")
                conf_issues = self._extract_section(response, "置信度质疑")
                suggestions = [line for line in failed if "建议" in line]

                return Phase3Output(
                    role=role,
                    passed=passed,
                    failed=failed,
                    confidence_issues=conf_issues,
                    suggestions=suggestions,
                )

            return Phase3Output(role=role, passed=[], failed=[], confidence_issues=[], suggestions=[])

        # 并行执行
        tasks = [review(role) for role in task.reviewers]
        results = await asyncio.gather(*tasks)

        for i, role in enumerate(task.reviewers):
            outputs[role] = results[i]

        return outputs

    async def _check_collision_quality(self, phase1_outputs: Dict, phase3_outputs: Dict) -> bool:
        """碰撞检测

        Phase 3 结束后检测：是否发生了真正的碰撞？

        如果所有 reviewer 都是"全部通过✅"且无置信度质疑
        → 可能是方案确实好，也可能是 reviewer 在敷衍
        → 触发 Critic 用更尖锐的 prompt

        如果有实质性的 ❌ 和质疑
        → 正常进入 Phase 4
        """
        total_passed = 0
        total_failed = 0
        total_conf_issues = 0

        for role, output in phase3_outputs.items():
            total_passed += len(output.passed)
            total_failed += len(output.failed)
            total_conf_issues += len(output.confidence_issues)

        # 有实质碰撞
        if total_failed > 0 or total_conf_issues > 0:
            return True

        # 全部通过，疑似空转
        return False

    async def _phase_4_critic(self, task: TaskSpec, proposal: str,
                              phase3_outputs: Dict[str, Phase3Output],
                              had_collision: bool) -> CriticResult:
        """Phase 4: Critic 终审

        支持韧性机制：通过 resilience.execute() 包装 LLM 调用
        """
        # 收集审查结论
        all_passed = []
        all_failed = []
        all_conf_issues = []

        for role, output in phase3_outputs.items():
            all_passed.extend(output.passed)
            all_failed.extend(output.failed)
            all_conf_issues.extend(output.confidence_issues)

        base_prompt = get_role_prompt("Critic", task.role_prompts.get("Critic", ""))
        model = get_role_model("Critic")

        collision_hint = ""
        if not had_collision:
            collision_hint = """
【特别注意】
各角色似乎过于一致。请主动寻找方案中的盲点、
未覆盖的验收标准、和被回避的困难问题。"""

        prompt = f"""【proposer 方案摘要】
{proposal[:1000]}

【审查结论】
通过项：
{chr(10).join(all_passed[:10]) if all_passed else '无'}

不通过项：
{chr(10).join(all_failed[:10]) if all_failed else '无'}

置信度质疑：
{chr(10).join(all_conf_issues[:5]) if all_conf_issues else '无'}

【验收标准】
{chr(10).join(f'{i+1}. {c}' for i, c in enumerate(task.acceptance_criteria))}
{collision_hint}

请逐条验收标准审查，输出：
## 验收标准审查
- 标准1：✅ 通过 / ❌ 不通过 — 原因：...
- 标准2：...

## 置信度审查
（标注是否诚实）

## P0 问题（必须解决）
1. ...

## P1 问题（建议优化）
1. ...
"""

        # 通过韧性机制调用 LLM
        async def _call_llm():
            return self.gw.call(
                model_name=model,
                prompt=prompt,
                system_prompt=base_prompt,
                task_type="review",
            )

        if self.resilience:
            result = await self.resilience.execute(
                fn=_call_llm,
                context={"role": "Critic", "phase": "phase_4", "model": model, "task": task.topic}
            )
        else:
            result = await _call_llm()

        if result.get("success"):
            response = result.get("response", "")

            # 解析结果
            acceptance_results = self._extract_section(response, "验收标准审查")
            conf_issues = self._extract_section(response, "置信度审查")
            p0 = self._extract_section(response, "P0 问题")
            p1 = self._extract_section(response, "P1 问题")

            # 判断是否通过
            passed = "❌" not in acceptance_results and len(p0) == 0

            return CriticResult(
                acceptance_results=acceptance_results,
                confidence_issues=conf_issues,
                unresolved_conflicts=[],
                p0_issues=p0,
                p1_issues=p1,
                passed=passed,
            )

        return CriticResult(passed=False, acceptance_results=[], confidence_issues=[], unresolved_conflicts=[], p0_issues=["Critic 模型调用失败"], p1_issues=[])

    async def _phase_1_rethink(self, task: TaskSpec, context: CrystalContext,
                               feedback: str, original_outputs: Dict) -> Dict[str, Phase1Output]:
        """基于 P0 反馈重新思考"""
        # 简化：只让 proposer 重新思考
        proposer = task.proposer

        prompt = f"""【P0 问题反馈】
{feedback}

【你的原始约束】
{chr(10).join(original_outputs.get(proposer, Phase1Output(proposer)).constraints)}

请根据反馈调整你的约束和判断，重新输出：
## 约束清单
...

## 关键判断
...
"""

        result = self.gw.call(
            model_name=get_role_model(proposer),
            prompt=prompt,
            system_prompt=get_role_prompt(proposer, task.role_prompts.get(proposer, "")),
            task_type="reasoning",
        )

        if result.get("success"):
            response = result.get("response", "")
            constraints = self._extract_section(response, "约束清单")
            judgments = self._extract_section(response, "关键判断")

            new_output = Phase1Output(
                role=proposer,
                constraints=constraints,
                judgments=judgments,
                uncertainties=[],
                claims=extract_all_claims(response, proposer),
            )

            # 更新 outputs
            updated = original_outputs.copy()
            updated[proposer] = new_output
            return updated

        return original_outputs

    async def _generate_executive_summary(self, proposal: str,
                                           phase3_outputs: Dict,
                                           phase1_outputs: Dict) -> str:
        """Echo 压缩圆桌讨论为执行摘要

        支持韧性机制：通过 resilience.execute() 包装 LLM 调用
        """
        # 收集所有约束
        all_constraints = self._collect_constraints(phase1_outputs)
        model = get_role_model("Echo")

        prompt = f"""【最终方案】
{proposal[:800]}

【确认的约束】
{chr(10).join(all_constraints[:10])}

请压缩为执行摘要（约 500 字），包含：
1. 方案核心描述（只有结论，无讨论过程）
2. 硬约束清单（约 200 字）
3. 具体参数（如有）

不需要包含：
- 讨论过程
- 被否决的方案
- 角色分歧记录
"""

        # 通过韧性机制调用 LLM
        async def _call_llm():
            return self.gw.call(
                model_name=model,
                prompt=prompt,
                system_prompt=get_role_prompt("Echo"),
                task_type="refine",
            )

        if self.resilience:
            result = await self.resilience.execute(
                fn=_call_llm,
                context={"role": "Echo", "phase": "exec_summary", "model": model}
            )
        else:
            result = await _call_llm()

        if result.get("success"):
            return result.get("response", "")
        return proposal[:500]

    def _collect_constraints(self, phase1_outputs: Dict) -> List[str]:
        """收集所有约束"""
        constraints = []
        for role, output in phase1_outputs.items():
            constraints.extend(output.constraints)
        return constraints

    def _build_confidence_map(self, phase1_outputs: Dict, phase3_outputs: Dict) -> Dict[str, str]:
        """构建决策点置信度映射"""
        conf_map = {}
        for role, output in phase1_outputs.items():
            for claim in output.claims:
                if claim.content:
                    key = claim.content[:30]
                    conf_map[key] = f"{claim.claim_type}·{claim.confidence}"
        return conf_map

    def _build_p0_feedback(self, critic_result: CriticResult, phase3_outputs: Dict) -> str:
        """构建 P0 反馈文本"""
        lines = ["## P0 问题清单"]
        lines.extend(critic_result.p0_issues)
        lines.append("\n## Reviewer 建议")
        for role, output in phase3_outputs.items():
            if output.suggestions:
                lines.append(f"[{role}] " + "\n".join(output.suggestions))
        return "\n".join(lines)

    def _extract_section(self, text: str, section_name: str) -> List[str]:
        """从结构化文本中提取指定部分"""
        lines = []
        in_section = False
        for line in text.split("\n"):
            if line.startswith(f"## {section_name}"):
                in_section = True
                continue
            if in_section and line.startswith("## "):
                break
            if in_section and line.strip():
                lines.append(line.strip())
        return lines

    def _log_phase(self, phase: str, role: str, content: Any):
        """记录 Phase 输出到磁盘"""
        if not hasattr(self, "current_log_dir"):
            return

        filename = f"{phase}_{role}.md"
        filepath = self.current_log_dir / filename

        if isinstance(content, str):
            filepath.write_text(content, encoding="utf-8")
        else:
            # CriticResult 等对象
            filepath.write_text(str(content), encoding="utf-8")

    def _log_phase_outputs(self, phase: str, outputs: Dict):
        """记录多个 Phase 输出"""
        for role, output in outputs.items():
            self._log_phase(phase, role, output)