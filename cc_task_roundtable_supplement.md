# CC 补充任务：圆桌系统增强 — 元认知层 + 韧性机制

> 基于已实现的 scripts/roundtable/ 框架，补充两个关键模块。
> 架构讨论已完成，直接执行。

---

## 补充 1：思考通道作为元认知层

### 背景

Claude 思考通道（通过 `scripts/claude_bridge.py` 的 `call_claude_via_cdp()` 调用）不是圆桌中的一个角色，而是站在圆桌之外审视整盘棋的"元裁判"。

它不参与方案设计、不参与审查，它判断的是："这场讨论本身在做对的事吗？"

### 新增文件：`scripts/roundtable/meta_cognition.py`

```python
"""
元认知层：Claude 思考通道嵌入圆桌系统
不参与打球，判断这场球赛打得对不对。
"""

class MetaCognition:
    def __init__(self, claude_bridge, feishu):
        """
        claude_bridge: scripts/claude_bridge.py 的调用接口
        feishu: 飞书通知
        """
        self.bridge = claude_bridge
        self.feishu = feishu
    
    async def check_blind_spots(self, phase_name: str, phase_outputs: dict) -> str | None:
        """
        每个 Phase 完成后调用。
        
        问思考通道一个固定问题：
        "这一轮讨论（{phase_name}），以下是各角色的输出。
         有没有被集体忽略的盲点？有没有在错误前提上推进？
         如果没问题，回复'无问题'。
         如果有问题，简要说明是什么问题，不超过200字。"
        
        如果思考通道发现问题 → 返回问题描述，注入到下一个 Phase 的上下文
        如果没问题 → 返回 None，流程不阻塞
        
        超时处理：如果思考通道 60 秒内无响应，不阻塞，返回 None 继续
        """

    async def review_executive_summary(self, summary: str, task_topic: str) -> str | None:
        """
        圆桌收敛后、Generator 生成前调用。
        
        问思考通道：
        "以下是圆桌讨论收敛后的执行摘要，即将用于生成{task_topic}。
         如果你是创始人 Leo，看到这份摘要，你会批准还是会追问什么？
         如果批准，回复'批准'。
         如果有疑问，说明追问什么，不超过200字。"
        
        思考通道有 thinking_history.jsonl 积累的 Leo 决策偏好，
        能模拟 Leo 视角做预审。减少 Leo 需要介入的频率。
        
        如果有疑问 → 返回追问内容，圆桌补充回应后再生成
        如果批准 → 返回 None，继续
        """

    async def final_quality_gate(self, output: str, task_topic: str) -> str | None:
        """
        Verifier 通过后、最终输出前调用。
        
        问思考通道：
        "以下是{task_topic}的最终输出（代码/文档摘要）。
         Verifier 已通过所有验收标准。
         但验收标准可能有遗漏——你作为最终把关，
         这个输出拿去给投资人/供应商看，会不会丢人？
         有没有验收标准没覆盖到但明显有问题的地方？
         如果没问题，回复'通过'。
         如果有问题，说明是什么，不超过300字。"
        
        这不是逐条验收标准检查（Verifier 已做），
        而是整体品质和 sense 的判断。
        """

    async def judge_crystallization_level(self, new_conclusions: list[str], task_topic: str) -> str:
        """
        知识回写时调用。
        
        问思考通道：
        "圆桌讨论{task_topic}产出了以下新结论。
         每条结论应该写入哪个级别？
         A. 决策备忘录（decision_memo）— 具体议题的结论
         B. 产品锚点（product_anchor）— 影响产品方向的重大决策
         C. 不值得记录 — 过于细节或临时性的判断
         逐条回复级别即可。"
        
        确保重要结论不会被埋在备忘录里，
        也确保不会把鸡毛蒜皮的事写进产品锚点。
        """

    async def diagnose_system_issue(self, error, phase, context) -> dict:
        """
        韧性机制调用（见补充 2）。
        
        当系统在某个环节反复出错时，把完整的错误链路推给思考通道诊断：
        "圆桌系统在{phase}环节反复出错。
         错误信息：{error}
         已尝试的修复：{attempts}
         请诊断根因，可能是：
         1. 模型能力不足（建议换哪个模型）
         2. prompt 有问题（建议怎么改）
         3. TaskSpec 有问题（验收标准矛盾/遗漏）
         4. 其他原因
         给出诊断和建议的修复行动。"
        
        返回 {"diagnosis": str, "action": "retry"|"change_model"|"modify_spec"|"escalate_to_leo", "details": str}
        """
```

