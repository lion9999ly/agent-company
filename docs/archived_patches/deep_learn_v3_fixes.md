# 深度学习 v3 修复指令 — overnight_deep_learning_v3.py

> 4 个修复 + 1 个新机制，按顺序执行

---

## 修复 1（P0）: Phase B deep_refine 拆小 — 80% 失败的根因

**根因**: `deep_learn_deep_refine` 任务 max_tokens=4096，深度精炼输出天然超长，截断后 len=0。25 个主题 20 个失败全是 `finish_reason=length`。

**修法**: 深度精炼从一次调用拆成三步，每步输出控制在 ~2000 token 安全区内。

### Step 1: 添加拆步精炼函数

找到 `deep_learn_deep_refine` 的调用位置（Phase B 的核心生成逻辑），替换为以下三步法：

```python
async def _deep_refine_chunked(topic: str, search_data: str, existing_entry: str = "") -> str:
    """
    三步精炼：框架 → 逐段填充 → 合并
    每步 max_tokens <= 2000，避免截断
    """
    
    # === Step 1: 生成框架（要点骨架） ===
    framework_prompt = f"""你是智能骑行头盔领域的高级研究员。
针对主题「{topic}」，基于以下搜索数据，输出一份结构化框架。

要求：
- 列出 3-5 个核心要点（每个要点一行，格式: "## 要点N: 标题"）
- 每个要点下列出需要填充的关键数据项（格式: "- 数据项: [待填充]"）
- 不要展开写正文，只给骨架
- 总输出控制在 500 字以内

搜索数据:
{search_data[:3000]}

{"已有知识条目（需深化而非重复）:" + existing_entry[:1000] if existing_entry else ""}
"""
    
    framework = await _call_llm_for_deep_learn(
        prompt=framework_prompt,
        task_name="deep_refine_framework",
        max_tokens=1500
    )
    
    if not framework:
        print(f"  [DeepRefine] {topic}: 框架生成失败")
        return ""
    
    # === Step 2: 逐要点展开 ===
    # 从框架中提取要点标题
    import re
    sections = re.findall(r'##\s*要点\d+[：:]\s*(.+)', framework)
    if not sections:
        # 兜底：按换行分段
        sections = [line.strip() for line in framework.split('\n') if line.strip() and len(line.strip()) > 5][:5]
    
    filled_sections = []
    for i, section_title in enumerate(sections):
        fill_prompt = f"""你是智能骑行头盔领域的高级研究员。
针对主题「{topic}」的子要点「{section_title}」，基于搜索数据写一段详细分析。

要求：
- 必须包含具体数字/型号/参数（不能只有定性描述）
- 引用数据时标注来源
- 输出 200-400 字
- 直接输出正文，不要重复标题

搜索数据:
{search_data[:3000]}

整体框架（参考上下文）:
{framework[:1000]}
"""
        
        section_content = await _call_llm_for_deep_learn(
            prompt=fill_prompt,
            task_name="deep_refine_fill",
            max_tokens=1500
        )
        
        if section_content:
            filled_sections.append(f"## {section_title}\n{section_content}")
        else:
            print(f"  [DeepRefine] {topic} 要点 {i+1}/{len(sections)} 填充失败，跳过")
    
    if not filled_sections:
        print(f"  [DeepRefine] {topic}: 所有要点填充失败")
        return ""
    
    # === Step 3: 合并成完整条目 ===
    merged = f"# {topic}\n\n" + "\n\n".join(filled_sections)
    
    # 可选：最终做一次精简合并（如果段落间有重复）
    if len(filled_sections) >= 3:
        merge_prompt = f"""将以下分段内容合并为一篇连贯的知识条目。
- 去除重复内容
- 保留所有具体数据和来源
- 输出 800-1500 字
- confidence 标记为 medium

{merged[:4000]}
"""
        final = await _call_llm_for_deep_learn(
            prompt=merge_prompt,
            task_name="deep_refine_merge",
            max_tokens=2000
        )
        if final:
            return final
    
    # 合并失败则直接返回拼接版
    return merged
```

### Step 2: 替换原有调用

