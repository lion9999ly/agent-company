"""
@description: 知识库管理 - 搜索、写入、检索项目级领域知识
@dependencies: json, pathlib, datetime
@last_modified: 2026-03-21
"""
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

KB_ROOT = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "knowledge"


def search_knowledge(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """根据关键词搜索知识库，返回匹配的知识条目"""
    if not KB_ROOT.exists():
        return []
    keywords = [w.lower() for w in query.split() if len(w) > 1]
    results = []
    for json_file in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            score = 0
            searchable = f"{data.get('title','')} {data.get('content','')} {' '.join(data.get('tags',[]))}".lower()
            for kw in keywords:
                if kw in searchable:
                    score += 1
            if score > 0:
                results.append({"score": score, "data": data, "path": str(json_file)})
        except Exception:
            continue
    results.sort(key=lambda x: x["score"], reverse=True)
    return [r["data"] for r in results[:limit]]


def add_knowledge(title: str, domain: str, content: str, tags: List[str],
                  source: str = "auto", confidence: str = "medium") -> str:
    """添加新的知识条目"""
    domain_dir = KB_ROOT / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c if c.isalnum() or c in "._-" else "_" for c in title[:50])
    filename = f"{timestamp}_{safe_title}.json"
    entry = {
        "title": title,
        "domain": domain,
        "content": content,
        "source": source,
        "created_at": datetime.now().strftime("%Y-%m-%d"),
        "tags": tags,
        "confidence": confidence
    }
    filepath = domain_dir / filename
    filepath.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(filepath)


def format_knowledge_for_prompt(entries: List[Dict[str, Any]]) -> str:
    """将知识条目格式化为可注入 prompt 的文本"""
    if not entries:
        return ""
    parts = ["## 项目知识库参考"]
    for e in entries:
        conf = {"high": "★★★", "medium": "★★", "low": "★"}.get(e.get("confidence", ""), "")
        parts.append(f"### {e['title']} [{conf}]")
        parts.append(e.get("content", "")[:500])
    return "\n\n".join(parts)


def get_knowledge_stats() -> Dict[str, int]:
    """获取知识库统计"""
    if not KB_ROOT.exists():
        return {}
    stats = {}
    for domain_dir in KB_ROOT.iterdir():
        if domain_dir.is_dir():
            count = len(list(domain_dir.glob("*.json")))
            if count > 0:
                stats[domain_dir.name] = count
    return stats