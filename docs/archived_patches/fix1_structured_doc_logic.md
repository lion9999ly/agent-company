# 修复文档 1/2: structured_doc.py 逻辑修复

> 目标: 消灭生成失败、消灭模块分裂、提升评分质量
> 可与修复文档 2（HTML 模板）并行执行

---

## 修复 1: prompt 硬约束输出条数（替代 max_tokens 调整）

**根因**: 部分模块输出超 4096 token 被截断，但提高 max_tokens 治标不治本。

**修法**: 在 `_gen_one` 的 LLM prompt 中加硬约束，同时在 AutoSplit 判断中加兜底。

### Step 1: prompt 加条数限制

找到 `_gen_one` 函数中拼装 prompt 的位置，在 prompt 的"要求"部分加入：

```python
# 在 prompt 中找到类似"输出要求"或"JSON格式"的说明段落，加入：

output_limit_instruction = """
【输出数量硬约束】
- 本模块最多输出 18 条功能（含 L1/L2/L3 所有层级合计）
- 如果功能点超过 18 条，优先保留 P0 和 P1，P2/P3 可精简合并
- 每条功能的 description 字段限 80 字以内
- 每条功能的 acceptance 字段限 120 字以内
- 严格遵守此上限，超出部分不会被系统采纳
"""

# 把 output_limit_instruction 拼入 prompt
```

### Step 2: AutoSplit 兜底 — 对未被标记为复杂但输出失败的模块也走拆解

找到 Retry 逻辑（处理首轮失败模块的位置），在精简重试之前加一步判断：

```python
# 在 [Retry] 逻辑中，当前流程是：失败 → 精简模式重试 → 完整重试 → Gemini 降级
# 改为：失败 → 检查是否因 length 截断 → 是则走拆解而非精简重试

for module_name in failed_modules:
    # 检查失败原因
    fail_reason = failure_reasons.get(module_name, '')
    
    if 'finish_reason=length' in fail_reason or 'too_short' in fail_reason:
        # 因输出过长截断导致的失败 → 走拆解路径
        print(f"  [Retry] {module_name}: 因输出截断失败，改用拆解模式")
        sub_modules = [
            f"{module_name}-核心功能",
            f"{module_name}-交互与状态", 
            f"{module_name}-异常与边界",
        ]
        sub_futures = []
        for sub_name in sub_modules:
            sf = executor.submit(_gen_one, sub_name, ...)  # 用实际参数
            sub_futures.append(sf)
        # 收集并合并
        sub_results = []
        for sf in sub_futures:
            try:
                rows = sf.result(timeout=120)
                if rows:
                    sub_results.append(rows)
            except:
                pass
        if sub_results:
            merged = _merge_sub_modules(module_name, sub_results)
            all_rows.extend(merged)
            retry_success.add(module_name)
            print(f"  ✅ [Retry] {module_name}: +{len(merged)} 条 (拆解重试)")
            continue
    
    # 非截断原因的失败 → 走原有精简重试流程
    # ... 原有 retry 逻辑 ...
```

### Step 3: 拆解子模块的 KB 检索要带子维度关键词

找到 `_gen_one` 中调用知识库检索的位置，当模块名包含 `-` 时（说明是拆解出来的子模块），增强检索关键词：

```python
# 在 KB 检索前：
def _build_kb_query(module_name: str) -> str:
    """为拆解子模块构建差异化的 KB 检索关键词"""
    if '-' not in module_name:
        return module_name
    
    parent, suffix = module_name.rsplit('-', 1)
    
    # 子维度到检索关键词的映射
    suffix_keywords = {
        '核心功能': f'{parent} 核心 功能 规格 参数 指标',
        '交互与状态': f'{parent} 交互 HUD 语音 按键 状态 反馈 显示',
        '异常与边界': f'{parent} 异常 断连 降级 故障 恢复 兜底 边界 低电量',
    }
    
    return suffix_keywords.get(suffix, module_name)

# 在 KB 检索调用处：
kb_query = _build_kb_query(module_name)
kb_data = knowledge_base.search(kb_query, top_k=5)
```

---

## 修复 2: 消灭"[待生成]"— 失败模块不透出给用户

**根因**: 生成失败的模块以占位符写入 Excel 和 HTML，用户看到"[待生成]"。

### Step 1: 最终输出前过滤

找到写入 Excel/HTML 的位置（`_write_feature_sheet` 或类似函数），在写入前过滤掉失败占位行：

