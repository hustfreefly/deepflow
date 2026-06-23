# DeepFlow 按功能模块开发恢复手册 — Part 5: Blackboard 系统

---

## 5. Blackboard（数据交换层）

### 5.1 概述

Blackboard是DeepFlow的数据交换层——文件系统目录，每个运行产生一个目录，包含输入、阶段输出、状态文件、交付文件。没有数据库，所有状态都在文件系统里。消费者是LLM sub-agent。

### 5.2 当前五个核心问题

| # | 问题 | 严重度 |
|:---|:---|:---|
| P1 | 同topic重跑互相覆盖（无版本隔离） | 🔴 高 |
| P2 | Ship Pro嵌套blackboard/子目录（套娃） | 🔴 高 |
| P3 | 状态文件散落根目录（.completed、.cron_*混在数据文件里） | 🟡 中 |
| P4 | 三域命名规则不统一 | 🟡 中 |
| P5 | 无A/B对比支持 | 🔴 高 |

### 5.3 V2新目录结构设计

```
blackboard/
├── projects/
│   └── deepflow-observability/          ← 项目slug（人类可读）
│       ├── project.json                 ← 项目元数据
│       ├── runs/
│       │   ├── 20260620_223900/         ← Run 1（时间戳命名）
│       │   │   ├── run.json             ← 运行元数据
│       │   │   ├── spec/                ← Spec Pro输出
│       │   │   │   └── living_spec.json
│       │   │   ├── solution/            ← Solution Pro输出
│       │   │   │   ├── stages/
│       │   │   │   │   ├── planning.json
│       │   │   │   │   └── ...
│       │   │   │   └── final_result.json
│       │   │   ├── ship/                ← Ship Pro输出（同级，不套娃）
│       │   │   │   ├── stages/
│       │   │   │   └── ship_package.json
│       │   │   └── state/               ← 状态文件（集中管理）
│       │   │       ├── .completed
│       │   │       └── .stage_progress.json
│       │   └── 20260621_104400/         ← Run 2
│       └── runs.json                    ← 运行索引
├── archive/
└── _legacy/                             ← 旧数据迁移目录
```

### 5.4 关键设计决策

#### D1: 项目slug生成
方案: 从topic自动生成人类可读slug + 冲突时加hash后缀
示例: "DeepFlow开发者可观测性系统" → "deepflow-observability-a1b2c3d4"

#### D2: Run目录命名
方案: {YYYYMMDD_HHMMSS}时间戳，天然有序且唯一

#### D3: 状态文件集中
所有.xxx状态文件写入state/子目录

#### D4: Ship Pro不再套娃
删除run_pipeline.py中的bb_dir = output_p / "blackboard"
Ship Pro阶段文件直接写入ship/stages/

#### D5: 跨域数据流
```
Spec Pro    output → spec/living_spec.json
Solution Pro input ← spec/living_spec.json
             output → solution/final_result.json
Ship Pro    input ← solution/final_result.json
            output → ship/ship_package.json
```

### 5.5 三域session_id命名现状

| 域 | 生成方式 | 唯一性 | 可重跑？ |
|:---|:---|:---|:---|
| Spec Pro | {prefix}_spec_{uuid16} | UUID保证 | ✅ 每次新目录 |
| Solution Pro | {topic截断}_{domain}_{hash6} | 输入决定 | ❌ 同输入同目录 |
| Research Pro | research_pro_{hash8}_{timestamp} | timestamp | ✅ 每次新目录 |
| Ship Pro | 无独立目录，嵌套在Solution Pro的ship/下 | 依赖父 | ❌ 覆盖 |

### 5.6 需要改动的文件（12个，有完整diff）

| 文件 | 改动类型 | 说明 |
|:---|:---|:---|
| core/config/path_config.py | 新增方法 | generate_slug, get_project_path, get_run_path, is_v2_session_id等 |
| domains/solution_pro/blackboard.py | STAGE_PATH_REGISTRY v3.0.0 | 所有stage路径加solution/前缀；summarizer改为final_result.json |
| domains/solution_pro/prompts/summarizer.md | v5.5.0 | 单文件输出+REQ传播铁律 |
| domains/solution_pro/completion_handler.py | 列表变更 | 删除final_solution.md |
| core/orchestrator/pipeline_orchestrator.py | 路径变更 | summarizer→final_result.json |
| domains/solution_pro/eval/propagation_checker.py | 删除降级 | 移除summarizer.json降级逻辑 |
| frontend/backend/routers/status_v2.py | 新增渲染 | 从JSON渲染报告 |
| domains/solution_pro/task_builder.py | 输出变更 | 只写final_result.json |
| scripts/golden_solution_pro_dry_run.py | mock适配 | 删除final_solution.md的mock |
| tests/golden/verify_golden_case.py | 检查变更 | 检查final_result.json |
| prompts/orchestrator_completion.md | 引用更新 | final_result.json |
| skills/solution-pro/orchestrator_prompt_v2.md | 引用更新 | final_result.json |

### 5.7 向后兼容策略

新代码走新路径，旧数据走降级路径。不迁移历史数据。
completion_handler: 先查新路径state/.completed，降级查旧路径.completed

### 5.8 Loop Engine对齐

```
Loop Iteration #1:
  projects/{slug}/runs/{ts1}/
    ├── spec/          ← Spec Pro Run
    ├── solution/      ← Solution Pro Run
    ├── ship/          ← Ship Pro Run
    └── feedback/      ← 运行反馈

Loop Iteration #2:
  projects/{slug}/runs/{ts2}/
    ├── spec/          ← 修改后的Spec
    ├── solution/      ← 重新跑
    ├── ship/          ← 重新跑
    └── feedback/
```

### 5.9 评审结论

架构师评审: 方案可行，建议实施
建议补充:
- slug生成规则: slugify(topic[:30]) + "-" + hash8
- 统一跨域路径引用: 相对路径，相对于run根目录
- 先试点再推广
- 加清理策略（保留最近10个run）

### 5.10 待办

- [ ] Phase 1: 创建projects/目录+blackboard_manager.py+path_resolver.py
- [ ] Phase 2: 5个核心文件改动
- [ ] Phase 3: runs.json自动更新+Dashboard+自动归档+旧数据迁移
