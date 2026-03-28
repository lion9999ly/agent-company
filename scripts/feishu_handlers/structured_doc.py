"""
@description: 结构化文档快速通道 - PRD/清单/表格类需求不走多Agent
@dependencies: model_gateway, knowledge_base, openpyxl
@last_modified: 2026-03-27

功能：
- 检测清单/表格/PRD类需求关键词
- 单次LLM调用生成JSON结构
- 导出Excel并发送到飞书
- 降级发送树形摘要文本
"""

import json
import re
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Any, Optional

PARALLEL_WORKERS = 4  # 并行生成线程数

# 导出目录（项目固定路径，避免 tempfile 权限问题）
EXPORT_DIR = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# === 关键词检测 ===
STRUCTURED_DOC_KEYWORDS = ["清单", "表格", "PRD", "Excel", "excel", "列表", "功能列表"]
FULL_SPEC_KEYWORDS = ["规格书", "状态场景", "语音指令", "按键映射", "灯效", "6个Sheet", "完整PRD", "6Sheet"]
MIN_TEXT_LENGTH = 50


def is_structured_doc_request(text: str) -> bool:
    """判断是否为结构化文档需求"""
    if len(text) < MIN_TEXT_LENGTH:
        return False
    return any(kw in text for kw in STRUCTURED_DOC_KEYWORDS)


def is_full_spec_request(text: str) -> bool:
    """判断是否需要完整规格书（6 Sheet）"""
    if len(text) < MIN_TEXT_LENGTH:
        return False
    return any(kw in text for kw in FULL_SPEC_KEYWORDS)


def _extract_l1_from_user_text(text: str) -> List[Dict]:
    """从用户文本中提取一级功能列表"""
    features = []

    # HUD 功能（拆分"简易"和"路线"为独立项）
    hud_names = [
        "导航", "来电", "音乐", "消息", "Ai语音助手", "AI语音助手",
        "简易",   # 简易模式/极简显示
        "路线",   # 路线规划/路线概览
        "主动安全预警提示",  # 匹配完整名称优先
        "组队", "摄像状态", "胎温胎压",
        "开机动画", "速度", "设备状态", "显示队友位置"
    ]
    for name in hud_names:
        if name in text:
            features.append({"name": name, "module": "头盔HUD"})

    # App Tab（4 个）- 独立匹配
    app_tabs = ["设备", "社区", "商城", "我的"]
    for tab in app_tabs:
        # 明确的 App-设备 格式
        if f"App-{tab}" in text or f"App的{tab}" in text or f"APP-{tab}" in text:
            features.append({"name": f"App-{tab}", "module": f"App-{tab}"})
        elif tab in text and ("App" in text or "APP" in text or "app" in text):
            # 检查是否有独立的 tab（不在其他词中）
            if tab == "设备":
                # 如果"设备"出现次数 > "设备状态"出现次数，说明有独立的"设备"
                device_count = text.count("设备")
                device_status_count = text.count("设备状态")
                if device_count > device_status_count:
                    features.append({"name": f"App-{tab}", "module": f"App-{tab}"})
            else:
                features.append({"name": f"App-{tab}", "module": f"App-{tab}"})

    # 额外模块（AI 相关拆细）
    extras = [
        ("AI功能", "AI功能"),
        ("语音交互", "AI功能"),
        ("视觉交互", "AI功能"),      # ADAS、追踪
        ("多模态交互", "AI功能"),   # 陀螺仪、心率
        ("实体按键交互", "头盔交互"),
        ("氛围灯交互", "头盔交互"),
        ("身份认证", "系统"),
        ("用户学习", "系统"),
        ("设备互联", "系统"),
        ("产品介绍", "系统"),
        ("设备配对流程", "系统"),
    ]
    for name, module in extras:
        if name in text:
            features.append({"name": name, "module": module})

    # 额外匹配：用户可能分开写"简易"和"路线"
    if "简易" in text and not any(f["name"] == "简易" for f in features):
        features.append({"name": "简易显示模式", "module": "头盔HUD"})
    if "路线" in text and not any(f["name"] == "路线" for f in features):
        features.append({"name": "路线规划与预览", "module": "头盔HUD"})

    # 去重
    seen = set()
    unique_features = []
    for f in features:
        key = f["name"]
        if key not in seen:
            seen.add(key)
            unique_features.append(f)

    # 兜底：如果没有提取到，使用默认
    if not unique_features:
        unique_features = [{"name": "完整功能", "module": "全部"}]

    return unique_features


