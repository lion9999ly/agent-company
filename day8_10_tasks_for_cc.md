# Day 8-10 合并任务 — 系统自学习质量 + 自治能力

> 生成时间: 2026-03-24
> 来源: Claude.ai，基于 plan v5.5 Day 8-10 + 源码分析
> Day 11-12 PRD 相关，暂不执行
> 执行顺序: Task 1 → 2 → 3 → 4 → 5，每个 Task 完成后跑验证

---

## Task 1: 多源搜索修复（8a）

**问题**: daily_learning 日志显示全是 (1 src)，tavily 和 alt_query 没跑起来。
**根因排查**: 需要确认 TAVILY_API_KEY 是否设置、tavily 包是否安装、调用是否报错但被静默吞掉。

### 1.1 诊断脚本（先跑这个，看输出再决定修什么）

```python
python3 << 'PYEOF'
"""诊断多源搜索为什么只有 1 src"""
import os, sys
sys.path.insert(0, '.')

# 检查 1: TAVILY_API_KEY
from pathlib import Path
env_file = Path(".env")
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

tavily_key = os.environ.get("TAVILY_API_KEY", "")
print(f"[1] TAVILY_API_KEY: {'✅ 已设置 (' + tavily_key[:8] + '...)' if tavily_key else '❌ 未设置'}")

# 检查 2: tavily 包
try:
    from tavily import TavilyClient
    print(f"[2] tavily 包: ✅ 已安装")
except ImportError:
    print(f"[2] tavily 包: ❌ 未安装 → pip install tavily-python --break-system-packages")

# 检查 3: 实际调用测试
from src.tools.tool_registry import get_tool_registry
registry = get_tool_registry()

print(f"\n[3] 实际搜索测试:")
test_query = "motorcycle smart helmet HUD AR display 2026"

r1 = registry.call("deep_research", test_query)
print(f"  deep_research: success={r1.get('success')}, data_len={len(r1.get('data', ''))}")
if not r1.get('success'):
    print(f"    error: {r1.get('error', '')[:200]}")

r2 = registry.call("tavily_search", test_query)
print(f"  tavily_search: success={r2.get('success')}, data_len={len(r2.get('data', ''))}")
if not r2.get('success'):
    print(f"    error: {r2.get('error', '')[:200]}")

# 检查 4: alt_query 逻辑
alt_query = test_query.replace("2026", "latest") if "2026" in test_query else test_query + " 2026 review"
r3 = registry.call("tavily_search", alt_query)
print(f"  tavily_alt: success={r3.get('success')}, data_len={len(r3.get('data', ''))}")
if not r3.get('success'):
    print(f"    error: {r3.get('error', '')[:200]}")

total_src = sum(1 for r in [r1, r2, r3] if r.get('success') and len(r.get('data', '')) > 200)
print(f"\n[总计] {total_src}/3 个来源有效")
if total_src >= 2:
    print("✅ 多源搜索正常")
else:
    print("❌ 多源搜索异常，需要修复")
PYEOF
```

### 1.2 根据诊断结果修复

**如果 TAVILY_API_KEY 未设置**：
```bash
# 在 .env 文件中添加（替换为实际 key）
echo "TAVILY_API_KEY=tvly-xxxxxxxxx" >> .env
```

**如果 tavily 包未安装**：
```bash
pip install tavily-python --break-system-packages
```

**如果 tavily 已配置但调用失败**：检查错误信息。如果是网络问题（公司代理），在 `_tool_tavily_search` 中添加超时和重试：

在 tool_registry.py 的 `_tool_tavily_search` 方法中，把 `client.search(...)` 调用包一层 retry：

```python
def _tool_tavily_search(self, query: str, search_depth: str = "advanced") -> Dict[str, Any]:
    """Tavily AI 搜索"""
    import os
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return {"success": False, "error": "TAVILY_API_KEY not set"}
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        
        # 重试 2 次
        last_error = None
        for attempt in range(2):
            try:
                response = client.search(
                    query=query,
                    search_depth=search_depth if attempt == 0 else "basic",  # 第二次降级为 basic
                    max_results=5,
                    include_answer=True
                )
                parts = []
                if response.get("answer"):
                    parts.append(f"[AI Summary]\n{response['answer']}")
                for r in response.get("results", [])[:5]:
                    title = r.get("title", "")
                    content = r.get("content", "")
                    url = r.get("url", "")
                    if content:
                        parts.append(f"[{title}]\n{content[:500]}\nURL: {url}")
                if parts:
                    combined = "\n\n".join(parts)[:5000]
                    return {"success": True, "tool": "tavily", "data": combined}
                return {"success": False, "error": "No results"}
            except Exception as e:
                last_error = e
                import time
                time.sleep(2)
        return {"success": False, "error": str(last_error)}
    except ImportError:
        return {"success": False, "error": "tavily package not installed"}
```

