# CC 指令：修复测试脚本 + 验证模型可用性

> 执行文档 — 2026-03-30
> 不涉及 git commit，纯诊断

---

## Step 1：查 .env 加载方式

```bash
grep -rn "load_dotenv\|dotenv" scripts/feishu_sdk_client_v2.py scripts/feishu_handlers/*.py src/utils/model_gateway.py start_all.bat --include="*.py" --include="*.bat" | head -20
```

确认项目里用的是 `python-dotenv` 的 `load_dotenv()`，还是 bat 里 `set` 环境变量。把结果贴出来。

## Step 2：改测试脚本

在 `scripts/test_model_availability.py` 顶部（`import sys` 之前）加：

```python
from dotenv import load_dotenv
load_dotenv()  # 从项目根 .env 加载环境变量
```

如果 Step 1 发现 `load_dotenv` 指定了路径（如 `load_dotenv(Path(__file__).parent.parent / '.env')`），用同样的路径。

## Step 3：跑测试

```bash
python scripts/test_model_availability.py
```

把完整输出贴回来。重点关注：
- o3 和 o3_deep_research 是返回 200 还是 404？
- 如果 404，日志里会打印当前的 `deployment=xxx`，这个值就是需要改的
- gpt_5_4 和 gemini 系列是否正常

## 不要做的事

- 不要改 model_registry.yaml（等测试结果出来再决定）
- 不要重启服务
- 不要 git commit