找到 Phase B 中调用 `deep_learn_deep_refine` 的地方（大约在 batch 处理循环内），将原有的单次 LLM 调用替换为 `_deep_refine_chunked`：

```python
# 原代码大致:
# result = await _call_llm(..., task_name="deep_learn_deep_refine", max_tokens=4096)

# 改为:
result = await _deep_refine_chunked(
    topic=topic,
    search_data=extracted_data,  # extract 步骤的输出
    existing_entry=existing_kb_entry  # 广度阶段已有的条目（如果有）
)
```

> **注意**: `_call_llm_for_deep_learn` 是占位名，CC 需要对照实际代码中的 LLM 调用函数名适配（可能是 `call_azure`、`call_gemini` 或统一的 `model_gateway` 调用）。关键是每次 `max_tokens <= 2000`。

---

## 修复 2（P1）: 自测前 reload 知识库 + 多实体检索

**根因**: Phase A 写入 108 条新知识后，自测引擎用的是启动时的内存快照，新条目不在检索范围内。同时自测问题涉及多实体比较（"对比 Sena 与 Cardo"），单次检索只命中一个实体。

### Step 1: 自测前强制 reload

找到 Phase A+ 自测入口（约在 `Phase A Done` 之后、`SelfTest` 之前），添加知识库重新加载：

```python
# 在自测开始前加:
print("[SelfTest] Reloading knowledge base to include new entries...")

# 根据实际知识库实现，选择合适的 reload 方式:
# 方案 A: 如果知识库是文件扫描
from src.tools.knowledge_base import KnowledgeBase
kb = KnowledgeBase()  # 重新实例化，扫描最新文件
# 或 kb.reload()  如果有 reload 方法

# 方案 B: 如果知识库有全局单例
import importlib
import src.tools.knowledge_base as kb_module
importlib.reload(kb_module)

# 确保自测的 answer 函数使用 reload 后的实例
```

### Step 2: 多实体分别检索

找到自测回答函数（`self_test_answer` 调用 LLM 前的知识库检索逻辑）：

```python
def _retrieve_for_test(question: str, kb) -> str:
    """
    从问题中提取多个实体，分别检索，合并结果
    """
    import re
    
    # 提取品牌/产品名（中英文）
    brands = re.findall(
        r'(?:Sena|Cardo|Forcite|LIVALL|CrossHelmet|EyeRide|Shoei|AGV|HJC|Arai|'
        r'Strava|Relive|Rever|'
        r'ECE|DOT|FCC|CE-RED|UN38\.3|Snell|FIM|GB 811|3C|'
        r'LCoS|DLP|MicroLED|BLE|WiFi|UWB|'
        r'歌尔|立讯|闻泰|龙旗|舜宇|丘钛|欧菲)',
        question,
        re.IGNORECASE
    )
    
    # 提取关键词
    keywords = re.findall(
        r'(?:HUD|OTA|ADAS|ANC|BOM|NRE|V2X|CAN|GATT|'
        r'头盔|认证|电池|充电|语音|摄像|脑图|氛围灯|按键|配对|'
        r'成本|价格|市场|渠道|用户|骑行|拆解)',
        question,
        re.IGNORECASE
    )
    
    all_terms = list(set(brands + keywords))
    
    if not all_terms:
        # 兜底：用原始问题检索
        return kb.search(question, top_k=10)
    
    # 每个实体/关键词分别检索 top 3，合并去重
    all_results = []
    seen_ids = set()
    
    for term in all_terms[:8]:  # 最多 8 个词，避免过度检索
        results = kb.search(term, top_k=3)
        if isinstance(results, list):
            for r in results:
                rid = r.get('id') or r.get('title', '')
                if rid not in seen_ids:
                    seen_ids.add(rid)
                    all_results.append(r)
        elif isinstance(results, str) and results not in all_results:
            all_results.append(results)
    
    # 截断到合理长度
    if isinstance(all_results[0], dict) if all_results else False:
        combined = '\n---\n'.join([r.get('content', str(r))[:500] for r in all_results[:15]])
    else:
        combined = '\n---\n'.join([str(r)[:500] for r in all_results[:15]])
    
    return combined
```

