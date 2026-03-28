# PRD 全面进化 — 一次性完成所有改进

> 全部修改集中在 scripts/feishu_handlers/structured_doc.py
> 包含：Phase 1 小修 + HTML 排版 + 知识库注入 + 重试策略 + 智能增量 + 一致性审计 + 新 Sheet + 优先级校准
> 共 13 项改动，按顺序执行

---

## 改动 1：AI 导航场景 Sheet 表头对齐四通道格式

找到 `_gen_sheet7_voice_nav_scenarios` 函数中的 prompt，修改 JSON 格式为：

```
'{"scene":"场景名称","trigger":"触发条件","user_input":"用户输入(语音/按键/自动)",'
'"ai_action":"AI执行动作","hud_display":"HUD显示内容与样式",'
'"voice_output":"语音播报内容","light_effect":"灯光反馈",'
'"fallback":"异常兜底策略","priority":"P0-P3","note":"备注"}'
```

同时更新 `_export_to_excel` 中 voice_nav Sheet 的表头和 key：

```python
        if extra_sheets.get("voice_nav"):
            ws7 = wb.create_sheet("AI语音导航场景")
            _write_generic_sheet(ws7, extra_sheets["voice_nav"],
                ["场景名称", "触发条件", "用户输入", "AI执行动作", "HUD显示", "语音播报", "灯光反馈", "异常兜底", "优先级", "备注"],
                ["scene", "trigger", "user_input", "ai_action", "hud_display", "voice_output", "light_effect", "fallback", "priority", "note"],
                [18, 20, 18, 24, 24, 24, 16, 24, 8, 16])
```

---

## 改动 2："我的"Tab 补全

在 `_gen_one` 函数中，对 App-我的 模块追加额外指示：

```python
    extra_hint = ""
    if "我的" in name:
        extra_hint = (
            "\n该模块除了账号与设置外，必须包含以下 L2：\n"
            "- 帮助与反馈（FAQ、在线客服、反馈提交）\n"
            "- 关于设备（SN、固件版本、保修状态、使用时长统计）\n"
            "- 隐私与协议（隐私政策、用户协议、数据授权管理）\n"
            "- 数据管理（骑行数据导出、视频批量导出、账号注销）\n"
        )
```

---

## 改动 3：按键映射改为场景矩阵

替换 `_gen_sheet5_button_mapping` 函数：

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
        "2. 同一操作在不同场景可以含义不同\n"
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

同时更新 Excel 和 HTML 中按键映射的表头：

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

## 改动 4：去重逻辑加强

在合并 all_items 后、生成 ID 前，确认去重代码如下：

```python
    _normalize_module_names(all_items)
    
    seen = set()
    unique = []
    for item in all_items:
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

## 改动 5：知识库注入（每个 L1 生成前查知识库）

修改 `_gen_one` 函数，在 prompt 构建前查知识库：

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
            f"验收标准必须基于这些数据，不要凭空编造数字。\n"
            f"竞品数据要对标或超越。认证要求必须满足。\n"
            f"知识库中没有数据的，验收标准标注[待验证]。\n\n"
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
        f"- 验收标准基于知识库真实参数，没有数据标[待验证]\n"
        f"- 优先级分布：P0≤30%, P1约40%, P2约25%, P3约5%\n"
        f"- 模块名必须完全一致：{module}\n"
        f"- note 列标注关联页面（如'骑行主界面'、'App-设备Tab'）\n"
        f"- 补充的功能在 note 标注[补充]\n"
        f"- 只输出 JSON 数组\n"
    )
    
    result = _gw.call_azure_openai("cpo", batch_prompt,
        "只输出JSON数组。", "structured_doc")
    
    if result.get("success"):
        import re as _re, json as _json
        json_match = _re.search(r'\[[\s\S]*\]', result["response"])
        if json_match:
            try:
                return _json.loads(json_match.group())
            except:
                pass
    return []
```

---

## 改动 6：重试策略升级（指数退避 + Gemini 降级 + 不编假数据）

新增 `_gen_one_with_gemini` 函数：

