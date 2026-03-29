# PRD v2 Round 6 修复文档

> CC 执行文档 — 2026-03-29
> 目标：修复 Round 5 产出中的 4 个问题
> 文件：`scripts/feishu_handlers/structured_doc.py`
> 完成后：`git add -A && git commit -m "fix: Round 6 — Mermaid bracket escape, Excel normalize, token truncation guard"`

---

## Fix 1：Mermaid 流程图方括号嵌套导致 Syntax Error（P0）

### 问题

Mermaid 节点标签中出现嵌套方括号，导致解析失败：
```
A[头盔开机配对模式<br/>[头盔]]   ← Mermaid 把内层 [ 当作新节点开始
```

8 个流程图中有 3 个报 Syntax Error（首次配对、组队配对、部件更换）。

另外存在混合转义：部分节点用 `&lt;br/&gt;`，部分用 `<br/>`，不一致。

### 根因

生成 Mermaid 代码的 prompt 或后处理没有约束节点标签格式。

### 修复

在 `structured_doc.py` 中找到生成 Mermaid 代码后、写入 DATA / Excel 之前的位置，添加后处理函数：

```python
import re

def sanitize_mermaid(code: str) -> str:
    """修复 Mermaid 节点标签中的嵌套方括号和混合 HTML 转义"""
    if not code:
        return code

    # 1. 统一 &lt;br/&gt; → <br/>
    code = code.replace('&lt;br/&gt;', '<br/>')
    code = code.replace('&amp;lt;br/&amp;gt;', '<br/>')

    # 2. 去掉节点标签内的 <br/>[xxx] 标注 → " - xxx"
    #    匹配模式: <br/>[任意文字] 在 ] 之前
    code = re.sub(r'<br/>\[([^\]]+)\]', r' - \1', code)

    # 3. 修复菱形节点 {text} 中的 <br/>[xxx] 同理
    code = re.sub(r'<br/>\(([^)]+)\)', r' - \1', code)

    # 4. 修复残留的嵌套方括号: A[xxx[yyy]] → A[xxx - yyy]
    #    逐行处理节点定义
    lines = code.split('\n')
    fixed_lines = []
    for line in lines:
        stripped = line.strip()
        # 匹配节点定义行: 字母数字[...] 或 字母数字{...} 或 字母数字([...])
        # 修复 [text[inner]] 模式
        if re.match(r'\s*\w+\[', stripped):
            # 找到第一个 [ 后，检查是否有嵌套 [
            bracket_start = stripped.index('[')
            content = stripped[bracket_start+1:]
            # 如果 content 中还有 [ 且不是最后的 ]
            if '[' in content[:-1]:
                content = content.replace('[', '(').replace(']', ')', 1)
                # 最后一个 ] 保留
                stripped = stripped[:bracket_start+1] + content
            fixed_lines.append(line.replace(line.strip(), stripped))
        else:
            fixed_lines.append(line)

    return '\n'.join(fixed_lines)
```

调用点 — 在所有写入 Mermaid 代码的地方调用：

搜索 `structured_doc.py` 中所有对 `mermaid` 字段赋值的位置（包括 `mermaid_code`、`Mermaid代码` 列），在赋值前套一层 `sanitize_mermaid()`：

```python
# 示例：在构建 flow_diagrams 列表时
flow['mermaid_code'] = sanitize_mermaid(flow['mermaid_code'])

# 示例：在写入 Excel "关键流程" sheet 时
row['Mermaid代码'] = sanitize_mermaid(row.get('Mermaid代码', ''))
```

### 验证

生成后用正则检查所有 Mermaid 代码块：
```python
for flow in flow_diagrams:
    code = flow.get('mermaid_code', '')
    # 检查嵌套方括号
    if re.search(r'\[[^\]]*\[', code):
        print(f"[MermaidCheck] ⚠️ 嵌套方括号仍存在: {flow['name']}")
    # 检查混合转义
    if '&lt;' in code or '&gt;' in code:
        print(f"[MermaidCheck] ⚠️ HTML实体未清理: {flow['name']}")
    else:
        print(f"[MermaidCheck] ✅ {flow['name']}")
```

---

## Fix 2：Excel 端社区 Tab 未归一化（P1）

### 问题

HTML DATA 中社区模块名为 `社区`（正确），但 Excel `App端` sheet 中仍为 `社区Tab`。说明 Excel 写入路径没有经过 `module_normalize` 映射。

### 根因

`structured_doc.py` 中写入 Excel 的函数在构建行数据时，直接使用了原始模块名，没有过 normalize。HTML 端的 DATA 构建路径有 normalize，Excel 路径漏了。

### 修复

1. 搜索 `structured_doc.py` 中写入 Excel `App端` sheet 的代码段（通常是遍历 app_features 写入行的循环）。

2. 找到 `module_normalize` 或 `normalize_map` 的定义位置（应该已经存在）。

3. 在 Excel 写入循环中，对 L1 功能名做 normalize：

