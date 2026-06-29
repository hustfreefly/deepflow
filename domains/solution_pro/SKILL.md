# Solution Pro V2 — Agent 执行指南

> **版本**: V5.0 | **最后更新**: 2026-06-29  
> **架构**: MasterOrchestrator → Planning（三层）+ Research（多专家并行）+ ReviewQC（Fix Loop + 收敛）  
> **V1 架构**: 固定多阶段管线方案（已归档，仅用于已有 session 续跑）

---

## 📌 V1/V2 版本选择指南

| 场景 | 选择 | 说明 |
|------|------|------|
| 新建 session | **V2（默认）** | 三层架构，AI Native 合规 |
| 已有 V1 session 续跑 | V1 | 读取 `.stage_progress.json` 确认阶段，从断点继续 |
| 不确定 | V2 | V2 是未来方向，V1 仅维护 |

**判断方法**：检查 `blackboard/<session_id>/v2/master_state.json` 是否存在。存在 = V2 session。

---

## 🏗️ 架构总览

```
MasterOrchestrator（极简调度器，不做语义判断）
  │
  ├── Module 1: PlanningOrchestrator（三层架构）
  │   ├── Layer 0: Meta-Planner → 分析任务 → 选择专家 → 配置 Gate
  │   ├── Layer 1: Expert Planners ×N（并行）→ 各自生成约束/风险/验收标准
  │   └── Layer 2: Convergence Planner → 合并 + 验证 + P0 REQ 追溯
  │       └── Gate A + Gate B 评估 → planning_convergence.json
  │
  ├── Module 2: ResearchOrchestrator（多专家并行研究）
  │   ├── Stage 1: Knowledge Freshness → LLM 提取查询 → web_search → 压缩
  │   ├── Stage 2: Expert Config → 从 planning_output.risk_areas 动态确定
  │   ├── Stage 3: Research Experts ×M（并行 + 迭代）→ 各自研究成果
  │   ├── Stage 4: Consolidation → 批量去重 + 冲突检测 + 分层分类
  │   └── Stage 5: Convergence → research_convergence.json
  │
  └── Module 3: ReviewQCOrchestrator（质量保障 + 最终收敛）
      ├── Stage 1: Fix Loop → 检测并修复问题（最多 3 轮）
      ├── Stage 2: Harness Check → 对抗性检查
      ├── Stage 3: Final Review → 最终评审
      └── Stage 4: Convergence → final_convergence.json
```

**设计原则**：
- Code controls flow（确定性逻辑）
- LLM generates content（语义理解）
- 模块间通过 Blackboard 文件通信（状态靠文件，不靠内存）
- 每模块有独立超时 + 降级策略

---

## 🚀 主 Agent 执行步骤（V2）

### Step 0: 准备 Frozen Spec

**触发条件**：用户没有先跑 Spec Pro，直接从对话启动 Solution Pro

```python
# 如果有 Spec Pro 产出，直接使用其 living_spec
# 否则，从用户输入提取 topic + constraints，构造最小 frozen_spec

frozen_spec = {
    "topic": "{TOPIC}",
    "solution_type": "architecture",  # architecture | migration | optimization
    "mode": "standard",
    "domain": "backend_api",  # 从 frozen_spec 或用户输入推断
    "constraints": [
        {"req_id": "REQ-P0-001", "description": "...", "priority": "P0"},
    ],
}
```

### Step 1: 初始化 Blackboard + MasterOrchestrator

```python
from domains.solution_pro.master_orchestrator import MasterOrchestrator
from domains.solution_pro.blackboard import BlackboardManager

# 1. 创建 Blackboard（自动配置 SolutionRegistry）
session_id = "sol_{timestamp}"  # 或从 Spec Pro 继承
bb = BlackboardManager(session_id)

# 2. 保存 frozen_spec 到 Blackboard
bb.write("data/frozen_spec.json", frozen_spec)

# 3. 创建 MasterOrchestrator
master = MasterOrchestrator(blackboard=bb, spawn_fn=spawn_fn)

# 4. 运行 Pipeline
result = master.run(
    user_input="{用户原始需求描述}",
    config={
        "topic": "{TOPIC}",
        "solution_type": "architecture",
        "mode": "standard",
        "domain": "backend_api",
        "constraints": [...],
    }
)
```

