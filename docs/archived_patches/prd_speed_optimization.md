# PRD 生成速度优化 — 批内并行 + 文件并行生成发送

> 改 scripts/feishu_handlers/structured_doc.py
> 和 prd_quality_evolution_final.md 不冲突（改的是不同函数/位置）
> 目标：额外 Sheet 从 13 分钟降到 3 分钟，文件生成发送从 18 秒降到 6 秒

---

## 改动 1：_gen_test_cases 内部批次改并行

当前：14 批串行 × 30 秒 = 13 分钟（整个流程的瓶颈）
改后：14 批 ÷ 4 路并行 × 30 秒 = 2 分钟

```python
def _gen_test_cases(items, gateway):
    """基于 L3 验收标准生成测试用例（批内并行）"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import re, json
    
    l3_features = [i for i in items if i.get("level") == "L3" and i.get("acceptance")]
    all_cases = []
    batch_size = 30
    
    # 构建所有批次
    batches = []
    for start in range(0, len(l3_features), batch_size):
        batches.append((start, l3_features[start:start + batch_size]))
    
    print(f"[TestCase] {len(l3_features)} 个 L3 → {len(batches)} 批 × 4 路并行")
    
    def _gen_batch(batch_info):
        start, batch = batch_info
        features_text = "\n".join(
            f"- {f.get('name','')}: 验收={f.get('acceptance','')}"
            for f in batch
        )
        prompt = (
            f"为以下验收标准生成测试用例。输出 JSON 数组，每个元素：\n"
            f'{{"case_id":"TC-001","feature":"功能名","title":"用例标题",'
            f'"precondition":"前置条件","steps":"操作步骤(分号分隔)",'
            f'"expected":"预期结果","priority":"P0-P3"}}\n\n'
            f"每个功能 1-2 条（正常+异常）。预期结果含具体数字。\n"
            f"功能列表：\n{features_text}\n\n只输出 JSON。"
        )
        result = gateway.call_azure_openai("cpo", prompt, "只输出JSON。", "structured_doc")
        if result.get("success"):
            match = re.search(r'\[[\s\S]*\]', result["response"])
            if match:
                try:
                    cases = json.loads(match.group())
                    for idx, c in enumerate(cases):
                        c["case_id"] = f"TC-{start + idx + 1:04d}"
                    return cases
                except:
                    pass
        return []
    
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_gen_batch, b): b[0] for b in batches}
        done = 0
        for f in as_completed(futs):
            cases = f.result()
            all_cases.extend(cases)
            done += 1
            if done % 3 == 0:
                print(f"  [TestCase] 进度: {done}/{len(batches)} 批完成")
    
    print(f"[TestCase] 生成 {len(all_cases)} 条")
    return all_cases
```

---

## 改动 2：_gen_user_stories 内部批次改并行

同样的改造：

```python
def _gen_user_stories(items, gateway):
    """基于功能清单生成用户故事（批内并行）"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import re, json
    
    l2_features = [i for i in items if i.get("level") == "L2"]
    all_stories = []
    batch_size = 30
    
    batches = []
    for start in range(0, len(l2_features), batch_size):
        batches.append((start, l2_features[start:start + batch_size]))
    
    print(f"[UserStory] {len(l2_features)} 个 L2 → {len(batches)} 批 × 4 路并行")
    
    def _gen_batch(batch_info):
        start, batch = batch_info
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
            match = re.search(r'\[[\s\S]*\]', result["response"])
            if match:
                try:
                    return json.loads(match.group())
                except:
                    pass
        return []
    
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_gen_batch, b): b[0] for b in batches}
        for f in as_completed(futs):
            all_stories.extend(f.result())
    
    print(f"[UserStory] 生成 {len(all_stories)} 条")
    return all_stories
```

---

## 改动 3：_gen_dev_tasks 内部批次改并行

```python
def _gen_dev_tasks(items, gateway):
    """基于功能清单生成开发任务（批内并行）"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import re, json
    
    l2_features = [i for i in items if i.get("level") == "L2"]
    all_tasks = []
    batch_size = 30
    
    batches = []
    for start in range(0, len(l2_features), batch_size):
        batches.append((start, l2_features[start:start + batch_size]))
    
    print(f"[DevTask] {len(l2_features)} 个 L2 → {len(batches)} 批 × 4 路并行")
    
    def _gen_batch(batch_info):
        start, batch = batch_info
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
            match = re.search(r'\[[\s\S]*\]', result["response"])
            if match:
                try:
                    tasks = json.loads(match.group())
                    for idx, t in enumerate(tasks):
                        t["task_id"] = f"T-{start + idx + 1:04d}"
                    return tasks
                except:
                    pass
        return []
    
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_gen_batch, b): b[0] for b in batches}
        for f in as_completed(futs):
            all_tasks.extend(f.result())
    
    print(f"[DevTask] 生成 {len(all_tasks)} 条")
    return all_tasks
```

---

## 改动 4：取消 batch 3，dev_tasks 并入 batch 2

找到主流程中 batch 2 和 batch 3 的代码。把 dev_tasks 从单独的 batch 3 合并到 batch 2：

