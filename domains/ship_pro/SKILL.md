# Ship Pro V4.0 — Agent 执行指南

> **版本**: V4.0.0 | **最后更新**: 2026-06-26  
> **架构**: Generator + Judge 两阶段闭环 + Orchestrator 模式  
> **CLI 引擎**: `run_pipeline.py`（prepare/task/gate/next/fix-context/validate/status/finalize）  
> **替代**: V3.1 的 6-Agent 线性管线（Architect→Decomposer→Specifier→Packager→Reviewer）

---

## 🏗️ 架构总览

```
主 Agent
  ├── exec: start_ship_pro.py → 准备管线 + 生成 spawn_params
  ├── sessions_spawn(orchestrator) → 启动编排器
  ├── cron_add(watcher) → 启动进度巡检
  └── sessions_yield() → 等待完成通知

orchestrator (sub-agent, depth=1)
  ├── exec: run_pipeline.py prepare → 初始化
  └── 循环 (max 3 轮):
      ├── exec: run_pipeline.py task generator → 构建 prompt
      ├── sessions_spawn(generator_worker) → 启动 Generator
      ├── sessions_yield() → 等待完成
      ├── exec: run_pipeline.py gate generator → Pydantic 门控
      ├── exec: run_pipeline.py task judge → 构建 prompt
      ├── sessions_spawn(judge_worker) → 启动 Judge
      ├── sessions_yield() → 等待完成
      ├── exec: run_pipeline.py gate judge → Pydantic 门控
      └── exec: run_pipeline.py next → 状态机决策:
          ├── validate → 管线完成
          ├── fix_and_rerun → fix-context → 下一轮
          └── spawn → gate 失败需重试
  └── 写 .completed → 完成

cron watcher (isolated, 每 3 分钟)
  └── pipeline_watcher.py → 检测新阶段 → 通知用户
  └── 检测 .completed → 最终报告 → cron 自删
```

### V3.1 vs V4.0 对比

| 维度 | V3.1 (6-Agent 线性) | V4.0 (2-Agent 闭环) |
|------|---------------------|---------------------|
| Agent 数量 | 5+1 (Architect, Decomposer, Specifier, Packager, Reviewer) | 2 (Generator, Judge) |
| 单轮 LLM 调用 | 5 次 | 2 次 |
| 3 轮总调用 | 15 次 | 6 次 |
| 信息保真度 | 低（逐级衰减） | 高（Generator 直出全量） |
| 修复精度 | 粗（回退到 Architect 重做） | 精（FixContext 定向修复） |
| 收敛保障 | 隐式（依赖 Reviewer 判断） | 显式（fixable 标记 + max_rounds + 回归检测） |

---

## 🚀 主 Agent 执行步骤

### Step 1: 启动管线

```bash
cd ~/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 scripts/start_ship_pro.py \
  --input "<input_path>" \
  --output "<output_dir>"
```

**输入**: Solution Pro 的 `final_result.json` 路径（相对于 .deepflow）  
**输出**: JSON 包含 `spawn_params` + `watcher_cron_payload`

### Step 2: Spawn Orchestrator

```python
sessions_spawn(**result["spawn_params"])
```

### Step 3: 创建 Watcher Cron

```python
cron_payload = result["watcher_cron_payload"]
cron_result = cron(action="add", job=cron_payload)
```

### Step 4: 发送启动通知

```
✅ 已启动 Ship Pro V4.0 管线
📦 输入: {input_path}
🔄 2 阶段闭环: Generator ←→ Judge (最多 3 轮)
💬 完成后我会通知你
```

### Step 5: Yield 等待

```python
sessions_yield()
```

---

## 🔄 Orchestrator 行为

Orchestrator 是 V4.0 管线的运行时调度器，执行 Generator → Judge 闭环。

### 核心循环