```python
def _gen_one_with_gemini(feature):
    """降级到 Gemini 生成单个模块"""
    name = feature["name"]
    module = feature["module"]
    
    from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt
    
    kb_context = ""
    for q in [f"{name} 技术参数", f"{name} 竞品", f"{name} 标准"]:
        try:
            entries = search_knowledge(q, limit=3)
            if entries:
                kb_context += format_knowledge_for_prompt(entries)[:1500] + "\n"
        except:
            pass
    kb_context = kb_context[:3000]
    
    kb_inject = f"\n\n## 知识库参考\n{kb_context}\n" if kb_context else ""
    
    extra_hint = ""
    if "我的" in name:
        extra_hint = "\n必须包含：帮助与反馈、关于设备、隐私与协议、数据管理。\n"
    
    batch_prompt = (
        f"为智能摩托车全盔项目生成「{name}」模块的功能清单。\n"
        f"模块归属：{module}\n"
        f"{extra_hint}{kb_inject}\n"
        f"输出 JSON 数组，每个元素格式：\n"
        f'{{"module":"{module}","level":"L1或L2或L3","parent":"父功能名",'
        f'"name":"功能名称","priority":"P0-P3",'
        f'"interaction":"交互方式","description":"描述",'
        f'"acceptance":"验收标准(含数字)","dependencies":"关联功能","note":"备注"}}\n\n'
        f"规则：第一条L1，下至少3个L2每个至少2个L3。验收标准基于知识库，无数据标[待验证]。\n"
        f"P0≤30% P1约40% P2约25%。只输出JSON。"
    )
    
    import re as _re, json as _json
    result = _gw.call_gemini("gemini_pro", batch_prompt,
        "只输出JSON数组。", "structured_doc_fallback")
    
    if result.get("success"):
        match = _re.search(r'\[[\s\S]*\]', result["response"])
        if match:
            try:
                return _json.loads(match.group())
            except:
                pass
    return []
```

替换当前失败模块重试逻辑为指数退避：

```python
    if failed_features:
        print(f"[FastTrack] {len(failed_features)} 个模块失败，指数退避重试...")
        import time as _time
        
        for feature in failed_features:
            success = False
            
            for attempt in range(3):
                wait = [5, 15, 30][attempt]
                use_gemini = (attempt >= 2)
                provider = "Gemini" if use_gemini else "Azure"
                
                print(f"  [重试 {attempt+1}/3] {feature['name']}（{provider}，等{wait}秒）")
                _time.sleep(wait)
                
                try:
                    if use_gemini:
                        batch = _gen_one_with_gemini(feature)
                    else:
                        batch = _gen_one(feature)
                    
                    if batch:
                        all_items.extend(batch)
                        print(f"  ✅ [重试成功] {feature['name']}: +{len(batch)} 条")
                        success = True
                        break
                except Exception as e:
                    print(f"  ❌ [重试 {attempt+1}] {feature['name']}: {e}")
            
            if not success:
                all_items.append({
                    "module": feature["module"], "level": "L1", "parent": "",
                    "name": feature["name"], "priority": "P0", "interaction": "",
                    "description": "[待生成] 该模块生成失败（3次重试均超时），请重新触发",
                    "acceptance": "[待生成]", "dependencies": "", "note": "生成失败"
                })
                print(f"  ⚠️ [放弃] {feature['name']}: 标记为[待生成]")
```

---

## 改动 7：智能增量迭代（自动检测历史版本）

在 try_structured_doc_fast_track 主流程中，并行生成开始前（l1_features 提取完后），插入：

