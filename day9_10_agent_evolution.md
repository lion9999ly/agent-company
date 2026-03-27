# Day 9-10 Agent 进化 — 从执行者到合伙人

> 生成时间: 2026-03-24
> 依赖: router.py (LangGraph 状态机), daily_learning.py, feishu_sdk_client.py
> 执行顺序: Task 1 → 2 → 3，每个完成后跑验证

---

## Task 1: 研发任务增加"主动建议"（9b）

**目标**: 研发任务完成后，除了回答用户的问题，CPO 额外输出一段主动建议——"基于这次研究，我还建议你关注 XXX"。

### 1.1 修改 cpo_synthesis 节点

在 router.py 的 `cpo_synthesis` 函数中（约第 762 行），在 CPO 整合成功后，让它额外生成一段"主动建议"。

找到这段代码：
```python
result = gateway.call_azure_openai("cpo", merge_summary[:8000], system_prompt, "synthesis")
synthesis = result["response"] if result.get("success") else merge_summary
```

在其后面添加主动建议生成：

```python
    # === Agent 主动建议：不只回答问题，还要提出用户没想到的方向 ===
    proactive_advice = ""
    if result.get("success") and len(synthesis) > 500:
        task_goal = state.get("task_contract", {}).get("task_goal", "")
        
        advice_prompt = (
            f"你是智能摩托车全盔项目的产品 VP（CPO），刚刚完成了一个研发任务的整合。\n\n"
            f"## 用户的原始任务\n{task_goal}\n\n"
            f"## 你的整合结论（摘要）\n{synthesis[:2000]}\n\n"
            f"## 你的任务\n"
            f"基于这次研究的结论，作为合伙人级别的 CPO，你需要主动提出 2-3 条用户可能没想到但确实值得关注的建议。\n\n"
            f"要求：\n"
            f"1. 每条建议要具体可执行（不要泛泛而谈'建议深入研究'）\n"
            f"2. 至少一条是跨领域关联（例如：'这个方案的散热问题会影响电池寿命，建议同步评估'）\n"
            f"3. 如果发现知识库在某个方向信息不够，直接说'我今晚会自动补充 XXX 方面的研究'\n"
            f"4. 如果某个结论和之前的研究有矛盾，指出来\n"
            f"5. 控制在 200 字以内\n\n"
            f"输出格式：\n"
            f"💡 合伙人建议：\n"
            f"1. ...\n"
            f"2. ...\n"
            f"3. ..."
        )
        
        advice_result = gateway.call_azure_openai("cpo", advice_prompt, 
            "你是产品VP，输出简洁的主动建议。", "proactive_advice")
        
        if advice_result.get("success"):
            proactive_advice = advice_result["response"].strip()
            print(f"[CPO_Synthesis] 主动建议: {len(proactive_advice)} 字")
    
    # 将主动建议附加到 synthesis 末尾
    if proactive_advice:
        synthesis = synthesis + "\n\n---\n" + proactive_advice
```

### 1.2 让主动建议中的"知识缺口"自动触发补充

在主动建议生成后，提取其中提到的知识缺口，写入一个待研究队列：

```python
    # === 主动建议中的知识缺口 → 写入待研究队列 ===
    if proactive_advice and ("今晚" in proactive_advice or "补充" in proactive_advice or "研究" in proactive_advice):
        try:
            gap_file = ROOT_DIR / ".ai-state" / "auto_research_queue.json"
            existing = []
            if gap_file.exists():
                existing = json.loads(gap_file.read_text(encoding="utf-8"))
            
            existing.append({
                "source": "proactive_advice",
                "task_goal": task_goal[:100],
                "advice": proactive_advice[:500],
                "created": datetime.now().isoformat()
            })
            
            # 只保留最近 20 条
            gap_file.write_text(json.dumps(existing[-20:], ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[CPO_Synthesis] 知识缺口已加入研究队列")
        except Exception as e:
            print(f"[CPO_Synthesis] 队列写入失败: {e}")
```

### 1.3 夜间自动研究读取队列

在 daily_learning.py 的 `auto_schedule_research` 函数开头，添加从队列读取待研究主题：

