# DeepFlow Blackboard 系统重构方案

> **版本**: v1.0.0-draft
> **日期**: 2026-06-21
> **状态**: 待专家评审
> **作者**: 小满 🦞

---

## 一、现状诊断

### 1.1 当前目录结构（以 DeepFlow 可观测性项目为例）

```
.deepflow/blackboard/
├── DeepFlow_开发者可观测性系统架构_architecture_1a43ee1f/    ← Solution Pro 项目目录
│   ├── .completed                                           ← 状态文件（混在根目录）
│   ├── .cron_run_count                                      ← 状态文件
│   ├── .delivery_config.json                                ← 状态文件
│   ├── .notified_stages.json                                ← 状态文件
│   ├── .stage_progress.json                                 ← 状态文件
│   ├── control_contract.json                                ← 控制文件
│   ├── execution_plan.json                                  ← 控制文件
│   ├── final_result.json                                    ← ⚠️ 交付文件（5KB，0 REQ）
│   ├── final_solution.md                                    ← 交付文件（即将废弃）
│   ├── requirements_traceability_matrix.json                ← 交付文件
│   ├── tasks.json                                           ← 控制文件
│   ├── COMPARISON_REPORT.md                                 ← 分析文件（非管线产物）
│   ├── data/                                                ← 输入数据
│   │   ├── collection.json
│   │   ├── frozen_spec.json
│   │   └── structured_requirements.json
│   ├── stages/                                              ← 10 个阶段输出
│   │   ├── planning.json
│   │   ├── reviewer_technical.json
│   │   ├── ...
│   │   └── summarizer.json                                  ← ⚠️ 即将废弃
│   ├── .prompts/                                            ← orchestrator prompt 快照
│   └── ship/                                                ← Ship Pro 输出（嵌套！）
│       ├── pipeline_config.json
│       ├── pipeline_status.json
│       ├── .cron_job_id                                     ← 状态文件（又一层）
│       ├── .cron_run_count
│       ├── ...
│       ├── review_*.md                                      ← 评审文件
│       └── blackboard/                                      ← ⚠️⚠️ 套娃！
│           ├── .completed
│           ├── .cron_job_id
│           ├── architect_output.json
│           ├── decomposer_output.json
│           ├── specifier_output.json
│           ├── reviewer_output.json
│           ├── packager_output.json
│           ├── final_result.json
│           └── summary.md
│
├── blackboard/                                              ← ⚠️ V1 Ship Pro 独立运行的遗留
│   ├── architect_output.json
│   ├── final_result.json
│   └── ...
│
└── archive/                                                 ← 归档（刚清理完）
```

### 1.2 五个核心问题

| # | 问题 | 严重度 | 影响 |
|:---|:---|:---:|:---|
| **P1** | **同 topic 重跑互相覆盖** | 🔴 | Solution Pro 目录名 = `{topic}_{domain}_{hash6}`，hash 由输入决定。同输入 → 同目录 → stages/ 被覆盖。今天 V1 的 Solution Pro stages 就是这样丢的 |
| **P2** | **Ship Pro 嵌套 blackboard/ 子目录** | 🔴 | `run_pipeline.py` 硬编码 `bb_dir = output_p / "blackboard"`。当 output_dir 是 Solution Pro 的 `ship/` 时，产生 `ship/blackboard/` 套娃 |
| **P3** | **状态文件散落根目录** | 🟡 | `.completed`、`.cron_*`、`.stage_progress.json` 等 8+ 个状态文件混在项目根目录，跟交付文件 `final_result.json` 不分彼此 |
| **P4** | **三域命名规则不统一** | 🟡 | Spec Pro: `{prefix}_spec_{uuid16}`；Solution Pro: `{topic}_{architecture}_{hash6}`；Research Pro: `research_pro_{hash8}_{timestamp}`；Ship Pro: 无独立目录 |
| **P5** | **无版本/运行隔离** | 🔴 | 没有"第 N 次运行"的概念。同一个项目跑 3 次 Solution Pro，只有最后一次的数据。无法做 A/B 对比 |

### 1.3 三个域的 session_id 生成逻辑

