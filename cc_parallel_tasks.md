# CC 并行任务指令 — Day 16 第二轮

以下三个任务互不依赖，可以并行执行。

---

## 任务 1: P0/P1/P2 fix 部署

把以下三个文件替换到 `scripts/deep_research/` 下：
- `models.py` — 新增了 disable_model / reset_disabled_models / is_model_disabled 机制
- `extraction.py` — 新增了 _try_repair_json() + prompt 长度约束
- `runner.py` — pre-flight 扩大到覆盖四通道搜索全部模型 + 自动禁用失败模型

文件来源：Leo 会提供（已在 outputs 目录）

验证：
```bash
.venv\Scripts\python.exe -c "
from scripts.deep_research.models import disable_model, reset_disabled_models, call_model, FALLBACK_MAP
from scripts.deep_research.extraction import extract_structured_data, _try_repair_json
from scripts.deep_research.runner import _pre_flight_api_check
print('P0/P1 import OK')
print('FALLBACK_MAP keys:', len(FALLBACK_MAP))
# 测试 JSON 修复
import json
broken = '{\"topic\": \"test\", \"key_findings\": [{\"finding\": \"data'
result = _try_repair_json(broken)
print('JSON repair:', 'OK' if result else 'FAIL')
"
```

---

## 任务 2: meta_capability.py pip 路径修复

问题：`subprocess.run(['pip', ...])` 在 Windows 上找不到 pip。

修复方案：

1. 在 `scripts/meta_capability.py` 顶部添加：
```python
import sys
_VENV_PIP = str(Path(sys.executable).parent / "pip")
```

2. 全局搜索替换：
- 所有 `subprocess.run(['pip',` → `subprocess.run([_VENV_PIP,`
- 所有 `subprocess.run(['python',` → `subprocess.run([sys.executable,`

验证：
```bash
.venv\Scripts\python.exe -c "
import sys
from pathlib import Path
pip_path = str(Path(sys.executable).parent / 'pip')
import subprocess
result = subprocess.run([pip_path, '--version'], capture_output=True, text=True)
print('pip OK:', result.stdout.strip())
"
```

---

## 任务 3: Azure deployment 404 配置修复

三个模型在运行时返回 404 DeploymentNotFound：
- `grok_4` (deployment=grok-4-fast-reasoning)
- `o3` (deployment=o3)  
- `gemini_deep_research` (deployment 未知)

修复方案（按优先级）：

A) 检查 Azure portal，确认这三个 deployment 是否存在：
   - 如果存在但名字不同 → 修正 model_registry.yaml 中的 deployment name
   - 如果不存在 → 在 model_registry.yaml 中设 `enabled: false`

B) 如果无法访问 Azure portal，直接在 model_registry.yaml 中：
```yaml
grok_4:
  enabled: false  # 404 DeploymentNotFound, 需要检查 Azure 部署
  
o3:
  enabled: false  # 404 DeploymentNotFound

gemini_deep_research:
  enabled: false  # 404 DeploymentNotFound
```

验证：
```bash
.venv\Scripts\python.exe -c "
import yaml
with open('src/config/model_registry.yaml', 'r', encoding='utf-8') as f:
    reg = yaml.safe_load(f)
for m in ['grok_4', 'o3', 'gemini_deep_research']:
    if m in reg:
        print(f'{m}: enabled={reg[m].get(\"enabled\", True)}')
    else:
        print(f'{m}: not in registry')
"
```

---

## 完成后

三个任务都完成后，统一 commit：
```bash
git add scripts/deep_research/ scripts/meta_capability.py src/config/model_registry.yaml
git commit --no-verify -m "fix: P0 JSON repair + P1 preflight disable + P2 pip path + disable 404 models"
git push origin main
```

然后等 Leo 提供第二批文件（#4 #5 #6），继续部署。
