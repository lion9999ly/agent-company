# PRD 交付质量全面进化 — 失败诊断 + 智能迭代 + HTML 修复 + XMind

> 全部改 scripts/feishu_handlers/structured_doc.py（除脑图外）
> 8 个改动，按依赖顺序执行

---

## 改动 1：_gen_one 加详细错误日志（定位失败根因）

在 _gen_one 函数中，LLM 调用处加完整错误捕获和日志：

```python
def _gen_one(feature):
    name = feature["name"]
    module = feature["module"]
    
    # ... 知识库注入逻辑（改动 2 会修改）...
    
    try:
        result = _gw.call_azure_openai("cpo", batch_prompt,
            "只输出JSON数组。", "structured_doc")
        
        if not result.get("success"):
            error_msg = result.get("error", "未知错误")
            print(f"  [GenOne] {name} LLM 返回失败: {error_msg}")
            print(f"  [GenOne] {name} prompt 长度: {len(batch_prompt)} 字")
            return []
        
        response = result.get("response", "")
        if len(response) < 50:
            print(f"  [GenOne] {name} 响应太短: {len(response)} 字")
            return []
        
        import re as _re, json as _json
        json_match = _re.search(r'\[[\s\S]*\]', response)
        if not json_match:
            print(f"  [GenOne] {name} 无法提取 JSON，响应前200字: {response[:200]}")
            return []
        
        try:
            items = _json.loads(json_match.group())
            return items
        except _json.JSONDecodeError as je:
            print(f"  [GenOne] {name} JSON 解析失败: {je}")
            print(f"  [GenOne] {name} JSON 片段: {json_match.group()[:300]}")
            return []
            
    except Exception as e:
        print(f"  [GenOne] {name} 异常: {type(e).__name__}: {e}")
        print(f"  [GenOne] {name} prompt 长度: {len(batch_prompt)} 字")
        import traceback
        traceback.print_exc()
        return []
```

对 _gen_one_with_gemini 做同样改造。

---

## 改动 2：知识库注入从"灌全文"改为"提取数据点"

当前 _gen_one 把知识库搜索结果全文灌进 prompt（3000-5000 字）。
改为：先用 LLM 从知识库全文中提取关键数据点（~200 字），再注入 prompt。

但这样会多一次 LLM 调用，太慢。所以改用**正则提取**，不走 LLM：

```python
def _extract_data_points(kb_text: str, max_points: int = 15) -> str:
    """从知识库全文中提取关键数据点（纯正则，不走 LLM）"""
    import re
    
    points = set()
    
    # 提取含数字+单位的句子片段
    num_patterns = re.findall(
        r'[^。\n]{0,40}?\d+\.?\d*\s*(?:mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|USD|\$|%|nits|lux|fps|°|μm|TOPS|nm|GHz|MHz|MB|GB|TB|ms|秒|分钟|小时|天|个月|台|件|条|款|代|层|路|位|倍|次)[^。\n]{0,20}',
        kb_text
    )
    for match in num_patterns[:20]:
        clean = match.strip().strip('，,、；;：:')
        if len(clean) > 10:
            points.add(clean)
    
    # 提取含型号的句子片段
    model_patterns = re.findall(
        r'[^。\n]{0,30}?(?:[A-Z]{2,}\d{2,}|IMX\d+|QCC\d+|BES\d+|nRF\d+|AR[12]\s*Gen|BMI\d+|ICM-\d+|STM32|ESP32|MT\d{4}|BCM\d+|CS\d{4}|WM\d{4})[^。\n]{0,30}',
        kb_text
    )
    for match in model_patterns[:10]:
        clean = match.strip().strip('，,、；;：:')
        if len(clean) > 8:
            points.add(clean)
    
    # 提取含品牌名的句子片段
    brand_patterns = re.findall(
        r'[^。\n]{0,20}?(?:歌尔|立讯|舜宇|索尼|高通|联发科|博世|Qualcomm|Sony|Bosch|Nordic|Himax|JBD|Sena|Cardo|Forcite|LIVALL|EyeRide|CrossHelmet|GoPro|Insta360|TÜV|DEKRA|SGS)[^。\n]{0,30}',
        kb_text
    )
    for match in brand_patterns[:10]:
        clean = match.strip().strip('，,、；;：:')
        if len(clean) > 8:
            points.add(clean)
    
    # 提取含认证标准的
    cert_patterns = re.findall(
        r'[^。\n]{0,20}?(?:ECE\s*22\.0[56]|DOT\s*FMVSS|GB\s*811|FCC|CE|IP\d{2}|MIL-STD|Qi|BQB|SRRC)[^。\n]{0,30}',
        kb_text
    )
    for match in cert_patterns[:5]:
        clean = match.strip().strip('，,、；;：:')
        if len(clean) > 8:
            points.add(clean)
    
    # 去重并截断
    result = list(points)[:max_points]
    
    if not result:
        return ""
    
    return "关键数据点：\n" + "\n".join(f"- {p}" for p in result)
```

