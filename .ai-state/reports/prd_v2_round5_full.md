# PRD v2 Round 5 完整修复 — CC 执行文档

> 8 个修复项，按优先级顺序执行
> ⚠️ 不要重启服务，只做代码修改和 git commit

---

## 修复 1（P0 阻塞）: HTML SyntaxError — 真正的空白根因

**根因定位**: Chrome Console 报 `SyntaxError: Invalid or unexpected token` at line 318。

HTML 中的 `cleanMermaid` JS 函数有一行：
```javascript
// 当前生成的（错误的）:
code = 'graph TD
' + code;
// 正确应该是:
code = 'graph TD\n' + code;
```

Python 生成 HTML 模板时，`\n` 被 Python 解释为真实换行符写入文件，导致 JS 字符串字面量被换行截断 → SyntaxError → 整个 `<script>` 块无法解析 → 页面空白。

**修法**: 在 structured_doc.py 中，找到生成 `cleanMermaid` JS 函数的 Python 代码：

```bash
grep -n "cleanMermaid\|graph TD\|graph TD" scripts/feishu_handlers/structured_doc.py
```

找到类似这样的 Python 字符串：
```python
# 错误的写法（Python 解释 \n 为换行）:
code = 'graph TD\n' + code;

# 或在 f-string / 三引号中:
"""
code = 'graph TD\n' + code;
"""
```

**修改为以下任一写法**（确保 HTML 输出中 `\n` 是字面量，不是真实换行）:

```python
# 写法 A: 双重转义
"""
code = 'graph TD\\n' + code;
"""

# 写法 B: 用 + 号拼接避免转义问题
"""
code = 'graph TD' + '\\n' + code;
"""

# 写法 C: 直接用模板字面量（推荐）
"""
code = `graph TD\n${code}`;
"""
```

**同时检查整个 HTML 模板中所有 JS 字符串里的 `\n`**：

```bash
# 搜索所有可能有同样问题的地方
grep -n "'.*\\\\n.*'" scripts/feishu_handlers/structured_doc.py | head -20
grep -n "graph TD" scripts/feishu_handlers/structured_doc.py
```

把每个 JS 字符串中的 `\n` 都改为 `\\n`（在 Python 层面是 `\\\\n`）。

**验证**: 修完后本地生成一个测试 HTML，用浏览器打开确认不报 SyntaxError。
或者用命令行验证：
```bash
# 用 node.js 检查语法（如果有 node）
node -c prd_interactive.html 2>&1 | head -5
# 或者用 python 简单检查
python3 -c "
with open('.ai-state/exports/prd_interactive_test.html') as f:
    html = f.read()
# 找到 script 区域检查有没有跨行字符串
import re
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
for i, s in enumerate(scripts):
    lines = s.split('\n')
    for j, line in enumerate(lines):
        # 检查单引号字符串是否跨行
        if line.count(\"'\") % 2 == 1 and not line.strip().endswith(\"'\"):
            if j+1 < len(lines) and lines[j+1].strip().startswith(\"'\"):
                print(f'⚠️ Script {i}, 行 {j+1}: 字符串跨行: {line.strip()[:60]}')
print('检查完成')
"
```

---

## 修复 2（P1）: 社区Tab → 社区 归一化（连续 3 轮未修好）

**排查**: ForceNormalize 有 `社区Tab: 社区` 映射但不生效。

```bash
# Step 1: 确认 anchor yaml 中 normalize_map 的内容
python3 -c "
import yaml
with open('.ai-state/product_spec_anchor.yaml','r',encoding='utf-8') as f:
    d = yaml.safe_load(f)
nm = d.get('module_normalize',{})
for k,v in nm.items():
    if '社区' in str(k) or '社区' in str(v):
        print(f'  key={repr(k)} ({type(k).__name__}) → val={repr(v)}')
"
```

**可能的问题**:
- key 是 `社区Tab` 但 row 中的值带空格如 `社区Tab ` 或 `社区 Tab`
- yaml 中的 key 类型不是 str（有些 yaml 解析器会把 Tab 解析为特殊字符）

**终极修法**: 在 `_force_normalize` 中，不依赖精确 key 匹配，改用模糊匹配：

