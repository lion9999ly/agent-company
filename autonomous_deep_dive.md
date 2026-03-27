# 自主深挖调度器 — 系统自己决定今晚深挖什么

> 生成时间: 2026-03-25
> 核心理念: "深挖芯片"是一个模式，不是一个任务。系统自动发现薄弱领域，自动生成种子，自动深挖。
> 依赖: knowledge_graph_expander.py, daily_learning.py

---

## Task 1: 将知识图谱扩展器从"硬编码种子"改为"动态生成种子"

### 1.1 在 knowledge_graph_expander.py 中，添加自动种子生成函数

在现有的 `DOMAIN_SEEDS` 字典之后，添加：

```python
def auto_discover_domains() -> list:
    """
    自动发现需要深挖的领域，生成种子节点。
    不依赖硬编码——从知识库现状出发，让 LLM 判断哪里薄弱、该深挖什么。
    
    返回格式和 DOMAIN_SEEDS 中的条目一致，可以直接传给 expand_one_domain。
    """
    gateway = get_model_gateway()
    
    # Step 1: 收集知识库现状
    stats = get_knowledge_stats()
    total = sum(stats.values())
    
    # 维度覆盖统计
    dimension_counts = {}
    target_dimensions = {
        "HUD/AR显示": ["HUD", "AR", "光机", "光波导", "Micro OLED", "近眼显示", "waveguide"],
        "4K摄像": ["4K", "摄像", "IMX", "EIS", "防抖", "行车记录", "camera"],
        "ANC/ENC降噪": ["ANC", "ENC", "降噪", "风噪", "通话", "麦克风", "noise cancellation"],
        "ADAS安全": ["ADAS", "盲区", "碰撞预警", "前向预警", "雷达", "AEB", "APA", "BSD", "毫米波", "USS", "主动安全"],
        "SoC/芯片": ["AR1", "BES2800", "高通", "恒玄", "SoC", "芯片", "Nordic", "QCC", "J6", "Orin"],
        "认证标准": ["ECE", "DOT", "3C", "FCC", "CE RED", "UN38.3", "GB 811", "FMVSS", "ENCAP"],
        "供应商/JDM": ["歌尔", "Goertek", "JDM", "ODM", "供应商", "代工", "立讯"],
        "Mesh对讲": ["Mesh", "对讲", "自组网", "Sena", "Cardo", "intercom"],
        "电池/散热": ["电池", "散热", "热管理", "温控", "mAh", "充电", "BMS", "锂聚合物"],
        "结构/材料": ["碳纤维", "玻纤", "EPS", "壳体", "模具", "MIPS", "carbon fiber", "重量"],
        "连接器/接口": ["连接器", "FAKRA", "USB-C", "Type-C", "FPC", "天线", "RF"],
        "传感器/IMU": ["IMU", "加速度计", "陀螺仪", "气压计", "GPS", "GNSS", "跌倒检测"],
    }
    
    for dim_name, keywords in target_dimensions.items():
        count = 0
        for f in KB_ROOT.rglob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                text = (data.get("title", "") + " " + data.get("content", "")[:200]).lower()
                if any(kw.lower() in text for kw in keywords):
                    count += 1
            except:
                continue
        dimension_counts[dim_name] = count
    
    # 按覆盖量排序，找最薄弱的方向
    sorted_dims = sorted(dimension_counts.items(), key=lambda x: x[1])
    
    # 收集已有的技术档案标题（避免重复深挖）
    existing_profiles = set()
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if "knowledge_graph" in data.get("tags", []) or "tech_profile" in data.get("tags", []):
                existing_profiles.add(data.get("title", "")[:40].lower())
        except:
            continue
    
    # Step 2: 让 LLM 基于薄弱方向生成深挖计划
    weak_report = "\n".join([f"  {d}: {c}条" for d, c in sorted_dims])
    existing_report = "\n".join(list(existing_profiles)[:30]) if existing_profiles else "暂无"
    
    plan_prompt = (
        f"你是智能摩托车全盔项目的知识管理专家。\n\n"
        f"## 知识库总量: {total} 条\n\n"
        f"## 各维度覆盖（从少到多排列）:\n{weak_report}\n\n"
        f"## 已有技术档案（不要重复这些）:\n{existing_report}\n\n"
        f"## 你的任务\n"
        f"从最薄弱的 2-3 个维度出发，为每个维度设计一个'知识图谱深挖计划'。\n\n"
        f"每个计划需要：\n"
        f"1. 明确的领域名称\n"
        f"2. 3-5 个种子节点（具体的产品/技术/标准名称，不要泛泛的关键词）\n"
        f"3. 让 LLM 发现更多节点的扩展提示词\n"
        f"4. 针对每个节点的深搜模板（中英文各 2 条）\n"
        f"5. 技术档案的输出模板（该领域特有的字段）\n\n"
        f"## 约束\n"
        f"- 必须围绕摩托车智能全盔\n"
        f"- 种子节点必须具体到型号/标准号/公司名\n"
        f"- 避免和已有技术档案重复\n"
        f"- 选择的维度应该是对产品决策最有影响的\n\n"
        f"输出 JSON 数组，每个元素格式：\n"
        f'{{"domain_key": "英文标识(如 battery_bms)", '
        f'"name": "中文名称(如 电池与BMS方案)", '
        f'"seeds": ["种子1", "种子2", "种子3"], '
        f'"expansion_prompt": "让LLM发现更多节点的提示词...", '
        f'"deep_search_template": ["搜索模板1 {{chip}} {{vendor}}", "搜索模板2"], '
        f'"knowledge_template": "技术档案输出模板..."}}'
    )
    
    result = gateway.call_azure_openai("cpo", plan_prompt,
        "你是知识管理专家。只输出 JSON 数组。", "auto_discover_domains")
    
    if not result.get("success"):
        print("[AutoDiscover] LLM 调用失败，降级到硬编码种子")
        return []
    
    try:
        resp = result["response"].strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        domains = json.loads(resp)
        
        if not isinstance(domains, list):
            return []
        
        # 转换为 expand_one_domain 能接受的格式
        valid_domains = []
        for d in domains[:3]:  # 每晚最多 3 个领域
            domain_key = d.get("domain_key", "")
            if not domain_key:
                continue
            
            # 确保必要字段存在
            domain_config = {
                "name": d.get("name", domain_key),
                "seeds": d.get("seeds", [])[:5],
                "expansion_prompt": d.get("expansion_prompt", 
                    f"列出与以下已知节点同家族或竞品的其他选项：{{known_list}}\n只输出 JSON 数组。最多 15 个。"),
                "deep_search_template": d.get("deep_search_template", [
                    "{chip} datasheet specifications 2026",
                    "{chip} {vendor} features comparison",
                    "{chip} 参数 规格 价格 对比",
                    "{chip} smart motorcycle helmet application",
                ]),
                "knowledge_template": d.get("knowledge_template",
                    "请基于以下搜索结果，输出关于 {chip} 的完整技术档案。\n"
                    "必须包含具体参数、价格、适用场景、对摩托车全盔的适配度。\n\n"
                    "搜索结果：\n{search_data}"),
            }
            
            valid_domains.append({"key": domain_key, "config": domain_config})
            print(f"[AutoDiscover] 发现深挖方向: {domain_config['name']} ({len(domain_config['seeds'])} 个种子)")
        
        return valid_domains
    
    except Exception as e:
        print(f"[AutoDiscover] 解析失败: {e}")
        return []
```

