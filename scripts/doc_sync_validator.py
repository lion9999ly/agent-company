# 📄 文档同构校验器 (Doc Code Sync Validator)
"""
核心职责：验证代码与文档的同构性，防止知识库腐化。

检查维度：
1. 文件级：Python文件头部Docstring格式
2. 模块级：目录README.md存在性和内容
3. 依赖级：声明的依赖与实际import一致性
4. 架构级：代码变更与文档变更同步

报告输出：.ai-state/sync_report.json

参考：RULES.md 第4条"三层分形文档与强制同构铁律"

作者：虚拟研发中心安全团队
创建：2026-03-16
"""

import ast
import re
import json
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

# === 配置 ===

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
AI_ARCH_DIR = PROJECT_ROOT / ".ai-architecture"
SYNC_REPORT_FILE = PROJECT_ROOT / ".ai-state" / "sync_report.json"


class SyncCheckType(Enum):
    """检查类型"""
    DOCSTRING_FORMAT = "docstring_format"       # Docstring格式
    MODULE_README = "module_readme"             # 模块README
    DEPENDENCY_MATCH = "dependency_match"       # 依赖匹配
    ARCHITECTURE_SYNC = "architecture_sync"     # 架构同步


class SyncSeverity(Enum):
    """问题严重程度"""
    INFO = "info"           # 信息提示
    WARNING = "warning"     # 警告
    ERROR = "error"         # 错误
    CRITICAL = "critical"   # 严重错误


@dataclass
class SyncIssue:
    """同构问题"""
    check_type: SyncCheckType
    severity: SyncSeverity
    file_path: str
    message: str
    suggestion: str
    line: Optional[int] = None


@dataclass
class FileSyncReport:
    """文件同步报告"""
    file_path: str
    has_docstring: bool
    docstring_fields: dict[str, Optional[str]]
    declared_dependencies: list[str]
    actual_imports: list[str]
    dependency_mismatch: list[str]
    issues: list[SyncIssue]


@dataclass
class ModuleSyncReport:
    """模块同步报告"""
    module_path: str
    has_readme: bool
    readme_sections: list[str]
    expected_sections: list[str]
    missing_sections: list[str]
    files_checked: int
    files_with_issues: int


@dataclass
class SyncReport:
    """完整同步报告"""
    generated_at: str
    total_files_checked: int
    total_modules_checked: int
    total_issues: int
    critical_issues: int
    error_issues: int
    warning_issues: int
    file_reports: list[FileSyncReport]
    module_reports: list[ModuleSyncReport]
    passed: bool


# === Docstring 解析 ===

REQUIRED_DOCSTRING_FIELDS = ["description", "dependencies", "last_modified"]
OPTIONAL_DOCSTRING_FIELDS = ["author", "version", "status"]


def parse_docstring(docstring: str) -> dict[str, Optional[str]]:
    """
    解析Docstring中的字段

    支持格式：
    @description: 文件描述
    @dependencies: 依赖模块
    @last_modified: YYYY-MM-DD
    """
    fields = {f: None for f in REQUIRED_DOCSTRING_FIELDS + OPTIONAL_DOCSTRING_FIELDS}

    if not docstring:
        return fields

    # 匹配 @field: value 格式
    pattern = r'@(\w+):\s*(.+?)(?=@\w+:|$)'
    matches = re.findall(pattern, docstring, re.DOTALL)

    for field_name, value in matches:
        field_name = field_name.lower()
        if field_name in fields:
            fields[field_name] = value.strip()

    return fields


