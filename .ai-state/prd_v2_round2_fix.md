# PRD v2 首轮验证修复 — CC 执行文档

> 7 个问题，分 2 个并行轨道
> 轨道 A: 结构性修复（App/HUD分离 + 旧数据归一化 + 新列回填）
> 轨道 B: 功能性修复（流程图函数名 + 灯效灯区列 + 缺失功能强化 + 导航拆解）

---

# ============ 轨道 A ============

## A1（P0）: App/HUD 分离逻辑

**根因**: `_gen_one` 把 anchor 中所有模块都写入 HUD 表。14 个纯 App 模块（AI Tab、相册Tab、社区Tab 等）全进了 HUD 表，App 表只有旧版 313 行。

**修法**: 在模块生成和写入时，根据 anchor 的 section 分类决定归属。

### Step 1: 在 _load_anchor 后构建模块归属映射

在 `_process_in_background` 中加载 anchor 之后，构建一个 dict 记录每个模块归属 HUD 还是 App：

```python
# 在 anchor = _load_anchor() 之后:

def _build_module_placement(anchor: dict) -> dict:
    """
    根据 anchor 的 section 分类，决定每个模块写入 HUD表 还是 App表。
    返回 {module_name: 'hud' | 'app'}
    """
    placement = {}
    
    # HUD 端模块
    for mod in anchor.get('hud_modules', []):
        placement[mod['name']] = 'hud'
    
    # App 端模块
    for mod in anchor.get('app_modules', []):
        placement[mod['name']] = 'app'
    
    # 跨端模块：根据性质分配
    cross_to_hud = {'AI功能', '语音交互', '视觉交互', '多模态交互', '实体按键交互', '氛围灯交互'}
    cross_to_app = {'多语言支持', '手机系统权限管理', '部件识别与兼容性管理'}
    
    for mod in anchor.get('cross_cutting', []):
        name = mod['name']
        if name in cross_to_hud:
            placement[name] = 'hud'
        elif name in cross_to_app:
            placement[name] = 'app'
        else:
            # 默认：如果名字含 Tab/App/手机/用户/商城/社区 → app，否则 hud
            if any(kw in name for kw in ['Tab', 'App', '手机', '商城', '社区', '通知', '用户成就', '用户学习', '新手', '身份', '权限']):
                placement[name] = 'app'
            else:
                placement[name] = 'hud'
    
    # Prompt 新增的模块（不在 anchor 中）也需要判断
    # 这些通过名称推断
    
    hud_count = sum(1 for v in placement.values() if v == 'hud')
    app_count = sum(1 for v in placement.values() if v == 'app')
    print(f"[Placement] HUD: {hud_count} 模块, App: {app_count} 模块")
    
    return placement

# 调用:
if anchor:
    module_placement = _build_module_placement(anchor)
else:
    module_placement = {}
```

### Step 2: 在收集结果时按归属分流

找到 `_gen_one` 结果收集后的位置（all_rows 汇总处），将 rows 按归属分为两组：

```python
# 原代码可能是:
# all_rows.extend(rows)

# 改为: 给每条 row 打上 placement 标记
hud_rows = []
app_rows = []

for row in all_rows:
    module_name = row.get('module', '')
    # 查归属，未找到的默认按名字推断
    target = module_placement.get(module_name, '')
    if not target:
        # 兜底推断
        if any(kw in module_name for kw in ['Tab', 'App-', '商城', '社区', '通知', '用户成就', '新手', '身份', '权限', '部件识别', '消息同步', '多语言', '恢复出厂']):
            target = 'app'
        else:
            target = 'hud'
    
    if target == 'hud':
        hud_rows.append(row)
    else:
        app_rows.append(row)

print(f"[Placement] 分流结果: HUD {len(hud_rows)} 条, App {len(app_rows)} 条")
```

### Step 3: 写入 Excel 时用分流后的数据

找到写入 HUD Sheet 和 App Sheet 的代码：

```python
# 原代码可能是:
# _write_feature_sheet(ws_hud, all_rows, is_hud=True)
# _write_feature_sheet(ws_app, old_app_rows, is_hud=False)  # App 用的旧数据

# 改为:
_write_feature_sheet(ws_hud, hud_rows, is_hud=True)   # 只放 HUD 模块
_write_feature_sheet(ws_app, app_rows, is_hud=False)   # 放 App 模块（新+旧合并后）
```