| 域 | 生成方式 | 唯一性保证 | 可重跑？ |
|:---|:---|:---|:---|
| **Spec Pro** | `{prefix}_spec_{uuid16}` | UUID 保证 | ✅ 每次运行新目录 |
| **Solution Pro** | `{topic截断}_{domain}_{hash6}` | hash 由输入决定 | ❌ 同输入同目录 |
| **Research Pro** | `research_pro_{hash8}_{timestamp}` | timestamp 保证 | ✅ 每次运行新目录 |
| **Ship Pro** | 无独立目录，嵌套在 Solution Pro 的 `ship/` 下 | 依赖父目录 | ❌ 同项目覆盖 |

**核心矛盾**：Solution Pro 和 Ship Pro 用**确定性 hash**做目录名（同输入 → 同目录），Spec Pro 和 Research Pro 用 **UUID/timestamp**（每次新目录）。前者保证幂等但无法多版本，后者保证隔离但可能产生垃圾。

---

## 二、设计目标

基于 DeepFlow 未来作为 **Loop Engine** 的定位，Blackboard 系统需要满足：

### 2.1 核心需求

| # | 需求 | 理由 |
|:---|:---|:---|
| **R1** | **运行隔离** | 同一项目可以跑 N 次，每次互不影响。支持 A/B 对比（今天的 V1 vs V3 需求） |
| **R2** | **跨域数据流清晰** | Spec Pro → Solution Pro → Ship Pro 的数据传递路径明确，不依赖隐式约定 |
| **R3** | **状态与产出分离** | 控制文件（`.completed`、`.cron_*`）和交付文件（`final_result.json`、stages/）分开放 |
| **R4** | **统一命名规范** | 三个域 + 未来的 Loop Engine 共用一套目录命名规则 |
| **R5** | **向后兼容** | 现有代码（run_pipeline.py、completion_handler.py 等）改动最小化 |

### 2.2 面向未来的扩展

- **Loop Engine**: 同一项目多轮迭代（Spec → Solution → Ship → 运行 → 反馈 → 修改 Spec → 重新跑），每轮是一个独立的 "run"
- **Dashboard**: 前端需要按项目分组、按运行对比
- **清理机制**: 过期运行自动归档，不手动清理

---

## 三、方案设计

### 3.1 新目录结构

```
.deepflow/blackboard/
├── projects/                                    ← 🆕 项目层（按 topic 分组）
│   └── deepflow-observability/                  ← 项目 slug（人类可读）
│       ├── project.json                         ← 项目元数据
│       ├── runs/                                ← 🆕 运行层（每次运行一个目录）
│       │   ├── 20260620_223900/                 ← Run 1（V1，时间戳命名）
│       │   │   ├── run.json                     ← 运行元数据（domain, status, input_hash）
│       │   │   ├── input/                       ← 输入数据
│       │   │   │   ├── living_spec.json         ← Spec Pro 输出 / Solution Pro 输入
│       │   │   │   └── frozen_spec.json
│       │   │   ├── stages/                      ← 阶段输出
│       │   │   │   ├── planning.json
│       │   │   │   ├── consolidator.json
│       │   │   │   └── ...
│       │   │   ├── output/                      ← 🆕 交付文件（状态与产出分离）
│       │   │   │   ├── final_result.json
│       │   │   │   └── requirements_traceability_matrix.json
│       │   │   ├── state/                       ← 🆕 状态文件（集中管理）
│       │   │   │   ├── .completed
│       │   │   │   ├── .cron_job_id
│       │   │   │   ├── .stage_progress.json
│       │   │   │   └── ...
│       │   │   └── ship/                        ← Ship Pro 输出（同级，不嵌套 blackboard/）
│       │   │       ├── run.json
│       │   │       ├── stages/                  ← Ship Pro 阶段输出
│       │   │       │   ├── architect_output.json
│       │   │       │   └── ...
│       │   │       ├── output/
│       │   │       │   └── ship_package.json
│       │   │       └── state/
│       │   │           └── .completed
│       │   │
│       │   ├── 20260621_093600/                 ← Run 2（V2，去重实验）
│       │   │   └── ...
│       │   │
│       │   └── 20260621_104400/                 ← Run 3（V3，部分去重 + Living Spec）
│       │       └── ...
│       │
│       └── runs.json                            ← 运行索引（所有 run 的摘要列表）
│
├── archive/                                     ← 归档（已有）
└── _legacy/                                     ← 🆕 旧数据迁移目录
    └── DeepFlow_开发者可观测性系统架构_architecture_1a43ee1f/
        └── ... (原样保留)
```

### 3.2 关键设计决策

#### D1: 项目 slug 怎么来？

