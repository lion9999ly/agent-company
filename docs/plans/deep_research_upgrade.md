# 深度研究管道能力升级方案

> 部署路径：`docs/plans/deep_research_upgrade.md`
> 执行方式：Claude Code 按步骤顺序执行
> 涉及文件：tonight_deep_research.py / model_registry.yaml / agents.yaml / agent_prompts.yaml
> 预计总工作量：~170min
> 前置条件：当前无任务在跑，服务可重启

---

## 升级目标

将深度研究管道从"搜索+拼接+单次生成"升级为"精准搜索→结构化提取→专家知识注入→分片深度分析→决策支撑输出→多轮挑战式深化"。

核心改动 5 层：
1. 模型分层——贵的模型只用在思考环节
2. Prompt 知识密度注入——从"扮演角色"到"具备专家判断力"
3. 搜索管道三合一（精准搜索+结构化提取+分片处理）
4. 输出目标重定义——从"给推荐"到"给决策支撑"
5. 多轮迭代深化——Critic 从打分员变挑战者

---
---

## Layer 1：模型分层升级

### 改动文件
- `tonight_deep_research.py` 中所有模型调用处
- 如需要，同步更新 `src/config/model_registry.yaml` 和 `src/config/agents.yaml`

### 模型分配方案

#### 轻量任务（体力活）→ 用最便宜最快的

| 环节 | 当前模型 | 改为 | 理由 |
|------|---------|------|------|
| 搜索 query 生成 / discovery | GPT-5.4 | **gemini_2_5_flash** | 只需生成搜索词，Flash 够了 |
| 搜索后结构化提取（新增） | 不存在 | **gemini_2_5_flash** | 数据提取不需要深度推理 |
| 角色分配 role_assign | GPT-5.4 | **gemini_2_5_flash** | 当前返回 12 tokens，GPT-5.4 太浪费 |
| 知识提取 extract | GPT-5.4 | **gemini_2_5_flash** | 结构化 JSON 提取，中等即可 |

#### 核心思考（大脑）→ 用最强推理模型

| 环节 | 当前模型 | 改为 | 理由 |
|------|---------|------|------|
| CTO 深度分析 | GPT-5.4 | **o3** | 最强推理，适合技术参数分析和专家级判断 |
| CMO 市场研究 | GPT-5.4 | **o3_deep_research** | 专为深度研究设计的模型 |
| CDO 设计分析 | GPT-5.4 | **gemini_3_1_pro** | 多模态能力强，适合设计和布局分析 |
| Synthesis 整合 | GPT-5.4 | **o3** | 跨角色信息融合需要最强综合推理 |
| Critic 评审（首选） | gemini_3_1_pro | **gemini_3_1_pro**（不变） | 保持独立于生成模型的视角 |
| Critic 评审（备选） | claude_opus_4_6 | **gpt_5_4** | 双模型交叉评审，用不同家族的模型 |

#### 修复/补充调用 → 中等模型

| 环节 | 当前模型 | 改为 | 理由 |
|------|---------|------|------|
| CTO fix（Critic 返修后） | GPT-5.4 | **gpt_5_4**（不变） | 修复不需要最强模型，保持成本可控 |
| CDO fix | GPT-5.4 | **gemini_2_5_pro** | 稳定可靠 |
| Re-synthesis | GPT-5.4 | **o3** | 与首次 synthesis 保持同一模型，保证一致性 |

### 实现方式

在 `tonight_deep_research.py` 中，找到每个模型调用处（grep `gateway.call` 或 `model_gateway`），把 model_name 参数改为上表中的目标模型。

示例：
```python
# 当前（推测）
result = gateway.call("gpt-5.4", prompt, system_prompt, task_type="deep_research_cto")

# 改为
result = gateway.call("o3", prompt, system_prompt, task_type="deep_research_cto")
```

如果 `tonight_deep_research.py` 不是直接传 model_name 而是走 agent 绑定，则需要修改 `agents.yaml` 中的绑定关系，或在 deep_research 流程中 override agent 的默认模型。

---
---

## Layer 2：Prompt 知识密度注入

### 改动文件
- `tonight_deep_research.py`（CTO/CDO prompt 构建逻辑）
- 新建 `src/config/expert_frameworks.yaml`（专家框架模板）

