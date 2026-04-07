"""
@description: 审查闭环 - 规则层 + LLM层混合验证
@dependencies: model_gateway, task_spec
@last_modified: 2026-04-06
"""
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import re
import json

from src.utils.model_gateway import get_model_gateway
from scripts.roundtable.task_spec import TaskSpec


@dataclass
class Issue:
    """缺陷描述"""
    criterion: str          # 对应的验收标准
    description: str        # 缺陷描述
    expected: str           # 期望行为
    severity: str           # "P0" | "P1"


@dataclass
class VerifyResult:
    """审查结果"""
    passed: bool            # 全部通过
    issues: List[Issue]     # 未通过的缺陷清单
    stuck: bool             # 同一缺陷连续两轮未修复
    stuck_issues: List[str] # 卡住的具体问题


class Verifier:
    """审查闭环

    混合验证：
    - 规则层（代码，不调 LLM）：格式正确性、关键词存在性
    - LLM 层（Critic 模型）：逐条验收标准评分

    退出条件：
    - passed=True → 完成
    - stuck=True → 升级策略（换模型/拆子问题/通知人工）
    - 否则 → 继续迭代

    没有轮数上限。退出靠验收标准和卡住检测。
    """

    # 规则层检查关键词映射
    RULE_KEYWORDS = {
        "html": ["<!DOCTYPE", "<html", "</html>", "<head>", "<body>"],
        "json": ["{", "}"],
        "markdown": ["#"],
    }

    def __init__(self, gw=None, stuck_threshold: int = 2):
        self.gw = gw or get_model_gateway()
        self.stuck_threshold = stuck_threshold
        self._previous_issues = []  # 用于卡住检测

    async def verify(self, task: TaskSpec, output: str) -> VerifyResult:
        """验证输出

        Args:
            task: TaskSpec
            output: 生成的产物内容

        Returns:
            VerifyResult
        """
        issues = []

        # 1. 规则层：格式检查
        rule_issues = self._rule_layer_check(task, output)
        issues.extend(rule_issues)

        # 2. 规则层：可自动验证的验收标准
        auto_issues = self._auto_check_criteria(task, output)
        issues.extend(auto_issues)

        # 3. LLM 层：复杂验收标准
        llm_issues = await self._llm_check_criteria(task, output, issues)
        issues.extend(llm_issues)

        # 4. 卡住检测
        stuck = self._detect_stuck(issues)

        passed = len(issues) == 0

        return VerifyResult(
            passed=passed,
            issues=issues,
            stuck=stuck,
            stuck_issues=self._previous_issues if stuck else [],
        )

    def _rule_layer_check(self, task: TaskSpec, output: str) -> List[Issue]:
        """规则层：格式正确性"""
        issues = []

        output_type = task.output_type

        # HTML 格式检查
        if output_type == "html":
            keywords = self.RULE_KEYWORDS.get("html", [])
            for kw in keywords:
                if kw not in output:
                    issues.append(Issue(
                        criterion="文件格式",
                        description=f"缺少必要标签：{kw}",
                        expected=f"应包含 {kw}",
                        severity="P0",
                    ))

            # 检查标签闭合
            open_tags = re.findall(r"<(\w+)[^>]*>", output)
            close_tags = re.findall(r"</(\w+)>", output)
            # 简化检查：只检查关键标签
            for tag in ["html", "head", "body", "div", "script"]:
                if tag in open_tags and tag not in close_tags:
                    issues.append(Issue(
                        criterion="文件格式",
                        description=f"标签未闭合：{tag}",
                        expected=f"</{tag}>",
                        severity="P0",
                    ))

        # JSON 格式检查
        elif output_type == "json":
            try:
                json.loads(output)
            except json.JSONDecodeError as e:
                issues.append(Issue(
                    criterion="文件格式",
                    description=f"JSON 解析错误：{str(e)}",
                    expected="有效的 JSON 格式",
                    severity="P0",
                ))

        return issues

    def _auto_check_criteria(self, task: TaskSpec, output: str) -> List[Issue]:
        """规则层：可自动验证的验收标准"""
        issues = []

        for criterion in task.acceptance_criteria:
            # 关键词存在性检查
            if "包含" in criterion or "含有" in criterion or "必须" in criterion:
                # 提取关键词
                keywords = re.findall(r'["\']([\w\-]+)["\']|包含\s+(\w+)', criterion)
                for kw_tuple in keywords:
                    kw = kw_tuple[0] or kw_tuple[1]
                    if kw and kw not in output:
                        issues.append(Issue(
                            criterion=criterion,
                            description=f"缺少关键词：{kw}",
                            expected=f"应包含 '{kw}'",
                            severity="P1",
                        ))

            # 文件大小检查（如果有要求）
            if "文件大小" in criterion or "行数" in criterion:
                # 解析数值要求
                match = re.search(r"(\d+)\s*(行|KB|MB)", criterion)
                if match:
                    limit = int(match.group(1))
                    unit = match.group(2)
                    if unit == "行":
                        actual = len(output.split("\n"))
                        if actual > limit:
                            issues.append(Issue(
                                criterion=criterion,
                                description=f"行数超限：{actual} > {limit}",
                                expected=f"≤ {limit} 行",
                                severity="P1",
                            ))

        return issues

    async def _llm_check_criteria(self, task: TaskSpec, output: str,
                                   existing_issues: List[Issue]) -> List[Issue]:
        """LLM 层：复杂验收标准审查"""
        issues = []

        # 排除已检查的标准
        checked_criteria = [i.criterion for i in existing_issues]
        unchecked_criteria = [c for c in task.acceptance_criteria
                             if c not in checked_criteria and not self._can_auto_check(c)]

        if not unchecked_criteria:
            return issues

        prompt = f"""【输出内容】
{output[:5000]}

【待审查的验收标准】
{chr(10).join(f'{i+1}. {c}' for i, c in enumerate(unchecked_criteria))}

请逐条审查，判断每条标准是否满足。
对于不满足的标准，给出：
- 缺陷描述
- 期望行为

格式：
## 审查结果
- 标准1：✅ 满足
- 标准2：❌ 不满足 — 缺陷：..., 期望：...
"""

        result = self.gw.call(
            model_name="gemini_3_1_pro",
            prompt=prompt,
            system_prompt="你是质量审查官，严格审查代码是否满足验收标准。",
            task_type="review",
        )

        if result.get("success"):
            response = result.get("response", "")

            # 解析结果
            parsed_any = False
            for line in response.split("\n"):
                if "❌" in line:
                    # 提取缺陷描述
                    match = re.search(r"标准(\d+).*❌.*缺陷[:：]\s*(.+)", line)
                    if match:
                        parsed_any = True
                        idx = int(match.group(1)) - 1
                        if idx < len(unchecked_criteria):
                            desc = match.group(2).strip()
                            issues.append(Issue(
                                criterion=unchecked_criteria[idx],
                                description=desc,
                                expected="满足该标准",
                                severity="P0",
                            ))
                elif "✅" in line or "✓" in line:
                    parsed_any = True

            # 解析失败检查：如果完全没有解析出任何结果，不能默认通过
            if not parsed_any and unchecked_criteria:
                issues.append(Issue(
                    criterion="LLM 审查解析失败",
                    description=f"无法解析 LLM 输出格式，共 {len(unchecked_criteria)} 条标准未验证",
                    expected="每条标准应有明确的 ✅ 或 ❌ 标记",
                    severity="P0",
                ))

        return issues

    def _can_auto_check(self, criterion: str) -> bool:
        """判断标准是否可以自动检查"""
        auto_patterns = [
            "包含", "含有", "必须", "文件大小", "行数",
            "零依赖", "单文件", "双击",
        ]
        return any(p in criterion for p in auto_patterns)

    def _detect_stuck(self, issues: List[Issue]) -> bool:
        """卡住检测：同一缺陷连续两轮未修复"""
        current_issue_keys = [i.criterion + i.description[:30] for i in issues]

        # 与上一次比较
        common = set(current_issue_keys) & set(self._previous_issues)

        # 更新历史
        self._previous_issues = current_issue_keys

        # 如果超过阈值的问题相同，判定为卡住
        return len(common) >= self.stuck_threshold