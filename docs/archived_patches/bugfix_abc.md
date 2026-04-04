# Bug A/B/C 修复指令 — structured_doc.py

> 按顺序执行，每个 bug 独立，互不依赖

---

## Bug A: `_score_module` 中 re.search 收到 list 崩溃

**根因**: `_score_module` 对 `acceptance`/`description` 等字段做正则匹配，但这些字段可能是 list（LLM 返回的 JSON 未被上游完全转换）。

**修复**: 在 `_score_module` 函数开头加字段类型防御。

找到 `_score_module` 函数定义（约 line 1560 附近），在函数体最前面、任何 `re.search` 调用之前，插入以下代码：

```python
def _score_module(rows):
    """质量优先评分"""
    # ===== Bug A fix: 确保所有待正则匹配的文本字段是 string =====
    def _ensure_str(val):
        if isinstance(val, list):
            return ', '.join(str(v) for v in val)
        if isinstance(val, dict):
            return json.dumps(val, ensure_ascii=False)
        if val is None:
            return ''
        return str(val)
    
    for row in rows:
        for key in ('acceptance', 'description', 'dependencies', 'interaction', 'name', 'priority'):
            if key in row:
                row[key] = _ensure_str(row[key])
    # ===== End Bug A fix =====
    
    # ... 后面是原有的评分逻辑，不动 ...
```

**同时**，在 `_process_in_background` 中调用 `_score_module` 的地方（约 line 2623），加 try-except 兜底，避免评分崩溃导致整个对比中断：

```python
# 找到类似这样的代码:
#   old_score = _score_module(old)
#   new_score = _score_module(new)
# 改为:

try:
    old_score = _score_module(old)
except Exception as e:
    print(f"  [Score] 旧版评分异常: {e}, 默认0分")
    old_score = 0

try:
    new_score = _score_module(new)
except Exception as e:
    print(f"  [Score] 新版评分异常: {e}, 默认0分")
    new_score = 0
```

---

## Bug B: 复杂模块自动拆解（替代调高 max_tokens）

**根因**: "AI语音助手"、"主动安全预警提示"等模块功能复杂度高，单次 LLM 调用输出超 4096 token 被截断。应拆成子任务并行生成后合并。

### Step 1: 添加复杂度判断函数

在 `_gen_one` 函数之前，添加：

```python
def _estimate_complexity(module_name: str, user_prompt: str, kb_data_points: str, prev_version_rows: list = None) -> list[str]:
    """
    判断模块是否需要拆解。返回子模块名列表。
    如果不需要拆解，返回 [module_name] 本身（单元素列表）。
    """
    reasons = []
    
    # 信号1: 知识库数据点超过 700 字 → 说明涉及面广
    if len(kb_data_points) >= 700:
        reasons.append('kb_dense')
    
    # 信号2: 上一版该模块条目数 >= 25
    if prev_version_rows and len(prev_version_rows) >= 25:
        reasons.append('prev_large')
    
    # 信号3: 用户 prompt 中该模块相关描述包含多个子项（用顿号/逗号/斜杠分隔）
    # 从 user_prompt 中提取该模块相关片段
    import re
    # 找模块名后面跟着的内容（到下一个换行或模块）
    pattern = re.escape(module_name) + r'[：:]\s*(.+?)(?:\n|$)'
    match = re.search(pattern, user_prompt)
    if match:
        sub_items = re.split(r'[、,，/]', match.group(1))
        if len(sub_items) >= 3:
            reasons.append('multi_sub_items')
    
    # 需要至少 2 个信号才触发拆解
    if len(reasons) < 2:
        return [module_name]
    
    # === 自动拆解逻辑 ===
    # 用轻量方式拆：基于用户 prompt 中的子项
    if match:
        sub_items = [s.strip() for s in re.split(r'[、,，/]', match.group(1)) if s.strip()]
        # 每 2-3 个子项合成一个子模块
        chunks = []
        chunk_size = max(2, len(sub_items) // 3 + 1)
        for i in range(0, len(sub_items), chunk_size):
            chunk = sub_items[i:i + chunk_size]
            sub_name = f"{module_name}-{'与'.join(chunk[:2])}"
            chunks.append(sub_name)
        if chunks:
            print(f"  [AutoSplit] {module_name} 拆解为 {len(chunks)} 个子模块: {chunks}")
            return chunks
    
    # 兜底：按通用维度拆 3 份
    default_splits = [
        f"{module_name}-核心功能",
        f"{module_name}-交互与状态",
        f"{module_name}-异常与边界",
    ]
    print(f"  [AutoSplit] {module_name} 按默认维度拆解为 3 个子模块")
    return default_splits
```

### Step 2: 添加子模块合并函数

紧接着添加：

```python
def _merge_sub_modules(parent_name: str, sub_results: list[list[dict]]) -> list[dict]:
    """
    将多个子模块的生成结果合并回父模块，去重。
    """
    merged = []
    seen_names = set()
    
    for sub_rows in sub_results:
        for row in sub_rows:
            # 统一挂回父模块
            if row.get('level') == 'L1':
                row['name'] = parent_name
                row['module'] = parent_name
            else:
                row['module'] = parent_name
            
            # 按 name 去重
            name = row.get('name', '')
            if name and name not in seen_names:
                seen_names.add(name)
                merged.append(row)
            elif not name:
                merged.append(row)
    
    print(f"  [Merge] {parent_name}: {sum(len(r) for r in sub_results)} 条合并去重为 {len(merged)} 条")
    return merged
```