```python
    # === 智能增量：自动检测历史版本并决定策略 ===
    import json as _json
    from datetime import datetime as _dt
    from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt, KB_ROOT
    
    versions_dir = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "prd_versions"
    prev_items = []
    regen_modules = set()
    keep_modules = {}
    is_incremental = False
    
    if versions_dir.exists():
        latest_files = sorted(versions_dir.glob("prd_v_*.json"), reverse=True)
        if latest_files:
            prev = _json.loads(latest_files[0].read_text(encoding="utf-8"))
            prev_items = prev.get("items", [])
            prev_version = prev.get("version", "")
            prev_time = prev.get("timestamp", "")
            
            print(f"[SmartIterate] 发现上一版: {prev_version} ({len(prev_items)} 条)")
            
            # 按 L1 名称分组
            current_l1_name = ""
            for item in prev_items:
                if item.get("level") == "L1":
                    current_l1_name = item.get("name", "")
                if current_l1_name:
                    if current_l1_name not in keep_modules:
                        keep_modules[current_l1_name] = []
                    keep_modules[current_l1_name].append(item)
            
            # 规则 1：上次失败的模块
            for item in prev_items:
                if "[待生成]" in item.get("description", "") or "[待生成]" in item.get("acceptance", ""):
                    regen_modules.add(item.get("name", ""))
                    print(f"  [重生成] {item.get('name')}: 上次失败")
            
            # 规则 2：审计问题模块
            audit_file = versions_dir.parent / "prd_audit_issues.json"
            if audit_file.exists():
                try:
                    issues = _json.loads(audit_file.read_text(encoding="utf-8"))
                    for issue in (issues if isinstance(issues, list) else []):
                        issue_text = issue.get("issue", "") if isinstance(issue, dict) else str(issue)
                        for mod_name in keep_modules:
                            if mod_name in issue_text and mod_name not in regen_modules:
                                regen_modules.add(mod_name)
                                print(f"  [重生成] {mod_name}: 审计问题")
                except:
                    pass
            
            # 规则 3：知识库有新数据的模块
            try:
                prev_dt = _dt.fromisoformat(prev_time) if prev_time else None
            except:
                prev_dt = None
            
            if prev_dt:
                for f in KB_ROOT.rglob("*.json"):
                    try:
                        if _dt.fromtimestamp(f.stat().st_mtime) > prev_dt:
                            data = _json.loads(f.read_text(encoding="utf-8"))
                            title = data.get("title", "").lower()
                            for mod_name in keep_modules:
                                if mod_name[:4].lower() in title and mod_name not in regen_modules:
                                    regen_modules.add(mod_name)
                                    print(f"  [重生成] {mod_name}: 知识库新数据")
                                    break
                    except:
                        continue
            
            # 规则 4：[待验证]现在有数据了
            for mod_name, items in keep_modules.items():
                if mod_name in regen_modules:
                    continue
                has_pending = any("[待验证]" in i.get("acceptance", "") for i in items)
                if has_pending:
                    try:
                        entries = search_knowledge(mod_name, limit=3)
                        if entries and len(format_knowledge_for_prompt(entries)) > 500:
                            regen_modules.add(mod_name)
                            print(f"  [重生成] {mod_name}: [待验证]现有数据")
                    except:
                        pass
            
            # 规则 5：内容太浅（L2<3 或 L3<6）
            for mod_name, items in keep_modules.items():
                if mod_name in regen_modules:
                    continue
                l2_count = sum(1 for i in items if i.get("level") == "L2")
                l3_count = sum(1 for i in items if i.get("level") == "L3")
                if l2_count < 3 or l3_count < 6:
                    regen_modules.add(mod_name)
                    print(f"  [重生成] {mod_name}: 太浅(L2={l2_count},L3={l3_count})")
            
            # 规则 6：用户明确要求改进的
            if any(kw in text for kw in ["深化", "改进", "重新", "优化", "补充"]):
                for mod_name in keep_modules:
                    if mod_name in text:
                        regen_modules.add(mod_name)
                        print(f"  [重生成] {mod_name}: 用户要求改进")
            
            # 规则 7：新模块
            for f in l1_features:
                if f["name"] not in keep_modules:
                    regen_modules.add(f["name"])
                    print(f"  [新模块] {f['name']}")
            
            is_incremental = len(regen_modules) < len(l1_features)
            print(f"\n[SmartIterate] {'增量' if is_incremental else '全量'}: "
                  f"重新生成 {len(regen_modules)}/{len(keep_modules)+len(regen_modules-set(keep_modules.keys()))} 个模块")
    
    # === 执行生成策略 ===
    if is_incremental and prev_items:
        keep_items = []
        for mod_name, items in keep_modules.items():
            if mod_name not in regen_modules:
                keep_items.extend(items)
        
        regen_features = [f for f in l1_features if f["name"] in regen_modules]
        
        send_reply(reply_target,
            f"📋 检测到上一版PRD（{len(prev_items)}条），智能增量更新中...\n"
            f"复用 {len(keep_modules) - len(regen_modules)} 个模块，重新生成 {len(regen_modules)} 个",
            reply_type)
        
        new_items = []
        done_count = 0
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
            futures = {pool.submit(_gen_one, f): f for f in regen_features}
            for future in as_completed(futures):
                feature = futures[future]
                batch = future.result()
                done_count += 1
                if batch:
                    new_items.extend(batch)
                    print(f"  ✅ [更新 {done_count}/{len(regen_features)}] {feature['name']}: +{len(batch)} 条")
                else:
                    print(f"  ❌ [更新 {done_count}/{len(regen_features)}] {feature['name']}: 失败")
        
        all_items = keep_items + new_items
        # 失败模块继续走改动 6 的指数退避重试
        
    else:
        # 全量生成（保持原有逻辑不变）
        pass
```

