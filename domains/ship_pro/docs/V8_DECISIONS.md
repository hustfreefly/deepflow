# Ship Pro 2.0.0 Architecture Decision Document

> **版本**: 2.0.0 (Orchestrator 单入口 + 统一 Blackboard)  
> **日期**: 2026-07-04  
> **状态**: GO（审计通过，R1 已修复，2.0.0 架构定型）  
> **评审**: 3 位 Prompt 专家 + 1 位 AI Native 审计  
> **Prompt 教训**: 10 条历史经验融入  

---

## 1. 2.0.0 问题总结

| 层面 | 问题 | 根因 | 影响 |
|------|------|------|------|
| 架构 | Dispatcher 太重 | 设计+执行一身兼 | LLM 做机械工作 |
| 架构 | 跳步骤 | Prompt 建议≠代码强制 | WorkerGate 被跳过 |
| 架构 | 8min 空转 | 读 82K task 文件 | Python 已准备好 params |
| Prompt | 11KB 信息过载 | 80 REQ 全塞 | ACs=0, deliverables=0 |
| Prompt | 无示例 | 只有规则 | LLM 按最低标准执行 |
| Prompt | 无接口契约 | 不知道上下游 | 孤立 WP |
| Prompt | Worker 写代码 | 没明确禁止 | 10min 写框架 |
| 拆分 | 按 REQ 分组 | 需求≠开发 | 大量重叠 |
| 拆分 | 7 Worker 太多 | 拆太细 | API 限流 |

---

## 2. 2.0.0 角色架构

### 2.1 角色清单（2.0.0 简化为 5 个）

| 角色 | 职责 | 性质 | 深度 |
|------|------|------|------|
| **Orchestrator** | 全权调度：设计→执行→验证→报告 | LLM 子 Agent | depth-1 |
| **PipelineDesigner** | 设计拆分+依赖+裁剪上下文 | Python 函数 | Orchestrator 内 exec |
| **Worker** | read context→产出 WPs→write 文件 | LLM | depth-2 |
| **Consolidator** | 5 步法合并→write 文件 | LLM | depth-2 |
| **Judge** | LLM 语义验证（质量/守恒/品质） | LLM | depth-2 |

> 2.0.0 变更：PipelineRunner 被 Orchestrator 替代。Main Agent 只 spawn Orchestrator，不再参与管线执行。

### 2.2 执行流（2.0.0）

```
Main Agent (depth-0)
  │
  ├─ exec: run_ship_pro(project_name)
  │   └─ Python: 定位统一 blackboard + 读取 Solution Pro 输出 + 构建 Orchestrator prompt
  │   └─ 返回 spawn_params
  │
  ├─ sessions_spawn(**spawn_params)  →  Orchestrator (depth-1)
  │   │
  │   ├─ Phase 1: exec design_pipeline() → PipelinePlan
  │   ├─ Phase 2: exec prepare_runner_spawn() → spawn Workers (cron wake 等待)
  │   │     └─ L1 确定性验证 + L2 LLM Judge
  │   ├─ Phase 3: spawn Consolidator (cron wake 等待)
  │   │     └─ L1 + L2 + L3 三层验证
  │   └─ 输出最终报告
  │
  └─ 收到完成事件 → 读取 ShipPackage
```

---

## 3. Worker 拆分原则

- ✅ 按**交付物模块**（代码内聚性）拆
- ❌ 不按 REQ/需求分组/architecture.layers
- 三维度：内聚性 + 可并行性 + 可验证性
- 数量：小 3-4 / 中 4-6 / 大 5-8

---

## 4. Worker Prompt（6 段式，~2750 tokens）

| Section | Tokens | 内容 | 位置策略 |
|---------|--------|------|---------|
| 1. 角色与任务 | 200 | 角色+数据流声明+禁止写代码 | 开头（高注意力） |
| 2. 模块概述 | 300 | 职责、边界、架构位置 | — |
| 3. 相关需求 | 1200 | Markdown 表格，仅 15-20 REQ | 中间（低注意力） |
| 4. 接口契约 | 300 | 上下游+接口签名 | — |
| 5. 输出规范+示例 | 600 | 1 个高质量 WP 示例 | 靠后（高注意力） |
| 6. 反模式护栏 | 150 | 5 条"不要做" | 结尾（高注意力） |

**传递**：Prompt 内嵌 ~800t + context.json 文件引用 ~2KB

---

## 5. Consolidator（6 步法）

