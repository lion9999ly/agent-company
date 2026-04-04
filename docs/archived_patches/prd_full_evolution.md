# PRD 输出全面进化 — 数据修复 + HTML 排版 + 知识库注入 + 远期规划

> 全部修改集中在 scripts/feishu_handlers/structured_doc.py
> 分三个执行优先级：立即执行 / Week 3 / 长期
> 立即执行部分预计 CC 工作量 30-40 分钟

---

## ============================================
## 立即执行（Phase 1 + HTML 修复 + 知识库注入）
## ============================================

### 1. AI 导航场景 Sheet 表头对齐四通道格式

找到 _gen_sheet7_voice_nav_scenarios 函数中的 prompt，修改输出 JSON 格式：

当前 key：scene, trigger, intent_type, system_response, action, fallback, context, priority, note

改为：
```
'{"scene":"场景名称","trigger":"触发条件","user_input":"用户输入(语音/按键/自动)",'
'"ai_action":"AI执行动作","hud_display":"HUD显示内容与样式",'
'"voice_output":"语音播报内容","light_effect":"灯光反馈",'
'"fallback":"异常兜底策略","priority":"P0-P3","note":"备注"}'
```

同时修改 _export_to_excel 中 voice_nav Sheet 的表头和 key 映射：

```python
        if extra_sheets.get("voice_nav"):
            ws7 = wb.create_sheet("AI语音导航场景")
            _write_generic_sheet(ws7, extra_sheets["voice_nav"],
                ["场景名称", "触发条件", "用户输入", "AI执行动作", "HUD显示", "语音播报", "灯光反馈", "异常兜底", "优先级", "备注"],
                ["scene", "trigger", "user_input", "ai_action", "hud_display", "voice_output", "light_effect", "fallback", "priority", "note"],
                [18, 20, 18, 24, 24, 24, 16, 24, 8, 16])
```

同时修改交互式 HTML 中 buildTableView 的 voice_nav 分支：

```javascript
    } else if (id === 'voice_nav') {
        data = DATA.voice_nav;
        headers = ['场景','触发','用户输入','AI动作','HUD显示','语音播报','灯光反馈','异常兜底','优先级','备注'];
        keys = ['scene','trigger','user_input','ai_action','hud_display','voice_output','light_effect','fallback','priority','note'];
    }
```

---

### 2. "我的"Tab 补全

在 _extract_l1_from_user_text 函数中，确认"我的"Tab 已在 app_tabs 中。

然后在 _gen_one 的 prompt 中，对"App-我的"模块追加额外指示：

```python
    # 在 _gen_one 中，对特定模块追加额外要求
    extra_hint = ""
    if name == "App-我的" or name == "我的":
        extra_hint = (
            "\n该模块除了账号与设置外，必须包含以下 L2：\n"
            "- 帮助与反馈（FAQ、在线客服、反馈提交）\n"
            "- 关于设备（SN、固件版本、保修状态、使用时长统计）\n"
            "- 隐私与协议（隐私政策、用户协议、数据授权管理）\n"
            "- 数据管理（骑行数据导出、视频批量导出、账号注销）\n"
        )
    
    batch_prompt = (
        f"为智能摩托车全盔项目生成「{name}」模块的功能清单。\n"
        f"模块归属：{module}\n"
        f"{extra_hint}\n"
        # ... 后续原有 prompt ...
    )
```

---

### 3. 按键映射改为场景矩阵格式

修改 _gen_sheet5_button_mapping 的 prompt，要求按"按键×场景"矩阵输出：

```python
def _gen_sheet5_button_mapping(gateway):
    prompt = (
        "为智能摩托车全盔项目生成【实体按键场景矩阵表】。\n"
        "头盔有以下按键：主按键(侧面)、音量+键、音量-键、功能键(可选)。\n"
        "同一个按键在不同场景下动作不同。\n\n"
        "输出 JSON 数组，每个元素代表一个按键在一个场景下的完整映射：\n"
        '{"button":"按键位置","scene":"场景(通用/导航中/通话中/录制中/组队中/音乐播放中/来电响铃中/语音助手激活中)",'
        '"single_click":"单击动作","double_click":"双击动作",'
        '"long_press":"长按动作(>2秒)","combo":"组合键动作",'
        '"feedback":"操作反馈(震动/语音/HUD/灯光)","note":"备注"}\n\n'
        "规则：\n"
        "1. 每个按键必须在所有 8 个场景下都有定义（4 按键 × 8 场景 = 32 条）\n"
        "2. 同一操作在不同场景可以含义不同（如通用单击=播放暂停，导航中单击=确认路线）\n"
        "3. 未定义的动作填'同通用'或'无'\n"
        "4. 每条必须标明操作反馈方式\n"
        "5. 骑行中戴手套操作，动作必须简单明确\n\n"
        "目标 32-40 条。只输出 JSON 数组。\n"
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

同时更新 Excel 和 HTML 的表头：

Excel:
```python
        if extra_sheets.get("button"):
            ws5 = wb.create_sheet("按键映射表")
            _write_generic_sheet(ws5, extra_sheets["button"],
                ["按键位置", "场景", "单击", "双击", "长按", "组合键", "操作反馈", "备注"],
                ["button", "scene", "single_click", "double_click", "long_press", "combo", "feedback", "note"],
                [14, 16, 20, 20, 20, 20, 16, 16])