### 2.1 新建专家框架模板

创建文件 `src/config/expert_frameworks.yaml`：

```yaml
# 专家判断框架 —— 根据任务类型注入领域专家知识和常见陷阱
# 选择机制：任务 spec 文件名或目标中的关键词 → 匹配 framework → 注入 CTO/CDO prompt

optical_benchmark:
  match_keywords: ["光学", "optics", "FOV", "亮度", "HUD参数", "对标"]
  role: "你是有 10 年近眼显示光学量产经验的技术专家，曾参与过 3 款 AR 眼镜和 2 款车载 HUD 的量产项目"
  known_pitfalls:
    - "眼盒标称值 vs 实际可用值：供应商标称 10mm 眼盒，在头盔振动环境下有效可用范围通常只有标称值的 60-70%。EyeRide 用户大量投诉的'有时看得见有时看不见'，本质就是眼盒不够"
    - "面板亮度 vs 到眼亮度：自由曲面反射损耗 70-85%。面板标称 3000 nits，到眼只有 450-900 nits。供应商报的永远是面板值，你必须追问到眼值"
    - "FOV 口径陷阱：行业惯性用对角线 FOV 做宣传，但骑行场景关心的是水平 FOV。对角 20° 约等于水平 16°×垂直 12°，别被大数字骗了"
    - "良率对 BOM 的乘数效应：光学模组 30% 良率意味着单件有效成本是标价的 3.3 倍。供应商报价永远是理论良率下的单价"
    - "虚像距离与调焦疲劳：VID < 3m 会导致骑手在路面和 HUD 之间频繁调焦，长时间骑行引发视觉疲劳。VID > 15m 则光机体积和校准难度急剧上升"
    - "Free Form 在振动环境下的结构风险：EyeRide 用户投诉最多的不是显示质量，而是光纤连接线断裂。这不是质量问题，是自由曲面方案在摩托车振动环境下的结构性缺陷"
    - "单色 vs 全彩的真实 tradeoff：全彩好看但功耗高 3-5 倍、光学效率低 40-60%。对于'箭头+数字+图标'的信息类型，单绿色高对比方案的可读性反而更好"
  evaluation_criteria:
    - "每个参数必须标注来源类型：供应商 datasheet / 竞品官方公布 / 第三方评测实测 / 行业经验推算 / 未公开"
    - "区分标称值和实测值，如果只有标称值，必须注明"
    - "搜不到的参数填 null 并标注'未公开'，绝不能编数字"
    - "与产品约束交叉验证：这个参数组合下的重量、功耗、成本是否能闭环到 ≤1.65kg / ≥8h / 5000-8000 RMB"
    - "给出参数时必须附 confidence：0.9=供应商 spec sheet / 0.8=第三方实测 / 0.7=行业报告 / 0.6=推算 / 0.3=未验证"

layout_analysis:
  match_keywords: ["布局", "layout", "分区", "四角", "单角", "显示方案"]
  role: "你是有摩托车人因工程和 HMI 设计背景的技术专家，熟悉 ISO 15008 和汽车/航空 HUD 的信息架构演进"
  known_pitfalls:
    - "多区域布局的认知负荷不是线性增长：2 个区域的认知成本约为 1 个区域的 1.5 倍，4 个区域则是 3-4 倍。骑行高速场景下这个系数还要乘以 1.3-1.5"
    - "骑行环境下的有效注视时间比静态场景短 40-60%：振动、风压、路况变化导致余光扫视时间极短。汽车 HUD 的研究数据不能直接套用"
    - "预警方向映射不是普适的：'左前方威胁→左上角闪烁'的直觉性取决于个人习惯和训练程度，不能假设所有用户都能直觉理解"
    - "信息位置一致性比最优位置更重要：用户会习惯'速度在右下角'，一旦建立习惯，比把速度放在理论最优位置更有效"
    - "汽车 AR-HUD 的叠加策略不适合摩托车：汽车有固定的挡风玻璃和稳定的头部位置，摩托车的头部自由度大得多"
  evaluation_criteria:
    - "评分必须有量化依据，不能只凭主观判断"
    - "每种方案的分析必须覆盖 S0-S3 全部速度档"
    - "必须考虑光学实现可行性——单光学模组能覆盖四角吗？"
    - "给出方案推荐时必须附 2-3 个需要用户决策的关键分歧点"

hardware_layout:
  match_keywords: ["硬件布局", "组件", "按键", "灯效", "重心", "散热"]
  role: "你是有头盔结构设计和 ECE 22.06 认证经验的硬件专家，曾参与过 2 款量产头盔的结构设计"
  known_pitfalls:
    - "EPS 缓冲层完整性是 ECE 22.06 认证底线：任何嵌入电子件的方案都不能削弱冲击吸收区域的完整性。Skully 的失败部分原因就是电子件布局侵占了 EPS 空间"
    - "前重心增加 30g 在高速骑行中的影响是非线性的：80km/h 以上，前重心偏移导致的颈部疲劳和风压下的头部摆动会被放大 2-3 倍"
    - "散热路径必须避开头皮热敏区：前额和耳侧温度敏感度最高，超过 40°C 就会有明显不适感。SoC 和电池的热量必须导向壳体外表面，而不是内衬"
    - "按键间距和凸起高度直接决定戴手套盲操成功率：间距 < 15mm 时误触率急剧上升，凸起 < 2mm 时手套基本无法区分"
    - "USB-C 接口位置不能在下巴区域：骑行中下巴区域是雨水汇集点，即使有防水盖也容易进水。后脑下方或左侧面是更安全的位置"
    - "天线位置受壳体材料限制：如果壳体用碳纤维，RF 信号会被严重屏蔽，天线必须从非碳纤维区域伸出或使用专用天线窗"
  evaluation_criteria:
    - "每个组件的位置建议必须附重量和体积数据"
    - "必须给出前后左右的重心分布估算"
    - "必须说明散热路径：热源在哪→热量怎么传导→从哪里散出"
    - "必须考虑 ECE 22.06 对内部组件位置的具体约束"
    - "竞品拆解数据优先于理论分析"

general_research:
  match_keywords: []
  role: "你是一名严谨的技术分析师"
  known_pitfalls:
    - "避免确认偏误：不要因为找到了支持某个结论的数据就停止搜索反面证据"
    - "区分相关性和因果性"
    - "标注每个关键数据的来源和 confidence"
  evaluation_criteria:
    - "结论必须有数据支撑"
    - "不确定的地方标注不确定，不要编造"
    - "给出 2-3 个需要决策者判断的关键问题"
```

