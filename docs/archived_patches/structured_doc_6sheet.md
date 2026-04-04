# structured_doc.py 升级：支持 6 Sheet PRD 规格书

> 优先级: P0
> 预计改动: structured_doc.py 一个文件
> 目标: 飞书发一条消息 → 生成包含 6 个 Sheet 的 Excel + 脑图

---

## 改动概述

当前 structured_doc.py 只生成功能清单（HUD + App 两个 Sheet）。
升级为支持 6 个 Sheet 的完整 PRD 规格书。

核心思路不变：**拆小并行**。
- Sheet 1-2（功能清单）：按 L1 拆分，4 路并行（已有逻辑）
- Sheet 3-6（对策表/语音/按键/灯效）：每个 Sheet 一次 LLM 调用（4 个调用并行）
- 总时间预期：3-4 分钟

---

## Step 1: 修改关键词检测，识别"规格书"类需求

在 try_structured_doc_fast_track 的关键词检测中，增加对多 Sheet 需求的识别：

```python
    # 检测是否需要多 Sheet 完整规格书
    is_full_spec = any(kw in text for kw in [
        "规格书", "状态场景", "语音指令", "按键映射", "灯效", "6个Sheet", "完整PRD"
    ])
    
    # 基础清单需求（原有逻辑）
    is_structured_doc = any(kw in text for kw in [
        "清单", "表格", "PRD", "Excel", "excel", "列表", "功能列表"
    ])
```

如果 is_full_spec=True，走完整规格书流程；否则走原有功能清单流程。

---

## Step 2: 新增 4 个 Sheet 的生成函数

每个函数独立，可以并行调用：

```python
def _gen_sheet3_state_scenarios(gateway, kb_context="", goal_text=""):
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
        import re, json
        match = re.search(r'\[[\s\S]*\]', result["response"])
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
    return []


def _gen_sheet4_voice_commands(gateway, kb_context=""):
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
        import re, json
        match = re.search(r'\[[\s\S]*\]', result["response"])
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
    return []


def _gen_sheet5_button_mapping(gateway):
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
        import re, json
        match = re.search(r'\[[\s\S]*\]', result["response"])
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
    return []


def _gen_sheet6_light_effects(gateway):
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
        import re, json
        match = re.search(r'\[[\s\S]*\]', result["response"])
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
    return []
```

---

## Step 3: 并行生成 Sheet 3-6

在 try_structured_doc_fast_track 中，功能清单生成完后（或与功能清单并行），生成额外 4 个 Sheet：

```python
    if is_full_spec:
        print("[FastTrack] 完整规格书模式：并行生成 Sheet 3-6")
        
        sheet_results = {}
        
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(_gen_sheet3_state_scenarios, _gw, kb_context, goal_text): "state",
                pool.submit(_gen_sheet4_voice_commands, _gw, kb_context): "voice",
                pool.submit(_gen_sheet5_button_mapping, _gw): "button",
                pool.submit(_gen_sheet6_light_effects, _gw): "light",
            }
            for future in as_completed(futures):
                sheet_name = futures[future]
                result = future.result()
                sheet_results[sheet_name] = result
                print(f"  ✅ Sheet-{sheet_name}: {len(result)} 条")
```

---

## Step 4: Excel 导出支持 6 个 Sheet

修改 _export_to_excel 函数，接受额外的 sheet_data 参数：

```python
def _export_to_excel(items, task_id, task_goal="", extra_sheets=None):
    """导出 Excel，支持多 Sheet"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from pathlib import Path
    
    wb = Workbook()
    
    # --- Sheet 1 & 2: 功能清单（原有逻辑）---
    hud_items = [i for i in items if not i.get("module", "").startswith("App-")]
    app_items = [i for i in items if i.get("module", "").startswith("App-")]
    
    ws_hud = wb.active
    ws_hud.title = "HUD及头盔端"
    _write_feature_sheet(ws_hud, hud_items)
    
    ws_app = wb.create_sheet("App端")
    _write_feature_sheet(ws_app, app_items)
    
    # --- Sheet 3-6: 额外 Sheet ---
    if extra_sheets:
        if extra_sheets.get("state"):
            ws3 = wb.create_sheet("状态场景对策")
            _write_generic_sheet(ws3, extra_sheets["state"], 
                ["前置状态", "当前状态/场景/操作", "执行状态", "HUD提示", "灯光提示", "语音提示", "App提示", "提示周期"],
                ["pre_state", "current", "exec_state", "hud", "light", "voice", "app", "cycle"],
                [16, 24, 16, 28, 20, 28, 28, 14])
        
        if extra_sheets.get("voice"):
            ws4 = wb.create_sheet("语音指令表")
            _write_generic_sheet(ws4, extra_sheets["voice"],
                ["指令分类", "唤醒方式", "用户说法", "常见变体", "系统动作", "成功语音反馈", "成功HUD反馈", "失败反馈", "优先级", "备注"],
                ["category", "wake", "user_says", "variants", "action", "success_voice", "success_hud", "fail_feedback", "priority", "note"],
                [14, 12, 20, 24, 24, 24, 20, 20, 8, 16])
        
        if extra_sheets.get("button"):
            ws5 = wb.create_sheet("按键映射表")
            _write_generic_sheet(ws5, extra_sheets["button"],
                ["按键位置", "单击动作", "双击动作", "长按动作", "组合键动作", "当前场景", "备注"],
                ["button", "single_click", "double_click", "long_press", "combo", "scene", "note"],
                [14, 20, 20, 20, 20, 16, 20])
        
        if extra_sheets.get("light"):
            ws6 = wb.create_sheet("灯效定义表")
            _write_generic_sheet(ws6, extra_sheets["light"],
                ["触发场景", "灯光颜色", "闪烁模式", "频率Hz", "持续时长", "优先级", "备注"],
                ["trigger", "color", "mode", "frequency", "duration", "priority", "note"],
                [24, 12, 16, 10, 14, 8, 20])
    
    # 保存
    export_dir = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = export_dir / f"prd_{task_id}.xlsx"
    wb.save(str(xlsx_path))
    print(f"[Export] Excel {wb.sheetnames}: {xlsx_path}")
    return str(xlsx_path)


def _write_generic_sheet(ws, items, headers, keys, widths):
    """通用 Sheet 写入函数"""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    
    # 优先级颜色（如果有优先级列）
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
    
    # 写表头
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
    
    # 写数据
    for row_idx, item in enumerate(items, 2):
        for col, key in enumerate(keys, 1):
            val = item.get(key, "")
            cell = ws.cell(row=row_idx, column=col, value=str(val) if val else "")
            cell.border = thin_border
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            
            # 优先级颜色
            if key == "priority" and str(val).upper() in priority_fills:
                cell.fill = priority_fills[str(val).upper()]
                cell.font = priority_fonts[str(val).upper()]
                cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # 列宽
    for i, w in enumerate(widths):
        ws.column_dimensions[get_column_letter(i + 1)].width = w
    
    # 冻结+筛选
    ws.freeze_panes = "A2"
    if items:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(items) + 1}"
```

