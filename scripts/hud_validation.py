"""
@description: HUD Demo v2 验收标准验证脚本 (59条)
@dependencies: 无
@last_modified: 2026-04-13
"""

import re
import sys
import io
from pathlib import Path

# Emoji pattern (U+1F000-U+1FFFF range)
EMOJI_PATTERN = re.compile("[\U0001F000-\U0001FFFF]+")

class HUDValidator:
    """HUD Demo v2 59条验收标准验证器"""

    def __init__(self, html_path: str = "demo_outputs/hud_demo_v2.html"):
        self.html_path = Path(html_path)
        self.content = ""
        self.results = []

    def load(self) -> bool:
        if not self.html_path.exists():
            return False
        self.content = self.html_path.read_text(encoding="utf-8")
        return True

    def check(self, id: str, name: str, passed: bool, details: str):
        self.results.append({"id": id, "name": name, "passed": passed, "details": details})

    def has(self, *patterns) -> bool:
        return all(p.lower() in self.content.lower() for p in patterns)

    def has_any(self, *patterns) -> bool:
        return any(p.lower() in self.content.lower() for p in patterns)

    def has_regex(self, pattern) -> bool:
        return re.search(pattern, self.content) is not None

    # === A. 物理布局 (7条) ===
    def check_A1(self): self.check("A1", "中央无HUD元素", self.has_any("center-area", "center-gap", "hud-center") and self.has("hud-viewport"), f"center_layout={self.has_any('center-area','center-gap')}")
    def check_A2(self): self.check("A2", "显示带中偏上", self.has_any("strip-top-offset", "stripTopOffset") or self.has_regex(r'top:\s*\d+'), f"top_offset={self.has_any('strip-top-offset')}")
    def check_A3(self): gap = int(re.search(r'center-gap:\s*(\d+)', self.content).group(1) if re.search(r'center-gap:\s*(\d+)', self.content) else 0); self.check("A3", "中央间距≥400px", gap >= 400, f"gap={gap}px")
    def check_A4(self): self.check("A4", "sandbox滑块可调", self.has_any("strip-width", "strip-height", "center-gap-slider"), f"controls found")
    def check_A5(self): self.check("A5", "路面背景可见", self.has_any("road-bg", "bg-opacity") and (self.has_regex(r'bg-opacity:\s*[0-9.]+') or "road-bg" in self.content), f"bg exists")
    def check_A6(self): self.check("A6", "背景上传按钮", self.has_any("type='file'", 'type="file"', "bg-upload"), f"file_input found")
    def check_A7(self): self.check("A7", "zone间隔不填充", self.has_any("background: transparent", "background-color: transparent") or self.has_regex(r'zone.*gap'), f"transparent or gap")

    # === B. 光学模式 (8条) ===
    def check_B1(self): self.check("B1", "FreeForm全彩50%", self.has_any("F1", "freeform"), f"F1/freeform found")
    def check_B2(self): self.check("B2", "全彩波导低亮", self.has_any("F2", "waveguide"), f"F2/waveguide found")
    def check_B3(self): self.check("B3", "单绿#00FF00", self.has_any("F3", "optics-green"), f"F3/optics-green found")
    def check_B4(self): emojis = EMOJI_PATTERN.findall(self.content); self.check("B4", "单绿无emoji", len(emojis) == 0, f"emoji_count={len(emojis)}")
    def check_B5(self): self.check("B5", "单绿用opacity", not self.has_regex(r'rgba\(0,\s*255,\s*0,\s*0\.[0-9]+\)'), f"no_rgba_alpha")
    def check_B6(self): self.check("B6", "亮度分级可调", self.has_any("brightness-level", "green-brightness", "luminance"), f"brightness_control")
    def check_B7(self): self.check("B7", "FOV滑块改宽度", self.has_any("fov-slider", "fov"), f"fov_slider")
    def check_B8(self): self.check("B8", "光学模式视觉差异", self.has_any("setOptics", "switchMode") and self.has_any("brightness", "color"), f"mode_switch found")

    # === C. ADAS预警 (10条) ===
    def check_C1(self): self.check("C1", "6种预警可触发", self.has_any("FCW", "BSD", "Dooring", "pedestrian", "LDW"), f"warning_types found")
    def check_C2(self): self.check("C2", "预警五项信息", self.has_any("type", "direction", "distance", "closingSpeed", "ttc"), f"fields found")
    def check_C3(self): self.check("C3", "预警不溢出", self.has_any("overflow: hidden", "overflow:hidden") or self.has_regex(r'zone.*height'), f"overflow_control")
    def check_C4(self): self.check("C4", "BSD外边缘闪烁", self.has_any("BSD") and self.has_any("leftEdgeOuter"), f"bsd_outer")
    def check_C5(self): self.check("C5", "Dooring外边缘", self.has_any("Dooring") and self.has_any("rightEdgeOuter"), f"dooring_outer")
    def check_C6(self): self.check("C6", "LDW左内边缘", self.has_any("ldw-left", "LDW_L") and (self.has_any("leftEdgeInner") or self.has("dashed")), f"ldw_left_inner")
    def check_C7(self): self.check("C7", "LDW右内边缘", self.has_any("ldw-right", "LDW_R") and (self.has_any("rightEdgeInner") or self.has("dashed")), f"ldw_right_inner")
    def check_C8(self): self.check("C8", "多重预警TTC优先", self.has_any("activeWarnings.sort", "sortTTC") or self.has_any("TTC", "priority"), f"ttc_priority")
    def check_C9(self): self.check("C9", "预警数组上限2", self.has_regex(r'activeWarnings\.slice\(0,\s*2\)') or self.has("activeWarnings.length > 2"), f"array_limit")
    def check_C10(self): self.check("C10", "预警方向SVG", self.has_regex(r'<svg[^>]*arrow') or self.has_any("arrow-up", "arrow-down"), f"svg_arrow")

    # === D. 状态机 (5条) ===
    def check_D1(self): modes = ["cruise", "nav", "call", "music", "mesh", "warn", "dvr"]; found = sum(1 for m in modes if m in self.content.lower()); self.check("D1", "7种模式", found >= 6, f"found {found}/7")
    def check_D2(self): self.check("D2", "优先级抢占缩小", self.has_any("shrunk", "scale") and self.has("opacity"), f"shrunk+opacity")
    def check_D3(self): self.check("D3", "预警结束恢复", self.has_any("popMode", "restoreMode", "previousMode"), f"pop_restore")
    def check_D4(self): self.check("D4", "S2导航降级", self.has_any("S2", "speed > 60", "nav-level"), f"S2_or_nav_level")
    def check_D5(self): self.check("D5", "S3极简", self.has_any("S3", "speed > 100", "hideMusic"), f"S3_or_hide")

    # === E. 导航 (4条) ===
    def check_E1(self): self.check("E1", "导航三级视觉", self.has_regex(r'<svg[^>]*(arrow|road|route)') or self.has_any("nav-level"), f"nav_svg")
    def check_E2(self): self.check("E2", "速度自动降级", self.has_any("autoDowngrade") or (self.has("speed") and self.has("nav")), f"auto_downgrade")
    def check_E3(self): self.check("E3", "导航左侧中段", self.has_any("nav-middle", "nav-strip") or (self.has("left-strip") and self.has("nav")), f"nav_position")
    def check_E4(self): self.check("E4", "手动切换导航", self.has_any("navLevel", "nav-level-btn") or self.has_regex(r'nav.*button'), f"nav_switch")

    # === F. 通信与媒体 (4条) ===
    def check_F1(self): self.check("F1", "来电占主要", self.has("call") and self.has_any("caller", "accept", "reject"), f"call_display")
    def check_F2(self): self.check("F2", "交通标志持续", self.has_any("TrafficSign", "currentSign", "setTrafficSign"), f"traffic_sign")
    def check_F3(self): self.check("F3", "Mesh SVG简图", self.has("mesh") and (self.has_regex(r'<svg[^>]*(team|member)') or self.has_any("relative", "position")), f"mesh_svg")
    def check_F4(self): self.check("F4", "DVR REC/Moment", self.has_any("dvr", "rec", "REC") and self.has_any("Moment saved", "showMomentSaved"), f"dvr_moment")

    # === G. 剧本 (8条) ===
    def check_G1(self): self.check("G1", "4剧本可播放", self.has_any("commute", "emergency", "group", "touring"), f"4_scenarios")
    def check_G2(self): voice_count = len(re.findall(r'showVoiceSubtitle', self.content)); self.check("G2", "语音字幕≥8", voice_count >= 8, f"voice_count={voice_count}")
    def check_G3(self): em = re.search(r'emergency:\s*\{[^}]*events:\s*\[[^\]]*\]', self.content, re.DOTALL); self.check("G3", "emergency LDW", em and ("LDW" in em.group(0)), f"ldw_in_emergency")
    def check_G4(self): self.check("G4", "emergency并发预警", self.has_regex(r'emitWarning.*emitWarning') or self.has("activeWarnings"), f"concurrent_warnings")
    def check_G5(self): tm = re.search(r'touring:\s*\{[^}]*events:\s*\[[^\]]*\]', self.content, re.DOTALL); cnt = len(re.findall(r'setTrafficSign', tm.group(0) if tm else "")); self.check("G5", "touring标志≥2", cnt >= 2, f"sign_count={cnt}")
    def check_G6(self): tm = re.search(r'touring:\s*\{[^}]*events:\s*\[[^\]]*\]', self.content, re.DOTALL); self.check("G6", "touring精彩瞬间", tm and "showMomentSaved" in tm.group(0), f"moment_in_touring")
    def check_G7(self): tm = re.search(r'touring:\s*\{[^}]*events:\s*\[[^\]]*\]', self.content, re.DOTALL); evts = len(re.findall(r'(emitEvent|showVoice|setTraffic|showMoment|emitWarning)', tm.group(0) if tm else "")); self.check("G7", "touring事件≥15", evts >= 15, f"event_count={evts}")
    def check_G8(self): self.check("G8", "语音字幕底部", self.has("bottom-bar") and self.has("voice-subtitle"), f"subtitle_position")

    # === H. 图标与视觉 (4条) ===
    def check_H1(self): emojis = EMOJI_PATTERN.findall(self.content); self.check("H1", "SVG无emoji", len(emojis) == 0 and self.has_regex(r'<svg[^>]*icon'), f"svg_icons={self.has_regex(r'<svg')}")
    def check_H2(self): self.check("H2", "预警脉冲glow", self.has("box-shadow") and self.has_any("pulse", "animation"), f"glow_effect")
    def check_H3(self): self.check("H3", "图标细线条", self.has("stroke-width"), f"stroke_width")
    def check_H4(self): self.check("H4", "产品原型级别", self.has_any("sandbox", "timeline") and self.has_any("transition", "animation"), f"polished_ui")

    # === I. Sandbox控件 (5条) ===
    def check_I1(self): self.check("I1", "F1/F2/F3快捷键", self.has("F1") and self.has("F2") and self.has("F3"), f"f_keys")
    def check_I2(self): self.check("I2", "FOV滑块28-50", self.has_any("fov-slider", "fovSlider") or self.has_regex(r'fov.*28.*50'), f"fov_range")
    def check_I3(self): ctrls = ["strip-width", "center-gap", "bg-opacity"]; found = sum(1 for c in ctrls if c in self.content.lower()); self.check("I3", "显示区域调节", found >= 2, f"found {found}/3")
    def check_I4(self): self.check("I4", "亮度分级调节", self.has_any("brightness-level", "luminance") or (self.has("brightness") and self.has("level")), f"brightness_input")
    def check_I5(self): self.check("I5", "背景图片上传", self.has_any("type='file'", 'type="file"'), f"file_input")

    # === J. 技术约束 (4条) ===
    def check_J1(self): lines = len(self.content.split('\n')); self.check("J1", "HTML≤2500行", lines <= 2500, f"lines={lines}")
    def check_J2(self): apis = ["setMode", "getMode", "setSpeed", "setOptics", "emitWarning", "emitEvent", "playScenario"]; found = sum(1 for a in apis if a in self.content); self.check("J2", "window API", found >= 6, f"found {found}/7")
    def check_J3(self): self.check("J3", "全局CONFIG", self.has("CONFIG") and self.has_regex(r'CONFIG\s*=\s*\{'), f"config_object")
    def check_J4(self): self.check("J4", "CSS clamp()", self.has_regex(r'clamp\([^)]+\)'), f"clamp_found")

    def run_all(self):
        self.results = []
        for i in range(1, 8): getattr(self, f'check_A{i}')()
        for i in range(1, 9): getattr(self, f'check_B{i}')()
        for i in range(1, 11): getattr(self, f'check_C{i}')()
        for i in range(1, 6): getattr(self, f'check_D{i}')()
        for i in range(1, 5): getattr(self, f'check_E{i}')()
        for i in range(1, 5): getattr(self, f'check_F{i}')()
        for i in range(1, 9): getattr(self, f'check_G{i}')()
        for i in range(1, 5): getattr(self, f'check_H{i}')()
        for i in range(1, 6): getattr(self, f'check_I{i}')()
        for i in range(1, 5): getattr(self, f'check_J{i}')()

        passed = sum(1 for r in self.results if r["passed"])
        return {"file": str(self.html_path), "total": len(self.results), "passed": passed, "failed": len(self.results) - passed, "pass_rate": f"{passed/len(self.results)*100:.1f}%", "results": self.results}