### 2.2 deep_research 启动时检索知识库

在 `tonight_deep_research.py` 中，每个研究任务开始时（搜索之前），增加知识库检索：

```python
from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt

def _get_kb_context(task_goal, task_title):
    """从知识库检索与任务相关的高质量知识条目"""
    queries = []
    # 从任务目标提取关键词
    import re
    # 提取中文关键词
    keywords = re.findall(r'[\u4e00-\u9fff]{2,6}', task_goal)[:10]
    # 提取英文技术词
    tech_terms = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*|[A-Z]{2,}', task_goal)[:5]
    
    queries = keywords[:5] + tech_terms[:3] + [task_title]
    
    all_entries = []
    seen_ids = set()
    for q in queries:
        entries = search_knowledge(q, limit=5)
        for e in entries:
            entry_id = e.get('id', str(e))
            if entry_id not in seen_ids:
                seen_ids.add(entry_id)
                all_entries.append(e)
    
    # 按 confidence 排序，取 top 15
    all_entries.sort(key=lambda x: x.get('confidence', 0), reverse=True)
    top_entries = all_entries[:15]
    
    return format_knowledge_for_prompt(top_entries)[:3000]
```

### 2.3 匹配专家框架

```python
import yaml

def _match_expert_framework(task_goal, task_title):
    """根据任务关键词匹配专家框架"""
    with open('src/config/expert_frameworks.yaml', 'r', encoding='utf-8') as f:
        frameworks = yaml.safe_load(f)
    
    combined_text = task_goal + " " + task_title
    
    best_match = None
    best_score = 0
    
    for name, fw in frameworks.items():
        if name == 'general_research':
            continue
        score = sum(1 for kw in fw.get('match_keywords', []) if kw in combined_text)
        if score > best_score:
            best_score = score
            best_match = name
    
    if best_match and best_score > 0:
        return frameworks[best_match]
    return frameworks.get('general_research', {})
```

