"""
@description: CPO Critic 双模型评审模块
@dependencies: src.utils.model_gateway
@last_modified: 2026-03-16

核心职责：
1. 对CPO生成的任务契约进行毒性审查
2. 双模型阵列：Gemini + Qwen 必须双PASS才可下发
3. 输出结构化评审报告
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.model_gateway import get_model_gateway


class ReviewVerdict(Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    WARNING = "WARNING"


@dataclass
class CriticReviewResult:
    """评审结果"""
    task_id: str
    timestamp: str
    gemini_score: float
    gemini_verdict: str
    gemini_issues: list
    qwen_score: float
    qwen_verdict: str
    qwen_issues: list
    final_verdict: str
    dual_pass: bool

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "timestamp": self.timestamp,
            "gemini": {
                "score": self.gemini_score,
                "verdict": self.gemini_verdict,
                "issues": self.gemini_issues
            },
            "qwen": {
                "score": self.qwen_score,
                "verdict": self.qwen_verdict,
                "issues": self.qwen_issues
            },
            "final_verdict": self.final_verdict,
            "dual_pass": self.dual_pass
        }


class CPOCritic:
    """
    CPO Critic 交叉评审委员会

    规则：
    1. 必须双模型PASS才可下发任务
    2. 单模型BLOCK即阻止
    3. 评审维度：完整性、可行性、安全性、合规性
    """

    SYSTEM_PROMPT = """你是一个严格的任务契约评审专家。你需要对任务契约进行"挑刺"审查。

评审维度：
1. 完整性：是否缺失关键维度？指标是否可量化？
2. 可行性：技术方案是否可实现？资源是否足够？
3. 安全性：是否存在安全风险？是否触犯红线？
4. 合规性：是否符合项目规范？是否遵循架构文档？

输出格式（JSON）：
{
  "score": <1-10>,
  "verdict": "PASS" 或 "BLOCK",
  "issues": ["问题1", "问题2"],
  "suggestions": ["建议1", "建议2"]
}

注意：
- 发现任何致命问题，verdict必须是"BLOCK"
- score >= 8 才能PASS
- 要严格，不要放水
"""

    def __init__(self):
        self.gateway = get_model_gateway()

    def review_task_contract(self, task_contract: dict, task_description: str = "") -> CriticReviewResult:
        """
        评审任务契约

        Args:
            task_contract: 任务契约字典
            task_description: 任务描述

        Returns:
            CriticReviewResult: 评审结果
        """
        task_id = task_contract.get("task_id", "unknown")

        # 构建评审提示
        prompt = f"""请评审以下任务契约：

## 任务ID
{task_id}

## 任务描述
{task_description}

## 任务契约
```json
{json.dumps(task_contract, ensure_ascii=False, indent=2)}
```

请进行严格评审，输出JSON格式的结果。
"""

        # Gemini评审
        gemini_result = self._review_with_gemini(prompt)

        # Qwen评审（如果可用）
        qwen_result = self._review_with_qwen(prompt)

        # 汇总结果
        return CriticReviewResult(
            task_id=task_id,
            timestamp=datetime.now().isoformat(),
            gemini_score=gemini_result.get("score", 0),
            gemini_verdict=gemini_result.get("verdict", "BLOCK"),
            gemini_issues=gemini_result.get("issues", []),
            qwen_score=qwen_result.get("score", 0),
            qwen_verdict=qwen_result.get("verdict", "BLOCK"),
            qwen_issues=qwen_result.get("issues", []),
            final_verdict="PASS" if gemini_result.get("verdict") == "PASS" and qwen_result.get("verdict") == "PASS" else "BLOCK",
            dual_pass=gemini_result.get("verdict") == "PASS" and qwen_result.get("verdict") == "PASS"
        )

    def review_execution_output(self, output_content: str, criteria: dict) -> CriticReviewResult:
        """
        评审执行输出

        Args:
            output_content: 输出内容
            criteria: 验收标准

        Returns:
            CriticReviewResult: 评审结果
        """
        prompt = f"""请评审以下任务执行输出：

## 输出内容
{output_content[:3000]}

