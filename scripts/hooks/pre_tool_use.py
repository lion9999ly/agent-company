#!/usr/bin/env python3
"""
@description: Hook 拦截脚本 - 代码质量与安全检查
@dependencies: ast, pathlib, json, re
@last_modified: 2026-03-16

用法:
    python scripts/hooks/pre_tool_use.py --file <path> --content <content>
    python scripts/hooks/pre_tool_use.py --stdin

退出码:
    0 - 通过检查
    1 - 阻断（硬性拦截）
    2 - 警告（允许通过但记录）
"""

import ast
import sys
import json
import re
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field

# ==========================================
# 配置与常量
# ==========================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AI_STATE_DIR = PROJECT_ROOT / ".ai-state"
VIOLATION_COUNTS_FILE = AI_STATE_DIR / "violation_counts.json"

# 质量阈值
MAX_FILE_LINES = 800
MAX_FUNCTION_LINES = 30
MAX_NESTING_DEPTH = 3
MAX_BRANCHES = 3

# 安全黑名单
DANGEROUS_FUNCTIONS = {
    "eval": "代码注入风险",
    "exec": "代码注入风险",
    "system": "命令注入风险 (os.system)",
    "popen": "命令注入风险 (subprocess.Popen)"
}

# 密钥关键词
SECRET_PATTERNS = [
    r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']+["\']',
    r'(?i)(secret|api_key|apikey|token)\s*=\s*["\'][^"\']+["\']',
    r'(?i)(private_key|privatekey)\s*=\s*["\'][^"\']+["\']',
]


# ==========================================
# 数据结构
# ==========================================
@dataclass
class Violation:
    """违规项"""
    type: str
    severity: str  # blocker, warning
    message: str
    line: int = 0
    file: str = ""


@dataclass
class CheckResult:
    """检查结果"""
    passed: bool
    violations: List[Violation] = field(default_factory=list)
    warnings: List[Violation] = field(default_factory=list)

    def add_violation(self, v: Violation):
        if v.severity == "blocker":
            self.violations.append(v)
        else:
            self.warnings.append(v)
        self.passed = False