### 2.4 拼装完整的 CTO/CDO prompt

```python
def _build_expert_prompt(role_name, task_goal, task_title, structured_data, kb_context, expert_fw):
    """构建注入了专家知识的角色 prompt"""
    
    pitfalls_text = "\n".join(f"- {p}" for p in expert_fw.get('known_pitfalls', []))
    criteria_text = "\n".join(f"- {c}" for c in expert_fw.get('evaluation_criteria', []))
    
    system_prompt = f"""{expert_fw.get('role', '你是一名技术分析师')}

## 你必须知道的行业陷阱和经验
{pitfalls_text}

## 评估标准
{criteria_text}
"""
    
    user_prompt = f"""## 任务目标
{task_goal}

## 项目已有知识（知识库，已验证）
{kb_context}

## 本次搜索收集的数据
{structured_data}

请基于以上信息，作为 {role_name} 给出你的专业分析。
注意：你的分析将被用于产品决策，每个关键论点都必须有数据支撑和 confidence 标注。"""
    
    return system_prompt, user_prompt
```

---
---

## Layer 3：搜索管道三合一

### 改动文件
- `tonight_deep_research.py`（搜索流程和 CTO 调用方式）

### 3.C 精准搜索 query 生成

在 discovery 阶段之后、正式搜索之前，增加一步：根据任务 spec 中的表格/列表结构，生成定向搜索词。

```python
async def _generate_targeted_queries(task_spec_text, base_queries):
    """从任务 spec 中提取竞品名和参数字段，生成精准搜索词"""
    
    prompt = f"""分析以下研究任务规格书，提取出：
1. 所有需要对标的具体产品/竞品名称
2. 需要收集的具体参数字段

然后为每个产品生成 2-3 个精准的搜索查询，每个查询聚焦于该产品的具体参数。

任务规格书（节选）：
{task_spec_text[:3000]}

输出格式（JSON）：
{{
  "products": ["Shoei GT-Air 3 Smart", "EyeRide V3", ...],
  "params": ["FOV", "resolution", "brightness", ...],
  "targeted_queries": [
    "Shoei GT-Air 3 Smart EyeLights FOV resolution OLED specs",
    "EyeRide V3 nano OLED brightness nits eye box specs review",
    ...
  ]
}}

只输出 JSON，不要其他内容。"""
    
    result = await gateway.call("gemini_2_5_flash", prompt, task_type="query_generation")
    # 解析 JSON，合并到 base_queries
    # targeted_queries 优先执行，base_queries 作为补充
    return targeted_queries + base_queries
```

### 3.A 搜索后结构化提取（核心新增步骤）

在每轮搜索完成后，立即用 Flash 提取结构化数据点：