```python
def auto_schedule_research(alignment_report: str, progress_callback=None) -> str:
    """基于对齐报告 + 主动建议队列，自动发起深度研究"""
    from src.utils.model_gateway import get_model_gateway
    
    gateway = get_model_gateway()
    
    # === 读取主动建议中的知识缺口队列 ===
    queue_context = ""
    queue_file = Path(__file__).parent.parent / ".ai-state" / "auto_research_queue.json"
    if queue_file.exists():
        try:
            queue = json.loads(queue_file.read_text(encoding="utf-8"))
            if queue:
                queue_context = "\n\n## 研发任务中发现的知识缺口（优先研究）\n"
                for item in queue[-5:]:
                    queue_context += f"- 来自任务「{item.get('task_goal', '')[:50]}」: {item.get('advice', '')[:200]}\n"
                # 读完清空
                queue_file.write_text("[]", encoding="utf-8")
        except:
            pass
    
    # 让 LLM 从对齐报告 + 队列中提取可执行的研究任务
    extract_prompt = (
        f"以下是今日的对齐报告和研发任务中发现的知识缺口。请提取 2-3 个最值得深入研究的具体主题。\n"
        f"要求：\n"
        f"1. 优先处理知识缺口队列中的主题\n"
        f"2. 必须围绕摩托车智能全盔\n"
        f"3. 搜索词具体（含品牌/型号/技术名）\n\n"
        f"输出 JSON 数组：\n"
        f'[{{"title": "研究主题", "goal": "要回答的核心问题", '
        f'"searches": ["搜索词1", "搜索词2", "搜索词3", "搜索词4"]}}]\n\n'
        f"对齐报告：\n{alignment_report[:2000]}"
        f"{queue_context}"
    )
    
    # ... 后续逻辑不变 ...
```

### 1.4 验证

```bash
python -c "
from src.graph.router import cpo_synthesis
print('cpo_synthesis 可导入')
from pathlib import Path
queue = Path('.ai-state/auto_research_queue.json')
queue.parent.mkdir(parents=True, exist_ok=True)
if not queue.exists():
    queue.write_text('[]', encoding='utf-8')
print(f'研究队列: {queue.exists()}')
print('✅ Task 1 完成')
"
```

---

## Task 2: 经验卡片驱动进化（9c）

**目标**: 用户评价 A/B/C/D 不只是记录，要实际影响 Agent 行为。D → 分析失败原因写入教训，A → 提取成功模式强化。

### 2.1 修改飞书评价处理逻辑

找到 feishu_sdk_client.py 中处理用户评价（A/B/C/D回复）的代码，在保存评价后添加进化触发。

搜索位置：
```bash
grep -n "评价\|rating\|A.*可直接使用\|B.*需要小改\|user_rating" scripts/feishu_sdk_client.py | head -20
```

在评价保存成功后添加：

```python
    # === 评价驱动进化 ===
    if rating in ("C", "D"):
        # 差评 → 自动分析失败原因，写入经验教训
        import threading
        def _analyze_failure():
            try:
                from src.utils.model_gateway import get_model_gateway
                from src.tools.knowledge_base import add_knowledge
                
                gw = get_model_gateway()
                task_goal = record.get("task_goal", "")
                synthesis = record.get("synthesis_output", "")
                user_feedback = feedback_text if feedback_text else f"用户评价{rating}"
                
                analysis_prompt = (
                    f"一个研发任务收到了差评（{rating}）。请分析失败原因并提取教训。\n\n"
                    f"## 任务目标\n{task_goal}\n\n"
                    f"## Agent 输出（摘要）\n{synthesis[:2000]}\n\n"
                    f"## 用户反馈\n{user_feedback}\n\n"
                    f"请输出：\n"
                    f"1. 失败根因（一句话）\n"
                    f"2. Agent 哪个环节出了问题（CPO规划/CTO技术/CMO市场/Critic评审/知识库不足）\n"
                    f"3. 下次遇到类似任务应该怎么做\n"
                    f"4. 需要补充什么知识\n"
                    f"控制在 300 字以内。"
                )
                
                result = gw.call_azure_openai("cpo", analysis_prompt, "你是质量分析师。", "failure_analysis")
                
                if result.get("success"):
                    # 写入知识库作为经验教训
                    add_knowledge(
                        title=f"[教训] {task_goal[:40]}（评价{rating}）",
                        domain="lessons",
                        content=result["response"],
                        tags=["evolution", "failure", f"rating_{rating.lower()}"],
                        source="user_feedback_analysis",
                        confidence="high"
                    )
                    print(f"[Evolution] 差评分析完成，已写入知识库")
                    
                    # 通知用户
                    send_reply(open_id, f"🔍 已分析任务失败原因并记录为经验教训，下次类似任务会注意。")
            except Exception as e:
                print(f"[Evolution] 差评分析失败: {e}")
        
        threading.Thread(target=_analyze_failure, daemon=True).start()
    
    elif rating == "A":
        # 好评 → 提取成功模式
        import threading
        def _extract_success():
            try:
                from src.utils.model_gateway import get_model_gateway
                from src.tools.knowledge_base import add_knowledge
                
                gw = get_model_gateway()
                task_goal = record.get("task_goal", "")
                synthesis = record.get("synthesis_output", "")
                
                success_prompt = (
                    f"一个研发任务收到了满分评价（A）。请提取成功模式。\n\n"
                    f"## 任务目标\n{task_goal}\n\n"
                    f"## Agent 输出（摘要）\n{synthesis[:2000]}\n\n"
                    f"请输出：\n"
                    f"1. 这个任务为什么做得好（一句话）\n"
                    f"2. 哪些做法值得复制到其他任务\n"
                    f"3. 成功的关键因素是什么\n"
                    f"控制在 200 字以内。"
                )
                
                result = gw.call_azure_openai("cpo", success_prompt, "你是质量分析师。", "success_analysis")
                
                if result.get("success"):
                    add_knowledge(
                        title=f"[成功模式] {task_goal[:40]}",
                        domain="lessons",
                        content=result["response"],
                        tags=["evolution", "success", "rating_a"],
                        source="user_feedback_analysis",
                        confidence="high"
                    )
                    print(f"[Evolution] 成功模式提取完成")
            except Exception as e:
                print(f"[Evolution] 成功分析失败: {e}")
        
        threading.Thread(target=_extract_success, daemon=True).start()
```

