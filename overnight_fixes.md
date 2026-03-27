# 夜间运行问题修复 — 6 个问题

> 生成时间: 2026-03-25
> 来源: 8 小时夜间自治运行日志分析
> 执行顺序: Task 1 → 6，每个完成后跑验证

---

## Task 1: 自主研究没触发（P0）

**问题**: 对齐报告生成了 5 份，但 auto_schedule_research 从未执行。日志里没有任何 [AutoResearch] 输出。

**排查**: 在 daily_learning.py 的 run_night_deep_learning 函数末尾，对齐报告生成后应该调用 auto_schedule_research。检查是否调用了、是否报错被 except 吞掉了。

```bash
grep -n "auto_schedule_research\|AutoResearch" scripts/daily_learning.py
```

**可能的原因**：
1. auto_schedule_research 没被 import 或没被调用
2. 调用了但在 try/except 里静默失败
3. 函数定义了但没被嵌入到 run_night_deep_learning 的流程中

**修复**: 确认 run_night_deep_learning 末尾的代码。应该是这样的结构：

```python
    # 在 run_night_deep_learning 函数末尾，对齐报告生成之后
    try:
        alignment = generate_alignment_report()
        # 保存对齐报告
        reports_dir = Path(__file__).parent.parent / ".ai-state" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = reports_dir / f"alignment_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        report_path.write_text(alignment, encoding="utf-8")
        print(f"\n[Alignment] 对齐报告已生成: {report_path}")
        
        # === 自主研究：基于对齐报告自动发起 ===
        print("[AutoResearch] 开始基于对齐报告自动规划研究...")
        auto_report = auto_schedule_research(alignment, progress_callback=progress_callback)
        print(f"[AutoResearch] 完成: {auto_report[:200]}")
        report += f"\n\n{auto_report}"
        if progress_callback:
            progress_callback(auto_report[:500])
            
    except Exception as e:
        # 不要静默吞掉！打印完整错误
        import traceback
        print(f"[AutoResearch] 失败: {e}")
        print(traceback.format_exc())
```

如果 auto_schedule_research 的调用根本不在代码里，添加上去。如果在但被 except 吞了，添加 traceback 打印。

**额外保险**: 每晚只触发一次自主研究（避免 5 轮夜间学习每轮都触发）。添加一个标记：

```python
    # 在 run_night_deep_learning 函数开头
    AUTO_RESEARCH_FLAG = Path(__file__).parent.parent / ".ai-state" / f"auto_research_{datetime.now().strftime('%Y%m%d')}.flag"
    
    # 在对齐报告生成后、调用 auto_schedule_research 之前
    if not AUTO_RESEARCH_FLAG.exists():
        print("[AutoResearch] 今晚首次触发，开始自主研究...")
        auto_report = auto_schedule_research(alignment, progress_callback=progress_callback)
        AUTO_RESEARCH_FLAG.write_text(datetime.now().isoformat(), encoding="utf-8")
        print(f"[AutoResearch] 完成")
        report += f"\n\n{auto_report}"
    else:
        print("[AutoResearch] 今晚已执行过，跳过")
```

### 验证

```bash
python -c "
from scripts.daily_learning import auto_schedule_research, generate_alignment_report
print('auto_schedule_research: 可导入')
print('generate_alignment_report: 可导入')

# 检查 run_night_deep_learning 中是否调用了 auto_schedule_research
import inspect
from scripts.daily_learning import run_night_deep_learning
source = inspect.getsource(run_night_deep_learning)
has_call = 'auto_schedule_research' in source
print(f'run_night_deep_learning 中是否调用: {\"✅\" if has_call else \"❌ 缺失！\"}')
"
```

---

## Task 2: Tavily 配额耗尽短路（P0）

**问题**: Tavily 免费配额用完了，每次调用都失败再降级，产生大量重复日志 "[Tavily] 配额耗尽，降级到 Gemini"。应该检测到配额耗尽后短路跳过一段时间。

**修复**: 在 tool_registry.py 的 `_tool_tavily_search` 方法中添加配额耗尽记忆。

在 ToolRegistry 类的 `__init__` 中添加：

```python
        self._tavily_exhausted_until = 0  # Unix timestamp，在此之前不尝试 Tavily
```

