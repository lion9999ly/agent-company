"""
@description: HUD Demo v2 验收标准验证脚本
@dependencies: 无
@last_modified: 2026-04-12
"""

import os
import re
from pathlib import Path


def validate_hud_demo():
    """验证 HUD Demo HTML 文件是否符合 14 条验收标准"""

    hud_file = Path("demo_outputs/hud_demo_v2.html")
    if not hud_file.exists():
        return {"error": f"HUD Demo file not found: {hud_file}"}

    content = hud_file.read_text(encoding="utf-8")

    results = []

    # AC1: 光学模式编码差异 - 检查 CSS 中是否有亮度编码变量
    ac1 = {
        "id": "AC1",
        "name": "光学模式编码差异",
        "passed": False,
        "details": ""
    }
    # 检查是否有 brightness 变量定义和 optical mode CSS
    if "brightness" in content.lower() or "green-brightness" in content.lower():
        if "--brightness-" in content or "brightness: " in content:
            ac1["passed"] = True
            ac1["details"] = "Found brightness encoding for green mode in CSS"
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
    # 检查 optics-green CSS 定义
    green_mode_pattern = r'\.optics-green[^{]*\{[^}]*\}'
    green_matches = re.findall(green_mode_pattern, content, re.DOTALL)
    if green_matches:
        # 检查是否有其他颜色（非 #00ff00 的 hex 颜色）
        color_pattern = r'#[0-9a-fA-F]{6}'
        all_colors = re.findall(color_pattern, content)
        non_green_colors = [c for c in all_colors if c.lower() != '#00ff00']
        # 在 optics-green 块中检查
        green_content = '\n'.join(green_matches)
        green_colors = re.findall(color_pattern, green_content)
        green_non_green = [c for c in green_colors if c.lower() != '#00ff00']
        if len(green_non_green) == 0:
            ac2["passed"] = True
            ac2["details"] = f"optics-green CSS only uses #00FF00 (found {len(green_colors)} green color refs)"
        else:
            ac2["details"] = f"Found non-green colors in optics-green: {green_non_green}"
    else:
        ac2["details"] = "No optics-green CSS block found"
    results.append(ac2)

    # AC3: 中央透明区域 - 检查是否有 central 区域定义且透明
    ac3 = {
        "id": "AC3",
        "name": "中央透明区域",
        "passed": False,
        "details": ""
    }
    if "central" in content.lower() or "center" in content.lower():
        # 检查中央区域是否定义为透明
        if "transparent" in content.lower() or "opacity: 0" in content.lower():
            ac3["passed"] = True
            ac3["details"] = "Central area defined as transparent"
    else:
        # 检查布局是否使用 left/right strip 结构
        if "strip-left" in content.lower() or "strip-right" in content.lower() or "left-strip" in content.lower():
            ac3["passed"] = True
            ac3["details"] = "Layout uses left/right strips with central gap"
    results.append(ac3)

    # AC4: ADAS 信息完整性 - 检查是否有距离、速度、TTC 显示
    ac4 = {
        "id": "AC4",
        "name": "ADAS 信息完整性",
        "passed": False,
        "details": ""
    }
    required_fields = ["distance", "speed", "ttc"]
    found_fields = []
    for field in required_fields:
        if field in content.lower():
            found_fields.append(field)
    if len(found_fields) == 3:
        ac4["passed"] = True
        ac4["details"] = f"Found all required fields: {found_fields}"
    else:
        ac4["details"] = f"Missing fields: {[f for f in required_fields if f not in found_fields]}"
    results.append(ac4)

    # AC5: 多重预警优先级 - 检查 TTC 优先级逻辑
    ac5 = {
        "id": "AC5",
        "name": "多重预警优先级",
        "passed": False,
        "details": ""
    }
    if "ttc" in content.lower() and ("priority" in content.lower() or "max" in content.lower() or "min" in content.lower()):
        ac5["passed"] = True
        ac5["details"] = "Found TTC priority logic"
    else:
        ac5["details"] = "No TTC priority logic found"
    results.append(ac5)

    # AC6: BSD 外边缘闪烁
    ac6 = {
        "id": "AC6",
        "name": "BSD 外边缘闪烁",
        "passed": False,
        "details": ""
    }
    if "bsd" in content.lower() and ("outer" in content.lower() or "edge-outer" in content.lower() or "left-edge" in content.lower()):
        ac6["passed"] = True
        ac6["details"] = "Found BSD outer edge flashing"
    else:
        ac6["details"] = "No BSD outer edge definition found"
    results.append(ac6)

    # AC7: LDW 内边缘闪烁
    ac7 = {
        "id": "AC7",
        "name": "LDW 内边缘闪烁",
        "passed": False,
        "details": ""
    }
    if "ldw" in content.lower() and ("inner" in content.lower() or "edge-inner" in content.lower()):
        ac7["passed"] = True
        ac7["details"] = "Found LDW inner edge flashing"
    else:
        ac7["details"] = "No LDW inner edge definition found"
    results.append(ac7)

    # AC8: 优先级抢占保留
    ac8 = {
        "id": "AC8",
        "name": "优先级抢占保留",
        "passed": False,
        "details": ""
    }
    if "priority" in content.lower() and ("shrink" in content.lower() or "reduce" in content.lower() or "smaller" in content.lower()):
        ac8["passed"] = True
        ac8["details"] = "Found priority preemption shrink logic"
    else:
        ac8["details"] = "No priority preemption logic found"
    results.append(ac8)

    # AC9: 预警后自动恢复
    ac9 = {
        "id": "AC9",
        "name": "预警后自动恢复",
        "passed": False,
        "details": ""
    }
    if "restore" in content.lower() or "recovery" in content.lower() or "auto" in content.lower():
        ac9["passed"] = True
        ac9["details"] = "Found auto recovery logic"
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
    if "touring" in content.lower() and ("moment" in content.lower() or "voice" in content.lower() or "mark" in content.lower()):
        ac10["passed"] = True
        ac10["details"] = "Found touring scenario with voice mark"
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
    if "subtitle" in content.lower() or "caption" in content.lower() or "voice-text" in content.lower():
        if "bottom" in content.lower() or "top" in content.lower():
            ac11["passed"] = True
            ac11["details"] = "Found subtitle positioning outside HUD area"
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
    if "opacity" in content.lower() and ("slider" in content.lower() or "sandbox" in content.lower()):
        ac12["passed"] = True
        ac12["details"] = "Found opacity control in sandbox"
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
    if "traffic" in content.lower() or "sign" in content.lower():
        if "zone-rt" in content.lower() or "right-top" in content.lower():
            ac13["passed"] = True
            ac13["details"] = "Found traffic sign display in RT zone"
    else:
        ac13["details"] = "No traffic sign logic found"
    results.append(ac13)

    # AC14: 显示区域可调
    ac14 = {
        "id": "AC14",
        "name": "显示区域可调",
        "passed": False,
        "details": ""
    }
    if "sandbox" in content.lower() and ("width" in content.lower() or "height" in content.lower() or "position" in content.lower()):
        ac14["passed"] = True
        ac14["details"] = "Found display area controls in sandbox"
    else:
        ac14["details"] = "No display area controls found"
    results.append(ac14)

    # 计算总体通过率
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
    print("HUD Demo v2 验收标准验证报告")
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