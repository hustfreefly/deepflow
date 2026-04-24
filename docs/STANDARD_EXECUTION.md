# DeepFlow V1.0 标准执行手册

> **版本**: 1.0 | **日期**: 2026-04-21 | **状态**: 已验证
> **当前版本**: 0.1.0 (V4.0) — 本文档为 V1.0 时期验证记录
>
> 本文档记录 DeepFlow 投资分析管线的**标准执行模式**，基于京仪装备(688652.SH)分析任务的完整验证。

---

## 一、执行架构（已验证）

```
主Agent (depth-0)
  └── sessions_spawn → Orchestrator Agent (depth-1)
        └── PipelineEngine.run()
              ├── Stage 1: DataManager Agent (depth-2)  ← 自动 spawn
              │     └── 数据采集 + 统一搜索
              ├── Stage 2: Planner Agent
              ├── Stage 3: Researchers × 6 (并行)
              ├── Stage 4: Auditors × 3 (并行)
              ├── Stage 5: Fixer Agent
              ├── Stage 6: Verifier Agent (迭代收敛)
              └── Stage 7: Summarizer Agent
```

**关键改进**: DataManager 作为 PipelineEngine 的第一个 stage，自动 spawn 为 Agent，Orchestrator 不再手动执行数据采集。

**验证结论**: 架构设计先进，三层深度 spawn 完全可行。

---

## 二、标准执行流程

### 前置条件

| 条件 | 说明 |
|------|------|
| maxSpawnDepth | ≥ 2（支持 depth-1 Orchestrator spawn depth-2 Workers）|
| 环境变量 | DEEPFLOW_DOMAIN, DEEPFLOW_CODE, DEEPFLOW_NAME |
| 文件权限 | blackboard/ 目录可读写 |

### 步骤 1: 主Agent spawn Orchestrator

```python
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="orchestrator",
    task="""
你是 DeepFlow V1.0 PipelineEngine Orchestrator Agent（depth-1）。

## 环境变量
- DEEPFLOW_DOMAIN=investment
- DEEPFLOW_CODE=688652.SH
- DEEPFLOW_NAME=京仪装备

## 执行步骤
1. 读取 `/Users/allen/.openclaw/workspace/.deepflow/prompts/pipeline_engine_orchestrator.md`
2. 按 Prompt 指令执行完整管线
3. 所有 sessions_spawn 调用必须设置 label 参数
4. 最终报告写入 blackboard/{session_id}/final_report.md
""",
    timeout_seconds=600
)
```

**关键规则**:
- ✅ 必须通过 sessions_spawn 进入 Agent Run 环境
- ✅ 不能直接在 shell 中执行 python orchestrator_agent.py
- ✅ 必须等待 Orchestrator 完成（不轮询，yield 等待推送）

### 步骤 2: Orchestrator 执行（depth-1）

**自动执行**:
1. 环境准备（读取环境变量，加载配置）
2. **PipelineEngine.run()** — 自动执行所有 stages，包括：
   - Stage 1: DataManager Agent（自动 spawn，采集10个数据集）
   - Stage 2-7: Planner → Researchers → Auditors → Fixer → Verifier → Summarizer
3. 保存结果

**关键机制**: Orchestrator 不再手动 spawn DataManager，全部委托给 PipelineEngine。

```python
# Orchestrator 简化逻辑
def run(self):
    # Step 1: 委托给 PipelineEngine（DataManager 作为第一个 stage）
    result = self.step2_pipeline_execution()
    
    # Step 2: 保存结果
    self.step3_save_results(result)
    return 0

# PipelineEngine 自动处理所有 stages
def run(self):
    for stage in self._pipeline.stages:
        result = self._execute_stage_with_resilience(stage)
        # 第一个 stage 是 data_manager，自动 spawn
```

### 步骤 3: PipelineEngine spawn Workers（depth-2）

**Worker 创建**:
```python
# PipelineEngine._do_spawn_agent()
if self._spawn_fn:
    result = self._spawn_fn(
        task=task_desc,
        runtime="subagent",
        mode="run",
        timeout_seconds=timeout,
        label=stage.id  # ← 必须设置 label
    )
    return result.get("childSessionKey", agent_id)
```

**Worker 类型**（investment 领域）:

| 批次 | 角色 | 数量 | 并行 |
|------|------|------|------|
| 1 | planner | 1 | 否 |
| 2 | researcher_finance | 1 | 是 |
| 2 | researcher_tech | 1 | 是 |
| 2 | researcher_market | 1 | 是 |
| 2 | researcher_macro_chain | 1 | 是 |
| 2 | researcher_management | 1 | 是 |
| 2 | researcher_sentiment | 1 | 是 |
| 3 | auditor_factual | 1 | 是 |
| 3 | auditor_upside | 1 | 是 |
| 3 | auditor_downside | 1 | 是 |
| 4 | fixer | 1 | 否 |
| 5 | verifier | 1 | 否 |
| 6 | summarizer | 1 | 否 |