---

## 改动 8：全局优先级校准

新增函数，在主流程中去重后、审计前调用：

```python
def _calibrate_priorities(all_items):
    """全局优先级校准：确保 P0≤25%"""
    total = len(all_items)
    if total == 0:
        return
    
    p0_count = sum(1 for i in all_items if i.get("priority") == "P0")
    p0_ratio = p0_count / total
    
    if p0_ratio <= 0.25:
        print(f"[Calibrate] P0 占比 {p0_ratio:.0%}，无需校准")
        return
    
    print(f"[Calibrate] P0 占比 {p0_ratio:.0%} > 25%，开始校准...")
    
    CORE_MODULES = {"导航", "主动安全预警提示", "AI语音助手", "Ai语音助手",
                    "组队", "设备状态", "摄像状态"}
    
    p0_l3 = [i for i in all_items if i.get("priority") == "P0" and i.get("level") == "L3"]
    target_demote = p0_count - int(total * 0.25)
    demoted = 0
    
    for item in p0_l3:
        if demoted >= target_demote:
            break
        if item.get("module", "") not in CORE_MODULES:
            item["priority"] = "P1"
            demoted += 1
    
    new_p0 = sum(1 for i in all_items if i.get("priority") == "P0")
    print(f"[Calibrate] 降级 {demoted} 个 L3: P0 {p0_count}→{new_p0} ({new_p0/total:.0%})")
```

---

## 改动 9：跨模块一致性审计

新增函数：

```python
def _cross_module_audit(all_items, extra_sheets):
    """跨模块一致性审计"""
    import json as _json
    issues = []
    
    # 1. 功能标注"语音"交互但语音指令表无对应
    voice_commands = extra_sheets.get("voice", [])
    voice_texts = " ".join(str(vc) for vc in voice_commands).lower()
    for item in all_items:
        interaction = item.get("interaction", "")
        name = item.get("name", "")
        if "语音" in interaction and item.get("level") == "L2":
            if name[:4].lower() not in voice_texts:
                issues.append({"type": "功能-语音不一致",
                    "issue": f"「{name}」标注支持语音但语音指令表无对应",
                    "module": item.get("module", "")})
    
    # 2. 状态场景 vs 灯效交叉检查
    light_triggers = {le.get("trigger", "").lower() for le in extra_sheets.get("light", [])}
    for sc in extra_sheets.get("state", []):
        light = sc.get("light", "")
        scene = sc.get("current", "")
        if light and light != "无" and scene[:6].lower() not in " ".join(light_triggers):
            issues.append({"type": "场景-灯效不一致",
                "issue": f"状态场景「{scene[:30]}」有灯光提示但灯效表无对应",
                "module": "灯效"})
    
    # 3. 模块级 P0 占比过高
    p0_by_mod = {}
    total_by_mod = {}
    for item in all_items:
        mod = item.get("module", "")
        total_by_mod[mod] = total_by_mod.get(mod, 0) + 1
        if item.get("priority") == "P0":
            p0_by_mod[mod] = p0_by_mod.get(mod, 0) + 1
    for mod, p0 in p0_by_mod.items():
        total = total_by_mod.get(mod, 1)
        if p0 / total > 0.5:
            issues.append({"type": "优先级失衡",
                "issue": f"「{mod}」P0 占比 {p0/total:.0%}（{p0}/{total}），建议降级",
                "module": mod})
    
    # 4. [待生成][待验证] 统计
    pending_gen = sum(1 for i in all_items if "[待生成]" in i.get("description", ""))
    pending_verify = sum(1 for i in all_items if "[待验证]" in i.get("acceptance", ""))
    if pending_gen > 0:
        issues.append({"type": "生成不完整",
            "issue": f"{pending_gen} 个模块标记[待生成]，需重新触发", "module": "全局"})
    if pending_verify > 5:
        issues.append({"type": "验收待验证",
            "issue": f"{pending_verify} 个功能标记[待验证]，建议补充知识库后重新生成", "module": "全局"})
    
    if issues:
        print(f"\n[Audit] 发现 {len(issues)} 个一致性问题:")
        for iss in issues[:15]:
            print(f"  ⚠️ [{iss['type']}] {iss['issue'][:60]}")
    else:
        print("[Audit] 一致性检查通过 ✅")
    
    # 保存供下次迭代使用
    try:
        audit_path = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "prd_audit_issues.json"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(_json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")
    except:
        pass
    
    return issues
```

