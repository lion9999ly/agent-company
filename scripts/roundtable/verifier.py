"""
@description: 审查闭环 - 规则层 + LLM层混合验证（v2: 三层规则库）
@dependencies: model_gateway, task_spec
@last_modified: 2026-04-08

v2 新增：
- 三层规则执行：global.json → type_{output_type}.json → TaskSpec.auto_verify_rules
- 自动生成规则：TaskSpec 无规则时 LLM 根据验收标准生成
- 规则存储：.ai-state/verifier_rules/{global,type_html,...}.json
"""
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import re
import json

from src.utils.model_gateway import get_model_gateway
from scripts.roundtable.task_spec import TaskSpec


# v2: 规则检查函数库
RULE_CHECKS = {
    "no_external_deps": lambda output: (
        "https://cdn.jsdelivr.net" not in output and
        "https://unpkg.com" not in output and
        "https://cdnjs.cloudflare.com" not in output and
        # 豁免字体 CDN
        "fonts.googleapis.com" not in output and
        "fonts.gstatic.com" not in output
    ),
    "keyword_exists": lambda output, keyword: keyword in output,
    "keyword_count": lambda output, keyword, min_count: output.count(keyword) >= min_count,
    "file_size_range": lambda output, min_kb, max_kb: min_kb * 1024 <= len(output) <= max_kb * 1024,
    "line_count_range": lambda output, min_lines, max_lines: min_lines <= len(output.split("\n")) <= max_lines,
    "html_valid": lambda output: all(tag in output for tag in ["<!DOCTYPE", "<html", "</html>", "<head>", "</head>", "<body>", "</body>"]),
    "json_parseable": lambda output: _try_parse_json(output),
}


def _try_parse_json(output: str) -> bool:
    """尝试解析 JSON"""
    try:
        json.loads(output)
        return True
    except json.JSONDecodeError:
        return False


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

    v2 三层规则：
    - global.json: 全局通用规则
    - type_{output_type}.json: 输出类型专用规则
    - TaskSpec.auto_verify_rules: 任务专用规则

    混合验证：
    - 规则层（代码，不调 LLM）：格式正确性、关键词存在性
    - LLM 层（Critic 模型）：逐条验收标准评分

    退出条件：
    - passed=True → 完成
    - stuck=True → 升级策略（换模型/拆子问题/通知人工）
    - 否则 → 继续迭代
    """

    # 规则存储目录
    RULES_DIR = Path(".ai-state/verifier_rules")

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
        self._ensure_rules_dir()

    def _ensure_rules_dir(self):
        """确保规则目录存在"""
        self.RULES_DIR.mkdir(parents=True, exist_ok=True)

    def _load_rules(self, rule_file: str) -> List[Dict]:
        """加载规则文件"""
        path = self.RULES_DIR / rule_file
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return []
        return []

    def _save_rules(self, rule_file: str, rules: List[Dict]):
        """保存规则文件"""
        path = self.RULES_DIR / rule_file
        path.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")

    def _get_all_rules(self, task: TaskSpec) -> List[Dict]:
        """v2: 获取三层规则（合并）

        优先级：global → type → task_spec_file → task.auto_verify_rules
        """
        all_rules = []

        # 1. 全局规则
        global_rules = self._load_rules("global.json")
        all_rules.extend(global_rules)

        # 2. 输出类型规则
        type_rules = self._load_rules(f"type_{task.output_type}.json")
        all_rules.extend(type_rules)

        # 3. 任务专用规则文件（task_{safe_topic}.json）
        safe_topic = "".join(c for c in task.topic[:20] if c.isalnum() or c in "_-").strip()
        if safe_topic:
            task_rules = self._load_rules(f"task_{safe_topic}.json")
            all_rules.extend(task_rules)

        # 4. TaskSpec 内嵌规则
        if task.auto_verify_rules:
            all_rules.extend(task.auto_verify_rules)

        return all_rules

    async def _auto_generate_rules(self, task: TaskSpec) -> List[Dict]:
        """v2: 根据验收标准自动生成规则"""
        prompt = f"""请根据以下验收标准生成验证规则。