```python
async def _extract_structured_data(raw_text, task_type, topic):
    """从搜索结果中提取结构化数据点"""
    
    # 根据任务类型选择提取 schema
    if "光学" in task_type or "optics" in task_type or "对标" in task_type:
        schema = OPTICAL_BENCHMARK_SCHEMA
    elif "布局" in task_type or "layout" in task_type:
        schema = LAYOUT_ANALYSIS_SCHEMA
    elif "硬件" in task_type or "hardware" in task_type:
        schema = HARDWARE_LAYOUT_SCHEMA
    else:
        schema = GENERAL_SCHEMA
    
    prompt = f"""从以下搜索结果中提取结构化数据。

提取规则：
1. 只提取搜索结果中明确包含的数据，不要推测
2. 搜不到的字段填 null
3. 每个有值的字段必须附 source（URL 或文章标题）
4. confidence: high=官方spec/实测数据, medium=官方宣称/评测引用, low=推算/间接推断

Schema:
{json.dumps(schema, ensure_ascii=False, indent=2)}

搜索主题: {topic}
搜索结果:
{raw_text[:4000]}

只输出 JSON，不要其他内容。"""
    
    result = await gateway.call("gemini_2_5_flash", prompt, task_type="data_extraction")
    return parse_json_safe(result)


# ========= 提取 Schema 定义 =========

OPTICAL_BENCHMARK_SCHEMA = {
    "product": "string - 产品名称",
    "manufacturer": "string - 制造商",
    "product_type": "string - helmet_integrated / clip_on / smartglasses",
    "display_tech": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "fov_diagonal_deg": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "fov_horizontal_deg": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "resolution": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "brightness_panel_nits": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "brightness_eye_nits": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "eye_box_mm": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "virtual_image_distance_m": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "battery_hours": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "weight_g": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "price_usd": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "display_position": {"value": "string|null - right_eye/left_eye/binocular/visor", "source": "string", "confidence": "high|medium|low"},
    "status": "string - on_sale / announced / prototype / discontinued",
    "notable_issues": "string|null - 已知问题或用户投诉",
    "data_gaps": ["string - 哪些参数搜不到"]
}

LAYOUT_ANALYSIS_SCHEMA = {
    "product": "string",
    "hud_position": {"value": "string|null - 描述显示区域在视野中的位置", "source": "string", "confidence": "high|medium|low"},
    "info_layout": {"value": "string|null - 全屏/分区/单角/多角/底部条", "source": "string", "confidence": "high|medium|low"},
    "simultaneous_elements": {"value": "number|null - 同时显示最多几个信息元素", "source": "string", "confidence": "high|medium|low"},
    "priority_mechanism": {"value": "string|null - 信息优先级切换方式", "source": "string", "confidence": "high|medium|low"},
    "direction_indication": {"value": "string|null - 是否支持方向指示（预警方向）", "source": "string", "confidence": "high|medium|low"}
}

HARDWARE_LAYOUT_SCHEMA = {
    "product": "string",
    "button_count": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "button_position": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "battery_position": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "battery_capacity_mah": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "camera_position": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "camera_specs": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "total_weight_g": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "charging_port": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "led_light_position": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "certification": {"value": "string|null", "source": "string", "confidence": "high|medium|low"}
}

GENERAL_SCHEMA = {
    "topic": "string",
    "key_findings": [{"finding": "string", "source": "string", "confidence": "high|medium|low"}],
    "data_gaps": ["string"]
}
```

### 3.B CTO 分片处理

改 CTO 调用方式，从"一次吃全部"变为"按数据分组分批处理"：

```python
async def _run_expert_analysis_in_slices(role, structured_data_list, system_prompt, user_prompt_template, model_name):
    """将结构化数据分组，每组独立让专家模型处理"""
    
    # 按产品类型分组
    groups = {}
    for item in structured_data_list:
        product_type = item.get('product_type', item.get('topic', 'general'))
        if product_type not in groups:
            groups[product_type] = []
        groups[product_type].append(item)
    
    # 如果分组太少（<2），按数量均分
    if len(groups) <= 1:
        items = list(structured_data_list)
        mid = len(items) // 2
        groups = {"group_1": items[:mid], "group_2": items[mid:]}
    
    partial_outputs = []
    for group_name, group_items in groups.items():
        group_data = json.dumps(group_items, ensure_ascii=False, indent=2)
        
        user_prompt = user_prompt_template + f"""

## 本轮分析的数据（{group_name}，共 {len(group_items)} 条）
{group_data}

请只针对这批数据给出分析。其他批次由同一流程的其他轮次处理，最后会统一整合。"""
        
        result = await gateway.call(model_name, user_prompt, system_prompt, task_type=f"deep_research_{role}")
        partial_outputs.append({
            "group": group_name,
            "output": result,
            "items_count": len(group_items)
        })
    
    return partial_outputs
```

### 整体搜索流程改造

将 `tonight_deep_research.py` 中的核心研究流程改为：

