# 圆桌系统架构设计 · `scripts/roundtable/`

> 本文档是 CC 的完整实施指令。架构讨论已在 Claude Chat 完成，直接执行。
> 验证任务：通过 TaskSpec 传入 HUD Demo 生成任务，但系统本身是通用任务引擎，不包含任何 HUD 相关硬编码。

---

## 一、核心理念

agent_company 的当前管道是流水线式分段加工——A 做完传给 B，B 做完传给 C。信息在每一步损耗，没有视角碰撞，没有质量闭环。

圆桌系统是替代方案：**多角色围绕同一个议题，独立思考→信息增量构建→交叉审查→收敛→生成→审查迭代**，直到验收标准全部通过。

三层飞轮一体运行，不分先后：
- **知识结晶**：把 KB 原料转化为高密度决策备忘录
- **圆桌碰撞**：多角色有序讨论，视角碰撞产出比单一模型更好的方案
- **审查闭环**：生成物必须通过验收标准，不通过就迭代修复

最终判断标准：**圆桌系统输出的质量 > 单个最强模型直接输出的质量。** 如果做不到，说明改造没到位。

---

## 二、文件结构

```
scripts/roundtable/
├── __init__.py              # 公开接口：run_task(task_spec, gw, kb, feishu)
├── task_spec.py             # TaskSpec 数据类定义
├── crystallizer.py          # 知识结晶：KB → 决策备忘录 + 角色分片上下文
├── roundtable.py            # 圆桌核心：Phase 1-4 编排
├── generator.py             # 生成器：拿圆桌结论生成具体产物
├── verifier.py              # 审查闭环：规则 + Critic 审查 → 缺陷 → 迭代
├── memory.py                # 决策备忘录读写管理（.ai-state/decision_memos/）
├── roles.py                 # 角色注册表：模型 + 通用 system prompt 骨架
└── confidence.py            # 置信度标注解析 + 冲突裁决逻辑
```

与现有系统的关系：
- 共享 `src/utils/model_gateway/` 和 `src/tools/knowledge_base.py`
- 与 `scripts/deep_research/` 平级，互不干扰
- 旧 `scripts/demo_generator.py` 保留不动

---

## 三、TaskSpec 定义（task_spec.py）

```python
from dataclasses import dataclass, field

@dataclass
class TaskSpec:
    # ── 议题 ──
    topic: str                          # 简短议题名："HUD Demo 生成"
    goal: str                           # 一句话目标
    
    # ── 验收标准（退出条件，不是轮数）──
    acceptance_criteria: list[str]      # 每条可验证，全部通过才算完成
    
    # ── 角色分配 ──
    proposer: str                       # 出方案的角色："CDO"
    reviewers: list[str]                # 审方案的角色：["CTO", "CMO"]
    critic: str                         # 终审："Critic"
    
    # ── 权威性映射（冲突裁决用）──
    authority_map: dict[str, str]       # {"design":"CDO", "feasibility":"CTO", "user_fit":"CMO", "final":"Leo"}
    
    # ── 输入 ──
    input_docs: list[str]               # 输入文档路径列表
    kb_search_queries: list[str]        # KB 搜索关键词，用于 Crystallizer 准备上下文
    
    # ── 角色议题专属 prompt（角色×议题矩阵）──
    role_prompts: dict[str, str]        # {"CDO": "本议题下你需要关注...", "CTO": "...", ...}
    
    # ── 输出 ──
    output_type: str                    # "html" | "markdown" | "json" | "code"
    output_path: str                    # 输出文件路径
```

**关键设计**：
- `acceptance_criteria` 是唯一退出条件，没有轮数上限
- `role_prompts` 是角色×议题的专属 prompt，不是通用角色描述
- `authority_map` 定义冲突裁决权威，`"final": "Leo"` 表示不可调和分歧上报人工
- TaskSpec 不包含任何业务逻辑，是纯配置

---

## 四、置信度与冲突裁决（confidence.py）

### 4.1 置信度标注格式

每个角色的每条输出必须使用以下标注格式（通过 system prompt 强制）：