```python
# 在最终写入前：
def _remove_placeholder_rows(rows: list) -> list:
    """移除生成失败的占位行，用上一版数据或空骨架替代"""
    cleaned = []
    for row in rows:
        desc = str(row.get('description', ''))
        if '待生成' in desc or '生成失败' in desc:
            # 尝试从上一版获取该模块的数据
            module_name = row.get('module') or row.get('name', '')
            prev_rows = prev_version_map.get(module_name, [])
            if prev_rows:
                cleaned.extend(prev_rows)
                print(f"  [Fallback] {module_name}: 用上一版 {len(prev_rows)} 条替代")
            else:
                # 上一版也没有 → 生成最小骨架
                skeleton = {
                    **row,
                    'description': f'{module_name}模块（待详细展开）',
                    'acceptance': '待下一版本迭代补充',
                    'level': 'L1',
                }
                cleaned.append(skeleton)
                print(f"  [Skeleton] {module_name}: 生成最小骨架")
        else:
            cleaned.append(row)
    return cleaned

# 在写入 Excel 前调用：
final_rows = _remove_placeholder_rows(all_rows)
```

---

## 修复 3: 模块命名去重/合并

**根因**: 智能增量迭代保留旧版碎片，新版生成了新命名模块，两者没合并。
例如: "我的" + "App-我的" + "我的首页" + "我的首页与个人中心" 四个并存。

### Step 1: 在 Compare 阶段加模块名归一化

```python
# 模块名归一化映射表（放在文件顶部或配置中）
MODULE_NAME_NORMALIZE = {
    # App 端归一化
    'App-我的': '我的',
    '我的首页': '我的',
    '我的首页与个人中心': '我的',
    'App-社区': '社区',
    'App-商城': '商城',
    'App-设备': '设备Tab',
    '设备连接与管理': '设备Tab',
    '设备控制与显示设置': '设备Tab',
    '电量续航与固件维护': '设备Tab',
    # HUD 端归一化
    '简易': '简易路线',
    '路线': '简易路线',
}

def _normalize_module_name(name: str) -> str:
    return MODULE_NAME_NORMALIZE.get(name, name)
```

### Step 2: 在 Compare 的逐模块对比前，先归一化再合并

```python
# 在 [Compare] 逻辑开头：
# 1. 按归一化名称分组
from collections import defaultdict

normalized_groups = defaultdict(list)
for row in all_rows:
    module = row.get('module') or row.get('name', '')
    norm_name = _normalize_module_name(module)
    row['module'] = norm_name  # 统一模块名
    normalized_groups[norm_name].append(row)

# 2. 同名模块合并去重
merged_rows = []
for norm_name, group_rows in normalized_groups.items():
    if len(group_rows) <= 1:
        merged_rows.extend(group_rows)
        continue
    
    # 按 name(L3功能名) 去重，保留验收标准更完整的那条
    seen = {}
    for row in group_rows:
        key = row.get('name', '')
        if key in seen:
            # 比较质量，保留更好的
            old_acc = str(seen[key].get('acceptance', ''))
            new_acc = str(row.get('acceptance', ''))
            if len(new_acc) > len(old_acc):
                seen[key] = row
        else:
            seen[key] = row
    
    deduped = list(seen.values())
    print(f"  [Normalize] {norm_name}: {len(group_rows)} 条合并去重为 {len(deduped)} 条")
    merged_rows.extend(deduped)

all_rows = merged_rows
```

---

## 修复 4: _score_module 质量评分修正

**问题**: `速度: 53->53` 判定"新版更好"（>=也算赢），且 0 分模块保留无意义。

找到 Compare 的比较逻辑：

```python
# 原代码可能是:
# if new_score >= old_score:
#     use_new = True

# 改为:
def _compare_decision(module_name, old_rows, new_rows, old_score, new_score):
    """比较决策：新版必须显著更好才替换"""
    
    # 两者都是空/失败 → 都不要
    if old_score <= 1 and new_score <= 1:
        print(f"  SKIP {module_name}: 新旧都是空壳 (旧{old_score}, 新{new_score})")
        return None  # 标记为需要重新生成
    
    # 新版是空/失败 → 保留旧版
    if new_score <= 1:
        print(f"  KEEP {module_name}: 新版空壳 (旧{old_score})")
        return 'keep'
    
    # 旧版是空/失败 → 用新版
    if old_score <= 1:
        print(f"  OK {module_name}: 旧版空壳 (新{new_score})")
        return 'new'
    
    # 都有内容 → 新版必须高出 5% 以上才替换
    threshold = max(3, old_score * 0.05)
    if new_score > old_score + threshold:
        print(f"  OK {module_name}: 新版显著更好 ({old_score}->{new_score})")
        return 'new'
    elif new_score < old_score - threshold:
        print(f"  KEEP {module_name}: 旧版更好 ({old_score} vs 新{new_score})")
        return 'keep'
    else:
        # 分数接近 → 合并两版的精华
        print(f"  MERGE {module_name}: 分数接近 ({old_score} vs {new_score})，合并取优")
        return 'merge'
```