```python
async def run_single_research(task):
    """单个研究任务的完整流程"""
    
    task_goal = task['goal']
    task_title = task['title']
    constraint_context = task.get('constraint_context', '')
    
    # ===== 准备阶段 =====
    
    # 1. 匹配专家框架
    expert_fw = _match_expert_framework(task_goal, task_title)
    
    # 2. 检索知识库
    kb_context = _get_kb_context(task_goal, task_title)
    
    # 3. 生成精准搜索词（Layer 3.C）
    base_queries = task.get('queries', [])
    targeted_queries = await _generate_targeted_queries(task_goal, base_queries)
    
    # ===== 搜索阶段 =====
    
    # 4. 执行搜索（保持原有逻辑，用 targeted_queries 替换原 queries）
    raw_results = await _run_searches(targeted_queries, notify_func)
    
    # 5. 结构化提取（Layer 3.A —— 核心新增）
    structured_data_list = []
    for topic, raw_text in raw_results:
        extracted = await _extract_structured_data(raw_text, task_title, topic)
        if extracted:
            structured_data_list.append(extracted)
    
    # 6. 汇总结构化数据为紧凑文本
    structured_summary = json.dumps(structured_data_list, ensure_ascii=False, indent=2)
    
    # ===== 分析阶段 =====
    
    # 7. 构建专家 prompt（Layer 2）
    system_prompt, user_prompt = _build_expert_prompt(
        "CTO", task_goal, task_title,
        structured_summary, kb_context, expert_fw
    )
    # 约束文件也注入
    if constraint_context:
        user_prompt += f"\n\n## 约束文件\n{constraint_context[:2000]}"
    
    # 8. 角色分配（用 Flash）
    roles = await _assign_roles(task_goal, model="gemini_2_5_flash")
    
    # 9. 分片专家分析（Layer 3.B）
    expert_outputs = {}
    for role in roles:
        model = _get_model_for_role(role)  # CTO→o3, CMO→o3_deep_research, CDO→gemini_3_1_pro
        sliced_outputs = await _run_expert_analysis_in_slices(
            role, structured_data_list, system_prompt, user_prompt, model
        )
        expert_outputs[role] = sliced_outputs
    
    # ===== 整合阶段 =====
    
    # 10. Synthesis（Layer 4 —— 输出目标改为决策支撑）
    synthesis = await _run_synthesis(expert_outputs, task_goal, constraint_context, model="o3")
    
    # 11. Critic 挑战（Layer 5）
    challenges = await _run_critic_challenge(synthesis, kb_context, expert_fw, model="gemini_3_1_pro")
    
    # 12. 专家回应挑战（Layer 5）
    responses = await _respond_to_challenges(challenges, structured_data_list, expert_fw, roles, targeted_queries)
    
    # 13. 最终整合
    final_report = await _final_synthesis(synthesis, challenges, responses, task_goal, model="o3")
    
    return final_report
```

---
---

## Layer 4：输出目标重定义

### 改动文件
- `tonight_deep_research.py` 中 synthesis 的 prompt

### Synthesis prompt 改为决策支撑模式

```python
SYNTHESIS_SYSTEM_PROMPT = """你是一名高级技术整合分析师。你的输出目标不是"给出推荐"，而是"提供决策支撑"。

输出结构（严格遵守）：

## 一、数据对比表
- 必须包含每个数据点的来源和 confidence
- 未公开的数据标注 null，不要填推测值
- 如果有推算值，单独列一列标注推算方法

## 二、候选方案（2-3 个）
- 每个方案附完整的 pros/cons
- 每个 pros/cons 必须有量化依据
- 不要只说"成本更低"，要说"BOM 低 40-60%，约 $80-180 vs $180-400"

## 三、关键分歧点（不超过 5 个）
- 方案之间的核心分歧，每个分歧点用一句话概括
- 每个分歧点附：支持 A 方案的证据 vs 支持 B 方案的证据

## 四、需要决策者判断的问题
- 列出 3-5 个你无法替决策者回答的问题
- 每个问题附上你能提供的背景信息
- 格式："[决策点] 问题描述。背景：xxx"

## 五、数据缺口
- 本次研究中哪些关键数据没有找到
- 建议通过什么渠道补充（供应商询价 / 竞品拆机 / 专利检索 / 行业报告）

你不要替用户做最终选择。用户的价值是定义 Why，你的价值是把 How 的选项和代价摆清楚。"""
```

---
---

## Layer 5：多轮迭代深化

### 改动文件
- `tonight_deep_research.py`（Critic 调用逻辑和后续处理）
- `src/config/agent_prompts.yaml`（Critic prompt）