```
[事实·高] 陈述内容 — 来源：xxx
[事实·中] 陈述内容 — 来源：xxx，但数据不完整
[判断·高] 陈述内容 — 基于：有直接研究数据支撑
[判断·中] 陈述内容 — 基于：类似领域类推
[判断·低] 陈述内容 — 基于：个人推测
[偏好·--] 陈述内容 — 设计选择，无对错
```

三种命题类型：
- **事实类**：可验证的客观陈述，有数据源支撑就高置信
- **判断类**：基于专业经验的推断，有直接数据高置信，类推中置信，推测低置信
- **偏好类**：主观选择，不参与置信度裁决

### 4.2 冲突裁决规则

```python
def resolve_conflict(claim_a, claim_b, authority_map, topic_dimension):
    """
    裁决规则（按优先级）：
    
    1. 硬约束否决软偏好
       事实·高 的"做不到" > 任何判断或偏好
       但必须区分"做不到"（事实）和"很难做"（判断）——后者可被挑战
    
    2. 同维度冲突看置信度
       高 > 中 > 低
    
    3. 同维度同置信度看权威性
       该维度 authority_map 中指定的角色胜出
    
    4. 跨维度冲突不自动裁决
       → 标记为"未解决分歧"→ 飞书通知 Leo
       附上：双方立场 + 置信度 + 依据
    """
```

### 4.3 Critic 的置信度审查职责

Critic 不参与裁决，职责是审查置信度标注是否诚实：
- 角色把"判断·中"标成"事实·高"来增加权重 → Critic 指出
- 角色声称有数据支撑但未引用具体来源 → Critic 要求补充
- 角色的多条输出之间自相矛盾 → Critic 指出

---

## 五、知识结晶（crystallizer.py）

### 5.1 准备上下文

```python
class Crystallizer:
    async def prepare_context(self, task: TaskSpec) -> CrystalContext:
        """
        1. 读取核心锚点文档（product_anchor.md, founder_mindset.md）
        2. 读取与 task.topic 相关的已有决策备忘录（.ai-state/decision_memos/）
        3. 从 KB 搜索相关条目（使用 task.kb_search_queries）
        4. 用 gpt_5_4 提炼 KB 条目为关键事实摘要（~500字）
        5. 按角色分片：每个角色只收到与自己职责相关的上下文部分
        
        输出 CrystalContext：
        - anchor_docs: str            # 核心锚点（所有角色共享）
        - decision_memos: str         # 已有备忘录（所有角色共享）
        - distilled_facts: str        # 提炼后的关键事实（所有角色共享）
        - raw_kb_refs: list[str]      # 原始 KB 条目摘要（可查但不默认传递）
        - role_slices: dict[str, str] # 角色专属上下文分片
        """
```

### 5.2 角色分片逻辑

不是所有角色读同一份大文档：
- **CMO** 收到：用户画像 + 竞品数据 + 产品锚点中的用户需求部分
- **CTO** 收到：技术约束 + 供应商数据 + 产品锚点中的技术选型部分
- **CDO** 收到：设计原则 + 视觉参考 + 产品锚点中的形态/审美部分
- **Critic** 收到：验收标准 + 所有角色的分片摘要（用于审查完整性）

分片逻辑通过 KB 搜索关键词 + 文档段落的语义匹配实现。如果无法自动分片，退化为所有角色收到相同的提炼版上下文（可用但非最优）。

### 5.3 知识回写

```python
    async def crystallize_learnings(self, task: TaskSpec, roundtable_output: RoundtableResult):
        """
        圆桌结束后，将讨论中产生的新结论写回决策备忘录。
        
        1. 扫描圆桌各 Phase 输出，提取"达成共识的判断"
        2. 更新或新建 .ai-state/decision_memos/{topic}.md
        3. 如果结论影响产品锚点级别的决策 → 标记需要 Leo 确认
        """
```

决策备忘录格式：
```markdown
# 决策备忘录：{topic}
更新时间：{datetime}
状态：已确认 | 待确认

## 结论
{一段话总结}

## 支撑依据
1. [事实·高] ...
2. [判断·中] ...

## 否决的替代方案
- 方案X：否决理由——...

## 待确认
- {如有}
```

---

## 六、圆桌核心（roundtable.py）

### 6.0 议题审查（圆桌启动前）