在 `_tool_tavily_search` 方法开头添加短路检查：

```python
    def _tool_tavily_search(self, query: str, search_depth: str = "advanced") -> Dict[str, Any]:
        """Tavily AI 搜索"""
        import os, time
        
        # === 配额耗尽短路：4 小时内不重试 ===
        if time.time() < self._tavily_exhausted_until:
            remaining_min = int((self._tavily_exhausted_until - time.time()) / 60)
            # 静默降级到 Gemini，不打日志（避免刷屏）
            return self._tavily_fallback_gemini(query)
        
        api_key = os.environ.get("TAVILY_API_KEY", "")
        if not api_key:
            return self._tavily_fallback_gemini(query)
        
        # ... 原有逻辑 ...
```

在 catch 到配额错误时设置短路时间：

```python
        except Exception as e:
            error_str = str(e)
            # 检测配额耗尽
            if "exceeds your plan" in error_str or "usage limit" in error_str:
                import time as _time
                self._tavily_exhausted_until = _time.time() + 4 * 3600  # 4 小时后再试
                print(f"[Tavily] 配额耗尽，4 小时内自动跳过，降级到 Gemini")
                return self._tavily_fallback_gemini(query)
            # ... 其他错误处理 ...
```

添加降级辅助方法（如果还没有的话）：

```python
    def _tavily_fallback_gemini(self, query: str) -> Dict[str, Any]:
        """Tavily 降级到 Gemini Deep Research"""
        gateway = get_model_gateway()
        result = gateway.call_gemini("gemini_deep_research", query, "详细搜索以下内容", "tavily_fallback")
        if result.get("success"):
            return {"success": True, "tool": "tavily_fallback_gemini", "data": result["response"]}
        # Gemini 也失败，尝试 Flash
        result2 = gateway.call_gemini("gemini_2_5_flash", query, "搜索以下内容", "tavily_fallback_flash")
        if result2.get("success"):
            return {"success": True, "tool": "tavily_fallback_flash", "data": result2["response"]}
        return {"success": False, "error": "Tavily exhausted and Gemini fallback failed"}
```

### 验证

```bash
python -c "
from src.tools.tool_registry import get_tool_registry
r = get_tool_registry()
# 模拟配额耗尽
import time
r._tavily_exhausted_until = time.time() + 100
result = r.call('tavily_search', 'test query')
print(f'短路降级: success={result.get(\"success\")}, tool={result.get(\"tool\", \"?\")}')
# 重置
r._tavily_exhausted_until = 0
print('✅ Task 2 完成')
"
```

---

## Task 3: 日学习 skip 率过高（P1）

**问题**: 16 个主题只有 4-5 个新增，skip 率 75%。固定主题覆盖后只靠 5 个动态主题，太少了。

**修复**: 

### 3.1 增加动态主题数量

在 daily_learning.py 的 `_generate_dynamic_topics` 函数中，把请求 5 个动态主题改为 10 个：

找到这行（约第 169 行）：
```python
        f"请生成 5 个高价值搜索词。要求：\n"
```

改为：
```python
        f"请生成 10 个高价值搜索词。要求：\n"
```

### 3.2 固定主题覆盖后自动切换为更新模式

固定主题不应该永远跳过——应该定期检查有没有新信息。修改覆盖逻辑：覆盖超过 7 天的固定主题重新搜索。

在 `run_daily_learning` 函数中，固定主题跳过逻辑处：

```python
        # === 固定主题覆盖跳过（7 天后重新搜索） ===
        if not is_dynamic:
            fp = _topic_fingerprint(query)
            if fp in covered:
                # 检查覆盖时间——超过 7 天重新搜
                cover_age = _get_cover_age(fp)
                if cover_age is not None and cover_age < 7:
                    skip_count += 1
                    continue
                else:
                    # 超过 7 天或无记录，重新搜索
                    pass
```

添加覆盖时间追踪：

