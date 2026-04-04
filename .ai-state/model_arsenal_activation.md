# 模型武器库全面激活方案

> 原则: 有价值更重要，别省 token。21 个模型全部上阵。

---

## 一、深度研究管道：从 6 模型到 14 模型

### Layer 1 搜索：四通道并行（原来双通道）

| 通道 | 模型 | 搜索方向 | 新增？ |
|------|------|---------|--------|
| 英文技术 | o3-deep-research | 技术论文/专利/厂商数据 | 已有 |
| 中文互联网 | doubao-seed-pro | 小红书/B站/知乎 | 已有 |
| 社交实时 | **grok-4** | X/Twitter/行业动态/KOL | **新增** |
| 学术深挖 | **gemini-deep-research** | Google 学术/行业报告 | **新增** |
| fallback | tavily / gpt-4o-norway | 兜底 | 已有 |

每个 query 同时发给四个通道，取并集。信息覆盖面从双通道直接翻倍。

### Layer 2 提炼：不变（gemini-2.5-flash，便宜快速）

### Layer 3 Agent 分析：每个 Agent 用最适合的模型

| Agent | 现在用的 | 应该用的 | 理由 |
|-------|---------|---------|------|
| CTO | gpt-5.4 | gpt-5.4 | 不变，最强推理 |
| CMO | doubao-seed-pro | **gpt-5.3** + doubao 双源 | 5.3 做深度分析，doubao 补充中文市场数据 |
| CDO | gemini-3.1-pro | gemini-3.1-pro | 不变，多模态 |
| 新增: 推理验证 | — | **o3** | 对 CTO 的数值推算做独立验证（BOM/续航/功耗） |
| 新增: 中文交叉 | — | **qwen-3-32b** | 对 CMO 的中文市场结论做交叉验证 |

### Layer 4 整合：升级

| 角色 | 现在用的 | 应该用的 | 理由 |
|------|---------|---------|------|
| Synthesis | gpt-5.4 | **gemini-2.5-pro** | 65K 上下文（比 5.4 的 16K 大 4 倍），能一次看完所有 Agent 输出+辩论记录，不丢信息 |
| 推理链验证 | — | **deepseek-r1** | 对 synthesis 的推理链做独立验证（这个结论逻辑上站得住吗？） |

### Layer 5 Critic：双 Critic 交叉

| 角色 | 现在用的 | 应该用的 | 理由 |
|------|---------|---------|------|
| Critic 主审 | gemini-3.1-pro | gemini-3.1-pro | 不变 |
| Critic 交叉 | — | **o3** | 65K output + 最强推理，适合用逻辑挑战报告中的漏洞 |

---

## 二、日常问答：分层路由

| 复杂度 | 模型 | 响应时间 | 适用场景 |
|--------|------|---------|---------|
| 简单查询 | **gemini-2.5-flash** | 1-2s | "歌尔的产能是多少" |
| 中等问答 | **gpt-5.3** | 3-5s | "OLED 和 MicroLED 哪个更适合我们" |
| 复杂分析 | **gpt-5.4** | 10-15s | "帮我分析 V1 的完整 BOM" |
| 推理密集 | **o3** | 30-60s | "如果电池改成 1500mAh，推算所有连锁影响" |

现在所有问答都走 gpt-5.4，等于拿最贵的模型回答"帮助"这种简单问题。分层后大部分查询走 Flash 或 5.3，复杂的才上 5.4 或 o3。

---

## 三、特殊任务的专属模型

| 任务 | 最佳模型 | 理由 |
|------|---------|------|
| 意图分类 | **o3-mini** | 便宜+推理能力够，1 秒判断意图 |
| 数据对抗验证 | **deepseek-r1** | 推理链长，能层层追问"这个数据的口径是什么" |
| Demo 代码生成 | **gpt-5.4** | 代码生成能力最强的可用模型 |
| Demo 视觉验证 | **gemini-2.5-flash** (Vision) | 便宜+视觉能力够用 |
| 产品愿景/创意 | **gpt-5.4** | 创意写作用最强模型，temperature 调高到 0.7 |
| 教练模式 | **gpt-5.4** | 苏格拉底式提问需要最深度的推理 |
| 决策简报 | **gpt-5.4** + **o3** 交叉 | 5.4 生成简报，o3 验证数值 |
| 谈判准备 | **grok-4** + **gpt-5.4** | Grok 搜实时动态，5.4 生成策略 |
| 竞品推演 | **grok-4** + **deepseek-r1** | Grok 搜最新情报，R1 做推理推演 |
| 沙盘 What-If | **o3** | 65K output，能输出详尽的因果链条 |
| 反事实分析 | **deepseek-r1** | 推理链最长，适合"如果...那么..."型分析 |
| 入职包/综述 | **gpt-5.3** | 够用但不需要最强，性价比高 |
| 用户声音分析 | **qwen-3-32b** + **doubao** | 中文社区数据分析最强组合 |
| 图片 OCR 验证 | **llama-4-maverick** | 多模态+开源，处理报价单/名片/数据表 |
| 知识保鲜验证 | **gemini-2.5-flash** | 轻量搜索验证，成本低 |
| 经验法则提取 | **gpt-5.3** | 模式识别够用 |
| 早报生成 | **gemini-2.5-flash** | 聚合已有数据，不需要推理 |
| 品牌层/情绪感知 | **o3-mini** | 轻量判断，够用 |

