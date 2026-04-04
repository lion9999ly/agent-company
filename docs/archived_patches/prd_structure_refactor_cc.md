# PRD 模块结构重组 — CC 适配文档

> 前置条件：anchor yaml 已替换，prd_v2_final_combined_fix.md 已执行
> 本文档处理：代码层面适配新的模块结构
> ⚠️ 不要重启服务，只做代码修改和 git commit

---

## 背景：模块结构变更摘要

Leo 手工调整了脑图结构，以下模块被合并或删除，anchor yaml 已同步更新：

| 原独立模块 | 归属变更 | normalize_map 映射 |
|------------|----------|-------------------|
| 简易路线 | → 导航 的 L2 子功能 | 简易路线 → 导航 |
| 简易 | → 导航 | 简易 → 导航 |
| 路线 | → 导航 | 路线 → 导航 |
| 显示队友位置 | → 组队 的 L2 子功能 | 显示队友位置 → 组队 |
| 自定义HUD显示 | → 场景模式 的子功能 | 自定义HUD显示 → 场景模式 |
| 日程提醒 | → 我的Tab/第三方应用联动 | 日程提醒 → 我的Tab |
| 身份认证 | → 我的Tab 的 L2 子功能 | 身份认证 → 我的Tab |
| 用户成就 | → 我的Tab 的 L2 子功能 | 用户成就 → 我的Tab |
| 手机消息同步 | → 我的Tab 的 L2 子功能 | 手机消息同步 → 我的Tab |
| 第三方应用联动 | → 我的Tab 的 L2 子功能 | 第三方应用联动 → 我的Tab |
| 社区Tab | → 改名为"社区" | 社区Tab → 社区 |
| 产品介绍 | 删除（非软件功能） | 产品介绍 → 设备配对流程 |
| 用户学习与新手引导 | 删除（融入配对流程） | 用户学习与新手引导 → 设备配对流程 |
| SOS与紧急救援 | 从 HUD 移到 App 端 | 不需要归一化，placement 自动处理 |

总模块数：46 → 36

---

## 适配 1: Placement 映射更新

找到 `_build_module_placement` 函数，确保新结构下的模块归属正确。

现在 anchor 中：
- hud_modules: 17 个（导航/来电/音乐/消息/AI语音助手/信息中岛/主动安全/组队/摄像/胎压/开机动画/速度/设备状态/生命体征/场景模式/佩戴检测/恢复出厂）
- app_modules: 10 个（设备Tab/相册Tab/社区/AI Tab/我的Tab/通知中心/商城/SOS与紧急救援/设备互联/设备配对流程）
- cross_cutting: 9 个（多语言/AI功能/语音交互/视觉交互/多模态交互/实体按键/氛围灯/部件识别/手机权限）

`_build_module_placement` 直接从 anchor 的 section 读取，不需要手动改映射——只要 anchor 正确，placement 就正确。但需要确认：

```bash
# 验证 placement 函数是否直接读 anchor sections
grep -A20 "_build_module_placement" scripts/feishu_handlers/structured_doc.py
```

如果函数中有硬编码的模块列表（如 `cross_to_hud = {'AI功能', ...}` 或 `cross_to_app = {'多语言支持', ...}`），需要更新：

```python
# cross_cutting 中归 HUD 的模块
cross_to_hud = {'AI功能', '语音交互', '视觉交互', '多模态交互', '实体按键交互', '氛围灯交互'}

# cross_cutting 中归 App 的模块  
cross_to_app = {'多语言支持', '手机系统权限管理', '部件识别与兼容性管理'}
```

---

## 适配 2: Prompt 中的模块列表（如有硬编码）

搜索代码中是否硬编码了旧模块名：

```bash
grep -n "简易路线\|显示队友位置\|自定义HUD显示\|日程提醒\|产品介绍\|用户学习与新手引导\|社区Tab\|身份认证\|用户成就\|手机消息同步\|第三方应用联动" scripts/feishu_handlers/structured_doc.py
```

如果搜到，需要判断是在 normalize_map 中（正确，保留）还是在其他逻辑中（需要更新为新名称）。

特别注意以下位置：
- `known_complex` 列表（哪些模块被标记为复杂需要拆解）
- `depth: deep` 模块列表
- Tab 名称列表（HTML 生成）
- 脑图 L1 分类逻辑

