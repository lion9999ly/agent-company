"""
@description: 文档导入收件箱 - 自动扫描、读取、提炼、写入知识库
@dependencies: pathlib, json, src.tools.knowledge_base, src.utils.model_gateway
@last_modified: 2026-03-21
"""
import sys
import json
import re
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.knowledge_base import add_knowledge, get_knowledge_stats
from src.utils.model_gateway import get_model_gateway

INBOX_DIR = Path(__file__).parent.parent / ".ai-state" / "inbox"
PROCESSED_DIR = INBOX_DIR / "processed"
SUPPORTED_EXT = {".txt", ".md", ".csv", ".json", ".log"}


def _read_file(filepath: Path) -> str:
    """读取文件内容"""
    ext = filepath.suffix.lower()

    if ext in (".txt", ".md", ".csv", ".json", ".log"):
        try:
            return filepath.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return filepath.read_text(encoding="gbk", errors="ignore")

    elif ext == ".pdf":
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, "-c", f"""
import fitz
doc = fitz.open(r'{filepath}')
text = '\\n'.join(page.get_text() for page in doc)
print(text[:10000])
"""],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return f"[PDF 文件，需要安装 pymupdf 才能读取: {filepath.name}]"

    elif ext == ".docx":
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, "-c", f"""
from docx import Document
doc = Document(r'{filepath}')
text = '\\n'.join(p.text for p in doc.paragraphs)
print(text[:10000])
"""],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return f"[DOCX 文件，需要安装 python-docx 才能读取: {filepath.name}]"

    return f"[不支持的文件类型: {ext}]"


def _refine_document(content: str, filename: str) -> dict:
    """用 LLM 提炼文档内容，提取与项目相关的关键信息"""
    if len(content) < 20:
        return {"success": False, "error": "内容过少"}

    gateway = get_model_gateway()
    prompt = (
        f"以下是文件「{filename}」的内容。\n\n"
        f"请分析这份文档，提取与「智能骑行头盔产品研发」相关的所有关键信息。\n"
        f"按以下 JSON 格式回复，不要有其他内容：\n"
        f'{{"title": "知识条目标题(20字以内)", '
        f'"domain": "competitors或components或standards或lessons中选一个最合适的", '
        f'"tags": ["标签1", "标签2", "标签3"], '
        f'"summary": "500字以内的结构化摘要，保留关键数据、参数、结论", '
        f'"relevance": "high或medium或low，与智能骑行头盔的相关度"}}\n\n'
        f"如果文档与智能骑行头盔完全无关，relevance 设为 low。\n\n"
        f"文档内容：\n{content[:6000]}"
    )

    result = gateway.call_azure_openai(
        "cpo", prompt,
        "你是研发情报分析专家。只输出 JSON，不输出任何其他内容。",
        "doc_import"
    )

    if not result.get("success"):
        return {"success": False, "error": result.get("error", "LLM 调用失败")}

    response = result["response"].strip()
    response = re.sub(r'^```json\s*', '', response)
    response = re.sub(r'\s*```$', '', response)

    try:
        data = json.loads(response)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": f"JSON 解析失败: {e}"}


def scan_and_import(progress_callback=None) -> str:
    """扫描 inbox 目录，处理所有新文件"""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    all_ext = SUPPORTED_EXT | {".pdf", ".docx"}
    files = [f for f in INBOX_DIR.iterdir() if f.is_file() and f.suffix.lower() in all_ext]

    if not files:
        return ""

    report_lines = [f"📂 文档导入 ({datetime.now().strftime('%H:%M')})"]
    imported = 0
    skipped = 0

    for f in files:
        if progress_callback:
            progress_callback(f"📂 正在处理：{f.name}")

        content = _read_file(f)
        if len(content) < 20 or content.startswith("["):
            report_lines.append(f"  ⏭️ {f.name} — 内容过少或不支持")
            skipped += 1
            f.rename(PROCESSED_DIR / f.name)
            continue

        refined = _refine_document(content, f.name)
        if not refined.get("success"):
            report_lines.append(f"  ❌ {f.name} — {refined.get('error', '处理失败')[:100]}")
            skipped += 1
            f.rename(PROCESSED_DIR / f.name)
            continue

        data = refined["data"]
        if data.get("relevance") == "low":
            report_lines.append(f"  ⏭️ {f.name} — 与项目无关")
            skipped += 1
            f.rename(PROCESSED_DIR / f.name)
            continue

        add_knowledge(
            title=data.get("title", f.stem),
            domain=data.get("domain", "lessons"),
            content=data.get("summary", content[:500]),
            tags=data.get("tags", []),
            source=f"doc_import:{f.name}",
            confidence="high" if data.get("relevance") == "high" else "medium"
        )
        imported += 1
        report_lines.append(f"  ✅ {f.name} → {data.get('domain')}/")
        f.rename(PROCESSED_DIR / f.name)

    stats = get_knowledge_stats()
    report_lines.append(f"\n📊 知识库现状: {stats}")
    report_lines.append(f"📝 导入: {imported} 条 | 跳过: {skipped} 条")

    report = "\n".join(report_lines)
    print(report)
    return report


if __name__ == "__main__":
    report = scan_and_import()
    if not report:
        print("📂 inbox 为空，无文件需要处理")