---

## 四、需要更新的文件

### model_registry.yaml
- Grok 的 capabilities 补充 `"search"`, `"web_search"`, `"social_media"`
- Gemini Deep Research 的 capabilities 补充 `"web_search"`
- Claude Opus 的 purpose 更新为"深度整合、创意写作、教练模式"
- GPT-5.3 的 purpose 更新为"日常问答主力、中等复杂度分析"

### tonight_deep_research.py (或 deep_research/)
- `_get_model_for_task()` 全面更新
- `_get_model_for_role()` 全面更新
- Layer 4 synthesis 改用 claude-opus-4.6
- Layer 5 增加 claude-opus-4.6 交叉审查

### text_router.py
- `_smart_route_and_reply()` 中的模型选择改为分层路由
- 各飞书指令用最适合的模型

### 降级映射表更新
```python
FALLBACK_MAP = {
    "gpt_5_4": "gpt_5_3",           # 5.4 → 5.3
    "gpt_5_3": "gpt_4o_norway",     # 5.3 → 4o
    "o3": "deepseek_r1",            # o3 → DeepSeek R1（同为推理专家）
    "o3_mini": "gemini_2_5_flash",  # o3-mini → Flash
    "deepseek_r1": "o3_mini",       # R1 → o3-mini
    "grok_4": "gpt_4o_norway",      # Grok → 4o
    "gemini_deep_research": "o3_deep_research",  # Gemini Deep → o3 Deep
    "doubao_seed_pro": "doubao_seed_lite",
    "gemini_3_1_pro": "gemini_3_pro",
    "gemini_3_pro": "gemini_2_5_pro",
    "gemini_2_5_pro": "gpt_5_3",    # Gemini Pro → 5.3
    "o3_deep_research": "gpt_5_4",
    "qwen_3_32b": "deepseek_v3_2",  # Qwen → DeepSeek（都擅长中文）
    "llama_4_maverick": "gpt_4o_norway",
    "deepseek_v3_2": "qwen_3_32b",  # DeepSeek → Qwen（互为备选）
}
```

注意：Claude Opus 和 Sonnet 暂不使用（Leo 没有 Claude API），保留在 registry 中供未来激活。Agent 角色绑定中 critic_azure 和 cro 暂时降级：
- critic_azure: 改用 gpt-5.4 或 o3
- cro: 改用 gpt-5.3

---

## 五、并发信号量更新

```python
PROVIDER_SEMAPHORES = {
    "o3_deep": threading.Semaphore(3),
    "o3": threading.Semaphore(3),
    "o3_mini": threading.Semaphore(5),
    "grok": threading.Semaphore(3),
    "gemini_deep": threading.Semaphore(2),
    "doubao": threading.Semaphore(8),
    "flash": threading.Semaphore(8),
    "gemini_pro": threading.Semaphore(3),
    "gpt54": threading.Semaphore(4),
    "gpt53": threading.Semaphore(4),
    "gpt4o": threading.Semaphore(4),
    "claude_opus": threading.Semaphore(3),
    "claude_sonnet": threading.Semaphore(4),
    "deepseek_r1": threading.Semaphore(3),
    "qwen": threading.Semaphore(4),
    "llama": threading.Semaphore(3),
}
```

---

## 六、效果预估

### Before（6 个模型工作）
- 搜索：2 通道（o3 + 豆包）
- 分析：3 Agent 同一水平（都用 5.4 或指定单模型）
- 整合：gpt-5.4（16K 上下文可能不够）
- 审查：单 Critic
- 日常问答：一律 gpt-5.4（杀鸡用牛刀）
- 12 个模型吃灰

### After（19 个模型全上阵，Claude 暂保留未来激活）
- 搜索：4 通道（o3 + 豆包 + Grok + Gemini Deep）
- 分析：5 Agent + 独立推理验证（o3）+ 中文交叉验证（Qwen）
- 整合：Gemini 2.5 Pro（65K 上下文，不丢信息）+ DeepSeek R1 推理链验证
- 审查：双 Critic 交叉（Gemini 3.1 Pro + o3）
- 日常问答：4 层路由（Flash → 5.3 → 5.4 → o3）
- 每个特殊任务都有最适合的模型
- 2 个模型待激活（Claude Opus/Sonnet，等 API），其余全部上阵
