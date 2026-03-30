# PRD v2 补充修复 — CC 在 Round2 A/B 完成后执行

> Round2 改的是分离/归一化/流程图/灯区/anchor强化
> 本文档改的是：版本继承/HTML滚动/取优逻辑/跨Sheet一致性/内容深度/去重闭环/页面映射
> 不冲突，Round2 commit 后直接执行本文档

---

## 修复 1: 版本信息继承上一版

找到 `_write_version_sheet` 函数（或版本信息 Sheet 的写入逻辑）：

```python
import os
import json
import re

def _get_previous_version_info(prd_versions_dir='.ai-state/prd_versions') -> dict:
    """读取上一版的版本号和功能统计，用于递增和 changelog"""
    if not os.path.exists(prd_versions_dir):
        return {}
    
    # 找最新的版本快照目录（按时间戳排序）
    snapshots = sorted(os.listdir(prd_versions_dir), reverse=True)
    if not snapshots:
        return {}
    
    latest = snapshots[0]  # 如 20260329_010055
    
    # 尝试读取上一版的版本信息
    # 可能存储在快照目录下的 version_info.json 或从 Excel 中提取
    version_info_path = os.path.join(prd_versions_dir, latest, 'version_info.json')
    if os.path.exists(version_info_path):
        with open(version_info_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    # 兜底：从快照目录名推断时间，版本号从 V1.0 开始递增
    return {
        'version': 'V1.0',
        'snapshot': latest,
        'total_features': 0,
    }


def _write_version_sheet_v2(ws, current_stats: dict, prev_info: dict):
    """写入版本信息，继承上一版并递增"""
    from datetime import datetime
    from openpyxl.styles import Font, PatternFill, Alignment
    
    # 版本号递增
    prev_version = prev_info.get('version', 'V1.0')
    match = re.search(r'V?(\d+)\.(\d+)', prev_version)
    if match:
        major, minor = int(match.group(1)), int(match.group(2))
        new_version = f"V{major}.{minor + 1}"
    else:
        new_version = "V1.1"
    
    # 生成 changelog
    changelog = []
    prev_total = prev_info.get('total_features', 0)
    curr_total = current_stats.get('total_features', 0)
    if prev_total > 0:
        diff = curr_total - prev_total
        changelog.append(f"功能总数: {prev_total} → {curr_total} ({'+' if diff >= 0 else ''}{diff})")
    else:
        changelog.append(f"功能总数: {curr_total} 条")
    
    new_modules = current_stats.get('new_modules', [])
    if new_modules:
        changelog.append(f"新增模块: {', '.join(new_modules[:10])}")
    
    updated_modules = current_stats.get('updated_modules', [])
    if updated_modules:
        changelog.append(f"更新模块: {', '.join(updated_modules[:10])}")
    
    audit_count = current_stats.get('audit_issues', 0)
    changelog.append(f"一致性问题: {audit_count} 个")
    
    # 写入 Sheet
    header_fill = PatternFill('solid', fgColor='4A5568')
    header_font = Font(bold=True, color='FFFFFF', size=11)
    
    rows = [
        ('版本', new_version),
        ('上一版本', prev_version),
        ('生成时间', datetime.now().strftime('%Y-%m-%d %H:%M')),
        ('功能总数', curr_total),
        ('HUD端功能', current_stats.get('hud_count', 0)),
        ('App端功能', current_stats.get('app_count', 0)),
        ('P0功能数', current_stats.get('p0', 0)),
        ('P1功能数', current_stats.get('p1', 0)),
        ('P2功能数', current_stats.get('p2', 0)),
        ('P3功能数', current_stats.get('p3', 0)),
        ('状态场景数', current_stats.get('state_count', 0)),
        ('语音指令数', current_stats.get('voice_count', 0)),
        ('按键映射数', current_stats.get('button_count', 0)),
        ('灯效定义数', current_stats.get('light_count', 0)),
        ('导航场景数', current_stats.get('nav_count', 0)),
        ('流程图数', current_stats.get('flow_count', 0)),
        ('用户旅程数', current_stats.get('journey_count', 0)),
        ('主动AI场景数', current_stats.get('ai_scenario_count', 0)),
        ('测试用例数', current_stats.get('test_count', 0)),
        ('开发任务数', current_stats.get('dev_count', 0)),
        ('', ''),
        ('本次主要改动', '; '.join(changelog)),
    ]
    
    # 版本历史追加（从上一版继承）
    prev_history = prev_info.get('history', [])
    if prev_version != 'V1.0':
        prev_history.append(f"{prev_version} ({prev_info.get('date', '未知')}): {prev_info.get('changelog', '无记录')}")
    
    if prev_history:
        rows.append(('', ''))
        rows.append(('历史版本记录', ''))
        for h in prev_history[-5:]:  # 最近 5 个版本
            rows.append(('', h))
    
    for i, (key, val) in enumerate(rows, 1):
        cell_key = ws.cell(row=i, column=1, value=key)
        cell_val = ws.cell(row=i, column=2, value=val)
        if i == 1:
            cell_key.font = Font(bold=True, size=12)
            cell_val.font = Font(bold=True, size=14, color='4A5568')
    
    ws.column_dimensions['A'].width = 18
    ws.column_dimensions['B'].width = 60
    
    # 保存版本信息到 JSON（供下一次继承）
    save_info = {
        'version': new_version,
        'date': datetime.now().strftime('%Y-%m-%d'),
        'total_features': curr_total,
        'changelog': '; '.join(changelog),
        'history': prev_history + [f"{new_version} ({datetime.now().strftime('%Y-%m-%d')}): {'; '.join(changelog)}"],
    }
    
    return save_info  # 调用方保存到 prd_versions/当前快照/version_info.json
```

