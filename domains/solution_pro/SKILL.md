---
name: solution-pro
description: "DeepFlow Solution Pro — 领域自适应方案设计引擎。触发：设计解决方案、架构设计、技术方案。"
version: "V4.0.0"
---

# Solution Pro — Agent 执行指南

> **版本**: V4.0.0 | **最后更新**: 2026-07-27  
> **架构**: 纯 Agent Orchestrator（V4.0 简化版）  
> **V4.0 变更**: 移除 Step 4/5 后置验证，orchestrator 简化为 3 步（初始化→模块执行→完成标记）  
> **质量保证**: Module 内置 Harness + post_validator.py（独立调用，非 orchestrator 步骤）  
> **2.1.0 新增**: Domain Adaptation Layer — domain_analysis.py (DomainProfile 10字段) + 16+ Prompt 泛化 + Schema 开放枚举

---

## 📌 入口函数说明（契约笼子 2026-07-05）

| 函数 | 版本 | 说明 |
|------|------|------|
| `run_solution_pro(user_input, **kwargs)` | **2.0.0（默认）** | 三模块架构，AI Native 合规 |
| `run_solution_pro_v1(topic, **kwargs)` | 2.0.0（兼容） | 10 阶段管线，仅供已有 session 续跑 |

> ⚠️ **2.0.0 已降级为兼容入口**。新流程统一使用 `run_solution_pro()`（2.0.0）。
> 2.0.0 通过 `scripts/start_solution_pro.py` 自动调用，无需直接使用。
> 
> **Blackboard 路径**：2.0.0 和 2.0.0 统一写入 `.deepflow/blackboard/{session_id}/`，
> 确保 Ship Pro 能从统一路径读取。

---

## 🏗️ 架构总览（V4.0）

```
Orchestrator Agent（纯 LLM 调度器，depth-1）
  │
  ├── 🧠 Domain Analysis（领域自适应前置步骤）
  │   ├── domain_analysis.py → DomainProfile (10字段 Pydantic schema)
  │   ├── LLM 推断领域类型 + 专家角色 + 质量维度 + 验证方法
  │
  ├── 📝 Planning Module Agent（depth-2）
  │   └── sessions_spawn → Worker Agents（depth-3）
  │
  ├── 🔍 Research Module Agent（depth-2）
  │   └── sessions_spawn → Research Expert Agents（depth-3）
  │
  ├── 📋 Summary Module Agent（depth-2）
  │   └── sessions_spawn → Analyzer + Synthesizer Agents（depth-3）
  │
  │   ├── 4 个 YAML 配置降级为 few-shot 参考（software/investment/hardware/business）
  │   └── domain_profile 注入全链路：Planning/Research/Summary → task_builder → Prompt
  │
  ├── Module 1: Planning（三层架构，由 Module Agent 直接 spawn Workers）
  │   ├── Layer 0: Meta-Planner → 分析任务 → 选择专家 → 配置 Gate
  │   ├── Layer 1: Expert Planners ×N（并行）→ 各自生成约束/风险/验收标准
  │   └── Layer 2: Convergence Planner → 合并 + 验证 + P0 REQ 追溯
  │       └── planning_convergence.json
  │
  ├── Module 2: Research（多专家并行研究，由 Module Agent 直接 spawn Workers）
  │   ├── Stage 1: Knowledge Freshness → LLM 提取查询 → web_search → 压缩
  │   ├── Stage 2: Expert Config → 从 planning_output.risk_areas 动态确定
  │   ├── Stage 3: Research Experts ×M（并行 + 迭代）→ 各自研究成果
  │   ├── Stage 4: Consolidation → 批量去重 + 冲突检测 + 分层分类
  │   └── Stage 5: Convergence → research_convergence.json
  │
  └── Module 3: Summary（5+1 Phase 收敛，由 Module Agent 直接 spawn Workers）
      ├── Phase 1: Base Synthesis → 基础方案
      ├── Phase 2: Meta Summary Planner → 审查规划
      ├── Phase 3: Parallel Analysis ×N → 多角度审查
      ├── Phase 4: Fix Judge → Fix Agent → Harness Check
      ├── Phase 5a: Document Generator → 方案文档
      └── Phase 5b: JSON Extractor → final_solution.json
```

