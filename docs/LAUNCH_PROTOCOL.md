# DeepFlow 启动协议 v2.0

> **日期**: 2026-04-22 | **版本**: 2.0 | **状态**: 修复后
>
> 本文档规定主 Agent 如何正确 spawn Orchestrator Agent，确保 PipelineEngine 被正确执行。

---

## ❌ 错误方式（导致本次失败）

**问题**: 主 Agent 手动拼了一个通用 task，Orchestrator 作为通用 Agent 执行，绕过代码。

```python
# ❌ 错误：手动拼通用 task
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="orchestrator",
    task="""
你是 DeepFlow Orchestrator Agent...
读取 /Users/allen/.openclaw/workspace/.deepflow/prompts/pipeline_engine_orchestrator.md
按指令执行完整管线...
""",
    timeout_seconds=600
)
```

**后果**:
- Orchestrator 没有执行 `orchestrator_agent.py` 的代码
- PipelineEngine 被完全绕过
- Orchestrator 手动 spawn Workers，无 ResilienceManager/QualityGate
- 执行到一半中断（Auditor 阶段未完成）

---

## ✅ 正确方式

**核心原则**: Orchestrator 必须执行 `orchestrator_agent.py` 的代码，创建 PipelineEngine 并调用 `engine.run()`。

**关键修正（2026-04-22）**: 必须通过 `env` 参数传递环境变量，子 Agent 环境不会自动继承。

```python
# ✅ 正确：让 Orchestrator 执行代码
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="orchestrator",
    task="""
# DeepFlow Orchestrator Agent 执行脚本

你是 DeepFlow V1.0 Orchestrator Agent。

## 执行步骤

1. 读取 /Users/allen/.openclaw/workspace/.deepflow/orchestrator_agent.py
2. 按代码逻辑执行：
   - 初始化 OrchestratorAgent（从环境变量读取配置）
   - 调用 agent.run() 执行完整管线
   - agent.run() 内部会：
     a. step1: 委托 PipelineEngine 执行 DataManager
     b. step2: PipelineEngine.run() 执行所有 stages
     c. step3: 保存结果
3. 所有 sessions_spawn 调用必须设置 label 参数
4. 最终报告写入 blackboard/{session_id}/final_report.md

## 关键规则
- ✅ 必须执行 orchestrator_agent.py 的代码
- ✅ 必须创建 PipelineEngine 并调用 engine.run()
- ✅ PipelineEngine 自动执行所有 stages（包括 data_manager）
- ✅ 禁止绕过 PipelineEngine，手动 spawn Workers
- ✅ 禁止自行生成报告替代 Summarizer

## 禁止
- ❌ 不得跳过 PipelineEngine，手动 spawn Workers
- ❌ 不得简化或改写执行流程
- ❌ 不得自行写报告替代 Summarizer Agent
""",
    env={
        "DEEPFLOW_DOMAIN": "investment",
        "DEEPFLOW_CODE": "688652.SH",
        "DEEPFLOW_NAME": "京仪装备"
    },
    timeout_seconds=600
)
```

---

## 为什么必须这样

| 对比项 | 错误方式（通用 Agent） | 正确方式（代码执行） |
|--------|----------------------|---------------------|
| PipelineEngine | ❌ 被绕过 | ✅ 正常执行 |
| ResilienceManager | ❌ 无重试/熔断 | ✅ 完整支持 |
| QualityGate | ❌ 无评分 | ✅ 实际评分 |
| FSM 状态机 | ❌ 无状态管理 | ✅ 完整状态机 |
| 收敛检测 | ❌ 无收敛 | ✅ ≥2 轮检测 |
| session_id | ❌ 不一致 | ✅ 统一生成 |
| DataManager | ❌ 手动 spawn | ✅ Pipeline 第一个 stage |

---

## 修复记录

| 日期 | 修复项 | 状态 |
|------|--------|------|
| 2026-04-22 | 修复启动协议，明确必须执行 orchestrator_agent.py | ✅ 完成 |
| 2026-04-22 | 修复 orchestrator_agent.py main() 函数，确保 Agent 环境正确获取 sessions_spawn | ✅ 完成 |
| 2026-04-22 | 修复 PipelineEngine spawn_agent 构建 data_manager task | ✅ 完成 |

---

*契约笼子验证: P0=0*