当 decision == 'merge' 时，按 L3 功能名逐条对比，每条取验收标准更完整的那个版本。

---

## 修复 5: 版本信息自动升版

找到版本信息 Sheet 写入逻辑，改为自动递增 + changelog：

```python
def _write_version_sheet(ws, version_data: dict, prev_version: str = None):
    """写入版本信息 Sheet，支持自动升版"""
    import re
    from datetime import datetime
    
    # 自动递增版本号
    if prev_version:
        # 从 "V1.0" 提取数字，+0.1
        match = re.search(r'V?(\d+)\.(\d+)', prev_version)
        if match:
            major, minor = int(match.group(1)), int(match.group(2))
            new_version = f"V{major}.{minor + 1}"
        else:
            new_version = "V1.1"
    else:
        new_version = "V1.0"
    
    version_data['PRD版本'] = new_version
    version_data['更新日期'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    # 生成 changelog
    changelog_items = []
    if version_data.get('new_modules'):
        changelog_items.append(f"新增模块: {', '.join(version_data['new_modules'])}")
    if version_data.get('updated_modules'):
        changelog_items.append(f"更新模块: {', '.join(version_data['updated_modules'])}")
    if version_data.get('total_features'):
        changelog_items.append(f"功能总数: {version_data['total_features']} 条")
    if version_data.get('audit_issues'):
        changelog_items.append(f"一致性问题: {version_data['audit_issues']} 个")
    
    version_data['本次主要改动'] = '; '.join(changelog_items) if changelog_items else '首版生成'
    
    # 写入 Sheet（保持原有写入逻辑，追加 changelog 行）
    # ...
```

---

## 修复 6: 一致性审计自我迭代闭环

找到 `[Audit]` 逻辑的位置（审计完成后），加一步自动修复：

```python
async def _auto_fix_audit_issues(audit_issues: list, sheets_data: dict):
    """
    针对可自动修复的审计问题，自动补生成缺失条目
    """
    fixable = []
    manual = []
    
    for issue in audit_issues:
        issue_type = issue.get('type', '')
        
        if '功能-语音不一致' in issue_type:
            # 功能表有语音控制，但语音指令表缺对应条目 → 可自动补
            fixable.append(issue)
        elif '场景-灯效不一致' in issue_type:
            # 状态场景有灯光提示，但灯效表缺对应条目 → 可自动补
            fixable.append(issue)
        else:
            manual.append(issue)
    
    if not fixable:
        print(f"  [Audit-Fix] 无可自动修复的问题")
        return
    
    print(f"  [Audit-Fix] 发现 {len(fixable)} 个可自动修复问题，开始补生成...")
    
    # 按类型分组批量生成
    voice_gaps = [i for i in fixable if '语音' in i['type']]
    light_gaps = [i for i in fixable if '灯效' in i['type']]
    
    if voice_gaps:
        # 提取缺失的功能名
        missing_features = [i.get('feature_name', '') for i in voice_gaps]
        prompt = f"""以下功能具备语音控制能力，但语音指令表中缺少对应条目。
请为每个功能生成语音指令表条目，JSON 数组格式，每条包含:
指令分类、唤醒方式、用户说法、常见变体、系统动作、成功语音反馈、成功HUD反馈、失败反馈、优先级

缺失功能: {', '.join(missing_features)}

每个功能生成 1-2 条指令即可，不超过 {len(missing_features) * 2} 条总计。"""
        
        result = await _call_llm(prompt, task_name="audit_fix_voice", max_tokens=2000)
        if result:
            new_voice_rows = _parse_json_safe(result)
            if new_voice_rows:
                sheets_data['voice'].extend(new_voice_rows)
                print(f"  [Audit-Fix] 语音指令表补充 {len(new_voice_rows)} 条")
    
    if light_gaps:
        missing_scenes = [i.get('scene_name', '') for i in light_gaps]
        prompt = f"""以下状态场景有灯光提示，但灯效定义表中缺少对应条目。
请为每个场景生成灯效定义条目，JSON 数组格式，每条包含:
触发场景、灯光颜色、闪烁模式、频率Hz、持续时长、优先级、备注

缺失场景: {', '.join(missing_scenes)}

每个场景 1 条定义，不超过 {len(missing_scenes)} 条总计。"""
        
        result = await _call_llm(prompt, task_name="audit_fix_light", max_tokens=2000)
        if result:
            new_light_rows = _parse_json_safe(result)
            if new_light_rows:
                sheets_data['light'].extend(new_light_rows)
                print(f"  [Audit-Fix] 灯效定义表补充 {len(new_light_rows)} 条")
    
    # 修复后重新审计，输出修复后的问题数
    remaining = len(manual)
    print(f"  [Audit-Fix] 自动修复完成。剩余 {remaining} 个需人工确认的问题")

# 在 [Audit] 完成后调用:
# await _auto_fix_audit_issues(audit_issues, sheets_data)
# 然后重新写入 Excel（审计结果页也要更新）
```