```python
def _force_normalize(rows, normalize_map):
    # 构建清洁的映射表（strip + 统一空格）
    clean_map = {}
    for k, v in normalize_map.items():
        clean_key = str(k).strip().replace(' ', '')
        clean_map[clean_key] = str(v).strip()
    
    renamed_count = 0
    for row in rows:
        for key in ['module', 'L1功能', 'l1', 'name']:
            val = str(row.get(key, '')).strip()
            clean_val = val.replace(' ', '')
            if clean_val and clean_val in clean_map:
                new_val = clean_map[clean_val]
                if new_val != val:
                    row[key] = new_val
                    renamed_count += 1
    
    if renamed_count:
        print(f"[ForceNormalize] 重命名 {renamed_count} 个字段")
    return rows
```

这样 `社区Tab`、`社区 Tab`、`社区tab` 都能匹配到 `社区`。

同时补充 anchor normalize_map 中可能遗漏的变体名：

```python
# 在 anchor 中追加:
extras = {
    'AI能力中心': 'AI Tab',
    'AI能力设置': 'AI Tab',
    'AI能力': 'AI Tab',
    '社区tab': '社区',
    'App-社区': '社区',
}
```

---

## 修复 3（P1）: 失败重试策略 — 先拆分再精简

当前: 失败 → 直接精简模式（丢失 anchor/KB/分离规则，质量差）
改为: 失败 → AutoSplit（拆 3 个子模块，保留完整上下文）→ 子模块也失败 → 才降级精简

找到重试逻辑：

```bash
grep -n "Retry\|精简模式\|minimal\|_retry" scripts/feishu_handlers/structured_doc.py
```

找到类似这段代码的位置：

```python
# 原代码:
for module_name in failed_modules:
    print(f"  [Retry] {module_name}: 精简模式...")
    result = _gen_one_minimal(module_name, ...)
```

**改为**:

```python
for module_name in failed_modules:
    # Step 1: 先尝试 AutoSplit（保留完整上下文）
    print(f"  [Retry] {module_name}: 拆分重试...")
    sub_names = [
        f"{module_name}-核心功能",
        f"{module_name}-交互与状态",
        f"{module_name}-异常与边界",
    ]
    
    split_results = []
    split_success = True
    for sub_name in sub_names:
        try:
            sub_result = _gen_one(sub_name, anchor=anchor, kb_data=kb_data, 
                                  separation_rules=separation_rules, 
                                  parent_module=module_name)
            if sub_result and len(sub_result) > 0:
                split_results.extend(sub_result)
                print(f"    [Split] {sub_name}: +{len(sub_result)} 条")
            else:
                print(f"    [Split] {sub_name}: 空结果")
                split_success = False
        except Exception as e:
            print(f"    [Split] {sub_name}: 失败 - {e}")
            split_success = False
    
    if split_results:
        # 拆分有结果，合并去重
        from collections import OrderedDict
        seen = OrderedDict()
        for r in split_results:
            name = r.get('name', '')
            if name not in seen or len(str(r.get('acceptance',''))) > len(str(seen[name].get('acceptance',''))):
                seen[name] = r
        merged = list(seen.values())
        print(f"  [Retry] {module_name}: 拆分成功 → {len(merged)} 条")
        all_rows.extend(merged)
    else:
        # Step 2: 拆分全部失败，才降级精简模式
        print(f"  [Retry] {module_name}: 拆分失败，降级精简模式...")
        minimal_result = _gen_one_minimal(module_name, ...)
        if minimal_result:
            all_rows.extend(minimal_result)
            print(f"  [Retry] {module_name}: 精简模式 → {len(minimal_result)} 条")
        else:
            print(f"  ❌ [Retry] {module_name}: 完全失败")
```

---

## 修复 4（P1）: Phase 2 五路并行

当前状态对策/用户故事/测试用例/页面映射/开发任务可能是串行或部分并行。这 5 个互不依赖，可以全并行。

找到 Phase 2 生成代码：

```bash
grep -n "state\|user_stories\|test_cases\|page_mapping\|dev_tasks" scripts/feishu_handlers/structured_doc.py | grep -i "generate\|submit\|future"
```

**改为 5 路并行**:

```python
# Phase 2: 依赖主功能表的 5 个 Sheet，全部并行
print("[FastTrack] Phase 2: 5 路并行生成依赖型 Sheet")

with ThreadPoolExecutor(max_workers=5) as phase2_executor:
    futures = {
        'state': phase2_executor.submit(_generate_state_sheet, all_rows, prompt_text),
        'user_stories': phase2_executor.submit(_generate_user_stories, all_rows),
        'test_cases': phase2_executor.submit(_generate_test_cases, all_rows),
        'page_mapping': phase2_executor.submit(_generate_page_mapping, all_rows),
        'dev_tasks': phase2_executor.submit(_generate_dev_tasks, all_rows),
    }
    
    for name, future in futures.items():
        try:
            result = future.result(timeout=600)
            sheets_data[name] = result
            count = len(result) if isinstance(result, list) else 0
            print(f"  ✅ {name}: {count} 条")
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            sheets_data[name] = []

print(f"[FastTrack] Phase 2 完成")
```

