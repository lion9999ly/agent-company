# 从规则驱动到学习驱动

> 核心问题：系统跑了 100 次和跑第 1 次的行为完全一样。
> 目标：系统应该越用越聪明——从每次运行中学到什么有效、什么无效，自动调整行为。

---

## 一、现状诊断

系统有三层：
- **数据层**（KB）：在增长 ✅
- **规则层**（prompt/流程/配置）：完全不变 ❌
- **行为层**（模型选择/搜索策略/输出格式）：完全不变 ❌

数据在积累，但行为没有进化。就像一个人读了 3000 本书但做事方式从来不变。

---

## 二、应该学什么？怎么学？

### W1: 搜索策略学习

**现在：** 每次深度研究的搜索词由 LLM 临时生成，不知道哪些词有效、哪些白搜。

**学习机制：**
- 每次搜索后记录：`{query: "JBD MicroLED price", model: "o3", result_quality: "high", useful_info_extracted: 3}`
- 积累 100+ 条记录后，系统知道：
  - "搜价格用英文+型号+price 效果最好"
  - "搜中文社区内容 doubao 比 o3 好"
  - "加上年份（2026）能过滤掉旧信息"
- 下次生成搜索词时，自动注入历史最佳实践

**实现：**
```python
# .ai-state/search_learning.jsonl — 每次搜索后追加
{"query": "...", "model": "o3", "tokens": 1500, "useful_findings": 3, "quality": "high", "timestamp": "..."}

# 每 50 条搜索记录后，自动总结搜索策略
def evolve_search_strategy():
    """从搜索历史中提取最佳实践"""
    # 按 quality 分组统计：什么关键词组合 + 什么模型 = 最高质量
    # 生成 .ai-state/search_best_practices.yaml
    # 下次搜索词生成时自动注入
```

commit: `"feat: search strategy learning — remember what queries work and auto-optimize"`

---

### W2: Agent prompt 自进化

**现在：** CTO/CMO/CDO 的 prompt 是静态的。每次分析用同样的指引。

**学习机制：**
- 每次 Critic 发现 P0 问题时，记录"哪个 Agent 漏掉了什么"
- 积累后自动在对应 Agent 的 prompt 中追加"注意事项"

**示例：**
```
Critic P0: "CTO 分析 HUD 方案时忽略了功耗影响"
→ 系统学到：CTO prompt 自动追加 "⚠️ 分析任何硬件方案时，必须包含功耗估算和对电池续航的影响"

Critic P0: "CMO 的市场数据来源不可靠"
→ 系统学到：CMO prompt 自动追加 "⚠️ 引用市场数据时，必须标注数据来源和时间，优先使用官方报告"
```

**实现：**
```python
# .ai-state/agent_lessons.yaml
cto:
  learned_warnings:
    - "分析硬件方案时必须包含功耗估算（来源：P0 cal_1774946819_573）"
    - "BOM 成本必须区分样品价和量产价（来源：P0 cal_1774951678_342）"
cmo:
  learned_warnings:
    - "市场数据必须标注来源和时间（来源：P0 20260331）"

# Agent prompt 构建时自动注入
def get_agent_prompt_with_lessons(role: str) -> str:
    base = get_agent_prompt(role)
    lessons = load_agent_lessons(role)
    if lessons:
        base += "\n\n## 从历史错误中学到的注意事项\n"
        for lesson in lessons:
            base += f"- {lesson}\n"
    return base
```

commit: `"feat: agent prompt self-evolution — auto-inject lessons from Critic P0 findings"`

---

### W3: 模型效果学习

**现在：** 模型选择是硬编码的——CTO 永远用 gpt-5.4，CMO 永远用 doubao。不知道哪个模型对什么任务效果最好。

**学习机制：**
- 每次模型调用后记录效果评分（从 Critic 分数和用户评价推断）
- 积累后发现："gemini-3.1-pro 做竞品分析比 gpt-5.4 好"、"o3 做数值计算比 deepseek-r1 准"
- 模型路由从静态映射变成动态最优选择

**实现：**
```python
# .ai-state/model_effectiveness.jsonl
{"model": "gpt_5_4", "task_type": "competitor_analysis", "quality_score": 7, "timestamp": "..."}
{"model": "gemini_3_1_pro", "task_type": "competitor_analysis", "quality_score": 9, "timestamp": "..."}

def select_best_model_learned(task_type: str) -> str:
    """基于历史效果选择最佳模型"""
    history = load_model_effectiveness(task_type)
    if len(history) < 10:
        return _get_model_for_task(task_type)  # 数据不够，用默认
    # 按 quality_score 排序，选历史效果最好的
    best = max(history, key=lambda x: x["avg_score"])
    return best["model"]
```

commit: `"feat: model effectiveness learning — dynamic model routing based on historical performance"`

---

### W4: 输出格式学习

**现在：** 报告格式固定。不管 Leo 喜不喜欢，每次都是同样的结构。