```python
def _load_covered_topics() -> dict:
    """加载已覆盖的固定主题及其覆盖时间"""
    if not COVERED_TOPICS_FILE.exists():
        return {}
    try:
        data = json.loads(COVERED_TOPICS_FILE.read_text(encoding="utf-8"))
        # 兼容旧格式（set → dict）
        covered = data.get("covered", {})
        if isinstance(covered, list):
            # 旧格式是 list，转换为 dict
            covered = {fp: datetime.now().strftime("%Y-%m-%d") for fp in covered}
        return covered
    except:
        return {}

def _save_covered_topics(covered: dict):
    """保存已覆盖的固定主题及时间"""
    COVERED_TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    COVERED_TOPICS_FILE.write_text(
        json.dumps({"covered": covered, "updated": datetime.now().isoformat()}, ensure_ascii=False),
        encoding="utf-8"
    )

def _get_cover_age(fp: str) -> int:
    """获取固定主题覆盖了多少天，返回 None 表示无记录"""
    covered = _load_covered_topics()
    date_str = covered.get(fp)
    if not date_str:
        return None
    try:
        cover_date = datetime.strptime(date_str, "%Y-%m-%d")
        return (datetime.now() - cover_date).days
    except:
        return 0
```

同步修改 `_topic_fingerprint` 后的标记逻辑，保存时带日期：

```python
        # 标记固定主题已覆盖（带日期）
        if not is_dynamic:
            newly_covered[_topic_fingerprint(query)] = datetime.now().strftime("%Y-%m-%d")
```

保存时 merge：

```python
    if newly_covered:
        covered = _load_covered_topics()
        covered.update(newly_covered)
        _save_covered_topics(covered)
```

### 验证

```bash
python -c "
from scripts.daily_learning import _generate_dynamic_topics
topics = _generate_dynamic_topics()
print(f'动态主题数量: {len(topics)}')
assert len(topics) >= 8, f'动态主题太少: {len(topics)}'
print('✅ Task 3 完成')
"
```

---

## Task 4: 无数据条目占比 39%（P1）

**问题**: 925/2352 条目没有具体数据（型号、参数、价格），说明 LLM 提炼时产出了大量泛泛内容。

**修复**: 在入库的质量过滤中，对"无数据"条目做更严格的处理——不是跳过，而是要求 LLM 重写补充数据。

### 4.1 在 daily_learning.py 的入库前质量过滤中添加"无数据补充"

在 `run_daily_learning` 中，现有的质量过滤逻辑之后（约第 382-406 行），对通过了其他检查但无数据的条目，要求补充：

```python
        # === 无数据条目补充（不跳过，要求 LLM 补充具体数据） ===
        if not has_data and not has_model and not is_low_quality:
            # 内容够长但缺数据，让 LLM 补充
            if len(refined_content) >= 200 and len(sources) > 0:
                enrich_prompt = (
                    f"以下知识条目内容缺少具体数据。请基于原始搜索结果补充：\n"
                    f"- 具体型号（如 IMX678、BES2800、QCC5181）\n"
                    f"- 具体参数（如 3000nits、42dB、1.65kg）\n"
                    f"- 具体价格（如 $15-25/颗、￥200-300）\n"
                    f"- 具体公司/品牌名\n\n"
                    f"如果原始搜索结果中确实没有这些数据，保持原文不变。\n\n"
                    f"当前条目：\n标题：{refined_title}\n内容：{refined_content}\n\n"
                    f"原始搜索结果：\n{combined[:3000]}\n\n"
                    f"输出 JSON：{{\"content\": \"补充数据后的完整内容(500-800字)\"}}"
                )
                enrich_result = _refine_with_llm_raw(enrich_prompt)
                if enrich_result and len(enrich_result.get("content", "")) > len(refined_content):
                    old_len = len(refined_content)
                    refined_content = enrich_result["content"][:800]
                    print(f"  [ENRICH] {short_query} 补充数据: {old_len} -> {len(refined_content)}字")
```

### 4.2 一次性清理现有无数据条目（可选，后台跑）

这个太重了不建议现在跑。让夜间深化逐步处理。但在夜间 Phase 1 的浅条目选择中，优先选"无数据"条目深化。

在 `audit_knowledge_base` 返回的 `shallow_entries` 中，也包含无数据条目：

在 audit_knowledge_base 函数中，收集无数据条目的逻辑：

```python
            # 无数据条目也加入待深化列表
            if not has_number and not has_model and len(content) > 0:
                if data.get("type") != "report" and "night_deepened" not in data.get("tags", []):
                    shallow_entries.append({
                        "path": str(f),
                        "title": title[:50],
                        "domain": data.get("domain", ""),
                        "content_len": len(content),
                        "reason": "no_data"
                    })
```

