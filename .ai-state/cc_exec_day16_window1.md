# Day 16 窗口 1 — 串行执行

> 前置已完成：API 探测、registry 修复、L2 降级链、Claude CLI 修复
> 不要重启飞书服务
> 所有 Gemini 模型不可用（API key leaked），用 doubao_seed_lite 或 gpt_4o_norway 替代

按顺序执行以下 7 个任务。每完成一个就 commit + push。

---

## 任务 0e：学习系统 + 决策树回流连通

在 scripts/tonight_deep_research.py 中：

### 1. 搜索完成后记录学习数据（W1）

找到 Layer 1 搜索完成后的位置（print 了 "搜索完成，N/N 有效" 的地方）。
在那之后追加：

```python
# W1: 记录搜索效果
import json as _json
from pathlib import Path as _Path
_learning_path = _Path(".ai-state/search_learning.jsonl")
_learning_path.parent.mkdir(parents=True, exist_ok=True)
for _sq in search_queries_used:  # 根据实际变量名调整
    try:
        with open(_learning_path, 'a', encoding='utf-8') as _f:
            _f.write(_json.dumps({
                "query": str(_sq)[:200],
                "task": task.get("title", ""),
                "chars_returned": sum(len(str(r)) for r in raw_results if r),
                "timestamp": time.strftime('%Y-%m-%d %H:%M')
            }, ensure_ascii=False) + "\n")
    except Exception as _e:
        print(f"[W1] 记录失败: {_e}")
```

注意：变量名（search_queries_used, raw_results）需要根据代码中的实际变量名调整。关键是在搜索结束后把 query 和结果长度写入 jsonl。

### 2. 任务完成后回流决策树（C-5）

找到每个任务完成后保存报告的位置（有 `[Saved]` 或 `[KB Report]` 的 print 的地方）。
在那之后追加：

```python
# C-5: 回流决策树
try:
    import yaml as _yaml
    _dt_path = Path(__file__).parent.parent / ".ai-state" / "product_decision_tree.yaml"
    if _dt_path.exists():
        _dt = _yaml.safe_load(_dt_path.read_text(encoding='utf-8'))
        _report_lower = (report_content or "").lower()
        for _d in _dt.get("decisions", []):
            _q = _d.get("question", "")
            # 用问题中的关键词匹配报告内容
            _keywords = [w for w in _q.replace("？", "").replace("?", "").split() if len(w) > 1]
            _match_count = sum(1 for kw in _keywords if kw.lower() in _report_lower)
            if _match_count >= 2:  # 至少匹配 2 个关键词
                _d["resolved_knowledge"] = _d.get("resolved_knowledge", 0) + 1
                print(f"  [DecisionTree] {_d.get('id')}: +1 -> {_d['resolved_knowledge']}")
        _dt_path.write_text(
            _yaml.dump(_dt, allow_unicode=True, default_flow_style=False),
            encoding='utf-8'
        )
except Exception as _e:
    print(f"  [DecisionTree] 回流失败: {_e}")
```

### 3. 模型效果记录（W3）

在同一个位置（报告保存后）追加：

```python
# W3: 模型效果记录
try:
    _meff_path = Path(__file__).parent.parent / ".ai-state" / "model_effectiveness.jsonl"
    with open(_meff_path, 'a', encoding='utf-8') as _f:
        _f.write(_json.dumps({
            "task": task.get("title", ""),
            "report_chars": len(report_content or ""),
            "duration_min": round((time.time() - task_start_time) / 60, 1),
            "timestamp": time.strftime('%Y-%m-%d %H:%M')
        }, ensure_ascii=False) + "\n")
except Exception as _e:
    print(f"  [W3] 记录失败: {_e}")
```

git add -A && git commit -m "fix: connect W1 search learning, W3 model effectiveness, C-5 decision tree backflow" && git push origin main

---

## 任务 0f：启动前 API 健康检查

在 scripts/tonight_deep_research.py 的 run_deep_learning() 函数（或主入口函数）最开头，在任何研究任务之前，新增：