---

## 改动 10：新增 5 个 Sheet（用户故事/测试用例/页面映射/开发任务/版本信息）

### 10.1 用户故事

```python
def _gen_user_stories(items, gateway):
    l2_features = [i for i in items if i.get("level") == "L2"]
    all_stories = []
    batch_size = 15
    
    for start in range(0, len(l2_features), batch_size):
        batch = l2_features[start:start + batch_size]
        features_text = "\n".join(
            f"- {f.get('name','')}（{f.get('module','')}）: {f.get('description','')}"
            for f in batch
        )
        prompt = (
            f"为以下功能生成用户故事。输出 JSON 数组，每个元素：\n"
            f'{{"feature":"功能名","role":"用户角色","story":"作为[角色]，我想要[功能]，以便[价值]",'
            f'"acceptance":"验收条件","priority":"P0-P3"}}\n\n'
            f"角色库：通勤骑手、摩旅骑手、团骑领队、内容创作骑手、新手骑手\n"
            f"功能列表：\n{features_text}\n\n每个功能一条。只输出 JSON。"
        )
        result = gateway.call_azure_openai("cpo", prompt, "只输出JSON。", "structured_doc")
        if result.get("success"):
            import re, json
            match = re.search(r'\[[\s\S]*\]', result["response"])
            if match:
                try: all_stories.extend(json.loads(match.group()))
                except: pass
    
    print(f"[UserStory] 生成 {len(all_stories)} 条")
    return all_stories
```

### 10.2 测试用例

```python
def _gen_test_cases(items, gateway):
    l3_features = [i for i in items if i.get("level") == "L3" and i.get("acceptance")]
    all_cases = []
    batch_size = 15
    
    for start in range(0, len(l3_features), batch_size):
        batch = l3_features[start:start + batch_size]
        features_text = "\n".join(
            f"- {f.get('name','')}: 验收={f.get('acceptance','')}"
            for f in batch
        )
        prompt = (
            f"为以下验收标准生成测试用例。输出 JSON 数组，每个元素：\n"
            f'{{"case_id":"TC-001","feature":"功能名","title":"用例标题",'
            f'"precondition":"前置条件","steps":"操作步骤(分号分隔)",'
            f'"expected":"预期结果","priority":"P0-P3"}}\n\n'
            f"每个功能 1-2 条（正常+异常）。预期结果含验收标准的具体数字。\n"
            f"功能列表：\n{features_text}\n\n只输出 JSON。"
        )
        result = gateway.call_azure_openai("cpo", prompt, "只输出JSON。", "structured_doc")
        if result.get("success"):
            import re, json
            match = re.search(r'\[[\s\S]*\]', result["response"])
            if match:
                try:
                    cases = json.loads(match.group())
                    for idx, c in enumerate(cases):
                        c["case_id"] = f"TC-{start + idx + 1:04d}"
                    all_cases.extend(cases)
                except: pass
    
    print(f"[TestCase] 生成 {len(all_cases)} 条")
    return all_cases
```

### 10.3 页面映射表

```python
def _gen_page_mapping(items, gateway):
    l1_l2 = [i for i in items if i.get("level") in ("L1", "L2")]
    features_text = "\n".join(f"- {f.get('name','')}（{f.get('module','')}）" for f in l1_l2[:60])
    
    prompt = (
        f"基于以下功能列表生成页面→功能映射表。输出 JSON 数组，每个元素：\n"
        f'{{"page":"页面名","parent":"父页面(顶级填空)","platform":"HUD/App/系统",'
        f'"features":"该页面包含的功能(逗号分隔)","entry":"入口方式(Tab/按钮/自动/语音)",'
        f'"priority":"P0-P3","note":"备注"}}\n\n'
        f"页面分类：\n"
        f"- HUD：骑行主界面、导航态、来电态、录制态、组队态、预警态、设置态\n"
        f"- App：设备Tab、社区Tab、商城Tab、我的Tab、导航页、录制管理、组队管理、设置、配对引导\n"
        f"- 系统：开机自检、首次引导、权限申请、OTA升级\n\n"
        f"功能列表：\n{features_text}\n\n目标 25-35 页面。只输出 JSON。"
    )
    result = gateway.call_azure_openai("cpo", prompt, "只输出JSON。", "structured_doc")
    if result.get("success"):
        import re, json
        match = re.search(r'\[[\s\S]*\]', result["response"])
        if match:
            try: return json.loads(match.group())
            except: pass
    return []
```