# ==========================================
# 渐进式违规计数器
# ==========================================
class ViolationCounter:
    """违规计数管理 - 渐进式拦截策略"""

    def __init__(self):
        self.counts = self._load_counts()

    def _load_counts(self) -> Dict[str, int]:
        if VIOLATION_COUNTS_FILE.exists():
            try:
                return json.loads(VIOLATION_COUNTS_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _save_counts(self):
        AI_STATE_DIR.mkdir(parents=True, exist_ok=True)
        VIOLATION_COUNTS_FILE.write_text(json.dumps(self.counts, indent=2), encoding="utf-8")

    def increment(self, violation_type: str) -> int:
        """增加计数并返回当前值"""
        self.counts[violation_type] = self.counts.get(violation_type, 0) + 1
        self._save_counts()
        return self.counts[violation_type]

    def get_count(self, violation_type: str) -> int:
        return self.counts.get(violation_type, 0)

    def should_block(self, violation_type: str, threshold: int = 3) -> bool:
        """判断是否应该阻断"""
        return self.get_count(violation_type) >= threshold


# ==========================================
# 检查器类
# ==========================================
class CodeChecker:
    """代码质量与安全检查器"""

    def __init__(self, file_path: str, content: str):
        self.file_path = file_path
        self.content = content
        self.lines = content.split("\n")
        self.result = CheckResult(passed=True)
        self.violation_counter = ViolationCounter()

    def check_all(self) -> CheckResult:
        """执行所有检查"""
        # 1. 文件行数检查
        self._check_file_lines()

        # 2. 安全黑名单检查 (AST + 正则)
        self._check_dangerous_functions()

        # 3. 密钥硬编码检查
        self._check_secrets()

        # 4. 函数长度检查 (仅对 Python 文件)
        if self.file_path.endswith(".py"):
            self._check_function_length()
            self._check_nesting_depth()

        return self.result

    def _check_file_lines(self):
        """检查文件行数"""
        line_count = len(self.lines)
        if line_count > MAX_FILE_LINES:
            count = self.violation_counter.increment("file_lines")
            severity = "blocker" if count >= 3 else "warning"
            self.result.add_violation(Violation(
                type="file_lines",
                severity=severity,
                message=f"文件行数 {line_count} 超过阈值 {MAX_FILE_LINES} (第 {count} 次违规)",
                file=self.file_path
            ))

    def _check_dangerous_functions(self):
        """检查危险函数调用"""
        # 正则快速检查
        for func_name, risk in DANGEROUS_FUNCTIONS.items():
            pattern = rf'\b{func_name}\s*\('
            for i, line in enumerate(self.lines, 1):
                if re.search(pattern, line, re.IGNORECASE):
                    # 排除注释行
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                        continue

                    count = self.violation_counter.increment(f"dangerous_{func_name}")
                    severity = "blocker"  # 安全问题始终是 blocker
                    self.result.add_violation(Violation(
                        type="dangerous_function",
                        severity=severity,
                        message=f"检测到危险函数 {func_name}() - {risk}",
                        line=i,
                        file=self.file_path
                    ))

        # AST 深度检查 (仅 Python)
        if self.file_path.endswith(".py"):
            try:
                tree = ast.parse(self.content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        func_name = self._get_call_name(node)
                        if func_name and func_name.lower() in [f.lower() for f in DANGEROUS_FUNCTIONS]:
                            # AST 检查到，但正则没检测到（可能是字符串拼接等）
                            pass
            except SyntaxError:
                pass  # 语法错误，让其他工具处理

    def _get_call_name(self, node: ast.Call) -> Optional[str]:
        """获取调用函数名"""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return node.func.attr
        return None

    def _check_secrets(self):
        """检查密钥硬编码"""
        for i, line in enumerate(self.lines, 1):
            for pattern in SECRET_PATTERNS:
                if re.search(pattern, line):
                    # 排除环境变量读取
                    if "os.getenv" in line or "os.environ" in line:
                        continue
                    # 排除注释
                    if line.strip().startswith("#"):
                        continue

                    count = self.violation_counter.increment("secret_hardcoded")
                    severity = "blocker"  # 安全问题始终是 blocker
                    self.result.add_violation(Violation(
                        type="secret_hardcoded",
                        severity=severity,
                        message=f"检测到可能的硬编码密钥",
                        line=i,
                        file=self.file_path
                    ))

    def _check_function_length(self):
        """检查函数长度"""
        try:
            tree = ast.parse(self.content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_lines = node.end_lineno - node.lineno + 1
                    if func_lines > MAX_FUNCTION_LINES:
                        count = self.violation_counter.increment("function_lines")
                        severity = "blocker" if count >= 3 else "warning"
                        self.result.add_violation(Violation(
                            type="function_lines",
                            severity=severity,
                            message=f"函数 {node.name} 行数 {func_lines} 超过阈值 {MAX_FUNCTION_LINES}",
                            line=node.lineno,
                            file=self.file_path
                        ))
        except SyntaxError:
            pass

    def _check_nesting_depth(self):
        """检查嵌套深度"""
        try:
            tree = ast.parse(self.content)
            self._check_nesting_recursive(tree, 0)
        except SyntaxError:
            pass

    def _check_nesting_recursive(self, node: ast.AST, depth: int):
        """递归检查嵌套深度"""
        nesting_nodes = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler)

        for child in ast.iter_child_nodes(node):
            if isinstance(child, nesting_nodes):
                new_depth = depth + 1
                if new_depth > MAX_NESTING_DEPTH:
                    count = self.violation_counter.increment("nesting_depth")
                    severity = "blocker" if count >= 3 else "warning"
                    self.result.add_violation(Violation(
                        type="nesting_depth",
                        severity=severity,
                        message=f"嵌套深度 {new_depth} 超过阈值 {MAX_NESTING_DEPTH}",
                        line=getattr(child, 'lineno', 0),
                        file=self.file_path
                    ))
                self._check_nesting_recursive(child, new_depth)
            else:
                self._check_nesting_recursive(child, depth)


# ==========================================
# 命令行接口
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="代码质量与安全检查 Hook")
    parser.add_argument("--file", required=True, help="文件路径")
    parser.add_argument("--content", help="文件内容 (如不提供则从文件读取)")
    args = parser.parse_args()

    # 读取内容
    file_path = Path(args.file)
    if not file_path.is_absolute():
        file_path = PROJECT_ROOT / args.file

    if args.content:
        content = args.content
    elif file_path.exists():
        content = file_path.read_text(encoding="utf-8")
    else:
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    # 执行检查
    checker = CodeChecker(str(file_path), content)
    result = checker.check_all()

    # 输出结果
    if result.violations:
        print("\n" + "="*50)
        print("HOOK BLOCKED - 发现阻断性问题:")
        print("="*50)
        for v in result.violations:
            print(f"  [{v.type.upper()}] {v.message}")
            if v.line:
                print(f"    位置: 第 {v.line} 行")
        print("="*50)
        sys.exit(1)

    if result.warnings:
        print("\n" + "="*50)
        print("HOOK WARNING - 发现警告性问题:")
        print("="*50)
        for v in result.warnings:
            print(f"  [{v.type.upper()}] {v.message}")
            if v.line:
                print(f"    位置: 第 {v.line} 行")
        print("="*50)
        print("提示: 连续 3 次同类违规将触发硬性拦截")
        sys.exit(2)  # 警告但允许通过

    print(f"\n[PASS] {file_path.name} 通过所有检查")
    sys.exit(0)


if __name__ == "__main__":
    main()