在 _gen_one 中替换知识库注入方式：

```python
    # === 知识库注入：提取数据点模式 ===
    from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt
    
    kb_queries = [
        f"{name} 技术参数 方案",
        f"{name} 竞品",
        f"{name} 认证 标准",
    ]
    
    CORE_MODULES = {"导航", "主动安全预警提示", "AI语音助手", "Ai语音助手",
                    "组队", "摄像状态", "胎温胎压", "设备状态"}
    
    if name in CORE_MODULES:
        kb_queries.extend([f"{name} 用户需求", f"{name} 功耗 续航"])
    
    kb_raw = ""
    for q in kb_queries:
        try:
            entries = search_knowledge(q, limit=3)
            if entries:
                kb_raw += format_knowledge_for_prompt(entries)[:2000] + "\n"
        except:
            pass
    
    # 从全文提取数据点（~200字），不灌全文（~3000字）
    kb_data_points = _extract_data_points(kb_raw)
    
    kb_inject = ""
    if kb_data_points:
        kb_inject = (
            f"\n\n## 项目知识库数据（验收标准必须参考这些真实数据）\n"
            f"{kb_data_points}\n"
            f"基于以上数据填写验收标准。知识库无相关数据的标注[待验证]。\n"
        )
    
    print(f"  [KB] {name}: 知识库原文 {len(kb_raw)} 字 → 数据点 {len(kb_data_points)} 字")
```

效果：prompt 从 +3000 字降到 +200 字，超时风险大幅降低，数据更精准。

---

## 改动 3：智能增量迭代 — 逐模块对比取优

替换改动 7 的增量逻辑。核心思想：**以上一版为基线，每个模块都尝试改进，最终逐模块取两版中更好的那个。**

