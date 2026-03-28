# Day 12 批次 2：Critic 升级 + daily_learning 三合一 + 进度心跳 + 完成提示音

> 和 prd_complete_evolution.md 不冲突，可以同时执行
> 改 4 个文件：agent_prompts.yaml / daily_learning.py / tonight_deep_research.py / router.py

---

## 1. Critic 质疑能力升级

当前 Critic 只输出 PASS/REJECT + 简单评语。升级为基于知识库硬数据指出具体矛盾。

### 1.1 修改 src/config/agent_prompts.yaml

找到 critic 的 prompt 部分，替换为：

```yaml
critic:
  system: |
    你是智能骑行头盔项目的技术评审专家（Critic）。
    你的职责不是简单说 PASS 或 REJECT，而是用硬数据指出具体问题。

    评审规则：
    1. 每条评审意见必须引用知识库中的具体数据作为依据
    2. 发现矛盾时，格式为：「[矛盾] XXX 方案建议 A，但知识库显示 B，两者冲突因为 C」
    3. 发现缺失时，格式为：「[缺失] XXX 方案未提及 Y，但根据知识库 Z 数据，Y 是关键约束」
    4. 确认合理时，格式为：「[确认] XXX 方案合理，知识库数据 Y 支持该结论」
    5. 不要笼统说"建议加强"，要说具体加强什么、参考什么数据、目标值多少
    
    评审维度：
    - 技术可行性：方案参数是否在知识库已有芯片/传感器/模组的能力范围内
    - 成本合理性：BOM 估算是否与知识库供应链数据一致
    - 认证合规：方案是否满足知识库中的 ECE/DOT/GB 等认证要求
    - 功耗预算：方案功耗是否在知识库电池容量和续航目标范围内
    - 竞品对标：方案指标是否对标或超越知识库中的竞品数据
    
    输出格式：
    ## 评审结论：PASS / CONDITIONAL_PASS / REJECT
    
    ## 具体问题（按严重程度排序）
    1. [矛盾/缺失/风险] 具体描述...
    2. ...
    
    ## 确认项
    1. [确认] 合理的部分...
    
    ## 建议改进（如果 CONDITIONAL_PASS 或 REJECT）
    1. 具体改进建议，含目标数值和知识库依据
```

### 1.2 修改 src/graph/router.py 中的 critic 节点

找到 critic 节点的代码（grep "critic" router.py），确认：

1. critic 调用前要先搜索知识库获取相关数据作为上下文
2. 把知识库上下文一起传给 critic

```python
# 在 critic 节点函数中，调用 LLM 前加知识库查询：
    
    from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt
    
    # 从待审内容中提取关键词搜索知识库
    review_text = state.get("cpo_synthesis", "") or state.get("cto_output", "")
    
    # 搜索相关知识作为评审依据
    kb_queries = []
    # 提取关键技术词
    import re
    tech_terms = re.findall(r'[A-Z]{2,}\d{2,}|AR[12]|QCC\d|BES\d|IMX\d|ECE|DOT|GB\s*\d+', review_text)
    for term in tech_terms[:5]:
        kb_queries.append(term)
    
    # 通用查询
    kb_queries.extend(["BOM 成本", "功耗预算 续航", "认证 标准"])
    
    critic_kb_context = ""
    for q in kb_queries[:8]:
        entries = search_knowledge(q, limit=2)
        if entries:
            critic_kb_context += format_knowledge_for_prompt(entries)[:1000] + "\n"
    
    critic_kb_context = critic_kb_context[:4000]
    
    # 注入到 critic 的 user prompt 中
    critic_prompt = (
        f"请评审以下研发产出：\n\n"
        f"{review_text[:3000]}\n\n"
        f"## 评审依据（知识库数据）\n"
        f"{critic_kb_context}\n\n"
        f"基于以上知识库数据进行评审。"
    )
```

### 1.3 修改哈希后提交

```bash
# 如果改了 agent_prompts.yaml，必须更新 snapshot_hashes.json
python -c "
import hashlib, json
from pathlib import Path
root = Path('.')
hashes = {}
for f in (root / '.ai-architecture').glob('*.md'):
    hashes[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
for f in (root / 'src' / 'config').glob('*.yaml'):
    hashes[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
(root / '.ai-state' / 'snapshot_hashes.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
print(f'已更新 {len(hashes)} 个哈希')
"
git add .ai-state/snapshot_hashes.json src/config/agent_prompts.yaml
git commit --no-verify -m "Critic 质疑能力升级：基于知识库硬数据评审"
```

---

## 2. daily_learning.py 三合一改动

三个改动合到一次修改中：并行化 + 自测嵌入 + 进度心跳

### 2.1 搜索改 4 路并行

找到 daily_learning.py 中每轮学习的搜索逻辑（可能是 `_learn_one_topic` 或类似函数），把串行搜索改为并行：

