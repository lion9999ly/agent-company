"""
Phase 0.2 — 无数据条目清洗脚本
运行方式: python scripts/kb_cleanup_nodata.py [--dry-run] [--report-only]

策略（铁律：不删除任何条目）:
  1. content < 50 字 且 confidence != "authoritative" 的条目为"无数据条目"
  2. 有价值标题（含芯片型号、标准编号、品牌名、具体技术术语）→ confidence 降为 low，加 tag pending_research，加入研究队列
  3. 标题也泛泛的 → confidence 降为 low，加 tag needs_content
  4. 已有 anchor/internal 标签的不动
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
KB_ROOT = ROOT / ".ai-state" / "knowledge"
RESEARCH_QUEUE = ROOT / ".ai-state" / "auto_research_queue.json"
REPORT_PATH = ROOT / ".ai-state" / "kb_cleanup_report_20260326.json"


# === 判断标题是否有价值 ===
# 包含具体实体（芯片型号、品牌、标准编号等）的标题值得保留并加入研究队列

# 芯片/型号模式
MODEL_PATTERNS = [
    r'[A-Z]{2,5}\d{3,}',          # QCC5171, BES2800, IMX678
    r'[A-Z]+\d+[A-Z]+\d*',        # AR1, AR2, STM32
    r'Snapdragon\s+\w+',          # Snapdragon AR1
    r'骁龙',
    r'BCM\d+', r'ESP32', r'nRF\d+', r'RTL\d+',
]

# 品牌名
BRAND_NAMES = [
    "Qualcomm", "高通", "Sony", "索尼", "Cardo", "Sena", "Reso",
    "Shoei", "Arai", "AGV", "Forcite", "CrossHelmet", "EyeLights",
    "JBD", "Micro LED", "MicroLED", "OLED", "OLEDoS",
    "BES", "恒玄", "Bestechnic", "Realtek", "瑞昱",
    "Bosch", "博世", "InvenSense", "ST", "意法",
    "TI", "Texas Instruments", "Nordic", "Dialog",
    "Tavily", "Gemini", "Azure",  # 这些不算有价值标题
    "雷鸟", "RayNeo", "Rokid", "Livall", "Lumos",
    "莫界", "光粒", "灵犀微光", "亮亮视野",
    "歌尔", "GoerTek", "立讯", "Luxshare",
]

# 标准/认证编号
STANDARD_PATTERNS = [
    r'ECE\s*22', r'DOT\s+FMVSS', r'3C', r'UN\s*38',
    r'IP\d{2}', r'ISO\s*\d+', r'IEC\s*\d+', r'GB\s*\d+',
    r'FCC', r'CE', r'SAR', r'EMC', r'REACH', r'RoHS',
]

# 具体技术术语（比泛泛的"技术方案"有价值）
TECH_TERMS = [
    "光波导", "衍射", "自由曲面", "Free Form", "BirdBath",
    "Mesh 2.0", "DMC", "aptX", "LC3", "LE Audio",
    "IMU", "六轴", "加速度计", "陀螺仪", "气压计",
    "MEMS", "麦克风阵列", "ANC", "主动降噪",
    "USB-C", "PD", "无线充电", "Qi",
    "PCB", "FPC", "柔性电路",
    "散热", "热管", "石墨烯", "导热",
    "注塑", "碳纤维", "玻纤", "ABS", "PC",
    "Mesh", "BLE 5", "蓝牙5", "Wi-Fi",
    "4K", "1080p", "FHD", "720p",
    "nits", "cd/m2", "FOV",
]


def has_valuable_title(title: str, content: str = "") -> bool:
    """判断标题+内容前100字是否包含具体实体，值得保留并研究"""
    check_text = f"{title} {content[:100]}".upper()
    check_text_original = f"{title} {content[:100]}"

    # 芯片型号
    for pattern in MODEL_PATTERNS:
        if re.search(pattern, check_text_original, re.IGNORECASE):
            return True

    # 品牌名（排除太泛的）
    skip_brands = {"Tavily", "Gemini", "Azure"}
    for brand in BRAND_NAMES:
        if brand in skip_brands:
            continue
        if brand.lower() in check_text_original.lower():
            return True

    # 标准编号
    for pattern in STANDARD_PATTERNS:
        if re.search(pattern, check_text_original, re.IGNORECASE):
            return True

    # 具体技术术语
    for term in TECH_TERMS:
        if term.lower() in check_text_original.lower():
            return True

    return False


def scan_nodata_entries():
    """扫描所有无数据条目"""
    results = {
        "valuable": [],      # 有价值标题 → pending_research
        "generic": [],       # 泛泛标题 → needs_content
        "skipped_anchor": [],  # 跳过的 anchor/internal 条目
        "skipped_ok": [],    # content >= 50 字，不需要处理
    }

    if not KB_ROOT.exists():
        print("[ERROR] 知识库目录不存在")
        return results

    total = 0
    for json_file in KB_ROOT.rglob("*.json"):
        total += 1
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [SKIP] 无法读取: {json_file.name} ({e})")
            continue

        title = data.get("title", "")
        content = data.get("content", "")
        tags = data.get("tags", [])
        confidence = data.get("confidence", "medium")
        content_len = len(content.strip())

        # 跳过 anchor/internal 条目
        if "anchor" in tags or "internal" in tags:
            results["skipped_anchor"].append({
                "file": str(json_file),
                "title": title,
                "reason": "anchor/internal 标签，不动"
            })
            continue

        # 跳过 authoritative confidence
        if confidence == "authoritative":
            results["skipped_ok"].append({
                "file": str(json_file),
                "title": title,
                "reason": "authoritative confidence"
            })
            continue

        # 跳过内容足够的条目
        if content_len >= 50:
            results["skipped_ok"].append({
                "file": str(json_file),
                "title": title,
                "content_len": content_len
            })
            continue

        # 无数据条目：分类
        entry_info = {
            "file": str(json_file),
            "title": title,
            "content_preview": content[:80] if content else "(空)",
            "content_len": content_len,
            "domain": data.get("domain", "unknown"),
            "confidence": confidence,
            "tags": tags,
            "source": data.get("source", ""),
        }

        if has_valuable_title(title, content):
            entry_info["action"] = "pending_research"
            results["valuable"].append(entry_info)
        else:
            entry_info["action"] = "needs_content"
            results["generic"].append(entry_info)

    print(f"\n[扫描完成] 知识库总量: {total}")
    print(f"  无数据条目: {len(results['valuable']) + len(results['generic'])}")
    print(f"    有价值标题 → pending_research: {len(results['valuable'])}")
    print(f"    泛泛标题 → needs_content: {len(results['generic'])}")
    print(f"  跳过 (anchor/internal): {len(results['skipped_anchor'])}")
    print(f"  跳过 (内容充足): {len(results['skipped_ok'])}")

    return results


def execute_cleanup(results: dict, dry_run: bool = False):
    """执行清洗"""
    modified = 0
    research_queue_additions = []

    # 处理有价值标题的条目
    for entry in results["valuable"]:
        filepath = Path(entry["file"])
        if not filepath.exists():
            continue

        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))

            changed = False

            # 降级 confidence
            if data.get("confidence") != "low":
                data["confidence"] = "low"
                changed = True

            # 加 pending_research tag
            tags = data.get("tags", [])
            if "pending_research" not in tags:
                tags.append("pending_research")
                data["tags"] = tags
                changed = True

            # 加 nodata_cleanup 标记
            if "nodata_cleanup" not in tags:
                tags.append("nodata_cleanup")
                data["tags"] = tags
                changed = True

            if changed:
                if not dry_run:
                    filepath.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                modified += 1

                # 加入研究队列
                research_queue_additions.append({
                    "source": "kb_cleanup_nodata",
                    "title": entry["title"],
                    "domain": entry["domain"],
                    "advice": f"知识库条目「{entry['title']}」内容不足（{entry['content_len']}字），需要补充具体数据",
                    "created": datetime.now().isoformat()
                })

        except Exception as e:
            print(f"  [ERROR] {filepath.name}: {e}")

    # 处理泛泛标题的条目
    for entry in results["generic"]:
        filepath = Path(entry["file"])
        if not filepath.exists():
            continue

        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))

            changed = False

            # 降级 confidence
            if data.get("confidence") != "low":
                data["confidence"] = "low"
                changed = True

            # 加 needs_content tag
            tags = data.get("tags", [])
            if "needs_content" not in tags:
                tags.append("needs_content")
                data["tags"] = tags
                changed = True

            if "nodata_cleanup" not in tags:
                tags.append("nodata_cleanup")
                data["tags"] = tags
                changed = True

            if changed:
                if not dry_run:
                    filepath.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                modified += 1

        except Exception as e:
            print(f"  [ERROR] {filepath.name}: {e}")

    # 写入研究队列
    if research_queue_additions and not dry_run:
        existing = []
        if RESEARCH_QUEUE.exists():
            try:
                existing = json.loads(RESEARCH_QUEUE.read_text(encoding="utf-8"))
            except Exception:
                existing = []

        # 去重：不重复添加同标题的条目
        existing_titles = {item.get("title", "") for item in existing}
        new_items = [item for item in research_queue_additions
                     if item["title"] not in existing_titles]

        existing.extend(new_items)
        # 保留最近 50 条
        existing = existing[-50:]
        RESEARCH_QUEUE.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"\n[研究队列] 新增 {len(new_items)} 条待研究主题")

    return modified


def save_report(results: dict, modified: int):
    """保存清洗报告"""
    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_nodata": len(results["valuable"]) + len(results["generic"]),
            "valuable_pending_research": len(results["valuable"]),
            "generic_needs_content": len(results["generic"]),
            "skipped_anchor": len(results["skipped_anchor"]),
            "modified": modified,
        },
        "valuable_entries": [
            {"title": e["title"], "domain": e["domain"], "content_len": e["content_len"]}
            for e in results["valuable"]
        ],
        "generic_entries": [
            {"title": e["title"], "domain": e["domain"], "content_len": e["content_len"]}
            for e in results["generic"]
        ],
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n[报告] 已保存到: {REPORT_PATH}")


def main():
    dry_run = "--dry-run" in sys.argv
    report_only = "--report-only" in sys.argv

    print("=" * 60)
    print("[Phase 0.2] 知识库无数据条目清洗")
    print(f"  模式: {'DRY RUN（不修改文件）' if dry_run else 'REPORT ONLY（仅扫描）' if report_only else 'EXECUTE（将修改文件）'}")
    print(f"  知识库: {KB_ROOT}")
    print("=" * 60)

    # Step 1: 扫描
    results = scan_nodata_entries()

    if report_only:
        # 打印详情
        print("\n" + "=" * 60)
        print("[有价值标题 → pending_research]")
        for i, e in enumerate(results["valuable"][:20], 1):
            print(f"  {i}. [{e['domain']}] {e['title']}")
            print(f"     内容: {e['content_preview']}")

        print(f"\n[泛泛标题 → needs_content]")
        for i, e in enumerate(results["generic"][:20], 1):
            print(f"  {i}. [{e['domain']}] {e['title']}")
            print(f"     内容: {e['content_preview']}")

        save_report(results, 0)
        print("\n[完成] 报告模式，未修改任何文件")
        return

    # Step 2: 执行清洗
    print("\n" + "-" * 60)
    modified = execute_cleanup(results, dry_run=dry_run)

    print(f"\n{'[DRY RUN] 将会修改' if dry_run else '[完成] 已修改'} {modified} 个文件")

    # Step 3: 保存报告
    save_report(results, modified)

    # Step 4: 摘要
    print("\n" + "=" * 60)
    print("[摘要]")
    print(f"  无数据条目总数: {len(results['valuable']) + len(results['generic'])}")
    print(f"  有价值 → pending_research: {len(results['valuable'])}")
    print(f"  泛泛 → needs_content: {len(results['generic'])}")
    print(f"  修改文件数: {modified}")
    if not dry_run:
        print(f"  研究队列已更新: {RESEARCH_QUEUE}")
        print(f"  清洗报告: {REPORT_PATH}")
    print("=" * 60)

    # 提示下一步
    if dry_run:
        print("\n[下一步] 确认无误后，去掉 --dry-run 参数正式执行：")
        print(f"  python scripts/kb_cleanup_nodata.py")


if __name__ == "__main__":
    main()