```python
    # === 智能增量迭代 ===
    import json as _json
    
    versions_dir = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "prd_versions"
    prev_items = []
    prev_by_module = {}  # {module_name: [items]}
    
    if versions_dir.exists():
        latest_files = sorted(versions_dir.glob("prd_v_*.json"), reverse=True)
        if latest_files:
            prev = _json.loads(latest_files[0].read_text(encoding="utf-8"))
            prev_items = prev.get("items", [])
            prev_version = prev.get("version", "")
            
            # 按 L1 模块分组上一版数据
            current_l1 = ""
            for item in prev_items:
                if item.get("level") == "L1":
                    current_l1 = item.get("name", "")
                if current_l1:
                    if current_l1 not in prev_by_module:
                        prev_by_module[current_l1] = []
                    prev_by_module[current_l1].append(item)
            
            print(f"[SmartIterate] 上一版: {prev_version} ({len(prev_items)} 条, {len(prev_by_module)} 模块)")
    
    # === 全量生成（每个模块都尝试改进）===
    # 不跳过任何模块——全部重新生成，但生成完后和上一版对比取优
    # ... 原有的并行生成逻辑（所有 l1_features 都生成）...
    
    # === 逐模块对比取优 ===
    if prev_by_module:
        print(f"\n[Compare] 逐模块对比取优...")
        
        # 按 L1 分组新版数据
        new_by_module = {}
        current_l1 = ""
        for item in all_items:
            if item.get("level") == "L1":
                current_l1 = item.get("name", "")
            if current_l1:
                if current_l1 not in new_by_module:
                    new_by_module[current_l1] = []
                new_by_module[current_l1].append(item)
        
        # 逐模块对比
        final_items = []
        all_module_names = set(list(prev_by_module.keys()) + list(new_by_module.keys()))
        
        for mod_name in all_module_names:
            old = prev_by_module.get(mod_name, [])
            new = new_by_module.get(mod_name, [])
            
            old_score = _score_module(old)
            new_score = _score_module(new)
            
            if new_score >= old_score:
                final_items.extend(new)
                if old:
                    print(f"  ✅ {mod_name}: 新版更好 ({old_score}→{new_score})")
                else:
                    print(f"  🆕 {mod_name}: 新增模块 (score={new_score})")
            else:
                final_items.extend(old)
                print(f"  ⏪ {mod_name}: 保留上一版 (新{new_score} < 旧{old_score})")
        
        all_items = final_items
        print(f"[Compare] 最终: {len(all_items)} 条")


def _score_module(items: list) -> int:
    """给一个模块的内容打分，用于对比两版取优"""
    if not items:
        return 0
    
    score = 0
    
    # 条目数量（有内容的，不算空壳）
    l1_count = sum(1 for i in items if i.get("level") == "L1")
    l2_count = sum(1 for i in items if i.get("level") == "L2")
    l3_count = sum(1 for i in items if i.get("level") == "L3")
    
    # 空壳检测：L1 存在但 L2 为 0
    if l1_count > 0 and l2_count == 0:
        return 1  # 空壳，最低分
    
    # 基础分：有内容就给分
    score += l2_count * 3 + l3_count * 1
    
    # 验收标准质量
    has_data = 0
    has_pending = 0
    has_empty = 0
    for item in items:
        acc = item.get("acceptance", "")
        if not acc or acc == "[待生成]":
            has_empty += 1
        elif "[待验证]" in acc:
            has_pending += 1
        elif any(c.isdigit() for c in acc):
            has_data += 1  # 有具体数字
    
    score += has_data * 2  # 有数字的验收标准加分
    score -= has_empty * 5  # 空的严重扣分
    score -= has_pending * 1  # 待验证轻微扣分
    
    # 描述完整性
    has_desc = sum(1 for i in items if len(i.get("description", "")) > 10)
    score += has_desc * 1
    
    return max(score, 0)
```

---

## 改动 4：重试策略改进（加裸跑但不降智）

指数退避 3 次失败后，不是标[待生成]就放弃，而是**用更短的 prompt 再试一次**。
注意：不是"去掉知识库"（那是降智），而是"用数据点模式的最短 prompt"——知识库数据点仍然在，只是 prompt 更精简。

