# 🛑 系统质量红线与硬阈值规范 (Quality Redlines)

> **[SYSTEM DIRECTIVE]**
> 本文件定义了本虚拟公司产出物的所有“不可逾越之红线”。
> 任何 Agent（特别是 Coder 和 Reviewer）在生成或审查代码时，必须将此文件作为唯一判例法。拦截脚本 (Hooks) 将基于以下量化指标执行 exit code 1 的无情打回。

## 1. 代码质量硬阈值 (Code Quality Thresholds)
* **文件体积红线**：单文件绝对禁止超过 **800 行**（包含注释与空行）。超限必须拆分模块。
* **函数体积红线**：单个函数/方法绝对禁止超过 **30 行**。超限必须提取子函数 (Extract Method)。
* **圈复杂度红线**：
    * 代码嵌套层数绝对禁止超过 **3 层**（例如：`if` 内套 `for` 内套 `if` 即达上限）。
    * 单函数内逻辑分支（`if/elif/else/switch`）绝对禁止超过 **3 个**。
* **强类型红线**：所有 Python 代码必须 100% 包含 Type Hints（类型注解）。严禁在业务逻辑中使用 `Any`（除数据结构解析的极特殊情况外，且必须带注释说明）。

## 2. 文档与规范同构红线 (Documentation Thresholds)
* **模块级红线**：任何新增的业务模块（Folder），必须在同级目录下包含 `README.md`。必须包含：模块功能一句话描述、核心成员文件清单、对外暴露的 API/函数列表。
* **文件级红线**：任何新增的 `.py` 或 `.ts` 文件，顶部必须包含标准化 Docstring，强制包含以下字段：
    * `@description`: 文件核心职责
    * `@dependencies`: 依赖的内部模块
    * `@last_modified`: YYYY-MM-DD
* **脱节判定**：PR/合并请求中，如果有代码逻辑变更，但未检测到对应 `README.md` 或 Docstring 的 diff，判定为“文档脱节”，直接打回。

## 3. 安全硬阈值 (Security Thresholds)
* **高危函数黑名单**：代码中绝对禁止出现 `eval()`, `exec()`, `os.system()`, `subprocess.Popen(shell=True)`。一旦检测到，触发最高级系统告警。
* **依赖库白名单**：CTO 团队只能使用 `03-mcp-tools-registry.md` 或全局环境预设好的依赖包。严禁 Agent 在代码中自行 `pip install` 或引入未经审批的第三方库。
* **密钥硬编码拦截**：任何包含 `secret`, `key`, `password`, `token` 字样的变量赋值，若其值为明文硬编码（而非从环境变量 `os.getenv` 读取），拦截脚本将立即阻断。

## 4. 性能与健壮性硬阈值 (Performance Thresholds)
* **网络请求红线**：所有涉及外部 API 调用的代码，必须且必定包含 `timeout` 参数（默认最大 10 秒），绝对禁止无限期挂起的网络请求。
* **异常捕获红线**：禁止使用裸露的 `except:` 或 `except Exception: pass`。必须精确捕获特定异常，并将错误信息标准化写入系统日志或 State 中的 `error_traceback`。

## 5. 红线豁免管控与边界声明 (Exemptions & Boundaries)

* **🚫 绝对不可豁免区 (Zero Tolerance)**：
  * 第 3 节中所有的【安全硬阈值】（如禁止 `eval`、密钥硬编码、非白名单依赖）。
  * 任何试图绕过或修改 `.ai-architecture/` 目录权限的操作。
  * 任何违反 Append-Only 规则的写入尝试。
  * *注：若 Agent 触碰此区域，不仅拦截，立即触发系统挂起与安全告警。*

* **⚠️ 附条件可豁免区 (Restricted Exemptions)**：
  * 单文件 800 行限制（仅限自动生成的协议代码、大型数据模型定义）。
  * 文档脱节判定（仅当修改不涉及对外 API、出入参结构、核心业务逻辑时）。
  * *注：Agent 必须在 `.ai-state/` 目录下生成标准化豁免申请，由人类审批通过后，本次流转方可放行。严禁 Agent 自行豁免。*