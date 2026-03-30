"""
@description: 知识库管理 - 搜索、写入、检索项目级领域知识
@dependencies: json, pathlib, datetime
@last_modified: 2026-03-23
"""
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

KB_ROOT = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "knowledge"

# Domain 白名单
VALID_DOMAINS = {"competitors", "components", "standards", "lessons"}

# Domain 映射表（非白名单 domain 自动映射）
DOMAIN_MAP = {
    "技术深挖": "components", "技术 深挖": "components",
    "标准法规": "standards", "标准 法规": "standards",
    "竞品深挖": "competitors", "竞品 深挖": "competitors",
    "technology": "components", "market": "competitors",
    "regulation": "standards", "insight": "lessons",
    "供应链": "components", "supply_chain": "components",
    "audio": "components", "optical": "components",
}


def _normalize_domain(domain: str) -> str:
    """强制 domain 白名单，非白名单自动映射"""
    if domain in VALID_DOMAINS:
        return domain
    mapped = DOMAIN_MAP.get(domain)
    if mapped:
        return mapped
    # 默认归入 lessons
    return "lessons"


def _track_knowledge_usage(file_path: Path):
    """Track knowledge entry usage count"""
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))

        # Increment usage count
        data["_usage_count"] = data.get("_usage_count", 0) + 1
        data["_last_used"] = datetime.now().isoformat()

        # Record first use time
        if "_first_used" not in data:
            data["_first_used"] = datetime.now().isoformat()

        file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except:
        pass


def search_knowledge(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """根据关键词搜索知识库，返回匹配的知识条目（中文友好）"""
    import re
    if not KB_ROOT.exists():
        return []
    # 中文友好：提取2字以上的关键词片段
    keywords = []
    for word in query.split():
        if len(word) > 1:
            keywords.append(word.lower())

    # 额外：提取英文型号（如 AR1, AR2, BES2800, QCC 等）
    model_patterns = re.findall(r'[A-Z]{1,4}\d+[A-Z]*|[A-Z]+-\d+|[A-Z]{2,}\d*', query.upper())
    for m in model_patterns:
        if len(m) > 1:
            keywords.append(m.lower())

    # 额外：对中文按常见领域关键词匹配
    domain_keywords = ["头盔", "骑行", "灯光", "充电", "蓝牙", "通讯", "对讲", "安全",
                       "传感器", "LED", "设计", "竞品", "标准", "认证", "市场",
                       "智能", "通讯", "系统", "方案", "产品", "价格", "技术",
                       "芯片", "高通", "AR1", "AR2", "SoC", "骁龙"]
    for dk in domain_keywords:
        if dk in query or dk.lower() in query.lower():
            keywords.append(dk.lower())

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
                # 推测性内容降权
                if "speculative" in data.get("tags", []):
                    score -= 3
                results.append({"score": score, "data": data, "path": json_file})
        except Exception:
            continue
    results.sort(key=lambda x: x["score"], reverse=True)

    # Track usage for returned results
    for r in results[:limit]:
        _track_knowledge_usage(r["path"])

    return [r["data"] for r in results[:limit]]


def add_knowledge(title: str, domain: str, content: str, tags: List[str],
                  source: str = "auto", confidence: str = "medium",
                  caller: str = "auto") -> Optional[str]:
    """添加新的知识条目

    Args:
        caller: 调用来源，影响 confidence 上限
            - "user_share" / "doc_import" / "user_upload": 允许 high
            - "self_learning" / "auto" / "llm_generate": 上限 medium
            - "product_decision": 允许 authoritative
    """
    import random

    # === Guardrail 1: 内容最小长度 ===
    if len(content.strip()) < 30:
        print(f"[KB_GUARD] 拒绝入库: content 太短 ({len(content.strip())} 字) — {title[:40]}")
        return None

    # === Guardrail 2: confidence 上限 ===
    TRUSTED_CALLERS = {"user_share", "doc_import", "user_upload", "product_decision",
                       "user_feedback_analysis", "critic_rule"}
    if caller not in TRUSTED_CALLERS:
        if confidence == "high":
            confidence = "medium"
            print(f"[KB_GUARD] confidence 降级: {caller} 不允许标 high — {title[:40]}")
        if confidence == "authoritative":
            confidence = "medium"
            print(f"[KB_GUARD] confidence 降级: {caller} 不允许标 authoritative — {title[:40]}")

    # === 入库前去重：同 domain 下相同内容不重复入库 ===
    import hashlib
    domain = _normalize_domain(domain)
    domain_dir = KB_ROOT / domain
    fingerprint = f"{title[:30]}||{content[:200]}"
    content_hash = hashlib.md5(fingerprint.encode()).hexdigest()
    if domain_dir.exists():
        for existing in domain_dir.glob("*.json"):
            try:
                existing_data = json.loads(existing.read_text(encoding="utf-8"))
                existing_fp = f"{existing_data.get('title', '')[:30]}||{existing_data.get('content', '')[:200]}"
                if hashlib.md5(existing_fp.encode()).hexdigest() == content_hash:
                    return str(existing)  # 已存在，返回现有路径
            except:
                continue

    # 强制 domain 白名单
    domain_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rand_suffix = random.randint(100, 999)
    safe_title = "".join(c for c in title[:30] if c.isalnum() or c in "_ -").strip()[:30]
    filename = f"{timestamp}_{rand_suffix}_{safe_title}.json"
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


def add_report(title: str, domain: str, content: str, tags: List[str] = None,
               source: str = "", confidence: str = "high") -> str:
    """存储完整研究报告（不截断）"""
    import random
    # 强制 domain 白名单
    domain = _normalize_domain(domain)
    domain_dir = KB_ROOT / domain
    domain_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rand_suffix = f"{random.randint(100,999)}"
    safe_title = "".join(c for c in title[:30] if c.isalnum() or c in "_ -").strip()[:30]
    filename = f"REPORT_{timestamp}_{rand_suffix}_{safe_title}.json"

    entry = {
        "title": title,
        "content": content,  # 全文，不截断
        "domain": domain,
        "tags": tags or [],
        "source": source,
        "confidence": confidence,
        "created": datetime.now().isoformat(),
        "type": "report",  # 区分报告和条目
        "word_count": len(content)
    }

    filepath = domain_dir / filename
    filepath.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(filepath)