收集 → 去重 → 冲突检测 → 依赖图 → 统计 → 组装 → write 文件

---

## 6. 三层验证架构（R1 修复，契约笼子）

### 6.1 原则

> **Prompt 建议 ≠ 代码强制。只有 Layer 1 的 Gate 是瞎的。**

### 6.2 三层

```
Layer 1: 确定性检查（Python，快速过滤）
  → Pydantic + ACs≥2 + desc≥100 + deliverables≥1 + WP ID 前缀
Layer 2: LLM 语义验证（Judge Agent，独立视角）
  → MUST 约束语义保留 + 信息守恒 + 工程品质
Layer 3: 综合决策（Python 合并 L1+L2）
  → PASS / CONDITIONAL / FAIL
```

### 6.3 三个 Gate

| Gate | L1 确定性 | L2 LLM Judge | L3 综合 |
|------|----------|-------------|---------|
| **WorkerGate** | Schema + ACs≥2 + desc≥100 + deliverables≥1 | MUST 约束语义检查 | L1 PASS + L2 无 CRITICAL |
| **ConsolidatorGate** | ShipPackage Schema + WP>0 | 信息守恒 rate | L1 PASS + rate≥0.7 |
| **FinalGate** | REQ≥80% + 依赖图非空 | Completeness + HarnessV3 | L1 PASS + 综合≥6/10 |

### 6.4 Judge 三步模式（复用 2.0.0 gates.py）

```python
# Step 1: 构建 Judge prompt（2.0.0 已有 build_judge_prompt）
judge_prompt = WorkerGate.build_judge_prompt(worker_spec, worker_output)
# Step 2: spawn Judge Agent
sessions_spawn(task=judge_prompt, label=f"judge_{role}")
# Step 3: 合并结果（2.0.0 check() 已支持 judge_results 参数）
gate_result = WorkerGate.check(worker_spec, worker_output, judge_results=verdict)
```

### 6.5 契约笼子（代码强制，不靠 Prompt）

```python
# WorkerGate.check() — MUST 约束缺失时 raise ValueError
if must_constraints:
    if judge_results is None or task_name not in judge_results:
        raise ValueError(f"契约笼子违规: Judge '{task_name}' 未提供")

# InformationConservationGate.check() — 必须提供 Judge 结果
if judge_results is None or "info_conservation" not in judge_results:
    raise ValueError("契约笼子违规: InformationConservationGate 需要 Judge 结果")

# validate_all_worker_outputs() — L1 失败直接 raise
if not l1_passed:
    raise ValueError(f"L1 验证失败: {failures}")
```

---

## 7. Orchestrator Prompt（2.0.0 替代 PipelineRunner）

2.0.0 废弃了 PipelineRunner，改为 Orchestrator 子 Agent。

**区别**：
- PipelineRunner 是薄 LLM，只能机械执行，遇问题就挂
- Orchestrator 是全权调度者，能自主诊断和恢复

**Main Agent 用法**：
```python
from domains.ship_pro import run_ship_pro
result = run_ship_pro("项目名称")
sessions_spawn(**result["spawn_params"])  # spawn Orchestrator
# 完事。等待完成事件。
```

**Orchestrator 内部流程**：
```
Phase 1: exec design_pipeline() → spawn Designer LLM → PipelinePlan
Phase 2: exec prepare_runner_spawn() → spawn Workers (cron wake) → L1 + L2 验证
Phase 3: spawn Consolidator (cron wake) → L1 + L2 + L3 验证 → ShipPackage
```

**铁律**：禁止 sessions_yield（用 cron wake 替代）；禁止 read() task 文件；禁止回调 Main Agent。

---

## 8. 信息裁剪

PipelineDesigner 从 23KB Solution Pro 提取每个 Worker 的 ~2KB context.json：
- module_reqs（15-20 REQ，Markdown 表格）
- relevant_decisions（3-5 个）
- relevant_risks（2-3 个）
- interface_contracts（上下游接口）

---

## 9. 2.0.0→2.0.0 变化