```python
async def _pre_check_task_spec(self, task: TaskSpec, context: CrystalContext) -> TaskSpec:
    """
    Critic 审查 TaskSpec 本身：
    - 验收标准之间有没有矛盾？
    - 有没有明显遗漏？
    - 标准是否可验证（不是"做得好看"这种模糊表述）？
    
    如果有问题 → 修正 TaskSpec 再启动讨论
    如果没问题 → 原样返回
    """
```

### 6.1 Phase 1：独立思考（并行）

```python
async def _phase_1_independent(self, task, context) -> dict[str, str]:
    """
    所有角色并行，互相不可见。
    
    每个角色收到：
    - CrystalContext 中该角色的分片（role_slices[role]）
    - 共享的锚点文档 + 决策备忘录
    - task 的 goal + acceptance_criteria
    - role_prompts[role]（议题专属 prompt）
    
    每个角色输出（结构化模板，≤800字）：
    
    ## 约束清单（每条一句话 + 置信度标注）
    1. [事实·高] ...
    2. [判断·中] ...
    
    ## 关键判断（最多3条，结论先行）
    1. ...
    2. ...
    
    ## 我不确定的（最多2条）
    1. ...
    
    目的：形成独立判断，不被其他角色影响。
    输出的是约束和判断，不是方案。
    """
```

### 6.2 Phase 2：方案生成（proposer 串行）

```python
async def _phase_2_propose(self, task, context, phase1_outputs: dict) -> str:
    """
    Phase 1 三份输出同时公开给 proposer。
    
    proposer 收到：
    - 自己的 Phase 1 输出
    - 所有其他角色的 Phase 1 输出（结构化约束清单）
    - CrystalContext 中自己的分片
    - 指令："基于所有约束的交集，出具体方案。
             方案中每个决策点必须标注回应了哪条约束。"
    
    proposer 输出（≤1200字）：
    - 方案描述
    - 每个决策点 → 回应了哪条约束 + 置信度
    - 自评：方案的最大风险
    
    Phase 1 三份约束清单总计约 2400 字 + proposer 自己的分片上下文
    → proposer 的输入总量控制在 ~4000 字
    """
```

### 6.3 Phase 3：定向审查（reviewers 并行）

```python
async def _phase_3_review(self, task, phase1_outputs, proposal) -> dict[str, str]:
    """
    每个 reviewer 并行，只审自己擅长的维度。
    
    每个 reviewer 收到：
    - proposer 的方案
    - 自己的 Phase 1 约束清单
    - 指令："你的约束，方案满足了吗？哪些没满足？
             如果有更好的建议，给出替代方案。
             可以挑战 proposer 的置信度标注。"
    
    每个 reviewer 输出（≤600字）：
    
    ## 通过 ✅
    1. 约束X — 满足
    
    ## 不通过 ❌
    1. 约束Y — 不满足，原因：..., 建议修改：...
    
    ## 置信度质疑（如有）
    1. proposer 标注[判断·高]但我认为是[判断·低]，理由：...
    """
```

### 6.4 碰撞检测

```python
async def _check_collision_quality(self, phase1_outputs, phase3_outputs) -> bool:
    """
    Phase 3 结束后检测：是否发生了真正的碰撞？
    
    如果所有 reviewer 都是"全部通过✅"且无置信度质疑
    → 可能是方案确实好，也可能是 reviewer 在敷衍
    → 触发 Critic 用更尖锐的 prompt 进入 Phase 4
    
    如果有实质性的 ❌ 和质疑
    → 正常进入 Phase 4
    
    返回 True = 有碰撞，False = 疑似空转
    """
```

### 6.5 Phase 4：Critic 终审

```python
async def _phase_4_critic(self, task, proposal, reviews, had_collision: bool) -> CriticResult:
    """
    Critic 收到：
    - proposer 的方案摘要
    - 每个 reviewer 的审查结论
    - 验收标准清单
    - had_collision 标记
    
    如果 had_collision=False，Critic 的 prompt 追加：
    "各角色似乎过于一致。请主动寻找方案中的盲点、
     未覆盖的验收标准、和被回避的困难问题。"
    
    Critic 输出：
    - 验收标准逐条：通过 ✅ / 不通过 ❌ + 原因
    - 置信度审查：标注是否诚实
    - 未解决分歧清单（如有）
    - P0 问题清单（必须解决）
    - P1 问题清单（建议优化）
    """
```