**同时**确保 App 的 `_write_feature_sheet` 不输出 HUD 的 4 个新列（显示输出/显示优先级/异常与降级/显示时长）。

---

## A2（P1）: 旧版继承数据的归一化

**根因**: Normalize 只处理了新生成的模块，从旧版 Compare 继承来的 App 端数据仍有 "我的"/"我的首页"/"我的首页与个人中心" 等重复。

**修法**: 在 Compare 完成后、写入 Excel 前，对所有数据（包括旧版继承的）做一次全量归一化。

```python
# 在 [Compare] 最终结果确定后，写入 Excel 前:

def _normalize_all_rows(rows: list, normalize_map: dict) -> list:
    """对所有行的 module 字段做归一化，然后合并同名模块去重"""
    # Step 1: 归一化 module 名
    for row in rows:
        module = row.get('module', '')
        if module in normalize_map:
            row['module'] = normalize_map[module]
    
    # Step 2: 按归一化后的 module 分组去重
    from collections import defaultdict
    groups = defaultdict(list)
    for row in rows:
        groups[row.get('module', 'unknown')].append(row)
    
    deduped = []
    for module_name, group_rows in groups.items():
        # 按 name (L3功能名) 去重
        seen = {}
        for row in group_rows:
            name = str(row.get('name', ''))
            if name in seen:
                # 保留验收标准更长的
                old_acc = str(seen[name].get('acceptance', ''))
                new_acc = str(row.get('acceptance', ''))
                if len(new_acc) > len(old_acc):
                    seen[name] = row
            else:
                seen[name] = row
        deduped.extend(seen.values())
    
    original = len(rows)
    final = len(deduped)
    if original != final:
        print(f"[NormalizeAll] {original} → {final} 条 (去重 {original - final})")
    
    return deduped

# 使用 anchor 中的 normalize_map:
normalize_map = anchor.get('module_normalize', {}) if anchor else {}
# 补充代码中硬编码的映射
normalize_map.update({
    'App-我的': '我的Tab',
    '我的': '我的Tab',
    '我的首页': '我的Tab',
    '我的首页与个人中心': '我的Tab',
    '我的首页与账户中心': '我的Tab',
    'App-社区': '社区Tab',
    '社区': '社区Tab',
    'App-商城': '商城',
    'App-设备': '设备Tab',
    '设备连接与管理': '设备Tab',
    '设备控制与显示设置': '设备Tab',
    '电量续航与固件维护': '设备Tab',
    '设备 Tab': '设备Tab',
    '用户学习': '用户学习与新手引导',
    '简易': '简易路线',
})

all_rows = _normalize_all_rows(all_rows, normalize_map)
```

---

## A3（P1）: HUD 新 4 列回填

**根因**: 从旧版继承的 HUD 模块行没有 `visual_output`/`display_priority`/`degradation`/`display_duration` 字段，导致 186/1109 = 17% 填充率。

**修法**: 对缺少新字段的行，用规则填默认值（不调 LLM，速度快）。