# === 功能ID生成 ===
def _generate_ids(items: List[Dict]) -> List[Dict]:
    """为功能清单生成层级式功能ID"""
    MODULE_PREFIX = {
        "头盔HUD": "HUD", "导航": "HUD", "来电": "HUD", "音乐": "HUD",
        "消息": "HUD", "AI语音助手": "HUD", "Ai语音助手": "HUD",
        "简易": "HUD", "路线": "HUD", "主动安全预警提示": "HUD",
        "组队": "HUD", "摄像状态": "HUD", "胎温胎压": "HUD",
        "开机动画": "HUD", "速度": "HUD", "设备状态": "HUD",
        "显示队友位置": "HUD", "HUD": "HUD",
        "App-设备": "DEV", "App-社区": "COM", "App-商城": "MAL", "App-我的": "MY",
        "AI功能": "AI", "语音交互": "AI", "视觉交互": "AI", "多模态交互": "AI",
        "实体按键交互": "BTN", "氛围灯交互": "LED",
        "身份认证": "AUTH", "用户学习": "LRN", "设备互联": "IOT", "产品介绍": "INTRO",
        "设备配对流程": "PAIR",
        "系统": "SYS", "头盔交互": "BTN",
    }

    l1_counter = {}
    l2_counter = {}
    l3_counter = {}
    current_l1_id = ""
    current_l2_id = ""

    for item in items:
        level = item.get("level", "")
        module = item.get("module", "")
        prefix = MODULE_PREFIX.get(module, "OTH")

        if level == "L1":
            l1_counter[prefix] = l1_counter.get(prefix, 0) + 1
            current_l1_id = f"{prefix}-{l1_counter[prefix]:03d}"
            item["_id"] = current_l1_id
        elif level == "L2":
            l2_counter[current_l1_id] = l2_counter.get(current_l1_id, 0) + 1
            current_l2_id = f"{current_l1_id}-{l2_counter[current_l1_id]:02d}"
            item["_id"] = current_l2_id
        elif level == "L3":
            l3_counter[current_l2_id] = l3_counter.get(current_l2_id, 0) + 1
            item["_id"] = f"{current_l2_id}-{l3_counter[current_l2_id]:02d}"

    return items


# === 模块名统一 ===
def _normalize_module_names(items: List[Dict]) -> List[Dict]:
    """统一模块名（大小写/变体合并）"""
    name_map = {
        "Ai语音助手": "AI语音助手",
        "ai语音助手": "AI语音助手",
        "头盔HUD": "HUD",
    }
    for item in items:
        m = item.get("module", "")
        if m in name_map:
            item["module"] = name_map[m]
    return items


# === Excel Sheet写入 ===
def _write_sheet(ws, items: List[Dict]):
    """写入单个 Sheet"""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    headers = ["功能ID", "L1功能", "L2功能", "L3功能", "优先级",
               "交互方式", "描述", "验收标准", "关联功能", "备注"]

    # 表头样式
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border

    # 优先级颜色
    priority_fills = {
        "P0": PatternFill(start_color="FF4444", end_color="FF4444", fill_type="solid"),
        "P1": PatternFill(start_color="FF8C00", end_color="FF8C00", fill_type="solid"),
        "P2": PatternFill(start_color="4CAF50", end_color="4CAF50", fill_type="solid"),
        "P3": PatternFill(start_color="9E9E9E", end_color="9E9E9E", fill_type="solid"),
    }
    priority_fonts = {
        "P0": Font(bold=True, color="FFFFFF"),
        "P1": Font(bold=True, color="FFFFFF"),
        "P2": Font(color="FFFFFF"),
        "P3": Font(color="FFFFFF"),
    }

    # L1 行样式
    l1_fill = PatternFill(start_color="D6E4F0", end_color="D6E4F0", fill_type="solid")
    l1_font = Font(bold=True, size=11)
    l2_font = Font(bold=True, size=10)

    for row_idx, item in enumerate(items, 2):
        level = item.get("level", "")
        name = item.get("name", "")

        # 功能ID
        ws.cell(row=row_idx, column=1, value=item.get("_id", ""))

        # L1/L2/L3 分列填写
        if level == "L1":
            ws.cell(row=row_idx, column=2, value=name)
        elif level == "L2":
            ws.cell(row=row_idx, column=3, value=name)
        elif level == "L3":
            ws.cell(row=row_idx, column=4, value=name)

        # 其余列
        ws.cell(row=row_idx, column=5, value=item.get("priority", ""))
        ws.cell(row=row_idx, column=6, value=item.get("interaction", ""))
        ws.cell(row=row_idx, column=7, value=item.get("description", ""))
        ws.cell(row=row_idx, column=8, value=item.get("acceptance", ""))
        ws.cell(row=row_idx, column=9, value=item.get("dependencies", ""))
        ws.cell(row=row_idx, column=10, value=item.get("note", ""))

        # 样式
        for col in range(1, 11):
            cell = ws.cell(row=row_idx, column=col)
            cell.border = thin_border
            cell.alignment = Alignment(vertical="center", wrap_text=True)

        if level == "L1":
            for col in range(1, 11):
                ws.cell(row=row_idx, column=col).fill = l1_fill
                ws.cell(row=row_idx, column=col).font = l1_font
        elif level == "L2":
            ws.cell(row=row_idx, column=3).font = l2_font

        # 优先级颜色
        p = item.get("priority", "").upper()
        if p in priority_fills:
            pc = ws.cell(row=row_idx, column=5)
            pc.fill = priority_fills[p]
            pc.font = priority_fonts[p]
            pc.alignment = Alignment(horizontal="center", vertical="center")

    # 列宽
    widths = [16, 20, 24, 28, 8, 16, 36, 36, 20, 16]
    for i, w in enumerate(widths):
        ws.column_dimensions[get_column_letter(i + 1)].width = w

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(items) + 1}"