### 6.6 收敛

```python
async def _converge(self, task, context, proposal, reviews, critic_result) -> RoundtableResult:
    """
    Echo(CPO) 综合所有输出。
    
    情况 1：Critic 全部 ✅，无 P0
    → 直接收敛，生成执行摘要
    
    情况 2：有 P0 问题
    → 把 P0 缺陷清单 + reviewer 的修改建议反馈给 proposer
    → proposer 修改方案
    → 再跑 Phase 3 + Phase 4
    → 退出条件：P0 全部解决
    
    情况 3：有未解决分歧（跨维度冲突）
    → 飞书通知 Leo，附结构化的双方立场 + 置信度 + 依据
    → 等待 Leo 裁决后继续
    
    情况 4：同一 P0 问题连续两轮未解决
    → 判断为能力不足
    → 尝试升级：换更强模型 / 拆解为子问题
    → 如果仍无法解决 → 飞书通知人工，说明卡在哪里
    
    最终输出 RoundtableResult：
    - final_proposal: str          # 收敛后的最终方案
    - executive_summary: str       # 压缩后的执行摘要（给 Generator 用）
    - all_constraints: list[str]   # 所有已确认的约束
    - confidence_map: dict         # 各决策点的置信度
    - full_log_path: str           # 完整讨论记录磁盘路径
    """
```

### 6.7 执行摘要生成

```python
async def _generate_executive_summary(self, proposal, reviews, constraints) -> str:
    """
    Echo 将圆桌讨论的最终结论压缩为 Generator 直接可用的执行指令。
    
    包含：
    - 确认的方案描述（~500字，只有结论，没有讨论过程）
    - 硬约束清单（~200字）
    - 验收标准（原文）
    - 具体参数（配色值、布局坐标、素材路径等）
    
    不包含：
    - 讨论过程
    - 被否决的方案
    - 角色之间的分歧记录
    
    讨论全程完整记录保存在 roundtable_logs/ 供追溯和知识结晶使用。
    """
```

---

## 七、生成器（generator.py）

```python
class Generator:
    async def generate(self, task: TaskSpec, rt_result: RoundtableResult) -> str:
        """
        拿圆桌收敛后的执行摘要，调最强模型生成产物。
        
        Generator 收到的是精炼后的执行指令（≤2000字），
        不是讨论过程。
        
        模型选择：gpt_5_4（代码/HTML）或按 task.output_type 匹配
        降级链：gpt_5_4 → gpt_4o_norway
        """
    
    async def fix(self, current_output: str, issues: list[str], rt_result: RoundtableResult) -> str:
        """
        根据 Verifier 的缺陷清单修复输出。
        
        模型收到：
        - 当前输出代码
        - 具体缺陷清单（每条缺陷 + 期望行为）
        - 执行摘要（用于理解原始意图）
        
        不是重新生成，是定点修复。
        """
```

---

## 八、审查闭环（verifier.py）

```python
class Verifier:
    async def verify(self, task: TaskSpec, output: str) -> VerifyResult:
        """
        混合验证。
        
        规则层（代码，不调 LLM）：
        - 文件格式正确性（HTML 标签闭合、JSON 可解析等）
        - 验收标准中可自动验证的项（关键词存在性、文件大小等）
        
        LLM 层（Critic 模型：gemini_3_1_pro）：
        - 逐条验收标准评分：通过/不通过 + 缺陷描述
        - 注意：Critic 看代码内容，不只是看文件是否存在
        
        输出 VerifyResult：
        - passed: bool              # 全部通过
        - issues: list[Issue]       # 未通过的缺陷清单
        - stuck: bool               # 同一缺陷连续两轮未修复
        - stuck_issues: list[str]   # 卡住的具体问题
        """
```

**退出条件**：
- `passed=True` → 完成
- `stuck=True` → 升级策略（换模型/拆子问题/通知人工）
- 否则 → 继续迭代

**没有轮数上限。** 退出靠验收标准和卡住检测，不靠计数器。