```python
def _backfill_hud_columns(hud_rows: list) -> list:
    """为缺少 HUD 新 4 列的行填充默认值"""
    filled_count = 0
    
    for row in hud_rows:
        changed = False
        
        # 显示输出（视觉）
        if not row.get('visual_output') or len(str(row.get('visual_output', ''))) < 3:
            # 根据交互方式推断
            interaction = str(row.get('interaction', ''))
            name = str(row.get('name', ''))
            if 'HUD' in interaction or 'HUD' in name:
                row['visual_output'] = 'HUD卡片/图标显示'
            elif '语音' in interaction:
                row['visual_output'] = '无视觉输出（纯语音）'
            elif '按键' in interaction:
                row['visual_output'] = 'HUD操作反馈'
            elif '灯' in interaction or '灯' in name:
                row['visual_output'] = '灯效反馈'
            else:
                row['visual_output'] = 'HUD状态提示'
            changed = True
        
        # 显示优先级
        if not row.get('display_priority') or len(str(row.get('display_priority', ''))) < 2:
            priority = str(row.get('priority', 'P2'))
            priority_map = {'P0': 'critical', 'P1': 'high', 'P2': 'medium', 'P3': 'low'}
            row['display_priority'] = priority_map.get(priority, 'medium')
            changed = True
        
        # 异常与降级
        if not row.get('degradation') or len(str(row.get('degradation', ''))) < 3:
            row['degradation'] = '功能不可用时隐藏对应卡片，不影响其他功能'
            changed = True
        
        # 显示时长
        if not row.get('display_duration') or len(str(row.get('display_duration', ''))) < 2:
            name = str(row.get('name', ''))
            if any(kw in name for kw in ['预警', '告警', '提醒', '通知', '来电']):
                row['display_duration'] = 'event_5s'
            elif any(kw in name for kw in ['速度', '导航', '电量', '状态']):
                row['display_duration'] = 'permanent'
            else:
                row['display_duration'] = 'user_dismiss'
            changed = True
        
        if changed:
            filled_count += 1
    
    print(f"[Backfill] HUD新列回填: {filled_count}/{len(hud_rows)} 行")
    return hud_rows

# 在分流后、写入前调用:
hud_rows = _backfill_hud_columns(hud_rows)
```

---

# ============ 轨道 B ============

## B1（P0）: 流程图函数名修复

**根因**: `_generate_flow_diagrams` 中调用了 `_call_llm`，但实际函数名不同。

```bash
# 先找到实际的 LLM 调用函数名
grep -rn "async def.*call.*llm\|def.*call.*azure\|def.*call.*gemini\|def.*model_gateway" scripts/feishu_handlers/structured_doc.py | head -10
```

找到实际函数名后（假设是 `_call_model` 或 `call_azure` 或其他），做全局替换：

```bash
# 假设实际函数名是 _call_model_gateway（根据 grep 结果替换）
sed -i 's/_call_llm(/_call_model_gateway(/g' scripts/feishu_handlers/structured_doc.py
```

**或者**如果函数签名不一致，在 `_generate_flow_diagrams` 函数开头加一个适配层：

```python
async def _generate_flow_diagrams(anchor: dict) -> list:
    # 找到实际可用的 LLM 调用方式，加适配
    # 方式1: 如果有全局的 model_gateway
    from src.utils.model_gateway import call_model
    
    async def _call_llm(prompt, task_name, max_tokens):
        return await call_model(
            prompt=prompt,
            model='azure_gpt4o',  # 或实际使用的模型标识
            task=task_name,
            max_tokens=max_tokens
        )
    
    # ... 原有逻辑不变 ...
```

**最简单的方式**: 搜索同文件中其他地方是怎么调 LLM 的（比如 `_gen_one` 函数内），复制那个调用方式：

```bash
# 看 _gen_one 怎么调 LLM 的
grep -A5 "Azure-Diag\|call.*model\|call.*azure\|completion" scripts/feishu_handlers/structured_doc.py | head -30
```

照抄那个写法替换 `_call_llm`。

**同样的修复也适用于 `_generate_user_journeys`**（如果也报同样错误的话）。不过 user_journeys 不调 LLM（纯拼接），所以可能不受影响。但要确认 `_generate_user_journeys` 函数是否已被添加到代码中——从日志看没有 `[UserJourney]` 输出，说明函数可能没被调用或不存在。

检查清单：
```bash
grep -n "UserJourney\|user_journey\|_generate_user_journeys\|ai_proactive_scenarios\|_write_journey\|_write_ai_scenarios" scripts/feishu_handlers/structured_doc.py
```

如果搜不到，说明修复 7（用户旅程）和修复 8（AI场景表）的代码还没被加进去。需要从 `prd_flow_diagrams_fix.md` 的修复 7 和修复 8 中复制代码添加。

---

## B2（P2）: 灯效表增加"作用灯区"列

找到灯效表的生成 prompt（搜索 `light` 或 `灯效` 相关的 LLM 调用）：