```python
    if failed_features:
        print(f"[FastTrack] {len(failed_features)} 个模块失败，指数退避重试...")
        import time as _time
        
        for feature in failed_features:
            success = False
            
            # 阶段 1：指数退避重试 Azure（3 次）
            for attempt in range(3):
                wait = [5, 15, 30][attempt]
                print(f"  [重试 {attempt+1}/3] {feature['name']}（Azure，等{wait}秒）")
                _time.sleep(wait)
                try:
                    batch = _gen_one(feature)
                    if batch and len(batch) > 1:
                        all_items.extend(batch)
                        print(f"  ✅ [重试成功] {feature['name']}: +{len(batch)} 条")
                        success = True
                        break
                except Exception as e:
                    print(f"  ❌ [重试 {attempt+1}] {feature['name']}: {e}")
            
            # 阶段 2：Gemini 降级（1 次）
            if not success:
                print(f"  [降级] {feature['name']}: 切换 Gemini...")
                _time.sleep(5)
                try:
                    batch = _gen_one_with_gemini(feature)
                    if batch and len(batch) > 1:
                        all_items.extend(batch)
                        print(f"  ✅ [Gemini成功] {feature['name']}: +{len(batch)} 条")
                        success = True
                except Exception as e:
                    print(f"  ❌ [Gemini失败] {feature['name']}: {e}")
            
            # 阶段 3：精简 prompt 最后一搏（知识库数据点仍保留，但 prompt 模板极简）
            if not success:
                print(f"  [精简] {feature['name']}: 最短 prompt 最后一搏...")
                _time.sleep(5)
                try:
                    batch = _gen_one_minimal(feature)
                    if batch and len(batch) > 1:
                        all_items.extend(batch)
                        # 标注为精简生成
                        for item in batch:
                            item["note"] = (item.get("note", "") + " [精简生成,可进一步优化]").strip()
                        print(f"  ✅ [精简成功] {feature['name']}: +{len(batch)} 条")
                        success = True
                except Exception as e:
                    print(f"  ❌ [精简失败] {feature['name']}: {e}")
            
            if not success:
                # 真正全部失败：如果上一版有这个模块，保留上一版
                if feature["name"] in prev_by_module:
                    all_items.extend(prev_by_module[feature["name"]])
                    print(f"  ⏪ [兜底] {feature['name']}: 保留上一版 ({len(prev_by_module[feature['name']])} 条)")
                else:
                    all_items.append({
                        "module": feature["module"], "level": "L1", "parent": "",
                        "name": feature["name"], "priority": "P0", "interaction": "",
                        "description": "[待生成] 5 次尝试全部失败",
                        "acceptance": "[待生成]", "dependencies": "", "note": "生成失败"
                    })
                    print(f"  ⚠️ [放弃] {feature['name']}: 标记[待生成]")


def _gen_one_minimal(feature):
    """精简模式：最短 prompt，但仍包含知识库数据点"""
    name = feature["name"]
    module = feature["module"]
    
    # 仍然搜知识库，但只取数据点
    from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt
    kb_raw = ""
    try:
        entries = search_knowledge(name, limit=3)
        if entries:
            kb_raw = format_knowledge_for_prompt(entries)[:1500]
    except:
        pass
    
    data_points = _extract_data_points(kb_raw)
    kb_line = f"\n参考数据：{data_points}\n" if data_points else ""
    
    prompt = (
        f"生成「{name}」功能清单。模块：{module}。{kb_line}"
        f"输出JSON数组：module/level(L1,L2,L3)/parent/name/priority/interaction/description/acceptance/dependencies/note。"
        f"至少3个L2每个2个L3。只输出JSON。"
    )
    
    import re as _re, json as _json
    result = _gw.call_azure_openai("cpo", prompt, "只输出JSON。", "structured_doc")
    
    if result.get("success"):
        match = _re.search(r'\[[\s\S]*\]', result["response"])
        if match:
            try:
                return _json.loads(match.group())
            except:
                pass
    return []
```

---

## 改动 5：空壳 L1 自动检测与补救

在去重之后、对比取优之前，检测空壳并自动补救：