```
exec: run_pipeline.py prepare <input> <output_dir>

while True:
    # ── Generator 阶段 ──
    exec: run_pipeline.py task generator <output_dir>    → 获取 prompt
    sessions_spawn(generator_worker, task=prompt)         → 启动 Generator
    sessions_yield()                                      → 等待完成
    exec: run_pipeline.py gate generator <output_dir>     → Pydantic 门控
    
    if gate FAIL → increment-retry → 重试 generator（最多 2 次）
    
    # ── Judge 阶段 ──
    exec: run_pipeline.py task judge <output_dir>         → 获取 prompt
    sessions_spawn(judge_worker, task=prompt)              → 启动 Judge
    sessions_yield()                                       → 等待完成
    exec: run_pipeline.py gate judge <output_dir>          → Pydantic 门控
    
    if gate FAIL → increment-retry → 重试 judge（最多 2 次）
    
    # ── 状态机决策 ──
    result = exec: run_pipeline.py next <output_dir>
    
    if result.action == "validate":
        exec: run_pipeline.py validate <output_dir>
        exec: run_pipeline.py finalize <output_dir> pass
        写 .completed → 完成
    
    elif result.action == "fix_and_rerun":
        exec: run_pipeline.py fix-context <output_dir>    → 构建 FixContext
        继续循环（Generator 将收到 FixContext 进行定向修复）
    
    elif result.action == "fail":
        exec: run_pipeline.py finalize <output_dir> fail
        写 .completed → 失败退出
    
    elif result.action == "spawn":
        继续循环（gate 重试）
```

### CLI 命令参考

| 命令 | 用途 | 示例 |
|------|------|------|
| `prepare` | 初始化管线 | `run_pipeline.py prepare <input> <output_dir>` |
| `task` | 构建 worker prompt | `run_pipeline.py task generator <output_dir>` |
| `gate` | Pydantic 门控 | `run_pipeline.py gate generator <output_dir>` |
| `next` | 状态机决策 | `run_pipeline.py next <output_dir>` |
| `fix-context` | 构建修复上下文 | `run_pipeline.py fix-context <output_dir>` |
| `validate` | 最终验证 | `run_pipeline.py validate <output_dir>` |
| `finalize` | 标记完成 | `run_pipeline.py finalize <output_dir> pass` |
| `status` | 查看状态 | `run_pipeline.py status <output_dir>` |
| `increment-retry` | 原子递增重试 | `run_pipeline.py increment-retry <output_dir> generator` |

### Gate 门控说明

| Agent | Pydantic 模型 | 检查项 |
|-------|--------------|--------|
| generator | GeneratorOutput | modules≥1, requirements≥1, work_packages≥1 |
| judge | JudgeOutput | verdict 合法, risks 结构正确 |

Gate FAIL 时：`increment-retry` → 如果 retry_count < 2 → 重新 task + spawn；否则 → next 决定跳过或失败。

---

## 📦 Generator 输出结构

Generator 一次性输出完整的架构蓝图 + WP 规格 + 打包信息（合并 V3.1 的 4 个 Agent 输出）：

```json
{
  "_meta": {"agent": "generator", "model_id": "...", "round": 1},
  "project_type": "...",
  "project": {"name": "...", "objective": "...", "problem_statement": "..."},
  "modules": [{"id": "...", "name": "...", "summary": "...", "responsibilities": [...]}],
  "requirements": [{"req_id": "...", "description": "...", "priority": "P0|P1|P2", "coverage": "..."}],
  "work_packages": [
    {
      "id": "WP-001", "title": "...", "objective": "...",
      "source_modules": [...], "dependencies": [...], "priority": "high|medium|low",
      "acceptance_criteria": ["..."], "serving_principles": [...]
    }
  ],
  "dependency_graph": {"edges": [...], "execution_order": [...], "parallel_groups": [...]}
}
```

**Pydantic 契约**: `contracts/ship_generator.py` (GeneratorOutput, WorkPackageSpec, DependencyGraph)

---

## ⚖️ Judge 输出结构

Judge 替代 V3.1 的 Reviewer，增强 AC 质量检查 + 回归检测 + fixable 标记：

```json
{
  "_meta": {"agent": "judge", "round": 1, "stance": "implementor"},
  "verdict": "pass|fail|conditional",
  "risks": [
    {"id": "risk-1", "severity": "critical|major|minor", "description": "...",
     "fix_suggestion": "...", "fixable": true}
  ],
  "ac_quality": {
    "total_acs": 30, "executable_count": 25, "verifiable_count": 28,
    "specific_count": 26, "complete_coverage": true,
    "details": [{"wp_id": "WP-001", "issues": ["..."]}]
  },
  "regressions": [],
  "consumability_score": 0.85,
  "summary": "..."
}
```