```bash
# 检查 known_complex 和 deep 模块列表
grep -n "known_complex\|deep_modules\|DEEP_MODULES" scripts/feishu_handlers/structured_doc.py
```

如果有硬编码的深度模块列表，更新为：

```python
DEEP_MODULES = [
    '导航',           # 含简易导航，内容多
    '场景模式',       # 含HUD自定义，内容多
    '组队',           # 含显示队友位置，内容多
    '我的Tab',        # 吸收了6个模块，内容最多
    'AI语音助手',
    '主动安全预警提示',
    'SOS与紧急救援',
    '设备Tab',
    'AI Tab',
    '部件识别与兼容性管理',
]
```

---

## 适配 3: 全量重生成时跳过不存在的模块

当 `anchor.get('hud_modules')` 返回 17 个模块时，如果 Prompt 中提到了旧模块名（如"简易路线"），合并逻辑会通过 normalize_map 将其映射到"导航"。但如果 Prompt 生成了一个名为"简易路线"的独立模块，归一化后它会合并到导航中——这是预期行为。

**确认 normalize_map 在以下 3 个位置都被调用**（之前的修复应该已经加了）：

```bash
grep -n "normalize_map\|_normalize_all_rows\|NormalizeAll" scripts/feishu_handlers/structured_doc.py
```

应该在：
1. 生成后、去重前
2. 去重后、分流前
3. 分流后、写入 Excel/HTML 前

如果只有 1-2 处，补加缺失的调用。

---

## 适配 4: HTML TAB_CONFIG 更新

找到 HTML 中的 TAB_CONFIG（Tab 配置列表），确认没有引用已删除的模块作为独立 Tab：

```bash
grep -n "TAB_CONFIG" scripts/feishu_handlers/structured_doc.py
```

TAB_CONFIG 应该是按 Sheet 类型（HUD/App/状态场景/语音/按键/灯效/...）分的，不是按功能模块分的。所以一般不需要改。但确认一下没有"简易路线 Tab"或"身份认证 Tab"这种错误配置。

---

## 适配 5: 脑图 L1 分类逻辑

如果脑图生成代码中有硬编码的 L1 分类（如 `hud_l1 = ['导航', '来电', ...]`），需要更新。

更好的做法是直接从 anchor 读取：

```python
# 从 anchor 动态获取 L1 分类
hud_l1_names = [m['name'] for m in anchor.get('hud_modules', [])]
app_l1_names = [m['name'] for m in anchor.get('app_modules', [])]
cross_l1_names = [m['name'] for m in anchor.get('cross_cutting', [])]
```

---

## 适配 6: 确认之前的 Bug 修复仍然生效

由于结构变了，确认以下修复仍然正确：

```bash
# Bug 1: get_column_letter 局部 import
grep -c "from openpyxl.utils import get_column_letter" scripts/feishu_handlers/structured_doc.py

# Bug 2: _clean_mermaid_code 函数存在
grep -c "_clean_mermaid_code" scripts/feishu_handlers/structured_doc.py

# Bug 3: 模块行数封顶
grep -c "MAX_PER_MODULE" scripts/feishu_handlers/structured_doc.py

# Bug 4: .mm 生成已注释
grep -c "\.mm" scripts/feishu_handlers/structured_doc.py
# 如果 > 0，确认是注释掉的

# Speed: 并行度
grep "max_workers\|PARALLEL_WORKERS" scripts/feishu_handlers/structured_doc.py
# 应该是 8
```

如果任何一项返回 0 或不符合预期，说明之前的修复没有生效，需要重新执行 `prd_v2_final_combined_fix.md` 中对应的修复。

---

## 执行完成

```bash
git add scripts/feishu_handlers/structured_doc.py .ai-state/product_spec_anchor.yaml
git commit --no-verify -m "refactor: 模块结构重组适配 (46→36模块)"
```

⚠️ **不要重启服务**。Leo 会手动重启。

---

## 验证清单

- [ ] `grep` 确认没有硬编码引用已删除的旧模块名（简易路线/显示队友位置等作为独立模块）
- [ ] DEEP_MODULES 列表已更新
- [ ] Placement 函数中 cross_to_hud / cross_to_app 已更新（如有）
- [ ] normalize_map 在 3 个位置被调用
- [ ] Bug 1-5 + Speed 修复仍然生效
- [ ] git commit 成功
