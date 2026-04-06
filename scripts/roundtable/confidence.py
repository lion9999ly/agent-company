"""
@description: 置信度标注解析与冲突裁决逻辑
@dependencies: typing, re
@last_modified: 2026-04-06
"""
import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


# ============================================================
# 置信度标注格式
# ============================================================

CONFIDENCE_PATTERN = r"\[(事实|判断|偏好)·(高|中|低|--)\]"

# 命题类型权重
TYPE_WEIGHT = {
    "事实": 3,   # 客观陈述，最高权重
    "判断": 2,   # 专业推断
    "偏好": 0,   # 主观选择，不参与裁决
}

# 置信度权重
CONF_WEIGHT = {
    "高": 3,
    "中": 2,
    "低": 1,
    "--": 0,  # 偏好类不参与
}


@dataclass
class Claim:
    """置信度标注声明"""
    text: str                    # 原始文本
    claim_type: str              # "事实" | "判断" | "偏好"
    confidence: str              # "高" | "中" | "低" | "--"
    content: str                 # 声明内容（去除标注后的）
    source: Optional[str] = None # 来源（如果有）
    role: Optional[str] = None   # 发言角色

    def weight(self) -> float:
        """计算权重"""
        if self.claim_type == "偏好":
            return 0
        return TYPE_WEIGHT.get(self.claim_type, 0) * CONF_WEIGHT.get(self.confidence, 0)


def parse_confidence_claim(text: str, role: str = None) -> Optional[Claim]:
    """解析置信度标注

    示例输入：
    "[事实·高] 陈述内容 — 来源：xxx"

    Returns:
        Claim 对象，如果解析失败返回 None
    """
    match = re.search(CONFIDENCE_PATTERN, text)
    if not match:
        return None

    claim_type = match.group(1)
    confidence = match.group(2)

    # 提取内容（去除标注）
    content = text.replace(match.group(0), "").strip()

    # 提取来源（如果有）
    source_match = re.search(r"— 来源[:：]\s*(.+)", content)
    source = None
    if source_match:
        source = source_match.group(1).strip()
        content = content.replace(source_match.group(0), "").strip()

    return Claim(
        text=text,
        claim_type=claim_type,
        confidence=confidence,
        content=content,
        source=source,
        role=role,
    )


def extract_all_claims(text: str, role: str = None) -> List[Claim]:
    """从文本中提取所有置信度标注"""
    claims = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("["):
            claim = parse_confidence_claim(line, role)
            if claim:
                claims.append(claim)
    return claims


# ============================================================
# 冲突裁决
# ============================================================

@dataclass
class Conflict:
    """冲突描述"""
    claim_a: Claim               # 声明 A
    claim_b: Claim               # 声明 B（与 A 矛盾）
    dimension: str               # 冲突维度（design/feasibility/user_fit 等）
    resolved: bool = False       # 是否已解决
    winner: Optional[str] = None # 胜出的角色
    reason: Optional[str] = None # 裁决理由


def detect_conflict(claim_a: Claim, claim_b: Claim) -> Optional[Conflict]:
    """检测两个声明是否冲突

    简单规则：
    - 相同话题但内容矛盾
    - 一方说"做不到"/"不可行"，另一方说"可以"
    """
    if claim_a.claim_type == "偏好" or claim_b.claim_type == "偏好":
        return None  # 偏好类不参与冲突检测

    # 检测"做不到" vs "可以" 的矛盾
    impossibility_keywords = ["做不到", "不可行", "无法实现", "不可能"]
    possibility_keywords = ["可以", "可行", "能够", "可以实现"]

    a_impossible = any(kw in claim_a.content for kw in impossibility_keywords)
    a_possible = any(kw in claim_a.content for kw in possibility_keywords)
    b_impossible = any(kw in claim_b.content for kw in impossibility_keywords)
    b_possible = any(kw in claim_b.content for kw in possibility_keywords)

    # 矛盾：一方说做不到，另一方说可以
    if (a_impossible and b_possible) or (a_possible and b_impossible):
        return Conflict(
            claim_a=claim_a,
            claim_b=claim_b,
            dimension="feasibility",  # 默认可行性维度
        )

    return None


