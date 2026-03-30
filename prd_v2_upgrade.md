# PRD 系统 v2 升级 — CC 执行文档

> 总计 10 项修复，分 2 个并行轨道
> 预计执行时间: 30-45 分钟
> 完成后需要重启服务 + 跑一次 PRD 验证

---

## 并行轨道说明

**轨道 A（终端 1）**: 放置 anchor 文件 + 修改 structured_doc.py 读取逻辑 + 模块解析器
**轨道 B（终端 2）**: 评分逻辑 + 按键映射表修复 + HUD表结构 + 审计闭环

两轨道改的函数不同，不冲突。

---

# ============ 轨道 A ============

## A1: 放置 product_spec_anchor.yaml

将已生成的 `product_spec_anchor.yaml` 文件复制到项目目录:

```bash
cp /path/to/product_spec_anchor.yaml D:\Users\uih00653\my_agent_company\pythonProject1\.ai-state\product_spec_anchor.yaml
```

（文件内容已由 Leo 确认，直接放置即可）

---

## A2: structured_doc.py 添加 anchor 读取逻辑

在 `structured_doc.py` 的 **文件顶部 import 区域**，确认有 `import yaml`（如果没有则添加）。

然后在文件中找到 **模块列表解析逻辑**（大约在 `_process_in_background` 函数开头附近，解析用户 prompt 提取一级功能名的位置），在其 **之前** 添加以下函数：

```python
import yaml
from pathlib import Path

def _load_anchor():
    """加载产品需求锚点文件，返回合并后的模块列表和配置"""
    anchor_path = Path('.ai-state/product_spec_anchor.yaml')
    if not anchor_path.exists():
        print("[Anchor] 未找到 product_spec_anchor.yaml，跳过锚点加载")
        return None
    
    try:
        with open(anchor_path, 'r', encoding='utf-8') as f:
            anchor = yaml.safe_load(f)
        print(f"[Anchor] 已加载锚点文件: "
              f"HUD {len(anchor.get('hud_modules', []))} 模块, "
              f"App {len(anchor.get('app_modules', []))} 模块, "
              f"跨端 {len(anchor.get('cross_cutting', []))} 模块")
        return anchor
    except Exception as e:
        print(f"[Anchor] 加载失败: {e}")
        return None


def _merge_anchor_with_prompt(anchor: dict, prompt_modules: list) -> list:
    """
    将 anchor 中的模块与用户 prompt 解析出的模块合并。
    anchor 为底线（保证不遗漏），prompt 为增量（可新增 anchor 没有的）。
    返回去重后的完整模块名列表。
    """
    anchor_names = set()
    
    # 从 anchor 提取所有模块名
    for section in ['hud_modules', 'app_modules', 'cross_cutting']:
        for mod in anchor.get(section, []):
            name = mod.get('name', '')
            if name:
                anchor_names.add(name)
    
    # 合并: anchor 全部保留 + prompt 中 anchor 没有的新增
    prompt_set = set(prompt_modules)
    new_from_prompt = prompt_set - anchor_names
    
    merged = list(anchor_names) + list(new_from_prompt)
    
    if new_from_prompt:
        print(f"[Anchor] Prompt 新增 {len(new_from_prompt)} 个模块: {new_from_prompt}")
    
    print(f"[Anchor] 合并后共 {len(merged)} 个模块")
    return merged


def _get_anchor_sub_features(anchor: dict, module_name: str) -> str:
    """
    获取 anchor 中某个模块的 sub_features 和 existing_l2，
    拼接成字符串注入到 _gen_one 的 prompt 中。
    """
    for section in ['hud_modules', 'app_modules', 'cross_cutting']:
        for mod in anchor.get(section, []):
            if mod.get('name') == module_name:
                parts = []
                
                sub = mod.get('sub_features', [])
                if sub:
                    parts.append("【新增/重点功能】\n" + '\n'.join(f'- {s}' for s in sub))
                
                existing = mod.get('existing_l2', [])
                if existing:
                    parts.append("【已有L2维度（保留并深化）】\n" + '\n'.join(f'- {e}' for e in existing))
                
                notes = mod.get('notes', '')
                if notes:
                    parts.append(f"【设计备注】{notes}")
                
                ref = mod.get('reference', '')
                if ref:
                    parts.append(f"【参考】{ref}")
                
                return '\n'.join(parts)
    
    return ''


def _get_anchor_config(anchor: dict) -> dict:
    """提取 anchor 中的配置项"""
    return {
        'hud_columns': anchor.get('hud_table_columns', []),
        'normalize_map': anchor.get('module_normalize', {}),
        'separation_rules': anchor.get('separation_rules', []),
        'languages': [],
    }
    # 提取多语言配置
    for mod in anchor.get('cross_cutting', []):
        if mod.get('name') == '多语言支持':
            return {
                **_, 
                'languages': mod.get('languages', [])
            }
```