### 嵌入 roundtable.py 的位置

在已有的 `roundtable.py` 中，在每个 Phase 之间插入 MetaCognition 调用：

```python
# Phase 1 完成后
phase1_outputs = await self._phase_1_independent(task, context)
blind_spot = await self.meta.check_blind_spots("Phase 1: 独立思考", phase1_outputs)
if blind_spot:
    # 注入到 Phase 2 的上下文
    context.meta_injection = f"[元认知提醒] {blind_spot}"
    await self._notify(f"🧠 元认知层发现盲点：{blind_spot[:80]}...")

# Phase 2 完成后
proposal = await self._phase_2_propose(task, context, phase1_outputs)
direction_check = await self.meta.check_blind_spots("Phase 2: 方案生成", {"proposal": proposal})
if direction_check:
    context.meta_injection = f"[元认知提醒] {direction_check}"

# 收敛后，生成前
summary = await self._generate_executive_summary(...)
leo_check = await self.meta.review_executive_summary(summary, task.topic)
if leo_check:
    # 需要补充回应，把追问反馈给 Echo 补充摘要
    summary = await self._supplement_summary(summary, leo_check)

# Verifier 通过后，输出前
quality_check = await self.meta.final_quality_gate(output, task.topic)
if quality_check:
    # 回到 Generator 修复
    output = await gen.fix(output, [quality_check], result)

# 知识回写时
levels = await self.meta.judge_crystallization_level(new_conclusions, task.topic)
```

### 关键约束

- **不阻塞**：思考通道的每次调用设 60 秒超时，超时返回 None，流程继续
- **不替代角色**：元认知层不出方案、不做审查，只发现盲点和方向性问题
- **不频繁调用**：只在 Phase 之间的关键节点调用，不是每次 LLM 调用都过一遍
- **结果写日志**：每次元认知调用的输入输出写入 `roundtable_logs/{task}/meta_cognition.md`
- **CDP 桥接**：使用已有的 `scripts/claude_bridge.py` 的 `call_claude_via_cdp()` 接口，不新增 Claude 调用通道

---

## 补充 2：韧性机制（Resilience）

### 背景

当前 agent_company 碰到报错的处理方式是降级或中止。两种都不对。
- 降级 = 接受低质量输出
- 中止 = 放弃任务

正确的处理是：**诊断原因 → 自主修复 → 断点续跑。** 报错是需要解决的问题，不是终止或降级的理由。

### 新增文件：`scripts/roundtable/resilience.py`