验收标准：
{chr(10).join(f'{i+1}. {c}' for i, c in enumerate(task.acceptance_criteria))}

输出类型：{task.output_type}

请生成 JSON 数组格式的规则，每个规则包含：
- type: 规则类型（keyword_exists, keyword_count, line_count_range, html_valid 等）
- params: 参数对象
- criterion: 对应的验收标准
- severity: P0 或 P1

示例输出：
[
  {{"type": "html_valid", "params": {{}}, "criterion": "单 HTML 文件", "severity": "P0"}},
  {{"type": "keyword_exists", "params": {{"keyword": "hud-container"}}, "criterion": "四角布局", "severity": "P1"}}
]

只输出 JSON 数组，不要其他文字。
"""

        result = self.gw.call(
            model_name="gpt_4o_norway",  # 使用较便宜的模型
            prompt=prompt,
            system_prompt="你是验证规则生成器，输出 JSON 格式。",
            task_type="generation",
        )

        if result.get("success"):
            response = result.get("response", "")
            try:
                # 提取 JSON
                json_match = re.search(r'\[.*\]', response, re.DOTALL)
                if json_match:
                    rules = json.loads(json_match.group())
                    # 保存到任务专用规则文件
                    self._save_rules(f"task_{task.topic[:20].replace(' ', '_')}.json", rules)
                    return rules
            except json.JSONDecodeError:
                pass

        return []

    async def verify(self, task: TaskSpec, output: str) -> VerifyResult:
        """验证输出

        v2: 支持三层规则 + 自动生成规则

        Args:
            task: TaskSpec
            output: 生成的产物内容

        Returns:
            VerifyResult
        """
        issues = []

        # v2: 获取三层规则（如果无规则，自动生成）
        rules = self._get_all_rules(task)
        if not rules:
            print("  [Verifier] 无规则，自动生成...")
            rules = await self._auto_generate_rules(task)
            # 更新 TaskSpec
            if rules:
                task.auto_verify_rules = rules

        # 1. v2: 执行三层规则
        rule_issues = self._execute_rules(rules, output, task)
        issues.extend(rule_issues)

        # 2. 规则层：格式检查
        format_issues = self._rule_layer_check(task, output)
        issues.extend(format_issues)

        # 3. 规则层：可自动验证的验收标准
        auto_issues = self._auto_check_criteria(task, output)
        issues.extend(auto_issues)

        # 4. LLM 层：复杂验收标准
        llm_issues = await self._llm_check_criteria(task, output, issues)
        issues.extend(llm_issues)

        # 5. 卡住检测
        stuck = self._detect_stuck(issues)

        passed = len(issues) == 0

        return VerifyResult(
            passed=passed,
            issues=issues,
            stuck=stuck,
            stuck_issues=self._previous_issues if stuck else [],
        )

    def _execute_rules(self, rules: List[Dict], output: str, task: TaskSpec) -> List[Issue]:
        """v2: 执行规则检查"""
        issues = []

        for rule in rules:
            rule_type = rule.get("type")
            params = rule.get("params", {})
            criterion = rule.get("criterion", "")
            severity = rule.get("severity", "P1")

            if rule_type not in RULE_CHECKS:
                continue

            check_fn = RULE_CHECKS[rule_type]

            try:
                # 执行检查
                if rule_type in ("keyword_exists", "keyword_count", "file_size_range", "line_count_range"):
                    passed = check_fn(output, **params)
                else:
                    passed = check_fn(output)

                if not passed:
                    issues.append(Issue(
                        criterion=criterion,
                        description=f"规则检查失败: {rule_type}",
                        expected=f"应满足 {rule_type} 规则",
                        severity=severity,
                    ))
            except Exception as e:
                # 规则执行出错，跳过
                print(f"  [Verifier] 规则执行出错: {rule_type} - {e}")

        return issues

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