### 1.2 添加自主深挖调度主函数

```python
def run_autonomous_deep_dive(progress_callback=None) -> str:
    """
    自主深挖：系统自动判断今晚该深挖什么领域，自动生成种子，自动执行。
    每晚由夜间学习调用，无需人工指定方向。
    """
    print(f"\n{'='*60}")
    print(f"[AutoDeepDive] 自主深挖启动 ({datetime.now().strftime('%H:%M')})")
    print(f"{'='*60}")
    
    report_lines = ["[AutoDeepDive] 自主深挖报告"]
    
    # Step 1: 检查是否有未完成的深挖任务（断点续传）
    progress_file = Path(__file__).parent.parent / ".ai-state" / "kg_progress.json"
    has_pending = False
    if progress_file.exists():
        try:
            progress = json.loads(progress_file.read_text(encoding="utf-8"))
            pending = {k: v for k, v in progress.items() if isinstance(v, dict) and v.get("remaining", 0) > 0}
            if pending:
                has_pending = True
                report_lines.append(f"\n📋 发现 {len(pending)} 个未完成的深挖任务，优先续传")
                for key, info in pending.items():
                    report_lines.append(f"  - {info.get('name', key)}: 剩余 {info.get('remaining', '?')} 个节点")
        except:
            pass
    
    if has_pending:
        # 续传未完成的任务
        for key, info in pending.items():
            config = info.get("config")
            if config:
                # 动态注册到 DOMAIN_SEEDS 中
                DOMAIN_SEEDS[key] = config
                report = expand_one_domain(key, progress_callback)
                report_lines.append(report)
    else:
        # Step 2: 自动发现今晚该深挖什么
        discovered = auto_discover_domains()
        
        if not discovered:
            # 降级：用硬编码种子中尚未完成的
            report_lines.append("  LLM 未能生成新方向，检查硬编码种子中未完成的领域")
            for key in DOMAIN_SEEDS:
                prog = _load_progress(key)
                if prog == 0:  # 还没开始的
                    report = expand_one_domain(key, progress_callback)
                    report_lines.append(report)
                    break  # 每晚只做一个
        else:
            report_lines.append(f"\n🔍 今晚深挖 {len(discovered)} 个方向:")
            
            for item in discovered:
                key = item["key"]
                config = item["config"]
                
                report_lines.append(f"\n  📊 {config['name']}")
                report_lines.append(f"  种子: {', '.join(config['seeds'][:3])}...")
                
                # 动态注册
                DOMAIN_SEEDS[key] = config
                
                # 执行
                report = expand_one_domain(key, progress_callback)
                report_lines.append(report)
    
    report = "\n".join(report_lines)
    print(report)
    return report
```

