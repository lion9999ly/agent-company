# Day 17 系统全量审计 - Part 2: 圆桌全链路 + 夜间管道

## B. 圆桌全链路

### 11. scripts/roundtable/__init__.py 完整内容

**公开接口：**
- run_task / run_task_by_topic
- TaskSpec, load_task_spec
- Crystallizer, Roundtable, Generator, Verifier, MetaCognition, Resilience

### 12. scripts/roundtable/roundtable.py 完整内容

**四层飞轮：**
- Phase 1: 独立思考（并行）
- Phase 2: 方案生成（proposer 串行）
- Phase 3: 定向审查（reviewers 并行）
- Phase 4: Critic 终审

**v2 新增：**
- 收敛分层：方案层最多 3 轮
- 震荡检测：P0 数量不下降时锁定基线
- 快照保留：roundtable_runs/{topic}_{timestamp}/

**已知问题：**
- 文件超过 800 行（已豁免，待独立重构）

### 13. scripts/roundtable/generator.py 完整内容

**分段生成策略：**
- 段1: CSS + HTML 骨架
- 段2: 状态机 JS
- 段3: 渲染函数
- 段4: 自动剧本 + 时间轴
- 段5: 沙盒面板 + 控制层

**v2 新增：**
- generator_input_mode: raw_proposal / executive_summary / auto
- 分段重试机制

### 14. scripts/roundtable/verifier.py 完整内容

**三层规则：**
- global.json: 全局通用规则
- type_{output_type}.json: 输出类型专用规则
- TaskSpec.auto_verify_rules: 任务专用规则

**规则类型：**
- no_external_deps
- keyword_exists / keyword_count
- file_size_range / line_count_range
- html_valid / json_parseable

### 15. scripts/roundtable/task_spec.py 完整内容

**TaskSpec 数据类：**
- topic, goal, acceptance_criteria
- proposer, reviewers, critic
- authority_map
- input_docs, kb_search_queries
- role_prompts
- output_type, output_path
- generator_input_mode (v2)
- auto_verify_rules (v2)

**加载逻辑：**
- 精确匹配 → 归一化匹配 → 子串匹配 → JSON 内部 topic 字段匹配

### 16. scripts/roundtable/verdict_parser.py 完整内容

**交互流程：**
1. 圆桌完成后 10 分钟内用户发的消息自动当评判处理
2. LLM 解析为结构化缺陷
3. 判断能否转化为规则
4. 飞书展示规则草案
5. 用户回复"确认"后入库

### 17. scripts/roundtable/crystallizer.py 完整内容

**三步流程：**
1. 读取核心锚点文档 + 已有决策备忘录
2. 从 KB 搜索相关条目并提炼
3. 按角色分片上下文

**角色特定上下文：**
- CMO: 用户画像 + 竞品数据
- CTO: 技术约束 + 供应商数据
- CDO: 设计原则 + 视觉参考
- Critic: 验收标准 + 所有角色摘要

---

## C. 夜间管道

### 18. scripts/auto_learn.py 完整内容

**设计：**
- 每 30 分钟自动触发
- 只跑 Layer 1（搜索）+ Layer 2（提炼）+ 直接入库
- 不走 Agent 分析，不生成报告
- 已覆盖的搜索词不会重复搜索（7 天后过期重试）

**缺口检测策略：**
1. 优先从决策树的 blocking_knowledge 获取缺口
2. 从 research_task_pool.yaml 获取未完成任务
3. 域分布不均检查
4. 时效性检查（超过 30 天未更新）
5. 产品锚点覆盖检查

### 19. scripts/tonight_deep_research.py 完整内容

**向后兼容入口：**
- 所有实现已迁移到 scripts/deep_research/ 包
- 公开接口重导出：run_all, run_deep_learning, run_research_from_file

### 20. scripts/competitor_monitor.py 完整内容

**监控配置：**
- 6 层监控范围
- 时间过滤：current_year = true
- 输出规则：no_update_no_push = true

### 21. scripts/feishu_handlers/notify_rules.py 完整内容

**通知降噪配置：**
- deep_research: start + complete + error（静默 progress）
- competitor_monitor: 仅 has_update
- auto_learn: 仅 error（静默运行）
- roundtable: start + convergence + complete + error

---

**续接 Part 3/3**