**接口说明**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `blackboard` | `BlackboardManager` | 黑板管理器，自动配置 SolutionRegistry |
| `spawn_fn` | `Callable` | spawn 函数（由主 Agent 注入，通常是 `sessions_spawn`） |
| `config` | `dict` | 可选配置，覆盖默认超时等 |

**返回值**：
```python
{
    "status": "COMPLETE",          # COMPLETE | FAILED | DEGRADED
    "planning": {...},             # Planning 模块输出
    "research": {...},             # Research 模块输出
    "review_qc": {...},            # ReviewQC 模块输出
    "final_report": {...},         # 最终报告摘要
    "metrics": {...},              # Pipeline 指标（耗时、降级模块等）
    "degraded_modules": [...],     # 降级模块列表
}
```

### Step 2: 向用户发送启动通知

```
✅ 已启动 DeepFlow Solution Pro V2 管线
📋 主题: {TOPIC}
🏗️ 架构: Planning（三层）→ Research（多专家并行）→ ReviewQC（Fix Loop + 收敛）
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

### Step 4: yield 等待完成

```python
sessions_yield()
```

### Step 5: 处理完成事件

收到 orchestrator announce 后：
1. 解析完成状态（COMPLETE / DEGRADED / FAILED）
2. 执行兜底清理（删除 cron + 清理状态文件）
3. 更新 tasks 数据库为 `completed`
4. 向用户报告最终结果

---

## 🔄 V2 完整执行流程

### Module 1: Planning（三层架构）

```
Step 1.1: Meta-Planner（Layer 0）
  ├── 输入: frozen_spec.json + structured_requirements.json
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

### Module 3: ReviewQC（质量保障 + 最终收敛）

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
│   ├── frozen_spec.json              # 冻结的需求规格（REQ-ID 权威源）
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
│   ├── consolidation.json            # ReviewQC 整合
│   ├── harness_report.json           # Harness 检查报告
│   ├── fix_loop_state.json           # Fix Loop 状态
│   └── information_contract.json     # 信息守恒契约
│
├── v2/                               # V2 专属状态（与 V1 隔离）
│   ├── master_state.json             # Master 模块级完成状态
│   ├── planning_output.json          # Planning 模块输出
│   ├── research_output.json          # Research 模块输出
│   ├── review_qc_output.json         # ReviewQC 模块输出
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

### V2 使用

| Prompt | 模块 | 用途 |
|--------|------|------|
| `meta_planner.md` | Planning L0 | 分析任务 → 选择专家 → 配置 Gate |
| `expert_planner_base.md` | Planning L1 | Expert Planner 基础模板 |
| `convergence_planner.md` | Planning L2 | 合并约束 + 验证清单 + P0 追溯 |
| `reviewer_meta.md` | Planning | 验证 Meta-Planner 输出 |
| `reviewer_convergence.md` | Planning | 验证 Convergence 输出 |
| `harness_agent.md` | Planning | Gate A + Gate B 评估 |
| `research_expert_base.md` | Research | Research Expert 基础模板 |
| `consolidator.md` | Research | 研究成果整合 |
| `fixer_expert_v2_harness.md` | ReviewQC | Fix Loop 修复 |
| `harness_v3.md` | ReviewQC | Harness 对抗性检查 |
| `reviewer_v2_harness.md` | ReviewQC | 最终评审 |
| `summarizer.md` | ReviewQC | 最终总结 |
| `orchestrator_completion.md` | Master | 完成处理 |
| `planner_v2_harness.md` | Planning | Planner Harness 验证 |
| `researcher_v2_harness.md` | Research | Researcher Harness 验证 |
| `reviewer_v2_harness.md` | ReviewQC | Reviewer Harness 验证 |
| `summarizer_v2_harness.md` | ReviewQC | Summarizer Harness 验证 |
| `fixer_v2_harness.md` | ReviewQC | Fixer Harness 验证 |
| `consolidator_v2_harness.md` | Research | Consolidator Harness 验证 |
| `ai_native_cognitive_base.md` | 通用 | AI Native 认知基础 |
| `harness_scoring.md` | 通用 | Harness 评分逻辑 |
| `auditor_v2_harness.md` | 通用 | Auditor Harness 验证 |