> **Note**: V4.0 中 post_validator.py 和对抗 Agent 不再是 orchestrator 管线的内置步骤。
> 它们作为独立工具可供外部调用或按需手动触发。

**V3.1 关键变更**（对比 V2.1）：
- ❌ 删除 Python orchestrator 层（MasterOrchestrator / PlanningOrchestrator / ResearchOrchestrator / SummaryOrchestrator）
- ❌ 删除 bridge 模式（FileBasedSpawnBridge）
- ❌ 删除 Gate A/B 数值评分（convergence_layer.py）
- ✅ Module Agent 直接通过 `sessions_spawn` 创建 Workers
- ✅ 新增对抗 Agent（语义质量审查 + 跨模块一致性检查）
- ✅ 保留 post_validator.py 作为 L0 下限守卫

**V4.0 关键变更**（对比 V3.1）：
- ❌ 移除 Orchestrator 内置后置验证（L0 post_validator + L2 对抗审查 + L2 一致性检查）
- ❌ 移除 POST_VALIDATION 状态
- ✅ Orchestrator 简化为 3 步：初始化 → 模块执行 → 完成标记
- ✅ 状态机从 13 状态简化为 10 状态
- ✅ spawn 调用点从 5 个减少到 3 个
- ✅ 代码行数减少 23%（390→299 行）
- ✅ post_validator.py 和对抗 Agent 作为独立工具可供外部调用

**设计原则**：
- Code controls flow（确定性逻辑）
- LLM generates content（语义理解）
- 模块间通过 Blackboard 文件通信（状态靠文件，不靠内存）
- 每模块有独立超时 + 降级策略

---

## 🚀 主 Agent 执行步骤（2.0.0）

### Step 0: 准备 Frozen Spec

**触发条件**：用户没有先跑 Spec Pro，直接从对话启动 Solution Pro

```python
# 如果有 Spec Pro 产出，直接使用其 living_spec
# 否则，从 living_spec.requirement_index 读取 REQ-ID（由 spec_pro 原生生成）

requirement_index = living_spec.get("requirement_index", [])
    "topic": "{TOPIC}",
    "solution_type": "architecture",  # architecture | migration | optimization
    "mode": "standard",
    "domain": "backend_api",  # 从 living_spec 或用户输入推断
    "constraints": [
        {"req_id": "REQ-P0-001", "description": "...", "priority": "P0"},
    ],
}
```

### Step 1: 启动管线（Agent 级 spawn）

```python
from domains.solution_pro import run_solution_pro

# 1. 调用 run_solution_pro()，返回 spawn_params
result = run_solution_pro(
    user_input="{用户原始需求描述}",
    topic="{TOPIC}",
    solution_type="architecture",
    mode="standard",
    domain="backend_api",
    constraints=[...],
    living_spec=frozen_spec,  # Step 0 准备的 spec
)

# 2. 启动 Orchestrator 子 Agent（Agent 级 spawn，无桥接问题）
sessions_spawn(**result["spawn_params"])

# 3. 等待完成（push-based，不轮询）
sessions_yield()
```

**接口说明**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `user_input` | `str` | 用户原始需求描述（必填） |
| `topic` | `str` | 主题（必填） |
| `**kwargs` | `dict` | 其他配置（solution_type, mode, domain, constraints, living_spec 等） |

**返回值**：
```python
{
    "session_id": "sol_xxx",          # Session ID
    "base_path": "blackboard/sol_xxx", # Blackboard 路径
    "spawn_params": {                  # 直接传给 sessions_spawn
        "runtime": "subagent",
        "mode": "run",
        "label": "solution_orchestrator",
        "task": "...",                 # Orchestrator prompt（已填充变量）
        "cwd": "{deepflow_root}",
        "lightContext": True,
    },
}
```

**关键说明**：
- `run_solution_pro()` 内部自动创建 Blackboard、初始化 session_dir、读取 orchestrator.md 模板并填充变量
- **不需要手动创建 MasterOrchestrator** — Agent 级 spawn 无需 spawn_fn 桥接
- 子 Agent 会自动读取 `orchestrator.md` 并按 Planning → Research → Summary 顺序执行

### Step 2: 向用户发送启动通知

