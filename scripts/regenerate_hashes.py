"""
@description: 重新生成架构文件哈希快照，修改配置文件后运行
@dependencies: hashlib, json, pathlib
@last_modified: 2026-03-20
"""
import hashlib
import json
from pathlib import Path


def regenerate():
    root = Path(__file__).parent.parent
    hashes = {}
    for md_file in (root / ".ai-architecture").glob("*.md"):
        hashes[md_file.name] = hashlib.sha256(md_file.read_bytes()).hexdigest()
    for yaml_file in (root / "src" / "config").glob("*.yaml"):
        hashes[yaml_file.name] = hashlib.sha256(yaml_file.read_bytes()).hexdigest()
    out = root / ".ai-state" / "snapshot_hashes.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(hashes, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[Hash] 已更新 {len(hashes)} 个文件的哈希值")


if __name__ == "__main__":
    regenerate()