---

## 九、角色系统（roles.py）

### 9.1 角色注册表

```python
ROLE_REGISTRY = {
    "CDO": {
        "model": "deepseek_v3_volcengine",
        "base_prompt": """你是产品设计总监。
你的核心能力是用户体验设计和视觉方案。
你的盲区：技术可行性、工程复杂度、成本约束。
当 CTO 的技术约束与你的方案冲突时，优先考虑技术约束是否为硬约束。
所有输出必须使用置信度标注格式。""",
    },
    "CTO": {
        "model": "gpt_5_4",
        "base_prompt": """你是技术总监。
你的核心能力是系统架构和工程可行性判断。
你的盲区：用户体验感受、市场竞争态势。
区分"做不到"和"很难做"——前者是硬约束，后者是可挑战的判断。
所有输出必须使用置信度标注格式。""",
    },
    "CMO": {
        "model": "gpt_4o_norway",
        "base_prompt": """你是市场总监。
你的核心能力是用户需求洞察和竞品对标。
你的盲区：技术实现成本、理想化的用户预期。
你的核心价值：带入真实用户视角——骑手真的会用吗？愿意付钱吗？
所有输出必须使用置信度标注格式。""",
    },
    "Critic": {
        "model": "gemini_3_1_pro",
        "base_prompt": """你是独立质量审查官。
你不设计方案，你审查方案。
你的三个职责：
1. 逐条对照验收标准判断方案是否满足
2. 审查置信度标注是否诚实
3. 找到各角色回避的困难问题
每个问题标注：P0（必须解决）或 P1（建议优化）。
只有 P0 阻塞交付。不要吹毛求疵。""",
    },
    "Echo": {
        "model": "gpt_5_4",
        "base_prompt": """你是 CPO，圆桌的主持者和最终决策整合者。
你的职责：
1. 综合各角色观点，在约束交集内找到最优方案
2. 将讨论结论压缩为执行摘要
3. 识别未解决分歧并结构化上报
你不偏袒任何角色，按裁决规则处理冲突。""",
    },
}
```

### 9.2 角色×议题 prompt

TaskSpec 的 `role_prompts` 字段为每个角色提供议题专属的补充 prompt，和 `base_prompt` 拼接使用。

示例（HUD Demo 任务）：
```python
role_prompts = {
    "CDO": "本议题是 HUD Demo 的视觉和交互设计。关注：四角布局信息密度、预警视觉冲击力、A/B 光学方案的视觉差异表达、自动剧本的叙事节奏。已知陷阱：HUD 不是手机 App，骑手用余光扫视，信息必须一瞥可读。",
    "CTO": "本议题是 HUD Demo 的技术实现。关注：单 HTML 文件零依赖约束、状态机的完整性、键盘事件覆盖、自动剧本时序驱动、代码可维护性。已知陷阱：单次 LLM 生成的 HTML 超过 500 行时质量下降。",
    "CMO": "本议题是 HUD Demo 面向供应商和投资人的演示效果。关注：竞品 Shoei GT-Air 3 Smart 的 HUD 表现、演示场景是否覆盖核心卖点（ADAS 是最大差异化）、3 分钟内能否讲清楚产品价值。已知陷阱：技术人员容易堆功能而忽视叙事。",
}
```

---

## 十、信息流控制

### 10.1 每步输入输出上限

| Phase | 角色输入上限 | 角色输出上限 | 说明 |
|-------|------------|------------|------|
| 议题审查 | ~1500字 | ~400字 | Critic 审查 TaskSpec |
| Phase 1 | ~2000字（角色分片） | ~800字（结构化模板） | 独立思考 |
| Phase 2 | ~4000字（三份约束+分片） | ~1200字 | proposer 出方案 |
| Phase 3 | ~2500字（方案+自己的约束） | ~600字 | 定向审查 |
| Phase 4 | ~3000字（方案+审查结论+验收标准） | ~800字 | Critic 终审 |
| 执行摘要 | 全部 Phase 输出 | ~2000字 | Echo 压缩 |
| Generator | ~2000字执行摘要 | 不限（完整产物） | 生成 |

### 10.2 结构化模板强制