### 1.3 在 daily_learning.py 的多源搜索中加日志增强

在 `run_daily_learning` 函数的多源搜索部分（约第 320-345 行），当前已经有 `print` 日志了，确认它们在输出。如果 tavily 和 alt 都失败，在最终的 report_lines 中记录失败原因：

```python
        # 在 sources 为空的分支后添加失败原因汇总
        if not sources:
            fail_reasons = []
            if not r1_ok: fail_reasons.append(f"deep:{r1.get('error','')[:50]}")
            if not r2_ok: fail_reasons.append(f"tavily:{r2.get('error','')[:50]}")
            if not r3_ok: fail_reasons.append(f"tavily_alt:{r3.get('error','')[:50]}")
            report_lines.append(f"  ❌ {short_query} -- {'; '.join(fail_reasons)}")
            fail_count += 1
            continue
```

### 1.4 验证

```bash
python -c "
from src.tools.tool_registry import get_tool_registry
r = get_tool_registry()
result = r.call('tavily_search', 'motorcycle helmet HUD display')
print(f'tavily: success={result.get(\"success\")}, len={len(result.get(\"data\", \"\"))}')
assert result.get('success'), f'Tavily 仍然失败: {result.get(\"error\")}'
print('✅ Task 1 完成')
"
```

---

## Task 2: 自学习边际递减解决（8b）

**问题**: 固定主题每天重复搜同样的词，产出递减。当前 `_is_duplicate` 只按天去重，跨天又搜一遍。
**方案**: 固定主题搜索成功后标记"已覆盖"，后续轮次跳过已覆盖的固定主题，靠动态主题（缺口驱动）补充新知识。

### 2.1 添加固定主题覆盖追踪

在 daily_learning.py 中，`run_daily_learning` 函数的固定主题处理部分添加覆盖追踪。

在文件顶部（import 区域之后）添加：

```python
COVERED_TOPICS_FILE = Path(__file__).parent.parent / ".ai-state" / "covered_topics.json"

def _load_covered_topics() -> set:
    """加载已覆盖的固定主题指纹"""
    if not COVERED_TOPICS_FILE.exists():
        return set()
    try:
        data = json.loads(COVERED_TOPICS_FILE.read_text(encoding="utf-8"))
        return set(data.get("covered", []))
    except:
        return set()

def _save_covered_topics(covered: set):
    """保存已覆盖的固定主题"""
    COVERED_TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    COVERED_TOPICS_FILE.write_text(
        json.dumps({"covered": list(covered), "updated": datetime.now().isoformat()}, ensure_ascii=False),
        encoding="utf-8"
    )

def _topic_fingerprint(query: str) -> str:
    """固定主题指纹：取前40字符的小写"""
    return query[:40].lower().strip()
```

### 2.2 修改 run_daily_learning 的主循环

在 `run_daily_learning` 函数的 for 循环开头（约第 311 行 `for i, topic in enumerate(topics):` 之后），添加固定主题跳过逻辑：

```python
    covered = _load_covered_topics()
    newly_covered = set()

    for i, topic in enumerate(topics):
        query = topic["query"]
        domain = topic["domain"]
        tags = topic.get("tags", [])
        short_query = query[:35] + "..." if len(query) > 35 else query
        is_dynamic = query in dynamic_query_set

        # === 固定主题覆盖跳过 ===
        if not is_dynamic:
            fp = _topic_fingerprint(query)
            if fp in covered:
                # 已覆盖的固定主题，跳过（动态主题永远不跳过）
                skip_count += 1
                continue
        
        # ... 后续原有逻辑不变 ...
```

在循环内、成功 `add_knowledge` 之后（约第 419 行），标记固定主题为已覆盖：

```python
        # 标记固定主题已覆盖
        if not is_dynamic:
            newly_covered.add(_topic_fingerprint(query))
```