```python
# 在灯效表的 prompt 中，修改输出格式要求:

# 原 JSON 字段可能是:
# "trigger", "color", "mode", "frequency", "duration", "priority", "note"

# 改为增加 lamp_zone 字段:
light_prompt_addition = """
每条灯效必须包含 lamp_zone 字段，标明作用于哪个灯区:
- "后脑勺灯" — 制动、转向、后向告警、夜间常亮等安全类灯效
- "眼下方灯" — 语音助手状态、配对状态、通知提示、电量状态等反馈类灯效
- "双灯区" — SOS、开关机、充电完成等需要双灯协同的灯效
- "隐私灯" — 摄像头旁隐私指示灯（录像/拍照/ADAS时）

示例: {"trigger": "紧急制动", "color": "红", "mode": "高频闪", "frequency": "5.0", "duration": "制动期间", "priority": "P0", "lamp_zone": "后脑勺灯", "note": "IMU检测急减速触发"}
"""
# 注入到灯效生成的 prompt 中
```

同时在 `_write_light_sheet`（或等效函数）中增加 `灯区` 列：

```python
# 灯效表头改为:
light_headers = ['触发场景', '灯光颜色', '闪烁模式', '频率Hz', '持续时长', '作用灯区', '优先级', '备注']

# 写入时:
# ws.cell(row=i, column=6, value=row.get('lamp_zone', ''))
```

---

## B3（P1）: 缺失 5 个功能的 anchor 注入强化

**根因**: anchor 的 sub_features 注入到 prompt 中了，但 LLM 没有全部展开。需要更强的提醒。

找到 `_get_anchor_sub_features` 函数（在轨道 A 的修复中添加的），修改返回格式：

```python
def _get_anchor_sub_features(anchor: dict, module_name: str) -> str:
    for section in ['hud_modules', 'app_modules', 'cross_cutting']:
        for mod in anchor.get(section, []):
            if mod.get('name') == module_name:
                parts = []
                
                sub = mod.get('sub_features', [])
                if sub:
                    # 改为更强的指令语气
                    parts.append("【⚠️ 以下功能点必须全部出现在输出中，缺一不可 ⚠️】")
                    for i, s in enumerate(sub, 1):
                        parts.append(f'{i}. {s}')
                    parts.append(f"\n以上 {len(sub)} 个功能点中的每一个，至少对应输出 1 条 L2 或 L3 功能。如果某个功能点未出现在你的输出中，视为不合格。")
                
                existing = mod.get('existing_l2', [])
                if existing:
                    parts.append("\n【已有L2维度（保留并深化，但优先级低于上述必须功能点）】")
                    parts.append(', '.join(existing))
                
                notes = mod.get('notes', '')
                if notes:
                    parts.append(f"\n【设计备注】{notes}")
                
                return '\n'.join(parts)
    return ''
```

---

## B4（P2）: 导航拆解子模块仍撞 4096

导航-交互与状态、导航-异常与边界 都 `finish_reason=length`。

**根因**: 拆解子模块的 prompt 注入了 anchor 的 18 条 existing_l2，再加 KB 数据点 + 输出格式说明，prompt 太长导致输出空间不够。

**修法**: 拆解子模块的 prompt 不注入全量 anchor existing_l2，只注入与子维度相关的部分：

```python
# 在 _get_anchor_sub_features 中，当检测到是拆解子模块时，过滤 existing_l2

def _get_anchor_sub_features(anchor: dict, module_name: str) -> str:
    # 检测是否是拆解子模块
    is_split = '-' in module_name
    parent_name = module_name.rsplit('-', 1)[0] if is_split else module_name
    suffix = module_name.rsplit('-', 1)[1] if is_split else ''
    
    for section in ['hud_modules', 'app_modules', 'cross_cutting']:
        for mod in anchor.get(section, []):
            if mod.get('name') == parent_name or mod.get('name') == module_name:
                parts = []
                
                sub = mod.get('sub_features', [])
                if sub:
                    parts.append("【⚠️ 以下功能点必须全部出现在输出中 ⚠️】")
                    for i, s in enumerate(sub, 1):
                        parts.append(f'{i}. {s}')
                
                existing = mod.get('existing_l2', [])
                if existing:
                    if is_split:
                        # 拆解子模块：只保留相关的 existing_l2（最多 5 条）
                        suffix_keywords = {
                            '核心功能': ['核心', '功能', '规格', '展示', '显示', '控制'],
                            '交互与状态': ['交互', '状态', '反馈', 'HUD', '语音', '按键'],
                            '异常与边界': ['异常', '降级', '故障', '恢复', '边界', '兜底', '低电'],
                        }
                        keywords = suffix_keywords.get(suffix, [])
                        filtered = [e for e in existing if any(kw in e for kw in keywords)]
                        if not filtered:
                            filtered = existing[:5]  # 兜底取前5
                        parts.append(f"\n【相关L2维度（仅 {suffix} 相关）】")
                        parts.append(', '.join(filtered[:5]))
                    else:
                        parts.append("\n【已有L2维度】")
                        parts.append(', '.join(existing))
                
                return '\n'.join(parts)
    return ''
```