**方案 A**: 从 topic 自动生成 slug（`DeepFlow 开发者可观测性系统架构` → `deepflow-observability`）
- ✅ 人类可读
- ❌ 需要 slug 生成逻辑，可能冲突

**方案 B**: 用 topic 的 hash 前 8 位（`DeepFlow...` → `1a43ee1f`）
- ✅ 确定性，无冲突
- ❌ 不直观

**方案 C**: 用户首次运行时指定，后续自动继承
- ✅ 人类可读 + 无冲突
- ❌ 需要交互

**推荐**: **方案 A + 冲突时加 hash 后缀**。大多数情况人类可读，极端情况自动去重。

#### D2: Run 目录用什么命名？

**方案**: `{YYYYMMDD_HHMMSS}`（时间戳）
- ✅ 天然有序，每次运行唯一
- ✅ 不需要额外 ID 生成逻辑
- ✅ 跟 cron watcher 的 `run_start_at` 天然对齐
- ❌ 长，但作为目录名可以接受

#### D3: 状态文件怎么集中？

**方案**: 所有 `.xxx` 状态文件写入 `state/` 子目录。
- `completion_handler.py` 检查 `.completed` → 改为 `state/.completed`
- `pipeline_watcher.py` 读写 `.stage_progress.json` → 改为 `state/.stage_progress.json`
- 所有 `.cron_*`、`.watcher_*`、`.pipeline_watcher.lock` → `state/`

**改动量**: ~10 个文件的路径字符串替换。

#### D4: Ship Pro 怎么不再套娃？

**当前**: `run_pipeline.py prepare()` 中 `bb_dir = output_p / "blackboard"`
**修改**: `bb_dir = output_p`（直接用 output_dir 作为 blackboard）

Ship Pro 的 output_dir 改为：
```
projects/{slug}/runs/{timestamp}/ship/
```

不再创建 `ship/blackboard/`，Ship Pro 阶段文件直接写入 `ship/stages/`。

#### D5: 跨域数据流怎么传递？

```
Spec Pro
  output → projects/{slug}/runs/{ts}/input/living_spec.json

Solution Pro
  input  ← projects/{slug}/runs/{ts}/input/living_spec.json
  output → projects/{slug}/runs/{ts}/output/final_result.json

Ship Pro
  input  ← projects/{slug}/runs/{ts}/output/final_result.json  (Solution Pro 的交付)
  output → projects/{slug}/runs/{ts}/ship/output/ship_package.json
```