### 10.4 开发任务

```python
def _gen_dev_tasks(items, gateway):
    l2_features = [i for i in items if i.get("level") == "L2"]
    all_tasks = []
    batch_size = 15
    
    for start in range(0, len(l2_features), batch_size):
        batch = l2_features[start:start + batch_size]
        features_text = "\n".join(
            f"- {f.get('name','')}（{f.get('module','')}）: {f.get('description','')[:60]}"
            for f in batch
        )
        prompt = (
            f"为以下功能生成开发任务清单。输出 JSON 数组，每个元素：\n"
            f'{{"task_id":"T-001","feature":"功能名","task":"任务描述",'
            f'"assignee":"负责角色(前端/后端/嵌入式/算法/测试/设计)",'
            f'"effort_days":"预估工时(天)","dependency":"前置依赖",'
            f'"sprint":"建议迭代(Sprint1-MVP/Sprint2-增强/Sprint3-优化)",'
            f'"priority":"P0-P3","note":"备注"}}\n\n'
            f"工时规则：简单UI 0.5-1天，标准功能 1-3天，复杂算法 3-5天，跨端联调 2-3天。\n"
            f"每个L2拆 1-3 个任务。\n"
            f"功能列表：\n{features_text}\n\n只输出 JSON。"
        )
        result = gateway.call_azure_openai("cpo", prompt, "只输出JSON。", "structured_doc")
        if result.get("success"):
            import re, json
            match = re.search(r'\[[\s\S]*\]', result["response"])
            if match:
                try:
                    tasks = json.loads(match.group())
                    for idx, t in enumerate(tasks):
                        t["task_id"] = f"T-{start + idx + 1:04d}"
                    all_tasks.extend(tasks)
                except: pass
    
    print(f"[DevTask] 生成 {len(all_tasks)} 条")
    return all_tasks
```

### 10.5 主流程中并行生成所有额外 Sheet

在 is_full_spec 分支中，替换原有 Sheet 3-7 的生成为：

```python
    if is_full_spec:
        print("[FastTrack] 完整规格书：并行生成所有额外 Sheet")
        send_reply(reply_target, "📋 功能清单完成，生成状态对策/语音/按键/灯效/导航场景/用户故事/测试用例/页面映射/开发任务...", reply_type)
        
        extra_sheets = {}
        
        # 批次 1：不依赖功能清单的 4 个 Sheet（4 路并行）
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
        
        # 批次 2：依赖功能清单的 4 个 Sheet（4 路并行）
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
        
        # 批次 3：开发任务
        try:
            dev_tasks = _gen_dev_tasks(all_items, _gw)
            extra_sheets["dev_tasks"] = dev_tasks
            print(f"  ✅ dev_tasks: {len(dev_tasks)} 条")
        except Exception as e:
            print(f"  ❌ dev_tasks: {e}")
        
        total_extra = sum(len(v) for v in extra_sheets.values())
        print(f"[FastTrack] 额外 Sheet 完成: {total_extra} 条")
```

### 10.6 Excel 导出新增 Sheet

在 `_export_to_excel` 中追加（注意函数签名新增 `audit_issues=None`）：