---

## Step 5: 修改主流程，串起来

在 try_structured_doc_fast_track 中，功能清单并行生成完成后：

```python
    # ========== 功能清单生成完成 ==========
    # 去重 + 生成ID + 模块名统一（原有逻辑）
    # ...
    
    # ========== 如果是完整规格书，并行生成 Sheet 3-6 ==========
    extra_sheets = None
    
    if is_full_spec:
        print("[FastTrack] 并行生成 Sheet 3-6...")
        send_reply(reply_target, "📋 功能清单已完成，正在生成状态对策/语音/按键/灯效表...", reply_type)
        
        extra_sheets = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(_gen_sheet3_state_scenarios, _gw, kb_context, goal_text): "state",
                pool.submit(_gen_sheet4_voice_commands, _gw, kb_context): "voice",
                pool.submit(_gen_sheet5_button_mapping, _gw): "button",
                pool.submit(_gen_sheet6_light_effects, _gw): "light",
            }
            for future in as_completed(futures):
                name = futures[future]
                data = future.result()
                extra_sheets[name] = data
                count = len(data)
                print(f"  ✅ {name}: {count} 条")
        
        total_extra = sum(len(v) for v in extra_sheets.values())
        print(f"[FastTrack] Sheet 3-6 完成: 共 {total_extra} 条")
    
    # ========== 导出 Excel ==========
    xlsx_path = _export_to_excel(all_items, task_id, text[:50], extra_sheets=extra_sheets)
    
    # ========== 发送文件 + 摘要（原有逻辑）==========
    # ...
```

---

## Step 6: 把完整规格书的 prompt 模板导入知识库

```python
python << 'PYEOF'
import sys; sys.path.insert(0, '.')
from src.tools.knowledge_base import add_knowledge

add_knowledge(
    title="[内部PRD] 完整PRD规格书Sheet结构定义",
    domain="components",
    content="""
完整 PRD 规格书包含 6 个 Sheet：

Sheet 1: HUD及头盔端功能清单
Sheet 2: App端功能清单  
Sheet 3: 状态场景对策表（前置状态→场景→HUD/灯光/语音/App四通道反馈）
Sheet 4: 语音指令表（指令分类→用户说法→系统动作→成功/失败反馈）
Sheet 5: 按键映射表（按键位置→单击/双击/长按→场景→动作）
Sheet 6: 灯效定义表（触发场景→颜色→模式→频率→优先级）

触发关键词：规格书、状态场景、语音指令、按键映射、灯效、完整PRD、6个Sheet
""",
    tags=["internal", "prd", "product_definition", "spec_template"],
    source="user_defined",
    confidence="authoritative"
)
print("✅ PRD规格书模板已导入知识库")
PYEOF
```

---

## 验证

```bash
python -c "
from scripts.feishu_handlers.structured_doc import (
    _gen_sheet3_state_scenarios, _gen_sheet4_voice_commands,
    _gen_sheet5_button_mapping, _gen_sheet6_light_effects,
    _export_to_excel, _write_generic_sheet, _write_feature_sheet,
    try_structured_doc_fast_track
)
print('所有函数存在 OK')
"
```

重启后飞书测试提示词：
"请输出头盔项目完整软件功能PRD规格书，Excel格式，包含6个Sheet：HUD功能、App功能、状态场景对策、语音指令表、按键映射表、灯效定义表。用于给UIUX设计公司和软件研发沟通需求。"
