"""
@description: 知识库管理 - 搜索、写入、检索项目级领域知识
@dependencies: json, pathlib, datetime, sentence_transformers (可选)
@last_modified: 2026-04-04
"""
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

KB_ROOT = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "knowledge"
EMBEDDINGS_PATH = KB_ROOT.parent / "kb_embeddings.npz"

# 尝试导入向量搜索依赖
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    _EMBED_MODEL = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    HAS_VECTOR = True
except ImportError:
    HAS_VECTOR = False
    print("[KB] sentence-transformers 未安装，向量搜索禁用")

# Domain 白名单
VALID_DOMAINS = {"competitors", "components", "standards", "lessons", "methodology"}

# Domain 映射表（非白名单 domain 自动映射）
DOMAIN_MAP = {
    "技术深挖": "components", "技术 深挖": "components",
    "标准法规": "standards", "标准 法规": "standards",
    "竞品深挖": "competitors", "竞品 深挖": "competitors",
    "technology": "components", "market": "competitors",
    "regulation": "standards", "insight": "lessons",
    "供应链": "components", "supply_chain": "components",
    "audio": "components", "optical": "components",
    "方法论": "methodology", "method": "methodology",
    "流程": "methodology", "process": "methodology",
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


# ============================================================
# 向量搜索功能
# ============================================================

def _build_embedding_index() -> dict:
    """构建/更新 embedding 索引

    Returns:
        dict with entries (list of {path, title, content}) and embeddings (np.array)
    """
    if not HAS_VECTOR:
        return {}

    entries = []
    texts = []

    for json_file in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            title = data.get("title", "")
            content = data.get("content", "")[:500]  # 截断
            text = f"{title}\n{content}"
            entries.append({
                "path": str(json_file),
                "title": title,
                "domain": data.get("domain", ""),
            })
            texts.append(text)
        except:
            continue

    if not texts:
        return {}

    embeddings = _EMBED_MODEL.encode(texts, convert_to_numpy=True)

    # 缓存到文件
    try:
        np.savez(EMBEDDINGS_PATH, embeddings=embeddings, entries=json.dumps(entries))
    except:
        pass

    return {"entries": entries, "embeddings": embeddings}


def _load_embedding_index() -> dict:
    """加载缓存的 embedding 索引"""
    if not HAS_VECTOR:
        return {}

    if EMBEDDINGS_PATH.exists():
        try:
            data = np.load(EMBEDDINGS_PATH, allow_pickle=True)
            return {
                "entries": json.loads(str(data["entries"])),
                "embeddings": data["embeddings"]
            }
        except:
            pass

    # 重新构建
    return _build_embedding_index()


def vector_search(query: str, limit: int = 10) -> list:
    """向量相似度搜索

    Args:
        query: 搜索查询
        limit: 返回数量限制

    Returns:
        匹配的条目路径列表
    """
    if not HAS_VECTOR:
        return []

    index = _load_embedding_index()
    if not index:
        return []

    entries = index.get("entries", [])
    embeddings = index.get("embeddings")

    if not entries or embeddings is None:
        return []

    # 编码查询
    query_embedding = _EMBED_MODEL.encode([query], convert_to_numpy=True)[0]

    # 计算余弦相似度
    similarities = np.dot(embeddings, query_embedding) / (
        np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_embedding)
    )

    # 排序取 top
    top_indices = np.argsort(similarities)[::-1][:limit]

    results = []
    for idx in top_indices:
        if similarities[idx] > 0.3:  # 相似度阈值
            results.append({
                "path": entries[idx]["path"],
                "title": entries[idx]["title"],
                "domain": entries[idx]["domain"],
                "score": float(similarities[idx]),
            })

    return results


