# DeepFlow 快速执行卡（半屏速查）

> **版本**: 0.1.0 (V4.0)  

## 三步启动完整分析

```python
# 第1步：设置环境变量
export DEEPFLOW_DOMAIN=investment
export DEEPFLOW_CODE=688652.SH
export DEEPFLOW_NAME=京仪装备

# 第2步：主Agent spawn Orchestrator
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="orchestrator",
    task="""
你是 DeepFlow V1.0 Orchestrator Agent。
读取 /Users/allen/.openclaw/workspace/.deepflow/prompts/pipeline_engine_orchestrator.md
按指令执行完整管线。所有 sessions_spawn 必须设置 label。
""",
    timeout_seconds=600
)

# 第3步：等待完成
sessions_yield()  # ← 禁止轮询！等待推送
```

## 验证清单（执行后检查）

```bash
ls blackboard/{session_id}/
# 应有：
# ├── data/INDEX.json              ✅
# ├── researcher_*_output.json     ✅ (>2KB)
# ├── auditor_*_output.json        ✅ (>2KB)
# └── final_report.md              ✅
```

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| "sessions_spawn 不可用" | 未在 Agent Run 环境 | 必须通过 sessions_spawn 启动 |
| Worker 输出只有元数据 | 未等待 Worker 完成 | 检查 _wait_for_worker_completion |
| 收敛评分偏低 | 数据缺口/逻辑矛盾 | 检查 auditor P0/P1 问题 |

## 记忆锚点

> "Agent环境才spawn；spawn_fn逐层注入；yield等推送别轮询"
> "Worker 输出 >2KB 才真实；元数据 <500 字节是假的"
> "DataManager 是 Pipeline 第一个 stage，自动 spawn 不用管"

---
*标准执行手册详见：docs/STANDARD_EXECUTION.md*