```python
    # === 空壳 L1 检测与补救 ===
    l1_child_count = {}  # {l1_name: child_count}
    current_l1 = ""
    for item in all_items:
        if item.get("level") == "L1":
            current_l1 = item.get("name", "")
            if current_l1 not in l1_child_count:
                l1_child_count[current_l1] = 0
        elif item.get("level") in ("L2", "L3") and current_l1:
            l1_child_count[current_l1] = l1_child_count.get(current_l1, 0) + 1
    
    empty_l1s = [name for name, count in l1_child_count.items() if count == 0]
    
    if empty_l1s:
        print(f"\n[QA] 发现 {len(empty_l1s)} 个空壳 L1: {empty_l1s}")
        
        for l1_name in empty_l1s:
            feature = next((f for f in l1_features if f["name"] == l1_name), None)
            if not feature:
                continue
            
            # 先检查上一版有没有
            if l1_name in prev_by_module and len(prev_by_module[l1_name]) > 1:
                # 上一版有内容，直接用上一版
                all_items = [i for i in all_items if not (i.get("level") == "L1" and i.get("name") == l1_name)]
                all_items.extend(prev_by_module[l1_name])
                print(f"  ⏪ [空壳补救] {l1_name}: 用上一版 ({len(prev_by_module[l1_name])} 条)")
            else:
                # 上一版也没有，用精简模式生成
                print(f"  [空壳补救] {l1_name}: 精简模式生成...")
                batch = _gen_one_minimal(feature)
                if batch and len(batch) > 1:
                    all_items = [i for i in all_items if not (i.get("level") == "L1" and i.get("name") == l1_name)]
                    all_items.extend(batch)
                    print(f"  ✅ [空壳补救] {l1_name}: +{len(batch)} 条")
                else:
                    print(f"  ❌ [空壳补救] {l1_name}: 仍然失败")
```

---

## 改动 6：一致性审计收紧

替换 _cross_module_audit 中的语音不一致检测逻辑：

```python
    # 只检查名称或描述明确包含"语音控制/语音指令/语音操作"的 L2
    voice_commands = extra_sheets.get("voice", [])
    voice_texts = " ".join(str(vc) for vc in voice_commands).lower()
    
    for item in all_items:
        name = item.get("name", "")
        desc = item.get("description", "")
        
        is_voice_control = any(kw in name + desc for kw in 
            ["语音控制", "语音指令", "语音操作", "语音发起", "语音查询", "语音切换"])
        
        if is_voice_control and item.get("level") == "L2":
            has_match = any(
                name[:4].lower() in str(vc).lower()
                for vc in voice_commands
            )
            if not has_match:
                issues.append({
                    "type": "功能-语音不一致",
                    "issue": f"「{name}」含语音控制功能，但语音指令表无对应",
                    "module": item.get("module", "")
                })
```

---

## 改动 7：脑图改 .xmind 格式

.xmind 是 ZIP 包，内含 content.json + metadata.json。

替换 _generate_mindmap_mm 为 _generate_mindmap_xmind：

```python
def _generate_mindmap_xmind(items, title="智能骑行头盔 V1 功能框架"):
    """生成 .xmind 格式脑图（ZIP 包含 content.json + metadata.json）"""
    import json as _json
    import zipfile
    import uuid
    from io import BytesIO
    
    HUD_MODULES = {"导航", "来电", "音乐", "消息", "AI语音助手", "Ai语音助手",
        "简易", "简易路线", "路线", "主动安全预警提示", "组队", "摄像状态",
        "胎温胎压", "开机动画", "速度", "设备状态", "显示队友位置", "头盔HUD",
        "实体按键交互", "氛围灯交互", "AI功能", "语音交互", "视觉交互", "多模态交互"}
    APP_MODULES = {"App-设备", "App-社区", "App-商城", "App-我的"}
    
    # 构建树结构
    groups = {
        "HUD及头盔端": [],
        "App端": [],
        "系统与交互": [],
    }
    
    current_l1_node = None
    current_l2_node = None
    
    for item in items:
        level = item.get("level", "")
        name = item.get("name", "")
        module = item.get("module", "")
        priority = item.get("priority", "")
        
        if module in HUD_MODULES:
            group = "HUD及头盔端"
        elif module in APP_MODULES:
            group = "App端"
        else:
            group = "系统与交互"
        
        label_text = f"{name} [{priority}]" if priority else name
        node = {"id": str(uuid.uuid4()), "title": label_text, "children": {"attached": []}}
        
        if level == "L1":
            groups[group].append(node)
            current_l1_node = node
            current_l2_node = None
        elif level == "L2" and current_l1_node:
            current_l1_node["children"]["attached"].append(node)
            current_l2_node = node
        elif level == "L3" and current_l2_node:
            current_l2_node["children"]["attached"].append(node)
    
    # 构建 xmind content.json
    root_node = {
        "id": str(uuid.uuid4()),
        "class": "topic",
        "title": title,
        "children": {"attached": []}
    }
    
    for group_name, group_items in groups.items():
        if group_items:
            group_node = {
                "id": str(uuid.uuid4()),
                "title": group_name,
                "children": {"attached": group_items}
            }
            root_node["children"]["attached"].append(group_node)
    
    content = [{
        "id": str(uuid.uuid4()),
        "class": "sheet",
        "title": title,
        "rootTopic": root_node,
        "topicPositioning": "fixed"
    }]
    
    metadata = {
        "creator": {"name": "Agent Company", "version": "1.0"},
        "activeSheetId": content[0]["id"]
    }
    
    # 打包为 ZIP
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.json", _json.dumps(content, ensure_ascii=False, indent=2))
        zf.writestr("metadata.json", _json.dumps(metadata, ensure_ascii=False, indent=2))
    
    return buf.getvalue()
```