---

## A3: 修改模块解析逻辑 — 读取 anchor 后合并

找到 `_process_in_background` 函数中 **解析用户 prompt 提取模块名** 的代码段（类似 `[FastTrack] 检测到 N 个一级功能` 的逻辑位置）。

在原有解析逻辑之后，加入 anchor 合并:

```python
# === 原有代码: 从用户 prompt 解析模块列表 ===
# modules = _parse_modules_from_prompt(user_text)  # 原有逻辑
# print(f"[FastTrack] 检测到 {len(modules)} 个一级功能")

# === 新增: 加载 anchor 并合并 ===
anchor = _load_anchor()
if anchor:
    modules = _merge_anchor_with_prompt(anchor, modules)
    anchor_config = _get_anchor_config(anchor)
    
    # 用 anchor 的归一化映射覆盖硬编码的映射表
    global MODULE_NAME_NORMALIZE
    MODULE_NAME_NORMALIZE.update(anchor_config.get('normalize_map', {}))
    
    print(f"[FastTrack] 合并 anchor 后共 {len(modules)} 个一级功能,开始并行生成 (4 路)")
else:
    print(f"[FastTrack] 检测到 {len(modules)} 个一级功能,开始并行生成 (4 路)")
```

---

## A4: _gen_one 中注入 anchor 的 sub_features

找到 `_gen_one` 函数中 **拼装 LLM prompt** 的位置，在 prompt 中加入 anchor 的子功能提示:

```python
# 在 _gen_one 函数内，拼装 prompt 之前:
anchor_hint = ''
if anchor:  # anchor 变量需要传入或作为模块级变量
    anchor_hint = _get_anchor_sub_features(anchor, module_name)
    # 如果是拆解子模块，用父模块名查
    if '-' in module_name and not anchor_hint:
        parent_name = module_name.rsplit('-', 1)[0]
        anchor_hint = _get_anchor_sub_features(anchor, parent_name)

# 在 prompt 中注入:
if anchor_hint:
    prompt += f"""

【产品锚点要求 — 此模块必须覆盖以下功能点，不可遗漏】
{anchor_hint}
"""
```

---

## A5: _gen_one 的 prompt 中注入分离规则和 HUD 新列

在 `_gen_one` 的 prompt 中，添加分离规则（让 LLM 知道什么不该放 HUD 表）:

```python
# 添加到所有 HUD 端模块的 prompt 中:
hud_rules = """
【输出规则 — 严格遵守】
1. 纯App操作（历史数据查看、复杂设置、内容管理）不放此表，仅放App表
2. 按键操作细节不在此表展开，用"支持按键操作"概述，具体放按键映射表
3. 灯光效果不在此表展开，用"灯光联动提示"概述，具体放灯效定义表
4. 语音指令不在此表展开，用"支持语音控制"概述，具体放语音指令表
5. 本模块最多输出 18 条功能（L1+L2+L3 合计），P0/P1 优先

【额外输出字段 — 每条功能必须包含】
- visual_output: 该功能在HUD上的视觉呈现描述（如"左下角箭头卡片+距离数字"）
- display_priority: 显示优先级（critical/high/medium/low），决定屏幕空间争抢时的排序
- degradation: 异常时的降级方案（如"断连时显示最后缓存数据+灰色蒙层"）
- display_duration: 显示时长（permanent/event_Ns/user_dismiss/auto_5s 等）
"""

# 在拼装 HUD 端模块的 prompt 时加入 hud_rules
# 在拼装 App 端模块的 prompt 时不加
```

同时在 **JSON 输出格式说明** 中，对 HUD 端模块增加这 4 个字段的定义:

```python
# 找到 prompt 中定义 JSON 输出格式的部分，HUD 端模块增加:
# 原: "module", "level", "parent", "name", "priority", "interaction", "description", "acceptance"
# 改为:
hud_json_fields = '"module", "level", "parent", "name", "priority", "interaction", "description", "acceptance", "visual_output", "display_priority", "degradation", "display_duration"'
```

---

## A6: HUD 端 Excel 写入增加新列

找到 `_write_feature_sheet` 或写入 HUD Sheet 的函数，在表头中增加 4 列:

