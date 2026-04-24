# 契约笼子：投资场景任务结束自动发送 Summary 报告

## 目标
投资场景管线执行完成后，自动发送 Summary 报告到飞书，实现任务完全闭环

## 背景
- 当前管线：DataManager → Planner → Researchers → Auditors → Fixer → Summarizer → 结束
- 缺少：Summarizer 完成后自动发送报告到用户
- 现状：需要用户手动触发发送

## 需求
- 管线完成后，自动读取 final_report.md 和 summarizer_output.json
- 自动发送飞书消息给用户
- 发送内容：投资建议摘要（评级、目标价、置信度、核心逻辑）
- 无需用户干预，完全自动化

## 实现方案

### 方案A：Summarizer Prompt 中植入发送指令（简单）
- 在 summarizer.md Prompt 中添加发送指令
- Summarizer Agent 完成后执行发送
- 优点：简单，无需改代码
- 缺点：Agent 可能没有 message 工具权限

### 方案B：Master Agent 在生成任务时添加发送任务（推荐）
- 在 master_agent.py 的 execution_plan.json 中添加 Phase 7: SendReport
- 添加 send_reporter.md Prompt
- SendReport Worker 读取 final_report.md 并发送
- 优点：架构清晰，符合现有管线模式
- 缺点：需要新增一个 Worker

### 方案C：Orchestrator 完成后自动发送（最自动化）
- 修改 orchestrator_agent.py 指南
- Phase 6 Summarizer 完成后，Orchestrator 自动发送报告
- 优点：最自动化，不增加 Worker 数量
- 缺点：Orchestrator 职责变复杂

## 推荐方案：C（Orchestrator 自动发送）

理由：
1. 无需新增 Worker，利用 Orchestrator 已有权限
2. Orchestrator 已经知道所有 Worker 完成状态
3. 发送是"调度"行为，符合 Orchestrator 职责

## 实现步骤
1. 修改 orchestrator_agent.py 指南，添加 Phase 7: SendReport
2. 修改 master_agent.py，在 execution_plan 中添加 send_report 阶段
3. 创建 prompts/investment/send_reporter.md
4. 修改 task_builder.py 的 build_summarizer_task 或添加 build_send_reporter_task
5. 验证：完整跑一次管线，检查飞书是否收到消息

## 验收标准
- [ ] 管线完成后自动发送飞书消息
- [ ] 消息包含：评级、目标价、置信度、核心逻辑摘要
- [ ] 无需用户手动触发
- [ ] 发送失败不阻塞管线（记录错误继续）

## 文件变更
- `core/orchestrator_agent.py` - 添加发送阶段指南
- `core/master_agent.py` - execution_plan 添加 send_report
- `core/task_builder.py` - 添加 build_send_reporter_task
- `prompts/investment/send_reporter.md` - 新建

## 报告格式
```markdown
# 投资分析完成：{company_name}({company_code})

**评级**: {rating} | **目标价**: ¥{target_price} | **置信度**: {confidence}

**核心逻辑**:
{executive_summary}

**关键风险**:
{top_risks}

**完整报告**: {final_report_path}
```