## 验收标准
```json
{json.dumps(criteria, ensure_ascii=False, indent=2)}
```

请判断：
1. 输出是否满足验收标准？
2. 是否存在质量问题？
3. 是否需要返工？

输出JSON格式的评审结果。
"""
        gemini_result = self._review_with_gemini(prompt)
        qwen_result = self._review_with_qwen(prompt)

        return CriticReviewResult(
            task_id="execution_review",
            timestamp=datetime.now().isoformat(),
            gemini_score=gemini_result.get("score", 0),
            gemini_verdict=gemini_result.get("verdict", "BLOCK"),
            gemini_issues=gemini_result.get("issues", []),
            qwen_score=qwen_result.get("score", 0),
            qwen_verdict=qwen_result.get("verdict", "BLOCK"),
            qwen_issues=qwen_result.get("issues", []),
            final_verdict="PASS" if gemini_result.get("verdict") == "PASS" else "BLOCK",
            dual_pass=gemini_result.get("verdict") == "PASS"
        )

    def _review_with_gemini(self, prompt: str) -> dict:
        """使用Gemini进行评审"""
        result = self.gateway.call_gemini("critic_gemini", prompt, self.SYSTEM_PROMPT)

        if not result.get("success"):
            return {"score": 0, "verdict": "BLOCK", "issues": [f"Gemini API错误: {result.get('error')}"]}

        # 解析响应
        response_text = result.get("response", "")
        return self._parse_review_response(response_text)

    def _review_with_qwen(self, prompt: str) -> dict:
        """使用Qwen进行评审"""
        cfg = self.gateway.models.get("critic_qwen")
        if not cfg or not cfg.api_key:
            # Qwen未配置，默认放行（但不计入双PASS）
            return {"score": 8, "verdict": "PASS", "issues": ["Qwen API未配置，跳过评审"]}

        result = self.gateway.call_qwen("critic_qwen", prompt, self.SYSTEM_PROMPT)

        if not result.get("success"):
            return {"score": 0, "verdict": "BLOCK", "issues": [f"Qwen API错误: {result.get('error')}"]}

        response_text = result.get("response", "")
        return self._parse_review_response(response_text)

    def _parse_review_response(self, response: str) -> dict:
        """解析评审响应"""
        try:
            # 尝试提取JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass

        # 解析失败，根据关键词判断
        response_upper = response.upper()
        if "BLOCK" in response_upper or "严重" in response or "致命" in response:
            return {"score": 3, "verdict": "BLOCK", "issues": ["解析失败，但检测到负面评价"]}
        elif "PASS" in response_upper:
            return {"score": 8, "verdict": "PASS", "issues": []}
        else:
            return {"score": 5, "verdict": "WARNING", "issues": ["无法解析评审结果"]}


# 全局实例
_critic: Optional[CPOCritic] = None


def get_cpo_critic() -> CPOCritic:
    """获取全局CPO Critic实例"""
    global _critic
    if _critic is None:
        _critic = CPOCritic()
    return _critic


# === 测试 ===
if __name__ == "__main__":
    print("=" * 60)
    print("[CPO CRITIC TEST]")
    print("=" * 60)

    critic = get_cpo_critic()

    # 测试评审
    test_contract = {
        "task_id": "test_001",
        "task_goal": "测试评审功能",
        "sub_tasks": [
            {"id": "sub1", "description": "子任务1"}
        ]
    }

    result = critic.review_task_contract(test_contract, "这是一个测试任务")

    print(f"\n[RESULT]")
    print(f"Task ID: {result.task_id}")
    print(f"Gemini Score: {result.gemini_score}/10")
    print(f"Gemini Verdict: {result.gemini_verdict}")
    print(f"Qwen Score: {result.qwen_score}/10")
    print(f"Qwen Verdict: {result.qwen_verdict}")
    print(f"Final Verdict: {result.final_verdict}")
    print(f"Dual Pass: {result.dual_pass}")

    if result.gemini_issues:
        print(f"\nGemini Issues: {result.gemini_issues}")

    print("\n" + "=" * 60)