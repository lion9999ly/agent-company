#!/usr/bin/env python3
"""
@description: Codex 交叉评审脚本 - 支持 OpenAI、Azure OpenAI 和 Google Gemini API
@dependencies: openai, google-generativeai, pathlib, json
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

# 尝试导入 API 客户端
try:
    from openai import OpenAI, AzureOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    print("WARNING: openai package not installed. Run: pip install openai")

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    print("WARNING: google-generativeai package not installed. Run: pip install google-generativeai")


# ==========================================
# 配置与常量
# ==========================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # scripts -> pythonProject1
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
    """Codex 交叉评审器 - 支持 OpenAI、Azure OpenAI 和 Google Gemini"""

    def __init__(self, provider: str = "auto", api_key: Optional[str] = None):
        """
        初始化评审器

        provider: "auto", "azure", "openai", "gemini"
        - auto: 自动检测可用的 API（优先级: gemini > azure > openai）

        环境变量:
        - GOOGLE_API_KEY: Google Gemini API key
        - AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT: Azure OpenAI
        - OPENAI_API_KEY: 标准 OpenAI
        """
        self.provider = provider
        self.client = None
        self.gemini_model = None
        self.model = "unknown"

        # 自动选择或使用指定 provider
        if provider == "auto":
            self._init_auto()
        elif provider == "gemini":
            self._init_gemini(api_key)
        elif provider == "azure":
            self._init_azure()
        elif provider == "openai":
            self._init_openai(api_key)
        else:
            print(f"[WARNING] Unknown provider: {provider}")

    def _init_auto(self):
        """自动检测可用的 API"""
        # 优先级 1: Gemini (通常最稳定)
        gemini_key = os.getenv("GOOGLE_API_KEY")
        if gemini_key and HAS_GEMINI:
            self._init_gemini(gemini_key)
            if self.gemini_model:
                return

        # 优先级 2: Azure OpenAI
        azure_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        if azure_key and azure_endpoint and HAS_OPENAI:
            self._init_azure()
            if self.client:
                return

        # 优先级 3: 标准 OpenAI
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key and HAS_OPENAI:
            self._init_openai(openai_key)
            if self.client:
                return

        print("[WARNING] 未找到可用的 API，评审将被跳过")

    def _init_gemini(self, api_key: Optional[str] = None):
        """初始化 Google Gemini"""
        key = api_key or os.getenv("GOOGLE_API_KEY")
        if not key:
            print("[WARNING] GOOGLE_API_KEY not set")
            return

        if not HAS_GEMINI:
            print("[WARNING] google-generativeai not installed. Run: pip install google-generativeai")
            return

        try:
            genai.configure(api_key=key)
            self.gemini_model = genai.GenerativeModel('gemini-2.5-flash')
            self.model = "gemini-2.5-flash"
            print(f"[INFO] 已连接 Google Gemini: {self.model}")
        except Exception as e:
            print(f"[WARNING] Gemini 初始化失败: {e}")

    def _init_azure(self):
        """初始化 Azure OpenAI"""
        if not HAS_OPENAI:
            return

        azure_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_version = os.getenv("OPENAI_API_VERSION", "2024-02-15-preview")

        if not (azure_key and azure_endpoint):
            return

        try:
            self.client = AzureOpenAI(
                api_key=azure_key,
                api_version=api_version,
                azure_endpoint=azure_endpoint
            )
            self.model = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
            print(f"[INFO] 已连接 Azure OpenAI: {azure_endpoint}")
        except Exception as e:
            print(f"[WARNING] Azure OpenAI 初始化失败: {e}")

    def _init_openai(self, api_key: Optional[str] = None):
        """初始化标准 OpenAI"""
        if not HAS_OPENAI:
            return

        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            return

        try:
            self.client = OpenAI(api_key=key)
            self.model = "gpt-4o"
            print(f"[INFO] 已连接 OpenAI API")
        except Exception as e:
            print(f"[WARNING] OpenAI 初始化失败: {e}")

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

        # 直接发送完整内容，让模型自己分析
        all_content = ""
        for f, content in target_contents.items():
            all_content += f"=== {f} ===\n{content}\n\n"

        # 限制总长度
        if len(all_content) > 3000:
            all_content = all_content[:3000] + "\n...[truncated]"

        prompt = f"""Review this Chinese project documentation. Output ONLY valid JSON.