**学习机制：**
- 从 Leo 的评价（A/B/C/D）和修改请求中提取偏好
- "Leo 总说报告太长" → 自动缩短
- "Leo 总先看结论" → 自动把结论放第一段
- "Leo 问'具体数据呢'" → 自动增加数据密度

**实现：**
```python
# .ai-state/output_preferences.yaml（自动从评价中学习）
report:
  preferred_length: 1200  # 从评价中推断（C/D 评价时报告平均 2000字，A 评价时平均 1200字）
  structure: "conclusion_first"  # Leo 多次要求"先说结论"
  data_density: "high"  # Leo 多次追问"数据呢"
  avoid:
    - "过长的背景介绍"
    - "重复前面说过的内容"
    - "模糊的建议（'可以考虑'）"
```

commit: `"feat: output format learning — auto-adjust report style from user feedback patterns"`

---

### W5: PRD 生成学习

**现在：** PRD 靠 anchor 硬编码 36 个模块和子功能。每次生成同样的结构。

**学习机制：**
- 从 PRD 的评审反馈中学习："来电模块只有 5 条太少了" → 下次自动给来电模块分配更多生成预算
- 从用户修改中学习："Leo 手动在导航模块加了 3 条功能" → 下次自动包含这些功能方向
- 从 Critic 反馈中学习："测试用例和功能数量不匹配" → 下次自动增加测试用例密度

**实现：**
```python
# .ai-state/prd_learning.yaml（从历次 PRD 评审中积累）
module_budgets:
  来电与通话: {min_items: 15, note: "Leo 反馈 R12 只有 5 条太少"}
  导航: {min_items: 30, note: "核心模块，需要深度"}
  
test_case_ratio: 1.2  # 测试用例数/功能数的目标比例（从历史反馈中学到）

auto_additions:
  导航:
    - "离线地图缓存策略"  # Leo 手动加过
    - "隧道中 GPS 信号丢失的降级方案"  # Leo 手动加过
```

commit: `"feat: PRD generation learning — adjust module budgets and auto-additions from review feedback"`

---

### W6: Critic 标准自进化（增强版）

**现在：** Critic 校准只进化 few-shot 示例。判断标准（什么算 P0、什么算 P1）是硬编码的。

**学习机制：**
- 从校准数据中不只进化示例，还进化标准本身
- 如果 Leo 连续 5 次把某个 P1 标为"应该是 P0"（偏松），系统自动降低该类问题的 P0 门槛
- 如果 Leo 连续 5 次把某个 P0 标为"偏紧"，系统自动提高门槛

**实现：**
```python
# .ai-state/critic_evolved_rules.yaml（从校准数据中自动生成）
p0_triggers:
  - pattern: "功耗.*未.*评估"
    learned_from: "cal_1774949408_542 (Leo 标注 accurate)"
    confidence: 0.9
  - pattern: "成本.*低估|高估"
    learned_from: "3 个样本一致标注"
    confidence: 0.8

p0_suppressions:
  - pattern: "重量.*偏差.*5mm"
    learned_from: "cal_1774950570_451 (Leo 标注偏紧，降为 P2)"
    confidence: 0.7
```

commit: `"feat: Critic standard self-evolution — auto-adjust P0/P1 thresholds from calibration data"`

---

## 三、元学习：学会怎么学

最高级的学习不是"学到一条规则"，而是"学会怎么更好地学"。

**W7: 学习效果自评**

每周系统对自己的学习进行评估：
- 搜索策略优化后，搜索质量提升了吗？（对比优化前后的 quality_score 均值）
- Agent prompt 追加教训后，P0 率下降了吗？
- 模型动态选择后，平均报告质量提升了吗？

如果某项学习没有带来改善，自动回滚。

**实现：**
```python
def meta_learning_assessment():
    """评估各项学习机制的实际效果"""
    # 对比学习前后的关键指标
    # 无效的学习自动回滚
    # 有效的学习加大权重
```

commit: `"feat: meta-learning assessment — evaluate whether learned behaviors actually improve outcomes"`

---

## 四、总结

| 学习维度 | 从什么数据学 | 学到什么 | 影响什么行为 |
|---------|------------|---------|------------|
| W1 搜索策略 | 搜索日志 quality | 什么搜索词+什么模型效果好 | 搜索词生成 |
| W2 Agent 教训 | Critic P0 记录 | 哪个 Agent 容易漏什么 | Agent prompt |
| W3 模型效果 | Critic 分数 + 用户评价 | 哪个模型做什么最好 | 模型路由 |
| W4 输出偏好 | 用户评价 A/B/C/D | 什么格式 Leo 满意 | 报告格式 |
| W5 PRD 偏好 | PRD 评审反馈 | 哪个模块该深该浅 | PRD 模块预算 |
| W6 Critic 标准 | 校准标注 | P0/P1 分界线在哪 | Critic 判断 |
| W7 元学习 | 学习效果对比 | 哪些学习有效 | 学习策略本身 |

这 7 项实现后，系统从"规则驱动的工具"变成"经验驱动的伙伴"。跑 100 次后的系统，搜索更精准、分析更到位、输出更对味、判断更准确——因为它从每次运行中都在学。