### V1 专用（仅用于已有 V1 session 续跑）

| Prompt | 用途 |
|--------|------|
| `data_collection.md` | V1 Stage 1 需求收集 |
| `planner.md` | V1 Stage 2 任务规划 |
| `reviewer_business.md` | V1 Stage 3 业务评审 |
| `reviewer_technical.md` | V1 Stage 3 技术评审 |
| `reviewer_risk.md` | V1 Stage 3 风险评审 |
| `designer.md` | V1 Stage 6 设计 |
| `deliver.md` | V1 Stage 10 交付 |
| `pipeline_orchestrator.md` | V1 Orchestrator 指令 |
| `cron_watcher.md` | V1 Cron 巡检（已 deprecated） |

---

## 📐 Schema 文件清单

### V2 Schema（`schemas/v2_schemas.py`）

| Schema | 用途 | 对应 Stage |
|--------|------|-----------|
| `V2BaseSchema` | 基类（schema_version + timestamp） | 所有 V2 Stage |
| `ExpertManifestSchema` | Meta-Planner 专家清单 | meta_planning |
| `ExpertPlanSchema` | Expert Planner 输出 | expert_plans/* |
| `UnifiedConstraintsSchema` | 统一约束集 | unified_constraints |
| `VerificationChecklistSchema` | 验证清单 | verification_checklist |
| `PlanningConvergenceSchema` | Planning 收敛点 | planning_convergence |
| `ResearchExpertSchema` | Research Expert 输出 | research_experts/* |
| `ResearchConsolidatorSchema` | Research 整合结果 | research_consolidator |
| `ResearchConvergenceSchema` | Research 收敛点 | research_convergence |
| `DegradedFinalConvergenceSchema` | 降级最终收敛 | final_convergence (degraded) |

### V1 Schema（保留向后兼容）

V1 Schema 定义在 `task_builder.py` 中的 `STAGE_OUTPUT_SCHEMA`，此处不重复。

---

## 🔄 断点续跑（V2）

V2 使用双层 State 验证：
- `v2/master_state.json`: 模块级完成状态
- `v2/{module}_output.json`: 模块输出文件

**续跑流程**：
1. 检查 `v2/master_state.json` 中 `completed_modules` 列表
2. 对每个未完成模块，检查对应输出文件是否存在
3. 双层验证通过 → 跳过该模块，加载已有输出
4. 只运行未完成的模块

---

## ⏱️ 超时与降级策略

| 模块 | 默认超时 | 降级策略 |
|------|---------|---------|
| Planning | 5 min | `default_expert_manifest`（2 个通用 expert） |
| Research | 15 min | `skip_with_degraded_flag`（跳过，标记 degraded=true） |
| ReviewQC | 10 min | `degraded_final_convergence`（使用 DegradedFinalConvergenceSchema） |

超时配置可通过 `config.module_timeouts` 覆盖：
```python
master = MasterOrchestrator(
    blackboard=bb,
    spawn_fn=spawn_fn,
    config={"module_timeouts": {"planning": 600, "research": 1200}}
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
# ❌ V2 session 使用 V1 入口（from domains.solution import run_solution_pro）
# ❌ 手动拼接 stage 路径（使用 BlackboardManager V6 API: read_stage/write_stage）
```

---

## 🎯 记忆锚点

> "V2 三模块：Planning 三层、Research 多专家、ReviewQC Fix Loop"
> "Master 只做调度，不做语义判断"
> "状态靠文件，不靠内存"
> "双层验证：master_state.json + module_output.json"
> "超时降级，不崩溃"
> "Code controls flow, LLM generates content"

---

## 📖 参考文档

- **V2 架构设计**: `blackboard/plan_pro_sp_v2_redesign/plan_v2_final.md`
- **V2 开发计划**: `blackboard/plan_pro_sp_v2_redesign/development_plan_v2.md`
- **代码文件索引**: 见 [_overview.md](_overview.md)
- **Schema 契约**: 见 `schemas/v2_schemas.py`
- **V1 文档**: 见 `prompts/pipeline_orchestrator.md`（V1 Orchestrator 指令）

*V5.0 | 2026-06-29 | V2 三层架构（Planning + Research + ReviewQC）+ 断点续跑 + 超时降级*
