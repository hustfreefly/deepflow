# 契约笼子：端到端测试 - 中芯国际 2026 业绩预期分析

## 目标
验证改造后的 DeepFlow V4.0 管线（搜索配置化 + 自动发送报告）完整运行

## 测试范围
- Master Agent 初始化（含 SendReporter task）
- Orchestrator Agent 调度 7 个 Phase
- 搜索配置化（Gemini 2.5 Flash / DuckDuckGo / Tushare）
- 自动发送 Summary 报告到飞书

## 验收标准
- [ ] DataManager 完成
- [ ] Planner 完成
- [ ] 6 个 Researchers 完成
- [ ] 3 个 Auditors 完成
- [ ] Fixer 完成
- [ ] Summarizer 完成
- [ ] SendReport 完成（自动发送飞书）
- [ ] 收到飞书投资摘要消息

## 执行步骤
1. python3 core/master_agent.py --code 688981.SH --name 中芯国际 --industry 半导体制造
2. sessions_spawn Orchestrator Agent
3. sessions_yield 等待完成
4. 验证飞书消息收到

## 预期输出
- final_report.md
- 飞书消息：评级、目标价、置信度、核心逻辑