### 步骤 4: 主Agent 等待完成

```python
# 正确做法：yield 等待推送
sessions_yield()

# 错误做法：轮询检查状态
sessions_list()  # ← 禁止
sessions_history()  # ← 禁止
```

---

## 三、输出目录结构

```
blackboard/{session_id}/
├── data/
│   ├── INDEX.json              # 数据索引
│   ├── v0/
│   │   ├── financials.json     # 财务指标
│   │   ├── income_statement.json
│   │   ├── balance_sheet.json
│   │   ├── cashflow_statement.json
│   │   ├── daily_basics.json   # PE/PB/市值
│   │   ├── realtime_quote.json # 实时行情
│   │   └── ...                 # 其他数据集
│   ├── 01_financials/
│   │   └── key_metrics.json    # 财务关键指标
│   ├── 02_market_quote/
│   │   └── key_metrics.json    # 行情关键指标
│   ├── 05_supplement/          # 统一搜索补充数据
│   └── key_metrics.json        # 精简版综合指标
├── stages/
│   └── data_manager_output.json # DataManager 完成信号
├── planner_output.json
├── researcher_finance_output.json
├── researcher_tech_output.json
├── researcher_market_output.json
├── researcher_macro_chain_output.json
├── researcher_management_output.json
├── researcher_sentiment_output.json
├── auditor_factual_output.json
├── auditor_upside_output.json
├── auditor_downside_output.json
├── fixer_output.json
├── verifier_output.json
└── final_report.md             # 最终报告
```

---

## 四、关键成功要素

### 1. spawn_fn 注入链

```
主Agent (sessions_spawn 工具)
  ↓ 注入
Orchestrator Agent (self._spawn_fn)
  ↓ 注入
PipelineEngine (self._spawn_fn)
  ↓ 调用
Worker Agents (depth-2)
```

**教训**: 必须在每一层传递 spawn_fn，不能依赖 `import openclaw`。

### 2. Worker 输出验证

**真实 Worker 输出的特征**:
- ✅ 文件大小 > 2000 字节（非空/非元数据）
- ✅ 包含 "analysis" / "executive_summary" / "conclusions"
- ✅ 有具体数据支撑（非泛泛而谈）

**虚假 Worker 输出的特征**:
- ❌ 文件大小 < 500 字节
- ❌ 仅包含 {"status": "accepted", "childSessionKey": "..."}
- ❌ 无实质分析内容

### 3. 等待机制

**正确模式**:
1. Orchestrator spawn Worker
2. Worker 分析 → 写入 Blackboard 文件
3. Orchestrator 轮询 Blackboard 文件存在性
4. Orchestrator 读取文件 → 继续下一步

**错误模式**:
1. Orchestrator spawn Worker
2. Orchestrator **立即返回** spawn 元数据（未等待）
3. Blackboard 只有元数据，无分析内容

---

## 五、常见问题排查

### Q1: Orchestrator 报错 "sessions_spawn 不可用"
**原因**: 未在 Agent Run 环境中执行（直接 python 运行）
**解决**: 必须通过主Agent sessions_spawn 启动 Orchestrator

### Q2: Worker 输出只有元数据（无分析内容）
**原因**: _run_single_agent 未等待 Worker 完成
**解决**: 添加 _wait_for_worker_completion 轮询机制

### Q3: 收敛评分偏低（如 0.76 < 0.92）
**原因**: 数据缺口或逻辑矛盾
**解决**: 检查 auditor 输出中的 P0/P1 问题，补充数据

### Q4: DataManager 采集数据缺失
**原因**: 数据源配置错误或网络问题
**解决**: 检查 data_sources/investment.yaml 配置，确保 Tushare token 有效

---

## 六、验证清单

每次执行后检查:

```
□ Blackboard 目录存在
□ data/INDEX.json 存在且非空
□ Worker 输出文件大小 > 2000 字节
□ Worker 输出包含 analysis/conclusions
□ final_report.md 存在且完整
□ 收敛评分记录（>=0.88 或已记录原因）
□ 无 {"status": "accepted"} 元数据文件
```

---

## 七、修订历史

| 日期 | 版本 | 变更 | 验证 |
|------|------|------|------|
| 2026-04-22 | 1.1 | DataManager 改为 Agent spawn（PipelineEngine 第一个 stage） | ✅ P0=0 |
| 2026-04-21 | 1.0 | 初始版本，基于京仪装备分析任务 | ✅ 完整管线执行通过 |

---

*固化说明: 本文档为 DeepFlow V1.0 标准执行的唯一权威参考，后续执行必须遵循。*