在自测 answer 的 LLM 调用前，将原有的知识库检索替换为 `_retrieve_for_test`。

---

## 修复 3（P2）: KB_GUARD 降级噪声 — prompt 默认 medium

**根因**: LLM 总是标 `confidence: high`，KB_GUARD 总是打回到 medium，产生 ~80 条无意义日志。

找到 Phase A 广度精炼的 prompt（`deep_learn_refine` 任务的 system/user prompt），添加一行指令：

```python
# 在 refine prompt 中找到关于 confidence 的说明，改为:

# 原文可能类似:
# "confidence: 标记置信度（high/medium/low）"

# 改为:
# "confidence: 标记置信度。除非数据直接来自官方文档/datasheet 原文且你100%确认，否则一律标 medium。标 high 会被系统自动降级，不要浪费。low 用于纯推测内容。"
```

同时在 Phase B 的 deep_refine prompt 中也做同样修改。

---

## 修复 4（P2）: 自测选题逻辑修正

在修复 2 生效后，自测分数会大幅提升，深挖选题自然更精准。但为了防御性，在深挖主题选择逻辑中加一个过滤：

```python
# 找到 Phase B 主题选择的位置（[DeepDive] Selected 25 topics...）
# 在选择逻辑中加一个规则:

# 如果自测平均分 < 3.0，说明自测本身可能有问题（假阴性），
# 不完全依赖自测结果，改为混合策略：
if self_test_avg_score < 3.0:
    print(f"  [DeepDive] 自测平均分 {self_test_avg_score} 过低，可能是检索问题，采用混合选题策略")
    # 50% 来自自测失败题（仍可能有真盲区）
    from_test = failed_topics[:12]
    # 50% 来自广度阶段标记为 shallow/speculative 的条目（确定需要深挖的）
    from_quality = [t for t in breadth_results if t.get('quality') in ('shallow', 'speculative')]
    from_quality = sorted(from_quality, key=lambda x: x.get('score', 0), reverse=True)[:13]
    deep_dive_topics = from_test + from_quality
else:
    # 正常逻辑
    deep_dive_topics = selected_from_test[:25]
```

---

## 新机制: 自动撑满目标时长（自驱加活）

**需求**: 系统应检测"结束太快"，自动给自己加任务，填满目标运行时长。

### 设计思路

在 `overnight_deep_learning_v3.py` 的主函数末尾，添加一个"续命循环"：