主流程中生成 .xmind：

```python
    # 生成 .xmind 脑图
    try:
        xmind_data = _generate_mindmap_xmind(all_items, "智能骑行头盔 V1 功能框架")
        xmind_path = export_dir / f"mindmap_{task_id}.xmind"
        xmind_path.write_bytes(xmind_data)
        _send_file_to_feishu(reply_target, str(xmind_path), id_type)
        print(f"[FastTrack] 脑图 .xmind 已发送")
    except Exception as e:
        print(f"[FastTrack] .xmind 生成失败: {e}")
        import traceback
        traceback.print_exc()
```

同时保留 .mm 的生成作为备选（如果用户需要 FreeMind 格式）。

---

## 改动 8：HTML 排版修复（5 个问题）

### 8.1 脑图 HTML 改径向布局 + 消除空白

替换 _generate_mindmap_svg 函数中的 D3.js 代码。核心改动：

```javascript
// 径向布局
const width = 1200;
const height = 1200;
const radius = Math.min(width, height) / 2 - 100;

const tree = d3.tree()
    .size([2 * Math.PI, radius])
    .separation((a, b) => (a.parent === b.parent ? 1 : 2) / a.depth);

const svg = d3.select("body").append("svg")
    .attr("width", width).attr("height", height)
    .style("background", "#fff")
    .call(d3.zoom().scaleExtent([0.3, 5]).on("zoom", (e) => g.attr("transform", e.transform)));

const g = svg.append("g")
    .attr("transform", `translate(${width/2},${height/2})`);

// ... 节点和连线用径向坐标 ...

function radialPoint(d) {
    return [
        d.y * Math.cos(d.x - Math.PI / 2),
        d.y * Math.sin(d.x - Math.PI / 2)
    ];
}

// 初始渲染后自动 fit to content
setTimeout(() => {
    const bbox = g.node().getBBox();
    const padding = 50;
    const scale = Math.min(
        width / (bbox.width + padding * 2),
        height / (bbox.height + padding * 2)
    ) * 0.85;
    const cx = bbox.x + bbox.width / 2;
    const cy = bbox.y + bbox.height / 2;
    svg.transition().duration(500).call(
        d3.zoom().transform,
        d3.zoomIdentity
            .translate(width/2 - cx * scale, height/2 - cy * scale)
            .scale(scale)
    );
}, 200);
```

body CSS：`overflow: hidden;` 防止出现空白滚动条。

### 8.2 PRD HTML：表头 sticky 位置改 JS 动态计算

在 `_generate_interactive_prd_html` 的 JS 末尾加：