如果当前已经是部分并行（比如用了 asyncio.gather 或 ThreadPoolExecutor 但 workers 不够），确保 max_workers >= 5。

---

## 修复 5（P1）: 跨 Sheet 交叉验证

在 Phase 2 全部完成后、写入 Excel 前，加规则校验：

```python
def _cross_validate(all_rows, sheets_data):
    """跨 Sheet 交叉验证"""
    issues = []
    
    # 1. P0 功能 → 测试用例覆盖
    p0_names = set(r.get('name','') for r in all_rows if r.get('priority') == 'P0')
    tc_names = set()
    for tc in sheets_data.get('test_cases', []):
        # 测试用例的"功能名"或"关联功能"字段
        tc_names.add(str(tc.get('功能名', tc.get('feature', ''))))
    uncovered_p0 = p0_names - tc_names
    if uncovered_p0:
        issues.append(f"[P0-测试] {len(uncovered_p0)} 个 P0 功能无测试用例覆盖")
    
    # 2. 功能 → 开发任务对应
    all_modules = set(r.get('module', r.get('L1功能','')) for r in all_rows)
    dev_modules = set()
    for dt in sheets_data.get('dev_tasks', []):
        dev_modules.add(str(dt.get('功能名', dt.get('module', ''))))
    uncovered_modules = all_modules - dev_modules
    if uncovered_modules:
        issues.append(f"[功能-开发] {len(uncovered_modules)} 个模块无开发任务")
    
    # 3. 页面映射 → 模块覆盖
    pm_modules = set()
    for pm in sheets_data.get('page_mapping', []):
        pm_modules.add(str(pm.get('关联模块', pm.get('module', ''))))
    unmapped = all_modules - pm_modules
    if unmapped and len(unmapped) > 5:
        issues.append(f"[页面-映射] {len(unmapped)} 个模块无页面映射")
    
    # 4. 用户故事 vs 功能表重复检查
    story_count = len(sheets_data.get('user_stories', []))
    feature_count = len(all_rows)
    ratio = story_count / max(feature_count, 1)
    if ratio < 0.2:
        issues.append(f"[用户故事] 仅 {story_count} 条（功能的 {ratio:.0%}），偏少")
    
    if issues:
        print(f"\n[CrossValidate] 发现 {len(issues)} 个交叉问题:")
        for issue in issues:
            print(f"  ! {issue}")
    else:
        print(f"\n[CrossValidate] ✅ 跨 Sheet 一致性检查通过")
    
    return issues

# 在 Phase 2 完成后调用:
cross_issues = _cross_validate(all_rows, sheets_data)
```

---

## 修复 6（P1）: P0 校准 — 不盲目降级核心功能

当前 P0 占比超 25% 时直接降级 L3。但安全类模块（主动安全预警/SOS/佩戴检测）的 P0 占比高是合理的。

找到 P0 校准逻辑：

```bash
grep -n "Calibrate\|P0.*占比\|P0.*降级" scripts/feishu_handlers/structured_doc.py
```

**改为**: 豁免安全类和核心类模块：

```python
# 不参与 P0 降级的模块（核心安全功能）
P0_EXEMPT_MODULES = {
    '主动安全预警提示',  # 安全核心
    'SOS与紧急救援',     # 安全核心
    '佩戴检测与电源管理', # 硬件安全
    '导航',              # 产品核心卖点
    '组队',              # 产品核心卖点
    '设备状态',           # 基础功能
}

def _calibrate_p0(rows):
    """P0 占比校准，豁免核心安全模块"""
    total = len(rows)
    p0_rows = [r for r in rows if r.get('priority') == 'P0']
    p0_count = len(p0_rows)
    target_ratio = 0.25
    
    if p0_count / max(total, 1) <= target_ratio:
        return rows  # 不需要校准
    
    # 只对非豁免模块的 L3 降级
    candidates = [r for r in p0_rows 
                  if r.get('level') == 'L3' 
                  and r.get('module', r.get('L1功能','')) not in P0_EXEMPT_MODULES]
    
    excess = p0_count - int(total * target_ratio)
    to_downgrade = candidates[:excess]
    
    downgraded = 0
    for r in to_downgrade:
        r['priority'] = 'P1'
        downgraded += 1
    
    print(f"[Calibrate] P0 {p0_count}→{p0_count-downgraded} (降级 {downgraded} 个非核心 L3，豁免 {len(P0_EXEMPT_MODULES)} 个核心模块)")
    return rows
```