def resolve_conflict(conflict: Conflict, authority_map: Dict[str, str],
                     topic_dimension: str = None) -> Tuple[bool, str, str]:
    """裁决冲突

    Args:
        conflict: 冲突对象
        authority_map: 权威映射 {"design":"CDO", "feasibility":"CTO", ...}
        topic_dimension: 冲突维度（如果已知）

    Returns:
        (resolved, winner, reason)
        - resolved: 是否已解决
        - winner: 胜出的角色（如果有）
        - reason: 裁决理由
    """
    claim_a = conflict.claim_a
    claim_b = conflict.claim_b

    # 规则 1：硬约束否决软偏好
    # 事实·高的"做不到" > 任何判断或偏好
    if claim_a.claim_type == "事实" and claim_a.confidence == "高":
        impossibility_keywords = ["做不到", "不可行", "无法实现"]
        if any(kw in claim_a.content for kw in impossibility_keywords):
            return True, claim_a.role, "硬约束否决：事实·高的不可行声明"

    if claim_b.claim_type == "事实" and claim_b.confidence == "高":
        impossibility_keywords = ["做不到", "不可行", "无法实现"]
        if any(kw in claim_b.content for kw in impossibility_keywords):
            return True, claim_b.role, "硬约束否决：事实·高的不可行声明"

    # 规则 2：同维度冲突看置信度
    weight_a = claim_a.weight()
    weight_b = claim_b.weight()

    if weight_a > weight_b:
        return True, claim_a.role, f"置信度裁决：{claim_a.claim_type}·{claim_a.confidence} > {claim_b.claim_type}·{claim_b.confidence}"

    if weight_b > weight_a:
        return True, claim_b.role, f"置信度裁决：{claim_b.claim_type}·{claim_b.confidence} > {claim_a.claim_type}·{claim_a.confidence}"

    # 规则 3：同维度同置信度看权威性
    dimension = topic_dimension or conflict.dimension
    authority_role = authority_map.get(dimension)

    if authority_role:
        if claim_a.role == authority_role:
            return True, claim_a.role, f"权威性裁决：{dimension} 维度权威为 {authority_role}"
        if claim_b.role == authority_role:
            return True, claim_b.role, f"权威性裁决：{dimension} 维度权威为 {authority_role}"

    # 规则 4：跨维度冲突不自动裁决
    # → 标记为"未解决分歧" → 上报人工
    return False, None, "跨维度冲突，无法自动裁决，需人工介入"


# ============================================================
# Critic 置信度审查
# ============================================================

def validate_confidence_honesty(claims: List[Claim]) -> List[str]:
    """审查置信度标注是否诚实

    检查：
    1. 角色把"判断"标成"事实"来增加权重
    2. 角色声称有数据支撑但未引用具体来源
    3. 角色的多条输出之间自相矛盾

    Returns:
        问题列表（每条是一个审查发现）
    """
    issues = []

    for claim in claims:
        # 检查 1：事实类必须有来源
        if claim.claim_type == "事实" and claim.confidence in ["高", "中"]:
            if not claim.source:
                issues.append(f"[置信度质疑] {claim.role} 声称[事实·{claim.confidence}]但未提供来源：{claim.content[:50]}")

        # 棉查 2：高置信判断需要明确支撑
        if claim.claim_type == "判断" and claim.confidence == "高":
            if not claim.source:
                issues.append(f"[置信度质疑] {claim.role} 标注[判断·高]但未说明基于什么数据：{claim.content[:50]}")

    # 检查 3：内部矛盾检测
    for i, claim_a in enumerate(claims):
        for claim_b in claims[i+1:]:
            if claim_a.role == claim_b.role:
                conflict = detect_conflict(claim_a, claim_b)
                if conflict:
                    issues.append(f"[内部矛盾] {claim_a.role} 的两条声明矛盾：\n  - {claim_a.content[:30]}\n  - {claim_b.content[:30]}")

    return issues