### 5.1 Critic 从"打分员"改为"挑战者"

```python
CRITIC_CHALLENGE_PROMPT = """你的职责不是打分，而是提出最尖锐、最有建设性的挑战问题。

规则：
1. 找出分析中最薄弱的 3 个论点，每个提出一个具体的反驳或追问
2. 反驳必须基于知识库数据、搜索到的事实、或明显的逻辑漏洞，不能泛泛说"建议加强"
3. 特别关注：
   - 数据来源的可靠性（confidence 标注是否合理？有没有把推测当事实？）
   - 缺失的关键视角（有没有忽略某个重要的竞品/约束/风险？）
   - 结论与数据的一致性（数据说 A，结论却选了 B？）
4. 如果分析质量已经足够好，指出 1-2 个可以进一步深化的方向

输出格式：
[挑战1] "你说 X，但 Y 数据/事实显示 Z。请解释这个矛盾或修正结论。"
[挑战2] "你没有考虑 A 因素，而 A 可能导致 B 后果。请补充分析。"
[挑战3] "这个结论的核心依据 confidence 只有 0.5-0.6，不足以作为 Demo 默认参数。你有什么补强方案？"

不要输出 PASS/REJECT 评分。只输出挑战问题。"""
```

### 5.2 挑战回应流程

```python
async def _respond_to_challenges(challenges, structured_data, expert_fw, roles, search_queries):
    """专家针对 Critic 的挑战问题做定向回应"""
    
    # 解析挑战问题
    challenge_list = _parse_challenges(challenges)
    
    responses = []
    for i, challenge in enumerate(challenge_list[:3]):
        
        # 判断是否需要额外搜索
        needs_search = ("数据" in challenge or "证据" in challenge 
                       or "来源" in challenge or "补充" in challenge)
        
        extra_data = ""
        if needs_search:
            # 从挑战问题中提取搜索关键词，做定向补充搜索
            extra_query = await gateway.call("gemini_2_5_flash", 
                f"从以下挑战问题中提取 1-2 个搜索关键词：\n{challenge}\n只输出关键词，空格分隔",
                task_type="query_generation")
            
            if extra_query.strip():
                search_result = await _search_one(extra_query.strip())
                if search_result:
                    extra_data = f"\n\n## 针对此挑战的补充搜索结果\n{search_result[:2000]}"
        
        # 让原角色回应挑战
        response_prompt = f"""Critic 对你的分析提出了以下挑战：

{challenge}

{extra_data}

请直接回应这个挑战。如果 Critic 说得对，承认并修正你的结论。如果 Critic 的挑战不成立，用数据反驳。"""
        
        primary_role = roles[0] if roles else "CTO"
        model = _get_model_for_role(primary_role)
        
        response = await gateway.call(model, response_prompt, task_type=f"challenge_response_{i}")
        responses.append({
            "challenge": challenge,
            "response": response,
            "extra_search": bool(extra_data)
        })
    
    return responses
```

### 5.3 最终整合（带挑战和回应）

```python
async def _final_synthesis(initial_synthesis, challenges, responses, task_goal, model):
    """将初始整合、Critic 挑战和专家回应合并为最终报告"""
    
    challenge_dialogue = ""
    for r in responses:
        challenge_dialogue += f"\n[挑战] {r['challenge']}\n[回应] {r['response']}\n"
    
    prompt = f"""以下是一份技术研究的完整过程：

## 初始分析报告
{initial_synthesis}

## Critic 挑战与专家回应
{challenge_dialogue}

请基于初始报告和挑战对话，输出最终版报告。
要求：
1. 挑战中被证实的问题，必须在最终报告中修正
2. 挑战中补充的新数据，必须整合进来
3. 仍然遵守决策支撑输出格式（数据表+方案+分歧点+决策问题+数据缺口）
4. 在报告末尾添加"Critic 挑战记录"小节，记录每个挑战和处理结果

任务目标：{task_goal}"""
    
    return await gateway.call(model, prompt, task_type="final_synthesis")
```

---
---

## 模型路由辅助函数