---

## 修复 7（P2）: 开发任务数量恢复

上轮 711 条，本轮 484 条。原因可能是开发任务 prompt 中按模块数或功能数分批，模块合并后批次减少。

找到开发任务生成 prompt：

```bash
grep -n "DevTask\|dev_task.*prompt\|开发任务.*生成" scripts/feishu_handlers/structured_doc.py
```

在 prompt 中明确要求最低数量：

```python
dev_task_requirement = """
请为以下功能生成开发任务。要求：
- 每个 L1 模块至少 5 条开发任务
- 每个 L2 功能至少 1 条开发任务
- 包含前后端、测试、部署各角色
- 总数不少于 700 条
"""
```

---

## 修复 8（P2）: 添加深度学习任务减少[待验证]

当前 667/834 条验收标准标[待验证]。需要通过深度学习任务补充知识库中的性能指标数据。

在 anchor yaml 中添加一个新段落，定义需要研究的性能指标：

```bash
cat >> .ai-state/product_spec_anchor.yaml << 'EOF'

# ==================== 待研究的性能指标（用于降低[待验证]比例）====================
pending_research_tasks:
  - topic: "HUD 显示性能基准"
    targets: ["HUD 刷新率", "亮度范围 nit", "响应延迟 ms", "可视角度", "色域覆盖"]
  - topic: "蓝牙连接性能"
    targets: ["配对时间", "重连时间", "有效距离", "多设备切换延迟", "音频延迟"]
  - topic: "摄像头与存储性能"
    targets: ["录像分辨率/帧率", "存储写入速度", "传输速度 WiFi/BLE", "满卡预警阈值"]
  - topic: "电池与功耗基准"
    targets: ["全功能续航时长", "待机续航", "充电时间 0-100%", "各模块功耗占比"]
  - topic: "导航性能"
    targets: ["GPS 定位精度", "首次定位时间", "离线地图包大小", "偏航检测延迟"]
  - topic: "语音识别性能"
    targets: ["唤醒词识别率", "指令识别率 60km/h风噪", "响应延迟", "离线识别范围"]
  - topic: "ADAS/视觉处理"
    targets: ["目标检测帧率", "大车识别距离", "红绿灯识别准确率", "夜间性能衰减"]
  - topic: "App 性能基准"
    targets: ["冷启动时间", "AI剪片处理速度", "媒体同步速度", "推送到达延迟"]
EOF
```

后续可以通过飞书发送深度研究指令，逐个 topic 研究并写入知识库，下次生成 PRD 时 [待验证] 比例会自动下降。

---

## 执行顺序

1. ★ 修复 1: HTML SyntaxError（改 `\n` 为 `\\n`，最高优先）
2. 修复 2: 社区Tab 归一化（ForceNormalize 模糊匹配）
3. 修复 3: 失败先拆分再精简
4. 修复 4: Phase 2 五路并行
5. 修复 5: 跨 Sheet 交叉验证
6. 修复 6: P0 校准豁免核心模块
7. 修复 7: 开发任务数量要求
8. 修复 8: anchor 追加研究任务

```bash
git add scripts/feishu_handlers/structured_doc.py .ai-state/product_spec_anchor.yaml
git commit --no-verify -m "fix+feat: Round 5 - HTML根因修复+AutoSplit+并行+交叉验证+P0豁免"
```

⚠️ **不要重启服务**。Leo 会手动重启。

---

## 验证清单

- [ ] HTML 在 Chrome 中能正常显示（无 SyntaxError）
- [ ] Tab 栏可见且可切换
- [ ] 关键流程 Tab 中流程图可渲染
- [ ] App 模块中"社区Tab"变为"社区"
- [ ] 失败模块日志显示"拆分重试"而不是直接"精简模式"
- [ ] 日志显示"Phase 2: 5 路并行"
- [ ] 日志显示"[CrossValidate]"交叉验证结果
- [ ] 主动安全预警提示的 P0 不被降级
- [ ] 开发任务 > 600 条
