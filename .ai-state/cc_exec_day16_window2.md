# Day 16 窗口 2 — Demo 端到端测试

> 独立执行，不依赖窗口 1
> Gemini 不可用，视觉验证跳过

---

## 任务 4：Demo 端到端测试准备

### 1. 检查 Playwright

```bash
pip show playwright 2>nul || echo "Not installed"
```

如果没装：
```bash
pip install playwright --break-system-packages
playwright install chromium
```

如果安装失败（网络问题等），跳过——Demo 可以不做视觉验证。

### 2. 检查 demo_generator.py

```python
python -c "
from scripts.demo_generator import generate_hud_demo, generate_app_demo
print('demo_generator import OK')
"
```

如果 import 失败，检查报错并修复。

### 3. 确保降级逻辑

在 scripts/demo_generator.py 中，找到调用 Playwright 或 Vision 模型的地方，确保有 try/except 降级：

```python
# 视觉调试部分
try:
    # Playwright 截屏 + Vision 检查
    ...
except Exception as e:
    print(f"[Demo] 视觉调试跳过: {e}")
    # 跳过截屏，直接返回 HTML
```

同样，找到调用 Gemini 的地方，确保降级到可用模型：
- gemini_2_5_flash → doubao_seed_lite 或 gpt_4o_norway
- gemini_3_1_pro → gpt_5_4

### 4. 检查飞书指令注册

确认 "生成 HUD Demo" 或 "生成HUD Demo" 指令在 text_router.py 中已注册。

```bash
grep -n "Demo\|demo\|HUD.*[Dd]emo" scripts/feishu_handlers/text_router.py | head -10
```

如果没有注册，添加。

### 5. Dry-run 测试

```python
python -c "
import sys; sys.path.insert(0, '.')
from scripts.demo_generator import generate_hud_demo

# 用最小参数测试
result = generate_hud_demo(design_spec={
    'fov': '18-21°',
    'resolution': '1024x768',
    'color': 'green',
    'position': 'lower-right'
})
print(f'Result type: {type(result)}')
print(f'Result keys: {list(result.keys()) if isinstance(result, dict) else \"not dict\"}')
print(f'Success: {result.get(\"success\", \"?\") if isinstance(result, dict) else \"?\"}')
"
```

如果成功，检查生成的 HTML 文件。
如果失败，记录错误信息。

### 6. 提交

git add -A && git commit -m "feat: Demo e2e test prep — Playwright check + graceful degradation" && git push origin main