**决策逻辑**: critical→fail | major→conditional | minor→pass | regression→fail

**Pydantic 契约**: `contracts/judge_v4.py` (JudgeOutput, JudgeRisk)

---

## 🔧 FixContext（定向修复）

当 Judge 裁定 fail/conditional 时，`run_pipeline.py fix-context` 自动构建 FixContext：

```json
{
  "original_verdict": "fail",
  "current_round": 2,
  "max_rounds": 3,
  "instructions": [
    {"risk_id": "risk-1", "severity": "major", "fix_suggestion": "...", "affected_stages": ["generator"]}
  ],
  "focus_areas": ["组件-原则一致性"],
  "regression_warnings": ["上轮修复 WP-002 时引入了 WP-005 新问题"]
}
```

Generator 在 Round 2+ 会收到 FixContext，**只修复指定问题，不改动其他部分**。

**Pydantic 契约**: `contracts/fix_context.py` (FixContext, FixInstruction)

---

## 📡 Cron Watcher（进度巡检）

与 V3.x 相同，使用 `render_wrapper_prompt()` 契约化生成。

### 契约约束

- ✅ wrapper prompt 来自 `render_wrapper_prompt()`（start_ship_pro.py 已生成）
- ✅ `sessionTarget` = `"isolated"`（避免 SessionTakeoverError）
- ❌ 禁止主 Agent 手写 watcher prompt

### 通知策略

- V4.0 阶段更少（Generator + Judge），最多 3 轮 × 2 阶段 = 6 条进度 + 1 条完成
- 完成 → 发最终报告 → `cron remove` 自杀
- 超时（30 分钟）→ 超时告警 → `cron remove` 自杀

---

## 🛡️ 三层退出机制

### 第一层：正常退出
orchestrator 写 `.completed` → cron 检测到 → 发最终报告 → `cron remove` 自杀

### 第二层：超时退出
cron 运行超过 15 次（30 分钟）→ 发超时告警 → `cron remove` 自杀

### 第三层：主 Agent 兜底
主 Agent 收到 orchestrator announce 后：
1. 检查 `.completed` 是否存在
2. 删除 cron job（如未自杀）
3. 清理状态文件
4. 向用户报告结果

---

## 📊 状态文件

| 文件 | 创建者 | 用途 |
|------|--------|------|
| `pipeline_status.json` | run_pipeline.py | V4.0 管线状态（CLI 管理） |
| `pipeline_config.json` | run_pipeline.py prepare | 管线配置 |
| `blackboard/generator_output.json` | Generator Worker | Generator 输出 |
| `blackboard/judge_output.json` | Judge Worker | Judge 输出 |
| `blackboard/fix_context.json` | run_pipeline.py fix-context | 修复上下文 |
| `.completed` | orchestrator | 完成标记 |

---

## ⛔ 禁止

- ❌ 主 Agent 直接 spawn Worker（必须通过 Orchestrator）
- ❌ 手写 watcher prompt（必须用 `start_ship_pro.py` 生成的 `watcher_cron_payload`）
- ❌ 直接写 `pipeline_status.json`（必须用 CLI 命令）
- ❌ 修改 Pydantic 模型不同步更新 prompt 中的输出格式说明
- ❌ Generator Round 2+ 忽略 FixContext（必须只修复 instructions 中的问题）
- ❌ Judge 第 2+ 轮跳过回归检测（必须检查上轮修复是否回退）

---

## 🎯 记忆锚点

> "V4.0 = Generator + Judge 两阶段闭环"
> "6 Agent → 2 Agent，15 次 LLM → 6 次，信息逐级衰减 → 直出全量"
> "FixContext = 定向修复，不是回退重做"
> "run_pipeline.py next = 状态机，fix-context = 闭环关键"

---

## 📖 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| **V4.0** | **2026-06-26** | **Generator + Judge 两阶段闭环，替代 6-Agent 线性管线** |
| V3.2 | 2026-06-23 | Pydantic 契约笼子 + CLI 引擎 |
| V3.1 | 2026-06-22 | STAGE_PATH_REGISTRY 统一路径 |
| V3.0 | 2026-06-18 | 5 Agent LLM-native 管线 |