```
✅ 已启动 DeepFlow Solution Pro 管线
📋 主题: {TOPIC}
🏗️ 架构: Planning（三层）→ Research（多专家并行）→ Summary（5+1 Phase 收敛）
⏱️ 预计: 20-40 分钟
💬 期间你可以继续问我其他问题，完成后我会通知你
```

### Step 3: 创建 Cron 巡检 Agent

> 🔴 **铁律**: 必须从 `pipeline_watcher.py --print-watcher-prompt` 输出的 `watcher_wrapper_prompt_prefilled` 字段获取 prompt，原样用于 cron payload.message。禁止手动编写 prompt。

```python
from datetime import datetime
from contracts.shared.watcher_config import render_wrapper_prompt, DeliveryConfig

run_start_at = datetime.now().isoformat()

wrapper_prompt = render_wrapper_prompt(
    config_path=f"{deepflow_root}/domains/solution_pro/config/watcher_config.json",
    base_path=str(bb.session_dir),
    run_start_at=run_start_at,
    cron_job_id="{cron_job_id}",
    deepflow_root=deepflow_root,
)

delivery = DeliveryConfig(mode="announce")

cron_result = cron(
    action="add",
    job={
        "name": f"deepflow_watcher_{session_id[:8]}",
        "schedule": {"kind": "every", "everyMs": 180000},
        "sessionTarget": "isolated",
        "payload": {
            "kind": "agentTurn",
            "message": wrapper_prompt,
            "timeoutSeconds": 60,
            "lightContext": True
        },
        "delivery": delivery.to_cron_dict(),
        "enabled": True
    }
)

cron_job_id = cron_result["id"]
wrapper_prompt = wrapper_prompt.replace("{cron_job_id}", cron_job_id)
cron(action="update", jobId=cron_job_id, patch={"payload": {"message": wrapper_prompt}})
```

### Step 4: yield 等待完成（Main Agent 级）

> ⚠️ 这是 Main Agent 的 yield，不是 Orchestrator 的步骤。
> Orchestrator V4.0 已移除内部的 Step 4（后置验证）和 Step 5（复杂完成标记）。

```python
sessions_yield()
```

### Step 5: 处理完成事件（Main Agent 级）

> ⚠️ 这是 Main Agent 的步骤，不是 Orchestrator 的步骤。

收到 orchestrator announce 后：
1. 解析完成状态（COMPLETE / DEGRADED / FAILED）
2. 执行兜底清理（删除 cron + 清理状态文件）
3. 更新 tasks 数据库为 `completed`
4. 向用户报告最终结果

---

## 🔄 2.0.0 完整执行流程

### Module 1: Planning（三层架构）

```
Step 1.1: Meta-Planner（Layer 0）
  ├── 输入: living_spec.md (MD source of truth) + structured_requirements.json
  ├── 分析任务领域和复杂度
  ├── 决定需要哪些专家（1-5 个）
  ├── 配置 Gate A 权重 + Gate B 动态检查项
  └── 输出: stages/meta_planning.json

Step 1.2: Expert Planners ×N（Layer 1，并行）
  ├── 每个专家从自己的视角生成约束/风险/验收标准
  ├── 输出: stages/expert_plans/expert_plan_{name}.json（N 个文件）
  └── 约束格式: {constraint_id, description, priority, rationale, covered_req_ids}

Step 1.3: Convergence Planner（Layer 2）
  ├── 合并所有 Expert Plan 的约束（语义去重 + 冲突解决）
  ├── 生成验证清单（每个约束对应 1+ 个可执行验证项）
  ├── P0 REQ 追溯（确保所有 P0 需求被覆盖）
  └── 输出: stages/unified_constraints.json + stages/verification_checklist.json

Step 1.4: Reviewer_Meta + Reviewer_Convergence
  ├── 验证 Meta-Planner 输出质量
  └── 验证 Convergence 输出质量

Step 1.5: Gate A + Gate B 评估
  ├── Gate A: 四维度评分（completeness/necessity/alignment/global_impact）
  ├── Gate B: 动态检查项验证（CRITICAL/MINOR）
  └── 输出: planning_convergence.json
```

### Module 2: Research（多专家并行研究）