### 2.2 CPO 规划时读取经验教训

在 router.py 的 `_cpo_generate_plan` 函数中（约第 283 行），在构建 prompt 时注入最近的经验教训。

在 `parts.append(THINKING_PRINCIPLES)` 之后添加：

```python
    # === 注入经验教训：过去失败和成功的经验 ===
    from src.tools.knowledge_base import search_knowledge
    evolution_entries = search_knowledge("教训 成功模式 evolution", limit=5)
    if evolution_entries:
        evolution_text = "\n## 经验教训（过去任务的反馈总结）\n"
        for entry in evolution_entries:
            if "evolution" in entry.get("tags", []):
                evolution_text += f"\n- **{entry['title']}**: {entry['content'][:300]}\n"
        if len(evolution_text) > 50:
            parts.append(evolution_text)
            print(f"[CPO_Plan] 注入 {len(evolution_entries)} 条经验教训")
```

### 2.3 添加飞书查询指令

```python
elif text.strip() in ("进化记录", "evolution", "进化"):
    from src.tools.knowledge_base import search_knowledge
    entries = search_knowledge("evolution 教训 成功模式", limit=10)
    evo_entries = [e for e in entries if "evolution" in e.get("tags", [])]
    
    if not evo_entries:
        send_reply(open_id, "📊 暂无进化记录。给研发任务打 A 或 D 评价后，系统会自动分析并记录。")
    else:
        lines = ["📊 Agent 进化记录\n"]
        for e in evo_entries[:8]:
            tags = e.get("tags", [])
            icon = "✅" if "success" in tags else "❌" if "failure" in tags else "📝"
            lines.append(f"{icon} {e['title']}")
            lines.append(f"   {e['content'][:150]}...\n")
        send_reply(open_id, "\n".join(lines))
```

### 2.4 验证

```bash
python -c "
from src.tools.knowledge_base import search_knowledge, add_knowledge

# 模拟一条经验教训
add_knowledge(
    title='[教训] 测试任务（评价D）',
    domain='lessons',
    content='失败根因：Agent 输出了自行车方案而非摩托车。下次应该检查产品锚点。',
    tags=['evolution', 'failure', 'rating_d'],
    source='user_feedback_analysis',
    confidence='high'
)

# 验证能搜到
results = search_knowledge('evolution 教训', limit=5)
found = any('evolution' in e.get('tags', []) for e in results)
print(f'经验教训入库: {\"✅\" if found else \"❌\"} ({len(results)} 条)')

# 清理测试数据
import json
from pathlib import Path
KB_ROOT = Path('.ai-state/knowledge/lessons')
for f in KB_ROOT.glob('*.json'):
    try:
        data = json.loads(f.read_text(encoding='utf-8'))
        if data.get('title') == '[教训] 测试任务（评价D）':
            f.unlink()
            print('测试数据已清理')
    except:
        continue

print('✅ Task 2 完成')
"
```

---

## Task 3: 强化自主研究质量（9a）

**目标**: auto_schedule_research 产出的研究主题不能太泛，要能找到用户想不到但确实有价值的方向。

