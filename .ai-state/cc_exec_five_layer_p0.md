# CC 执行文档: 五层诊断 P0 改进

> 日期: 2026-04-01
> 来源: `.ai-state/five_layer_diagnosis.md`
> 涉及: 三项 P0 改进，按顺序执行
> 提交: 每项完成后单独 commit + push

---

## P0-1: 决策树驱动任务规划

### 创建决策树文件

创建 `.ai-state/product_decision_tree.yaml`：

```yaml
# 产品决策树 — V1 核心决策点
# 深度学习的任务发现引擎优先填充 blocking_knowledge 中的缺口

decisions:
  - id: "v1_display"
    question: "V1 HUD 用 OLED+FreeForm 还是 MicroLED+衍射光波导？"
    status: "open"
    priority: 1
    blocking_knowledge:
      - "两种方案户外直射阳光下亮度实测对比（到眼 nits）"
      - "两种方案的完整 BOM 成本对比（含光学模组+驱动+结构件）"
      - "OLED 微显示面板供应商交期和 MOQ（Sony ECX 系列 vs 京东方）"
      - "MicroLED 微显示面板供应商交期和 MOQ（JBD）"
      - "树脂衍射光波导良率和供应商产能（珑璟/灵犀/谷东）"
      - "两种方案在头盔内的散热表现"
    decided_value: null
    decided_at: null

  - id: "v1_soc"
    question: "主 SoC 用 Qualcomm AR1 Gen1？"
    status: "decided"
    priority: 1
    blocking_knowledge: []
    decided_value: "Qualcomm AR1 Gen 1"
    decided_at: "2026-03-26"

  - id: "v1_intercom"
    question: "Mesh Intercom 自研还是授权 Cardo DMC？"
    status: "open"
    priority: 1
    blocking_knowledge:
      - "Cardo DMC 授权费用和技术限制"
      - "自研 BLE Mesh 的开发周期和成本估算"
      - "Reso 国产 Mesh 方案的性能和成本"

  - id: "v1_audio"
    question: "扬声器用骨传导还是传统动圈？"
    status: "open"
    priority: 2
    blocking_knowledge:
      - "骨传导 vs 动圈在全脸头盔内的听感对比"
      - "骑行风噪环境下两种方案的 SNR 对比"
      - "ANC 方案选型（BES vs QCC）"

  - id: "v1_safety_cert"
    question: "V1 认证走 DOT+ECE 还是额外加 SNELL？"
    status: "open"
    priority: 2
    blocking_knowledge:
      - "DOT/ECE 认证周期和费用"
      - "SNELL 认证的增量成本和市场价值"
      - "HUD 模组对认证的影响（额外测试项？）"

  - id: "v1_camera"
    question: "V1 是否集成摄像头？前置/后置/双摄？"
    status: "open"
    priority: 2
    blocking_knowledge:
      - "头盔摄像头的防水防雾方案"
      - "摄像头对电池续航的影响"
      - "骑行场景录像的用户需求优先级"

  - id: "v1_jdm_partner"
    question: "JDM 合作伙伴选歌尔、立讯还是其他？"
    status: "open"
    priority: 1
    blocking_knowledge:
      - "歌尔头盔/AR 产品线的实际产能和报价"
      - "立讯精密的 AR/XR 代工经验和报价"
      - "其他潜在 JDM 供应商评估"
```

### 注入到任务发现引擎

在 `tonight_deep_research.py` 的 `_discover_new_tasks()` 函数中，读取决策树并优先生成填充 blocking_knowledge 的任务。

找到 `_discover_new_tasks()` 中构建 discover_prompt 的位置，在 `## 产品方向` 之后插入：

```python
    # 读取决策树
    decision_tree_path = Path(__file__).parent.parent / ".ai-state" / "product_decision_tree.yaml"
    decision_tree_text = ""
    if decision_tree_path.exists():
        try:
            with open(decision_tree_path, 'r', encoding='utf-8') as f:
                dt = yaml.safe_load(f)
            open_decisions = [d for d in dt.get("decisions", []) if d.get("status") == "open"]
            if open_decisions:
                decision_tree_text = "\n## 待决策事项（优先填充这些知识缺口）\n"
                for d in sorted(open_decisions, key=lambda x: x.get("priority", 99)):
                    decision_tree_text += f"\n### {d['question']}\n"
                    decision_tree_text += f"优先级: P{d.get('priority', 3)}\n"
                    decision_tree_text += "需要的知识:\n"
                    for bk in d.get("blocking_knowledge", []):
                        decision_tree_text += f"  - {bk}\n"
        except:
            pass
```

然后在 discover_prompt 中注入 `{decision_tree_text}`，并修改指引：