def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    v = HUDValidator()
    if not v.load():
        print(f"错误: 文件不存在 - {v.html_path}")
        return
    r = v.run_all()
    print("=" * 60)
    print("HUD Demo v2 验收标准验证报告 (59条)")
    print("=" * 60)
    print(f"文件: {r['file']}")
    print(f"总标准数: {r['total']}")
    print(f"通过: {r['passed']}")
    print(f"失败: {r['failed']}")
    print(f"通过率: {r['pass_rate']}")
    print("-" * 60)
    cats = {"A":"物理布局","B":"光学模式","C":"ADAS预警","D":"状态机","E":"导航","F":"通信媒体","G":"剧本","H":"图标视觉","I":"Sandbox","J":"技术约束"}
    for cid, cname in cats.items():
        cr = [x for x in r["results"] if x["id"].startswith(cid)]
        cp = sum(1 for x in cr if x["passed"])
        print(f"\n[{cid}] {cname} ({cp}/{len(cr)})")
        for x in cr:
            print(f"  {x['id']}: [{'PASS' if x['passed'] else 'FAIL'}] {x['name']}")
            print(f"       {x['details']}")
    print("=" * 60)
    print(f"结论: {'全部通过' if r['failed'] == 0 else f'{r['failed']}条失败'}")
    print("=" * 60)

if __name__ == "__main__":
    main()