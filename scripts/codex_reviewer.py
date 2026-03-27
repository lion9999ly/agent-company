#!/usr/bin/env python3
"""
@description: Codex 交叉评审脚本 - 使用 OpenAI API 进行代码/文档评审
@dependencies: openai, pathlib, json
@last_modified: 2026-03-16
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

# 尝试导入 openai，如果失败则提供友好提示
try:
    from openai import OpenAI
except ImportError:
    print("ERROR: openai package not installed. Run: pip install openai")
    sys.exit(1)


# ==========================================
# 配置与常量
# ==========================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AI_STATE_DIR = PROJECT_ROOT / ".ai-state"
REVIEW_LOGS_FILE = AI_STATE_DIR / "review_logs.jsonl"
REVIEW_REQUEST_FILE = AI_STATE_DIR / "review_request.json"
VIOLATION_COUNTS_FILE = AI_STATE_DIR / "violation_counts.json"

# 评审通过阈值
PASS_THRESHOLD = 8.0  # 10分制
MIN_REVIEW_ROUNDS = 1  # 最少评审轮数

# 评审维度定义
REVIEW_DIMENSIONS = {
    "hook_logic": "Hook 拦截逻辑合理性",
    "claude_md_content": "CLAUDE.md 内容完整性",
    "quality_compliance": "代码质量合规性",
    "architecture": "架构决策合理性",
    "security": "安全合规性"
}


# ==========================================
# 数据结构
# ==========================================
@dataclass
class ReviewRequest:
    """评审请求结构"""
    review_type: str  # pre_execution, post_edit, architecture_change
    target_files: List[str]
    review_dimensions: List[str]
    context: Dict[str, str]
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class ReviewResult:
    """评审结果结构"""
    request_id: str
    score: float  # 0-10
    passed: bool
    dimensions: Dict[str, Dict[str, Any]]  # {dimension: {score, issues, suggestions}}
    blockers: List[str]
    warnings: List[str]
    reviewer_model: str
    timestamp: str
    raw_response: str = ""


# ==========================================
# 评审核心逻辑
# ==========================================
class CodexReviewer:
    """Codex 交叉评审器"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            print("WARNING: OPENAI_API_KEY not set. Review will be skipped.")
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key)
        self.model = "gpt-4o"  # 使用 GPT-4o 作为评审模型

    def generate_request_id(self, request: ReviewRequest) -> str:
        """生成请求唯一ID"""
        content = f"{request.review_type}-{request.target_files}-{request.timestamp}"
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def load_context_files(self, context: Dict[str, str]) -> Dict[str, str]:
        """加载上下文文件内容"""
        loaded = {}
        for key, path in context.items():
            full_path = PROJECT_ROOT / path
            if full_path.exists():
                loaded[key] = full_path.read_text(encoding="utf-8")[:5000]  # 限制长度
            else:
                loaded[key] = f"[文件不存在: {path}]"
        return loaded

    def load_target_files(self, files: List[str]) -> Dict[str, str]:
        """加载目标文件内容"""
        loaded = {}
        for file_path in files:
            full_path = PROJECT_ROOT / file_path
            if full_path.exists():
                loaded[file_path] = full_path.read_text(encoding="utf-8")[:10000]  # 限制长度
            else:
                loaded[file_path] = f"[文件不存在: {file_path}]"
        return loaded

    def build_review_prompt(self, request: ReviewRequest) -> str:
        """构建评审提示词"""
        target_contents = self.load_target_files(request.target_files)
        context_contents = self.load_context_files(request.context)

        dimension_descriptions = [REVIEW_DIMENSIONS.get(d, d) for d in request.review_dimensions]

        prompt = f"""你是一个严格的代码评审专家。请对以下内容进行交叉评审。

## 评审类型
{request.review_type}

## 评审维度 (每项 0-10 分)
{chr(10).join(f'- {d}' for d in dimension_descriptions)}

## 上下文参考
```
{json.dumps(context_contents, ensure_ascii=False, indent=2)[:3000]}
```

## 待评审内容
```
{json.dumps(target_contents, ensure_ascii=False, indent=2)[:8000]}
```

## 输出格式 (严格 JSON)
请输出以下格式的 JSON：
{{
  "score": <总体评分 0-10>,
  "dimensions": {{
    "<维度名>": {{
      "score": <该维度评分>,
      "issues": ["问题1", "问题2"],
      "suggestions": ["建议1", "建议2"]
    }}
  }},
  "blockers": ["阻断性问题，必须修复"],
  "warnings": ["警告性问题，建议修复"]
}}

请严格评审，不要放宽标准。"""

        return prompt

    def review(self, request: ReviewRequest) -> ReviewResult:
        """执行评审"""
        request_id = self.generate_request_id(request)

        # 如果没有配置 API key，返回默认通过结果
        if not self.client:
            return ReviewResult(
                request_id=request_id,
                score=10.0,
                passed=True,
                dimensions={d: {"score": 10, "issues": [], "suggestions": []} for d in request.review_dimensions},
                blockers=["WARNING: OpenAI API key not configured, review skipped"],
                warnings=[],
                reviewer_model="none",
                timestamp=datetime.now().isoformat(),
                raw_response="Review skipped due to missing API key"
            )

        prompt = self.build_review_prompt(request)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个严格的代码评审专家，专注于发现问题和确保质量。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,  # 确定性输出
                max_tokens=2000
            )

            raw_response = response.choices[0].message.content

            # 解析 JSON 响应
            # 尝试从响应中提取 JSON
            json_start = raw_response.find("{")
            json_end = raw_response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = raw_response[json_start:json_end]
                result_data = json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")

            score = float(result_data.get("score", 0))
            passed = score >= PASS_THRESHOLD and len(result_data.get("blockers", [])) == 0

            return ReviewResult(
                request_id=request_id,
                score=score,
                passed=passed,
                dimensions=result_data.get("dimensions", {}),
                blockers=result_data.get("blockers", []),
                warnings=result_data.get("warnings", []),
                reviewer_model=self.model,
                timestamp=datetime.now().isoformat(),
                raw_response=raw_response
            )

        except Exception as e:
            print(f"ERROR during review: {e}")
            return ReviewResult(
                request_id=request_id,
                score=0.0,
                passed=False,
                dimensions={},
                blockers=[f"评审失败: {str(e)}"],
                warnings=[],
                reviewer_model=self.model,
                timestamp=datetime.now().isoformat(),
                raw_response=str(e)
            )

    def log_result(self, request: ReviewRequest, result: ReviewResult):
        """记录评审日志"""
        AI_STATE_DIR.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "request": asdict(request),
            "result": asdict(result)
        }

        with open(REVIEW_LOGS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")


# ==========================================
# 渐进式违规计数管理
# ==========================================
class ViolationCounter:
    """违规计数管理器"""

    def __init__(self):
        self.counts = self._load_counts()

    def _load_counts(self) -> Dict[str, int]:
        if VIOLATION_COUNTS_FILE.exists():
            return json.loads(VIOLATION_COUNTS_FILE.read_text(encoding="utf-8"))
        return {}

    def _save_counts(self):
        AI_STATE_DIR.mkdir(parents=True, exist_ok=True)
        VIOLATION_COUNTS_FILE.write_text(json.dumps(self.counts, indent=2), encoding="utf-8")

    def increment(self, violation_type: str) -> int:
        """增加违规计数，返回当前计数"""
        self.counts[violation_type] = self.counts.get(violation_type, 0) + 1
        self._save_counts()
        return self.counts[violation_type]

    def reset(self, violation_type: str):
        """重置违规计数"""
        if violation_type in self.counts:
            del self.counts[violation_type]
            self._save_counts()

    def should_block(self, violation_type: str, threshold: int = 3) -> bool:
        """判断是否应该阻断"""
        return self.counts.get(violation_type, 0) >= threshold


# ==========================================
# 命令行接口
# ==========================================
def main():
    """主入口"""
    if len(sys.argv) < 2:
        print("Usage: python codex_reviewer.py <review_request.json>")
        print("       python codex_reviewer.py --create-request <type> <files...>")
        sys.exit(1)

    if sys.argv[1] == "--create-request":
        # 创建评审请求
        review_type = sys.argv[2] if len(sys.argv) > 2 else "pre_execution"
        target_files = sys.argv[3:] if len(sys.argv) > 3 else []

        request = ReviewRequest(
            review_type=review_type,
            target_files=target_files,
            review_dimensions=["quality_compliance", "security"],
            context={
                "quality_redlines": ".ai-architecture/01-quality-redlines.md",
                "global_architecture": ".ai-architecture/00-global-architecture.md"
            }
        )

        AI_STATE_DIR.mkdir(parents=True, exist_ok=True)
        REVIEW_REQUEST_FILE.write_text(json.dumps(asdict(request), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Review request created: {REVIEW_REQUEST_FILE}")
        return

    # 执行评审
    request_file = Path(sys.argv[1])
    if not request_file.exists():
        print(f"ERROR: Request file not found: {request_file}")
        sys.exit(1)

    request_data = json.loads(request_file.read_text(encoding="utf-8"))
    request = ReviewRequest(**request_data)

    reviewer = CodexReviewer()
    result = reviewer.review(request)
    reviewer.log_result(request, result)

    # 输出结果
    print(f"\n{'='*50}")
    print(f"Review Result: {'PASS' if result.passed else 'BLOCK'}")
    print(f"Score: {result.score:.1f}/10")
    print(f"Request ID: {result.request_id}")
    print(f"{'='*50}")

    if result.blockers:
        print("\nBlockers:")
        for b in result.blockers:
            print(f"  - {b}")

    if result.warnings:
        print("\nWarnings:")
        for w in result.warnings:
            print(f"  - {w}")

    # 根据结果设置退出码
    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    main()