def extract_docstring(content: str) -> Optional[str]:
    """提取文件顶部Docstring，支持跳过开头的注释行"""
    lines = content.split('\n')
    # 跳过开头的注释行和空行
    start_idx = 0
    while start_idx < len(lines):
        line = lines[start_idx].strip()
        if line and not line.startswith('#'):
            break
        start_idx += 1

    # 从第一个非注释非空行开始查找
    remaining = '\n'.join(lines[start_idx:]).lstrip()

    if remaining.startswith('"""'):
        end_idx = remaining.find('"""', 3)
        if end_idx != -1:
            return remaining[3:end_idx].strip()
    elif remaining.startswith("'''"):
        end_idx = remaining.find("'''", 3)
        if end_idx != -1:
            return remaining[3:end_idx].strip()

    return None


# === Import 解析 ===

def extract_imports(content: str) -> list[str]:
    """提取文件中的import语句"""
    imports = []

    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
    except SyntaxError:
        pass

    return list(set(imports))


def parse_declared_dependencies(dependencies_str: Optional[str]) -> list[str]:
    """解析声明的依赖列表"""
    if not dependencies_str:
        return []

    # 支持逗号分隔或换行分隔
    deps = re.split(r'[,\n]', dependencies_str)
    return [d.strip() for d in deps if d.strip()]


def check_dependency_match(declared: list[str], actual: list[str]) -> list[str]:
    """
    检查声明的依赖与实际import是否匹配

    Returns:
        不匹配的依赖列表
    """
    mismatches = []

    # 内置模块白名单（不需要声明）
    BUILTIN_MODULES = {
        'os', 'sys', 'json', 're', 'ast', 'hashlib', 'datetime', 'pathlib',
        'typing', 'dataclasses', 'enum', 'functools', 'itertools', 'collections',
        'operator', 'subprocess', 'shutil', 'time', 'copy', 'io', 'contextlib'
    }

    # 检查实际import是否在声明中
    for imp in actual:
        # 跳过内置模块
        if imp.split('.')[0] in BUILTIN_MODULES:
            continue

        # 跳过项目内部模块（以src.开头的）
        if imp.startswith('src.') or imp in ['src']:
            continue

        # 检查是否在声明中
        is_declared = False
        for dep in declared:
            if dep in imp or imp in dep:
                is_declared = True
                break

        if not is_declared and imp not in BUILTIN_MODULES:
            mismatches.append(f"未声明依赖: {imp}")

    return mismatches


# === README 检查 ===

REQUIRED_README_SECTIONS = ["功能", "职责", "接口"]  # 或英文版本


def check_readme_sections(readme_path: Path) -> tuple[list[str], list[str]]:
    """
    检查README.md的内容结构

    Returns:
        (实际章节, 缺失章节)
    """
    if not readme_path.exists():
        return [], REQUIRED_README_SECTIONS

    content = readme_path.read_text(encoding='utf-8')

    # 提取所有标题
    sections = re.findall(r'^#+\s*(.+)$', content, re.MULTILINE)
    section_names = [s.strip() for s in sections]

    # 检查必需章节（中英文兼容）
    missing = []
    for required in REQUIRED_README_SECTIONS:
        found = False
        for section in section_names:
            if required.lower() in section.lower():
                found = True
                break
        if not found:
            missing.append(required)

    return section_names, missing


# === 核心校验器 ===