```python
def _pre_flight_api_check(send_reply=None, reply_target=None):
    """30 秒验证关键模型是否可用"""
    results = {}
    critical = ["gpt_5_4", "o3_deep_research"]
    important = ["doubao_seed_pro", "gpt_4o_norway", "deepseek_v3_volcengine"]
    
    for model in critical + important:
        try:
            r = gateway.call(model, "Ping", task_type="health_check")
            results[model] = "✅" if r.get("success") else f"❌ {str(r.get('error',''))[:50]}"
        except Exception as e:
            results[model] = f"❌ {e}"
    
    unavailable_critical = [m for m in critical if "❌" in results.get(m, "❌")]
    
    status_msg = "🔍 API 健康检查:\n" + "\n".join([f"  {m}: {s}" for m, s in results.items()])
    
    if unavailable_critical:
        status_msg += f"\n\n❌ 核心模型不可用: {unavailable_critical}，深度学习暂停"
        if send_reply and reply_target:
            send_reply(reply_target, status_msg)
        return False
    
    if any("❌" in v for v in results.values()):
        status_msg += "\n\n⚠️ 部分非核心模型不可用，将使用降级方案"
    else:
        status_msg += "\n\n✅ 所有模型可用"
    
    if send_reply and reply_target:
        send_reply(reply_target, status_msg)
    print(status_msg)
    return True
```

在主入口中调用（找到 "深度学习模式" 或 "深度学习开始" 的 print 位置，在它之前加）：

```python
if not _pre_flight_api_check(send_reply, reply_target):
    return
```

git add -A && git commit -m "feat: pre-flight API health check before deep learning" && git push origin main

---

## 任务 0g：任务池耗尽后多来源发现

找到 `[Scheduler] 任务池空，自主发现新方向` 相关的代码。
在好奇心模块返回空列表后，增加 fallback：

```python
def _discover_from_decision_tree():
    """从决策树的未解决决策中生成研究任务"""
    try:
        dt_path = Path(__file__).parent.parent / ".ai-state" / "product_decision_tree.yaml"
        if not dt_path.exists():
            return []
        dt = yaml.safe_load(dt_path.read_text(encoding='utf-8'))
        tasks = []
        for d in dt.get("decisions", []):
            resolved = d.get("resolved_knowledge", 0)
            needed = d.get("total_needed", 3)
            if resolved < needed:
                tasks.append({
                    "title": f"决策补充: {d.get('question', '')[:40]}",
                    "goal": f"补充决策所需信息: {d.get('question', '')}。目前进度 {resolved}/{needed}。",
                    "searches": 4,
                    "source": "decision_tree_gap"
                })
        return tasks
    except:
        return []
```

在 Scheduler 的"无新任务可发现"之前，调用这个函数：

```python
# 原有的好奇心发现
new_tasks = _discover_new_tasks(...)
if not new_tasks:
    # Fallback: 从决策树缺口中发现
    new_tasks = _discover_from_decision_tree()
    if new_tasks:
        print(f"[Scheduler] 从决策树发现 {len(new_tasks)} 个补充任务")
if not new_tasks:
    print("[Scheduler] 无新任务可发现，结束")
    break
```

git add -A && git commit -m "feat: decision tree gap discovery when task pool exhausted" && git push origin main

---

## 任务 2：CC CLI 路径修复

已完成（claude_cli_helper.py 已创建并验证）。跳过。

---

## 任务 1：auto_fixer 解析增强

修改 scripts/auto_fixer.py：

### 1. 修改发给模型的 prompt

找到生成修复建议的 prompt，在末尾追加格式要求：

```python
fix_prompt += (
    "\n\n必须用以下格式输出修复（严格遵守）:\n"
    "FILE: scripts/example.py\n"
    "OLD:\n```python\n原始代码\n```\n"
    "NEW:\n```python\n新代码\n```\n\n"
    "如果问题不在代码（如 API 不可用、配置问题），说明原因即可，不需要给代码修复。"
)
```

### 2. 增加 Flash fallback 解析

