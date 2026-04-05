# Day 16 追加执行 — 全部剩余任务（最终版）

> 一个 CC 窗口串行执行
> 所有 git commit 用 --no-verify
> 火山引擎新发现：deepseek-r1, glm-4-7, doubao-vision, seedream-3.0 均可用

按顺序执行。每完成一组 commit + push。

---

## 第 1 组：模型映射全面修复

### 1a. 修改 tonight_deep_research.py 的 _get_model_for_role()

把整个 role_model_map 替换为：

```python
role_model_map = {
    "CTO": "gpt_5_4",
    "CMO": "gpt_4o_norway",
    "CDO": "deepseek_v3_volcengine",
    "CPO": "gpt_5_4",
    "VERIFIER": "deepseek_r1_volcengine",
    "CHINESE_CROSS": "doubao_seed_pro",
}
```

### 1b. 修改 _get_model_for_task()

把整个 task_model_map 替换为：

```python
task_model_map = {
    "discovery": "doubao_seed_lite",
    "query_generation": "doubao_seed_lite",
    "data_extraction": "gpt_4o_norway",
    "role_assign": "doubao_seed_lite",
    "synthesis": "gpt_5_4",
    "re_synthesis": "gpt_5_4",
    "final_synthesis": "gpt_5_4",
    "critic_challenge": "gpt_5_4",
    "critic_cross": "deepseek_r1_volcengine",
    "consistency_check": "gpt_5_4",
    "knowledge_extract": "doubao_seed_lite",
    "fix": "gpt_5_4",
    "cdo_fix": "gpt_5_4",
    "chinese_search": "doubao_seed_pro",
    "deep_research_search": "o3_deep_research",
    "grok_search": "gpt_4o_norway",
    "gemini_deep_search": "o3_deep_research",
    "deep_drill_conclusion": "gpt_5_4",
    "debate": "deepseek_v3_volcengine",
    "analogy": "doubao_seed_lite",
    "sandbox": "deepseek_r1_volcengine",
}
```

### 1c. 修改 FALLBACK_MAP

把整个 FALLBACK_MAP 替换为：

```python
FALLBACK_MAP = {
    "gpt_5_4": "gpt_4o_norway",
    "gpt_4o_norway": "doubao_seed_pro",
    "o3_deep_research": "gpt_5_4",
    "doubao_seed_pro": "doubao_seed_lite",
    "doubao_seed_lite": "gpt_4o_norway",
    "deepseek_v3_volcengine": "deepseek_r1_volcengine",
    "deepseek_r1_volcengine": "gpt_5_4",
    "glm_4_7": "doubao_seed_pro",
    "doubao_vision_pro": "gpt_5_4",
    "gpt_5_3": "gpt_4o_norway",
    "o3": "deepseek_r1_volcengine",
    "o3_mini": "doubao_seed_lite",
    "grok_4": "gpt_4o_norway",
    "gemini_deep_research": "o3_deep_research",
    "gemini_3_1_pro": "gpt_5_4",
    "gemini_3_pro": "gpt_5_4",
    "gemini_2_5_pro": "gpt_5_4",
    "gemini_2_5_flash": "gpt_4o_norway",
    "qwen_3_32b": "doubao_seed_pro",
    "llama_4_maverick": "gpt_4o_norway",
    "deepseek_v3_2": "deepseek_v3_volcengine",
    "deepseek_r1": "deepseek_r1_volcengine",
}
```

### 1d. 在 model_registry.yaml 中新增火山引擎模型

追加：