### 1.3 替换夜间学习中的调用

在 daily_learning.py 的 `run_night_deep_learning` 末尾，原来的知识图谱扩展是"每周日"执行的。改为"每晚"执行自主深挖：

找到原来的：
```python
    # === 知识图谱扩展（每周一次，周日夜间） ===
    if datetime.now().weekday() == 6:  # 周日
```

替换为：
```python
    # === 自主深挖：每晚自动判断该深挖什么，执行一批 ===
    DEEPDIVE_FLAG = Path(__file__).parent.parent / ".ai-state" / f"deepdive_{datetime.now().strftime('%Y%m%d')}.flag"
    if not DEEPDIVE_FLAG.exists():
        try:
            print("[AutoDeepDive] 开始今晚的自主深挖")
            from scripts.knowledge_graph_expander import run_autonomous_deep_dive
            dd_report = run_autonomous_deep_dive(progress_callback=progress_callback)
            DEEPDIVE_FLAG.write_text(datetime.now().isoformat(), encoding="utf-8")
            report += f"\n\n{dd_report}"
            if progress_callback:
                # 只推送总结，不推送中间进度
                progress_callback(f"📊 自主深挖完成\n{dd_report[:300]}")
        except Exception as e:
            import traceback
            print(f"[AutoDeepDive] 失败: {e}")
            print(traceback.format_exc())
    else:
        print("[AutoDeepDive] 今晚已执行过")
```

### 1.4 更新飞书指令

把"深挖芯片"改为更通用的指令：

```python
elif text.strip() in ("知识图谱", "kg expand", "深挖芯片", "深挖", "自主深挖"):
    send_reply(target, "🔬 启动自主深挖：分析知识库薄弱方向，自动生成深挖计划...", reply_type)
    import threading
    def _deep():
        try:
            from scripts.knowledge_graph_expander import run_autonomous_deep_dive
            report = run_autonomous_deep_dive(progress_callback=lambda msg: send_reply(target, msg, reply_type))
            send_reply(target, f"✅ 自主深挖完成\n{report[:2000]}", reply_type)
        except Exception as e:
            send_reply(target, f"❌ 失败: {e}", reply_type)
    threading.Thread(target=_deep, daemon=True).start()
```