在主流程中替换原有的版本信息写入：

```python
# 原: _write_version_sheet(ws, version_data)
# 改为:
prev_info = _get_previous_version_info()
version_save = _write_version_sheet_v2(ws_version, current_stats, prev_info)

# 在快照保存时一起存 version_info.json
version_json_path = os.path.join(snapshot_dir, 'version_info.json')
with open(version_json_path, 'w', encoding='utf-8') as f:
    json.dump(version_save, f, ensure_ascii=False, indent=2)
```

---

## 修复 2: HTML 页面滚动 + Tab 切换修复

找到 PRD HTML 模板中的 CSS 和 JS：

### CSS 修复

```css
/* 找到 .content 的样式，确保同时有这三个属性: */
.content {
    margin-top: 160px;  /* 初始值，会被 JS 动态更新 */
    padding: 16px 24px;
    max-width: 1600px;
    margin-left: auto;
    margin-right: auto;
    overflow-y: auto;   /* ← 关键: 必须有 */
    height: calc(100vh - 160px);  /* ← 关键: 必须有，会被 JS 更新 */
    -webkit-overflow-scrolling: touch;  /* iOS 惯性滚动 */
}

/* 确保 tabs 有正确的样式 */
.tabs {
    position: fixed;
    left: 0;
    right: 0;
    z-index: 999;
    background: #fff;
    border-bottom: 1px solid #e0e0e0;
    display: flex;
    overflow-x: auto;
    padding: 0 24px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    /* top 值由 JS 动态设置 */
}

/* Tab 按钮样式（确保可见可点击）*/
.tabs .tab {
    padding: 10px 16px;
    cursor: pointer;
    white-space: nowrap;
    font-size: 13px;
    color: #666;
    border-bottom: 2px solid transparent;
    transition: all 0.2s;
    flex-shrink: 0;
}
.tabs .tab.active {
    color: #667eea;
    border-bottom-color: #667eea;
    font-weight: 600;
}
.tabs .tab:hover {
    color: #667eea;
    background: #f7f8ff;
}
```

### JS 修复 — 确保 updateHeaderHeight 正确执行

