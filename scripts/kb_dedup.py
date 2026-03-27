"""知识库一次性去重：基于内容 hash，保留最新的一条"""
import json, hashlib
from pathlib import Path
from collections import defaultdict

KB_ROOT = Path(".ai-state/knowledge")
if not KB_ROOT.exists():
    print("知识库目录不存在")
    exit()

# 按内容 hash 分组
hash_groups = defaultdict(list)
total = 0

for f in KB_ROOT.rglob("*.json"):
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        content = data.get("content", "")
        title = data.get("title", "")
        # hash = 标题前30字 + 内容前200字
        fingerprint = f"{title[:30]}||{content[:200]}"
        h = hashlib.md5(fingerprint.encode()).hexdigest()
        hash_groups[h].append({
            "path": f,
            "title": title[:50],
            "mtime": f.stat().st_mtime,
            "source": data.get("source", "")
        })
        total += 1
    except:
        continue

# 删除重复（保留最新的）
deleted = 0
for h, entries in hash_groups.items():
    if len(entries) <= 1:
        continue
    # 按修改时间排序，保留最新
    entries.sort(key=lambda x: x["mtime"], reverse=True)
    for entry in entries[1:]:  # 跳过最新的
        try:
            entry["path"].unlink()
            deleted += 1
        except:
            pass
    if len(entries) > 2:
        print(f"  去重 {len(entries)-1} 条: {entries[0]['title']}")

duplicated_groups = sum(1 for entries in hash_groups.values() if len(entries) > 1)
print(f"\n总计: {total} 条")
print(f"重复组: {duplicated_groups}")
print(f"删除: {deleted} 条")
print(f"剩余: {total - deleted} 条")