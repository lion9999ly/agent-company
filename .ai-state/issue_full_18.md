# Day 17 系统全量审计 - scripts/roundtable/verdict_parser.py

```python
"""
@description: 评判解析器 - 将用户自然语言评价解析为结构化缺陷，驱动规则库迭代
@dependencies: model_gateway
@last_modified: 2026-04-08

交互流程：
1. 圆桌完成后 10 分钟内用户发的消息自动当评判处理
2. LLM 解析为结构化缺陷
3. 判断能否转化为规则
4. 飞书展示规则草案
5. 用户回复"确认"后入库
"""
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import json
from datetime import datetime

from src.utils.model_gateway import get_model_gateway


@dataclass
class ParsedVerdict:
    """解析后的评判"""
    original_text: str           # 原始用户文本
    issues: List[Dict[str, str]] # 解析出的结构化缺陷 [{criterion, description, expected}]
    suggested_rules: List[Dict]  # 可转化的规则草案
    can_automate: bool           # 是否可自动化为规则
    timestamp: str


class VerdictParser:
    """评判解析器

    职责：
    - 解析用户自然语言评价为结构化缺陷
    - 判断能否转化为验证规则
    - 提供规则草案供用户确认
    """

    def __init__(self, gw=None):
        self.gw = gw or get_model_gateway()
        self.rules_dir = Path(".ai-state/verifier_rules")
        self.rules_dir.mkdir(parents=True, exist_ok=True)

    async def parse(self, user_text: str, task_topic: str, acceptance_criteria: List[str]) -> ParsedVerdict:
        """解析用户评价

        Args:
            user_text: 用户自然语言评价
            task_topic: 任务议题（用于上下文）
            acceptance_criteria: 验收标准列表

        Returns:
            ParsedVerdict
        """
        prompt = f"""用户对"{task_topic}"任务的评价：
"{user_text}"

验收标准：
{chr(10).join(f'{i+1}. {c}' for i, c in enumerate(acceptance_criteria))}

请解析用户评价：

1. 提取用户指出的缺陷，对应到具体验收标准
2. 判断每个缺陷的严重程度（P0/P1）
3. 判断是否可以转化为自动验证规则

输出 JSON 格式：
{{
  "issues": [
    {{"criterion": "验收标准X", "description": "具体问题", "expected": "期望行为", "severity": "P0/P1"}}
  ],
  "suggested_rules": [
    {{"type": "keyword_exists", "params": {{"keyword": "xxx"}}, "criterion": "验收标准X", "severity": "P1"}}
  ],
  "can_automate": true/false
}}
"""

        result = self.gw.call(
            model_name="gpt_4o_norway",
            prompt=prompt,
            system_prompt="你是评判解析器，将用户评价转换为结构化缺陷和验证规则。",
            task_type="generation",
        )

        if result.get("success"):
            response = result.get("response", "")
            try:
                # 提取 JSON
                import re
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    data = json.loads(json_match.group())
                    return ParsedVerdict(
                        original_text=user_text,
                        issues=data.get("issues", []),
                        suggested_rules=data.get("suggested_rules", []),
                        can_automate=data.get("can_automate", False),
                        timestamp=datetime.now().isoformat(),
                    )
            except json.JSONDecodeError:
                pass

        # 解析失败，返回原始文本
        return ParsedVerdict(
            original_text=user_text,
            issues=[{"criterion": "用户反馈", "description": user_text, "expected": "", "severity": "P1"}],
            suggested_rules=[],
            can_automate=False,
            timestamp=datetime.now().isoformat(),
        )

    def format_rules_for_display(self, rules: List[Dict]) -> str:
        """格式化规则草案供飞书展示"""
        if not rules:
            return "无可转化的规则"

        lines = ["检测到可自动化的验证规则：", ""]
        for i, rule in enumerate(rules, 1):
            lines.append(f"{i}. 类型: {rule.get('type')}")
            lines.append(f"   参数: {json.dumps(rule.get('params', {}), ensure_ascii=False)}")
            lines.append(f"   对应标准: {rule.get('criterion')}")
            lines.append("")

        lines.append("回复「确认」将规则加入规则库")
        return "\n".join(lines)

    async def confirm_rules(self, rules: List[Dict], task_topic: str) -> bool:
        """用户确认后，将规则加入规则库"""
        if not rules:
            return False

        # 加载现有规则
        task_rules_file = self.rules_dir / f"task_{task_topic[:20].replace(' ', '_')}.json"
        existing_rules = []
        if task_rules_file.exists():
            try:
                existing_rules = json.loads(task_rules_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing_rules = []

        # 添加新规则
        existing_rules.extend(rules)

        # 保存
        task_rules_file.write_text(
            json.dumps(existing_rules, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        # 记录进化日志
        self._log_evolution("user_verdict", rules, task_topic)

        return True

    def _log_evolution(self, source: str, rules: List[Dict], task_topic: str):
        """记录规则进化日志"""
        log_file = self.rules_dir / "evolution_log.jsonl"
        entry = {
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "task": task_topic,
            "rules_count": len(rules),
            "rules": rules,
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# === 飞书集成 ===
async def handle_user_verdict(text: str, reply_target: str, send_reply,
                               task_topic: str, acceptance_criteria: List[str]):
    """处理用户评判（飞书入口）

    用法：圆桌完成后 10 分钟内，用户发送的消息自动当评判处理
    """
    parser = VerdictParser()

    # 解析
    verdict = await parser.parse(text, task_topic, acceptance_criteria)

    # 展示解析结果
    if verdict.issues:
        issues_text = "\n".join(f"- [{i['severity']}] {i['description']}" for i in verdict.issues)
        send_reply(reply_target, f"收到评判：\n{issues_text}")

    # 如果有可转化的规则，展示并等待确认
    if verdict.can_automate and verdict.suggested_rules:
        rules_display = parser.format_rules_for_display(verdict.suggested_rules)
        send_reply(reply_target, rules_display)
        # 注意：实际确认需要等待用户下一条消息，这里简化处理

    return verdict
```