不靠"请简短回答"控制长度，靠结构化模板：

Phase 1 输出模板：
```
## 约束清单（每条一句话 + 置信度标注）
1. ...
2. ...

## 关键判断（最多3条，结论先行）
1. ...

## 我不确定的（最多2条）
1. ...
```

Phase 3 输出模板：
```
## 通过 ✅
1. 约束X — 满足

## 不通过 ❌
1. 约束Y — 不满足，原因：..., 建议：...

## 置信度质疑（如有）
1. ...
```

### 10.3 信息分层："压缩传递，原文可查"

讨论全程完整记录写入磁盘 `roundtable_logs/{task_topic}_{timestamp}/`：
```
roundtable_logs/
└── hud_demo_20260406/
    ├── phase1_cdo.md
    ├── phase1_cto.md
    ├── phase1_cmo.md
    ├── phase2_proposal.md
    ├── phase3_cto_review.md
    ├── phase3_cmo_review.md
    ├── phase4_critic.md
    ├── convergence.md
    ├── executive_summary.md
    └── verifier_rounds/
        ├── round1_issues.md
        ├── round1_fix.md
        └── ...
```

Phase 之间传递的是压缩后的结构化输出，但任何角色如果需要验证具体数据点，可以引用原始 KB 条目或之前 Phase 的完整记录。

---

## 十一、主入口

```python
# scripts/roundtable/__init__.py

async def run_task(task: TaskSpec, gw, kb, feishu):
    """一个任务的完整生命周期"""
    
    # 0. 知识结晶 — 准备上下文
    crystallizer = Crystallizer(gw, kb)
    context = await crystallizer.prepare_context(task)
    await feishu.notify(f"📚 知识准备完成")
    
    # 1. 议题审查
    rt = Roundtable(gw, feishu)
    task = await rt.pre_check_task_spec(task, context)
    
    # 2. 圆桌讨论
    result = await rt.discuss(task, context)
    await feishu.notify(f"🔵 圆桌收敛，共 {result.rounds} 轮")
    
    # 3. 生成
    gen = Generator(gw)
    output = await gen.generate(task, result)
    
    # 4. 审查闭环
    ver = Verifier(gw)
    iteration = 0
    while True:
        vr = await ver.verify(task, output)
        if vr.passed:
            await feishu.notify(f"✅ 审查通过")
            break
        if vr.stuck:
            await feishu.notify(f"⚠️ 能力瓶颈：{vr.stuck_issues}，尝试升级...")
            output = await gen.escalate(output, vr.stuck_issues, result)
            continue
        iteration += 1
        await feishu.notify(f"🔄 审查第{iteration}轮，{len(vr.issues)}个缺陷，修复中...")
        output = await gen.fix(output, vr.issues, result)
    
    # 5. 输出
    Path(task.output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(task.output_path).write_text(output, encoding='utf-8')
    
    # 6. 知识回写
    await crystallizer.crystallize_learnings(task, result)
    
    await feishu.notify(f"🎯 任务完成：{task.output_path}")
    return output
```

---

## 十二、飞书路由

在 `scripts/feishu_handlers/text_handler.py` 新增：

```python
# "圆桌:XXX" 格式触发
if text.startswith("圆桌:") or text.startswith("圆桌："):
    topic = text.split(":", 1)[1].strip() if ":" in text else text.split("：", 1)[1].strip()
    
    # 查找预定义的 TaskSpec
    spec = load_task_spec(topic)  # 从 .ai-state/task_specs/ 读取
    if spec:
        asyncio.create_task(run_task(spec, gw, kb, feishu))
        return f"🔵 圆桌启动：{topic}"
    else:
        return f"未找到预定义任务：{topic}。请先创建 TaskSpec。"
```

TaskSpec 存放位置：`.ai-state/task_specs/{topic}.json`

---

## 十三、实施注意事项

1. **所有产品业务逻辑在 TaskSpec 和配置文件里**，`scripts/roundtable/` 是通用引擎
2. **不修改现有文件**：不动 deep_research/、demo_generator.py、feishu_handlers/（只在 text_handler 里加路由）
3. **共享基础设施**：复用 model_gateway 的 call() 接口和 knowledge_base 的 search() 接口
4. **磁盘日志完整**：每个 Phase 的每个角色输出都写磁盘，支持事后追溯和知识结晶
5. **飞书通知每步进度**：但不暂停等人，人不在流程照跑
6. **测试**：实现完成后，用 HUD Demo TaskSpec 端到端验证。验证标准是输出质量超过本窗口手写的 hud_demo.html

