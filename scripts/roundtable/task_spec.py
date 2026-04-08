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

    # ── v2 新增：Generator 输入模式 ──
    generator_input_mode: str = "auto"  # "raw_proposal" | "executive_summary" | "auto"
    # auto 逻辑：html/code/json/jsx → raw_proposal; markdown/report/pptx → executive_summary

    # ── v2 新增：Verifier 自动验证规则 ──
    auto_verify_rules: List[Dict] = field(default_factory=list)
    # 规则类型：no_external_deps, keyword_exists, keyword_count, file_size_range, line_count_range, html_valid, json_parseable

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
            "generator_input_mode": self.generator_input_mode,  # v2
            "auto_verify_rules": self.auto_verify_rules,  # v2
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
            generator_input_mode=data.get("generator_input_mode", "auto"),  # v2
            auto_verify_rules=data.get("auto_verify_rules", []),  # v2
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
    """从预定义文件加载 TaskSpec，支持模糊匹配

    存放位置：.ai-state/task_specs/{topic}.json

    匹配优先级：
    1. 精确匹配文件名
    2. 归一化匹配（去空格、转下划线、转小写）
    3. 子串匹配（topic 包含文件名或反之）
    4. JSON 内部 topic 字段匹配
    """
    import json
    import re
    from pathlib import Path

    specs_dir = Path(".ai-state/task_specs")
    if not specs_dir.exists():
        return None

    # 归一化函数
    def normalize(s: str) -> str:
        s = s.strip().lower()
        s = re.sub(r'[\s\u3000]+', '_', s)          # 空格/全角空格 → _
        s = re.sub(r'[^\w\u4e00-\u9fff]', '', s)    # 去非字母数字非中文
        return s

    # 1. 精确匹配（原逻辑）
    exact = specs_dir / f"{topic}.json"
    if exact.exists():
        return TaskSpec.from_json_file(str(exact))

    norm_topic = normalize(topic)

    # 2. 归一化匹配
    for f in specs_dir.glob("*.json"):
        norm_file = normalize(f.stem)
        if norm_file == norm_topic:
            return TaskSpec.from_json_file(str(f))

    # 3. 子串匹配
    for f in specs_dir.glob("*.json"):
        norm_file = normalize(f.stem)
        if norm_topic in norm_file or norm_file in norm_topic:
            return TaskSpec.from_json_file(str(f))

    # 4. JSON 内部 topic 字段匹配
    for f in specs_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if normalize(data.get("topic", "")) == norm_topic:
                return TaskSpec.from_json_file(str(f))
        except Exception:
            continue

    return None