```
优先生成能填充"待决策事项"中知识缺口的研究任务。
每个任务的 goal 应该明确指向某个决策点的某个知识缺口。
```

---

## P0-2: Agent prompt 统一管理

### 问题
tonight_deep_research.py 中 CTO/CMO/CDO 的 prompt 是内联字符串，和 LangGraph 侧的 `agent_prompts.yaml` 不一致。

### 修复
先检查 `src/config/agent_prompts.yaml` 中是否有 CTO/CMO/CDO 的 prompt 定义。然后：

1. 在 `agent_prompts.yaml` 中为深度研究场景添加专用 prompt 段落（`deep_research_cto`、`deep_research_cmo`、`deep_research_cdo`），或在现有 prompt 中添加深度研究的角色说明。

2. 在 `tonight_deep_research.py` 的 Agent prompt 构建部分，改为从 yaml 读取：

```python
from src.config.prompt_loader import get_agent_prompt

# 替换内联的 cto_prompt 构建
base_prompt = get_agent_prompt("deep_research_cto")
# 如果 get_agent_prompt 不支持这个 key，用 "CTO" 兜底
if not base_prompt:
    base_prompt = get_agent_prompt("CTO")
if not base_prompt:
    base_prompt = "你是智能骑行头盔项目的技术合伙人（CTO）。"

cto_prompt = (
    f"{base_prompt}\n\n"
    f"{expert_injection}\n\n"
    f"{anchor_instruction}\n\n"
    f"## 调研数据\n{distilled_material}\n\n"
    f"## 已有知识库\n{kb_material}\n\n"
    f"{CAPABILITY_GAP_INSTRUCTION}\n\n"
    # ... 其余不变
)
```

CMO 和 CDO 同理。

---

## P0-3: 拆分 tonight_deep_research.py

### 当前状态
文件可能超过 1000 行，包含：并发基础设施、模型路由、降级映射、专家框架匹配、KB 检索增强、4 个 Schema 定义、结构化提取、Layer 1-5 完整逻辑、任务调度器、自主发现、汇总报告。

### 拆分方案

创建 `scripts/deep_research/` 目录，拆分为：

```
scripts/deep_research/__init__.py      — 空文件
scripts/deep_research/config.py        — PROVIDER_SEMAPHORES, FALLBACK_MAP, _get_model_for_role, _get_model_for_task, _call_model, _call_with_backoff
scripts/deep_research/schemas.py       — OPTICAL_BENCHMARK_SCHEMA, LAYOUT_ANALYSIS_SCHEMA, HARDWARE_LAYOUT_SCHEMA, GENERAL_SCHEMA
scripts/deep_research/search.py        — _search_one_query, Layer 1 并发搜索逻辑
scripts/deep_research/distill.py       — _extract_structured_data, Layer 2 并发提炼
scripts/deep_research/agents.py        — _run_agent, Layer 3 并行 Agent, _match_expert_framework, _get_kb_context_enhanced
scripts/deep_research/synthesis.py     — Layer 4 整合逻辑
scripts/deep_research/critic.py        — CRITIC_FEW_SHOT, _run_critic_challenge, Layer 5 完整逻辑
scripts/deep_research/scheduler.py     — run_deep_learning, _load_task_pool, _discover_new_tasks, _get_tasks_for_session
scripts/deep_research/pipeline.py      — deep_research_one, _run_layers_1_to_3, _run_layers_4_to_5
```

`scripts/tonight_deep_research.py` 保留为入口文件（~30 行），只做 import 和 expose：

```python
"""深度研究管道 v2 入口"""
from scripts.deep_research.pipeline import deep_research_one, _run_layers_1_to_3, _run_layers_4_to_5
from scripts.deep_research.scheduler import run_deep_learning, _load_task_pool, _discover_new_tasks
from scripts.deep_research.config import _call_model, _call_with_backoff, _get_model_for_role, _get_model_for_task, FALLBACK_MAP
from scripts.deep_research.critic import _run_critic_challenge

# 保持向后兼容：所有现有 import 路径不变
```

**CC 执行要点：**
- 先确认 tonight_deep_research.py 的实际行数和函数边界
- 拆分时保持所有函数签名不变
- 所有现有的 import（text_router.py 中的 `from scripts.tonight_deep_research import run_deep_learning`）必须继续工作
- 拆完后运行 `python -c "from scripts.tonight_deep_research import run_deep_learning; print('OK')"` 验证

---

## 执行顺序

1. P0-1: 创建决策树 + 注入发现引擎
2. P0-2: Agent prompt 统一管理
3. P0-3: 拆分 tonight_deep_research.py

每项完成后：
```bash
git add -A && git commit -m "improve: {描述}" && git push origin main
```

**不要重启服务。**
