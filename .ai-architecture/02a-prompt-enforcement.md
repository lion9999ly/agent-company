# 🔒 模型选型与执行固化机制 (Model Enforcement Config)

> **[SYSTEM DIRECTIVE]**
> 本文件定义了 Agent 运行时的强制配置参数。`src/graph/router.py` 中的大模型实例化代码，必须读取且仅能读取本配置，绝对禁止在 Python 代码中硬编码模型名称。

## 1. 核心大模型路由表 (`src/config/model_config.yaml`)

必须在项目配置文件中写入以下 YAML：

```yaml
system_model_routing:
  # CPO 规划中枢：强制强逻辑、大上下文模型
  cpo_plan_agent:
    provider: "anthropic"
    model_id: "claude-3-5-sonnet-20241022"
    temperature: 0.2
    max_tokens: 4096

  # CPO 评审中枢：强制跨厂商、强推理、低幻觉模型 (能力错位原则)
  cpo_critic_agent:
    provider: "google"
    model_id: "gemini-1.5-pro-002" # 或者配置 deepseek-coder
    temperature: 0.0 # 绝对确定性
    max_tokens: 2048

  # CTO / CMO 执行末端：平衡速度与代码能力
  execution_agents:
    provider: "anthropic"
    model_id: "claude-3-5-sonnet-20241022"
    temperature: 0.1
```    

## 2. 物理工具能力映射表 (src/config/tool_capabilities.yaml)
必须在项目中新增此配置，作为 Critic 审查“伪硬约束”的唯一合法物理依据：

```yaml
tool_capabilities:
  hardware_simulator_api:
    measurable_metrics: ["max_power_mw", "connection_timeout_ms", "packet_loss_rate"]
  linter_hook:
    measurable_metrics: ["type_hints_coverage", "no_eval_exec", "code_complexity", "max_lines"]
  internal_wiki_search:
    measurable_metrics: ["source_verified", "no_exaggerated_claims"]
```    

## 3. 全量哈希物理固化流程 (The Hash Hook V2)
CPO_Plan 输出 JSON 后，系统必须执行以下强制 Python 逻辑，哈希计算必须覆盖所有核心元数据，防止越权篡改：

Python
def enforce_contract_hash(state: AgentGlobalState) -> AgentGlobalState:
    import hashlib
    import json
    
    # 提取所有不可篡改的核心字段
    payload_parts = [
        json.dumps(state['sub_tasks'], sort_keys=True),
        json.dumps(state.get('prototype_evaluation', {}), sort_keys=True),
        state['contract_metadata']['contract_version'],
        state['contract_metadata']['generated_at'],
        state['contract_metadata']['operator_role_applied'],
        state['metadata']['task_id']
    ]
    
    # 有序拼接并计算 SHA-256
    payload = "|".join(payload_parts)
    contract_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    
    state['task_contract']['_sys_enforced_hash'] = contract_hash
    return state