```

HTML buildTableView:
```javascript
    } else if (id === 'button') {
        data = DATA.button_mapping;
        headers = ['按键','场景','单击','双击','长按','组合键','反馈','备注'];
        keys = ['button','scene','single_click','double_click','long_press','combo','feedback','note'];
    }
```

---

### 4. 去重逻辑加强

在合并 all_items 后、生成 ID 前，确认去重代码存在且生效：

```python
    # 模块名统一
    _normalize_module_names(all_items)
    
    # 去重（按名称+层级，不看模块——不同模块可能生成同名功能）
    seen = set()
    unique = []
    for item in all_items:
        # 用名称+层级作为去重 key
        key = (item.get("name", "").strip(), item.get("level", ""))
        if key not in seen:
            seen.add(key)
            unique.append(item)
        else:
            print(f"  [去重] {item.get('module')}/{item.get('name')}")
    
    if len(unique) < len(all_items):
        print(f"[FastTrack] 去重: {len(all_items)} → {len(unique)}")
    all_items = unique
```

---

### 5. HTML 排版修复（7 个问题）

修改 _generate_interactive_prd_html 函数中的 CSS 和 JS：

#### 5.1 L2 div 未闭合

buildTreeView 函数改为：

```javascript
function buildTreeView(features) {
    let html = '<div class="stats">';
    const counts = {};
    features.forEach(f => { counts[f.priority] = (counts[f.priority]||0) + 1; });
    Object.entries(counts).sort().forEach(([p,c]) => {
        html += `<div class="stat"><div class="num">${c}</div><div class="label">${p}</div></div>`;
    });
    html += `<div class="stat"><div class="num">${features.length}</div><div class="label">总计</div></div></div>`;

    let currentL1 = null, currentL2 = null;
    let l1Html = '';

    features.forEach(f => {
        const tag = `<span class="tag tag-${f.priority}">${f.priority}</span>`;
        if (f.level === 'L1') {
            if (currentL2) { l1Html += '</div>'; currentL2 = null; }
            if (currentL1) l1Html += '</div></div>';
            l1Html += `<div class="l1" data-name="${f.name}" data-priority="${f.priority}">
                <div class="l1-header" onclick="this.nextElementSibling.classList.toggle('open')">
                    ${tag} ${f.name} <span style="color:#999;font-size:12px;margin-left:auto">${f.interaction||''}</span>
                </div><div class="l1-body">`;
            currentL1 = f; currentL2 = null;
        } else if (f.level === 'L2') {
            if (currentL2) l1Html += '</div>';
            l1Html += `<div class="l2"><div class="l2-title" data-name="${f.name}" data-priority="${f.priority}">${tag} ${f.name}</div>`;
            currentL2 = f;
        } else if (f.level === 'L3') {
            l1Html += `<div class="l3" data-name="${f.name}" data-priority="${f.priority}">
                <span class="name">${tag} ${f.name}</span>
                <span class="desc">${f.description||''}</span>
                <span class="acc">${f.acceptance||''}</span></div>`;
        }
    });
    if (currentL2) l1Html += '</div>';
    if (currentL1) l1Html += '</div></div>';

    return html + l1Html;
}
```

#### 5.2 L3 flex 布局加宽度约束

CSS 中替换 .l3 相关样式：

```css
.l3 { margin-left: 24px; padding: 6px 0; font-size: 13px; color: #555; 
    border-bottom: 1px solid #f0f0f0; display: flex; gap: 12px; align-items: flex-start; }
.l3 .name { min-width: 160px; max-width: 220px; flex-shrink: 0; font-weight: 500; color: #333; }
.l3 .desc { flex: 1; min-width: 200px; color: #666; }
.l3 .acc { flex: 1; min-width: 200px; color: #4a9; font-size: 12px; }
```

#### 5.3 tabs sticky + th 高度修正

```css
.tabs { display: flex; background: #1a3a6c; padding: 0 30px; 
    position: sticky; top: 80px; z-index: 99; }
th { background: #2F5496; color: #fff; padding: 10px 12px; text-align: left; font-size: 13px; 
    position: sticky; top: 125px; z-index: 50; }
.content { padding: 20px 30px; max-width: 1600px; margin: 0 auto; }
```

#### 5.4 响应式适配

CSS 末尾加：

```css
@media (max-width: 768px) {
    .header h1 { font-size: 16px; }
    .controls { flex-direction: column; }
    .controls input { width: 100%; }
    .tabs { overflow-x: auto; white-space: nowrap; padding: 0 10px; }
    .tab { padding: 10px 14px; font-size: 12px; }
    .content { padding: 10px 12px; }
    .l3 { flex-direction: column; gap: 4px; }
    .l3 .name { max-width: none; }
    table { font-size: 12px; display: block; overflow-x: auto; }
    th, td { padding: 6px 8px; }
}
```

#### 5.5 筛选逻辑精确匹配

替换 filterAll 函数：

```javascript
function filterAll() {
    const q = document.getElementById('search').value.toLowerCase();
    const p = document.getElementById('priorityFilter').value;

    document.querySelectorAll('.l1').forEach(el => {
        const name = (el.dataset.name || '').toLowerCase();
        const priority = el.dataset.priority || '';
        const matchQ = !q || name.includes(q) || el.textContent.toLowerCase().includes(q);
        const matchP = !p || priority === p;
        el.classList.toggle('hidden', !(matchQ && matchP));
    });
    
    document.querySelectorAll('.l2, .l3').forEach(el => {
        const name = (el.dataset.name || '').toLowerCase();
        const priority = el.dataset.priority || '';
        const matchQ = !q || name.includes(q);
        const matchP = !p || priority === p;
        el.classList.toggle('hidden', !(matchQ && matchP));
    });

    document.querySelectorAll('tbody tr').forEach(tr => {
        const text = tr.textContent.toLowerCase();
        const matchQ = !q || text.includes(q);
        const tagEl = tr.querySelector('.tag');
        const rowP = tagEl ? tagEl.textContent.trim() : '';
        const matchP = !p || rowP === p;
        tr.classList.toggle('hidden', !(matchQ && matchP));
    });
}
```

#### 5.6 Tab 切换后滚动到顶部

```javascript
function switchTab(id) {
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.target === id));
    document.querySelectorAll('.section').forEach(s => s.classList.toggle('active', s.id === 'section-' + id));
    window.scrollTo(0, 0);
}
```

#### 5.7 默认展开第一个 L1

在 buildTabs() 调用后加：

```javascript
buildTabs();
const firstBody = document.querySelector('.l1-body');
if (firstBody) firstBody.classList.add('open');
```

---

### 6. 知识库注入（核心改动）

修改 _gen_one 函数，每个 L1 模块生成前先查知识库：

```python
def _gen_one(feature):
    name = feature["name"]
    module = feature["module"]
    
    # === 查知识库注入领域知识 ===
    from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt
    
    kb_queries = [
        f"{name} 技术参数 方案",
        f"{name} 竞品 Sena Cardo Forcite",
        f"{name} 认证 标准 要求",
    ]
    
    CORE_MODULES = {"导航", "主动安全预警提示", "AI语音助手", "Ai语音助手", 
                    "组队", "摄像状态", "胎温胎压", "设备状态"}
    
    if name in CORE_MODULES:
        kb_queries.extend([
            f"{name} 用户需求 场景 痛点",
            f"{name} 功耗 续航 热管理",
            f"{name} HUD 显示 交互设计",
        ])
    
    kb_context = ""
    for q in kb_queries:
        try:
            entries = search_knowledge(q, limit=3)
            if entries:
                kb_context += format_knowledge_for_prompt(entries)[:1500] + "\n"
        except:
            pass
    
    kb_context = kb_context[:5000 if name in CORE_MODULES else 3000]
    
    kb_inject = ""
    if kb_context:
        kb_inject = (
            f"\n\n## 项目知识库参考（必须基于这些真实数据）\n"
            f"以下是项目已有的研究数据，验收标准必须基于这些数据，不要凭空编造数字。\n"
            f"如果知识库有竞品数据，验收标准要对标或超越竞品。\n"
            f"如果知识库有认证要求，验收标准必须满足认证。\n"
            f"知识库中没有相关数据的，验收标准标注[待验证]。\n\n"
            f"{kb_context}\n"
        )
    
    # === "我的"Tab 额外指示 ===
    extra_hint = ""
    if "我的" in name:
        extra_hint = (
            "\n该模块除了账号与设置外，必须包含以下 L2：\n"
            "- 帮助与反馈（FAQ、在线客服、反馈提交）\n"
            "- 关于设备（SN、固件版本、保修状态、使用时长统计）\n"
            "- 隐私与协议（隐私政策、用户协议、数据授权管理）\n"
            "- 数据管理（骑行数据导出、视频批量导出、账号注销）\n"
        )
    
    batch_prompt = (
        f"为智能摩托车全盔项目生成「{name}」模块的功能清单。\n"
        f"模块归属：{module}\n"
        f"{extra_hint}"
        f"{kb_inject}\n"
        f"输出 JSON 数组，每个元素格式：\n"
        f'{{"module":"{module}","level":"L1或L2或L3","parent":"父功能名",'
        f'"name":"功能名称","priority":"P0-P3",'
        f'"interaction":"交互方式(HUD/语音/按键/App/灯光)",'
        f'"description":"一句话描述",'
        f'"acceptance":"可测试验收标准(基于知识库数据，含具体数字)",'
        f'"dependencies":"关联功能","note":"备注(标注关联页面/场景)"}}\n\n'
        f"规则：\n"
        f"- 第一条是 L1（{name}本身）\n"
        f"- L1 下至少 3 个 L2，每个 L2 至少 2 个 L3\n"
        f"- 验收标准必须基于知识库中的真实参数，没有数据的标注[待验证]\n"
        f"- 优先级分布：P0≤30%, P1约40%, P2约25%, P3约5%\n"
        f"- 模块名必须完全一致：{module}\n"
        f"- note 列标注关联页面（如'骑行主界面'、'App-设备Tab'）\n"
        f"- 你补充的功能在 note 标注[补充]\n"
        f"- 只输出 JSON 数组\n"
    )
    
    result = _gw.call_azure_openai("cpo", batch_prompt,
        "只输出JSON数组。", "structured_doc")
    
    if result.get("success"):
        import re as _re
        json_match = _re.search(r'\[[\s\S]*\]', result["response"])
        if json_match:
            try:
                import json as _json
                return _json.loads(json_match.group())
            except:
                pass
    return []
```

---

### 7. 失败模块自动重试

在并行生成完成后、去重之前：

```python
    # 检测失败模块并重试
    generated_modules = set()
    for item in all_items:
        if item.get("level") == "L1":
            generated_modules.add(item.get("name", ""))
    
    failed_features = [f for f in l1_features if f["name"] not in generated_modules]
    
    if failed_features:
        print(f"[FastTrack] {len(failed_features)} 个模块失败，重试中...")
        for feature in failed_features:
            try:
                batch = _gen_one(feature)
                if batch:
                    all_items.extend(batch)
                    print(f"  ✅ [重试] {feature['name']}: +{len(batch)} 条")
                else:
                    print(f"  ❌ [重试] {feature['name']}: 仍然失败")
            except Exception as e:
                print(f"  ❌ [重试] {feature['name']}: {e}")
```

---

## ============================================
## Phase 2 + Phase 3：全部一次性实现
## ============================================

### 8. PRD 版本管理

#### 8.1 每次生成后保存版本快照

在 try_structured_doc_fast_track 的 Excel 导出成功后：

```python
    # 保存版本快照
    try:
        import json as _json
        versions_dir = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "prd_versions"
        versions_dir.mkdir(parents=True, exist_ok=True)
        
        version_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot = {
            "version": version_id,
            "timestamp": datetime.now().isoformat(),
            "total_features": len(all_items),
            "l1_count": sum(1 for i in all_items if i.get("level") == "L1"),
            "l2_count": sum(1 for i in all_items if i.get("level") == "L2"),
            "l3_count": sum(1 for i in all_items if i.get("level") == "L3"),
            "priority_dist": {p: sum(1 for i in all_items if i.get("priority") == p) for p in ["P0","P1","P2","P3"]},
            "items": all_items,
            "extra_sheets_counts": {k: len(v) for k, v in (extra_sheets or {}).items()},
        }
        
        snap_path = versions_dir / f"prd_v_{version_id}.json"
        snap_path.write_text(_json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[Version] 版本快照已保存: {version_id}")
    except Exception as e:
        print(f"[Version] 保存失败: {e}")
```

#### 8.2 Excel 中新增"版本信息"Sheet

在 _export_to_excel 末尾（保存前）：

```python
    # 版本信息 Sheet
    ws_ver = wb.create_sheet("版本信息")
    ver_data = [
        ["项目", "智能骑行头盔 V1"],
        ["版本", datetime.now().strftime("v%Y%m%d.%H%M")],
        ["生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ["功能总数", len(items)],
        ["HUD端功能", len(hud_items)],
        ["App端功能", len(app_items)],
        ["P0功能数", sum(1 for i in items if i.get("priority") == "P0")],
        ["P1功能数", sum(1 for i in items if i.get("priority") == "P1")],
        ["P2功能数", sum(1 for i in items if i.get("priority") == "P2")],
        ["P3功能数", sum(1 for i in items if i.get("priority") == "P3")],
        ["状态场景数", len(extra_sheets.get("state", [])) if extra_sheets else 0],
        ["语音指令数", len(extra_sheets.get("voice", [])) if extra_sheets else 0],
        ["按键映射数", len(extra_sheets.get("button", [])) if extra_sheets else 0],
        ["灯效定义数", len(extra_sheets.get("light", [])) if extra_sheets else 0],
        ["导航场景数", len(extra_sheets.get("voice_nav", [])) if extra_sheets else 0],
        [],
        ["变更说明", ""],
    ]
    for row_idx, row_data in enumerate(ver_data, 1):
        for col_idx, val in enumerate(row_data, 1):
            cell = ws_ver.cell(row=row_idx, column=col_idx, value=val)
            if col_idx == 1:
                cell.font = Font(bold=True)
    ws_ver.column_dimensions['A'].width = 16
    ws_ver.column_dimensions['B'].width = 30
```

#### 8.3 版本对比函数

```python
def _compare_prd_versions(old_path: str, new_path: str) -> str:
    """对比两个版本的 PRD，生成变更清单"""
    import json as _json
    
    old = _json.loads(Path(old_path).read_text(encoding="utf-8"))
    new = _json.loads(Path(new_path).read_text(encoding="utf-8"))
    
    old_names = {(i["name"], i["level"]) for i in old.get("items", [])}
    new_names = {(i["name"], i["level"]) for i in new.get("items", [])}
    
    added = new_names - old_names
    removed = old_names - new_names
    
    # 优先级变更
    old_priorities = {i["name"]: i.get("priority", "") for i in old.get("items", [])}
    priority_changes = []
    for item in new.get("items", []):
        name = item["name"]
        new_p = item.get("priority", "")
        old_p = old_priorities.get(name, "")
        if old_p and new_p and old_p != new_p:
            priority_changes.append(f"{name}: {old_p} → {new_p}")
    
    report = (
        f"PRD 版本对比\n"
        f"旧版: {old.get('version', '?')} ({old.get('total_features', 0)} 条)\n"
        f"新版: {new.get('version', '?')} ({new.get('total_features', 0)} 条)\n\n"
        f"新增功能 ({len(added)} 条):\n" + "\n".join(f"  + {n} [{l}]" for n, l in sorted(added)[:20]) + "\n\n"
        f"移除功能 ({len(removed)} 条):\n" + "\n".join(f"  - {n} [{l}]" for n, l in sorted(removed)[:20]) + "\n\n"
        f"优先级变更 ({len(priority_changes)} 条):\n" + "\n".join(f"  ~ {c}" for c in priority_changes[:20]) + "\n"
    )
    return report
```

---

### 9. 自动生成用户故事 Sheet

新增 _gen_user_stories 函数，并行生成后写入 Excel：

```python
def _gen_user_stories(items, gateway):
    """基于功能清单生成用户故事"""
    
    # 提取所有 L2 功能
    l2_features = [i for i in items if i.get("level") == "L2"]
    
    # 按批次处理（每批 15 个 L2，一次 LLM 调用）
    all_stories = []
    batch_size = 15
    
    for start in range(0, len(l2_features), batch_size):
        batch = l2_features[start:start + batch_size]
        features_text = "\n".join(
            f"- {f.get('name', '')}（{f.get('module', '')}）: {f.get('description', '')}"
            for f in batch
        )
        
        prompt = (
            f"为以下功能生成用户故事（User Story）。\n"
            f"输出 JSON 数组，每个元素：\n"
            f'{{"feature":"功能名","role":"用户角色","story":"作为[角色]，我想要[功能]，以便[价值]",'
            f'"acceptance":"验收条件","priority":"P0-P3"}}\n\n'
            f"角色库（选最合适的）：通勤骑手、摩旅骑手、团骑领队、内容创作骑手、新手骑手、后台管理员\n\n"
            f"功能列表：\n{features_text}\n\n"
            f"每个功能一条故事。只输出 JSON。"
        )
        
        result = gateway.call_azure_openai("cpo", prompt,
            "生成用户故事。只输出JSON。", "structured_doc")
        
        if result.get("success"):
            import re, json
            match = re.search(r'\[[\s\S]*\]', result["response"])
            if match:
                try:
                    all_stories.extend(json.loads(match.group()))
                except:
                    pass
    
    print(f"[UserStory] 生成 {len(all_stories)} 条用户故事")
    return all_stories
```

Excel 中写入：

```python
        if user_stories:
            ws_story = wb.create_sheet("用户故事")
            _write_generic_sheet(ws_story, user_stories,
                ["功能名", "用户角色", "用户故事", "验收条件", "优先级"],
                ["feature", "role", "story", "acceptance", "priority"],
                [24, 14, 50, 36, 8])
```

---

### 10. PRD → 测试用例 Sheet

```python
def _gen_test_cases(items, gateway):
    """基于 L3 验收标准生成测试用例"""
    
    l3_features = [i for i in items if i.get("level") == "L3" and i.get("acceptance")]
    all_cases = []
    batch_size = 15
    
    for start in range(0, len(l3_features), batch_size):
        batch = l3_features[start:start + batch_size]
        features_text = "\n".join(
            f"- {f.get('name', '')}: 验收={f.get('acceptance', '')}"
            for f in batch
        )
        
        prompt = (
            f"为以下功能的验收标准生成测试用例。\n"
            f"输出 JSON 数组，每个元素：\n"
            f'{{"case_id":"TC-001","feature":"功能名","title":"用例标题",'
            f'"precondition":"前置条件","steps":"操作步骤(分号分隔)",'
            f'"expected":"预期结果","priority":"P0-P3"}}\n\n'
            f"规则：\n"
            f"- 每个功能 1-2 条用例（正常流程 + 异常流程）\n"
            f"- 操作步骤要具体可执行\n"
            f"- 预期结果要包含验收标准中的具体数字\n\n"
            f"功能列表：\n{features_text}\n\n"
            f"只输出 JSON。"
        )
        
        result = gateway.call_azure_openai("cpo", prompt,
            "生成测试用例。只输出JSON。", "structured_doc")
        
        if result.get("success"):
            import re, json
            match = re.search(r'\[[\s\S]*\]', result["response"])
            if match:
                try:
                    cases = json.loads(match.group())
                    # 自动编号
                    for idx, c in enumerate(cases):
                        c["case_id"] = f"TC-{start + idx + 1:04d}"
                    all_cases.extend(cases)
                except:
                    pass
    
    print(f"[TestCase] 生成 {len(all_cases)} 条测试用例")
    return all_cases
```

Excel 中写入：

```python
        if test_cases:
            ws_tc = wb.create_sheet("测试用例")
            _write_generic_sheet(ws_tc, test_cases,
                ["用例ID", "功能名", "用例标题", "前置条件", "操作步骤", "预期结果", "优先级"],
                ["case_id", "feature", "title", "precondition", "steps", "expected", "priority"],
                [12, 20, 24, 24, 36, 30, 8])
```

---

### 11. PRD → 页面流程图

```python
def _gen_page_mapping(items, gateway):
    """从功能清单生成页面→功能映射表"""
    
    # 提取所有 note 中的页面信息
    pages_mentioned = set()
    for item in items:
        note = item.get("note", "")
        if note:
            # 提取页面关键词
            for page in re.findall(r'(骑行主界面|App-\S+|首次配对|设置页|导航页|录制页|组队页|商城\S*|社区\S*)', note):
                pages_mentioned.add(page)
    
    # 如果 note 中没有足够页面信息，让 LLM 生成
    l1_l2 = [i for i in items if i.get("level") in ("L1", "L2")]
    features_text = "\n".join(f"- {f.get('name', '')}（{f.get('module', '')}）" for f in l1_l2[:60])
    
    prompt = (
        f"基于以下智能摩托车全盔的功能列表，生成页面→功能映射表。\n"
        f"输出 JSON 数组，每个元素代表一个页面：\n"
        f'{{"page":"页面名","parent":"父页面(顶级填空)","platform":"HUD/App/系统",'
        f'"features":"该页面包含的功能(逗号分隔)","entry":"入口方式(Tab/按钮/自动/语音)",'
        f'"priority":"P0-P3","note":"备注"}}\n\n'
        f"页面分类：\n"
        f"- HUD 页面：骑行主界面、导航态、来电态、录制态、组队态、预警态、设置态\n"
        f"- App 页面：设备Tab首页、社区Tab、商城Tab、我的Tab、导航页、录制管理、组队管理、设置页、配对引导页\n"
        f"- 系统页面：开机自检、首次使用引导、权限申请、OTA升级\n\n"
        f"功能列表：\n{features_text}\n\n"
        f"目标 25-35 个页面。只输出 JSON。"
    )
    
    result = gateway.call_azure_openai("cpo", prompt,
        "生成页面映射。只输出JSON。", "structured_doc")
    
    if result.get("success"):
        match = re.search(r'\[[\s\S]*\]', result["response"])
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
    return []
```

Excel 中写入：

```python
        if page_mapping:
            ws_page = wb.create_sheet("页面映射表")
            _write_generic_sheet(ws_page, page_mapping,
                ["页面名", "父页面", "平台", "包含功能", "入口方式", "优先级", "备注"],
                ["page", "parent", "platform", "features", "entry", "priority", "note"],
                [20, 16, 10, 40, 16, 8, 20])
```

---

### 12. PRD → 开发任务拆分

```python
def _gen_dev_tasks(items, gateway):
    """基于功能清单生成开发任务清单（含工时估算）"""
    
    l2_features = [i for i in items if i.get("level") == "L2"]
    all_tasks = []
    batch_size = 15
    
    for start in range(0, len(l2_features), batch_size):
        batch = l2_features[start:start + batch_size]
        features_text = "\n".join(
            f"- {f.get('name', '')}（{f.get('module', '')}）: {f.get('description', '')[:60]}"
            for f in batch
        )
        
        prompt = (
            f"为以下功能生成开发任务清单（含工时估算）。\n"
            f"输出 JSON 数组，每个元素：\n"
            f'{{"task_id":"T-001","feature":"功能名","task":"任务描述",'
            f'"assignee":"负责角色(前端/后端/嵌入式/算法/测试/设计)",'
            f'"effort_days":"预估工时(天)","dependency":"前置依赖任务",'
            f'"sprint":"建议迭代(Sprint1-MVP/Sprint2-增强/Sprint3-优化)",'
            f'"priority":"P0-P3","note":"备注"}}\n\n'
            f"工时估算规则：\n"
            f"- 简单UI展示: 0.5-1天\n"
            f"- 标准功能开发: 1-3天\n"
            f"- 复杂交互/算法: 3-5天\n"
            f"- 跨端联调: 2-3天\n"
            f"- 每个 L2 功能拆成 1-3 个开发任务\n\n"
            f"功能列表：\n{features_text}\n\n"
            f"只输出 JSON。"
        )
        
        result = gateway.call_azure_openai("cpo", prompt,
            "生成开发任务。只输出JSON。", "structured_doc")
        
        if result.get("success"):
            match = re.search(r'\[[\s\S]*\]', result["response"])
            if match:
                try:
                    tasks = json.loads(match.group())
                    for idx, t in enumerate(tasks):
                        t["task_id"] = f"T-{start + idx + 1:04d}"
                    all_tasks.extend(tasks)
                except:
                    pass
    
    print(f"[DevTask] 生成 {len(all_tasks)} 条开发任务")
    return all_tasks
```

Excel 中写入：

```python
        if dev_tasks:
            ws_dev = wb.create_sheet("开发任务")
            _write_generic_sheet(ws_dev, dev_tasks,
                ["任务ID", "功能名", "任务描述", "负责角色", "预估工时(天)", "前置依赖", "建议迭代", "优先级", "备注"],
                ["task_id", "feature", "task", "assignee", "effort_days", "dependency", "sprint", "priority", "note"],
                [10, 20, 30, 14, 12, 20, 16, 8, 16])
```

---

### 13. 主流程串接：并行生成所有额外 Sheet

在 try_structured_doc_fast_track 的 is_full_spec 分支中，把所有额外 Sheet 一起并行生成：

```python
    if is_full_spec:
        print("[FastTrack] 完整规格书模式：并行生成所有额外 Sheet")
        send_reply(reply_target, "📋 功能清单完成，正在生成状态对策/语音/按键/灯效/导航场景/用户故事/测试用例/页面映射/开发任务...", reply_type)
        
        extra_sheets = {}
        
        # 第一批：4 路并行（不依赖功能清单）
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
                print(f"  ✅ {name}: {len(data)} 条")
        
        # 第二批：4 路并行（依赖功能清单 all_items）
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures2 = {
                pool.submit(_gen_sheet7_voice_nav_scenarios, _gw, kb_context): "voice_nav",
                pool.submit(_gen_user_stories, all_items, _gw): "user_stories",
                pool.submit(_gen_test_cases, all_items, _gw): "test_cases",
                pool.submit(_gen_page_mapping, all_items, _gw): "page_mapping",
            }
            for future in as_completed(futures2):
                name = futures2[future]
                data = future.result()
                extra_sheets[name] = data
                print(f"  ✅ {name}: {len(data)} 条")
        
        # 第三批：开发任务（依赖功能清单）
        try:
            dev_tasks = _gen_dev_tasks(all_items, _gw)
            extra_sheets["dev_tasks"] = dev_tasks
            print(f"  ✅ dev_tasks: {len(dev_tasks)} 条")
        except Exception as e:
            print(f"  ❌ dev_tasks: {e}")
        
        total_extra = sum(len(v) for v in extra_sheets.values())
        print(f"[FastTrack] 额外 Sheet 完成: {total_extra} 条")
```

_export_to_excel 中补上新 Sheet 的写入：

```python
        # 原有 Sheet 3-7 写入（已有）
        # ...
        
        # 新增 Sheet 8-11
        user_stories = extra_sheets.get("user_stories", [])
        if user_stories:
            ws_story = wb.create_sheet("用户故事")
            _write_generic_sheet(ws_story, user_stories,
                ["功能名", "用户角色", "用户故事", "验收条件", "优先级"],
                ["feature", "role", "story", "acceptance", "priority"],
                [24, 14, 50, 36, 8])
        
        test_cases = extra_sheets.get("test_cases", [])
        if test_cases:
            ws_tc = wb.create_sheet("测试用例")
            _write_generic_sheet(ws_tc, test_cases,
                ["用例ID", "功能名", "用例标题", "前置条件", "操作步骤", "预期结果", "优先级"],
                ["case_id", "feature", "title", "precondition", "steps", "expected", "priority"],
                [12, 20, 24, 24, 36, 30, 8])
        
        page_mapping = extra_sheets.get("page_mapping", [])
        if page_mapping:
            ws_page = wb.create_sheet("页面映射表")
            _write_generic_sheet(ws_page, page_mapping,
                ["页面名", "父页面", "平台", "包含功能", "入口方式", "优先级", "备注"],
                ["page", "parent", "platform", "features", "entry", "priority", "note"],
                [20, 16, 10, 40, 16, 8, 20])
        
        dev_tasks = extra_sheets.get("dev_tasks", [])
        if dev_tasks:
            ws_dev = wb.create_sheet("开发任务")
            _write_generic_sheet(ws_dev, dev_tasks,
                ["任务ID", "功能名", "任务描述", "负责角色", "预估工时(天)", "前置依赖", "建议迭代", "优先级", "备注"],
                ["task_id", "feature", "task", "assignee", "effort_days", "dependency", "sprint", "priority", "note"],
                [10, 20, 30, 14, 12, 20, 16, 8, 16])
```

交互式 HTML 的 buildTableView 中追加新 Tab 数据映射：

```javascript
    } else if (id === 'user_stories') {
        data = DATA.user_stories || [];
        headers = ['功能名','角色','用户故事','验收条件','优先级'];
        keys = ['feature','role','story','acceptance','priority'];
    } else if (id === 'test_cases') {
        data = DATA.test_cases || [];
        headers = ['用例ID','功能名','标题','前置条件','步骤','预期结果','优先级'];
        keys = ['case_id','feature','title','precondition','steps','expected','priority'];
    } else if (id === 'page_mapping') {
        data = DATA.page_mapping || [];
        headers = ['页面','父页面','平台','功能','入口','优先级','备注'];
        keys = ['page','parent','platform','features','entry','priority','note'];
    } else if (id === 'dev_tasks') {
        data = DATA.dev_tasks || [];
        headers = ['任务ID','功能','描述','角色','工时','依赖','迭代','优先级','备注'];
        keys = ['task_id','feature','task','assignee','effort_days','dependency','sprint','priority','note'];
    }
```

TAB_CONFIG 追加新 Tab：

```javascript
const TAB_CONFIG = [
    {id: "hud", label: "HUD及头盔端", type: "tree"},
    {id: "app", label: "App端", type: "tree"},
    {id: "state", label: "状态场景对策", type: "table"},
    {id: "voice", label: "语音指令表", type: "table"},
    {id: "button", label: "按键映射表", type: "table"},
    {id: "light", label: "灯效定义表", type: "table"},
    {id: "voice_nav", label: "AI语音导航", type: "table"},
    {id: "user_stories", label: "用户故事", type: "table"},
    {id: "test_cases", label: "测试用例", type: "table"},
    {id: "page_mapping", label: "页面映射", type: "table"},
    {id: "dev_tasks", label: "开发任务", type: "table"},
];
```

Tab 数量计算也要更新：

```javascript
    if (tab.id === 'user_stories') count = (DATA.user_stories || []).length;
    else if (tab.id === 'test_cases') count = (DATA.test_cases || []).length;
    else if (tab.id === 'page_mapping') count = (DATA.page_mapping || []).length;
    else if (tab.id === 'dev_tasks') count = (DATA.dev_tasks || []).length;
```

---

### 14. 关键词检测更新

is_full_spec 的关键词扩展：

```python
    is_full_spec = any(kw in text for kw in [
        "规格书", "状态场景", "语音指令", "按键映射", "灯效", 
        "6个Sheet", "7个Sheet", "完整PRD", "导航场景",
        "用户故事", "测试用例", "页面映射", "开发任务", "全部Sheet"
    ])
```

---

## 验证清单

```bash
# 1. 确认所有函数存在
python -c "
from scripts.feishu_handlers.structured_doc import (
    _gen_one, _gen_sheet3_state_scenarios, _gen_sheet4_voice_commands,
    _gen_sheet5_button_mapping, _gen_sheet6_light_effects,
    _gen_sheet7_voice_nav_scenarios, _export_to_excel,
    _generate_mindmap_mm, _generate_mindmap_svg,
    _generate_interactive_prd_html, try_structured_doc_fast_track
)
print('所有函数存在 OK')
"

# 2. 测试知识库注入
python -c "
from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt
entries = search_knowledge('导航 转向 HUD', limit=3)
ctx = format_knowledge_for_prompt(entries) if entries else ''
print(f'知识库上下文: {len(ctx)} 字')
print('OK')
"

# 3. 测试 Excel 导出（含新表头）
python -c "
from scripts.feishu_handlers.structured_doc import _export_to_excel
items = [
    {'module':'导航','level':'L1','parent':'','name':'导航','priority':'P0','interaction':'HUD','description':'test','acceptance':'test','dependencies':'','note':'骑行主界面'},
]
extra = {
    'button': [{'button':'主按键','scene':'通用','single_click':'播放','double_click':'唤醒','long_press':'关机','combo':'配对','feedback':'震动','note':''}],
    'voice_nav': [{'scene':'开始导航','trigger':'语音','user_input':'导航去公司','ai_action':'规划路线','hud_display':'导航中','voice_output':'已开始导航','light_effect':'蓝闪','fallback':'目的地不明确','priority':'P0','note':''}],
}
path = _export_to_excel(items, 'test', 'test', extra_sheets=extra)
from pathlib import Path
print(f'Excel: {Path(path).exists()}')
Path(path).unlink(missing_ok=True)
print('OK')
"

# 4. 重启后完整测试
# 飞书发：请输出头盔项目完整软件功能PRD规格书，Excel格式，包含7个Sheet...
# 检查：
# a. 导航模块的验收标准是否引用了知识库数据（而非编造数字）
# b. AI导航场景表头是否为四通道格式
# c. 按键映射是否为场景矩阵（每按键×每场景）
# d. "我的"Tab 是否包含帮助/关于/隐私/数据管理
# e. HTML 中 L1 展开后 L2/L3 嵌套正确
# f. HTML 搜索/筛选按优先级精确匹配
# g. 手机宽度下 HTML 不溢出
# h. 零重复功能
```