```python
def _export_to_excel(items, task_id, task_goal="", extra_sheets=None, audit_issues=None):
    # ... 原有 Sheet 1-7 写入 ...
    
    # Sheet 8: 用户故事
    if extra_sheets and extra_sheets.get("user_stories"):
        ws = wb.create_sheet("用户故事")
        _write_generic_sheet(ws, extra_sheets["user_stories"],
            ["功能名", "用户角色", "用户故事", "验收条件", "优先级"],
            ["feature", "role", "story", "acceptance", "priority"],
            [24, 14, 50, 36, 8])
    
    # Sheet 9: 测试用例
    if extra_sheets and extra_sheets.get("test_cases"):
        ws = wb.create_sheet("测试用例")
        _write_generic_sheet(ws, extra_sheets["test_cases"],
            ["用例ID", "功能名", "用例标题", "前置条件", "操作步骤", "预期结果", "优先级"],
            ["case_id", "feature", "title", "precondition", "steps", "expected", "priority"],
            [12, 20, 24, 24, 36, 30, 8])
    
    # Sheet 10: 页面映射表
    if extra_sheets and extra_sheets.get("page_mapping"):
        ws = wb.create_sheet("页面映射表")
        _write_generic_sheet(ws, extra_sheets["page_mapping"],
            ["页面名", "父页面", "平台", "包含功能", "入口方式", "优先级", "备注"],
            ["page", "parent", "platform", "features", "entry", "priority", "note"],
            [20, 16, 10, 40, 16, 8, 20])
    
    # Sheet 11: 开发任务
    if extra_sheets and extra_sheets.get("dev_tasks"):
        ws = wb.create_sheet("开发任务")
        _write_generic_sheet(ws, extra_sheets["dev_tasks"],
            ["任务ID", "功能名", "任务描述", "负责角色", "工时(天)", "前置依赖", "建议迭代", "优先级", "备注"],
            ["task_id", "feature", "task", "assignee", "effort_days", "dependency", "sprint", "priority", "note"],
            [10, 20, 30, 14, 10, 20, 16, 8, 16])
    
    # Sheet 12: 版本信息
    from openpyxl.styles import Font
    ws_ver = wb.create_sheet("版本信息")
    ver_data = [
        ["项目", "智能骑行头盔 V1"],
        ["版本", datetime.now().strftime("v%Y%m%d.%H%M")],
        ["生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ["功能总数", len(items)],
        ["HUD端功能", len([i for i in items if not i.get("module","").startswith("App-")])],
        ["App端功能", len([i for i in items if i.get("module","").startswith("App-")])],
        ["P0", sum(1 for i in items if i.get("priority")=="P0")],
        ["P1", sum(1 for i in items if i.get("priority")=="P1")],
        ["P2", sum(1 for i in items if i.get("priority")=="P2")],
        ["P3", sum(1 for i in items if i.get("priority")=="P3")],
        ["状态场景", len(extra_sheets.get("state",[])) if extra_sheets else 0],
        ["语音指令", len(extra_sheets.get("voice",[])) if extra_sheets else 0],
        ["按键映射", len(extra_sheets.get("button",[])) if extra_sheets else 0],
        ["灯效定义", len(extra_sheets.get("light",[])) if extra_sheets else 0],
        ["导航场景", len(extra_sheets.get("voice_nav",[])) if extra_sheets else 0],
        ["用户故事", len(extra_sheets.get("user_stories",[])) if extra_sheets else 0],
        ["测试用例", len(extra_sheets.get("test_cases",[])) if extra_sheets else 0],
        ["页面映射", len(extra_sheets.get("page_mapping",[])) if extra_sheets else 0],
        ["开发任务", len(extra_sheets.get("dev_tasks",[])) if extra_sheets else 0],
    ]
    for row_idx, row_data in enumerate(ver_data, 1):
        for col_idx, val in enumerate(row_data, 1):
            cell = ws_ver.cell(row=row_idx, column=col_idx, value=val)
            if col_idx == 1:
                cell.font = Font(bold=True)
    ws_ver.column_dimensions['A'].width = 16
    ws_ver.column_dimensions['B'].width = 30
    
    # Sheet 13: 一致性审计（如果有）
    if audit_issues:
        ws_audit = wb.create_sheet("一致性审计")
        _write_generic_sheet(ws_audit, audit_issues,
            ["问题类型", "问题描述", "关联模块"],
            ["type", "issue", "module"],
            [16, 60, 16])
    
    # 版本快照保存
    try:
        versions_dir = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "prd_versions"
        versions_dir.mkdir(parents=True, exist_ok=True)
        import json as _json
        snapshot = {
            "version": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "timestamp": datetime.now().isoformat(),
            "total_features": len(items),
            "items": items,
        }
        snap_path = versions_dir / f"prd_v_{snapshot['version']}.json"
        snap_path.write_text(_json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[Version] 快照已保存: {snapshot['version']}")
    except Exception as e:
        print(f"[Version] 快照保存失败: {e}")
```

---

## 改动 11：交互式 HTML 新增 Tab

在 `_generate_interactive_prd_html` 的 JS 中更新 TAB_CONFIG 和 buildTableView：

TAB_CONFIG:
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

