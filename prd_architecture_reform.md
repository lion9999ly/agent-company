# PRD 生成系统架构改造文档

> CC 执行文档 — 2026-03-30
> 目标：解决功能膨胀、质量不收敛、跨轮次累积三大结构性问题
> 涉及文件：`scripts/feishu_handlers/structured_doc.py`
> 同时修复：Mermaid v9 降级、幽灵模块过滤
> 完成后：`git add -A && git commit -m "refactor: PRD architecture — anchor-driven, replace-mode compare, density cap, micro-loop QA"`

---

## 问题诊断

当前 PRD 生成每轮功能数只增不减：R5(805) → R7(1402) → R9(2038)。根因是三个结构性缺陷：

1. **Prompt 与 Anchor 双源驱动**：Prompt 中的模块名和 Anchor 不一致，合并后 36 变 44，多出的 8 个"伪模块"独立生成后又要 Normalize，造成重复
2. **Compare 只做并集**：无论新版好还是旧版好，都吸收对方独有功能，每轮净增 30-50%
3. **无密度控制**：单模块可以无限膨胀（导航 149 行、手机权限 130 行），LLM 的措辞差异被当作"独有功能"保留

---

## 四层改造方案

### Layer 1：Anchor 唯一驱动（控制模块数量）

#### 原则

Anchor（`product_spec_anchor.yaml`）是模块定义的唯一来源。Prompt 不创建新模块。

#### 改造

找到 `structured_doc.py` 中 Anchor 加载和 Prompt 合并的逻辑（日志标记 `[Anchor] Prompt 新增 X 个模块`），修改为：

```python
def _merge_anchor_and_prompt(anchor_modules: list, prompt_text: str, normalize_map: dict) -> list:
    """Anchor 驱动的模块合并——Prompt 关键词只补充已有模块，不创建新模块

    Args:
        anchor_modules: Anchor 中定义的模块列表
        prompt_text: 用户 Prompt 原文
        normalize_map: 模块名归一化映射表
    Returns:
        最终模块列表（数量 = Anchor 模块数，不会增加）
    """
    anchor_names = set(m['name'] for m in anchor_modules)

    # 从 Prompt 中提取可能的模块名
    prompt_keywords = _extract_module_keywords_from_prompt(prompt_text)

    absorbed = []
    dropped = []

    for kw in prompt_keywords:
        # 1. 先查 normalize_map
        normalized = normalize_map.get(kw, kw)

        if normalized in anchor_names:
            # 已在 Anchor 中，跳过（不重复添加）
            absorbed.append(f"{kw} → {normalized}")
            continue

        # 2. 模糊匹配：关键词是否是某个 Anchor 模块的子串
        matched = False
        for anchor_name in anchor_names:
            if kw in anchor_name or anchor_name in kw:
                absorbed.append(f"{kw} → {anchor_name} (fuzzy)")
                matched = True
                break

        if not matched:
            # 3. 不创建新模块，丢弃并警告
            dropped.append(kw)

    if absorbed:
        print(f"[Anchor] Prompt 关键词吸收: {len(absorbed)} 个")
        for a in absorbed[:5]:
            print(f"  ✓ {a}")

    if dropped:
        print(f"[Anchor] ⚠️ Prompt 关键词丢弃（未匹配到 Anchor 模块）: {dropped}")

    # 返回 Anchor 原始模块列表，不增加
    return anchor_modules
```

同时确保 `normalize_map` 包含以下映射（在 `product_spec_anchor.yaml` 中添加缺失的）：

```yaml
# Layer 1 必需的归一化映射
module_normalize:
  # ... 保留已有的 27 条 ...
  # 新增：Prompt 中出现但应归入已有模块的关键词
  简易: 导航
  简易路线: 导航
  简易导航: 导航
  简易导航模式: 导航
  路线: 导航
  显示队友位置: 组队
  App-社区: 社区
  App-设备: 设备Tab
  App-商城: 商城
  App-我的: 我的Tab
  身份认证: 我的Tab
  身份认证与用户信息采集: 我的Tab
  设备管理: 设备Tab
  我的首页: 我的Tab
  高光时刻异常与素材完整性: 相册Tab
  高光结果异常提示: 相册Tab
```

#### 验证