```python
# 找到搜索和提炼的主循环，改为两阶段

def run_learning_round(topics, notify_func=None):
    """一轮学习：并行搜索 + 串行提炼"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    registry = get_tool_registry()
    gateway = get_model_gateway()
    
    # 阶段 A：并行搜索（4 路）
    print(f"  [搜索] {len(topics)} 个主题，4 路并行...")
    search_results = []
    
    def _search_one(topic):
        title = topic if isinstance(topic, str) else topic.get("title", "")
        queries = topic.get("searches", [title]) if isinstance(topic, dict) else [title]
        
        search_data = ""
        for q in queries[:3]:
            result = registry.call("deep_research", q)
            if result.get("success") and len(result.get("data", "")) > 200:
                search_data += result["data"][:3000] + "\n---\n"
        
        return {"topic": topic, "title": title, "search_data": search_data}
    
    done_count = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_search_one, t): t for t in topics}
        for f in as_completed(futs):
            search_results.append(f.result())
            done_count += 1
            # 进度心跳（改动 2.3）
            if done_count % 5 == 0:
                print(f"  [搜索进度] {done_count}/{len(topics)}")
    
    print(f"  [搜索完成] {len(search_results)}/{len(topics)}")
    
    # 阶段 B：串行提炼
    added = 0
    skipped = 0
    for i, item in enumerate(search_results, 1):
        # ... 原有的提炼逻辑 ...
        # 每完成 10 条打日志
        if i % 10 == 0:
            print(f"  [提炼进度] {i}/{len(search_results)}，已入库 {added}")
    
    return {"added": added, "skipped": skipped}
```

注意：daily_learning.py 的具体结构可能和上面不完全一样。核心改动是：
1. 找到搜索循环（for topic in topics → search）
2. 改为 ThreadPoolExecutor 并行搜索
3. 保持提炼串行

先 grep 确认实际结构：
```bash
grep -n "def.*learn\|for.*topic\|search\|registry.call\|deep_research" scripts/daily_learning.py | head -30
```

### 2.2 嵌入自测闭环（每 3 轮自测 5 题）

在 daily_learning.py 的学习主循环中，找到每轮结束的位置，追加：

```python
    # === 自测闭环：每 3 轮学习后做一次自测 ===
    if not hasattr(sys.modules[__name__], '_learn_round_count'):
        sys.modules[__name__]._learn_round_count = 0
    sys.modules[__name__]._learn_round_count += 1
    round_count = sys.modules[__name__]._learn_round_count
    
    if round_count % 3 == 0:
        try:
            from scripts.self_test import run_self_test, auto_deep_dive_weak_areas
            
            print(f"\n[SelfTest] 第 {round_count} 轮，触发自测...")
            test_result = run_self_test(count=5)
            
            if test_result["avg_score"] < 6 and test_result["weak_areas"]:
                print(f"[SelfTest] 平均分 {test_result['avg_score']}/10，自动深挖 {len(test_result['weak_areas'][:3])} 个薄弱点")
                auto_deep_dive_weak_areas(test_result["weak_areas"][:3])
            else:
                print(f"[SelfTest] 平均分 {test_result['avg_score']}/10，暂不深挖")
        except Exception as e:
            print(f"[SelfTest] 异常: {e}")
```

### 2.3 长任务进度心跳

已在 2.1 中嵌入（搜索每 5 条打日志，提炼每 10 条打日志）。

额外：在飞书推送中加进度信息。找到 daily_learning.py 中推送飞书的函数，确认每轮完成后推送包含进度：

```python
    # 找到推送飞书的位置，确认推送格式包含进度
    if notify_func:
        try:
            notify_func(
                f"📚 学习轮次 #{round_count} 完成\n"
                f"入库: {added} | 跳过: {skipped} | 知识库: {get_knowledge_stats_total()}\n"
                f"{'🧪 自测: ' + str(test_result['avg_score']) + '/10' if round_count % 3 == 0 else ''}"
            )
        except:
            pass
```

---

## 3. tonight_deep_research.py 进度心跳

找到 tonight_deep_research.py 中多 Agent 研究的主循环，加进度推送：

```bash
grep -n "def.*research\|for.*topic\|notify\|send_reply\|飞书" scripts/tonight_deep_research.py | head -20
```

在搜索并行过程中加心跳：

```python
    # 在并行搜索的 as_completed 循环中
    done_count = 0
    for f in as_completed(futs):
        done_count += 1
        # 每 10 条搜索完成打日志
        if done_count % 10 == 0:
            print(f"  [搜索心跳] {done_count}/{total}")
        # 每 50 条推飞书
        if done_count % 50 == 0 and notify_func:
            try:
                notify_func(f"🔬 深度研究进度: {done_count}/{total} 搜索完成")
            except:
                pass
```

---

## 4. CC 任务完成提示音

这个最简单。在 CC 完成任务时播放提示音。

方案：CC 执行的每个任务脚本末尾加一行系统提示音：

Windows:
```python
import winsound
winsound.Beep(1000, 500)  # 1000Hz, 500ms
```

或更通用的：
```python
print('\a')  # ASCII bell
```

但更好的方式是在 CC 的 task runner 层面加，而不是每个脚本里加。

如果 CC 没有统一的 task runner，那在以下脚本的末尾加 `print('\a')`：
- daily_learning.py 每轮结束
- tonight_deep_research.py 任务结束
- overnight_deep_learning_v3.py 任务结束

```python
# 在各脚本的最终输出后加：
try:
    import platform
    if platform.system() == "Windows":
        import winsound
        winsound.Beep(1000, 300)
        winsound.Beep(1200, 300)
    else:
        print('\a')
except:
    print('\a')
```

---

## 验证

```bash
# 1. Critic prompt 更新
grep -c "矛盾\|缺失\|确认\|知识库" src/config/agent_prompts.yaml

# 2. daily_learning 并行化
grep -c "ThreadPoolExecutor\|并行" scripts/daily_learning.py

# 3. 自测嵌入
grep -c "self_test\|SelfTest" scripts/daily_learning.py

# 4. 进度心跳
grep -c "心跳\|进度\|done_count" scripts/daily_learning.py scripts/tonight_deep_research.py

# 5. 提示音
grep -c "winsound\|Beep\|bell" scripts/daily_learning.py scripts/overnight_deep_learning_v3.py
```