在循环结束后（`report_lines.append(f"\n{'='*40}")` 之前），保存覆盖状态：

```python
    # 保存新覆盖的主题
    if newly_covered:
        covered.update(newly_covered)
        _save_covered_topics(covered)
        report_lines.append(f"[Cover] 新覆盖 {len(newly_covered)} 个固定主题，累计 {len(covered)} 个")
```

### 2.3 添加飞书指令重置覆盖（可选）

在 feishu_sdk_client.py 的文本指令处理中，添加重置覆盖的指令：

```python
elif text.strip() in ("重置学习", "reset learning", "重学"):
    from scripts.daily_learning import COVERED_TOPICS_FILE
    if COVERED_TOPICS_FILE.exists():
        COVERED_TOPICS_FILE.unlink()
    send_reply(open_id, "✅ 已重置学习覆盖记录，下次学习将重新搜索所有固定主题")
```

### 2.4 验证

```bash
python -c "
from scripts.daily_learning import _load_covered_topics, _save_covered_topics, _topic_fingerprint
# 测试覆盖追踪
covered = _load_covered_topics()
print(f'当前覆盖: {len(covered)} 个')
covered.add(_topic_fingerprint('test query for coverage'))
_save_covered_topics(covered)
covered2 = _load_covered_topics()
assert 'test query for coverage' in covered2
print(f'保存后: {len(covered2)} 个')
# 清理
covered2.discard('test query for coverage')
_save_covered_topics(covered2)
print('✅ Task 2 完成')
"
```

---

## Task 3: 知识库质量自动审计（8c）

**问题**: 浅条目（<150字）占比 16%（282/1725），需要自动检测并深化。
**方案**: 建立定期审计机制，集成到日报中。

### 3.1 在 daily_learning.py 中添加知识库审计函数

```python
def audit_knowledge_base() -> dict:
    """审计知识库质量，返回审计报告"""
    from src.tools.knowledge_base import KB_ROOT
    
    if not KB_ROOT.exists():
        return {"total": 0}
    
    total = 0
    shallow = 0  # < 150 字
    medium = 0   # 150-300 字
    deep = 0     # > 300 字
    no_data = 0  # 无具体数据
    duplicates = 0
    
    seen_fingerprints = set()
    import hashlib
    
    stale_entries = []  # 可能过时的条目
    shallow_entries = []  # 需要深化的浅条目
    
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            content = data.get("content", "")
            title = data.get("title", "")
            total += 1
            
            # 深度分布
            if len(content) < 150:
                shallow += 1
                if data.get("type") != "report" and "night_deepened" not in data.get("tags", []):
                    shallow_entries.append({
                        "path": str(f),
                        "title": title[:50],
                        "domain": data.get("domain", ""),
                        "content_len": len(content)
                    })
            elif len(content) < 300:
                medium += 1
            else:
                deep += 1
            
            # 重复检测
            fp = hashlib.md5(f"{title[:30]}||{content[:200]}".encode()).hexdigest()
            if fp in seen_fingerprints:
                duplicates += 1
            seen_fingerprints.add(fp)
            
            # 无数据检测
            import re
            has_number = bool(re.search(r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|USD|\$|%|nits)', content))
            has_model = bool(re.search(r'[A-Z]{2,}\d{2,}|IMX\d|QCC\d|BES\d|ECE\s*\d', content))
            if not has_number and not has_model:
                no_data += 1
                
        except:
            continue
    
    shallow_pct = round(shallow / total * 100, 1) if total > 0 else 0
    
    return {
        "total": total,
        "shallow": shallow,
        "shallow_pct": shallow_pct,
        "medium": medium,
        "deep": deep,
        "no_data": no_data,
        "duplicates": duplicates,
        "shallow_entries": shallow_entries[:20],  # 最多返回 20 个待深化
    }
```

### 3.2 在夜间学习中自动深化浅条目

在 `run_night_deep_learning` 函数的 Phase 1（约第 443 行）中，已有深化逻辑。改进它：使用审计结果来优先深化最需要的条目。

在 Phase 1 开头替换浅条目收集逻辑：