Dimensions: {', '.join(request.review_dimensions)}

Check:
1. Security blacklist (安全黑名单) - must list forbidden functions like eval(), exec(), os.system()
2. Quality thresholds (质量硬阈值) - must have clear limits
3. Documentation rules (文档同构规则) - must be complete

Content:
{all_content}

JSON output (NO markdown):
{{"score": <0-10>, "dimensions": {{"<dim>": {{"score": <0-10>, "issues": [], "suggestions": []}}}}, "blockers": [], "warnings": []}}"""

        return prompt

    def review(self, request: ReviewRequest) -> ReviewResult:
        """执行评审"""
        request_id = self.generate_request_id(request)

        # 如果没有任何可用的 API
        if not self.client and not self.gemini_model:
            return ReviewResult(
                request_id=request_id,
                score=10.0,
                passed=True,
                dimensions={d: {"score": 10, "issues": [], "suggestions": []} for d in request.review_dimensions},
                blockers=["WARNING: No API configured, review skipped"],
                warnings=[],
                reviewer_model="none",
                timestamp=datetime.now().isoformat(),
                raw_response="Review skipped due to missing API configuration"
            )

        prompt = self.build_review_prompt(request)

        # 使用 Gemini
        if self.gemini_model:
            return self._review_with_gemini(request_id, prompt, request.review_dimensions)

        # 使用 OpenAI/Azure
        return self._review_with_openai(request_id, prompt, request.review_dimensions)

    def _try_complete_json(self, truncated_json: str) -> str:
        """尝试补全被截断的 JSON"""
        # 统计未闭合的括号
        open_braces = truncated_json.count("{") - truncated_json.count("}")
        open_brackets = truncated_json.count("[") - truncated_json.count("]")

        # 补全缺失的闭合
        completion = ""
        if open_brackets > 0:
            completion += "]" * open_brackets
        if open_braces > 0:
            completion += "}" * open_braces

        return truncated_json + completion

    def _review_with_gemini(self, request_id: str, prompt: str, dimensions: List[str]) -> ReviewResult:
        """使用 Gemini 执行评审"""
        try:
            response = self.gemini_model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.0,
                    "max_output_tokens": 4000  # 增加输出限制
                }
            )

            # 检查安全过滤
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                print(f"[DEBUG] Prompt feedback: {response.prompt_feedback}")

            # 获取完整响应
            raw_response = ""
            finish_reason = None
            if response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'finish_reason'):
                    finish_reason = candidate.finish_reason
                    if finish_reason == 2:  # MAX_TOKENS
                        print(f"[WARNING] Response truncated (MAX_TOKENS)")
                if candidate.content and candidate.content.parts:
                    raw_response = candidate.content.parts[0].text

            if not raw_response:
                print(f"[ERROR] Empty response. Candidates: {response.candidates}")
                raise ValueError("Empty response from Gemini")

            # 清理 markdown 代码块包装
            if raw_response.startswith("```json"):
                raw_response = raw_response[7:]  # 移除 ```json
            if raw_response.startswith("```"):
                raw_response = raw_response[3:]  # 移除 ```
            if raw_response.endswith("```"):
                raw_response = raw_response[:-3]  # 移除结尾的 ```
            raw_response = raw_response.strip()

            # 如果响应被截断，尝试补全 JSON
            if finish_reason == 2 and not raw_response.rstrip().endswith("}"):
                raw_response = self._try_complete_json(raw_response)

            # 解析 JSON 响应
            try:
                result_data = json.loads(raw_response)
            except json.JSONDecodeError:
                json_start = raw_response.find("{")
                json_end = raw_response.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = raw_response[json_start:json_end]
                    result_data = json.loads(json_str)
                else:
                    print(f"[ERROR] Cannot parse response. Raw length: {len(raw_response)}")
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
            print(f"ERROR during Gemini review: {e}")
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

    def _review_with_openai(self, request_id: str, prompt: str, dimensions: List[str]) -> ReviewResult:
        """使用 OpenAI/Azure 执行评审"""
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