### 验证

```bash
python -c "
from scripts.daily_learning import audit_knowledge_base
a = audit_knowledge_base()
print(f'无数据条目: {a[\"no_data\"]} / {a[\"total\"]} ({round(a[\"no_data\"]/a[\"total\"]*100, 1)}%)')
print('✅ Task 4 完成')
"
```

---

## Task 5: 夜间拓展主题重复（P1）

**问题**: "Shoei Opticson"、"Gentex Ops-Core"、"Hexr custom 3D printed" 每轮都出现。night_expanded.json 的去重没挡住。

**排查**: run_night_deep_learning 的 Phase 2 和 Phase 3 中，扩展主题的排除列表读取逻辑可能有问题。

```bash
grep -n "expanded_history\|EXPANDED_FILE\|expanded_exclude\|不要重复" scripts/daily_learning.py | head -20
```

**修复**: 

### 5.1 强化跨界搜索去重

在 run_night_deep_learning 的 Phase 3（跨界探索），生成搜索词的 prompt 中，当前只写了固定的 3 个排除词。改为动态注入已搜过的全部主题：

找到 `cross_prompt` 的构建（约第 563 行），修改排除列表：

```python
    # 读取已拓展历史（Phase 2 和 Phase 3 共享）
    all_expanded = list(set(expanded_history[-100:]))  # 去重
    expanded_exclude_text = "\n".join(all_expanded[-30:]) if all_expanded else "暂无"
    
    cross_prompt = (
        f"你是智能骑行头盔研发中心的学习规划师。\n"
        f"请生成 4 个跨界探索搜索词，用于从其他行业获取灵感。\n"
        f"要求：\n"
        f"1. 每个搜索词涉及不同行业（汽车、滑雪、建筑、军事、医疗、航空等）\n"
        f"2. 与智能头盔有潜在技术或设计关联\n"
        f"3. 具体（含品牌名/技术名/产品名），不要泛泛\n"
        f"4. 加入 2026 或 latest 等时间词\n"
        f"5. 【重要】以下主题已经搜过，绝对不要重复：\n{expanded_exclude_text}\n\n"
        f"只输出 JSON 数组：[\"搜索词1\", \"搜索词2\", ...]"
    )
```

### 5.2 Phase 3 搜索完成后也写入 expanded_history

确保跨界搜索的结果也被记录到 expanded_history 中（避免下一轮重复）：

```python
    for query in cross_topics:
        # ... 搜索和存储逻辑 ...
        
        # 记录已搜过（不管成功失败）
        expanded_history.append(query[:50])
```

### 5.3 Phase 2 拓展主题的排除也要更严格

Phase 2 的 `expand_prompt` 中 `expanded_exclude` 只取最近 50 条。如果已经有 200 条历史但最近 50 条不含 "Shoei Opticson"，它还是会重复。改为取全部去重后的列表：

```python
    expanded_exclude = "\n".join(list(set(expanded_history[-200:]))) if expanded_history else "暂无"
```

### 验证

```bash
python -c "
from pathlib import Path
import json

f = Path('.ai-state/night_expanded.json')
if f.exists():
    history = json.loads(f.read_text(encoding='utf-8'))
    unique = set(h[:30] for h in history)
    duplicates = len(history) - len(unique)
    print(f'拓展历史: {len(history)} 条, 去重后 {len(unique)} 条, 重复 {duplicates} 条')
    
    # 检查高频重复
    from collections import Counter
    c = Counter(h[:30] for h in history)
    top_dups = c.most_common(5)
    for item, count in top_dups:
        if count > 1:
            print(f'  重复 {count}x: {item}')
else:
    print('night_expanded.json 不存在')
print('✅ Task 5 完成')
"
```

---

## Task 6: ADAS 维度关键词匹配偏弱（P2）

**问题**: 智驾大陆 PPT 导入了大量 ADAS 内容（AEB、APA、盲区检测），但维度覆盖图里 ADAS 仍然最短。原因是维度关键词匹配不够全。

**修复**: 在 daily_learning.py 的 `target_dimensions` 字典中，扩充 ADAS 关键词列表。