```python
# 在写入 Excel 行之前，确保模块名经过归一化
# 找到类似这样的代码:
#   row['L1功能'] = feature.get('module', '')
# 改为:
def normalize_module(name: str, normalize_map: dict) -> str:
    """对模块名做归一化映射"""
    if not name:
        return name
    return normalize_map.get(name, name)

# 写入时:
raw_module = feature.get('module', '')
row['L1功能'] = normalize_module(raw_module, normalize_map)
```

4. 确保 `normalize_map` 包含 `'社区Tab': '社区'` 这条映射（根据移交文档的 27 条映射表，已有 `'社区Tab': '社区'`，确认即可）。

5. **同时检查** HUD 端 sheet 的写入路径是否也漏了 normalize（虽然本次没发现问题，预防性加上）。

### 验证

```python
# 生成后检查 Excel 中是否还有 "社区Tab"
import pandas as pd
app = pd.read_excel(output_path, sheet_name='App端')
bad = app[app['L1功能'].str.contains('社区Tab', na=False)]
if len(bad) > 0:
    print(f"[NormCheck] ❌ 仍有 {len(bad)} 行包含 '社区Tab'")
else:
    print("[NormCheck] ✅ 社区Tab 已归一化为 社区")
```

---

## Fix 3：completion_tokens 截断防护（P1）

### 问题

日志显示一条调用 `completion_tokens=16384, finish_reason=length`，响应被截断（`⚠️ 空/短响应! len=0`），该模块功能点丢失。

### 根因

LLM 输出超过 max_tokens 限制，返回不完整 JSON，解析失败后被丢弃。

### 修复

在 `structured_doc.py` 中 LLM 调用返回后的解析逻辑中，添加截断检测和重试：

```python
def call_llm_with_truncation_guard(prompt, module_name, max_retries=2, **kwargs):
    """带截断检测的 LLM 调用"""
    for attempt in range(max_retries + 1):
        response = call_llm(prompt, **kwargs)

        # 检查 finish_reason
        finish_reason = response.get('finish_reason', '') or ''
        if finish_reason == 'length':
            print(f"[TruncGuard] ⚠️ {module_name} 第{attempt+1}次被截断 "
                  f"(tokens={response.get('completion_tokens', '?')})")
            if attempt < max_retries:
                # 策略：要求 LLM 精简输出，减少描述字数
                prompt = prompt + "\n\n【重要】上次输出被截断。请精简每条功能的描述和验收标准，每条不超过50字。确保JSON完整闭合。"
                continue
            else:
                print(f"[TruncGuard] ❌ {module_name} 截断重试{max_retries}次仍失败，进入AutoSplit")
                return None  # 触发 AutoSplit 逻辑

        return response

    return None
```

在现有的模块生成主循环中，替换直接的 `call_llm` 为 `call_llm_with_truncation_guard`：

```python
# 搜索类似这样的调用:
#   response = call_llm(prompt, ...)
#   result = parse_json(response)
# 改为:
#   response = call_llm_with_truncation_guard(prompt, module_name, ...)
#   if response is None:
#       # 走 AutoSplit 重试
#       ...
#   result = parse_json(response)
```

### 验证

在日志中确认：
- 截断时打印 `[TruncGuard] ⚠️`
- 重试成功时正常继续
- 重试仍截断时进入 AutoSplit（打印 `[TruncGuard] ❌`）

---

## Fix 4：HUD + App 功能数不一致（P2）

### 问题

Excel: HUD 500 + App 305 = 805
HTML DATA: features 808, hud_features 500, app_features 305

`features` 数组 808 ≠ hud + app 的 805，多了 3 条。说明有 3 条功能在 `features` 中但不属于 HUD/App 分类。

### 修复

在 `structured_doc.py` 构建 HTML DATA 时，检查 `features` 列表的构建逻辑：

```python
# 找到构建 DATA 的代码，确认 features 是否是简单的 hud + app 合并
# 如果是独立生成的，需要改为:
data['features'] = data['hud_features'] + data['app_features']

# 或者如果 features 是先生成再拆分的，确认拆分逻辑没有遗漏
# 添加一致性校验:
total = len(data.get('features', []))
hud = len(data.get('hud_features', []))
app = len(data.get('app_features', []))
if total != hud + app:
    print(f"[ConsistCheck] ⚠️ features({total}) ≠ hud({hud}) + app({app}), 差{total - hud - app}条")
    # 强制修正
    data['features'] = data['hud_features'] + data['app_features']
    print(f"[ConsistCheck] 已修正 features = {len(data['features'])}")
else:
    print(f"[ConsistCheck] ✅ features={total} = hud({hud}) + app({app})")
```

---

## 执行顺序

1. Fix 1（Mermaid） — 改动最大但最紧急
2. Fix 2（Excel normalize） — 小改动
3. Fix 3（截断防护） — 中等改动
4. Fix 4（一致性校验） — 小改动

全部改完后：

```bash
git add -A && git commit -m "fix: Round 6 — Mermaid bracket escape, Excel normalize, token truncation guard, feature count consistency"
```

**不要重启服务，Leo 手动重启。**
