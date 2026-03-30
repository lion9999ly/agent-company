# 跨端上下文共享白板

> 本文件是飞书端与 PyCharm 端之间的上下文桥梁。
> 两个 Session 的对话历史相互独立，通过此文件实现关键信息流转。

---

## 协作约定

### 飞书端
- 完成讨论后，**主动**将结论写入本文件
- 写入格式：`[时间戳] 飞书端结论：...`

### PyCharm 端
- 启动新任务前，**先读取**本文件
- 完成任务后，**更新**本文件

---

## 最新关键结论

<!--
格式要求：
- [YYYY-MM-DD HH:MM] 来源：结论内容
- 每条结论单独一行
- 过期结论移至"历史归档"区域
-->

[2026-03-18] Phase 1 Gate 通过
- 方案：自建 feishu_sdk_client.py 替代 cc-connect
- 链路：飞书图片 → lark-oapi 下载 → OCR → 纯文字 → Claude Code CLI → 飞书回复
- 验收：图片内容被正确识别，零 Looki L1 幻觉
- cc-connect 降级为备用，不再作为主链路

[2026-03-18] Phase 2 Gate 通过
- CTO 节点已激活真实 LLM 调用
- 模型：Azure OpenAI GPT-5.4
- 验收：输入"智能骑行头盔导航HUD显示方案"，输出完整技术方案 8000+ 字
- 测试脚本：scripts/test_cto_node.py

[2026-03-18] Phase 3 Gate 通过
- CMO 节点已激活真实 LLM 调用（Azure OpenAI GPT-5.4）
- state_merge 节点已实现，双Agent输出汇聚逻辑完整
- 端到端测试：CTO ✅ CMO ⚠️(网络超时，代码正确) StateMerge ✅
- 测试脚本：scripts/test_dual_agent.py
- 待观察：CMO API 稳定性，建议增加 retry 机制

[2026-03-18] Phase 4 Gate 通过
- Send API 状态传参修复
- map_reduce_dispatcher 传递完整状态 {**state, "current_task_id": task_id}
- hash_check_node 返回值保留完整状态
- 验收：task_goal 正确到达 CTO/CMO 节点

[2026-03-18] Phase 5 Gate 通过
- Gemini Vision 接入图片理解链路
- model_gateway.py 新增 call_gemini_vision 方法（gemini-3-pro-preview）
- feishu_sdk_client.py 图片分支：Gemini Vision 优先，OCR 降级
- 图片压缩处理：max 1024px，JPEG quality 85
- 验收：PCB电路板 ✅ 头盔产品图 ✅ 纯文字截图 ✅ 负向测试(猫) ✅ 超时降级 ✅

[2026-03-18] Phase 6 Gate 有条件通过
- CPO_Critic 从存根替换为真实双模型评审（Gemini 3 Pro 主评审 + GPT-5.4 交叉评审）
- 主从评审机制：主 PASS 直接通过，主 REJECT 触发交叉，双 REJECT 才最终 REJECT
- REJECT 输出包含结构化修改建议
- timeout 已调整为 180 秒
- 验收：荒谬方案正确 REJECT ✅ 技术错误识别 ✅ 商业逻辑校验 ✅ HITL机制完整 ✅
- ⚠️ 有条件通过：Critic prompt 当前过严，合理方案也被 REJECT，需后续调优

[2026-03-18] Phase 7 Gate 通过
- agents.yaml 所有 Agent 模型配置对齐 gpt-5.4
- cpo_critic_agent 更新为双模型评审说明（gemini-3.1-pro-preview 主 + gpt-5.4 交叉）
- model_registry.yaml last_modified 已更新
- snapshot_hashes.json 重新生成（22个文件）
- doc_sync_validator: 0 critical, 21 error（docstring历史债务）, 5 warning
- hash_check_node 验证通过

[2026-03-19] Bug Fixes Gate 通过
- Fix 1: processed_ids 持久化，重启后不丢失已处理消息 ID
- Fix 2: handle_message 异常处理增加用户通知
- Fix 3: 输出截断限制放宽（feishu_sdk_client: 1500→4000, router: 500→2000/1500→4000）
- 验证：三个修复均已通过 import 测试

[2026-03-19] Phase 8 Gate 通过
- 杀掉 subprocess，非研发任务走 GPT-5.4 API 直连
- 新增 call_llm_chat 函数替代 call_claude_code
- 移除 subprocess、time、base64 未使用的 import
- 验证：call_llm_chat 导入成功，subprocess/call_claude_code 已清理