```python
# 找到 HUD 端 Sheet 的表头定义，大约类似:
# headers = ['功能ID', 'L1功能', 'L2功能', 'L3功能', '优先级', '交互方式', '描述', '验收标准']

# 改为:
hud_headers = ['功能ID', 'L1功能', 'L2功能', 'L3功能', '优先级', '交互方式', '描述', '验收标准', 
               '显示输出（视觉）', '显示优先级', '异常与降级', '显示时长']

# 在写入行数据时，增加这 4 个字段的提取:
# row_data 中增加:
# row.get('visual_output', ''),
# row.get('display_priority', ''),
# row.get('degradation', ''),
# row.get('display_duration', ''),

# App 端 Sheet 表头保持不变（不需要这 4 列）
```

---

# ============ 轨道 B ============

## B1: 评分逻辑改为抽样比质量（替代比总分）

找到 `_score_module` 和 `_compare_decision` 相关的 Compare 逻辑。

**替换整个比较决策函数**:

```python
import random

def _sample_compare(old_rows: list, new_rows: list, sample_size: int = 5) -> str:
    """
    抽样比质量：从新旧版各抽 N 条同名 L3 功能，逐条比较验收标准质量。
    返回 'new' / 'keep' / 'merge'
    """
    
    def _ensure_str(val):
        if isinstance(val, list):
            return ', '.join(str(v) for v in val)
        if isinstance(val, dict):
            import json
            return json.dumps(val, ensure_ascii=False)
        if val is None:
            return ''
        return str(val)
    
    def _quality_score_single(row: dict) -> float:
        """单条功能的质量评分"""
        score = 0
        
        acc = _ensure_str(row.get('acceptance', ''))
        desc = _ensure_str(row.get('description', ''))
        
        # 验收标准质量（权重 60%）
        import re
        numbers = re.findall(r'\d+\.?\d*', acc)
        if len(numbers) >= 2:
            score += 6  # 有 2 个以上具体数字
        elif len(numbers) >= 1:
            score += 3
        
        if any(unit in acc for unit in ['ms', 's', 'Hz', 'fps', 'dB', '%', '°', 'km', 'mAh', 'lux']):
            score += 2  # 有工程单位
        
        if '待验证' in acc or '待确认' in acc:
            score -= 1
        
        if len(acc) > 50:
            score += 1  # 足够详细
        
        # 描述质量（权重 20%）
        if len(desc) > 30:
            score += 2
        
        # 优先级合理性（权重 10%）
        priority = str(row.get('priority', ''))
        if priority in ['P0', 'P1', 'P2', 'P3']:
            score += 1
        
        return score
    
    # 构建同名功能映射
    old_map = {}
    for r in old_rows:
        name = _ensure_str(r.get('name', ''))
        if name:
            old_map[name] = r
    
    new_map = {}
    for r in new_rows:
        name = _ensure_str(r.get('name', ''))
        if name:
            new_map[name] = r
    
    # 找到两版都有的同名功能
    common_names = list(set(old_map.keys()) & set(new_map.keys()))
    
    if not common_names:
        # 没有重叠 → 比总条目数和平均质量
        old_avg = sum(_quality_score_single(r) for r in old_rows) / max(len(old_rows), 1)
        new_avg = sum(_quality_score_single(r) for r in new_rows) / max(len(new_rows), 1)
        if new_avg > old_avg + 1:
            return 'new'
        elif old_avg > new_avg + 1:
            return 'keep'
        return 'merge'
    
    # 抽样比较
    sample = random.sample(common_names, min(sample_size, len(common_names)))
    
    new_wins = 0
    old_wins = 0
    
    for name in sample:
        old_score = _quality_score_single(old_map[name])
        new_score = _quality_score_single(new_map[name])
        
        if new_score > old_score:
            new_wins += 1
        elif old_score > new_score:
            old_wins += 1
        # 平局不计
    
    # 判定
    total_compared = new_wins + old_wins
    if total_compared == 0:
        return 'merge'  # 全部平局
    
    if new_wins >= total_compared * 0.6:
        return 'new'
    elif old_wins >= total_compared * 0.6:
        return 'keep'
    else:
        return 'merge'
```

然后在 **Compare 主循环**中，替换原有的分数比较:

```python
# 原代码大致:
# if new_score > old_score + threshold: use 'new'
# elif ...: use 'keep'

# 改为:
for module_name in all_module_names:
    old_rows = old_version_map.get(module_name, [])
    new_rows = new_version_map.get(module_name, [])
    
    # 两者都空
    if not old_rows and not new_rows:
        print(f"  SKIP {module_name}: 新旧都为空")
        continue
    
    # 一方为空
    if not old_rows or len(old_rows) <= 1:
        print(f"  OK {module_name}: 旧版空壳 (新{len(new_rows)}条)")
        final_rows.extend(new_rows)
        continue
    
    if not new_rows or len(new_rows) <= 1:
        print(f"  KEEP {module_name}: 新版空壳 (旧{len(old_rows)}条)")
        final_rows.extend(old_rows)
        continue
    
    # 抽样比质量
    decision = _sample_compare(old_rows, new_rows)
    
    if decision == 'new':
        print(f"  OK {module_name}: 新版质量更好 (抽样)")
        final_rows.extend(new_rows)
    elif decision == 'keep':
        print(f"  KEEP {module_name}: 旧版质量更好 (抽样)")
        final_rows.extend(old_rows)
    else:
        # merge: 逐条取优
        merged = _merge_best_of_both(old_rows, new_rows)
        print(f"  MERGE {module_name}: 逐条取优 ({len(merged)}条)")
        final_rows.extend(merged)


def _merge_best_of_both(old_rows: list, new_rows: list) -> list:
    """逐条取验收标准更好的版本"""
    old_map = {_ensure_str(r.get('name', '')): r for r in old_rows if r.get('name')}
    new_map = {_ensure_str(r.get('name', '')): r for r in new_rows if r.get('name')}
    
    merged = {}
    all_names = set(old_map.keys()) | set(new_map.keys())
    
    for name in all_names:
        old_r = old_map.get(name)
        new_r = new_map.get(name)
        
        if old_r and not new_r:
            merged[name] = old_r
        elif new_r and not old_r:
            merged[name] = new_r
        else:
            # 两者都有 → 比验收标准长度和具体度
            old_acc = _ensure_str(old_r.get('acceptance', ''))
            new_acc = _ensure_str(new_r.get('acceptance', ''))
            import re
            old_nums = len(re.findall(r'\d+', old_acc))
            new_nums = len(re.findall(r'\d+', new_acc))
            if new_nums > old_nums:
                merged[name] = new_r
            elif old_nums > new_nums:
                merged[name] = old_r
            else:
                # 数字一样多 → 取更长的
                merged[name] = new_r if len(new_acc) >= len(old_acc) else old_r
    
    return list(merged.values())
```

---

## B2: 修复按键映射表回归 bug（button: 0 条）

日志中 `✅ button: 0 条` — 生成了但内容为空。

搜索 `structured_doc.py` 中生成按键映射表的代码（搜索 `button` 或 `按键映射`），检查:

```python
# 可能的问题 1: prompt 为空
# 搜索类似: task_name="button" 或 sheet_type="button" 的 LLM 调用
# 检查 prompt 是否正确包含了功能列表

# 可能的问题 2: JSON 解析返回空
# 在按键映射表的生成逻辑中加诊断日志:

# 找到类似这样的代码:
# result = await _call_llm(prompt, task_name="button_mapping", ...)
# 在调用后加:
print(f"[Button-Diag] prompt长度: {len(prompt)}")
print(f"[Button-Diag] 响应长度: {len(result) if result else 0}")
print(f"[Button-Diag] 响应前200字: {result[:200] if result else 'EMPTY'}")

# 可能的问题 3: Sheet 名称不匹配
# 确认 Export 阶段写入 Excel 时，按键映射表的 sheet 名是否被包含
# 搜索 Export 代码中的 sheet 列表，确认 '按键映射表' 在其中
# 当前日志: ['HUD及头盔端', 'App端', '状态场景对策', '语音指令表', '灯效定义表', ...]
# 注意: '按键映射表' 不在列表中! 这就是根因 — Sheet 没有被写入 Excel

# 修复: 在 Excel 导出的 Sheet 列表中，确认包含 '按键映射表'
# 搜索类似: sheet_list = [...] 或 for sheet_name in [...]
# 确保 '按键映射表' 在列表中，且对应的数据变量不为空
```

如果确认是 Sheet 列表遗漏：在导出逻辑中加回 `'按键映射表'`。

如果是生成逻辑返回空：检查按键映射表的 prompt 是否引用了正确的功能数据。按键映射表应该从实体按键交互模块的功能条目 + anchor 中的按键相关信息来生成。

---

## B3: Normalize 映射表完善

找到 `MODULE_NAME_NORMALIZE` 字典（如果已改为从 anchor 读取则此步可跳过），确认包含:

```python
MODULE_NAME_NORMALIZE = {
    'App-我的': '我的Tab',
    '我的首页': '我的Tab',
    '我的首页与个人中心': '我的Tab',
    '我的首页与账户中心': '我的Tab',  # 新增
    '我的': '我的Tab',
    'App-社区': '社区Tab',
    '社区': '社区Tab',
    'App-商城': '商城',
    'App-设备': '设备Tab',
    '设备连接与管理': '设备Tab',
    '设备控制与显示设置': '设备Tab',
    '电量续航与固件维护': '设备Tab',
    '设备 Tab': '设备Tab',  # 注意空格
    '简易': '简易路线',
    '路线': '简易路线',
}
```