```yaml
deepseek_r1_volcengine:
  provider: "volcengine"
  model: "deepseek-r1-250528"
  api_key_env: "ARK_API_KEY"
  purpose: "推理链/数学/逻辑"
  max_tokens: 8192
  temperature: 0.1
  enabled: true

glm_4_7:
  provider: "volcengine"
  model: "glm-4-7-251222"
  api_key_env: "ARK_API_KEY"
  purpose: "国产通用/中文"
  max_tokens: 4096
  temperature: 0.1
  enabled: true

doubao_vision_pro:
  provider: "volcengine"
  model: "doubao-1-5-vision-pro-32k-250115"
  api_key_env: "ARK_API_KEY"
  purpose: "图片理解/多模态"
  max_tokens: 4096
  temperature: 0.1
  capabilities: ["vision"]
  enabled: true

seedream_3_0:
  provider: "volcengine"
  model: "doubao-seedream-3-0-t2i-250415"
  api_key_env: "ARK_API_KEY"
  purpose: "图片生成"
  max_tokens: 1
  temperature: 0.1
  capabilities: ["image_generation"]
  enabled: true
```

### 1e. test_suite.py 软测试模型修复

所有 `gemini_2_5_flash` 替换为 `doubao_seed_lite`

git add -A && git commit --no-verify -m "fix: complete model remapping — 12 models, all chains verified" && git push origin main

---

## 第 2 组：验证脚本 + 集成测试

新建 scripts/verify_fallback_chains.py 和 scripts/integration_test.py。

verify_fallback_chains.py 内容：遍历 FALLBACK_MAP 中所有模型，验证每条链最终落到可用模型（gpt_5_4, gpt_4o_norway, o3_deep_research, doubao_seed_pro, doubao_seed_lite, deepseek_v3_volcengine, deepseek_r1_volcengine, glm_4_7, doubao_vision_pro, seedream_3_0）。

integration_test.py 内容：测试模型网关调用、KB 读写、学习系统文件可写、决策树可读、Claude CLI、降级链、图片生成（seedream）、DeepSeek R1。

运行：
python scripts/verify_fallback_chains.py
python scripts/integration_test.py

git add -A && git commit --no-verify -m "feat: fallback verifier + integration test" && git push origin main

---

## 第 3 组：飞书交互增强

3a. send_reply 消息分块（超 2000 字自动拆分）
3b. 所有带参数指令的解析统一 .strip().strip(":：").strip()
3c. "帮助"指令返回分组的完整指令列表

git add -A && git commit --no-verify -m "feat: message chunking + strip fix + help enhancement" && git push origin main

---

## 第 4 组：豆包多模态接入

4a. model_gateway.py 新增 call_image_generation() 方法（调用 seedream）
4b. call_volcengine() 增加 image_url 参数支持（多模态理解）
4c. CDO Agent 涉及图片分析时用 doubao_vision_pro

git add -A && git commit --no-verify -m "feat: volcengine image gen + vision multimodal" && git push origin main

---

## 第 5 组：自动化运维

5a. 新建 scripts/system_snapshot.py — 生成系统状态快照到 .ai-state/system_snapshot.md
5b. 新建 scripts/competitor_monitor.py — 每天搜索竞品关键词，有新内容推送飞书
5c. 新建 scripts/daily_system_report.py — 系统运行日报（KB统计/报告数/学习记录/决策树进度）
5d. feishu_sdk_client.py 注册定时任务：
    - 每天 00:00 自动深度学习 8h
    - 每天 06:00 竞品监控
    - 每天 07:00 系统日报
    注意 LEO_OPEN_ID = "ou_8e5e4f183e9eca4241378e96bac3a751"

git add -A && git commit --no-verify -m "feat: snapshot + competitor monitor + daily report + scheduler" && git push origin main

---

## 第 6 组：eval 安全

tonight_deep_research.py 中的 _evaluate_calculations() 用了 eval()。
替换为 ast.parse + 安全求值（只允许 +-*/），避免 pre-commit hook 拦截。

git add -A && git commit --no-verify -m "fix: replace eval with safe AST calculator" && git push origin main

---

## 最终验证

```bash
python scripts/verify_fallback_chains.py
python scripts/integration_test.py
python scripts/self_heal.py
python scripts/system_snapshot.py
```

把所有结果贴出来。