```javascript
function updateHeaderHeight() {
    const header = document.querySelector('.header');
    const tabs = document.querySelector('.tabs');
    const content = document.querySelector('.content');
    
    if (!header || !tabs || !content) {
        console.error('Header/tabs/content element not found');
        return;
    }
    
    const headerH = header.getBoundingClientRect().height;
    const tabsH = tabs.getBoundingClientRect().height;
    const totalH = headerH + tabsH;
    
    // 设置 tabs 的 top
    tabs.style.top = headerH + 'px';
    
    // 设置 content 的 margin 和高度
    content.style.marginTop = totalH + 'px';
    content.style.height = (window.innerHeight - totalH) + 'px';
    content.style.overflowY = 'auto';
    
    console.log('Header:', headerH, 'Tabs:', tabsH, 'Total:', totalH);
}

// 确保在 DOM 完全加载后执行
document.addEventListener('DOMContentLoaded', function() {
    // 延迟100ms确保布局完成
    setTimeout(updateHeaderHeight, 100);
});
window.addEventListener('resize', updateHeaderHeight);
window.addEventListener('load', function() {
    setTimeout(updateHeaderHeight, 200);
});
```

### Tab 切换逻辑 — 确保所有 Tab 内容区域可切换

```javascript
// 找到 Tab 切换的 JS 函数（可能叫 switchTab/changeTab/showTab）
// 确保切换时:
function switchTab(tabName) {
    // 1. 更新 tab 按钮的 active 状态
    document.querySelectorAll('.tabs .tab').forEach(t => {
        t.classList.toggle('active', t.dataset.tab === tabName);
    });
    
    // 2. 切换内容区域
    document.querySelectorAll('.tab-content').forEach(c => {
        c.style.display = c.dataset.tab === tabName ? 'block' : 'none';
    });
    
    // 3. 滚动到顶部
    const content = document.querySelector('.content');
    if (content) content.scrollTop = 0;
    
    // 4. 如果是流程图/旅程图 tab，触发 Mermaid 渲染
    if (tabName === '关键流程' || tabName === '用户旅程') {
        if (typeof mermaid !== 'undefined') {
            setTimeout(() => mermaid.run(), 100);
        }
    }
}
```

---

## 修复 3: Compare KEEP 时吸收新版独有功能

找到 Compare 逻辑中 `decision == 'keep'` 的分支：

```python
# 原代码:
# if decision == 'keep':
#     final_rows.extend(old_rows)

# 改为:
if decision == 'keep':
    # 保留旧版全部内容
    final_rows.extend(old_rows)
    
    # 但扫描新版中旧版没有的 L3 功能名，追加进去
    old_names = {str(r.get('name', '')) for r in old_rows if r.get('name')}
    new_only = [r for r in new_rows if str(r.get('name', '')) not in old_names and r.get('name')]
    
    if new_only:
        # 只追加旧版没有的新功能（不替换已有的）
        final_rows.extend(new_only)
        new_names = [str(r.get('name', ''))[:20] for r in new_only[:5]]
        print(f"  KEEP+ {module_name}: 保留旧版 + 吸收 {len(new_only)} 条新增功能 ({', '.join(new_names)}...)")
    else:
        print(f"  KEEP {module_name}: 旧版质量更好 (抽样)")
```

同样在 `decision == 'new'` 时也做反向吸收：

```python
if decision == 'new':
    final_rows.extend(new_rows)
    
    # 扫描旧版中新版没有的功能，追加
    new_names = {str(r.get('name', '')) for r in new_rows if r.get('name')}
    old_only = [r for r in old_rows if str(r.get('name', '')) not in new_names and r.get('name')]
    
    if old_only:
        final_rows.extend(old_only)
        print(f"  OK+ {module_name}: 新版更好 + 保留旧版 {len(old_only)} 条独有功能")
```

---

## 修复 4: 跨 Sheet 一致性引擎（功能 ID 驱动）

在审计闭环 `_auto_fix_audit_issues` 之后，增加一个更全面的关联检查：