### 3.1 改进自主研究的主题提取 prompt

在 daily_learning.py 的 `auto_schedule_research` 函数中，改进 `extract_prompt`，让它不只是从对齐报告提取关键词，而是做交叉分析：

替换 extract_prompt 为：

```python
    extract_prompt = (
        f"你是智能摩托车全盔项目的研究规划师。\n\n"
        f"## 你的任务\n"
        f"基于对齐报告和知识缺口，规划 2-3 个深度研究任务。\n\n"
        f"## 规划原则\n"
        f"1. 不要选太泛的主题（如'智能头盔市场分析'），要选具体到可以搜到数据的（如'高通AR1 vs 恒玄BES2800 功耗对比'）\n"
        f"2. 至少一个主题应该是'跨领域关联'——从别的行业借鉴（如'汽车ADAS供应商向摩托车迁移的案例'）\n"
        f"3. 优先填补知识缺口队列中的空白\n"
        f"4. 搜索词要能搜到英文 datasheet 和中文行业报告（各一半）\n\n"
        f"## 输出格式\n"
        f"JSON 数组，每个元素：\n"
        f'{{"title": "具体主题（含品牌/型号）", '
        f'"goal": "这个研究要回答的一个核心问题", '
        f'"searches": ["英文搜索词1", "中文搜索词2", "英文搜索词3", "中文搜索词4"]}}\n\n'
        f"## 对齐报告\n{alignment_report[:2000]}"
        f"{queue_context}"
    )
```

### 3.2 自主研究完成后自动评估质量

在 `auto_schedule_research` 的每个研究任务完成后，添加自评：

```python
        try:
            report = deep_research_one(task_dict, progress_callback=progress_callback)
            
            # === 自评研究质量 ===
            quality_check = gateway.call_azure_openai("cpo",
                f"以下研究报告是否有价值？标准：包含具体数据（型号/参数/价格）、有明确结论、能帮助决策。\n"
                f"只回答 HIGH/MEDIUM/LOW 和一句话理由。\n\n{report[:3000]}",
                "只输出 HIGH/MEDIUM/LOW 和理由。", "auto_research_quality")
            
            quality = "?"
            if quality_check.get("success"):
                resp = quality_check["response"].strip().upper()
                if "HIGH" in resp:
                    quality = "HIGH"
                elif "LOW" in resp:
                    quality = "LOW"
                else:
                    quality = "MEDIUM"
            
            report_lines.append(f"  ✅ {task_dict['title'][:40]} ({len(report)}字, 质量:{quality})")
        except Exception as e:
            report_lines.append(f"  ❌ {task_dict['title'][:40]}: {e}")
```

### 3.3 验证

```bash
python -c "
from scripts.daily_learning import auto_schedule_research
# 仅验证函数可导入，不实际执行
print('auto_schedule_research 可导入')
print('✅ Task 3 完成')
"
```

---

## 执行完成后的检查清单

```bash
# 1. 确认所有改动可导入
python -c "from src.graph.router import app; print('router OK')"
python -c "from scripts.daily_learning import auto_schedule_research; print('learning OK')"
python -c "from scripts.feishu_sdk_client import *; print('feishu OK')"

# 2. 确认研究队列文件存在
python -c "
from pathlib import Path
q = Path('.ai-state/auto_research_queue.json')
q.parent.mkdir(parents=True, exist_ok=True)
if not q.exists(): q.write_text('[]', encoding='utf-8')
print(f'队列: {q.exists()}')
"

# 3. 重启服务
# 然后在飞书测试：
#   发一条研发任务 → 观察回复末尾是否有"💡 合伙人建议"
#   给任务打 D 评价 → 观察是否触发失败分析
#   发"进化记录" → 查看进化日志
```

---

## 新增飞书指令汇总（Day 9-10）

| 指令 | 功能 |
|------|------|
| 进化记录 / evolution | 查看 Agent 从用户评价中学到的教训和成功模式 |

## 系统行为变化汇总

| 场景 | 之前 | 之后 |
|------|------|------|
| 研发任务完成 | 只输出方案 | 方案 + 💡合伙人建议 |
| 用户评价 D | 记录评分，无后续 | 自动分析失败原因 → 写入知识库 → 下次规划时注入 |
| 用户评价 A | 记录评分，无后续 | 提取成功模式 → 写入知识库 → 强化类似任务 |
| 夜间自动研究 | 只看对齐报告 | 对齐报告 + 主动建议中的知识缺口一起看 |
| CPO 规划 | 读知识库 + 记忆 | 知识库 + 记忆 + 经验教训 |