```
Step 2.1: Knowledge Freshness
  ├── LLM 从 planning_output 提取搜索查询
  ├── web_search 获取最新信息
  ├── 压缩搜索结果（去噪 + 提取关键信息）
  └── 输出: stages/knowledge_freshness.json

Step 2.2: Expert Config Determination
  ├── 从 planning_output.risk_areas 动态确定专家配置
  └── 专家数量 = risk_areas 数量（上限 5）

Step 2.3: Research Experts ×M（并行 + 迭代）
  ├── 每个专家从自己的视角研究
  ├── Search-First: 必须先搜索最新信息
  ├── Source Attribution: 每个 finding 必须有来源 URL
  ├── Confidence Self-Assessment: 输出 confidence_score (0-1)
  └── 输出: stages/research_experts/research_expert_{name}.json（M 个文件）

Step 2.4: Consolidation
  ├── 批量去重（跨专家相同发现合并）
  ├── 冲突检测（矛盾发现标记 + 解决建议）
  ├── 分层分类（Tier 1/2/3）
  └── 输出: stages/research_consolidator.json

Step 2.5: Research Convergence
  └── 输出: research_convergence.json
```

### Module 3: Summary（5+1 Phase 收敛）

```
Step 3.1: Fix Loop（最多 3 轮）
  ├── 检测问题（来自 Research 和 Planning 的质量问题）
  ├── 生成修复方案
  ├── 执行修复
  ├── 验证修复效果
  └── 输出: stages/fix_loop_state.json

Step 3.2: Harness Check
  ├── 对抗性检查（独立视角验证）
  ├── 四维度评分（完整性/必要性/目标一致性/全局影响）
  └── 输出: stages/harness_report.json

Step 3.3: Final Review
  ├── 最终评审（综合所有模块输出）
  ├── 质量评分
  └── 输出: stages/final_review.json

Step 3.4: Final Convergence
  ├── 生成最终收敛报告
  ├── ABORT 降级支持（如果质量不达标）
  └── 输出: final_convergence.json
```

---

## 📁 Blackboard 目录结构

```
blackboard/<session_id>/
├── data/
│   ├── frozen_spec.md                # MD source of truth（语义化 REQ-ID）
│   └── structured_requirements.json  # 结构化需求清单
│
├── stages/
│   ├── meta_planning.json            # Planning Layer 0 输出
│   ├── expert_plans/                 # Planning Layer 1 输出（目录）
│   │   ├── expert_plan_security.json
│   │   ├── expert_plan_performance.json
│   │   └── ...
│   ├── convergence_planning.json     # Planning Layer 2 中间产物
│   ├── unified_constraints.json      # 统一约束集
│   ├── verification_checklist.json   # 验证清单
│   ├── knowledge_freshness.json      # Research 知识新鲜度
│   ├── research_experts/             # Research 专家输出（目录）
│   │   ├── research_expert_security.json
│   │   ├── research_expert_scalability.json
│   │   └── ...
│   ├── research_consolidator.json    # Research 整合结果
│   ├── architecture.json             # 架构设计
│   ├── detailed_design.json          # 详细设计
│   ├── consolidation.json            # Summary 整合
│   ├── harness_report.json           # Harness 检查报告
│   ├── fix_loop_state.json           # Fix Loop 状态
│   └── information_contract.json     # 信息守恒契约
│
├── v2/                               # 2.0.0 专属状态（与 2.0.0 隔离）
│   ├── master_state.json             # Master 模块级完成状态
│   ├── planning_output.json          # Planning 模块输出
│   ├── research_output.json          # Research 模块输出
│   ├── summary_output.json           # Summary 模块输出
│   └── pipeline_metrics.json         # Pipeline 指标
│
├── planning_convergence.json         # Planning 收敛点
├── research_convergence.json         # Research 收敛点
├── final_convergence.json            # 最终收敛点
│
├── .completed                        # 完成标记
├── .stage_progress.json              # 阶段进度追踪（断点续接）
├── .cron_job_id                      # Cron Job ID
└── .cron_run_count                   # Cron 运行计数
```

---

## 📋 Prompt 文件清单

### 2.0.0 使用