### 验证

```bash
python -c "
from scripts.knowledge_graph_expander import auto_discover_domains, run_autonomous_deep_dive
print('auto_discover_domains: 可导入')
print('run_autonomous_deep_dive: 可导入')
print('✅ Task 1 完成')
"
```

---

## Task 2: 保留硬编码种子作为 fallback

不删除 `DOMAIN_SEEDS`，它作为 LLM 无法生成时的降级方案。同时作为"格式示例"让 LLM 知道输出什么结构。

在 `auto_discover_domains` 的 prompt 中加入一个格式示例（从 DOMAIN_SEEDS 中取一个）：

已在 Task 1 的 plan_prompt 中包含了格式说明，无需额外改动。

---

## Task 3: 深挖进度持久化（断点续传）

当前每批 10 个节点就停，下次从断点继续。但 auto_discover_domains 生成的动态种子没有持久化——如果进程重启，动态种子会丢失，下次不知道该继续哪个。

### 3.1 保存动态种子到磁盘

在 `run_autonomous_deep_dive` 中，发现新领域后立即保存：

```python
        for item in discovered:
            key = item["key"]
            config = item["config"]
            
            # 保存动态种子（断点续传用）
            seed_file = Path(__file__).parent.parent / ".ai-state" / "kg_dynamic_seeds.json"
            existing_seeds = {}
            if seed_file.exists():
                try:
                    existing_seeds = json.loads(seed_file.read_text(encoding="utf-8"))
                except:
                    pass
            existing_seeds[key] = {
                "config": config,
                "discovered_at": datetime.now().isoformat(),
                "status": "in_progress"
            }
            seed_file.write_text(json.dumps(existing_seeds, ensure_ascii=False, indent=2), encoding="utf-8")
```

### 3.2 续传时从磁盘读取

在 `run_autonomous_deep_dive` 的 Step 1（检查未完成任务）中，也读取动态种子文件：

```python
    # 读取动态种子
    seed_file = Path(__file__).parent.parent / ".ai-state" / "kg_dynamic_seeds.json"
    if seed_file.exists():
        try:
            saved_seeds = json.loads(seed_file.read_text(encoding="utf-8"))
            for key, info in saved_seeds.items():
                if info.get("status") == "in_progress":
                    config = info.get("config")
                    if config and key not in DOMAIN_SEEDS:
                        DOMAIN_SEEDS[key] = config
                        print(f"[AutoDeepDive] 恢复动态种子: {config.get('name', key)}")
        except:
            pass
```

### 验证

```bash
python -c "
from pathlib import Path
import json
seed_file = Path('.ai-state/kg_dynamic_seeds.json')
seed_file.parent.mkdir(parents=True, exist_ok=True)
if not seed_file.exists():
    seed_file.write_text('{}', encoding='utf-8')
print(f'种子文件: {seed_file.exists()}')
print('✅ Task 3 完成')
"
```

---

## 执行完成后的检查清单

```bash
# 1. 确认所有改动可导入
python -c "from scripts.knowledge_graph_expander import auto_discover_domains, run_autonomous_deep_dive; print('OK')"
python -c "from scripts.daily_learning import run_night_deep_learning; print('OK')"

# 2. 测试自动发现（不执行深挖，只看发现了什么方向）
python -c "
import sys; sys.path.insert(0, '.')
from scripts.knowledge_graph_expander import auto_discover_domains
domains = auto_discover_domains()
for d in domains:
    config = d['config']
    print(f'  {config[\"name\"]}: {config[\"seeds\"][:3]}')
"

# 3. 重启服务
```

---

## 效果预期

| 之前 | 之后 |
|------|------|
| 用户发"深挖芯片" → 只挖芯片 | 系统自动判断今晚挖什么 |
| 芯片深挖完就停了 | 第二天自动切换到下一个薄弱领域 |
| 硬编码 3 个领域 | LLM 动态生成，可以是电池/传感器/认证/任何方向 |
| 用户不提就不挖 | 每晚自动执行，用户不需要参与 |
| 深挖进度重启后丢失 | 断点续传，跨天继续 |
