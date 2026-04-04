深度学习正在跑，三个 bug 需要热修。

## Bug 1: o3-deep-research 全部 404

model_registry.yaml 中的配置没问题：deployment="o3-deep-research"，endpoint 指向 Norway East。

排查步骤（按顺序）：

1. 先用 curl 测试当前配置是否能通：
```bash
curl -s -w "\n%{http_code}" -X POST \
  "$AZURE_OPENAI_NORWAY_ENDPOINT/openai/deployments/o3-deep-research/responses?api-version=2025-04-01-preview" \
  -H "api-key: $AZURE_OPENAI_NORWAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": "Say hello", "max_output_tokens": 100}'
```

2. 如果 404，可能是 Responses API 的路径格式不对。试这些变体：
```bash
# 变体A：不带 /openai/ 前缀
curl -s -w "\n%{http_code}" -X POST \
  "$AZURE_OPENAI_NORWAY_ENDPOINT/deployments/o3-deep-research/responses?api-version=2025-04-01-preview" \
  -H "api-key: $AZURE_OPENAI_NORWAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": "Say hello", "max_output_tokens": 100}'

# 变体B：Chat Completions 端点（确认 deployment 还在）
curl -s -w "\n%{http_code}" -X POST \
  "$AZURE_OPENAI_NORWAY_ENDPOINT/openai/deployments/o3-deep-research/chat/completions?api-version=2025-04-01-preview" \
  -H "api-key: $AZURE_OPENAI_NORWAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello"}],"max_tokens":50}'

# 变体C：不同的 api-version
curl -s -w "\n%{http_code}" -X POST \
  "$AZURE_OPENAI_NORWAY_ENDPOINT/openai/deployments/o3-deep-research/responses?api-version=2025-03-01-preview" \
  -H "api-key: $AZURE_OPENAI_NORWAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": "Say hello", "max_output_tokens": 100}'

# 变体D：gpt-4o 确认 endpoint 本身能通
curl -s -w "\n%{http_code}" -X POST \
  "$AZURE_OPENAI_NORWAY_ENDPOINT/openai/deployments/gpt-4o/chat/completions?api-version=2025-04-01-preview" \
  -H "api-key: $AZURE_OPENAI_NORWAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello"}],"max_tokens":50}'
```

3. 把所有 curl 返回的 HTTP 状态码和响应体贴出来。根据哪个通了，更新 `call_azure_responses()` 中的 URL 构建逻辑。

## Bug 2+3: searches 嵌套 list（豆包 400 + tavily 422）

根因已确认：日志显示 `补充 5 个搜索词: [['JBD MicroLED 微显示器', '高亮度低功耗 AR头盔显示'], ...]`。discovery 返回的搜索词是 list of lists，混入 searches 列表后被直接当 query 传给了 doubao 和 tavily。

修复位置：`scripts/tonight_deep_research.py`，在 `[L1] 并发搜索` 打印之前，插入展平逻辑：

```python
    # 展平 searches（discovery 可能返回嵌套 list）
    flat_searches = []
    for s in searches:
        if isinstance(s, list):
            flat_searches.extend([str(item) for item in s])
        else:
            flat_searches.append(str(s))
    searches = flat_searches
```

同时在 `src/utils/model_gateway.py` 的 `call_volcengine()` 方法中加一层类型保护。找到构建 messages 的部分，确保 content 一定是 str：

```python
# 防御性转换
prompt = str(prompt) if not isinstance(prompt, str) else prompt
if system_prompt:
    system_prompt = str(system_prompt) if not isinstance(system_prompt, str) else system_prompt
```

## 执行顺序

1. Bug 2+3 先修（searches 展平 + volcengine content 保护）——改完立即生效
2. Bug 1 先 curl 排查，把结果贴出来

```bash
git add -A && git commit -m "hotfix: flatten nested search queries + volcengine content type guard"
```

Bug 1 的 curl 结果贴出来后再决定怎么改。