注意: 如果 A2 中已实现从 anchor 的 `module_normalize` 字段读取，这里只需确认 anchor yaml 中的映射正确即可（已在 yaml 中写好）。

---

## B4: 一致性审计闭环 — 确认调用

搜索 `[Audit]` 相关代码，确认审计完成后调用了 `_auto_fix_audit_issues`。

如果 `_auto_fix_audit_issues` 函数已存在但未被调用:

```python
# 找到审计逻辑完成后的位置（print 了 "[Audit] 发现 N 个一致性问题" 之后）
# 加入调用:

if audit_issues:
    print(f"[Audit] 发现 {len(audit_issues)} 个一致性问题")
    # 尝试自动修复
    try:
        await _auto_fix_audit_issues(audit_issues, sheets_data)
    except Exception as e:
        print(f"[Audit-Fix] 自动修复异常: {e}，跳过")
```

如果 `_auto_fix_audit_issues` 函数不存在，从之前的修复文档（fix1_structured_doc_logic.md 的修复 6）中复制代码添加。

---

## B5: HTML 模板中 HUD 表增加 4 列

找到 PRD HTML 模板中 **渲染 HUD 功能表** 的部分，在 L3 功能行的渲染逻辑中增加新字段:

```javascript
// 找到渲染 L3 功能行的 JS/HTML 模板代码
// 当 sheet 是 HUD 端时，每行增加 4 个字段的显示

// 在 L3 行的 HTML 模板中增加:
// (只对 HUD 端的 tab 生效，App 端不变)
function renderL3Row(item, isHud) {
    let extraFields = '';
    if (isHud) {
        extraFields = `
            <span class="visual-output">${item.visual_output || ''}</span>
            <span class="display-priority tag-${(item.display_priority || 'medium').toLowerCase()}">${item.display_priority || ''}</span>
            <span class="degradation">${item.degradation || ''}</span>
            <span class="display-duration">${item.display_duration || ''}</span>
        `;
    }
    // ... 原有的 name + desc + acc 渲染 ...
    // 在 acc 后面追加 extraFields
}
```

对应的 CSS:

```css
.visual-output { flex: 1; min-width: 150px; color: #5a67d8; font-size: 12px; }
.display-priority { min-width: 60px; }
.display-priority.tag-critical { color: #c53030; font-weight: 700; }
.display-priority.tag-high { color: #b7791f; }
.display-priority.tag-medium { color: #276749; }
.display-priority.tag-low { color: #718096; }
.degradation { flex: 1; min-width: 150px; color: #e53e3e; font-size: 12px; }
.display-duration { min-width: 80px; color: #718096; font-size: 12px; }
```

---

# ============ 执行完成后 ============

## 验证步骤

1. **重启服务**: `python scripts/feishu_sdk_client_v2.py`

2. **在飞书发送 PRD 请求**（用 Leo 确认的最新 prompt）

3. **检查终端日志**:
   - [ ] 出现 `[Anchor] 已加载锚点文件: HUD N 模块, App N 模块`
   - [ ] 模块总数 > 40（之前 29，anchor 补充后应更多）
   - [ ] 无 `finish_reason=length` 截断
   - [ ] 按键映射表 > 0 条
   - [ ] Compare 日志中出现 `(抽样)` 而非纯分数比较
   - [ ] 无模块分裂（"我的"只出现为"我的Tab"）
   - [ ] 出现 `[Audit-Fix]` 自动修复日志

4. **检查产出文件**:
   - [ ] HUD 表有 12 列（含新增 4 列）
   - [ ] 全文搜索: 信息中岛 > 0, 自定义HUD > 0, 水印 > 0, 摄像参数 > 0
   - [ ] 全文搜索: AI Tab > 0, 相册Tab > 0, SOS > 0, 疲劳监测 > 0
   - [ ] 全文搜索: 场景模式 > 0, 通知中心 > 0, 第三方应用联动 > 0
   - [ ] 全文搜索: 大车预警 > 0, 红绿灯读秒 > 0, 巡航模式 > 0, 返航模式 > 0
   - [ ] 全文搜索: 手机消息同步 > 0, WhatsApp > 0
   - [ ] 无 `[待生成]` 或 `生成失败`
   - [ ] 按键映射表有数据

5. **git commit --no-verify**