```python
"""
韧性机制：诊断-修复-续跑，替代降级和中止。
三个原则：
1. 平替不降级 — 换同级别模型，不降低质量预期
2. 诊断先于修复 — 搞清楚为什么错，再决定怎么修
3. 断点续跑不中止 — 某步走不通先跑其他步骤，回头处理
"""

class Resilience:
    def __init__(self, gw, meta_cognition, feishu):
        """
        gw: ModelGateway
        meta_cognition: MetaCognition 实例（用于根因诊断）
        feishu: 飞书通知
        """
        self.gw = gw
        self.meta = meta_cognition
        self.feishu = feishu
        self.attempt_history = {}  # 跟踪每个环节的尝试历史
    
    async def execute(self, fn, context: dict) -> any:
        """
        所有 LLM 调用和 Phase 执行都经过这一层。
        不是 try-except-pass，是 try-diagnose-fix-retry。
        
        参数：
        - fn: async callable，实际要执行的函数
        - context: dict，包含 role, phase, model, task 等信息
        
        返回：fn 的成功结果
        """
        role = context.get("role", "unknown")
        phase = context.get("phase", "unknown")
        key = f"{phase}:{role}"
        self.attempt_history[key] = []
        
        while True:
            try:
                result = await fn()
                
                # 检查输出质量
                quality = self._check_output_quality(result, context)
                if quality["ok"]:
                    return result
                
                # ── 输出质量不达标 ──
                self.attempt_history[key].append({
                    "type": "quality_fail",
                    "issues": quality["issues"],
                    "model": context.get("model")
                })
                
                # 第一次：反馈修正，同一模型重试
                if len([a for a in self.attempt_history[key] if a["type"] == "quality_fail"]) <= 2:
                    await self._notify(f"🔄 {role} 输出质量不达标，反馈修正中...")
                    result = await self._retry_with_feedback(fn, quality["issues"], context)
                    quality2 = self._check_output_quality(result, context)
                    if quality2["ok"]:
                        return result
                
                # 反复出问题 → 换同级别模型
                peer = self._get_peer_model(context)
                if peer:
                    context["model"] = peer
                    await self._notify(f"🔄 {role} 切换至同级别模型 {peer}（非降级）")
                    continue
                
                # 所有同级别模型都试过 → 思考通道诊断
                diagnosis = await self.meta.diagnose_system_issue(
                    quality["issues"], phase, context
                )
                action = await self._apply_diagnosis(diagnosis, context)
                if action == "retry":
                    continue
                elif action == "escalate":
                    await self._escalate_to_leo(key, context, diagnosis)
                    return await self._wait_and_retry(fn, context)
                    
            except Exception as e:
                self.attempt_history[key].append({
                    "type": "exception",
                    "error": str(e),
                    "model": context.get("model")
                })
                
                # ── 模型调用失败 ──
                if self._is_model_error(e):
                    peer = self._get_peer_model(context)
                    if peer:
                        context["model"] = peer
                        await self._notify(f"⚡ {role} 模型异常，平替至 {peer}")
                        continue
                    
                    # 所有模型不可用 → 暂存断点
                    await self._notify(f"⏸ {role} 所有模型暂不可用，暂存断点，继续其他步骤")
                    raise ParkedException(key, context)
                
                # ── 其他异常 → 思考通道诊断 ──
                diagnosis = await self.meta.diagnose_system_issue(
                    str(e), phase, context
                )
                action = await self._apply_diagnosis(diagnosis, context)
                if action == "retry":
                    continue
                elif action == "escalate":
                    await self._escalate_to_leo(key, context, diagnosis)
                    return await self._wait_and_retry(fn, context)
    
    def _check_output_quality(self, result, context) -> dict:
        """
        检查 LLM 输出质量（规则层，不调 LLM）：
        - 结果不为空
        - 如果是圆桌 Phase 输出：是否包含置信度标注
        - 如果是圆桌 Phase 输出：是否符合结构化模板
        - 字数是否在合理范围内（不是空的，也不是几万字的垃圾）
        
        返回 {"ok": bool, "issues": list[str]}
        """
    
    def _get_peer_model(self, context) -> str | None:
        """
        获取同级别备选模型，不是降级。
        
        同级别映射（在 roles.py 中定义）：
        - gpt_5_4 ↔ gemini_3_1_pro（推理能力同级）
        - deepseek_v3 ↔ gpt_4o_norway（中等能力同级）
        - gemini_2_5_flash ↔ doubao_seed_pro（轻量同级）
        
        如果当前模型的 peer 已经在本轮试过了 → 返回 None
        """
    
    async def _retry_with_feedback(self, fn, issues, context):
        """
        把质量问题反馈给同一模型重试。
        
        prompt 追加："上次输出存在以下问题：{issues}，请修正。
                      严格遵守输出模板格式。"
        """
    
    async def _apply_diagnosis(self, diagnosis, context) -> str:
        """
        根据思考通道的诊断结果执行修复：
        
        - "retry": 修改 prompt 后重试
        - "change_model": 换到诊断建议的模型
        - "modify_spec": 调整 TaskSpec（如验收标准矛盾）
        - "escalate": 上报 Leo
        
        返回 action 字符串
        """
    
    async def _escalate_to_leo(self, key, context, diagnosis):
        """
        上报 Leo。不是简单说"出错了"，而是打包完整诊断链路：
        
        飞书通知内容：
        "🔶 圆桌系统在 {phase} 环节遇到能力边界
         角色：{role}
         问题：{diagnosis['diagnosis']}
         已尝试：{self.attempt_history[key] 的摘要}
         思考通道诊断：{diagnosis['details']}
         建议：{diagnosis['action']}
         
         请回复处理意见。"
        """
    
    async def _wait_and_retry(self, fn, context):
        """
        等待 Leo 通过飞书回复后，根据回复内容调整 context 再重试。
        等待期间不阻塞其他任务。
        """
    
    def _is_model_error(self, e) -> bool:
        """判断是否为模型调用层面的错误（404、超时、认证失败等）"""

    # ── 自我健康检测 ──
    
    def _detect_infinite_loop(self, key) -> bool:
        """
        检测自身是否陷入无效循环。
        
        规则：
        - 同一个 key 的尝试历史超过 10 次
        - 且最近 5 次的错误类型相同
        → 判断为可能的无限循环
        
        触发时：把完整的尝试历史打包，通知 Leo：
        "系统检测到自己可能在无效循环。
         这是完整的诊断链路：[历史]
         这个问题可能超出了我当前的能力边界。"
        
        不是任务失败，是系统在说"我需要帮助"。
        """


class ParkedException(Exception):
    """断点暂存异常。调用方捕获后跳过当前步骤，继续其他步骤，稍后回来重试。"""
    def __init__(self, key, context):
        self.key = key
        self.context = context
```