找到 `target_dimensions` 的定义（出现在两处：`_generate_dynamic_topics` 约第 105 行，和 `generate_alignment_report` 约第 856 行），两处都改：

```python
    target_dimensions = {
        "HUD/AR显示": ["HUD", "AR", "光机", "光波导", "Micro OLED", "近眼显示", "waveguide"],
        "4K摄像": ["4K", "摄像", "IMX", "EIS", "防抖", "行车记录", "camera", "dashcam"],
        "ANC/ENC降噪": ["ANC", "ENC", "降噪", "风噪", "通话", "麦克风阵列", "noise cancellation"],
        "ADAS安全": ["ADAS", "盲区", "碰撞预警", "前向预警", "雷达", "AEB", "APA", "RPA",
                     "BSD", "LDW", "FCW", "ACC", "主动安全", "被动安全", "预警",
                     "blind spot", "collision", "emergency braking", "lane departure",
                     "泊车", "避障", "毫米波", "超声波", "USS", "ARAS"],
        "SoC/芯片": ["AR1", "BES2800", "高通", "恒玄", "SoC", "芯片", "Nordic", "nRF",
                     "QCC", "J6", "Orin", "TDA4", "征程", "horizon"],
        "认证标准": ["ECE", "DOT", "3C", "FCC", "CE RED", "UN38.3", "GB 811", "FMVSS",
                    "ENCAP", "CNCAP", "EN 1078", "NTA"],
        "供应商/JDM": ["歌尔", "Goertek", "JDM", "ODM", "供应商", "代工", "立讯", "Luxshare"],
        "Mesh对讲": ["Mesh", "对讲", "自组网", "Sena", "Cardo", "intercom", "DMC"],
        "电池/散热": ["电池", "散热", "热管理", "温控", "mAh", "充电", "thermal"],
        "结构/材料": ["碳纤维", "玻纤", "EPS", "壳体", "模具", "重量", "MIPS", "carbon fiber"]
    }
```

关键变化：ADAS 关键词从 5 个扩充到 20 个，覆盖了 AEB/APA/RPA/BSD/LDW/FCW/ACC/泊车/避障/毫米波/超声波/USS/ARAS 等智驾大陆 PPT 里的高频词。

### 验证

```bash
python -c "
from pathlib import Path
import json

KB_ROOT = Path('.ai-state/knowledge')
# 用新关键词统计 ADAS 覆盖
adas_keywords = ['ADAS', '盲区', '碰撞预警', '前向预警', '雷达', 'AEB', 'APA', 'RPA',
                 'BSD', 'LDW', 'FCW', 'ACC', '主动安全', '预警', 'blind spot',
                 'collision', 'emergency braking', '泊车', '避障', '毫米波', '超声波', 'USS', 'ARAS']
count = 0
for f in KB_ROOT.rglob('*.json'):
    try:
        data = json.loads(f.read_text(encoding='utf-8'))
        text = (data.get('title', '') + ' ' + data.get('content', '')[:200]).lower()
        if any(kw.lower() in text for kw in adas_keywords):
            count += 1
    except:
        continue
print(f'ADAS 维度（新关键词）: {count} 条')
print(f'对比旧统计（日报显示约 100 条），应该大幅增加')
print('✅ Task 6 完成')
"
```

---

## 执行完成后的检查清单

```bash
# 1. 确认所有改动可导入
python -c "from src.tools.tool_registry import get_tool_registry; print('registry OK')"
python -c "from scripts.daily_learning import run_night_deep_learning, auto_schedule_research; print('learning OK')"
python -c "from scripts.feishu_sdk_client import handle_message; print('feishu OK')"

# 2. 确认自主研究已嵌入夜间学习
python -c "
import inspect
from scripts.daily_learning import run_night_deep_learning
source = inspect.getsource(run_night_deep_learning)
print(f'auto_schedule_research 调用: {\"✅\" if \"auto_schedule_research\" in source else \"❌\"}')
print(f'AutoResearch 日志: {\"✅\" if \"AutoResearch\" in source else \"❌\"}')
"

# 3. ADAS 维度新统计
python -c "
from scripts.daily_learning import generate_alignment_report
# 只需确认函数可用，实际报告在飞书发'日报'查看
print('alignment report OK')
"

# 4. 重启服务
```