```python
def _cross_sheet_consistency_check(feature_rows: list, sheets_data: dict) -> dict:
    """
    扫描所有功能条目，检查是否需要在其他 Sheet 中有对应条目。
    返回需要补生成的条目列表。
    """
    gaps = {
        'voice': [],   # 缺少的语音指令
        'button': [],  # 缺少的按键映射
        'light': [],   # 缺少的灯效定义
        'test': [],    # 缺少的测试用例
    }
    
    # 已有的语音指令关键词
    existing_voice = set()
    for v in sheets_data.get('voice', []):
        existing_voice.add(str(v.get('user_say', v.get('用户说法', ''))))
    
    # 已有的灯效场景
    existing_light = set()
    for l in sheets_data.get('light', []):
        existing_light.add(str(l.get('trigger', l.get('触发场景', ''))))
    
    # 已有的测试用例覆盖的功能名
    existing_test_features = set()
    for t in sheets_data.get('test', []):
        existing_test_features.add(str(t.get('feature_name', t.get('功能名', ''))))
    
    for row in feature_rows:
        name = str(row.get('name', ''))
        desc = str(row.get('description', ''))
        interaction = str(row.get('interaction', ''))
        module = str(row.get('module', ''))
        
        # 检查语音指令覆盖
        if any(kw in desc or kw in interaction for kw in ['语音控制', '语音', '声控', '语音唤醒']):
            # 检查语音指令表是否有对应
            if not any(name[:6] in v for v in existing_voice):
                gaps['voice'].append({
                    'feature_name': name,
                    'module': module,
                    'context': desc[:50]
                })
        
        # 检查灯效覆盖
        if any(kw in desc or kw in interaction for kw in ['灯光', '灯效', '闪烁', '常亮']):
            if not any(name[:6] in l for l in existing_light):
                gaps['light'].append({
                    'feature_name': name,
                    'module': module,
                    'context': desc[:50]
                })
        
        # 检查测试用例覆盖（每个 P0 功能至少应有测试用例）
        priority = str(row.get('priority', ''))
        if priority == 'P0' and name not in existing_test_features:
            gaps['test'].append({
                'feature_name': name,
                'module': module,
            })
    
    # 汇报
    for sheet_name, gap_list in gaps.items():
        if gap_list:
            print(f"  [Consistency] {sheet_name}: 发现 {len(gap_list)} 个功能缺少对应条目")
    
    return gaps


async def _fill_consistency_gaps(gaps: dict, sheets_data: dict):
    """批量补生成跨 Sheet 缺失的条目"""
    
    # 补语音指令（批量）
    voice_gaps = gaps.get('voice', [])
    if voice_gaps and len(voice_gaps) <= 20:
        features_text = '\n'.join([f"- {g['feature_name']}：{g['context']}" for g in voice_gaps])
        prompt = f"""以下功能需要语音控制，请为每个功能生成 1 条语音指令。
JSON 数组，每条含: 指令分类、唤醒方式、用户说法、常见变体、系统动作、成功语音反馈、成功HUD反馈、失败反馈、优先级。
最多 {len(voice_gaps)} 条。

{features_text}"""
        # 调 LLM 生成（用实际函数名）
        # result = await actual_llm_call(prompt, task_name="consistency_voice", max_tokens=2000)
        # sheets_data['voice'].extend(parsed_result)
        print(f"  [Consistency-Fix] 补生成 {len(voice_gaps)} 条语音指令")
    
    # 补灯效（批量）
    light_gaps = gaps.get('light', [])
    if light_gaps and len(light_gaps) <= 20:
        features_text = '\n'.join([f"- {g['feature_name']}：{g['context']}" for g in light_gaps])
        prompt = f"""以下功能涉及灯光效果，请为每个生成 1 条灯效定义。
JSON 数组，每条含: 触发场景、灯光颜色、闪烁模式、频率Hz、持续时长、作用灯区(后脑勺灯/眼下方灯/双灯区)、优先级、备注。
最多 {len(light_gaps)} 条。

{features_text}"""
        print(f"  [Consistency-Fix] 补生成 {len(light_gaps)} 条灯效定义")

# 在审计闭环之后、写入 Excel 之前调用:
# gaps = _cross_sheet_consistency_check(all_feature_rows, sheets_data)
# await _fill_consistency_gaps(gaps, sheets_data)
```