日志应从 `[Anchor] Prompt 新增 8 个模块` 变为 `[Anchor] Prompt 关键词吸收: 8 个`，`合并后共 36 个模块`（不再是 44）。

---

### Layer 2：Compare 替换模式（控制跨轮次不累积）

#### 原则

每轮生成是**替换**而非**累加**。新版更好就整体替换，旧版更好就保留不动。不吸收对方独有功能。

#### 改造

找到 `structured_doc.py` 中 Compare 的核心逻辑（日志标记 `OK+`、`KEEP+`、`MERGE`），修改三种模式：

```python
def _compare_module(module_name: str, new_features: list, old_features: list) -> list:
    """模块级对比——择优替换，不做并集

    Returns:
        选中的功能列表（要么全是新版，要么全是旧版，不混合）
    """
    new_count = len(new_features)
    old_count = len(old_features)

    # Case 1: 旧版空壳（< 3 条），无条件用新版
    if old_count < 3:
        print(f"  OK {module_name}: 旧版空壳 → 用新版 ({new_count}条)")
        return new_features

    # Case 2: 新版空壳或生成失败
    if new_count < 3:
        print(f"  KEEP {module_name}: 新版空壳 → 保留旧版 ({old_count}条)")
        return old_features

    # Case 3: 都有内容，抽样对比质量
    winner = _sample_quality_compare(module_name, new_features, old_features)

    if winner == "new":
        print(f"  REPLACE {module_name}: 新版质量更好 → 整体替换 (新{new_count}条，弃旧{old_count}条)")
        return new_features
    elif winner == "old":
        print(f"  KEEP {module_name}: 旧版质量更好 → 保留旧版 ({old_count}条)")
        return old_features
    else:
        # 质量相当，稳定优先，保留旧版
        print(f"  KEEP {module_name}: 质量相当 → 稳定优先保留旧版 ({old_count}条)")
        return old_features
```

**删除**以下逻辑（搜索关键词定位）：
- `OK+` 模式中 "保留旧版 X 条独有功能" 的代码
- `KEEP+` 模式中 "吸收 X 条新增功能" 的代码
- `MERGE` 模式中 "逐条取优" 的代码

全部替换为上面的三分支逻辑。

#### 验证

日志应从 `OK+ 模块: 新版更好 + 保留旧版 7 条独有功能` 变为 `REPLACE 模块: 新版质量更好 → 整体替换`。不再出现 `+` 号。

---

### Layer 3：模块密度上限 + LLM 精简（控制单模块不臃肿）

#### 原则

每个模块有行数上限。超过上限时调用 LLM 合并精简，而不是截断。

#### 新增配置

在 `structured_doc.py` 顶部或 Anchor 中添加密度配置：

```python
# 模块密度上限——按复杂度分级
MODULE_DENSITY_LIMITS = {
    # 核心复杂模块：60 行
    "导航": 60, "组队": 60, "设备Tab": 60, "我的Tab": 60,
    "手机系统权限管理": 50,

    # 标准模块：35 行
    "场景模式": 35, "社区": 35, "商城": 35, "摄像状态": 35,
    "信息中岛": 35, "多模态交互": 35, "AI语音助手": 35,
    "主动安全预警提示": 40, "设备互联": 35, "设备配对流程": 35,
    "SOS与紧急救援": 35, "部件识别与兼容性管理": 35,
    "通知中心": 35, "AI Tab": 35, "相册Tab": 35,
    "多语言支持": 35, "AI功能": 35, "恢复出厂设置": 35,

    # 简单模块：25 行
    "开机动画": 25, "速度": 25, "来电": 25, "消息": 25,
    "音乐": 25, "胎温胎压": 25, "佩戴检测与电源管理": 25,
    "生命体征与疲劳监测": 25, "氛围灯交互": 25,
    "视觉交互": 25, "语音交互": 25, "实体按键交互": 25,
    "设备状态": 25,
}

DEFAULT_DENSITY_LIMIT = 35
```

#### 新增精简函数