```python
def _get_model_for_role(role):
    """深度研究流程中，各角色使用的模型"""
    role_model_map = {
        "CTO": "o3",
        "CMO": "o3_deep_research",
        "CDO": "gemini_3_1_pro",
    }
    return role_model_map.get(role.upper(), "gpt_5_4")

def _get_model_for_task(task_type):
    """各任务环节使用的模型"""
    task_model_map = {
        "discovery": "gemini_2_5_flash",
        "query_generation": "gemini_2_5_flash",
        "data_extraction": "gemini_2_5_flash",
        "role_assign": "gemini_2_5_flash",
        "synthesis": "o3",
        "re_synthesis": "o3",
        "final_synthesis": "o3",
        "critic_challenge": "gemini_3_1_pro",
        "knowledge_extract": "gemini_2_5_flash",
        "fix": "gpt_5_4",
    }
    return task_model_map.get(task_type, "gpt_5_4")
```

---
---

## 执行步骤（给 CC 的指令）

按以下顺序执行，每步完成后验证再进入下一步：

```
步骤 1（15min）：创建 src/config/expert_frameworks.yaml
   - 直接用本文档中 Layer 2.1 的内容
   - 验证：python -c "import yaml; yaml.safe_load(open('src/config/expert_frameworks.yaml'))"

步骤 2（15min）：修改模型调用配置
   - 在 tonight_deep_research.py 中添加 _get_model_for_role() 和 _get_model_for_task()
   - 替换所有硬编码的模型名调用
   - 验证：grep -n "gpt-5.4\|gpt_5_4" scripts/tonight_deep_research.py
     应该只在 fix 环节还保留 gpt_5_4

步骤 3（15min）：添加知识库检索注入
   - 添加 _get_kb_context() 函数
   - 添加 _match_expert_framework() 函数
   - 在研究任务开始时调用
   - 验证：手动跑一次 _get_kb_context("HUD光学参数")，确认返回知识条目

步骤 4（15min）：修改 Synthesis prompt 为决策支撑模式
   - 替换 synthesis 的 system_prompt 为本文档中 Layer 4 的内容
   - 验证：grep "决策支撑\|数据缺口\|分歧点" scripts/tonight_deep_research.py

步骤 5（25min）：添加搜索后结构化提取
   - 添加 _extract_structured_data() 函数和三个 Schema 定义
   - 在搜索循环中，每轮搜索完成后调用提取
   - 验证：手动测试一段搜索原文的提取结果

步骤 6（15min）：添加精准搜索 query 生成
   - 添加 _generate_targeted_queries() 函数
   - 在搜索开始前调用，与 discovery 生成的 queries 合并
   - 验证：给一段任务 spec 文本，检查生成的 queries 是否包含具体竞品名×参数名

步骤 7（20min）：CTO 分片处理
   - 添加 _run_expert_analysis_in_slices() 函数
   - 替换原来的单次 CTO 调用
   - 验证：确认分片逻辑正确（按产品类型或数量均分）

步骤 8（30min）：Critic 挑战模式 + 多轮迭代
   - 替换 Critic prompt 为挑战者模式
   - 添加 _respond_to_challenges() 和 _final_synthesis() 函数
   - 修改流程：synthesis → critic 挑战 → 专家回应 → 最终整合
   - 验证：检查流程是否正确串联

步骤 9（10min）：提交 + 重启
   - git add 所有修改文件
   - git commit --no-verify -m "feat: 深度研究管道5层升级 — 模型分层+专家知识注入+结构化提取+决策支撑输出+挑战式Critic"
   - 重启飞书 V2 服务
   - 验证：发一条简单研究任务测试完整流程
```

---

## 验证方法

全部步骤完成后，发以下飞书消息测试：

```
参考文件：
A. docs/tasks/hud_research_tasks.md
B. docs/specs/hud_display_principles.md
只执行研究A
```

对比改进前后的输出，检查：
1. 是否出现了竞品参数对比表（每个产品一行，每个参数一列）
2. 每个数据点是否附带了 source 和 confidence
3. 是否输出了"决策支撑"格式（方案+分歧点+决策问题+数据缺口）
4. 是否有 Critic 挑战记录
5. 日志中是否显示使用了不同模型（o3、gemini_3_1_pro、gemini_2_5_flash）