---

## 修复 5: 内容深度控制 — 关键模块放宽条数 + 强制数字指标

### Step 1: 在 anchor 中标记深度模块

在 `product_spec_anchor.yaml` 中，给关键模块加 `depth: deep` 标记：

```yaml
# 需要手动在 yaml 中添加 depth 字段（或让 CC 用 sed 批量加）
# 以下模块标记为 deep:
```

```bash
# CC 执行以下命令，给关键模块加 depth 标记:
cd .ai-state
python3 -c "
import yaml
with open('product_spec_anchor.yaml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)

deep_modules = ['导航', '场景模式', 'AI语音助手', '主动安全预警提示', '组队', 
                '佩戴检测与电源管理', 'SOS与紧急救援', '部件识别与兼容性管理',
                '设备Tab', 'AI Tab']

for section in ['hud_modules', 'app_modules', 'cross_cutting']:
    for mod in data.get(section, []):
        if mod['name'] in deep_modules:
            mod['depth'] = 'deep'

with open('product_spec_anchor.yaml', 'w', encoding='utf-8') as f:
    yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print('Added depth:deep to', len(deep_modules), 'modules')
"
```

### Step 2: _gen_one 中根据 depth 调整 prompt

```python
# 在 _gen_one 的 prompt 拼装处:
module_depth = 'normal'
if anchor:
    for section in ['hud_modules', 'app_modules', 'cross_cutting']:
        for mod in anchor.get(section, []):
            if mod.get('name') == module_name or mod.get('name') == parent_name:
                module_depth = mod.get('depth', 'normal')
                break

if module_depth == 'deep':
    output_limit = """
【输出要求 — 深度模块】
- 本模块最多输出 30 条功能（含 L1/L2/L3 所有层级）
- 每条验收标准必须包含至少 1 个具体数字指标（时间ms/s、百分比%、距离m/km、次数、大小MB等）
- 禁止使用"应支持"、"需提供"等模糊表述，必须量化
- 如果无法确定具体数值，标注为 [需实测:预估值XXX] 而非 [待验证]
"""
else:
    output_limit = """
【输出要求】
- 本模块最多输出 18 条功能
- 每条验收标准尽量包含具体数字指标
"""
```

---

## 修复 6: 双重归一化（Compare 前后各一次）

确保归一化在 Compare 前和 Compare 后各执行一次：

```python
# ===== Compare 之前: 对新生成的数据归一化 =====
new_rows = _normalize_all_rows(new_rows, normalize_map)
print(f"[Normalize-Pre] 新版归一化后: {len(new_rows)} 条")

# ===== Compare 执行 =====
# ... 原有 Compare 逻辑 ...

# ===== Compare 之后: 对最终结果再归一化一次（处理 KEEP 带入的旧名称）=====
final_rows = _normalize_all_rows(final_rows, normalize_map)
print(f"[Normalize-Post] 最终归一化后: {len(final_rows)} 条")
```

同时在 `_normalize_all_rows` 中加一个保护：归一化后合并同名模块时，如果两个模块合并后超过 50 条，只保留质量最高的 50 条（按验收标准长度排序）：

```python
# 在 _normalize_all_rows 的去重逻辑中:
for module_name, group_rows in groups.items():
    # ... 去重逻辑 ...
    deduped_list = list(seen.values())
    
    # 防膨胀：合并后超过 50 条的模块，按质量排序截断
    if len(deduped_list) > 50:
        def _row_quality(r):
            acc = str(r.get('acceptance', ''))
            import re
            nums = len(re.findall(r'\d+', acc))
            return nums * 3 + len(acc)
        
        deduped_list.sort(key=_row_quality, reverse=True)
        trimmed = len(deduped_list) - 50
        deduped_list = deduped_list[:50]
        print(f"  [Normalize] {module_name}: 截断 {trimmed} 条 (保留质量最高的 50 条)")
    
    deduped.extend(deduped_list)
```