```python
def _compress_module(module_name: str, features: list, limit: int) -> list:
    """对超限模块调用 LLM 合并精简

    Args:
        module_name: 模块名
        features: 当前功能列表
        limit: 行数上限
    Returns:
        精简后的功能列表（≤ limit 条）
    """
    if len(features) <= limit:
        return features

    print(f"  [Compress] {module_name}: {len(features)} 条 → 目标 ≤{limit} 条")

    # 分离 P0（不可删除）和非 P0
    p0_features = [f for f in features if f.get('priority') == 'P0']
    other_features = [f for f in features if f.get('priority') != 'P0']

    # 如果仅 P0 就超限，只精简非 P0 为 0
    if len(p0_features) >= limit:
        print(f"  [Compress] ⚠️ {module_name} 仅 P0 就有 {len(p0_features)} 条，超过上限 {limit}")
        return p0_features[:limit]

    remaining_budget = limit - len(p0_features)

    # 用 LLM 精简非 P0 部分
    compress_prompt = f"""你是 PRD 精简专家。以下模块「{module_name}」有 {len(other_features)} 条非P0功能，需要精简到 {remaining_budget} 条以内。

精简规则：
1. 同一件事的不同说法（如"蓝牙断连重连"和"蓝牙连接中断恢复"）→ 合并为一条，保留描述最完整的
2. L3 粒度过细的功能 → 合并到对应 L2，不需要每个细节都独立成行
3. 纯异常/边界场景如果跟正常功能重复 → 合并到正常功能的验收标准中
4. 保留所有独立功能点，只删除冗余表述
5. 输出精简后的 JSON 数组，格式与输入相同

当前功能列表（{len(other_features)} 条）：
{json.dumps(other_features, ensure_ascii=False, indent=1)[:8000]}

只输出 JSON 数组，不要其他内容。精简到 {remaining_budget} 条以内。"""

    result = _call_llm(compress_prompt, task_type="compress_module")

    if result and result.get("success"):
        try:
            resp = result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            compressed = json.loads(resp)

            if isinstance(compressed, list) and len(compressed) <= remaining_budget:
                final = p0_features + compressed
                print(f"  [Compress] ✅ {module_name}: {len(features)} → {len(final)} 条")
                return final
            else:
                print(f"  [Compress] ⚠️ LLM 返回 {len(compressed)} 条，超过预算 {remaining_budget}")
                # 截断兜底
                return p0_features + compressed[:remaining_budget]
        except Exception as e:
            print(f"  [Compress] ❌ JSON 解析失败: {e}")

    # LLM 失败兜底：按优先级截断
    print(f"  [Compress] 降级：按优先级截断")
    priority_order = {"P1": 0, "P2": 1, "P3": 2}
    other_features.sort(key=lambda f: priority_order.get(f.get('priority', 'P3'), 3))
    return p0_features + other_features[:remaining_budget]
```

#### 调用位置

在 Compare 之后、Export 之前，对所有模块执行密度检查：

```python
# === Layer 3: 密度控制 ===
print(f"\n[DensityCap] 检查模块密度上限...")
for module_name in module_names:
    limit = MODULE_DENSITY_LIMITS.get(module_name, DEFAULT_DENSITY_LIMIT)
    features = all_features_by_module[module_name]
    if len(features) > limit:
        all_features_by_module[module_name] = _compress_module(module_name, features, limit)
    else:
        # 不超限，不处理
        pass

# 统计
total_before = sum(len(v) for v in all_features_by_module_before.values())
total_after = sum(len(v) for v in all_features_by_module.values())
print(f"[DensityCap] {total_before} → {total_after} 条 (精简 {total_before - total_after})")
```

#### 验证

日志应出现 `[Compress]` 条目，超限模块被精简。最终总功能数应稳定在 800-1200 之间。

---

### Layer 4：模块级微循环 QA（交付前质量锁定）

#### 原则

每个模块生成后立即做规则检查 + 轻量 LLM 审查，不合格则带反馈重生成一次。在单模块粒度上收敛质量，不需要整体循环。

#### 新增 QA 函数