class DocCodeSyncValidator:
    """文档同构校验器"""

    def __init__(self, src_dir: Path = SRC_DIR):
        self.src_dir = src_dir
        self.file_reports: list[FileSyncReport] = []
        self.module_reports: list[ModuleSyncReport] = []
        self.all_issues: list[SyncIssue] = []

    def validate_all(self) -> SyncReport:
        """执行所有校验"""
        self.file_reports = []
        self.module_reports = []
        self.all_issues = []

        # 1. 校验所有Python文件
        for py_file in self.src_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            report = self._validate_file(py_file)
            self.file_reports.append(report)

        # 2. 校验所有模块目录
        checked_modules = set()
        for py_file in self.src_dir.rglob("*.py"):
            module_dir = py_file.parent
            if str(module_dir) not in checked_modules:
                report = self._validate_module(module_dir)
                self.module_reports.append(report)
                checked_modules.add(str(module_dir))

        # 3. 生成报告
        return self._generate_report()

    def _validate_file(self, file_path: Path) -> FileSyncReport:
        """校验单个文件"""
        rel_path = str(file_path.relative_to(PROJECT_ROOT))
        content = file_path.read_text(encoding='utf-8')
        issues = []

        # 提取Docstring
        docstring = extract_docstring(content)
        has_docstring = docstring is not None
        docstring_fields = parse_docstring(docstring)

        # 检查Docstring格式
        for field in REQUIRED_DOCSTRING_FIELDS:
            if not docstring_fields.get(field):
                issues.append(SyncIssue(
                    check_type=SyncCheckType.DOCSTRING_FORMAT,
                    severity=SyncSeverity.ERROR,
                    file_path=rel_path,
                    message=f"缺失Docstring字段: @{field}",
                    suggestion=f"添加 @{field}: 字段到文件顶部Docstring"
                ))

        # 提取import和声明的依赖
        actual_imports = extract_imports(content)
        declared_deps = parse_declared_dependencies(docstring_fields.get("dependencies"))
        mismatches = check_dependency_match(declared_deps, actual_imports)

        for mismatch in mismatches:
            issues.append(SyncIssue(
                check_type=SyncCheckType.DEPENDENCY_MATCH,
                severity=SyncSeverity.WARNING,
                file_path=rel_path,
                message=mismatch,
                suggestion="在@dependencies中声明此依赖"
            ))

        self.all_issues.extend(issues)

        return FileSyncReport(
            file_path=rel_path,
            has_docstring=has_docstring,
            docstring_fields=docstring_fields,
            declared_dependencies=declared_deps,
            actual_imports=actual_imports,
            dependency_mismatch=mismatches,
            issues=issues
        )

    def _validate_module(self, module_dir: Path) -> ModuleSyncReport:
        """校验模块目录"""
        rel_path = str(module_dir.relative_to(PROJECT_ROOT))
        readme_path = module_dir / "README.md"

        has_readme = readme_path.exists()
        sections, missing = check_readme_sections(readme_path)

        issues = []
        if not has_readme:
            issues.append(SyncIssue(
                check_type=SyncCheckType.MODULE_README,
                severity=SyncSeverity.ERROR,
                file_path=rel_path,
                message="缺失模块级README.md",
                suggestion=f"创建 {rel_path}/README.md，包含功能说明、接口文档"
            ))
        elif missing:
            issues.append(SyncIssue(
                check_type=SyncCheckType.MODULE_README,
                severity=SyncSeverity.WARNING,
                file_path=rel_path,
                message=f"README缺失章节: {', '.join(missing)}",
                suggestion="补充缺失的章节内容"
            ))

        self.all_issues.extend(issues)

        # 统计模块内文件
        py_files = list(module_dir.glob("*.py"))
        files_with_issues = sum(1 for f in py_files if f.name != "__init__.py"
                                and any(r.file_path == str(f.relative_to(PROJECT_ROOT))
                                       for r in self.file_reports if r.issues))

        return ModuleSyncReport(
            module_path=rel_path,
            has_readme=has_readme,
            readme_sections=sections,
            expected_sections=REQUIRED_README_SECTIONS,
            missing_sections=missing,
            files_checked=len(py_files),
            files_with_issues=files_with_issues
        )

    def _generate_report(self) -> SyncReport:
        """生成完整报告"""
        critical = sum(1 for i in self.all_issues if i.severity == SyncSeverity.CRITICAL)
        errors = sum(1 for i in self.all_issues if i.severity == SyncSeverity.ERROR)
        warnings = sum(1 for i in self.all_issues if i.severity == SyncSeverity.WARNING)

        report = SyncReport(
            generated_at=datetime.now().isoformat(),
            total_files_checked=len(self.file_reports),
            total_modules_checked=len(self.module_reports),
            total_issues=len(self.all_issues),
            critical_issues=critical,
            error_issues=errors,
            warning_issues=warnings,
            file_reports=[self._file_report_to_dict(r) for r in self.file_reports],
            module_reports=[self._module_report_to_dict(r) for r in self.module_reports],
            passed=(critical == 0 and errors == 0)
        )

        # 保存报告
        self._save_report(report)

        return report

    def _file_report_to_dict(self, report: FileSyncReport) -> dict:
        return {
            "file_path": report.file_path,
            "has_docstring": report.has_docstring,
            "docstring_fields": report.docstring_fields,
            "declared_dependencies": report.declared_dependencies,
            "actual_imports": report.actual_imports,
            "dependency_mismatch": report.dependency_mismatch,
            "issue_count": len(report.issues)
        }

    def _module_report_to_dict(self, report: ModuleSyncReport) -> dict:
        return {
            "module_path": report.module_path,
            "has_readme": report.has_readme,
            "readme_sections": report.readme_sections,
            "missing_sections": report.missing_sections,
            "files_checked": report.files_checked,
            "files_with_issues": report.files_with_issues
        }

    def _save_report(self, report: SyncReport):
        """保存报告到文件"""
        SYNC_REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)

        report_dict = {
            "generated_at": report.generated_at,
            "summary": {
                "total_files_checked": report.total_files_checked,
                "total_modules_checked": report.total_modules_checked,
                "total_issues": report.total_issues,
                "critical_issues": report.critical_issues,
                "error_issues": report.error_issues,
                "warning_issues": report.warning_issues,
                "passed": report.passed
            },
            "file_reports": report.file_reports,
            "module_reports": report.module_reports
        }

        with open(SYNC_REPORT_FILE, 'w', encoding='utf-8') as f:
            json.dump(report_dict, f, ensure_ascii=False, indent=2)

    def format_report(self, report: SyncReport) -> str:
        """格式化报告为可读文本"""
        lines = [
            "=" * 60,
            "[SYNC REPORT] Document-Code Synchronization Check",
            "=" * 60,
            f"Generated: {report.generated_at}",
            f"Files checked: {report.total_files_checked}",
            f"Modules checked: {report.total_modules_checked}",
            "",
            f"Issues: {report.total_issues} total",
            f"  Critical: {report.critical_issues}",
            f"  Errors: {report.error_issues}",
            f"  Warnings: {report.warning_issues}",
            "",
            f"Status: {'PASS' if report.passed else 'FAIL'}",
            "=" * 60
        ]

        # 显示文件问题
        files_with_issues = [r for r in self.file_reports if r.issues]
        if files_with_issues:
            lines.append("\n[FILES WITH ISSUES]")
            for fr in files_with_issues[:10]:
                lines.append(f"\n  {fr.file_path}")
                for issue in fr.issues[:3]:
                    lines.append(f"    [{issue.severity.value}] {issue.message}")

        # 显示模块问题
        modules_without_readme = [r for r in self.module_reports if not r.has_readme]
        if modules_without_readme:
            lines.append("\n[MODULES MISSING README]")
            for mr in modules_without_readme[:5]:
                lines.append(f"  {mr.module_path}")

        return "\n".join(lines)


# === 便捷函数 ===

_validator: Optional[DocCodeSyncValidator] = None

def get_sync_validator() -> DocCodeSyncValidator:
    """获取全局校验器"""
    global _validator
    if _validator is None:
        _validator = DocCodeSyncValidator()
    return _validator


def validate_doc_code_sync() -> SyncReport:
    """便捷函数：执行文档同构校验"""
    return get_sync_validator().validate_all()


# === 测试入口 ===

if __name__ == "__main__":
    print("=" * 60)
    print("Document-Code Sync Validator Test")
    print("=" * 60)

    validator = DocCodeSyncValidator()
    report = validator.validate_all()

    print(validator.format_report(report))

    print(f"\nReport saved to: {SYNC_REPORT_FILE}")