def _keyword_search(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """关键词搜索（原有逻辑提取为独立函数）"""
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
    return [r["data"] for r in results[:limit]]


def search_knowledge(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """混合搜索：向量 + 关键词

    Args:
        query: 搜索查询
        limit: 返回数量限制

    Returns:
        匹配的知识条目列表
    """
    if not KB_ROOT.exists():
        return []

    results = []

    # 1. 向量搜索（如果可用）
    if HAS_VECTOR:
        vector_results = vector_search(query, limit=limit * 2)
        for vr in vector_results:
            try:
                data = json.loads(Path(vr["path"]).read_text(encoding="utf-8"))
                data["_vector_score"] = vr["score"]
                results.append({"score": vr["score"] * 10, "data": data, "path": Path(vr["path"])})
            except:
                continue

    # 2. 关键词搜索
    keyword_results = _keyword_search(query, limit=limit * 2)
    for kr in keyword_results:
        # 检查是否已在向量结果中
        already = any(r["data"].get("title") == kr.get("title") for r in results)
        if not already:
            # 找到对应的文件路径
            for f in KB_ROOT.rglob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if data.get("title") == kr.get("title"):
                        results.append({"score": 5, "data": kr, "path": f})
                        break
                except:
                    continue

    # 3. 排序去重
    results.sort(key=lambda x: x["score"], reverse=True)

    # 4. Track usage
    for r in results[:limit]:
        _track_knowledge_usage(r["path"])

    return [r["data"] for r in results[:limit]]


def add_knowledge(title: str, domain: str, content: str, tags: List[str],
                  source: str = "auto", confidence: str = "medium",
                  caller: str = "auto",
                  confidence_score: float = None,
                  uncertainty_range: str = None,
                  derived_from: str = None) -> Optional[str]:
    """添加新的知识条目

    Args:
        caller: 调用来源，影响 confidence 上限
            - "user_share" / "doc_import" / "user_upload": 允许 high
            - "self_learning" / "auto" / "llm_generate": 上限 medium
            - "product_decision": 允许 authoritative
        confidence_score: 数值置信度 (0.0-1.0)
        uncertainty_range: 不确定性区间 (如 "500-800万台/年")
        derived_from: 引用的上游条目 path 或 title（用于可信度传播）
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

                # === 知识升级机制：同产品名+不同时间 = 更新而非新增 ===
                if (title[:15].lower() in existing_data.get("title", "").lower() and
                    existing_data.get("created_at", "") != datetime.now().strftime("%Y-%m-%d")):
                    # Merge: 保留旧条目作为历史版本
                    history = existing_data.get("_history", [])
                    history.append({
                        "content": existing_data.get("content", ""),
                        "date": existing_data.get("created_at", ""),
                        "confidence": existing_data.get("confidence", "")
                    })
                    existing_data["_history"] = history[-5:]  # 最多保留 5 个历史版本
                    existing_data["content"] = content
                    existing_data["created_at"] = datetime.now().strftime("%Y-%m-%d")
                    existing_data["confidence"] = confidence
                    existing_data["tags"] = list(set(existing_data.get("tags", []) + tags))
                    existing_data["source"] = source
                    existing.write_text(json.dumps(existing_data, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(f"[KB] 升级条目: {title[:40]}（保留 {len(history)} 个历史版本）")
                    return str(existing)
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
    # === 不确定性量化 ===
    if confidence_score is not None:
        entry["confidence_score"] = confidence_score  # 0.0-1.0
    if uncertainty_range is not None:
        entry["uncertainty_range"] = uncertainty_range  # "500-800万台/年"
    # === 可信度传播：记录上游条目 ===
    if derived_from is not None:
        entry["derived_from"] = derived_from
    # === 竞品动态时间线：competitors 域自动添加 observed_at ===
    if domain == "competitors":
        entry["observed_at"] = datetime.now().strftime("%Y-%m-%d")
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


def format_knowledge_for_answer(entries: List[Dict[str, Any]]) -> str:
    """格式化知识条目用于回答（含置信度和溯源）

    用于最终输出给用户时，显示置信度、时间戳和来源
    """
    if not entries:
        return ""
    parts = []
    for e in entries:
        conf = e.get("confidence", "medium")
        created = e.get("created_at", "?")
        source = e.get("source", "auto")
        conf_icon = {"authoritative": "⭐⭐⭐", "high": "⭐⭐", "medium": "⭐", "low": "⚠️"}.get(conf, "⭐")

        parts.append(f"{conf_icon} {e.get('title', '')} (📅{created} | 🔗{source})")
        parts.append(f"  {e.get('content', '')[:300]}")

        # 检查是否有矛盾标记
        if "needs_reconciliation" in e.get("tags", []):
            parts.append(f"  ⚠️ 此数据存在矛盾，建议交叉验证")

    return "\n".join(parts)


def detect_contradictions_in_results(results: list) -> str:
    """检测搜索结果中的矛盾数据

    简单规则：同一实体出现在多个条目中，如果数值差异超过 50% 则标记矛盾
    """
    import re
    if len(results) < 2:
        return ""

    # 按实体分组检测数值矛盾
    entities = {}
    for r in results:
        title = r.get("title", "")
        content = r.get("content", "")
        # 提取数值型数据（单位：万台/nits/mW/USD/元/克/g/mm/小时/h）
        numbers = re.findall(r'(\d+(?:\.\d+)?)\s*(万台|nits|mW|USD|元|克|g|mm|小时|h)', content)
        for num, unit in numbers:
            key = f"{title[:10]}_{unit}"
            if key not in entities:
                entities[key] = []
            entities[key].append({
                "value": float(num),
                "source": title,
                "confidence": r.get("confidence", "")
            })

    contradictions = []
    for key, values in entities.items():
        if len(values) >= 2:
            vals = [v["value"] for v in values]
            if max(vals) / max(min(vals), 0.01) > 1.5:  # 差异超过 50%
                contradictions.append({
                    "key": key,
                    "values": values,
                })

    if contradictions:
        lines = ["⚠️ KB 中存在矛盾信息:"]
        for c in contradictions[:3]:  # 只显示前 3 个
            for v in c["values"]:
                lines.append(f"  - {v['source']}: {v['value']} ({v['confidence']})")
        return "\n".join(lines)
    return ""


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