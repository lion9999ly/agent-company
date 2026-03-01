# 🗺️ 全局架构拓扑与状态树 (Global Architecture & State)

> **[SYSTEM DIRECTIVE]**
> 本文件定义了 Multi-Agent 虚拟公司的核心流转拓扑图 (DAG) 以及全局内存状态 (Global State) 的强类型约束。

## 1. 核心流转拓扑图 (DAG)

```mermaid
graph TD
    %% 节点定义
    START((START))
    Hash_Check{Hash_Check\n安全校验}
    CPO_Plan[CPO_Plan\n需求拆解]
    CPO_Critic[CPO_Critic\n漏洞对审]
    CPO_PrototypeDecision{原型梯度决策}
    
    %% 原型中心子图 ( LO_FI / HI_FI )
    subgraph Prototype_Team [产品原型中心]
        Proto_LoFi[LoFi_Agent\nUI流程/逻辑验证]
        Proto_HiFi[HiFi_Agent\n3D建模/高保真交互]
        Proto_Review[Proto_Reviewer\n原型可行性评审]
    end
    
    Router{并行分发路由\nMap-Reduce}
    
    %% CTO 子图
    subgraph CTO_Team [CTO 研发交付部]
        CTO_Coder[Coder_Agent\n软硬件代码]
        CTO_Hook((物理 Hook))
        CTO_DemoVerifier[Demo_Verifier\n仿真/编译]
        CTO_Reviewer[Reviewer_Agent\n逻辑审查]
        CTO_Acceptance((Acceptance_Checker\n结构化指标硬校验))
    end
    
    %% CMO 子图
    subgraph CMO_Team [CMO 市场策略部]
        CMO_Strategist[Strategist_Agent\n策略文案]
        CMO_FactCheck[Fact_Checker\n信源校验]
        CMO_Acceptance((Acceptance_Checker\n合规度硬校验))
    end
    
    Merge_Node[State_Merge\n合并与验收]
    Consensus_Log_Trigger[Log_Trigger\n架构变更草稿]
    END((END/ARCHIVED))
    HITL((人类介入\nHALTED))
    TERMINATED((TERMINATED\n异常终止))

    %% 前置流转
    START --> Hash_Check --> CPO_Plan --> CPO_Critic
    CPO_Critic -- "存在漏洞" --> CPO_Plan
    CPO_Critic -- "PASS" --> CPO_PrototypeDecision
    
    %% 原型分级流转
    CPO_PrototypeDecision -- "LO_FI" --> Proto_LoFi --> Proto_Review
    CPO_PrototypeDecision -- "HI_FI" --> Proto_HiFi --> Proto_Review
    CPO_PrototypeDecision -- "NO_PROTOTYPE" --> Router
    Proto_Review -- "打回修改" --> Proto_LoFi
    Proto_Review -- "LO_FI通过" --> Proto_HiFi
    Proto_Review -- "全量通过" --> Router
    
    %% 并行执行
    Router --> CTO_Coder
    Router --> CMO_Strategist
    
    %% CTO 执行环 (新增 Acceptance_Checker)
    CTO_Coder --> CTO_Hook --> CTO_DemoVerifier --> CTO_Reviewer --> CTO_Acceptance
    CTO_Acceptance -- "硬指标不达标" --> CTO_Coder
    CTO_Acceptance -- "达标" --> Merge_Node
    
    %% CMO 执行环
    CMO_Strategist --> CMO_FactCheck --> CMO_Acceptance
    CMO_Acceptance -- "格式/合规不达标" --> CMO_Strategist
    CMO_Acceptance -- "达标" --> Merge_Node
    
    %% 异常与终态
    Merge_Node --> Consensus_Log_Trigger --> END
    CTO_Acceptance -. "重试超限" .-> HITL
    HITL -- "人类驳回 (REJECTED)" --> TERMINATED
2. 全局状态机字典 (TypedDict & Enums)
Python
from typing import TypedDict, Annotated, List, Dict, Optional
from enum import Enum
import operator

def append_to_list(existing: List, new: List) -> List:
    return existing + new

# --- 2.1 强类型枚举区 (消除魔法字符串) ---
class GlobalStatus(str, Enum):
    PENDING = "pending"
    VALIDATING_HASH = "validating_hash"
    PLANNING = "planning"
    PROTOTYPING_LO_FI = "prototyping_lo_fi" 
    PROTOTYPING_HI_FI = "prototyping_hi_fi" 
    EXECUTING = "executing"
    MERGING = "merging"
    HALTED = "halted"
    COMPLETED = "completed"
    TERMINATED = "terminated" # 新增：被人类彻底否决的异常终态
    ARCHIVED = "archived"     # 新增：正常完结后的数据归档态

class TargetRole(str, Enum):
    CTO = "cto"
    CMO = "cmo"
    PROTOTYPE = "prototype"

class NodeStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    HALTED = "halted"
    TIMEOUT = "timeout" # 新增：依赖超时状态

class HumanApprovalStatus(str, Enum):
    NONE = "none"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"

class OperatorRole(str, Enum):
    # 新增：人类操作者权限隔离
    ARCHITECT = "architect"         # 架构师：可修改所有规则与 State
    PRODUCT_MANAGER = "pm"          # 产品经理：仅可修改需求与 CMO 契约
    HARDWARE_ENGINEER = "hw_eng"    # 硬件工程师：仅可修改 CTO 契约与指标

# --- 2.2 结构化契约与探针区 ---
class SubTaskContract(TypedDict):
    subtask_id: str
    target_role: TargetRole 
    task_description: str
    depends_on: List[str]
    is_core_dependency: bool        # 新增：True=超时触发挂起, False=超时仅提示并继续/跳过
    dependency_timeout_sec: int     # 防死锁超时阈值（如 1800 秒）
    output_schema: Dict[str, str] 
    acceptance_criteria: Dict[str, Dict[str, str]] 
    tool_white_list: List[str]

class NodeExecutionLog(TypedDict):
    node_name: str
    start_time: float
    end_time: float
    duration_sec: float
    token_usage: Optional[int]
    status: NodeStatus 

# --- 2.3 全局控制与状态树 ---
class ControlData(TypedDict):
    current_node: str
    retry_counts: Dict[str, int]
    error_traceback: Annotated[List[str], append_to_list]
    human_approval_status: HumanApprovalStatus 
    resume_from_node: Optional[str]
    human_intervention_logs: Annotated[List[Dict[str, str]], append_to_list]
    proposed_consensus_draft: Optional[str]
    node_execution_logs: Annotated[List[NodeExecutionLog], append_to_list]

class ExecutionData(TypedDict):
    prototype_output: Optional[Dict[str, str]]
    cto_output: Optional[Dict[str, str]]
    cmo_output: Optional[Dict[str, str]]
    review_reports: Annotated[List[Dict[str, str]], append_to_list]

class TaskMetadata(TypedDict):
    task_id: str
    original_query: str
    global_status: GlobalStatus 
    max_retry_threshold: int
    created_at: str

class AgentGlobalState(TypedDict):
    metadata: TaskMetadata
    task_contract: Dict[str, str]
    sub_tasks: Dict[str, SubTaskContract]
    execution: ExecutionData
    control: ControlData