```python
import time
from datetime import datetime, timedelta

# === 在文件顶部或 main 函数开头添加目标时长参数 ===
DEFAULT_TARGET_HOURS = 7.0  # 默认目标运行时长

def _generate_extension_topics(kb, existing_topics: set, count: int = 30) -> list:
    """
    基于当前知识库的薄弱环节，自动生成延伸学习主题
    """
    extension_strategies = [
        {
            "name": "竞品纵深",
            "prompt": """基于以下已有知识主题列表，找出尚未覆盖的竞品分析角度。
重点关注：
1. 已有品牌（Sena/Cardo/LIVALL/Forcite/CrossHelmet）的未覆盖维度（售后/定价/渠道/用户评价）
2. 尚未研究的竞品品牌（Ruroc/Bell/Schuberth/Nolan 的智能化尝试）
3. 跨行业参考（滑雪头盔/自行车头盔/工业安全帽的智能化）

输出 {count} 个具体研究主题，每行一个，不要编号。"""
        },
        {
            "name": "技术深挖",
            "prompt": """基于以下已有知识主题列表，找出技术领域的盲区。
重点关注：
1. 已有技术条目中提到但未展开的子技术（如"BLE GATT"提到了但没有详细协议设计）
2. 产品目标要求但知识库尚未覆盖的技术（4G/5G蜂窝、疲劳检测、全彩HUD、可换电池）
3. 制造工艺细节（注塑/喷涂/装配/检测工序）

输出 {count} 个具体研究主题，每行一个，不要编号。"""
        },
        {
            "name": "用户场景",
            "prompt": """基于以下已有知识主题列表，找出用户研究和场景设计的盲区。
重点关注：
1. 极端场景（暴雨/夜间/隧道/高原/严寒）下的产品行为
2. 特殊用户群体（女性骑手/新手/外卖骑手/赛道用户）
3. 用户旅程中未覆盖的环节（购买决策/开箱/学习曲线/维修/二手转卖）

输出 {count} 个具体研究主题，每行一个，不要编号。"""
        }
    ]
    
    # 获取现有知识主题列表（用于去重和找盲区）
    existing_titles = '\n'.join(list(existing_topics)[:200])
    
    all_new_topics = []
    for strategy in extension_strategies:
        prompt = strategy["prompt"].format(count=count // 3 + 1)
        prompt += f"\n\n已有主题列表:\n{existing_titles}"
        
        try:
            response = call_llm(  # 用实际的 LLM 调用函数名
                prompt=prompt,
                task_name="generate_extension_topics",
                max_tokens=1500
            )
            if response:
                topics = [line.strip() for line in response.split('\n') if line.strip() and len(line.strip()) > 5]
                # 去重
                topics = [t for t in topics if t not in existing_topics]
                all_new_topics.extend(topics)
                print(f"  [AutoExtend] {strategy['name']}: 生成 {len(topics)} 个新主题")
        except Exception as e:
            print(f"  [AutoExtend] {strategy['name']} 生成失败: {e}")
    
    return all_new_topics[:count]


# === 在 main 函数的最后（Phase B 完成之后），添加续命循环 ===

async def _auto_extend_loop(start_time: datetime, target_hours: float, kb, existing_topics: set):
    """
    检测是否提前完成，自动加活填满目标时长
    """
    elapsed = (datetime.now() - start_time).total_seconds() / 3600
    remaining_hours = target_hours - elapsed
    
    if remaining_hours < 0.5:
        print(f"[AutoExtend] 已用时 {elapsed:.1f}h，目标 {target_hours}h，无需延长")
        return
    
    print(f"\n{'='*60}")
    print(f"[AutoExtend] 提前完成！已用 {elapsed:.1f}h / 目标 {target_hours}h")
    print(f"[AutoExtend] 剩余 {remaining_hours:.1f}h，自动生成延伸学习任务")
    print(f"{'='*60}\n")
    
    # 通知飞书
    await notify_feishu(
        f"⏰ 提前完成 ({elapsed:.1f}h/{target_hours}h)，"
        f"自动启动延伸学习，剩余 {remaining_hours:.1f}h"
    )
    
    round_num = 0
    
    while True:
        # 检查剩余时间
        elapsed = (datetime.now() - start_time).total_seconds() / 3600
        remaining_hours = target_hours - elapsed
        
        if remaining_hours < 0.3:  # 少于 18 分钟就收工
            print(f"[AutoExtend] 剩余 {remaining_hours:.1f}h < 0.3h，收工")
            break
        
        round_num += 1
        print(f"\n[AutoExtend] === Round {round_num} (剩余 {remaining_hours:.1f}h) ===")
        
        # 动态决定本轮主题数量（根据剩余时间）
        # 每个主题约 2 分钟（搜索+精炼），取保守估计
        topics_this_round = min(30, max(10, int(remaining_hours * 20)))
        
        # 生成延伸主题
        new_topics = _generate_extension_topics(kb, existing_topics, count=topics_this_round)
        
        if not new_topics:
            print(f"[AutoExtend] 无法生成更多主题，结束")
            break
        
        print(f"[AutoExtend] 本轮 {len(new_topics)} 个主题")
        await notify_feishu(
            f"🔄 延伸学习 Round {round_num}: {len(new_topics)} 个主题 "
            f"(剩余 {remaining_hours:.1f}h)"
        )
        
        # 复用 Phase A 的广度扫描流程
        added = 0
        for i, topic in enumerate(new_topics):
            # 时间保护
            elapsed = (datetime.now() - start_time).total_seconds() / 3600
            if target_hours - elapsed < 0.2:
                print(f"[AutoExtend] 时间到，停止")
                break
            
            try:
                # 复用已有的搜索+精炼流程
                result = await _breadth_scan_one(topic)  # 用实际函数名
                if result and result.get('status') == 'ok':
                    added += 1
                    existing_topics.add(topic)
            except Exception as e:
                print(f"  [AutoExtend] {topic}: {e}")
            
            # 每 10 个主题输出心跳
            if (i + 1) % 10 == 0:
                elapsed = (datetime.now() - start_time).total_seconds() / 3600
                print(f"  [AutoExtend] 进度 {i+1}/{len(new_topics)}，已用时 {elapsed:.1f}h")
        
        print(f"[AutoExtend] Round {round_num} 完成: +{added} 条")
        await notify_feishu(f"✅ 延伸 Round {round_num}: +{added} 条知识")
        
        # 每 2 轮做一次自测（检验延伸学习效果）
        if round_num % 2 == 0:
            print(f"[AutoExtend] 中间自测...")
            # 复用自测流程
            # reload kb
            # run self_test
            # report
        
        # 再次检查时间
        elapsed = (datetime.now() - start_time).total_seconds() / 3600
        if target_hours - elapsed < 0.3:
            break
    
    # 最终汇报
    elapsed = (datetime.now() - start_time).total_seconds() / 3600
    kb_count = len(kb)  # 用实际方法获取知识库总数
    await notify_feishu(
        f"🏁 深度学习 v3 + 延伸学习全部完成\n"
        f"总用时: {elapsed:.1f}h / 目标 {target_hours}h\n"
        f"延伸轮次: {round_num}\n"
        f"知识库: {kb_count} 条"
    )


# === 在 main() 的最后调用 ===
# 在 "Deep Learning v3 Complete" 打印之前，插入:

start_time = ...  # 应该在 main 开头就记录了启动时间
target_hours = getattr(args, 'target_hours', DEFAULT_TARGET_HOURS)

# 收集已有主题（用于去重）
existing_topics = set()  # 从已处理的主题列表中收集
# existing_topics.update(breadth_topics)
# existing_topics.update(deep_dive_topics)

await _auto_extend_loop(
    start_time=start_time,
    target_hours=target_hours,
    kb=kb,
    existing_topics=existing_topics
)
```