每个域的输入从**上游的 output/** 读取，输出写入**自己的 output/**。数据流方向清晰，不需要隐式约定。

#### D6: 向后兼容策略

| 组件 | 改动 | 兼容层 |
|:---|:---|:---|
| `blackboard.py` STAGE_PATH_REGISTRY | 路径前缀加 `output/` 或 `stages/` | 提供 `get_stage_path()` 函数，内部判断新旧格式 |
| `completion_handler.py` | `.completed` 路径改为 `state/.completed` | 先查新路径，降级查旧路径 |
| `pipeline_watcher.py` | 状态文件路径改为 `state/` | 同上 |
| `run_pipeline.py` | 删除 `bb_dir = output_p / "blackboard"` | 直接用 `output_p` |
| `status_v2.py` | 查找路径改为 `output/final_result.json` | 先查新路径，降级查旧路径 |

**原则**: 新代码走新路径，旧数据走降级路径。不迁移历史数据。

### 3.3 project.json 和 run.json 设计

```json
// project.json
{
  "slug": "deepflow-observability",
  "topic": "DeepFlow 开发者可观测性系统架构设计",
  "created_at": "2026-06-20T21:00:00+08:00",
  "domains": ["spec_pro", "solution_pro", "ship_pro"],
  "runs_count": 3
}

// run.json (每次运行)
{
  "run_id": "20260621_104400",
  "domain": "solution_pro",
  "topic": "DeepFlow 开发者可观测性系统架构设计",
  "input_hash": "a1b2c3d4",
  "status": "completed",
  "started_at": "2026-06-21T10:44:00+08:00",
  "completed_at": "2026-06-21T11:11:00+08:00",
  "input_source": "projects/deepflow-observability/runs/20260621_104400/input/living_spec.json",
  "req_count": 108,
  "covered_req_count": 108,
  "quality_score": 0.89
}

// runs.json (运行索引，项目级)
{
  "runs": [
    {
      "run_id": "20260620_223900",
      "domain": "solution_pro",
      "status": "completed",
      "req_count": 122,
      "quality_score": null,
      "note": "V1: 全量 Living Spec"
    },
    {
      "run_id": "20260621_093600",
      "domain": "solution_pro",
      "status": "completed",
      "req_count": 8,
      "quality_score": null,
      "note": "V2: 过度去重"
    },
    {
      "run_id": "20260621_104400",
      "domain": "solution_pro",
      "status": "completed",
      "req_count": 108,
      "quality_score": 0.89,
      "note": "V3: 部分去重 + Living Spec"
    }
  ]
}
```

### 3.4 与 Loop Engine 的对齐

未来 DeepFlow Loop 的一次完整迭代：

```
Loop Iteration #1:
  projects/{slug}/runs/{ts1}/
    ├── spec/          ← Spec Pro Run
    ├── solution/      ← Solution Pro Run（读 spec/ 的输出）
    ├── ship/          ← Ship Pro Run（读 solution/ 的输出）
    └── feedback/      ← 🆕 运行反馈（用户评审、测试结果）

Loop Iteration #2:
  projects/{slug}/runs/{ts2}/
    ├── spec/          ← 基于 feedback 修改的 Spec
    ├── solution/      ← 重新跑 Solution Pro
    ├── ship/          ← 重新跑 Ship Pro
    └── feedback/
```

每次 Loop 迭代是一个 run，包含完整的 Spec→Solution→Ship→Feedback 链路。runs.json 记录所有迭代的历史，支持跨迭代的 A/B 对比。

---

## 四、实施计划

### Phase 1: 基础设施（不影响现有功能）

| # | 任务 | 改动文件 | 风险 |
|:---|:---|:---|:---|
| 1.1 | 创建 `projects/` 目录结构 | 无代码改动 | 零 |
| 1.2 | 新增 `blackboard_manager.py`（项目/运行管理 API） | 新文件 | 零 |
| 1.3 | 新增 `path_resolver.py`（新旧路径兼容层） | 新文件 | 零 |

### Phase 2: 核心迁移（改动 5 个文件）

| # | 任务 | 改动文件 |
|:---|:---|:---|
| 2.1 | Solution Pro session_id 改为 `{slug}/runs/{timestamp}` | `start_solution_pro.py` |
| 2.2 | Ship Pro 删除 `bb_dir = output_p / "blackboard"` | `run_pipeline.py` |
| 2.3 | 状态文件路径改为 `state/` 子目录 | `completion_handler.py`、`pipeline_watcher.py` |
| 2.4 | STAGE_PATH_REGISTRY 适配新结构 | `blackboard.py` |
| 2.5 | 前端 API 适配新路径 | `status_v2.py` |

### Phase 3: 增强功能

| # | 任务 |
|:---|:---|
| 3.1 | `runs.json` 自动更新（每次运行完成写入摘要） |
| 3.2 | Dashboard 按项目分组 + 按运行对比 |
| 3.3 | 过期运行自动归档（>30 天的 run → archive/） |
| 3.4 | 旧数据迁移脚本（`_legacy/` → `projects/`） |

---

## 五、风险与缓解

| 风险 | 缓解 |
|:---|:---|
| 改动 `run_pipeline.py` 影响 Ship Pro 所有运行 | 兼容层：新路径不存在时降级到旧路径 |
| 旧项目的 cron watcher 找不到状态文件 | completion_handler 先查新路径再查旧路径 |
| slug 生成冲突 | 冲突时自动加 hash 后缀 |
| 前端 status_v2 找不到历史数据 | 前端同时搜索 `projects/` 和 `_legacy/` |

---

## 六、开放问题（待专家评审）

1. **slug 生成策略**：自动 slug vs 用户指定 vs hash？推荐自动 + 冲突加后缀，是否有更好的方案？
2. **run 目录是否要分 domain 子目录**：当前方案是 `runs/{ts}/solution/` + `runs/{ts}/ship/`，还是 `runs/{ts}/`（Solution Pro）+ `runs/{ts}/ship/`（Ship Pro 嵌套）？
3. **runs.json 由谁维护**：orchestrator 写？completion_handler 写？还是独立的 registry 服务？
4. **旧数据迁移**：是否值得写迁移脚本把 `_legacy/` 数据搬到 `projects/`？还是直接保留原样？
5. **`input/` vs `data/`**：当前 Solution Pro 用 `data/` 放输入，新方案改为 `input/` 更语义化，但需要改 `data/collection.json` 等引用。

---

*本文档待专家评审后进入实施阶段。*