```python
        # 批次 2：依赖功能清单的 5 个 Sheet（5 路并行，不再有 batch 3）
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures2 = {
                pool.submit(_gen_sheet7_voice_nav_scenarios, _gw, kb_context): "voice_nav",
                pool.submit(_gen_user_stories, all_items, _gw): "user_stories",
                pool.submit(_gen_test_cases, all_items, _gw): "test_cases",
                pool.submit(_gen_page_mapping, all_items, _gw): "page_mapping",
                pool.submit(_gen_dev_tasks, all_items, _gw): "dev_tasks",
            }
            for future in as_completed(futures2):
                name = futures2[future]
                try:
                    data = future.result()
                    extra_sheets[name] = data
                    print(f"  ✅ {name}: {len(data)} 条")
                except Exception as e:
                    extra_sheets[name] = []
                    print(f"  ❌ {name}: {e}")
        
        total_extra = sum(len(v) for v in extra_sheets.values())
        print(f"[FastTrack] 额外 Sheet 完成: {total_extra} 条")
```

删掉原来单独的 batch 3 代码（如果有的话）。

---

## 改动 5：4 个文件并行生成

找到 Excel/.xmind/脑图HTML/PRD HTML 的生成代码，改为并行：

```python
    # === 并行生成 4 个文件 ===
    from concurrent.futures import ThreadPoolExecutor
    
    export_dir = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    
    file_results = {}
    
    def _make_excel():
        return _export_to_excel(all_items, task_id, text[:50],
                                extra_sheets=extra_sheets, audit_issues=audit_issues)
    
    def _make_xmind():
        data = _generate_mindmap_xmind(all_items, "智能骑行头盔 V1 功能框架")
        path = export_dir / f"mindmap_{task_id}.xmind"
        path.write_bytes(data)
        return str(path)
    
    def _make_mindmap_html():
        content = _generate_mindmap_svg(all_items, "智能骑行头盔 V1 功能框架")
        path = export_dir / f"mindmap_{task_id}.html"
        path.write_text(content, encoding="utf-8")
        return str(path)
    
    def _make_prd_html():
        content = _generate_interactive_prd_html(all_items, extra_sheets,
                                                  "智能骑行头盔 V1 PRD 规格书")
        path = export_dir / f"prd_interactive_{task_id}.html"
        path.write_text(content, encoding="utf-8")
        return str(path)
    
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_excel = pool.submit(_make_excel)
        f_xmind = pool.submit(_make_xmind)
        f_mindmap = pool.submit(_make_mindmap_html)
        f_prd = pool.submit(_make_prd_html)
        
        try:
            file_results["excel"] = f_excel.result()
        except Exception as e:
            print(f"[File] Excel 生成失败: {e}")
        try:
            file_results["xmind"] = f_xmind.result()
        except Exception as e:
            print(f"[File] XMind 生成失败: {e}")
        try:
            file_results["mindmap_html"] = f_mindmap.result()
        except Exception as e:
            print(f"[File] 脑图HTML 生成失败: {e}")
        try:
            file_results["prd_html"] = f_prd.result()
        except Exception as e:
            print(f"[File] PRD HTML 生成失败: {e}")
    
    print(f"[FastTrack] {len(file_results)} 个文件并行生成完成")
```

---

## 改动 6：4 个文件并行发送飞书

替换原来的串行发送：

```python
    # === 并行发送所有文件 ===
    send_files = []
    if file_results.get("excel"):
        send_files.append(("Excel", file_results["excel"]))
    if file_results.get("xmind"):
        send_files.append(("XMind脑图", file_results["xmind"]))
    if file_results.get("mindmap_html"):
        send_files.append(("交互脑图", file_results["mindmap_html"]))
    if file_results.get("prd_html"):
        send_files.append(("交互PRD", file_results["prd_html"]))
    
    def _send_one(name_path):
        name, path = name_path
        try:
            ok = _send_file_to_feishu(reply_target, path, id_type)
            return name, ok
        except Exception as e:
            print(f"[Send] {name} 失败: {e}")
            return name, False
    
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_send_one, sf): sf[0] for sf in send_files}
        for f in as_completed(futs):
            name, ok = f.result()
            print(f"  {'✅' if ok else '❌'} {name} 发送{'成功' if ok else '失败'}")
```

---

## 预期效果

| 阶段 | 改前 | 改后 |
|------|------|------|
| 功能清单（30 模块 × 4路） | 2.5 min | 2.5 min（不变） |
| batch 1（4 Sheet） | 1 min | 1 min（不变） |
| batch 2（test_cases 瓶颈） | 13 min | 2 min |
| batch 3（dev_tasks） | 5 min | 0（合并到 batch 2） |
| 文件生成 | 3 sec | 1 sec |
| 文件发送 | 15 sec | 5 sec |
| **总计** | **~22 min** | **~6 min** |

---

## 验证

```bash
# 确认三个函数已改为并行
grep -c "ThreadPoolExecutor" scripts/feishu_handlers/structured_doc.py
# 应该比改前多 3-5 个

# 确认没有 batch 3 的代码
grep -n "batch 3\|批次 3\|第三批" scripts/feishu_handlers/structured_doc.py
# 应该无结果

# 确认文件并行生成
grep -n "_make_excel\|_make_xmind\|_make_mindmap\|_make_prd" scripts/feishu_handlers/structured_doc.py

# 确认文件并行发送
grep -n "_send_one\|send_files" scripts/feishu_handlers/structured_doc.py
```