在 _apply_fix() 中，正则解析失败后，用 Claude CLI（GLM-5）做二次提取：

```python
# 正则解析失败后的 fallback
if not all([file_match, old_match, new_match]):
    try:
        from scripts.claude_cli_helper import call_claude_cli
        extract_result = call_claude_cli(
            f"从以下修复建议中提取代码修改。输出严格 JSON（不要 markdown）:"
            f'{{"file": "路径", "old_code": "原始代码", "new_code": "新代码"}}'
            f"如果不包含代码修改，输出: {{\"no_fix\": true}}\n\n{fix_suggestion[:2000]}",
            timeout=30
        )
        if extract_result:
            import json
            parsed = json.loads(extract_result.strip().replace('```json','').replace('```',''))
            if not parsed.get("no_fix"):
                return _do_replace(parsed["file"], parsed["old_code"], parsed["new_code"])
    except Exception as e:
        print(f"  [AutoFix] CLI fallback 也失败: {e}")
```

### 3. 增加文件路径模糊匹配

在 _do_replace() 中，如果文件路径不存在，尝试加前缀：

```python
if not target.exists():
    for prefix in ["scripts/", "src/", "scripts/feishu_handlers/", "src/utils/", "src/config/"]:
        candidate = PROJECT_ROOT / prefix / file_path.strip().split("/")[-1]
        if candidate.exists():
            target = candidate
            break
```

git add -A && git commit -m "fix: auto_fixer robust parsing — format hint + CLI fallback + path fuzzy match" && git push origin main

---

## 任务 3：handoff 机制验证

### 1. 在 scripts/handoff_processor.py 中增加执行逻辑

```python
def execute_handoff(handoff_path):
    """执行 handoff 文件中的任务"""
    from scripts.claude_cli_helper import call_claude_cli
    
    content = handoff_path.read_text(encoding='utf-8')
    print(f"[Handoff] 执行: {handoff_path.name}")
    
    result = call_claude_cli(
        f"读取以下 handoff 内容，按顺序执行其中的待办任务：\n\n{content[:4000]}",
        timeout=180
    )
    
    if result:
        mark_processed(handoff_path)
        print(f"[Handoff] 完成: {handoff_path.name}")
        return {"success": True, "output": result[:500]}
    else:
        print(f"[Handoff] CLI 不可用，仅标记已读")
        mark_processed(handoff_path)
        return {"success": False, "reason": "CLI unavailable"}
```

### 2. 创建测试 handoff

```bash
mkdir -p .ai-state/handoffs
echo "# Test Handoff" > .ai-state/handoffs/test_20260405.md
echo "" >> .ai-state/handoffs/test_20260405.md
echo "## 待执行任务" >> .ai-state/handoffs/test_20260405.md
echo "1. 在 .ai-state/ 下创建 handoff_test_result.txt，写入 handoff works" >> .ai-state/handoffs/test_20260405.md
```

### 3. 验证

```python
python -c "
from scripts.handoff_processor import scan_unprocessed, execute_handoff
pending = scan_unprocessed()
print(f'待处理: {len(pending)} 个')
for f in pending:
    result = execute_handoff(f)
    print(f'  {f.name}: {result}')
"
```

### 4. 在 feishu_sdk_client.py 启动逻辑中追加 handoff 扫描

找到服务启动完成后的位置（"服务启动，等待消息" 的 print 附近），追加：

```python
# 启动时扫描未处理的 handoff
try:
    from scripts.handoff_processor import scan_unprocessed, execute_handoff
    _pending = scan_unprocessed()
    if _pending:
        print(f"[Handoff] 发现 {len(_pending)} 个未处理")
        for _f in _pending:
            execute_handoff(_f)
except Exception as _e:
    print(f"[Handoff] 扫描失败: {_e}")
```

git add -A && git commit -m "feat: handoff execution + startup scan + test verification" && git push origin main

---

## 完成后验证

运行自愈系统自检：

```bash
cd D:\Users\uih00653\my_agent_company\pythonProject1
.venv\Scripts\python.exe scripts/self_heal.py
```

把自检结果贴出来。