### 启动方式增加目标时长参数

在 argparse 部分添加：

```python
parser.add_argument('--target-hours', type=float, default=7.0,
                    help='目标运行时长（小时），提前完成会自动加活')
```

使用：
```bash
# 默认 7 小时
python scripts/overnight_deep_learning_v3.py --all

# 指定时长
python scripts/overnight_deep_learning_v3.py --all --target-hours 6.5
```

---

## 验证清单

修完后启动一次短时测试验证核心修复：

```bash
python scripts/overnight_deep_learning_v3.py --all --target-hours 0.5
```

检查：
- [ ] Phase B 成功率 > 60%（之前 20%），不再出现连续 `finish_reason=length`
- [ ] 自测分数 > 5.0/10（之前 1.8），"Knowledge base missing" 明显减少
- [ ] KB_GUARD 降级日志大幅减少（之前 ~80 次）
- [ ] 提前完成后触发 `[AutoExtend]` 续命循环
- [ ] 飞书收到延伸学习通知
- [ ] 知识库条目持续增长直到目标时长

---

## 架构说明

```
启动
  │
  ├── Phase A: 广度扫描 (原有)
  │     └── 109 topics, 4路并行搜索 + 串行精炼
  │
  ├── Phase A+: 自测 (修复: reload KB + 多实体检索)
  │     └── 15 题，分数应从 1.8 提升到 5+
  │
  ├── Phase B: 精准深挖 (修复: 三步精炼替代单次调用)
  │     └── 25 topics, 成功率应从 20% 提升到 60%+
  │
  └── Phase C [新]: 自动延伸 (撑满目标时长)
        ├── 检查剩余时间
        ├── 自动生成新主题（竞品纵深/技术深挖/用户场景 三策略轮转）
        ├── 复用 Phase A 的搜索+精炼流程
        ├── 每 2 轮自测一次
        └── 循环直到目标时长 - 0.3h
```