| 维度 | 2.0.0 | 2.0.0 | 2.0.0 |
|------|-----|-----|------|
| 设计/执行 | 一身兼 | Designer + Runner | Designer + **Orchestrator** |
| Main Agent | 多步编排 | 多步编排 | **单步 spawn** |
| Blackboard | 独立目录 | 独立目录 | **统一 blackboard** |
| 拆分 | 按 REQ | 按交付物模块 | 同 2.0.0 |
| Worker 数 | 7 | 4-6 | 同 2.0.0 |
| Prompt | 11KB | 2-3KB | 同 2.0.0 |
| 示例 | 无 | 1 个高质量 WP | 同 2.0.0 |
| 接口 | 无 | Section 4 | 同 2.0.0 |
| 输出 | completion text | write 文件 | 同 2.0.0 |
| 验证 | 单层可跳过 | **三层契约笼子** | 同 2.0.0 |
| Consolidator | 模糊 | 6 步法 | 5 步法（语义整合） |
| 等待机制 | sessions_yield | sessions_yield | **cron wake** |

---

## 10. 审计结果

- ✅ 10 反模式：9 OK + 1 CRITICAL → R1 已修复（三层验证）
- ✅ 三公理：全部 PASS
- ✅ 10 条教训：10/10 覆盖
- ⚠️ 3 WARNING（R2/R3/R4）实施中补

---

## 11. 实施计划

### Phase 1: 核心重构
1. `pipeline_designer.py` — PipelineDesigner + 裁剪
2. `__init__.py` — `design_pipeline()` 入口
3. `prompts/pipeline_runner.md` — Runner prompt
4. `prompts/worker_template.md` — 6 段式 Worker prompt
5. `prompts/consolidator.md` — 6 步法 Consolidator prompt

### Phase 2: 验证加固（契约笼子）
6. 升级 `gates.py` — 三层验证（L1 + L2 Judge + L3 综合）
7. `prepare_judge_spawn_all()` — Judge spawn
8. `merge_gate_results()` — L3 综合决策
9. `trim_context_for_worker()` — 信息裁剪
10. 单元测试

### Phase 3: E2E 验证
11-15. E2E 跑通 + 验证三层 Gate + 执行时间 < 15min

---

---

## 12. 2.0.0 决策记录（2026-07-04）

### D1: Main Agent 单入口

**问题**：2.0.0 中 Main Agent 仍然需要 spawn Designer → spawn Runner → 手动接管挂掉的 Runner，本质上还在做编排工作。

**决策**：`run_ship_pro(project_name)` 返回单个 `spawn_params`，Main Agent 只做一次 `sessions_spawn`。

**理由**：
- 与 Solution Pro 的 Orchestrator 模式保持一致
- Main Agent 的 context 不被管线细节污染
- 减少 spawn 次数（4+ → 1）

### D2: 统一 Blackboard

**问题**：Ship Pro 在 `domains/ship_pro/blackboard_sessions/` 自建独立目录，与 Spec Pro / Solution Pro 的 `.deepflow/blackboard/` 完全割裂。每次运行需要手动搬运 Solution Pro 输出。

**决策**：所有域共享 `.deepflow/blackboard/{project_name}/`，Ship Pro 写入 `ship_pro/` 子目录。

**理由**：
- 跨域信息流靠文件路径约定，不靠手动搬运
- `run_ship_pro()` 自动从 `data/frozen_spec.md` 发现 Solution Pro 输出
- 同一项目的所有产出在同一个目录下

### D3: sessions_yield → cron wake

**问题**：PipelineRunner 使用 `sessions_yield()` 等待子 Agent 完成，但 yield 后无法被 child 完成事件唤醒，导致管线卡死。

**决策**：Orchestrator 内部一律用 `cron(action="wake", mode="next-heartbeat")` 替代 `sessions_yield`。

**理由**：
- cron wake 每次触发都是一个新的 turn，不会被阻塞
- 每个 wake turn 必须输出可见文字（避免 "visible content" 警告）
- 这是 2.0.0 E2E 中反复出现的致命问题

### D4: Dispatcher 命名为 Orchestrator

**理由**：与 Solution Pro 的 Orchestrator 模式对齐，语义更清晰。

### 2.0.0 E2E 验证结果

| 指标 | 2.0.0 | 2.0.0 E2E | 2.0.0 目标 |
|------|-----|--------|----------|
| Work Packages | 35 | 39 | 39 |
| 总工时 | ~900h | 1,240h | - |
| ShipPackage 大小 | 1.1KB | **103KB** | 完整保留 |
| 执行时间 | 51min | 12min | <15min |
| REQ 覆盖 | 91.3% | 91% | ≥90% |
| 依赖边 | 0 | 56 | 有 |

---

*R1 CRITICAL 已修复：三层验证架构 + 契约笼子（raise ValueError，不靠 Prompt）。*
*2.0.0 架构定型：Orchestrator 单入口 + 统一 blackboard + cron wake。*