# === 脑图HTML生成 ===
def _generate_mindmap_html(items: List[Dict], title: str = "功能框架脑图") -> str:
    """生成 HTML 脑图文件"""

    # 构建树结构
    tree = {}
    current_l1 = ""
    current_l2 = ""

    for item in items:
        level = item.get("level", "")
        name = item.get("name", "")
        module = item.get("module", "")
        priority = item.get("priority", "")

        if level == "L1":
            current_l1 = name
            if module not in tree:
                tree[module] = {}
            tree[module][name] = {"_priority": priority, "_children": {}}
        elif level == "L2":
            current_l2 = name
            if module in tree and current_l1 in tree[module]:
                tree[module][current_l1]["_children"][name] = {"_priority": priority, "_items": []}
        elif level == "L3":
            if module in tree and current_l1 in tree[module]:
                children = tree[module][current_l1]["_children"]
                if current_l2 in children:
                    children[current_l2]["_items"].append({"name": name, "priority": priority})

    # 生成 HTML
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; background: #f5f5f5; padding: 20px; max-width: 1200px; margin: 0 auto; }}
h1 {{ text-align: center; color: #2F5496; margin-bottom: 30px; }}
.module {{ margin-bottom: 30px; background: #fff; border-radius: 8px; padding: 16px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
.module-title {{ font-size: 18px; font-weight: bold; color: #fff; background: #2F5496;
    padding: 8px 16px; border-radius: 6px; display: inline-block; margin-bottom: 12px; }}
.l1 {{ margin-left: 20px; margin-bottom: 16px; }}
.l1-title {{ font-size: 15px; font-weight: bold; color: #2F5496;
    border-left: 4px solid #2F5496; padding-left: 10px; margin-bottom: 6px; }}
.l2 {{ margin-left: 40px; margin-bottom: 8px; }}
.l2-title {{ font-size: 13px; font-weight: bold; color: #555; margin-bottom: 4px; }}
.l3 {{ margin-left: 60px; font-size: 12px; color: #777; line-height: 1.8; }}
.tag {{ display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 11px;
    color: #fff; margin-left: 6px; }}
.tag-P0 {{ background: #FF4444; }}
.tag-P1 {{ background: #FF8C00; }}
.tag-P2 {{ background: #4CAF50; }}
.tag-P3 {{ background: #9E9E9E; }}
</style></head><body>
<h1>{title}</h1>
"""

    for module_name, l1s in tree.items():
        html += f'<div class="module"><span class="module-title">{module_name}</span>\n'
        for l1_name, l1_data in l1s.items():
            p = l1_data.get("_priority", "")
            html += f'<div class="l1"><div class="l1-title">{l1_name} <span class="tag tag-{p}">{p}</span></div>\n'
            for l2_name, l2_data in l1_data.get("_children", {}).items():
                p2 = l2_data.get("_priority", "")
                html += f'<div class="l2"><div class="l2-title">├ {l2_name} <span class="tag tag-{p2}">{p2}</span></div>\n'
                l3_items = l2_data.get("_items", [])
                if l3_items:
                    html += '<div class="l3">'
                    for l3 in l3_items:
                        p3 = l3.get("priority", "")
                        html += f'└ {l3["name"]} <span class="tag tag-{p3}">{p3}</span><br>\n'
                    html += '</div>\n'
                html += '</div>\n'
            html += '</div>\n'
        html += '</div>\n'

    html += "</body></html>"
    return html


# === Sheet 3-6 生成函数 ===
def _gen_sheet3_state_scenarios(gateway, kb_context: str = "", goal_text: str = "") -> List[Dict]:
    """生成 Sheet 3: 状态场景对策表"""

    prompt = (
        "为智能摩托车全盔项目生成【状态场景对策表】。\n"
        "输出 JSON 数组，每个元素格式：\n"
        '{"pre_state":"前置状态","current":"当前状态/场景/操作",'
        '"exec_state":"执行状态","hud":"HUD提示内容",'
        '"light":"灯光提示(颜色+模式)","voice":"语音提示内容",'
        '"app":"App提示内容","cycle":"提示周期/时长"}\n\n'
        "必须覆盖以下场景分类（每类至少5条）：\n"
        "1. 开关机与启动：开机自检、关机确认、低电自动关机\n"
        "2. 蓝牙连接：首次配对、自动回连、断连、回连成功、回连失败\n"
        "3. 导航：开始导航、转向提醒、偏航重算、到达目的地、导航取消、GPS弱信号\n"
        "4. 来电通话：来电提醒、接听、拒接、挂断、通话中断\n"
        "5. 录制：开始录制、停止录制、存储满、过热降级、录制异常中断\n"
        "6. 组队：创建队伍、加入队伍、掉队提醒、队友离线、退出队伍\n"
        "7. 胎压：正常、低压警告、高温警告、传感器离线\n"
        "8. 电量：充电中、低电量20%、极低电量10%、充电完成\n"
        "9. 安全预警：前向碰撞、侧后来车、盲区占用、急弯减速\n"
        "10. OTA：检测到新版本、下载中、升级中、升级成功、升级失败\n"
        "11. SOS：疑似事故检测、倒计时确认、触发报警、误触取消\n"
        "12. AI语音：唤醒成功、识别中、执行成功、识别失败、网络不可用\n\n"
        "目标 60-80 条。只输出 JSON 数组。\n"
    )

    if kb_context:
        prompt += f"\n参考内部文档：\n{kb_context[:2000]}\n"

    result = gateway.call_azure_openai("cpo", prompt,
        "只输出JSON数组，不要其他文字。", "structured_doc")

    if result.get("success"):
        json_match = re.search(r'\[[\s\S]*\]', result["response"])
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
    return []


def _gen_sheet4_voice_commands(gateway, kb_context: str = "") -> List[Dict]:
    """生成 Sheet 4: 语音指令表"""

    prompt = (
        "为智能摩托车全盔项目生成【语音指令表】。\n"
        "输出 JSON 数组，每个元素格式：\n"
        '{"category":"指令分类","wake":"唤醒方式(唤醒词/按键/自动)",'
        '"user_says":"用户说法","variants":"常见变体说法(逗号分隔)",'
        '"action":"系统执行动作","success_voice":"成功语音反馈",'
        '"success_hud":"成功HUD反馈","fail_feedback":"失败反馈",'
        '"priority":"P0-P3","note":"备注"}\n\n'
        "必须覆盖以下分类（每类至少5条指令）：\n"
        "1. 导航控制：开始导航、取消导航、查询距离/时间、切换路线、回家\n"
        "2. 通话控制：接听、拒接、挂断、回拨、打给XX\n"
        "3. 音乐控制：播放、暂停、上一首、下一首、调大/小音量、静音\n"
        "4. 录制控制：开始录制、停止录制、拍照、标记片段\n"
        "5. 组队控制：创建队伍、加入队伍、退出队伍、呼叫队友\n"
        "6. 设备查询：查电量、查存储、查胎压、查速度、查时间\n"
        "7. 设置控制：调亮度、切模式、开/关降噪、开/关免打扰\n"
        "8. 安全相关：紧急求救、取消报警\n\n"
        "每条指令必须给出至少2个用户常见变体说法。\n"
        "目标 40-60 条。只输出 JSON 数组。\n"
    )

    result = gateway.call_azure_openai("cpo", prompt,
        "只输出JSON数组。", "structured_doc")

    if result.get("success"):
        json_match = re.search(r'\[[\s\S]*\]', result["response"])
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
    return []


def _gen_sheet5_button_mapping(gateway) -> List[Dict]:
    """生成 Sheet 5: 按键映射表"""

    prompt = (
        "为智能摩托车全盔项目生成【实体按键映射表】。\n"
        "头盔有以下按键：主按键(头盔侧面)、音量+键、音量-键、功能键(可选)。\n"
        "输出 JSON 数组，每个元素格式：\n"
        '{"button":"按键位置","single_click":"单击动作",'
        '"double_click":"双击动作","long_press":"长按动作(>2秒)",'
        '"combo":"组合键动作","scene":"当前场景(通用/导航中/通话中/录制中/组队中)",'
        '"note":"备注"}\n\n'
        "规则：\n"
        "1. 每个按键在不同场景下可以有不同含义\n"
        "2. 必须考虑：通用场景、导航中、通话中、录制中、组队中、音乐播放中\n"
        "3. 骑行中戴手套操作，所以动作必须简单明确\n"
        "4. 长按必须有确认反馈（震动或语音）\n\n"
        "目标 20-30 条。只输出 JSON 数组。\n"
    )

    result = gateway.call_azure_openai("cpo", prompt,
        "只输出JSON数组。", "structured_doc")

    if result.get("success"):
        json_match = re.search(r'\[[\s\S]*\]', result["response"])
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
    return []


def _gen_sheet6_light_effects(gateway) -> List[Dict]:
    """生成 Sheet 6: 灯效定义表"""

    prompt = (
        "为智能摩托车全盔项目生成【氛围灯灯效定义表】。\n"
        "头盔有后部氛围灯带，支持 RGB 颜色和多种闪烁模式。\n"
        "输出 JSON 数组，每个元素格式：\n"
        '{"trigger":"触发场景","color":"灯光颜色(如红/蓝/绿/白/橙/紫)",'
        '"mode":"闪烁模式(常亮/慢闪/快闪/呼吸/流水/脉冲)",'
        '"frequency":"频率(Hz,常亮填0)","duration":"持续时长",'
        '"priority":"优先级(P0-P3,高优先级覆盖低优先级)",'
        '"note":"备注"}\n\n'
        "必须覆盖：\n"
        "1. 系统状态：开机、关机、充电中、充电完成、低电量、OTA中\n"
        "2. 连接状态：蓝牙配对中、配对成功、断连、回连\n"
        "3. 安全预警：前向碰撞(红快闪)、侧后来车(橙方向闪)、盲区(黄)\n"
        "4. 通信提醒：来电(蓝呼吸)、消息(白单闪)、组队成功(绿)\n"
        "5. 录制状态：录制中(红微亮)、录制暂停、录制异常\n"
        "6. 骑行辅助：刹车灯效(红常亮)、转向灯效(橙流水)、掉队提醒\n"
        "7. 特殊场景：SOS(红蓝交替快闪)、夜骑尾灯模式\n\n"
        "灯效优先级规则：安全>通信>系统>装饰。\n"
        "目标 25-35 条。只输出 JSON 数组。\n"
    )

    result = gateway.call_azure_openai("cpo", prompt,
        "只输出JSON数组。", "structured_doc")

    if result.get("success"):
        json_match = re.search(r'\[[\s\S]*\]', result["response"])
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
    return []


# === Excel 导出 ===
def _export_to_excel(items: List[Dict], filename_prefix: str, title_hint: str) -> str:
    """导出功能清单到 Excel 文件（HUD端 + App端 双 Sheet）"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        print("[FastTrack] openpyxl 未安装，降级使用 CSV")
        csv_path = EXPORT_DIR / f"{filename_prefix}.csv"
        with open(csv_path, "w", encoding="utf-8-sig") as f:
            headers = ["功能ID", "L1功能", "L2功能", "L3功能", "优先级",
                       "交互方式", "描述", "验收标准", "关联功能", "备注"]
            f.write(",".join(headers) + "\n")
            for item in items:
                level = item.get("level", "")
                name = item.get("name", "")
                row = [
                    item.get("_id", ""),
                    name if level == "L1" else "",
                    name if level == "L2" else "",
                    name if level == "L3" else "",
                    item.get("priority", ""),
                    item.get("interaction", ""),
                    item.get("description", ""),
                    item.get("acceptance", ""),
                    item.get("dependencies", ""),
                    item.get("note", "")
                ]
                f.write(",".join(row) + "\n")
        return str(csv_path)

    # 模块名统一
    items = _normalize_module_names(items)

    # 生成功能ID
    items = _generate_ids(items)

    # 分组：HUD端 vs App端
    hud_items = [i for i in items if not i.get("module", "").startswith("App-")]
    app_items = [i for i in items if i.get("module", "").startswith("App-")]

    wb = Workbook()

    # Sheet 1: HUD 及头盔端功能
    ws_hud = wb.active
    ws_hud.title = "HUD及头盔端"
    if hud_items:
        _write_sheet(ws_hud, hud_items)

    # Sheet 2: App 功能
    if app_items:
        ws_app = wb.create_sheet("App端")
        _write_sheet(ws_app, app_items)

    # 保存
    xlsx_path = EXPORT_DIR / f"{filename_prefix}.xlsx"
    wb.save(xlsx_path)
    return str(xlsx_path)


# === 飞书文件发送 ===
def _send_file_to_feishu(reply_target: str, file_path: str, reply_type: str) -> bool:
    """用 requests 直接调飞书 HTTP API 发送文件"""
    import requests

    file_path = Path(file_path)
    if not file_path.exists():
        print(f"[File] 文件不存在: {file_path}")
        return False

    try:
        # 获取配置
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if not env_path.exists():
            env_path = Path(__file__).resolve().parent.parent / ".env"

        from dotenv import dotenv_values
        env = dotenv_values(str(env_path))
        app_id = env.get("FEISHU_APP_ID", "") or os.getenv("FEISHU_APP_ID", "")
        app_secret = env.get("FEISHU_APP_SECRET", "") or os.getenv("FEISHU_APP_SECRET", "")

        print(f"[File] env路径: {env_path} (存在: {env_path.exists()})")
        print(f"[File] app_id: {app_id[:10] if app_id else '空'}...")
        print(f"[File] secret: {'有' if app_secret else '空'}")
        print(f"[File] 文件: {file_path.name} ({file_path.stat().st_size} bytes)")

        if not app_id or not app_secret:
            print("[File] 缺少 APP_ID 或 APP_SECRET")
            return False

        # 获取 tenant_access_token
        token_resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret}
        )
        token_data = token_resp.json()

        if token_data.get("code") != 0:
            print(f"[File] token 获取失败: {token_data}")
            return False

        token = token_data["tenant_access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 上传文件
        print(f"[File] 上传中...")
        with open(file_path, 'rb') as f:
            upload_resp = requests.post(
                "https://open.feishu.cn/open-apis/im/v1/files",
                headers=headers,
                data={"file_type": "stream", "file_name": file_path.name},
                files={"file": (file_path.name, f)}
            )

        upload_data = upload_resp.json()
        print(f"[File] 上传响应: code={upload_data.get('code')} msg={upload_data.get('msg', '')}")

        if upload_data.get("code") != 0:
            return False

        file_key = upload_data["data"]["file_key"]
        print(f"[File] file_key: {file_key[:30]}...")

        # 发送文件消息
        # 转换 reply_type：open_id/chat_id
        id_type = "chat_id" if reply_type == "chat_id" else "open_id"

        send_resp = requests.post(
            f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={id_type}",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "receive_id": reply_target,
                "msg_type": "file",
                "content": json.dumps({"file_key": file_key})
            }
        )

        send_data = send_resp.json()
        print(f"[File] 发送响应: code={send_data.get('code')} msg={send_data.get('msg', '')}")

        if send_data.get("code") == 0:
            print(f"[File] ✅ 文件发送成功")
            return True
        else:
            print(f"[File] ❌ 发送失败")
            return False

    except Exception as e:
        print(f"[File] 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


# === 树形摘要格式化 ===
def _format_items_as_tree(items: List[Dict]) -> str:
    """将功能列表格式化为树形摘要"""
    # 按 L1 -> L2 -> L3 分组
    tree: Dict[str, Dict[str, List[Dict]]] = {}

    for item in items:
        level = item.get("level", "L1")
        module = item.get("module", "未分类")
        parent = item.get("parent", "")
        name = item.get("name", "")
        priority = item.get("priority", "P2")

        if level == "L1":
            if module not in tree:
                tree[module] = {"_self": item, "_children": {}}
        elif level == "L2":
            if parent and parent in tree:
                if "_children" not in tree[parent]:
                    tree[parent]["_children"] = {}
                tree[parent]["_children"][name] = {"_self": item, "_children": []}
        elif level == "L3":
            # 找到对应的 L2 parent
            for l1_mod, l1_data in tree.items():
                if parent in l1_data.get("_children", {}):
                    l1_data["_children"][parent]["_children"].append(item)
                    break

    # 格式化输出
    lines = []
    for l1_mod, l1_data in tree.items():
        l1_item = l1_data.get("_self", {})
        l1_name = l1_item.get("name", l1_mod)
        l1_priority = l1_item.get("priority", "P1")
        lines.append(f"📁 {l1_name} [{l1_priority}]")

        for l2_name, l2_data in l1_data.get("_children", {}).items():
            l2_item = l2_data.get("_self", {})
            l2_priority = l2_item.get("priority", "P2")
            lines.append(f"  📂 {l2_name} [{l2_priority}]")

            for l3_item in l2_data.get("_children", []):
                l3_name = l3_item.get("name", "")
                l3_priority = l3_item.get("priority", "P3")
                l3_desc = l3_item.get("description", "")[:30]
                lines.append(f"    📄 {l3_name} [{l3_priority}] - {l3_desc}")

    return "\n".join(lines)


# === 主函数 ===
def try_structured_doc_fast_track(
    text: str,
    reply_target: str,
    reply_type: str,
    open_id: str,
    chat_id: str,
    send_reply_func: Optional[callable] = None
) -> bool:
    """
    结构化文档快速通道

    Args:
        text: 用户消息文本
        reply_target: 回复目标 ID
        reply_type: 回复类型 (open_id / chat_id)
        open_id: 用户 Open ID
        chat_id: 群聊 Chat ID
        send_reply_func: 发送回复的函数（可选，默认使用飞书 API）

    Returns:
        bool: True 表示走了快速通道，False 表示继续走原有逻辑
    """
    if not is_structured_doc_request(text):
        return False

    print(f"[FastTrack] 检测到结构化文档需求，走快速通道")

    # 发送回复的函数
    def _send_reply(msg: str, rt: str = None, rtype: str = None):
        rt = rt or reply_target
        rtype = rtype or reply_type
        if send_reply_func:
            send_reply_func(rt, msg, rtype)
        else:
            # 默认使用飞书 API
            try:
                import lark_oapi as lark
                import os
                APP_ID = os.getenv("FEISHU_APP_ID", "cli_a9326fa6ba389cc5")
                APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

                client = lark.Client.builder() \
                    .app_id(APP_ID) \
                    .app_secret(APP_SECRET) \
                    .log_level(lark.LogLevel.ERROR) \
                    .build()

                from lark_oapi.api.im.v1 import CreateMessage, CreateMessageRequestBody
                content = json.dumps({"text": msg})

                request = CreateMessage.builder() \
                    .receive_id_type(rtype) \
                    .request_body(CreateMessageRequestBody.builder()
                        .receive_id(rt)
                        .msg_type("text")
                        .content(content)
                        .build()) \
                    .build()

                client.im.v1.message.create(request)
            except Exception as e:
                print(f"[FastTrack] 发送回复失败: {e}")

    _send_reply("📋 检测到结构化文档需求，正在生成...")

    def _process_in_background():
        try:
            from src.utils.model_gateway import get_model_gateway
            from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt, KB_ROOT

            gw = get_model_gateway()

            # 搜知识库找内部文档
            kb_entries = search_knowledge(text, limit=10)
            kb_context = format_knowledge_for_prompt(kb_entries) if kb_entries else ""

            # 读产品目标
            goal_text = ""
            goal_file = KB_ROOT.parent.parent / "product_goal.json"
            if goal_file.exists():
                try:
                    goal_text = json.loads(goal_file.read_text(encoding="utf-8")).get("goal", "")
                except:
                    pass

            # 分批 LLM 调用：按一级功能逐个生成
            l1_features = _extract_l1_from_user_text(text)
            total = len(l1_features)

            print(f"[FastTrack] 检测到 {total} 个一级功能，开始并行生成 ({PARALLEL_WORKERS} 路)")

            all_items = []
            batch_system_prompt = (
                "你是智能摩托车全盔项目的产品经理。你必须且只输出一个 JSON 数组。\n"
                "不要输出任何 markdown、解释文字、标题、分隔线。\n"
                "只输出以 [ 开头、以 ] 结尾的 JSON 数组。\n\n"
                "每个元素格式：\n"
                '{"module":"模块名","level":"L1或L2或L3","parent":"父功能名(L1填空)","name":"功能名称",'
                '"priority":"P0或P1或P2或P3","interaction":"HUD/语音/按键/App/灯光",'
                '"description":"一句话描述","acceptance":"可测试验收标准(含数字)",'
                '"dependencies":"关联功能","note":"备注"}\n\n'
                "规则：\n"
                "1. 第一条是该模块的 L1\n"
                "2. L1 下至少 3 个 L2，每个 L2 至少 2 个 L3\n"
                "3. 验收标准必须可测试，含具体数字\n"
                "4. 你补充的功能在 note 标注[补充]\n"
                "5. 优先级只用 P0/P1/P2/P3\n"
                "6. 优先级分布：P0≤30%，P1占30-40%，P2占20-30%，P3占5-10%\n"
                "7. P0=不做就不能发售。P1=发售应有但可OTA补。P2=V2规划。P3=远期愿景\n"
                "8. 不要把所有功能都标P0，只有真正阻碍发售的才是P0\n"
            )

            # 单模块生成函数
            def _gen_one(feature: Dict) -> List[Dict]:
                """生成单个 L1 模块的功能清单"""
                # 判断是否为核心模块（需更深展开）
                core_modules = ["导航", "主动安全预警提示", "AI语音助手", "组队"]
                is_core = feature['name'] in core_modules

                batch_user_prompt = (
                    f"为智能摩托车全盔项目生成「{feature['name']}」模块的功能清单。\n"
                    f"模块归属：{feature['module']}\n\n"
                )
                if kb_context:
                    batch_user_prompt += f"内部产品文档参考：\n{kb_context[:2000]}\n\n"
                if goal_text:
                    batch_user_prompt += f"产品目标：\n{goal_text[:300]}\n\n"

                # 添加优化规则
                batch_user_prompt += (
                    f"规则：\n"
                    f"- 模块名必须和「{feature['name']}」完全一致，不允许大小写变体或缩写\n"
                    f"- 生成功能时考虑关联页面/场景，在note列标注（如'骑行主界面'、'App-设备Tab'）\n"
                )
                if is_core:
                    batch_user_prompt += f"- 这是核心卖点模块，至少展开5个L2，每个L2至少3个L3\n"

                batch_user_prompt += "\n只输出 JSON 数组。"

                result = gw.call_azure_openai(
                    "cpo", batch_user_prompt, batch_system_prompt,
                    "structured_doc", max_tokens=4096
                )

                if result.get("success"):
                    response = result["response"]
                    json_match = re.search(r'\[[\s\S]*\]', response)
                    if json_match:
                        try:
                            return json.loads(json_match.group())
                        except json.JSONDecodeError:
                            pass
                return []

            # 并行生成
            done_count = 0
            with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
                futures = {pool.submit(_gen_one, f): f for f in l1_features}
                for future in as_completed(futures):
                    feature = futures[future]
                    batch = future.result()
                    done_count += 1
                    if batch:
                        all_items.extend(batch)
                        print(f"  ✅ [{done_count}/{total}] {feature['name']}: +{len(batch)} 条")
                    else:
                        print(f"  ❌ [{done_count}/{total}] {feature['name']}: 失败")

            print(f"[FastTrack] 完成: {len(all_items)} 条功能 ({done_count} 个模块)")

            # 检查失败的模块并重试
            success_names = set()
            for item in all_items:
                # 从生成的条目中提取模块名
                mod = item.get("module", "") or item.get("parent", "")
                if mod:
                    success_names.add(mod)

            failed_features = [f for f in l1_features if f["name"] not in success_names]

            if failed_features:
                print(f"[FastTrack] {len(failed_features)} 个模块失败，重试中...")
                for feature in failed_features:
                    batch = _gen_one(feature)
                    if batch:
                        all_items.extend(batch)
                        print(f"  ✅ [重试] {feature['name']}: +{len(batch)} 条")
                    else:
                        print(f"  ❌ [重试] {feature['name']}: 仍然失败")

            # 合并后去重：同名功能只保留第一条
            seen = set()
            unique_items = []
            for item in all_items:
                key = (item.get("module", ""), item.get("name", ""), item.get("level", ""))
                if key not in seen:
                    seen.add(key)
                    unique_items.append(item)
                else:
                    print(f"  [去重] 跳过: {item.get('module')}/{item.get('name')}")

            print(f"[FastTrack] 去重: {len(all_items)} → {len(unique_items)}")
            all_items = unique_items

            if not all_items:
                _send_reply("生成失败：所有批次均未生成有效内容")
                return

            items = all_items

            # 导出 Excel
            try:
                task_id = f"{hash(text) % 100000:05d}"
                xlsx_path = _export_to_excel(items, f"prd_{task_id}", text[:50])
                print(f"[FastTrack] Excel: {xlsx_path}")

                # 发送 Excel 文件
                file_sent = _send_file_to_feishu(reply_target, xlsx_path, reply_type)

                # 生成脑图 HTML
                try:
                    mindmap_html = _generate_mindmap_html(items, "智能骑行头盔 V1 功能框架")
                    mindmap_path = EXPORT_DIR / f"mindmap_{task_id}.html"
                    mindmap_path.write_text(mindmap_html, encoding="utf-8")
                    print(f"[FastTrack] 脑图: {mindmap_path}")
                    _send_file_to_feishu(reply_target, str(mindmap_path), reply_type)
                except Exception as e:
                    print(f"[FastTrack] 脑图生成失败: {e}")

                if file_sent:
                    summary = _format_items_as_tree(items)
                    _send_reply(
                        f"📊 功能PRD清单已生成（{len(items)} 条），Excel + 脑图已发送。\n\n预览：\n{summary[:3000]}"
                    )
                else:
                    # 文件发送失败，发树形摘要
                    summary = _format_items_as_tree(items)
                    _send_reply(f"📋 功能PRD清单（{len(items)} 条）：\n\n{summary[:4000]}")
                    _send_reply(f"⚠️ 文件发送失败，Excel 已保存服务器: {xlsx_path}")

            except Exception as e:
                print(f"[FastTrack] Excel 失败: {e}")
                import traceback
                traceback.print_exc()
                # 降级发树形摘要
                summary = _format_items_as_tree(items)
                _send_reply(f"📋 功能清单（{len(items)} 条）：\n\n{summary[:4000]}")

        except Exception as e:
            print(f"[FastTrack] 异常: {e}")
            import traceback
            traceback.print_exc()
            _send_reply(f"生成失败: {str(e)[:200]}")

    # 后台线程执行
    threading.Thread(target=_process_in_background, daemon=True).start()
    return True


# === 测试入口 ===
if __name__ == "__main__":
    import os
    os.chdir(Path(__file__).parent.parent.parent)

    # 测试导入
    from scripts.feishu_handlers.structured_doc import try_structured_doc_fast_track
    print("模块导入成功")

    # 测试关键词检测
    test_texts = [
        "帮我生成智能头盔的功能清单",
        "这是一个短文本",
        "请输出PRD表格，包含HUD显示、语音交互、按键控制等功能模块",
    ]

    for t in test_texts:
        result = is_structured_doc_request(t)
        print(f"'{t[:30]}...' -> {result}")