### 同级别模型映射

在 `roles.py` 中补充 peer model 定义：

```python
PEER_MODELS = {
    # 强推理层
    "gpt_5_4": ["gemini_3_1_pro"],
    "gemini_3_1_pro": ["gpt_5_4"],
    
    # 中等能力层
    "deepseek_v3_volcengine": ["gpt_4o_norway", "gemini_2_5_pro"],
    "gpt_4o_norway": ["deepseek_v3_volcengine", "gemini_2_5_pro"],
    "gemini_2_5_pro": ["deepseek_v3_volcengine", "gpt_4o_norway"],
    
    # 轻量层
    "gemini_2_5_flash": ["doubao_seed_pro"],
    "doubao_seed_pro": ["gemini_2_5_flash"],
}
```

### 嵌入 roundtable.py

所有 LLM 调用都通过 `resilience.execute()` 包装：

```python
# 之前：
result = await self.gw.call(model, prompt, task_type="roundtable")

# 改为：
result = await self.resilience.execute(
    fn=lambda: self.gw.call(model, prompt, task_type="roundtable"),
    context={"role": "CDO", "phase": "phase_1", "model": model, "task": task}
)
```

### 断点续跑机制

在 `roundtable.py` 的 Phase 编排层面处理 `ParkedException`：

```python
# Phase 1 并行执行时
phase1_results = {}
parked = []

for role in roles:
    try:
        phase1_results[role] = await self.resilience.execute(
            fn=lambda r=role: self._call_role(r, ...),
            context={"role": role, "phase": "phase_1", ...}
        )
    except ParkedException as e:
        parked.append(e)
        await self._notify(f"⏸ {role} 暂存，等待模型恢复")

# 如果有角色被暂存，等一段时间后重试
if parked:
    await asyncio.sleep(120)  # 等 2 分钟
    for pe in parked:
        try:
            phase1_results[pe.context["role"]] = await self.resilience.execute(
                fn=lambda r=pe.context["role"]: self._call_role(r, ...),
                context=pe.context
            )
        except ParkedException:
            # 仍然不可用 → 用已有的角色结果继续，但标记信息不完整
            await self._notify(f"⚠️ {pe.context['role']} 仍不可用，用已有信息继续")
```

---

## 集成测试

补充完成后，用 HUD Demo TaskSpec 端到端测试：

1. 确认 MetaCognition 的各个 check 点正常调用（即使思考通道暂时不可用也不阻塞）
2. 模拟模型故障：临时禁用一个模型，确认 Resilience 自动平替
3. 模拟输出质量问题：故意传入格式错误的 prompt，确认反馈修正机制
4. 确认所有日志写入 roundtable_logs/
5. 确认飞书通知在每个关键节点都有

测试通过后 git commit。
