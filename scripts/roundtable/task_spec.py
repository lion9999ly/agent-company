"""
@description: TaskSpec 数据类定义 - 圆桌系统任务配置
@dependencies: dataclasses, typing
@last_modified: 2026-04-06
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class TaskSpec:
    """圆桌系统任务规格

    核心设计：
    - acceptance_criteria 是唯一退出条件，没有轮数上限
    - role_prompts 是角色×议题的专属 prompt，不是通用角色描述
    - authority_map 定义冲突裁决权威，"final": "Leo" 表示不可调和分歧上报人工
    - TaskSpec 不包含任何业务逻辑，是纯配置
    """

    # ── 议题 ──
    topic: str                          # 简短议题名："HUD Demo 生成"
    goal: str                           # 一句话目标

    # ── 验收标准（退出条件，不是轮数）──
    acceptance_criteria: List[str]      # 每条可验证，全部通过才算完成

    # ── 角色分配 ──
    proposer: str                       # 出方案的角色："CDO"
    reviewers: List[str]                # 审方案的角色：["CTO", "CMO"]
    critic: str                         # 终审："Critic"

    # ── 权威性映射（冲突裁决用）──
    authority_map: Dict[str, str]       # {"design":"CDO", "feasibility":"CTO", "user_fit":"CMO", "final":"Leo"}

    # ── 输入 ──
    input_docs: List[str]               # 输入文档路径列表
    kb_search_queries: List[str]        # KB 搜索关键词，用于 Crystallizer 准备上下文

    # ── 角色议题专属 prompt（角色×议题矩阵）──
    role_prompts: Dict[str, str]        # {"CDO": "本议题下你需要关注...", "CTO": "...", ...}

    # ── 输出 ──
    output_type: str                    # "html" | "markdown" | "json" | "code"
    output_path: str                    # 输出文件路径

    # ── 可选扩展 ──
    max_iterations: int = 10            # 最大迭代轮数（防止死循环）
    timeout_minutes: int = 60           # 任务超时时间

    def to_dict(self) -> dict:
        """转换为字典（用于 JSON 序列化）"""
        return {
            "topic": self.topic,
            "goal": self.goal,
            "acceptance_criteria": self.acceptance_criteria,
            "proposer": self.proposer,
            "reviewers": self.reviewers,
            "critic": self.critic,
            "authority_map": self.authority_map,
            "input_docs": self.input_docs,
            "kb_search_queries": self.kb_search_queries,
            "role_prompts": self.role_prompts,
            "output_type": self.output_type,
            "output_path": self.output_path,
            "max_iterations": self.max_iterations,
            "timeout_minutes": self.timeout_minutes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskSpec":
        """从字典创建（用于 JSON 反序列化）"""
        return cls(
            topic=data.get("topic", ""),
            goal=data.get("goal", ""),
            acceptance_criteria=data.get("acceptance_criteria", []),
            proposer=data.get("proposer", "CDO"),
            reviewers=data.get("reviewers", []),
            critic=data.get("critic", "Critic"),
            authority_map=data.get("authority_map", {}),
            input_docs=data.get("input_docs", []),
            kb_search_queries=data.get("kb_search_queries", []),
            role_prompts=data.get("role_prompts", {}),
            output_type=data.get("output_type", "html"),
            output_path=data.get("output_path", ""),
            max_iterations=data.get("max_iterations", 10),
            timeout_minutes=data.get("timeout_minutes", 60),
        )

    @classmethod
    def from_json_file(cls, path: str) -> "TaskSpec":
        """从 JSON 文件加载"""
        import json
        from pathlib import Path
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)


def load_task_spec(topic: str) -> Optional[TaskSpec]:
    """从预定义文件加载 TaskSpec

    存放位置：.ai-state/task_specs/{topic}.json
    """
    from pathlib import Path
    spec_path = Path(".ai-state/task_specs") / f"{topic}.json"
    if spec_path.exists():
        return TaskSpec.from_json_file(str(spec_path))
    return None