---

## B5: 确认用户旅程和 AI 场景表代码是否存在

```bash
# 检查这些函数和调用是否已在代码中
grep -c "_generate_user_journeys\|_write_journey_sheet\|_write_ai_scenarios_sheet\|ai_proactive_scenarios\|UserJourney" scripts/feishu_handlers/structured_doc.py
```

如果返回 0，说明 `prd_flow_diagrams_fix.md` 的修复 7（用户旅程）和修复 8（AI场景表）没有被 CC 添加。需要重新执行：

> 请阅读 prd_flow_diagrams_fix.md，执行修复 7（用户旅程图生成）和修复 8（主动AI场景表生成）的全部代码。确保函数被添加到 structured_doc.py 中，且在 _process_in_background 的额外 Sheet 生成阶段被调用。

---

# ============ 额外修复 ============

## C1: 飞书回复失败（receive_id invalid）

日志中有两次 `回复失败: invalid receive_id`。这是因为第一条消息没有 @bot（群聊中直接发了消息），系统尝试回复但 receive_id 不对。

找到回复逻辑，确保只回复有效的 message：

```python
# 在发送回复前检查:
if not chat_id and not open_id:
    print("[Reply] 无有效 receive_id，跳过回复")
    return
```

这不是本次重点，但能减少日志噪音。

---

## C2: JSON 解析失败

日志中有 `[Export] JSON 解析失败: Expecting value: line 1 column 2 (char 1)`。

这可能是某个 LLM 响应返回了非 JSON 内容。在 JSON 解析处加更强的防御：

```python
# 搜索 Export 相关的 json.loads 调用，确保有 try-except
try:
    data = json.loads(response_text)
except json.JSONDecodeError as e:
    print(f"[Export] JSON 解析失败: {e}")
    print(f"[Export] 原始响应前100字: {response_text[:100]}")
    data = []  # 降级为空，不中断整个流程
```

---

# ============ 验证清单 ============

修完后重启 + 跑 PRD，检查：

**结构性:**
- [ ] HUD 表只包含 HUD 端模块（导航/来电/音乐/消息/AI语音助手/信息中岛/自定义HUD/速度/组队/摄像/胎压/开机动画/设备状态/安全预警/显示队友/SOS/疲劳监测/场景模式/佩戴检测/日程提醒/恢复出厂/简易路线/路线）
- [ ] App 表包含 App 端模块（设备Tab/相册Tab/社区Tab/AI Tab/我的Tab/通知中心/第三方联动/消息同步/商城/身份认证/设备互联/设备配对/产品介绍/用户学习与新手引导/用户成就/多语言/权限管理/部件识别）
- [ ] App 表无模块分裂（"我的"只有"我的Tab"一个）
- [ ] HUD 4 新列填充率 > 80%

**功能性:**
- [ ] 出现"关键流程" Sheet（8 个流程图）
- [ ] 出现"用户旅程" Sheet（4 个角色）
- [ ] 出现"主动AI场景" Sheet（15 个场景）
- [ ] 灯效表有"作用灯区"列，标注后脑勺灯/眼下方灯/双灯区

**覆盖性:**
- [ ] 骑行/步行切换 > 0 条
- [ ] 隐私灯 > 0 条
- [ ] 后脑勺灯/眼下方灯 > 0 条
- [ ] 灯光开关权限（可关闭/不可关闭）> 0 条
- [ ] 用户信息采集（性别/出生/地区）> 0 条
- [ ] 海外售后/RMA > 0 条
- [ ] 无 `_call_llm is not defined` 错误
- [ ] 无 `finish_reason=length` 截断（或截断后成功拆解重试）