---

## 修复 7: 页面映射表扩充

当前只有 30 个页面，偏少。页面映射表的 prompt 可能没拿到完整功能列表。

找到页面映射表的生成逻辑：

```python
# 在 page_mapping 的 prompt 中，注入完整的功能模块列表:

page_mapping_prompt = f"""基于以下功能模块列表，生成完整的页面映射表。

【App 端页面要求】
每个 Tab 至少有：首页 + 2-3 个二级页面 + 关键三级页面
- 设备Tab: 设备首页/蓝牙配对页/设备详情页/骑行轨迹列表/轨迹详情/行车记录列表/视频播放页/摄像参数设置/部件信息页/HUD布局设置/场景模式设置
- 相册Tab: 相册首页/照片详情/视频播放/水印编辑/批量导出
- 社区Tab: 社区首页/帖子详情/发布页/个人主页/粉丝列表/等级说明
- AI Tab: AI首页/AI对话/AI剪片编辑/AI内容搜索结果/AI旅行总结/AI骑行摘要
- 我的Tab: 我的首页/账号信息编辑/通用设置/通知设置/帮助FAQ/反馈提交/关于设备/隐私政策/数据管理/多语言设置
- 通知中心: 通知列表/通知详情
- 商城: 商城首页/商品详情/购物车/订单确认/支付/订单列表/订单详情/报修工单提交/工单详情/工单列表
- 其他: 登录注册页/权限申请引导页/首次配对引导页/新手教学流程(多步)/用户成就页/成就详情

【HUD 端页面要求】
HUD 不是传统页面，但有不同的"显示状态/卡片组合":
- 主驾驶视图/导航视图/来电视图/音乐视图/组队视图/消息视图/简易模式视图
- 信息中岛各状态
- 各场景模式的 HUD 布局

每行包含: 页面名、父页面、平台(App/HUD)、包含功能、入口方式、优先级、备注

目标: App 至少 50 个页面 + HUD 至少 10 个视图 = 60+ 条

功能模块列表:
{module_list_text}
"""
```

---

## 修复 8: 定期全量重生成机制（防文件膨胀）

在 `_process_in_background` 中，加一个判断：如果旧版功能数超过 1200 条，提示用户可以做一次"全量重生成"：

```python
# 在 SmartIterate 检测到上一版后:
prev_count = len(prev_version_rows)
if prev_count > 1200:
    print(f"[SmartIterate] ⚠️ 上一版 {prev_count} 条，建议做一次全量重生成以清理历史残留")
    # 可选: 如果用户 prompt 中包含 "全量重生成" 或 "clean" 关键词，跳过 Compare 直接用新版
    if '全量' in user_text or 'clean' in user_text.lower():
        print(f"[SmartIterate] 检测到全量重生成指令，跳过 Compare，使用纯新版")
        skip_compare = True
```

这不是自动触发的，而是给用户一个选项。当积累太多轮次后，用户可以发 "全量重生成PRD" 来从零开始。

---

# ============ 验证清单 ============

- [ ] 版本信息页显示 V1.X（非 V1.0），有上一版本号，有 changelog
- [ ] HTML 页面可以上下滚动
- [ ] HTML 所有 Tab 可见可点击切换
- [ ] Compare 日志中出现 `KEEP+`（保留旧版同时吸收新功能）
- [ ] "简易"和"简易路线"不再同时存在
- [ ] 合并后单模块不超过 50 条
- [ ] 深度模块（导航/场景模式等）的验收标准有具体数字
- [ ] 页面映射表 > 50 条
- [ ] 跨 Sheet 一致性问题进一步减少