```python
    # === Phase 1: 优先深化审计发现的浅条目 ===
    report_lines.append("\n--- Phase 1: 知识库深化 ---")
    audit = audit_knowledge_base()
    report_lines.append(f"  审计: 总{audit['total']}条, 浅{audit['shallow']}({audit['shallow_pct']}%), 重复{audit['duplicates']}")
    
    shallow_entries = []
    for item in audit.get("shallow_entries", []):
        shallow_entries.append(item)
    
    # 如果审计没找到浅条目，用原来的遍历逻辑
    if not shallow_entries:
        # ... 保留原有的 KB_ROOT.rglob 遍历逻辑 ...
```

### 3.3 在日报中集成审计摘要

在 `generate_daily_report` 函数的末尾（`lines.append(f"\n{'=' * 35}")` 之前），添加：

```python
    # 知识库质量审计
    try:
        audit = audit_knowledge_base()
        lines.append(f"\n[Quality] 浅条目: {audit['shallow']}({audit['shallow_pct']}%) | 无数据: {audit['no_data']} | 重复: {audit['duplicates']}")
        if audit['shallow_pct'] > 15:
            lines.append(f"  ⚠️ 浅条目占比过高，夜间学习将优先深化")
    except:
        pass
```

### 3.4 添加飞书查询指令

在 feishu_sdk_client.py 的文本指令中添加：

```python
elif text.strip() in ("审计", "audit", "知识库审计"):
    from scripts.daily_learning import audit_knowledge_base
    audit = audit_knowledge_base()
    reply = (
        f"📊 知识库审计\n"
        f"总量: {audit['total']} 条\n"
        f"深度: 浅{audit['shallow']}({audit['shallow_pct']}%) | 中{audit['medium']} | 深{audit['deep']}\n"
        f"质量: 无数据{audit['no_data']} | 重复{audit['duplicates']}\n"
        f"待深化: {len(audit.get('shallow_entries', []))} 条"
    )
    send_reply(open_id, reply)
```

### 3.5 验证

```bash
python -c "
from scripts.daily_learning import audit_knowledge_base
audit = audit_knowledge_base()
print(f'总量: {audit[\"total\"]}')
print(f'浅条目: {audit[\"shallow\"]} ({audit[\"shallow_pct\"]}%)')
print(f'无数据: {audit[\"no_data\"]}')
print(f'重复: {audit[\"duplicates\"]}')
print(f'待深化: {len(audit.get(\"shallow_entries\", []))} 条')
print('✅ Task 3 完成')
"
```

---

## Task 4: 自主发现和修复问题（9a）

**问题**: 系统遇到错误需要人工干预。需要自动检测并修复常见问题。
**注意**: Gemini 配额降级已在 Day 7 Task 1 完成。"自行车"检测需要额外加。

### 4.1 在 daily_learning.py 中添加搜索结果质量自检

在 `_refine_with_llm_raw` 调用之后、入库之前（`run_daily_learning` 的约第 363 行），添加产品方向偏离检测：

在成功获得 refined 内容后，添加：

```python
        # === 搜索结果方向自检 ===
        refined_content_lower = refined.get("content", "").lower() if refined else ""
        refined_title_lower = refined.get("title", "").lower() if refined else ""
        combined_text = refined_content_lower + refined_title_lower
        
        # 检测是否偏离摩托车方向（输出了自行车内容但没提摩托车）
        is_bicycle_only = (
            ("自行车" in combined_text or "bicycle" in combined_text or "cycling helmet" in combined_text)
            and "摩托" not in combined_text
            and "motorcycle" not in combined_text
            and "全盔" not in combined_text
            and "full-face" not in combined_text
        )
        
        if is_bicycle_only:
            report_lines.append(f"  [FIX] {short_query} — 结果偏向自行车，自动追加摩托车限定重搜")
            # 自动重搜：在原 query 前加"摩托车"限定
            fixed_query = f"摩托车 motorcycle {query}"
            r_fix = registry.call("deep_research", fixed_query)
            if r_fix.get("success") and len(r_fix.get("data", "")) > 200:
                fix_prompt = (
                    f"基于以下搜索结果，撰写一条与摩托车智能全盔相关的知识条目。\n"
                    f"【重要】排除自行车头盔内容。\n"
                    f"输出 JSON：{{\"title\": \"标题\", \"domain\": \"...\", \"content\": \"500-800字\", \"tags\": [...]}}\n\n"
                    f"搜索词：{fixed_query}\n来源：\n{r_fix['data'][:4000]}"
                )
                refined = _refine_with_llm_raw(fix_prompt)
                if not refined:
                    skip_count += 1
                    continue
            else:
                skip_count += 1
                continue
```

