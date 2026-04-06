# P2 修复指令 — meta_capability.py pip 路径

## 问题
`scripts/meta_capability.py` 中的 `subprocess.run(['pip', 'install', ...])` 
在 Windows 上会找不到 `pip`（因为裸 `pip` 指向 Windows Store 空壳）。

日志证据:
```
[Meta] 安装: pip install beautifulsoup4
[Meta] 安装失败: [WinError 2] 系统找不到指定的文件。
```

## 修复方案
在 `meta_capability.py` 中，找到所有 `subprocess.run(['pip', ...]` 的地方，
将 `'pip'` 替换为 venv 内的完整路径。

具体修改:

1. 在文件顶部添加:
```python
import sys
from pathlib import Path

# 获取当前 venv 的 pip 路径（Windows: .venv\Scripts\pip.exe, Linux: .venv/bin/pip）
_VENV_PIP = str(Path(sys.executable).parent / "pip")
```

2. 全局搜索替换:
- `['pip',` → `[_VENV_PIP,`
- `'pip install'` 如果是传给 shell=True 的字符串 → 也要替换

3. 同理，如果有 `subprocess.run(['python', ...])`，也要替换为 `sys.executable`

## 验证
```python
.venv\Scripts\python.exe -c "
import sys
from pathlib import Path
pip_path = str(Path(sys.executable).parent / 'pip')
print(f'pip path: {pip_path}')
import subprocess
result = subprocess.run([pip_path, '--version'], capture_output=True, text=True)
print(result.stdout)
"
```