---

## 十四、第一个 TaskSpec 示例（单独文件，不是系统的一部分）

保存到 `.ai-state/task_specs/hud_demo.json`，作为验证用例：

```json
{
  "topic": "HUD Demo 生成",
  "goal": "生成一个可双击打开的 HUD 演示 HTML 文件，用于给供应商和投资人展示智能骑行座舱的 HUD 体验",
  "acceptance_criteria": [
    "单 HTML 文件，零外部依赖（字体CDN除外），双击可在浏览器打开",
    "全屏黑色背景模拟护目镜视角",
    "四角布局：LT=速度+骑行状态，RT=设备状态，RB=导航，LB=通知",
    "中央视野完全留空",
    "7个页面态全部可触发：骑行主界面/导航/来电/音乐/组队/预警/录制",
    "页面态按优先级自动切换：预警>来电>导航>组队>音乐>录制>主界面",
    "预警时对应方向角落闪烁：前方=LT+RT，左后=LB，右后=RB",
    "3条自动剧本（日常通勤/紧急场景/组队骑行），底部时间轴可播放/暂停/拖拽",
    "手动沙盒模式：右侧面板按类别分组列出所有可触发事件",
    "A/B光学方案切换：OLED全彩（默认）vs 光波导单绿色，有明显视觉差异",
    "速度分级S0-S3自动适应信息密度",
    "键盘快捷键覆盖所有核心操作",
    "全彩OLED为默认配色方案，各功能色彩语义清晰区分",
    "开机自检动画"
  ],
  "proposer": "CDO",
  "reviewers": ["CTO", "CMO"],
  "critic": "Critic",
  "authority_map": {
    "design": "CDO",
    "feasibility": "CTO",
    "user_fit": "CMO",
    "final": "Leo"
  },
  "input_docs": [
    ".ai-state/product_anchor.md",
    ".ai-state/founder_mindset.md"
  ],
  "kb_search_queries": [
    "HUD display layout",
    "helmet HUD user interface",
    "motorcycle HUD competitor",
    "ADAS warning display",
    "heads up display design principles"
  ],
  "role_prompts": {
    "CDO": "本议题是 HUD Demo 的视觉和交互设计。关注：四角布局信息密度、预警视觉冲击力、全彩配色的功能色语义（速度白/导航蓝/预警红/组队青/音乐紫）、A/B光学方案的视觉差异表达、自动剧本的叙事节奏。已知陷阱：HUD不是手机App，骑手用余光扫视，信息必须一瞥可读。产品核心使命：消灭停车掏手机。",
    "CTO": "本议题是 HUD Demo 的技术实现。关注：单HTML文件零依赖约束、状态机完整性（7个页面态+优先级切换）、键盘事件全覆盖、自动剧本时序驱动机制、代码结构可维护性。已知陷阱：单次LLM生成超500行HTML时质量下降——考虑是否需要分段生成策略。但最终产物必须是单文件。",
    "CMO": "本议题是 HUD Demo 的演示说服力。关注：竞品 Shoei GT-Air 3 Smart（$1199，EyeLights OLED HUD）的体验对标——我们要比它好在哪里看得出来？ADAS预警是核心差异化（Shoei做不到）——Demo里ADAS场景是否足够震撼？3分钟内投资人/供应商能否get到产品价值？目标用户是玩乐骑+摩旅骑手，不是通勤。",
    "Critic": "审查标准：14条验收标准逐条验证。额外关注：Demo是否传达了产品的核心差异化（ADAS安全感知），还是沦为了一个花哨的信息展示板？审查各角色置信度标注是否诚实。"
  },
  "output_type": "html",
  "output_path": "demo_outputs/hud_demo_roundtable.html"
}
```

此文件是测试用例，不是系统的一部分。系统通过 `load_task_spec()` 读取任意 TaskSpec JSON。