### Step 3: 在调用 `_gen_one` 的并行循环中集成

找到主生成循环（大约在 `_process_in_background` 中，提交 `_gen_one` 到 ThreadPoolExecutor 的地方）。当前代码大致结构：

```python
# 伪代码 - 找到类似逻辑的位置
for module_name in modules:
    futures.append(executor.submit(_gen_one, module_name, ...))
```

改为：

```python
# 获取上一版数据（如果有的话，应该已有变量）
prev_modules_map = {}  # 如果已有上一版数据的 dict，直接用

for module_name in modules:
    # Bug B: 复杂模块自动拆解
    prev_rows = prev_modules_map.get(module_name, [])
    sub_modules = _estimate_complexity(
        module_name=module_name,
        user_prompt=user_prompt,  # 用户原始输入
        kb_data_points=kb_cache.get(module_name, ''),  # 知识库数据点缓存
        prev_version_rows=prev_rows
    )
    
    if len(sub_modules) == 1:
        # 不需要拆解，正常生成
        futures.append((module_name, False, executor.submit(_gen_one, module_name, ...)))
    else:
        # 拆解模式：每个子模块独立提交
        sub_futures = []
        for sub_name in sub_modules:
            sf = executor.submit(_gen_one, sub_name, ...)
            sub_futures.append(sf)
        futures.append((module_name, True, sub_futures))

# 收集结果时也需要对应修改：
all_rows = []
for item in futures:
    if item[1] is False:
        # 普通模块
        module_name, _, future = item
        try:
            rows = future.result(timeout=120)
            if rows:
                all_rows.extend(rows)
                print(f"  ✅ {module_name}: +{len(rows)} 条")
        except Exception as e:
            failed.append(module_name)
            print(f"  ❌ {module_name}: {e}")
    else:
        # 拆解模块 - 收集所有子结果后合并
        module_name, _, sub_futures_list = item
        sub_results = []
        any_success = False
        for sf in sub_futures_list:
            try:
                rows = sf.result(timeout=120)
                if rows:
                    sub_results.append(rows)
                    any_success = True
            except Exception as e:
                print(f"  ⚠️ {module_name} 子模块失败: {e}")
        
        if any_success:
            merged = _merge_sub_modules(module_name, sub_results)
            all_rows.extend(merged)
            print(f"  ✅ {module_name}: +{len(merged)} 条 (拆解合并)")
        else:
            failed.append(module_name)
            print(f"  ❌ {module_name}: 所有子模块均失败")
```

> **注意**: 以上是逻辑骨架，CC 需要对照实际代码中的变量名（`user_prompt`、`kb_cache`、executor 提交的参数列表）做适配。核心逻辑不变：判断 → 拆 → 并行生成 → 合并回父模块。

---

## Bug C: JSON 控制字符导致解析失败

**根因**: LLM 输出的 JSON 字符串值内含未转义的控制字符（`\n`、`\t`、`\r` 等）。

**修复**: 在 `_gen_one` 中 `json.loads()` 调用之前，清洗响应文本。

找到 `_gen_one` 函数中做 JSON 解析的位置（应该有 `json.loads(response_text)` 或类似代码），在其前面加：

```python
import re

# ===== Bug C fix: 清洗 LLM 输出中的控制字符 =====
def _clean_json_text(text: str) -> str:
    """清洗 JSON 文本中的非法控制字符，保留正常换行"""
    # 先提取 JSON 数组/对象部分
    start = text.find('[')
    end = text.rfind(']')
    if start == -1 or end == -1:
        start = text.find('{')
        end = text.rfind('}')
    if start != -1 and end != -1:
        text = text[start:end + 1]
    
    # 处理 JSON 字符串值内部的换行符
    # 在 JSON 字符串值内（双引号之间），将裸换行替换为 \\n
    # 简单有效的方式：直接替换所有控制字符为空格
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
    
    return cleaned
# ===== End Bug C fix =====

# 然后在 json.loads 之前调用:
response_text = _clean_json_text(response_text)
try:
    data = json.loads(response_text)
except json.JSONDecodeError:
    # 二次尝试: strict=False 模式
    try:
        data = json.loads(response_text, strict=False)
    except json.JSONDecodeError as e:
        print(f"  [GenOne] {module_name} JSON 解析失败: {e}")
        print(f"  [GenOne] {module_name} JSON 片段: {response_text[:200]}")
        return []
```

**注意**: `_clean_json_text` 可以定义为模块级函数（放在文件顶部的工具函数区），因为重试逻辑中也会用到。确保所有调用 `json.loads` 解析 LLM 响应的地方都先经过 `_clean_json_text`。全文搜索 `json.loads` 确认覆盖以下位置：
- `_gen_one` 主路径
- 重试路径（精简模式）
- 任何其他解析 LLM JSON 响应的位置

---

## 验证清单

修完后重启服务，再跑一次相同的 PRD 请求，检查：

- [ ] `_score_module` 不再崩溃，逐模块对比完整执行完 30+ 模块
- [ ] "AI语音助手"、"主动安全预警提示" 首轮通过（看日志中是否有 `[AutoSplit]` 输出）
- [ ] "速度" 模块 JSON 解析成功（不再出现 `Invalid control character`）
- [ ] 总耗时仍在 10-15 分钟区间（拆解不应显著增加耗时，因为子模块并行）
- [ ] 最终产出条目数 ≥ 650（上一版 671，这次应持平或更多）
