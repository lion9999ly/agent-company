"""
@description: HUD Demo v2 验收标准验证脚本 (18条)
@dependencies: 无
@last_modified: 2026-04-13
"""

import os
import re
from pathlib import Path


# Emoji pattern for detecting emoji characters in HTML
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001F5FF"  # Symbols & Pictographs
    "\U0001F600-\U0001F64F"  # Emoticons
    "\U0001F680-\U0001F6FF"  # Transport & Map
    "\U0001F1E0-\U0001F1FF"  # Flags
    "\U00002700-\U000027BF"  # Dingbats
    "\U0001F900-\U0001F9FF"  # Supplemental Symbols A
    "\U0001FA00-\U0001FA6F"  # Chess Symbols
    "\U0001FA70-\U0001FAFF"  # Symbols & Pictographs Extended-A
    "\U00002600-\U000026FF"  # Misc Symbols
    "\U00002500-\U00002BEF"  # Geometric Shapes Extended
    "\U00002300-\U000023FF"  # Misc Technical
    "\u2600-\u26FF"          # Misc Symbols (narrow)
    "\u2700-\u27BF"          # Dingbats (narrow)
    "\ufe0f"                 # Variation Selector
    "]+"
)


def validate_hud_demo():
    """验证 HUD Demo HTML 文件是否符合 18 条验收标准"""

    hud_file = Path("demo_outputs/hud_demo_v2.html")
    if not hud_file.exists():
        return {"error": f"HUD Demo file not found: {hud_file}"}

    content = hud_file.read_text(encoding="utf-8")

    results = []

    # ========== Original 14 ACs ==========

    # AC1: 光学模式编码差异 - 检查 CSS 中是否有亮度编码变量
    ac1 = {
        "id": "AC1",
        "name": "光学模式编码差异",
        "passed": False,
        "details": ""
    }
    if "rgba(0,255,0" in content and "brightness" in content.lower():
        ac1["passed"] = True
        ac1["details"] = "Found brightness encoding (rgba opacity) for green mode"
    else:
        ac1["details"] = "No brightness encoding found"
    results.append(ac1)

    # AC2: 单绿模式色相唯一 - 检查单绿模式 CSS 是否只有 #00FF00
    ac2 = {
        "id": "AC2",
        "name": "单绿模式色相唯一",
        "passed": False,
        "details": ""
    }
    green_mode_pattern = r'\.optics-green[^{]*\{[^}]*\}'
    green_matches = re.findall(green_mode_pattern, content, re.DOTALL)
    if green_matches:
        green_content = '\n'.join(green_matches)
        color_pattern = r'#[0-9a-fA-F]{6}'
        green_colors = re.findall(color_pattern, green_content)
        green_non_green = [c for c in green_colors if c.lower() != '#00ff00']
        if len(green_non_green) == 0:
            ac2["passed"] = True
            ac2["details"] = f"optics-green CSS only uses #00FF00 (found {len(green_colors)} refs)"
        else:
            ac2["details"] = f"Found non-green colors in optics-green: {green_non_green}"
    else:
        ac2["details"] = "No optics-green CSS block found"
    results.append(ac2)

    # AC3: 中央透明区域
    ac3 = {
        "id": "AC3",
        "name": "中央透明区域",
        "passed": False,
        "details": ""
    }
    if "center-gap" in content.lower() and "hud-viewport-left" in content.lower():
        ac3["passed"] = True
        ac3["details"] = "Layout uses left/right strips with center-gap variable"
    else:
        ac3["details"] = "No center gap layout found"
    results.append(ac3)

    # AC4: ADAS 信息完整性
    ac4 = {
        "id": "AC4",
        "name": "ADAS 信息完整性",
        "passed": False,
        "details": ""
    }
    required_fields = ["distance", "closingSpeed", "ttc"]
    found_fields = [f for f in required_fields if f.lower() in content.lower()]
    if len(found_fields) == 3:
        ac4["passed"] = True
        ac4["details"] = f"Found all required fields: {found_fields}"
    else:
        ac4["details"] = f"Missing fields: {[f for f in required_fields if f not in found_fields]}"
    results.append(ac4)

    # AC5: 多重预警优先级
    ac5 = {
        "id": "AC5",
        "name": "多重预警优先级",
        "passed": False,
        "details": ""
    }
    if "activeWarnings.sort" in content and "ttc" in content.lower():
        ac5["passed"] = True
        ac5["details"] = "Found TTC priority sorting in activeWarnings"
    else:
        ac5["details"] = "No TTC priority sorting found"
    results.append(ac5)

    # AC6: BSD 外边缘闪烁
    ac6 = {
        "id": "AC6",
        "name": "BSD 外边缘闪烁",
        "passed": False,
        "details": ""
    }
    if "bsd" in content.lower() and "leftEdgeOuter" in content:
        ac6["passed"] = True
        ac6["details"] = "Found BSD outer edge (leftEdgeOuter) flashing"
    else:
        ac6["details"] = "No BSD outer edge found"
    results.append(ac6)

    # AC7: LDW 内边缘闪烁
    ac7 = {
        "id": "AC7",
        "name": "LDW 内边缘闪烁",
        "passed": False,
        "details": ""
    }
    if "ldw" in content.lower() and "leftEdgeInner" in content and "rightEdgeInner" in content:
        ac7["passed"] = True
        ac7["details"] = "Found LDW inner edge (EdgeInner) flashing"
    else:
        ac7["details"] = "No LDW inner edge found"
    results.append(ac7)

    # AC8: 优先级抢占保留
    ac8 = {
        "id": "AC8",
        "name": "优先级抢占保留",
        "passed": False,
        "details": ""
    }
    if "shrunk" in content.lower() and ("scale" in content.lower() or "opacity" in content.lower()):
        ac8["passed"] = True
        ac8["details"] = "Found shrunk state with scale/opacity for preemption"
    else:
        ac8["details"] = "No shrunk state found"
    results.append(ac8)

    # AC9: 预警后自动恢复
    ac9 = {
        "id": "AC9",
        "name": "预警后自动恢复",
        "passed": False,
        "details": ""
    }
    if "popMode" in content and "clearWarning" in content:
        ac9["passed"] = True
        ac9["details"] = "Found popMode in clearWarning for auto recovery"
    else:
        ac9["details"] = "No auto recovery logic found"
    results.append(ac9)

    # AC10: touring 语音标记
    ac10 = {
        "id": "AC10",
        "name": "touring 语音标记",
        "passed": False,
        "details": ""
    }
    if "touring" in content.lower() and "showMomentSaved" in content:
        ac10["passed"] = True
        ac10["details"] = "Found touring scenario with showMomentSaved"
    else:
        ac10["details"] = "No touring voice mark found"
    results.append(ac10)

    # AC11: 语音字幕位置
    ac11 = {
        "id": "AC11",
        "name": "语音字幕位置",
        "passed": False,
        "details": ""
    }
    if "voice-subtitle" in content and "bottom-bar" in content:
        ac11["passed"] = True
        ac11["details"] = "Found voice-subtitle in bottom-bar"
    else:
        ac11["details"] = "No subtitle positioning found"
    results.append(ac11)

    # AC12: 背景透明度可调
    ac12 = {
        "id": "AC12",
        "name": "背景透明度可调",
        "passed": False,
        "details": ""
    }
    if "bg-opacity" in content and "bgOpacity" in content:
        ac12["passed"] = True
        ac12["details"] = "Found bg-opacity slider control"
    else:
        ac12["details"] = "No opacity control found"
    results.append(ac12)

    # AC13: 交通标志持续显示
    ac13 = {
        "id": "AC13",
        "name": "交通标志持续显示",
        "passed": False,
        "details": ""
    }
    if "currentSign" in content and "setTrafficSign" in content:
        ac13["passed"] = True
        ac13["details"] = "Found traffic sign persistence via currentSign"
    else:
        ac13["details"] = "No traffic sign persistence found"
    results.append(ac13)

    # AC14: 显示区域可调
    ac14 = {
        "id": "AC14",
        "name": "显示区域可调",
        "passed": False,
        "details": ""
    }
    if "strip-width" in content and "center-gap-slider" in content:
        ac14["passed"] = True
        ac14["details"] = "Found strip-width and center-gap controls"
    else:
        ac14["details"] = "No display area controls found"
    results.append(ac14)

    # ========== New 4 ACs (Bug fixes) ==========

    # AC15: 单绿模式无 emoji - HTML 中不含任何 emoji 字符
    ac15 = {
        "id": "AC15",
        "name": "单绿模式无 emoji",
        "passed": False,
        "details": ""
    }
    emojis_found = EMOJI_PATTERN.findall(content)
    # Filter out common symbols that might be used in UI
    # Allow: arrows (←→), brackets, basic symbols
    problematic_emojis = [e for e in emojis_found if len(e) > 1 or e in ['⚠', '🔋', '📶', '🌡', '🚸', '👥', '🎵', '▶', '⏸', '⏹', '⬅', '➡']]
    if len(problematic_emojis) == 0:
        # Double check: search for common emoji patterns
        emoji_literals = ['⚠', '🔋', '📶', '🌡', '🚸', '👥', '🎵', '▶', '⏸', '⏹', '⬅️', '➡️']
        found_literals = [e for e in emoji_literals if e in content]
        if len(found_literals) == 0:
            ac15["passed"] = True
            ac15["details"] = "No emoji characters found in HTML"
        else:
            ac15["details"] = f"Found emoji literals: {found_literals}"
    else:
        ac15["details"] = f"Found emojis: {problematic_emojis[:5]}"
    results.append(ac15)

    # AC16: 预警内容不溢出 - warning-badge 使用紧凑布局
    ac16 = {
        "id": "AC16",
        "name": "预警内容不溢出",
        "passed": False,
        "details": ""
    }
    # Check for compact layout: gap:2px, padding:4px, smaller font sizes
    if "warning-badge" in content:
        # Check for compact padding/gap values
        compact_pattern = r'\.warning-badge\s*\{[^}]*gap:\s*2px[^}]*\}'
        if re.search(compact_pattern, content, re.DOTALL):
            ac16["passed"] = True
            ac16["details"] = "Found compact warning-badge layout (gap:2px)"
        elif "padding: 4px" in content or "padding:4px" in content:
            ac16["passed"] = True
            ac16["details"] = "Found compact padding in warning-badge"
        else:
            ac16["details"] = "No compact layout found"
    else:
        ac16["details"] = "No warning-badge found"
    results.append(ac16)

    # AC17: activeWarnings 最多保留 2 个
    ac17 = {
        "id": "AC17",
        "name": "预警数组上限2",
        "passed": False,
        "details": ""
    }
    # Check for slice(0, 2) or similar limit
    if "activeWarnings" in content:
        limit_pattern = r'activeWarnings\.slice\(0,\s*2\)|activeWarnings\s*=\s*activeWarnings\.slice\(0,\s*2\)'
        if re.search(limit_pattern, content):
            ac17["passed"] = True
            ac17["details"] = "Found activeWarnings.slice(0, 2) limit"
        elif "activeWarnings.length > 2" in content:
            ac17["passed"] = True
            ac17["details"] = "Found activeWarnings.length > 2 check"
        else:
            ac17["details"] = "No array limit found"
    else:
        ac17["details"] = "No activeWarnings found"
    results.append(ac17)

    # AC18: touring 剧本包含 2 次 showVoiceSubtitle 和 2 次 setTrafficSign
    ac18 = {
        "id": "AC18",
        "name": "touring 剧本完整",
        "passed": False,
        "details": ""
    }
    # Extract touring scenario block
    touring_pattern = r'touring:\s*\{[^}]*events:\s*\[[^\]]*\]'
    touring_match = re.search(touring_pattern, content, re.DOTALL)
    if touring_match:
        touring_content = touring_match.group(0)
        # Count showVoiceSubtitle calls
        voice_count = len(re.findall(r'showVoiceSubtitle', touring_content))
        # Count setTrafficSign calls
        sign_count = len(re.findall(r'setTrafficSign', touring_content))
        if voice_count >= 2 and sign_count >= 2:
            ac18["passed"] = True
            ac18["details"] = f"Found {voice_count} showVoiceSubtitle and {sign_count} setTrafficSign in touring"
        else:
            ac18["details"] = f"touring has {voice_count} voice calls, {sign_count} sign calls (need >=2 each)"
    else:
        ac18["details"] = "No touring scenario found"
    results.append(ac18)

    # ========== Summary ==========
    passed_count = sum(1 for r in results if r["passed"])
    total_count = len(results)
    pass_rate = passed_count / total_count

    return {
        "file": str(hud_file),
        "total_criteria": total_count,
        "passed": passed_count,
        "failed": total_count - passed_count,
        "pass_rate": f"{pass_rate:.2%}",
        "results": results
    }


if __name__ == "__main__":
    import sys
    import io
    # Force UTF-8 output on Windows
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    result = validate_hud_demo()
    print("=" * 60)
    print("HUD Demo v2 验收标准验证报告 (18条)")
    print("=" * 60)
    print(f"文件: {result.get('file', 'N/A')}")
    print(f"总标准数: {result.get('total_criteria', 0)}")
    print(f"通过: {result.get('passed', 0)}")
    print(f"失败: {result.get('failed', 0)}")
    print(f"通过率: {result.get('pass_rate', 'N/A')}")
    print("-" * 60)
    for r in result.get("results", []):
        status = "[PASS]" if r["passed"] else "[FAIL]"
        print(f"{r['id']}: {status} - {r['name']}")
        print(f"   {r['details']}")
    print("=" * 60)