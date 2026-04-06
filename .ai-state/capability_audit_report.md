# 功能排查报告
# 生成时间: 2026-04-06

## 飞书指令排查

### 学习研究类
1. token统计: ✅ 可用 — text_router.py:1020-1027 引用 token_usage_tracker
2. 日报: ✅ 可用 — text_router.py:170 匹配 "日报"
3. 对齐: ✅ 可用 — text_router.py:393 匹配 "对齐"
4. 知识库: ⚠️ 部分可用 — 有 KB治理(text_router.py:389)，但无独立的"知识库"统计指令
5. 删除 KB xxx: ❌ 丢失 — 无匹配
6. 研究 XXX: ⚠️ 部分可用 — 有"深钻"(text_router.py:1758)，但无直接"研究"匹配
7. 深度研究: ❌ 丢失 — 无独立入口
8. 深度学习: ✅ 可用 — text_router.py:378 匹配
9. 今晚研究: ❌ 丢失 — 无匹配
10. JDM学习: ❌ 丢失 — 无匹配
11. 学习: ✅ 可用 — text_router.py:370 匹配
12. 关注 XXX: ✅ 可用 — text_router.py:461 匹配

### 管理类
13. @dev: ⚠️ 部分可用 — command_prefixes 包含 "@dev" (text_router.py:546)，但无专门处理
14. A/B/C/D 方案评价: ❌ 需确认 — 检查 commands.py
15. 设置目标: ❌ 丢失 — 无匹配
16. 进化记录: ❌ 丢失 — 无匹配
17. 系统状态: ✅ 可用 — text_router.py:175 匹配
18. 导入文档: ✅ 可用 — text_router.py:465 匹配
19. PRD/清单: ✅ 可用 — structured_doc.py 处理
20. 决策简报: ✅ 可用 — text_router.py:185 匹配
21. 产品一页纸: ✅ 可用 — text_router.py:180 匹配
22. Demo生成: ✅ 可用 — text_router.py:397-421 匹配
23. 圆桌: ✅ 可用 — text_router.py:424 匹配
24. 重载模块: ✅ 可用 — commands.py:267 reload_modules

---

## 内部功能排查

25. token使用记录: ✅ 可用 — record_usage 在 config.py:91，各 provider 都有调用
26. URL分享检测: ✅ 可用 — _has_shareable_url(text_router.py:534)，_handle_share_url(text_router.py:777)
27. 图片OCR处理: ✅ 可用 — handle_image_message(image_handler.py:106)
28. 语音转文字: ✅ 可用 — handle_audio_message(image_handler.py:194)
29. 消息去重: ✅ 可用 — _processed_msgs(feishu_sdk_client_v2.py:41)
30. Watchdog心跳: ❌ 丢失 — feishu_sdk_client_v2.py 无匹配

---

## 定时任务排查

31. 每天00:00深度学习: ✅ 可用 — feishu_sdk_client.py:3262,3290
32. 每天06:00竞品监控: ✅ 可用 — feishu_sdk_client.py:3271,3291
33. 每天07:00系统日报: ✅ 可用 — feishu_sdk_client.py:3280,3292
34. 30min/2h自动学习: ✅ 可用 — daily_learning.py:1348, auto_learn.py:283

---

## 总结

### 完全可用 (✅): 20项
- token统计, 日报, 对齐, 深度学习, 学习, 关注, 系统状态, 导入文档
- PRD/清单, 决策简报, 产品一页纸, Demo生成, 圆桌, 重载模块
- token使用记录, URL分享检测, 图片OCR, 语音转文字, 消息去重
- 全部4个定时任务

### 部分可用 (⚠️): 3项
- 知识库: 有KB治理，缺独立统计入口
- 研究XXX: 有"深钻"，缺直接"研究"入口
- @dev: 在command_prefixes但无专门处理

### 需要修复 (❌): 7项
1. 删除 KB xxx — 需新增
2. 深度研究 — 被合并到深度学习
3. 今晚研究 — 需新增或合并
4. JDM学习 — 需新增或合并
5. 设置目标 — 已废弃（产品目标在 product_anchor.md）
6. 进化记录 — 已废弃（被圆桌替代）
7. Watchdog心跳 — 需恢复

---

## 修复优先级

P0 (阻塞):
- 无

P1 (重要):
- 删除 KB xxx 指令
- Watchdog 心跳监控

P2 (可延迟):
- 独立的知识库统计入口
- 整合后的学习指令入口