buildTableView 追加：
```javascript
    } else if (id === 'voice_nav') {
        data = DATA.voice_nav || [];
        headers = ['场景','触发','用户输入','AI动作','HUD显示','语音播报','灯光反馈','异常兜底','优先级','备注'];
        keys = ['scene','trigger','user_input','ai_action','hud_display','voice_output','light_effect','fallback','priority','note'];
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

Tab 数量计算追加：
```javascript
    if (tab.id === 'user_stories') count = (DATA.user_stories || []).length;
    else if (tab.id === 'test_cases') count = (DATA.test_cases || []).length;
    else if (tab.id === 'page_mapping') count = (DATA.page_mapping || []).length;
    else if (tab.id === 'dev_tasks') count = (DATA.dev_tasks || []).length;
```

关键词检测更新：
```python
    is_full_spec = any(kw in text for kw in [
        "规格书", "状态场景", "语音指令", "按键映射", "灯效",
        "完整PRD", "导航场景", "用户故事", "测试用例", "页面映射",
        "开发任务", "全部Sheet"
    ])
```

---

## 改动 12：HTML 排版修复（7 个问题）

### 12.1 L2 div 未闭合

替换 buildTreeView 函数（完整版见上面改动中的代码，关键改动是 L2 和 L1 结束时都要关闭 div）：

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

### 12.2 L3 flex 布局加宽度约束

```css
.l3 { margin-left: 24px; padding: 6px 0; font-size: 13px; color: #555; 
    border-bottom: 1px solid #f0f0f0; display: flex; gap: 12px; align-items: flex-start; }
.l3 .name { min-width: 160px; max-width: 220px; flex-shrink: 0; font-weight: 500; color: #333; }
.l3 .desc { flex: 1; min-width: 200px; color: #666; }
.l3 .acc { flex: 1; min-width: 200px; color: #4a9; font-size: 12px; }
```

### 12.3 tabs sticky + th 高度

```css
.tabs { display: flex; background: #1a3a6c; padding: 0 30px; 
    position: sticky; top: 80px; z-index: 99; }
th { background: #2F5496; color: #fff; padding: 10px 12px; text-align: left; font-size: 13px; 
    position: sticky; top: 125px; z-index: 50; }
.content { padding: 20px 30px; max-width: 1600px; margin: 0 auto; }
```

### 12.4 响应式适配

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

### 12.5 筛选精确匹配

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

### 12.6 Tab 切换回顶部

```javascript
function switchTab(id) {
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.target === id));
    document.querySelectorAll('.section').forEach(s => s.classList.toggle('active', s.id === 'section-' + id));
    window.scrollTo(0, 0);
}
```

### 12.7 默认展开第一个 L1

```javascript
buildTabs();
const firstBody = document.querySelector('.l1-body');
if (firstBody) firstBody.classList.add('open');
```

---

## 改动 13：主流程调用顺序

确认主流程中的调用顺序为：

```python
    # 1. 智能增量检测（改动 7）
    # 2. 并行生成功能清单（原有 + 改动 5 知识库注入）
    # 3. 失败模块指数退避重试（改动 6）
    # 4. 模块名统一 + 去重（改动 4）
    # 5. 全局优先级校准（改动 8）
    _calibrate_priorities(all_items)
    # 6. 并行生成额外 Sheet（改动 10）
    # 7. 跨模块一致性审计（改动 9）
    audit_issues = _cross_module_audit(all_items, extra_sheets if extra_sheets else {})
    # 8. 生成功能 ID（原有）
    _generate_ids(all_items)
    # 9. 导出 Excel（改动 10.6，含新 Sheet + 审计 + 版本快照）
    xlsx_path = _export_to_excel(all_items, task_id, text[:50], extra_sheets=extra_sheets, audit_issues=audit_issues)
    # 10. 发送文件 + 脑图 + 交互式 HTML（原有）
```

---

## 验证

```bash
python -c "
from scripts.feishu_handlers.structured_doc import (
    _gen_one, _gen_one_with_gemini,
    _gen_sheet3_state_scenarios, _gen_sheet4_voice_commands,
    _gen_sheet5_button_mapping, _gen_sheet6_light_effects,
    _gen_sheet7_voice_nav_scenarios,
    _gen_user_stories, _gen_test_cases, _gen_page_mapping, _gen_dev_tasks,
    _cross_module_audit, _calibrate_priorities,
    _export_to_excel, _generate_mindmap_mm, _generate_mindmap_svg,
    _generate_interactive_prd_html, try_structured_doc_fast_track
)
print('所有函数存在 OK')
"
```