| Prompt | 模块 | 用途 |
|--------|------|------|
| `meta_planner.md` | Planning L0 | 分析任务 → 选择专家 → 配置 Gate |
| `expert_planner_base.md` | Planning L1 | Expert Planner 基础模板 |
| `convergence_planner.md` | Planning L2 | 合并约束 + 验证清单 + P0 追溯 |
| `reviewer_meta.md` | Planning | 验证 Meta-Planner 输出 |
| `reviewer_convergence.md` | Planning | 验证 Convergence 输出 |
| `harness_agent.md` | 通用 | Gate A + Gate B 评估（统一 Harness） |
| `research_expert_base.md` | Research | Research Expert 基础模板 |
| `research_module.md` | Research | Research 模块调度（含 Consolidation） |
| `summary_base_synthesizer.md` | Summary | Phase 1: 基础方案合成 |
| `summary_meta_planner.md` | Summary | Phase 2: 审查规划 |
| `summary_analyzer_base.md` | Summary | Phase 3: 并行分析 |
| `summary_review_layer_b.md` | Summary | Phase 3: Review Layer B 审查 |
| `summary_refiner.md` | Summary | Phase 4: 判断 + 修复（合并原 fix_judge + fix_agent） |
| `summary_harness_check.md` | Summary | Phase 4 Step 2: Harness 检查 |
| `summary_summarizer.md` | Summary | Phase 5a: 方案文档生成 |
| `summary_json_extractor.md` | Summary | Phase 5b: JSON 元数据提取 |
| `summary_module.md` | Summary | Summary 模块调度入口 |
| `orchestrator.md` | Master | 主调度器（含完成处理） |
| `ai_native_cognitive_base.md` | 通用 | AI Native 认知基础 |
| `compliance_checker_base.md` | 通用 | 合规检查基础模板 |

### 2.0.0 专用（仅用于已有 2.0.0 session 续跑）

| Prompt | 用途 |
|--------|------|
| `data_collection.md` | 2.0.0 Stage 1 需求收集 |
| `planner.md` | 2.0.0 Stage 2 任务规划 |
| `reviewer_business.md` | 2.0.0 Stage 3 业务评审 |
| `reviewer_technical.md` | 2.0.0 Stage 3 技术评审 |
| `reviewer_risk.md` | 2.0.0 Stage 3 风险评审 |
| `designer.md` | 2.0.0 Stage 6 设计 |
| `deliver.md` | 2.0.0 Stage 10 交付 |
| `pipeline_orchestrator.md` | 2.0.0 Orchestrator 指令 |
| `cron_watcher.md` | 2.0.0 Cron 巡检（已 deprecated） |

---

## 📐 Schema 文件清单

### 2.0.0 Schema（`schemas/schemas.py`）