### 4.2 验证

```bash
python -c "
# 验证方向检测逻辑
test_cases = [
    ('自行车头盔LED灯', False),  # 纯自行车 → 应该触发修复
    ('摩托车头盔HUD', True),      # 摩托车 → OK
    ('自行车和摩托车头盔对比', True),  # 都有 → OK
    ('smart helmet display', True),  # 无关键词 → OK（不触发）
]
for text, should_pass in test_cases:
    is_bicycle_only = (
        ('自行车' in text or 'bicycle' in text)
        and '摩托' not in text
        and 'motorcycle' not in text
    )
    ok = (not is_bicycle_only) == should_pass
    print(f'  {\"✅\" if ok else \"❌\"} \"{text}\" → bicycle_only={is_bicycle_only}, expect_pass={should_pass}')
print('✅ Task 4 完成')
"
```

---

## Task 5: 自主发起研究任务（9b）

**问题**: 系统只被动响应，不会主动发起研究。
**方案**: 对齐报告生成后，解析其"行动建议"，自动排队为深度研究任务。

### 5.1 添加自主研究调度函数

在 daily_learning.py 中添加：

```python
def auto_schedule_research(alignment_report: str, progress_callback=None) -> str:
    """基于对齐报告的行动建议，自动发起深度研究"""
    from src.utils.model_gateway import get_model_gateway
    
    gateway = get_model_gateway()
    
    # 让 LLM 从对齐报告中提取可执行的研究任务
    extract_prompt = (
        f"以下是今日的对齐报告。请从中提取 2-3 个最值得深入研究的具体主题。\n"
        f"要求：\n"
        f"1. 每个主题必须围绕摩托车智能全盔（不是自行车）\n"
        f"2. 优先选择报告中提到的'知识缺口'和'行动建议'\n"
        f"3. 搜索词要具体（含品牌/型号/技术名/标准号）\n\n"
        f"输出 JSON 数组：\n"
        f'[{{"title": "研究主题", "goal": "要回答的核心问题", '
        f'"searches": ["搜索词1", "搜索词2", "搜索词3", "搜索词4"]}}]\n\n'
        f"对齐报告：\n{alignment_report[:3000]}"
    )
    
    result = gateway.call_azure_openai("cpo", extract_prompt, "只输出 JSON 数组。", "auto_research_plan")
    if not result.get("success"):
        return "[AutoResearch] LLM 提取失败"
    
    import re
    resp = result["response"].strip()
    resp = re.sub(r'^```json\s*', '', resp)
    resp = re.sub(r'\s*```$', '', resp)
    
    try:
        tasks = json.loads(resp)
    except:
        return "[AutoResearch] JSON 解析失败"
    
    if not isinstance(tasks, list) or not tasks:
        return "[AutoResearch] 无有效研究任务"
    
    # 执行研究
    from scripts.tonight_deep_research import deep_research_one
    
    report_lines = [f"[AutoResearch] 自动发起 {len(tasks[:3])} 个研究任务"]
    
    for i, task in enumerate(tasks[:3], 1):
        task_dict = {
            "id": f"auto_{datetime.now().strftime('%Y%m%d')}_{i}",
            "title": task.get("title", f"自动研究{i}"),
            "goal": task.get("goal", ""),
            "searches": task.get("searches", [])
        }
        
        if progress_callback:
            progress_callback(f"🔬 自动研究 [{i}/{len(tasks[:3])}]: {task_dict['title'][:20]}...")
        
        try:
            report = deep_research_one(task_dict, progress_callback=progress_callback)
            report_lines.append(f"  ✅ {task_dict['title'][:40]} ({len(report)}字)")
        except Exception as e:
            report_lines.append(f"  ❌ {task_dict['title'][:40]}: {e}")
        
        import time
        time.sleep(5)
    
    return "\n".join(report_lines)
```

### 5.2 在夜间学习结束后自动触发研究

在 `run_night_deep_learning` 函数的末尾，对齐报告生成之后（约第 625-636 行），添加自动研究：

```python
    # === 夜间学习结束后，基于对齐报告自动发起研究 ===
    try:
        alignment = generate_alignment_report()
        # 保存对齐报告（原有逻辑）
        reports_dir = Path(__file__).parent.parent / ".ai-state" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = reports_dir / f"alignment_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        report_path.write_text(alignment, encoding="utf-8")
        print(f"\n[Alignment] 对齐报告已生成: {report_path}")
        print(alignment[:500])
        
        # 基于对齐报告自动发起研究（每晚最多 2-3 个）
        auto_report = auto_schedule_research(alignment, progress_callback=progress_callback)
        print(auto_report)
        report += f"\n\n{auto_report}"
        if progress_callback:
            progress_callback(auto_report)
    except Exception as e:
        print(f"[Alignment/AutoResearch] 失败: {e}")
