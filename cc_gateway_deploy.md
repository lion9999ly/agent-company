# CC 任务：model_gateway 拆分部署

## 回滚方案（先做）
```bash
cp src/utils/model_gateway.py src/utils/model_gateway_backup_20260406.py
```
如果部署失败，一秒回滚：
```bash
cp src/utils/model_gateway_backup_20260406.py src/utils/model_gateway.py
rm -rf src/utils/model_gateway/
```

## 部署步骤

### 1. 创建包目录
```bash
mkdir -p src/utils/model_gateway/providers
```

### 2. 复制文件
把 Leo 提供的以下文件放到对应位置：
- `model_gateway/__init__.py`     → `src/utils/model_gateway/__init__.py`
- `model_gateway/config.py`       → `src/utils/model_gateway/config.py`
- `model_gateway/providers/__init__.py`     → `src/utils/model_gateway/providers/__init__.py`
- `model_gateway/providers/gemini.py`       → `src/utils/model_gateway/providers/gemini.py`
- `model_gateway/providers/azure_openai.py` → `src/utils/model_gateway/providers/azure_openai.py`
- `model_gateway/providers/volcengine.py`   → `src/utils/model_gateway/providers/volcengine.py`
- `model_gateway/providers/others.py`       → `src/utils/model_gateway/providers/others.py`

### 3. 将原文件改为 shim
将 `src/utils/model_gateway.py` 替换为以下内容：

```python
"""
model_gateway.py — 向后兼容入口
所有实现已迁移到 src/utils/model_gateway/ 包
"""
from src.utils.model_gateway import (
    ModelGateway,
    get_model_gateway,
    call_for_search,
    call_for_refine,
)
from src.utils.model_gateway.config import (
    ModelConfig,
    ModelProvider,
    TaskType,
    TIMEOUT_BY_TASK,
)
```

**注意**: Python 不允许同名的 .py 文件和包目录共存。
所以需要：
1. 先把 `model_gateway.py` 重命名为 `model_gateway_shim.py`
2. 把包目录命名为 `model_gateway/`
3. 找到所有 `from src.utils.model_gateway import` 的地方 —— 由于包的 `__init__.py` 导出了相同的接口，大部分不用改
4. 如果有 `from src.utils.model_gateway import ModelGateway` 这种写法，包的 `__init__.py` 已经导出了，不用改

**实际上更简单的做法**：直接删掉 `model_gateway.py`，因为 Python 会优先找 `model_gateway/` 目录。
```bash
# 备份已做，直接删
rm src/utils/model_gateway.py
# 包目录 src/utils/model_gateway/ 已经有 __init__.py，会自动接管所有 import
```

### 4. 验证 import
```bash
.venv\Scripts\python.exe -c "
from src.utils.model_gateway import get_model_gateway, call_for_search, call_for_refine, ModelGateway
from src.utils.model_gateway.config import ModelConfig, TaskType, TIMEOUT_BY_TASK
from src.utils.model_gateway.providers.gemini import call_gemini_image_gen
gw = get_model_gateway()
print(f'Models loaded: {len(gw.models)}')
print(f'Image models: {[n for n, c in gw.models.items() if \"image_generation\" in c.capabilities]}')
print('All imports OK')
"
```

### 5. 验证图像生成
```bash
.venv\Scripts\python.exe -c "
from src.utils.model_gateway import get_model_gateway
gw = get_model_gateway()

# 测试 Gemini 图像生成（通过 call_image 统一接口）
for model in ['nano_banana_pro', 'nano_banana_2', 'gemini_flash_image']:
    result = gw.call_image('Generate a simple green arrow icon on black background', model_name=model)
    status = 'OK' if result.get('success') else f'FAIL: {result.get(\"error\", \"\")[:80]}'
    print(f'{model}: {status}')

# 测试 Seedream
result = gw.call_image('一个绿色箭头图标，黑色背景', model_name='seedream_3_0')
status = 'OK' if result.get('success') else f'FAIL: {result.get(\"error\", \"\")[:80]}'
print(f'seedream_3_0: {status}')
"
```

### 6. 验证文本模型不受影响
```bash
.venv\Scripts\python.exe -c "
from src.utils.model_gateway import get_model_gateway
gw = get_model_gateway()
# 确认文本调用仍然正常
result = gw.call('gpt_5_4', 'Ping', task_type='health_check')
print(f'gpt_5_4: {\"OK\" if result.get(\"success\") else \"FAIL\"}')
result = gw.call('gemini_2_5_flash', 'Ping', task_type='health_check')
print(f'gemini_2_5_flash: {\"OK\" if result.get(\"success\") else \"FAIL\"}')
result = gw.call('doubao_seed_pro', 'Ping', task_type='health_check')
print(f'doubao_seed_pro: {\"OK\" if result.get(\"success\") else \"FAIL\"}')
"
```

### 7. 验证全链路（深度研究 import）
```bash
.venv\Scripts\python.exe -c "
from scripts.deep_research import run_deep_learning, deep_research_one, FALLBACK_MAP
from scripts.tonight_deep_research import run_all
print('Full chain import OK')
"
```

### 8. Commit
```bash
git add src/utils/model_gateway/ src/utils/model_gateway_backup_20260406.py
git rm src/utils/model_gateway.py 2>/dev/null  # 如果还存在
git add -A
git commit --no-verify -m "refactor: split model_gateway.py into package + fix image generation routing"
git push origin main
```

## 如果失败
```bash
# 回滚
cp src/utils/model_gateway_backup_20260406.py src/utils/model_gateway.py
rm -rf src/utils/model_gateway/
git checkout -- src/utils/model_gateway.py
echo "已回滚到原版 model_gateway.py"
```