| Schema | 用途 | 对应 Stage |
|--------|------|-----------|
| `V2BaseSchema` | 基类（schema_version + timestamp） | 所有 2.0.0 Stage |
| `ExpertManifestSchema` | Meta-Planner 专家清单 | meta_planning |
| `ExpertPlanSchema` | Expert Planner 输出 | expert_plans/* |
| `UnifiedConstraintsSchema` | 统一约束集 | unified_constraints |
| `VerificationChecklistSchema` | 验证清单 | verification_checklist |
| `PlanningConvergenceSchema` | Planning 收敛点 | planning_convergence |
| `ResearchExpertSchema` | Research Expert 输出 | research_experts/* |
| `ResearchConsolidatorSchema` | Research 整合结果 | research_consolidator |
| `ResearchConvergenceSchema` | Research 收敛点 | research_convergence |
| `DegradedFinalConvergenceSchema` | 降级最终收敛 | final_convergence (degraded) |

### 2.0.0 Schema（保留向后兼容）

2.0.0 Schema 定义在 `task_builder.py` 中的 `STAGE_OUTPUT_SCHEMA`，此处不重复。

---

## 🔄 断点续跑（2.0.0）

2.0.0 使用双层 State 验证：
- `master_state.json`: 模块级完成状态
- `v2/{module}_output.json`: 模块输出文件

**续跑流程**：
1. 检查 `master_state.json` 中 `completed_modules` 列表
2. 对每个未完成模块，检查对应输出文件是否存在
3. 双层验证通过 → 跳过该模块，加载已有输出
4. 只运行未完成的模块

---

## ⏱️ 超时与降级策略

| 模块 | 默认超时 | 降级策略 |
|------|---------|---------|
| Planning | 5 min | `default_expert_manifest`（2 个通用 expert） |
| Research | 15 min | `skip_with_degraded_flag`（跳过，标记 degraded=true） |
| Summary | 20 min | 降级为简化版合成 |

超时配置可通过 kwargs 覆盖：
```python
result = run_solution_pro(
    user_input="...",
    topic="...",
    module_timeouts={"planning": 600, "research": 1200},
)
```

---

## 🛡️ 三层退出机制

### 第一层：正常退出
orchestrator 写 `.completed` → cron 检测到 → 发最终报告 → `cron remove` 自杀

### 第二层：超时退出
cron 运行超过 20 次（60 分钟）→ 发超时告警 → `cron remove` 自杀

### 第三层：主 Agent 兜底
主 Agent 收到 orchestrator announce 后：
```python
# 读取 cron job ID 并删除
cron_job_id = Path(f"{bb.session_dir}/.cron_job_id").read_text().strip()
try:
    cron(action="remove", jobId=cron_job_id)
except:
    pass  # cron 已自杀
```

---

## ⛔ 禁止

```python
# ❌ orchestrator 使用 sessions_send（sub-agent 没有此工具）
# ❌ 主 Agent exec 阻塞轮询
# ❌ cron job 忘记自杀（必须有三层退出保障）
# ❌ 先发 cron remove 再发 message（顺序不能反）
# ❌ 2.0.0 session 使用 2.0.0 入口（from domains.solution import run_solution_pro）
# ❌ 手动拼接 stage 路径（使用 BlackboardManager 2.0.0 API: read_stage/write_stage）
```

---

## 🎯 记忆锚点

> "2.0.0 三模块：Planning 三层、Research 多专家、Summary 5+1 Phase 收敛"
> "Master 只做调度，不做语义判断"
> "状态靠文件，不靠内存"
> "双层验证：master_state.json + module_output.json"
> "超时降级，不崩溃"
> "Code controls flow, LLM generates content"

---

## 📖 参考文档

- **2.0.0 架构设计**: `blackboard/plan_pro_sp_v2_redesign/plan_v2_final.md`
- **2.0.0 开发计划**: `blackboard/plan_pro_sp_v2_redesign/development_plan_v2.md`
- **代码文件索引**: 见 [_overview.md](_overview.md)
- **Schema 契约**: 见 `schemas/schemas.py`
- **2.0.0 文档**: 见 `prompts/v1/pipeline_orchestrator.md`（2.0.0 Orchestrator 指令）

## 🆕 2.0.0 改进（2026-07-01）

> **背景**: E2E 2.0.0 质量评估 (4 Agent 并行分析) 发现 5 个系统性缺陷
> **详细计划**: `IMPROVEMENT_PLAN_V3.md`

| Fix | 描述 | 文件 | 状态 |
|-----|------|------|------|
| Fix 1 | 研究利用追踪器 | `information_conservation.py` | ✅ |
| Fix 4 | Finding Ledger | `summary_orchestrator.py` | ✅ |
| Fix 5 | 6 个确定性检查 | `deterministic_checks.py` | ✅ |
| Fix 2 | Python-only 控制器 | master_orchestrator.py | 📋 |
| Fix 3 | 独立 Verification Module | 新增 | 📋 |

*2.0.0 | 2026-07-01 | 2.0.0 三层架构 + 2.0.0 改进（研究追踪 + Finding Ledger + 确定性检查）*

### V2.1.1 变更（2026-07-08）
- **DAL 架构**: Domain Adaptation Layer — domain_analysis 前置步骤 + DomainProfile Pydantic schema + 全链路透传
- **反模式修复**: 9 个修复（3 P0 + 6 P1），清除代码中的语义判断反模式
  - Gate A/B: 关键词命中率 → raw_metrics + LLM Judge
  - 研究利用率: 子串匹配 → [REF-xxx] 引用标记
  - Schema: DOMAIN_CATEGORIES Literal → str 开放枚举
  - 约束验证: Cage F6/F7 关键词/正则 → 结构化字段
- **Prompt 泛化**: 16+ prompt 清除软件域硬编码，加入投资/硬件/商业多域示例
- **术语统一**: "技术选型"→"关键选型"、"架构设计"→"方案设计"
- **测试**: 127 passed, 10 skipped
