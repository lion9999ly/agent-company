import operator
from typing import TypedDict, Annotated, List, Dict, Optional, Any
from enum import Enum

# --- 1. 强类型枚举 (消除魔法字符串并补充 __str__ 方法) ---
class GlobalStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    PROTOTYPING_LO_FI = "prototyping_lo_fi"
    PROTOTYPING_HI_FI = "prototyping_hi_fi"
    EXECUTING = "executing"
    MERGING = "merging"
    HALTED = "halted"
    COMPLETED = "completed"
    TERMINATED = "terminated"
    ARCHIVED = "archived"

    def __str__(self) -> str:
        return self.value

class TargetRole(str, Enum):
    CTO = "cto"
    CMO = "cmo"
    PROTOTYPE = "prototype"

    def __str__(self) -> str:
        return self.value

class NodeStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    HALTED = "halted"
    TIMEOUT = "timeout"

    def __str__(self) -> str:
        return self.value

class OperatorRole(str, Enum):
    ARCHITECT = "architect"
    PRODUCT_MANAGER = "pm"
    HARDWARE_ENGINEER = "hw_eng"

    def __str__(self) -> str:
        return self.value

# --- Reducer 函数 ---
def append_logs(existing: List[Any], new: List[Any]) -> List[Any]:
    return existing + new if existing else new

# --- 结构化字典 ---
class SubTaskContract(TypedDict):
    subtask_id: str
    target_role: TargetRole
    task_description: str
    depends_on: List[str]
    is_core_dependency: bool
    dependency_timeout_sec: int
    output_schema: Dict[str, str]
    acceptance_criteria: Dict[str, Dict[str, str]]
    tool_white_list: List[str]

class NodeExecutionLog(TypedDict):
    node_name: str
    start_time: float
    end_time: float
    duration_sec: float
    status: NodeStatus

# --- 核心状态树 ---
class ControlData(TypedDict):
    current_node: str
    retry_counts: Dict[str, int]
    error_traceback: Annotated[List[str], append_logs]
    human_approval_status: str
    resume_from_node: Optional[str]
    node_execution_logs: Annotated[List[NodeExecutionLog], append_logs]

class ExecutionData(TypedDict):
    prototype_output: Optional[Dict[str, str]]
    cto_output: Optional[Dict[str, str]]
    cmo_output: Optional[Dict[str, str]]
    review_reports: Annotated[List[Dict[str, str]], append_logs]

class TaskMetadata(TypedDict):
    task_id: str
    global_status: GlobalStatus
    max_retry_threshold: int

# --- 2. 细化中枢元数据与契约 (消灭 Dict[str, Any]) ---
class ContractMetadata(TypedDict):
    contract_version: str
    generated_at: str
    operator_role_applied: str

class PrototypeEvaluation(TypedDict):
    has_hardware_ui: bool
    has_new_interaction_logic: bool
    is_existing_product_iteration: bool
    decision_result: str

class TaskContract(TypedDict):
    task_goal: str
    _sys_enforced_hash: str  # 由系统物理计算注入的哈希印记

# --- 3. 明确 Send API 扇出切片类型 ---
class CTOTaskSlice(TypedDict):
    current_task_id: str

class CMOTaskSlice(TypedDict):
    current_task_id: str

# --- 4. 组装终极 AgentGlobalState ---
class AgentGlobalState(TypedDict):
    metadata: TaskMetadata
    contract_metadata: ContractMetadata         # 已细化
    prototype_evaluation: PrototypeEvaluation   # 已细化
    task_contract: TaskContract                 # 已细化
    sub_tasks: Dict[str, SubTaskContract]
    execution: ExecutionData
    control: ControlData