```

### 5.3 添加飞书手动触发指令

```python
elif text.strip() in ("自动研究", "auto research"):
    from scripts.daily_learning import generate_alignment_report, auto_schedule_research
    send_reply(open_id, "🔬 正在基于最新对齐报告自动规划研究任务...")
    alignment = generate_alignment_report()
    report = auto_schedule_research(alignment, progress_callback=lambda msg: send_reply(open_id, msg))
    send_reply(open_id, report)
```

### 5.4 验证

```bash
python -c "
from scripts.daily_learning import auto_schedule_research
# 用一段假的对齐报告测试提取逻辑
test_report = '''
知识缺口：ADAS安全维度仅69条，远低于其他维度。
行动建议：建议重点研究毫米波雷达在摩托车头盔上的集成方案、V2X通讯标准、以及ADAS传感器供应商对比。
'''
# 只测试提取，不执行实际研究
from src.utils.model_gateway import get_model_gateway
import json, re
gateway = get_model_gateway()
extract_prompt = (
    f'从以下对齐报告提取2个研究主题，输出JSON数组。\n{test_report}'
)
result = gateway.call_azure_openai('cpo', extract_prompt, '只输出JSON数组。', 'test')
if result.get('success'):
    resp = re.sub(r'^.*?(\[)', r'\1', result['response'].strip(), count=1)
    resp = re.sub(r'\s*```$', '', resp)
    tasks = json.loads(resp)
    print(f'提取到 {len(tasks)} 个研究主题:')
    for t in tasks:
        print(f'  - {t.get(\"title\", \"\")}')
    print('✅ Task 5 完成')
else:
    print(f'❌ LLM 调用失败: {result.get(\"error\")}')
"
```

---

## Task 6: 研发任务回复格式优化（9c）

**问题**: 研发任务和深度研究的回复格式不一致，进度消息噪音多。

### 6.1 统一回复格式

找到 LangGraph 研发任务完成后的回复逻辑（在 src/graph/router.py 或处理研发任务响应的地方），统一为和深度研究相同的格式：

```
搜索 feishu_sdk_client.py 和 src/graph/ 下所有文件，找到研发任务完成后的飞书回复格式。

grep -rn "研发任务\|task.*完成\|report.*saved\|方案\|send_reply" src/graph/ scripts/feishu_sdk_client.py --include="*.py" | head -30

然后统一回复格式为：

[Research] Done: {任务标题}
{执行摘要（一句话核心结论 + 3-5个关键数据点 + 行动建议）}
Report saved ({字数} chars).

进度消息精简为最多 3 条：
1. 🚀 开始: {任务标题}
2. 📖 研究中: {当前阶段}（每个大阶段一条，不要每个搜索词一条）
3. ✅ 完成: {摘要前50字}

删除或合并其他中间进度消息。
```

### 6.2 验证

重启后在飞书发一条研发任务，观察回复格式是否精简。

---

## 执行完成后的检查清单

```bash
# 1. 确认所有改动能导入
python -c "from src.tools.tool_registry import get_tool_registry; print('registry OK')"
python -c "from scripts.daily_learning import audit_knowledge_base, auto_schedule_research; print('learning OK')"

# 2. 跑一次审计
python -c "
from scripts.daily_learning import audit_knowledge_base
a = audit_knowledge_base()
print(f'Total: {a[\"total\"]}, Shallow: {a[\"shallow\"]}({a[\"shallow_pct\"]}%), Dups: {a[\"duplicates\"]}')
"

# 3. 多源搜索测试
python -c "
from src.tools.tool_registry import get_tool_registry
r = get_tool_registry()
r1 = r.call('deep_research', 'motorcycle helmet HUD')
r2 = r.call('tavily_search', 'motorcycle helmet HUD')
print(f'deep: {r1.get(\"success\")}, tavily: {r2.get(\"success\")}')
"

# 4. 重启主服务，观察日志
```