```python
def _module_qa_check(module_name: str, features: list) -> dict:
    """模块级质量检查——纯规则 + 轻量 LLM

    Returns:
        {"pass": bool, "issues": [...], "auto_fixable": [...]}
    """
    issues = []
    auto_fixable = []

    for f in features:
        fid = f.get('功能ID', f.get('id', ''))
        name = f.get('name', f.get('L2功能', f.get('L3功能', '')))

        # Rule 1: 空描述
        desc = f.get('description', f.get('描述', ''))
        if not desc or len(str(desc).strip()) < 10:
            issues.append(f"[空描述] {fid} {name}")

        # Rule 2: 空验收标准
        acc = f.get('acceptance', f.get('验收标准', ''))
        if not acc or len(str(acc).strip()) < 10:
            issues.append(f"[空验收] {fid} {name}")

        # Rule 3: L1/L2/L3 层级错误（L1 有值但不等于 module_name）
        l1 = f.get('module', f.get('L1功能', ''))
        level = f.get('level', '')
        if level == 'L1' and l1 and l1 != module_name:
            issues.append(f"[L1错位] {fid} L1={l1} 应为 {module_name}")
            auto_fixable.append(('fix_l1', fid, module_name))

        # Rule 4: 功能ID前缀一致性
        # 同一模块的 ID 前缀应一致（如 HUD-008 系列不该出现在商城里）
        # 这个规则需要模块级上下文，此处简化为检查异常前缀

        # Rule 5: 优先级缺失
        pri = f.get('priority', f.get('优先级', ''))
        if not pri or pri not in ('P0', 'P1', 'P2', 'P3'):
            issues.append(f"[无优先级] {fid} {name}")
            auto_fixable.append(('fix_priority', fid, 'P2'))

    # Rule 6: 模块内 L2 功能名重复
    l2_names = [f.get('L2功能', f.get('name', '')) for f in features
                if f.get('level') in ('L2', '') and pd.notna(f.get('L2功能', f.get('name')))]
    seen = set()
    for n in l2_names:
        if n in seen:
            issues.append(f"[L2重复] {module_name} 有重复 L2: {n}")
        seen.add(n)

    passed = len(issues) == 0
    if not passed:
        print(f"  [QA] {module_name}: {len(issues)} 个问题")
        for iss in issues[:5]:
            print(f"    {iss}")
        if len(issues) > 5:
            print(f"    ...还有 {len(issues) - 5} 个")
    else:
        print(f"  [QA] ✅ {module_name}: 通过")

    return {"pass": passed, "issues": issues, "auto_fixable": auto_fixable}


def _module_qa_autofix(features: list, auto_fixable: list) -> list:
    """自动修复可修复的问题"""
    fix_map = {}
    for fix_type, fid, value in auto_fixable:
        fix_map[(fix_type, fid)] = value

    for f in features:
        fid = f.get('功能ID', f.get('id', ''))
        if ('fix_l1', fid) in fix_map:
            f['L1功能'] = fix_map[('fix_l1', fid)]
            f['module'] = fix_map[('fix_l1', fid)]
        if ('fix_priority', fid) in fix_map:
            f['优先级'] = fix_map[('fix_priority', fid)]
            f['priority'] = fix_map[('fix_priority', fid)]

    return features
```

#### 调用位置：嵌入生成主循环

在每个模块生成完成后（`✅ [N/44] 模块名: +X 条` 之后），立即执行 QA：

```python
# 在单模块生成成功后
features = parse_llm_response(response)

# === Layer 4: 模块级微循环 QA ===
qa_result = _module_qa_check(module_name, features)

if not qa_result["pass"]:
    # 自动修复
    if qa_result["auto_fixable"]:
        features = _module_qa_autofix(features, qa_result["auto_fixable"])
        print(f"  [QA-Fix] 自动修复 {len(qa_result['auto_fixable'])} 个问题")

    # 严重问题（>5 个非自动修复问题）→ 带反馈重生成一次
    non_auto_issues = [i for i in qa_result["issues"]
                       if not any(af[1] in i for af in qa_result["auto_fixable"])]

    if len(non_auto_issues) > 5:
        print(f"  [QA-Retry] {module_name} 严重问题 {len(non_auto_issues)} 个，重生成...")
        feedback = "\n".join(non_auto_issues[:10])
        retry_features = _regenerate_module_with_feedback(module_name, prompt, feedback)
        if retry_features and len(retry_features) > len(features) * 0.5:
            features = retry_features
            print(f"  [QA-Retry] ✅ 重生成完成: {len(features)} 条")
        else:
            print(f"  [QA-Retry] ⚠️ 重生成失败或质量更差，保留原版")

# QA 通过（或修复后），锁定
all_features_by_module[module_name] = features
```