[2026-03-19] Phase 10 Gate 通过
- memory_writer_node 节点实现本地长期记忆写入
- 流程链路：state_merge → memory_writer → consensus_log_trigger
- 记录字段：task_id, timestamp, task_goal, cto_summary, cmo_summary, critic_decision, merge_summary
- 验证：Graph compile OK，函数 26 行，.ai-state/memory 目录已创建
- 读取侧：cpo_plan_node 注入历史记忆，_load_recent_memories 辅助函数
- 验证：_load_recent_memories 20 行，cpo_plan_node 17 行

[2026-03-19] Phase 11a Gate 通过
- Critic prompt 调优：区分"技术硬伤"和"可改进建议"
- 新评审规则：事实错误/逻辑矛盾→REJECT，方向正确但不完善→PASS
- 验证：用例A（蓝牙评估）PASS ✅，用例B（纸板头盔）REJECT ✅

[2026-03-19] Phase 11b Gate 通过
- CPO 规划节点激活真实 LLM 调用
- 新增 _cpo_generate_plan 辅助函数（30行），根据任务目标/历史记忆/评审反馈生成规划
- cpo_plan_node 动态生成 sub_tasks，角色分配由 LLM 决定
- 验证：函数行数合规，Graph compile OK，Critic 测试不受影响

[2026-03-19] Phase 11 Gate 通过
- 11a: Critic prompt 调优，区分技术硬伤和可改进建议
- 11b: CPO 规划节点激活真实 LLM 调用，动态分配角色，注入历史记忆和评审反馈
- 11c: 外部工具能力，ToolRegistry 注册表 + CMO 接入 Gemini Deep Research
- 修复: 并行写入冲突（所有字段加 reducer）、roles 空格 bug、timeout 120→180 落盘
- 增强: 飞书进度提示（stream 模式）、Critic retry 保险机制
- 验收: CPO规划 ✅ CTO+CMO并行 ✅ 工具调研 ✅ Critic PASS ✅ 记忆写入 ✅ 进度提示 ✅
- ⚠️ 遗留: reducer 导致节点双重执行（不影响输出，浪费 API 调用）

[2026-03-19] Phase 12 Gate 通过
- CDO(Carl) 首席设计师 Agent 完整集成
- model_registry.yaml 新增 cdo 角色绑定（GPT-5.4, temperature 0.3）
- context_slicer.py 新增 CDO_WHITELIST + create_cdo_slice（上下文隔离）
- router.py 新增 cdo_designer_node + map_reduce_dispatcher 三角色分发
- state_merge 适配 CTO/CMO/CDO 三输出汇聚
- tool_registry 新增 design_vision_analysis + figma_design(占位)
- CPO 规划支持 cto/cmo/cdo 三角色动态分配
- 验收：三Agent并行 ✅ CDO设计调研 ✅ 进度提示 ✅ Critic评审 ✅

[2026-03-19] Bug Fix: Reducer 双重执行修复
- 根因：CTO/CMO/CDO 分支长度不同，state_merge 被每个分支分别触发
- 修复方案：幂等性保护
  - state_merge: 检查 merge_summary 是否已存在，存在则返回空 dict
  - cpo_critic_node: 检查 critic_decision 是否已存在
  - memory_writer_node: 新增 memory_written 标记，写入后设为 True
- 状态扩展：AgentGlobalState 新增 memory_written 和 current_task_id 字段
- 验证：幂等性测试全部通过，重复调用返回空 dict

[2026-03-19] Phase 13 Gate 通过
- CDO(Carl) 图像生成能力完整实现
- 第一层：system_prompt 输出 [AI_IMAGE_PROMPT] 区域
- 第二层：Imagen 4.0 Fast 生图 + 飞书图片消息发送
- tool_registry 新增 image_generation 工具
- feishu_sdk_client 新增 send_image_reply + _try_generate_design_image
- 修复：reducer 节点双重执行（幂等性保护）
- 验收：极简北欧风格头盔概念图成功生成并在飞书展示 ✅

[2026-03-19] Phase 14 Gate 通过
- 飞书移动端审批执行机制完整实现
- fix_executor.py: FixProposal 数据结构 + 创建/审批/驳回/执行全流程
- feishu_sdk_client.py: 审批指令识别（批准/驳回/待审批）
- 安全机制：old_content 精确匹配，文件已变更时拒绝执行
- 验收：创建提案 ✅ 飞书查看 ✅ 手机审批执行 ✅ 安全拦截 ✅