```javascript
function updateStickyPositions() {
    const headerH = document.querySelector('.header')?.offsetHeight || 0;
    const tabsH = document.querySelector('.tabs')?.offsetHeight || 0;
    const totalH = headerH + tabsH;
    
    const tabsEl = document.querySelector('.tabs');
    if (tabsEl) tabsEl.style.top = headerH + 'px';
    
    document.querySelectorAll('th').forEach(th => {
        th.style.top = totalH + 'px';
    });
}

buildTabs();
updateStickyPositions();
window.addEventListener('resize', updateStickyPositions);
```

CSS 中移除硬编码的 top 值：

```css
.tabs { display: flex; background: #1a3a6c; padding: 0 24px; 
    position: sticky; z-index: 99; }
th { background: #2F5496; color: #fff; padding: 10px 12px; text-align: left; font-size: 13px; 
    position: sticky; z-index: 50; }
```

### 8.3 标题栏始终可见

确保 sticky 父链上没有 overflow 破坏：

```css
html, body { margin: 0; padding: 0; overflow-y: auto; overflow-x: hidden; }
.header { background: #2F5496; color: #fff; padding: 12px 24px; 
    position: sticky; top: 0; z-index: 100; }
.section { display: none; }
.section.active { display: block; }
.content { padding: 16px 24px; max-width: 1600px; margin: 0 auto; }
```

### 8.4 L2 div 闭合 + L3 flex 布局 + 响应式

（和之前方案一致，不重复写。确认 buildTreeView 中 L2 关闭逻辑、.l3 的 min-width/max-width、@media 查询都已加入。）

### 8.5 Tab 切换回顶部 + 默认展开第一个 L1 + 筛选精确匹配

（和之前方案一致，确认 switchTab 加 scrollTo、buildTabs 后展开第一个 L1、filterAll 用 dataset.priority 精确匹配。）

---

## 改动顺序与验证

主流程调用顺序：

```python
    # 1. 并行生成功能清单（改动 2 知识库数据点注入 + 改动 1 错误日志）
    # 2. 失败模块重试（改动 4：Azure退避→Gemini→精简→保留上一版）
    # 3. 去重 + 模块名统一
    # 4. 空壳 L1 检测与补救（改动 5）
    # 5. 逐模块对比取优（改动 3）
    # 6. 优先级校准
    # 7. 并行生成额外 Sheet
    # 8. 一致性审计（改动 6）
    # 9. 生成 ID
    # 10. 导出 Excel + .xmind + HTML
```

验证：

```bash
# 所有新函数存在
python -c "
from scripts.feishu_handlers.structured_doc import (
    _extract_data_points, _gen_one_minimal, _score_module,
    _generate_mindmap_xmind, _cross_module_audit,
    try_structured_doc_fast_track
)
print('OK')
"

# 数据点提取测试
python -c "
from scripts.feishu_handlers.structured_doc import _extract_data_points
text = 'AR1 Gen2 功耗 1.2W，支持 720p/60fps。ECE 22.06 要求电子附件质量不超过 50g。Forcite MK1S 电池 2600mAh 续航 6h。'
points = _extract_data_points(text)
print(points)
"

# 模块评分测试
python -c "
from scripts.feishu_handlers.structured_doc import _score_module
empty = [{'level':'L1','name':'导航','acceptance':''}]
good = [{'level':'L1','name':'导航','acceptance':'','description':'完整导航'},
        {'level':'L2','name':'路线规划','acceptance':'10秒内完成','description':'支持规划'},
        {'level':'L3','name':'搜索','acceptance':'3秒返回','description':'POI搜索'}]
print(f'空壳: {_score_module(empty)}')
print(f'有内容: {_score_module(good)}')
"

# 重启后测试 PRD
# 飞书发提示词，观察终端日志中：
# a. [KB] 每个模块显示"知识库原文 X 字 → 数据点 Y 字"
# b. [GenOne] 失败模块显示具体错误原因
# c. [Compare] 逐模块对比结果
# d. [QA] 空壳检测与补救结果
# e. 最终 Excel 中无空壳 L1
```