#### 验证

每个模块生成后日志应出现 `[QA] ✅ 模块名: 通过` 或 `[QA] 模块名: X 个问题`。

---

## 附加修复（随本次改造一起提交）

### Fix A：Mermaid v9 降级

**这个 bug 已跨 3 轮未修复，本次必须确认执行。**

搜索 `structured_doc.py` 中生成 HTML 的代码段：

**1) CDN 链接替换**
```
旧: https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js
新: https://cdn.jsdelivr.net/npm/mermaid@9.4.3/dist/mermaid.min.js
```

**2) mermaid.initialize 替换**
```javascript
// 旧:
mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'loose', flowchart: { useMaxWidth: true, htmlLabels: false } });
// 新:
mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'loose', flowchart: { useMaxWidth: true } });
```

**3) 所有 `mermaid.run(...)` 改为 `mermaid.init(...)`**

v9 没有 `mermaid.run()` API。搜索所有 `mermaid.run` 出现的位置（应有 4 处）：

```javascript
// 旧: mermaid.run({ querySelector: '.mermaid' });
// 新: mermaid.init(undefined, '.mermaid');

// 旧: mermaid.run({ nodes: body.querySelectorAll('.mermaid') });
// 新: mermaid.init(undefined, body.querySelectorAll('.mermaid'));

// 旧: mermaid.run()
// 新: mermaid.init()
```

**4) toggleFlowBody 中添加 `data-processed` 保护**

```javascript
// 展开时只对未渲染的 div 执行 init
const mermaidDivs = body.querySelectorAll('.mermaid:not([data-processed])');
if (mermaidDivs.length > 0 && typeof mermaid !== 'undefined') {
    try { mermaid.init(undefined, mermaidDivs); } catch(e) { console.error(e); }
}
```

### Fix B：幽灵模块过滤

在 Excel 写入前（Placement 之后），过滤掉不在 Anchor 定义中的 L1 模块：

```python
# 在写入 Excel 之前
valid_hud_modules = set(ANCHOR_HUD_MODULES)  # 从 Anchor 读取的 HUD 模块名集合
valid_app_modules = set(ANCHOR_APP_MODULES)  # 从 Anchor 读取的 App 模块名集合

# 过滤幽灵模块
hud_features = [f for f in hud_features if f.get('module') in valid_hud_modules]
app_features = [f for f in app_features if f.get('module') in valid_app_modules]

# 日志
filtered_count = original_count - len(hud_features) - len(app_features)
if filtered_count > 0:
    print(f"[GhostFilter] 过滤 {filtered_count} 条不在 Anchor 中的功能")
```

---

## 执行顺序

1. **Layer 1**（Anchor 唯一驱动）— 改 `_merge_anchor_and_prompt`，更新 `normalize_map`
2. **Layer 2**（Compare 替换模式）— 改 `_compare_module`，删除 OK+/KEEP+/MERGE 逻辑
3. **Layer 3**（密度上限 + 精简）— 新增 `MODULE_DENSITY_LIMITS` 和 `_compress_module`
4. **Layer 4**（模块级微循环 QA）— 新增 `_module_qa_check` 和调用点
5. **Fix A**（Mermaid v9 降级）— 替换 CDN + API 调用
6. **Fix B**（幽灵模块过滤）— Excel 写入前过滤

全部改完后：

```bash
git add -A && git commit -m "refactor: PRD architecture — anchor-driven, replace-mode compare, density cap, micro-loop QA, mermaid v9, ghost filter"
```

**不要重启服务，Leo 手动重启。**

---

## 预期效果

| 指标 | 当前 (R9) | 改造后预期 | 说明 |
|------|----------|-----------|------|
| 模块数 | 44→36（Normalize 后） | 36（生成时就是 36） | Layer 1 |
| 单轮功能增长 | +50% | ±10% | Layer 2 |
| 最大模块行数 | 149（导航） | ≤60 | Layer 3 |
| 总功能数 | 2038 | 800-1200 | Layer 1+2+3 |
| 空描述/空验收 | 未检查 | 0 | Layer 4 |
| Mermaid 渲染 | ❌ 全部失败 | ✅ | Fix A |
| 幽灵模块 | 2 个 | 0 | Fix B |