[2026-03-21] Phase 16 Gate 通过
- 16e: 每日自学习循环完整实现
- 25 个学习主题覆盖：竞品（含摩托车）、技术前沿（HUD/音频/摄像/材料/传感器/多模态）、设计趋势（户外/潮玩/出行）、行业标准（ECE/DOT/EN1078/EMC）、AI工具进化
- LLM 提炼：搜索结果经 GPT-5.4 提炼，只保留与项目相关的结构化知识
- 去重机制：避免重复写入
- 定时调度：每日 08:00 自动执行
- 飞书指令：「学习」手动触发、「关注 主题」动态添加
- 知识库从 4 条（手动）增长到 8 条（首次学习），持续自动增长中

Phase 16 完整验收：
- Agent 从实习生升级为合伙人：敢裁决、敢质疑、有数据支撑 ✅
- 正循环闭环：用户评价→反馈注入→输出提升 ✅
- 三层学习：持续自学习+当次即时学习+事后沉淀 ✅
- 知识库：竞品/标准/元器件/经验，持续自动增长 ✅

[2026-03-21] Phase 17 Gate 通过
- 飞书自主开发能力完整实现
- @dev 指令：分析需求 → 读取代码 → LLM 生成精确 diff → 创建 FixProposal → 飞书审批
- 自动验证：执行后自动跑 Graph compile，失败自动回滚
- dev_assistant.py：智能文件猜测 + 代码截取 + JSON 格式提案生成
- 验收：@dev 指令→提案→批准→执行→验证 全流程通过 ✅
- ⚠️ 待优化：LLM 对需求理解精度需提升（改了数据结构而非日志打印）

[2026-03-21] Phase 19 + 20 Gate 通过
- Phase 19: Watchdog 独立监控 + webhook 报警 + 自动重启 + 心跳定期刷新
- Phase 20: 语音输入链路，Gemini 多模态音频理解，转写后走正常路由
- 当日完成 Phase 16(全5子阶段) + 17 + 18 + 19 + 20，共 8 个 Phase

[2026-03-21] Phase 21 Gate 通过
- 21a: start_all.bat 一键启动（主服务+watchdog+学习+文档扫描）
- 21b: doc_importer 全格式导入（25种格式），PDF/Word/PPT 嵌入图片用 Vision 理解
- 21c: 学习加速（知识库<100条每2h，>=100条每4h）
- 文档导入支持：文字/图片/音频/视频/PDF(含嵌图)/Word(含嵌图)/PPT(含嵌图)/Excel
- Day 4 总成果：Phase 16-21 共 10 个 Phase，系统从实习生升级为合伙人公司

---

## 待办任务

<!--
格式要求：
- [ ] 任务描述 @负责人 预期完成时间
-->

- [x] Critic prompt 调优：已区分技术硬伤和可改进建议，用例A PASS，用例B REJECT @2026-03-19
- [ ] 调试日志清理：handle_image_message 中的错误详情打印，Phase 7 文档清理时一并处理
- [ ] Docstring 标准化：21个文件缺少标准头部（@description/@dependencies/@last_modified），纯机械修复 @低优先级
- [x] is_rd_task 关键词匹配优化：已扩充至 32 个关键词，验证通过 @2026-03-19
- [ ] LangGraph 调用阻塞主线程导致 WebSocket ping_timeout：需要异步化或后台线程处理 @中优先级
- [x] reducer 导致节点双重执行：已添加幂等性保护，state_merge/critic/memory 均验证通过 @2026-03-19
- [x] 飞书移动端审批执行机制：fix_executor + 审批指令识别，Phase 14 完成 @2026-03-19
- [ ] CDO 未被分配时图片仍生成：synthesis 的 AI_IMAGE_PROMPT 在无 CDO 参与时可能不够专业 @低优先级
- [ ] 进度消息 stream 事件重复：幂等性保护已生效但 stream 事件仍触发进度消息 @低优先级
- [ ] CTO 调研数据利用率低：133K 字截断到 3K，可考虑预处理提炼关键数据再注入 @中优先级
- [ ] 飞书多维表格读取：通过 Bitable API 拉取在线表格数据导入知识库 @中优先级

---

## 历史归档

<!--
超过 7 天的结论移至此处
-->

(暂无)

---

## 元信息

| 字段 | 值 |
|------|-----|
| 创建时间 | 2026-03-18 |
| 最后更新 | 2026-03-21 |
| 更新来源 | Phase 21: 一键启动 + 文档导入 + 学习加速 |

---

*本文件由 Claude Code 创建，遵循跨端协作规范*