---

## 修复 7: XMind 在线版兼容格式

**根因**: 当前 `.xmind` 文件可能是旧版格式（ZIP 内含 content.xml）。XMind 在线版需要新版格式（ZIP 内含 content.json）。

找到 XMind 生成逻辑，改为新版格式：

```python
import json
import zipfile
from io import BytesIO

def _generate_xmind_new_format(root_data: dict, output_path: str):
    """
    生成 XMind 新版格式（基于 JSON），兼容 XMind 在线版
    """
    
    def _build_node(name: str, children: list = None, note: str = None) -> dict:
        node = {
            "id": f"node_{hash(name) & 0xFFFFFFFF:08x}",
            "title": name,
            "children": {"attached": []} if children else {}
        }
        if children:
            node["children"]["attached"] = children
        if note:
            node["notes"] = {"plain": {"content": note}}
        return node
    
    def _convert_tree(data) -> dict:
        """递归转换功能树为 XMind JSON 节点"""
        if isinstance(data, dict):
            name = data.get('name', data.get('title', ''))
            children = data.get('children', [])
            note = data.get('description', '')
            child_nodes = [_convert_tree(c) for c in children] if children else []
            return _build_node(name, child_nodes if child_nodes else None, note)
        elif isinstance(data, str):
            return _build_node(data)
        return _build_node(str(data))
    
    # 构建 content.json
    root_node = _convert_tree(root_data)
    content = [{
        "id": "sheet_001",
        "class": "sheet",
        "title": "智能骑行头盔 V1 功能框架",
        "rootTopic": root_node,
        "topicPositioning": "fixed"
    }]
    
    # 构建 metadata.json
    metadata = {
        "creator": {"name": "Smart Helmet RD Center", "version": "2.0"}
    }
    
    # 打包为 .xmind (ZIP)
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('content.json', json.dumps(content, ensure_ascii=False, indent=2))
        zf.writestr('metadata.json', json.dumps(metadata, ensure_ascii=False))
        # manifest 可选但推荐
        manifest = {
            "file-entries": {
                "content.json": {},
                "metadata.json": {}
            }
        }
        zf.writestr('manifest.json', json.dumps(manifest))
    
    print(f"  ✅ XMind (新版格式): {output_path}")
```

替换原有的 XMind 生成调用，确保输出 `.xmind` 文件用新版 JSON 格式。

---

## 修复 8: 水印功能补充

在 `_gen_one` 调用前的模块列表中，检查用户输入中是否包含水印相关关键词。如果 inbox PRD 中有水印功能但用户 prompt 中没提到，系统应该从产品目标/知识库中自动补充。

**快速修法**: 在功能模块列表解析后，加一个"知识库驱动的功能补全"检查：

```python
# 在模块列表确定后、开始并行生成前：
KNOWN_FEATURES_FROM_KB = [
    '视频水印',  # 自定义水印（品牌/时间/GPS/速度叠加）
    '照片水印',
]

# 检查用户输入 + 当前模块列表中是否覆盖了这些功能
for feature in KNOWN_FEATURES_FROM_KB:
    if not any(feature in m for m in module_list):
        # 检查知识库中是否有相关条目
        kb_hits = kb.search(feature, top_k=1)
        if kb_hits:
            # 追加为"摄像状态"或"App-设备"的子功能
            # 不单独成模块，而是在生成 prompt 中提醒 LLM 涵盖此功能
            print(f"  [AutoComplete] 知识库有 {feature} 相关条目，追加到相关模块 prompt")
            # 在相关模块的 prompt 中追加提醒
```

更根本的做法是在产品目标文件（`product_goal.json`）中维护一份"必须覆盖的功能清单"，每次 PRD 生成后自动比对是否有遗漏。

---

## 验证清单

- [ ] 不再出现 `[待生成]` 或 `生成失败` 的行
- [ ] 模块名无重复分裂（"我的"只有一个，"设备Tab"只有一个）
- [ ] 分数相等时不判定"新版更好"
- [ ] 拆解子模块的 KB 数据点各不相同
- [ ] 一致性审计后自动补生成缺失的语音指令/灯效条目
- [ ] 版本信息页有版本号递增和 changelog
- [ ] XMind 在线版可正常打开编辑
- [ ] 水印功能出现在摄像/影像相关模块中
