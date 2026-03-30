# Azure + Doubao 探测结果

> 执行时间：2026-03-30

---

## Azure 探测结果

### 可用模型

| Deployment | 状态 | 说明 |
|------------|------|------|
| gpt-5.4 | ✅ 200 OK | 需要 `max_completion_tokens` 参数 |

### 不可用模型（404）

**o3 系列（全部未部署）：**
- o3, o3-mini, o3-2025-04-16, o3-mini-2025-01-31
- o3-2025-01-31, o3-preview, o3-mini-high
- o3-pro, o3-pro-2025-06-10
- o3-deep-research, o3-deep-research-2025-06-26
- o3-2025-06-26, o3-mini-2025-04-16
- o3-deep-research-preview, o3-2026, o3-latest
- o3mini, o3-mini-latest

**GPT 系列（除 gpt-5.4 外全部未部署）：**
- gpt-5.3, gpt-5.3-chat-2026-03-03
- gpt-5, gpt-5.0, gpt-5-turbo
- gpt-4o, gpt-4o-mini, gpt-4o-2024-08-06
- gpt-4, gpt-4-turbo, gpt-4-32k
- gpt-4o-mini-2024-07-18
- gpt-4.1, gpt-4.1-mini, gpt-4.1-nano
- gpt-4o-2024-11-20

**其他模型（全部未部署）：**
- o1 系列（o1, o1-mini, o1-preview）
- Claude 系列（claude-opus-4-6, claude-sonnet-4-6）
- DeepSeek 系列（DeepSeek-R1, DeepSeek-V3）
- Llama 系列（Llama-4-Maverick, meta-llama-3.1）
- Qwen 系列（qwen-3-32b, Qwen2.5-72B）
- Grok 系列（grok-4-fast-reasoning, grok-3）
- Phi 系列（Phi-4, Phi-3.5-mini）
- Mistral 系列（Mistral-large, mistral-small）
- DALL-E 3, Whisper

---

## Doubao 探测结果

**状态：❌ 未测试**

原因：`DOUBAO_API_KEY` 未设置

需要用户在 `.env` 中添加：
```bash
DOUBAO_API_KEY=your_api_key
DOUBAO_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3
```

然后运行：
```bash
python scripts/test_doubao.py
```

---

## 结论

1. **Azure 上只有 gpt-5.4 可用**
2. **o3 系列（包括 o3-deep-research）全部未部署**
3. **深度研究管道的模型路由修复（deep_research_model_routing_fix.md）已正确**：使用 gpt_5_4 和 gemini 系列
4. **豆包接入需要用户提供 API Key**

---

## 下一步建议

1. 如需使用豆包，请提供 DOUBAO_API_KEY
2. 如需 o3/deep-research，需在 Azure portal 创建新 deployment
3. 当前配置已正确使用可用模型（gpt_5_4, gemini 系列）