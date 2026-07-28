# Solution Pro vs Deliver Pro 架构对比

> **分析日期**: 2026-07-28  
> **分析范围**: Solution Pro V4.0 vs Deliver Pro V2 (Pulse Scheduling V1)  
> **分析目的**: 识别架构差异根因、可复用公共组件、反模式和技术债

---

## 1. 调度架构对比

### 1.1 总览

| 维度 | Solution Pro V4.0 | Deliver Pro V2 | 差异分析 |
|------|-------------------|----------------|----------|
| **调度模式** | 纯 Agent Orchestrator | 双路径（Agent Orchestrator + Python Driver/Pulse） | Deliver Pro 需要管理多 WP 并发，纯 Agent 无法处理依赖分层 |
| **入口函数** | `run_solution_pro()` → `spawn_params` | `run_deliver_pro()` → `spawn_params` | ✅ 已统一命名规则，接口形态一致 |
| **Orchestrator 类型** | 薄层 LLM（~68 行 prompt，读文件执行） | 薄层 LLM（~68 行 prompt）+ 厚层 Python（DeliverOrchestrator 800+ 行） | Solution Pro 的 LLM 做全部调度决策；Deliver Pro 的 LLM 只做分发，决策在 Python |
| **Agent 层级** | depth-1 Orch → depth-2 Module → depth-3 Worker | depth-1 Orch → depth-2 Phase Agent / depth-3 Worker | Solution Pro 多一层 Module Agent 做语义收敛 |
| **调度粒度** | 模块级（Planning/Research/Summary 各 1 个 Agent） | WP 级（每个 WP 独立走 5 Phase） | Solution Pro 串行模块；Deliver Pro 并行 WP |
| **并发模型** | 模块内并行（Expert Planners ×N, Research Experts ×M） | 跨 WP 并行（Layer 0 WPs 同时跑）+ WP 内串行 | Deliver Pro 需要依赖分层调度（Kahn 拓扑排序） |

### 1.2 调度路径详解

**Solution Pro — 纯 Agent 路径**:
```
run_solution_pro()
  → sessions_spawn(Orchestrator Agent, depth-1)
    → read orchestrator_prompt.md
    → sessions_spawn(Planning Module, depth-2)
      → sessions_spawn(Expert Planners ×N, depth-3)
    → sessions_spawn(Research Module, depth-2)
      → sessions_spawn(Research Experts ×M, depth-3)
    → sessions_spawn(Summary Module, depth-2)
      → sessions_spawn(Analyzers ×N, depth-3)
    → write .completed
```

**Deliver Pro — 双路径**:
```
路径 A: Agent Orchestrator（薄层 LLM 调度）
run_deliver_pro()
  → sessions_spawn(Orchestrator Agent, depth-1)
    → exec: DeliverOrchestrator.drive_all()  # Python 辅助
    → loop: spawn Phase Agents → yield → drive_all() → 直到 all_done

路径 B: Pulse Scheduling（cron 驱动，无长驻 Agent）
  → cron (每 5min) → isolated session → exec: DeliverOrchestrator.pulse()
    → 扫描 → 去重 → 预算控制 → spawn agents → 两阶段确认
```

### 1.3 差异根因分析

**为什么 Deliver Pro 需要双路径而 Solution Pro 不需要？**

| 根因 | Solution Pro | Deliver Pro |
|------|-------------|-------------|
| **工作单元数量** | 固定 3 个模块（Planning/Research/Summary） | 动态 N 个 WP（1-20+），来自 Ship Pro 拆分 |
| **依赖关系** | 固定线性（Planning → Research → Summary） | DAG 依赖（WP 间有 dependency_graph，需拓扑排序分层） |
| **执行时长** | 20-40 分钟（可预测） | 10-120+ 分钟（取决于 WP 数量和复杂度） |
| **失败恢复** | 模块级降级（skip with degraded flag） | WP 级重试（3 次预算）+ 孤儿分发恢复 +  stale lock 检测 |
| **并发需求** | 模块内并行（同模块的 Experts） | 跨 WP 并行 + 全局在途上限（MAX_IN_FLIGHT=8） |

**结论**: 双路径设计**合理**。Solution Pro 的固定 3 模块串行管线适合纯 Agent 调度；Deliver Pro 的多 WP DAG 依赖 + 长时间运行需要 Python 确定性调度 + 脉冲式容错。

---

## 2. 状态管理对比

### 2.1 状态机设计

| 维度 | Solution Pro V4.0 | Deliver Pro V2 | 差异分析 |
|------|-------------------|----------------|----------|
| **状态来源** | `master_state.json`（模块级完成状态） | 文件系统推导（`phase_deriver.py`） | **核心差异**: Solution Pro 显式状态 vs Deliver Pro 隐式推导 |
| **状态数量** | 10 个状态（V4.0 从 13 简化） | 6 个 phase（PENDING/GENERATING/ASSEMBLING/VALIDATING/PACKAGING/DONE） | Solution Pro 状态更多因为要追踪 3 模块的中间态 |
| **状态转换** | Orchestrator Agent 写入 `master_state.json` | `phase_deriver.py` 从 artifact 存在性推导 | Deliver Pro 的 "derive, don't sync" 更健壮（无状态漂移风险） |
| **持久化方式** | JSON 文件（master_state.json + v2/{module}_output.json） | JSON 文件（batch_progress.json + _pulse_state.json + 文件系统 artifact） | Deliver Pro 有更多持久化文件用于脉冲调度 |
| **恢复机制** | 双层验证（master_state + module_output）→ 跳过已完成模块 | phase_deriver 每次重新推导 → 自然断点续跑 | Deliver Pro 的恢复更简单（无需显式检查，文件即真相） |

### 2.2 状态机对比图

**Solution Pro 状态机（V4.0, 10 状态）**:
```
INITIALIZED → DOMAIN_ANALYSIS → PLANNING → RESEARCH → SUMMARY → COMPLETING → COMPLETED
                                    ↘ DEGRADED ↗           ↘ FAILED ↗
```

**Deliver Pro 状态机（6 phase，per-WP）**:
```
PENDING → GENERATING → ASSEMBLING → VALIDATING → PACKAGING → DONE
              ↘ failed/blocked ↗      ↘ FAIL verdict ↗
```

### 2.3 关键差异：显式 vs 隐式状态

**Solution Pro（显式状态）**:
```python
# master_state.json
{
    "status": "running",
    "current_module": "research",
    "completed_modules": ["planning"],
    "failed_modules": []
}
```
- ✅ 可读性强，人类可直接查看进度
- ❌ 状态可能与实际文件不一致（Agent 写了状态但没写文件，或反过来）
- ❌ 需要 Orchestrator 主动维护状态文件

**Deliver Pro（隐式状态 — derive, don't sync）**:
```python
# phase_deriver.py — 从 artifact 推导 phase
if (delivery_manifest exists AND final_deliverable non-empty):
    return "DONE"
elif (validation_result.json exists):
    return "PACKAGING"
elif (integrated_draft/DELIVERABLE.md exists):
    return "VALIDATING"
# ...
```
- ✅ 状态永远与实际产出一致（无漂移）
- ✅ 无需主动维护，天然支持断点续跑
- ❌ 推导逻辑复杂（需要理解所有 artifact 的依赖关系）
- ❌ 重新进入阶段时必须 `invalidate_downstream`（删旧 artifact）

**评价**: Deliver Pro 的 "derive, don't sync" 是更先进的模式。Solution Pro 的显式状态在 V4.0 简化后已足够，但如果模块数量增长，可能面临状态漂移风险。

---

## 3. 模块划分对比

### 3.1 模块结构

| Solution Pro（3 模块） | Deliver Pro（5 Phase） | 功能对应 |
|------------------------|------------------------|----------|
| **Planning Module**（三层收敛） | **Phase 1: Analyze**（单 Agent） | 任务分析/规划 |
| — | **Phase 2: Workers**（多 Worker 并行） | 实际执行/生产 |
| **Research Module**（多专家并行 + 整合） | — （无对应，Solution Pro 独有） | 知识研究 |
| — | **Phase 3: Integrate**（Python 代码） | 组装/集成 |
| — | **Phase 4: Validate**（单 Agent） | 质量验证 |
| **Summary Module**（5+1 Phase 收敛） | **Phase 5: Package**（单 Agent） | 最终交付 |

### 3.2 模块复杂度对比

| 模块 | Solution Pro | Deliver Pro | 分析 |
|------|-------------|-------------|------|
| **规划阶段** | Planning 三层（Meta → Expert ×N → Convergence）+ Reviewer + Gate A/B | Analyze 单 Agent → execution_plan.json | Solution Pro 规划更重（多专家视角 + 收敛验证）；Deliver Pro 规划更轻（单 Agent 出 plan） |
| **执行阶段** | Research 多专家并行 + Consolidation + Convergence | Workers 多 Task 并行 + Wave 管理 | 都有并行执行，但 Solution Pro 有知识整合层 |
| **质量保障** | Summary 5+1 Phase（合成 → 审查 → 分析 → 修复 → 文档 → JSON） | Validate 单 Agent + 分数阈值判定 | Solution Pro 质量保障更重（多轮对抗 + 修复循环）；Deliver Pro 更轻（单轮验证） |
| **组装阶段** | 无独立组装（Summary 直接输出 final_solution） | Integrate（Python 代码组装 Worker 产出） | Deliver Pro 需要组装因为 WP 产出是分散的 |

### 3.3 设计哲学差异

| 哲学 | Solution Pro | Deliver Pro |
|------|-------------|-------------|
| **核心理念** | "方案设计" — 重分析、重收敛、重质量 | "交付执行" — 重效率、重并行、重容错 |
| **LLM 使用** | 大量 LLM（每模块多 Agent 并行 + 多轮审查） | 精准 LLM（只在需要语义理解的节点用 Agent） |
| **代码使用** | 少量代码（仅用于确定性提取/渲染） | 大量代码（Assembly 纯代码、phase 推导纯代码、调度纯代码） |
| **质量 vs 速度** | 偏质量（20-40min，多轮收敛） | 偏速度（WP 并行，脉冲调度） |

---

## 4. 可复用公共组件清单

### 4.1 已共享的 Core 组件

| 组件 | 路径 | Solution Pro 使用 | Deliver Pro 使用 | 复用状态 |
|------|------|-------------------|------------------|----------|
| **BlackboardManager** | `core/blackboard/blackboard_manager.py` | ✅ 直接使用 | ✅ 通过 `DeliverProBlackboard` 封装 | ✅ 已共享 |
| **context_injector** | `core/blackboard/context_injector.py` | ✅ `build_bootstrap_task` | ✅ `auto_bootstrap` | ✅ 已共享 |
| **prompt_utils** | `core/prompt_utils.py` | ✅ `render_prompt` | ❌ 未使用（直接读 prompt 文件） | ⚠️ Deliver Pro 应接入 |
| **prompt_registry** | `core/prompt_registry.py` | ❌ 未使用 | ❌ 有独立 `prompt_registry.py` | ⚠️ 重复实现 |
| **track_generator** | `core/track_generator.py` | ✅ `generate_solution_track` | ❌ 未使用 | ⚠️ Deliver Pro 可接入 |
| **Pydantic Contracts** | `contracts/shared/` | ✅ `HandoffPackage` | ✅ `WatcherConfig` | ✅ 已共享 |

### 4.2 域内独立实现的组件（潜在可共享）

| 组件 | Solution Pro 实现 | Deliver Pro 实现 | 可共享性 | 优先级 |
|------|-------------------|------------------|----------|--------|
| **Blackboard DAL** | `solution_pro/blackboard.py`（路径注册表 + CoreBlackboardManager 委托） | `deliver_pro/blackboard.py`（独立 `DeliverProBlackboard` 类） | 🟡 中 — 接口不同但职责相同 | P2 |
| **State Manager** | `master_state.json` 直接读写 | `state_manager.py`（DEPRECATED，已迁移到 phase_deriver） | 🔴 低 — 两种哲学不可调和 | — |
| **Phase Deriver** | 无（显式状态） | `phase_deriver.py`（artifact → phase 推导） | 🟡 中 — Solution Pro 可借鉴 derive 模式 | P2 |
| **Pulse Scheduler** | `pulse.py`（Cron 巡检） | `orchestrator.py` 内 `pulse()` 方法 | 🟡 中 — 都有 cron watcher，实现不同 | P2 |
| **Prompt Registry** | `core/prompt_registry.py`（未使用） | `deliver_pro/prompt_registry.py`（独立实现） | 🟢 高 — 应统一到 core | P1 |
| **Post Validator** | `post_validator.py`（L0 下限守卫） | `wp_runner.py` 内 `verify_*` 方法 | 🟡 中 — 验证逻辑不同但框架可共享 | P2 |
| **Atomic Write** | 无（直接 write） | `_atomic_write_json`（temp + os.replace） | 🟢 高 — Solution Pro 应引入 | P1 |
| **Dependency Layer** | 无（固定线性流程） | `_compute_layers` + `_topo_layers`（Kahn 算法） | 🔴 低 — Solution Pro 不需要 | — |
| **WP Adapter** | 无（消费 living_spec） | `_adapt_ship_pro_wp`（Ship Pro → Deliver Pro 字段映射） | 🔴 低 — 特定于 Ship→Deliver 桥接 | — |

### 4.3 建议提取到 Core 的公共组件

| 组件 | 当前状态 | 提取建议 | 收益 |
|------|---------|---------|------|
| **Atomic JSON Writer** | Deliver Pro 独立实现 | 提取到 `core/fs_utils.py` | 所有域受益，防止并发写截断 |
| **Prompt Registry** | 两个域各自实现 | 统一到 `core/prompt_registry.py` | 单一真相源，减少重复 |
| **Phase Deriver Pattern** | Deliver Pro 独有 | 抽象为 `core/phase_deriver_base.py` | Solution Pro 可借鉴 derive 模式替代显式状态 |
| **Pulse Report Schema** | 各自有 `contracts/pulse_report.py` | 统一到 `contracts/shared/pulse_report.py` | 跨域 pulse 监控统一格式 |
| **Stale Dispatch Detection** | Deliver Pro 独立实现 | 如有其他域需要长时间调度可提取 | 暂时 P3 |

---

## 5. 架构差异根因分析

### 5.1 为什么 Deliver Pro 需要双路径？

**根因 1: 多 WP 并发管理**
- Solution Pro 固定 3 模块，LLM Orchestrator 可以记住并串行调度
- Deliver Pro 有 N 个 WP（动态数量），有依赖关系，需要 Python 做拓扑排序和分层调度
- LLM 不适合做 20+ WP 的 DAG 调度（上下文爆炸 + 容易遗漏）

**根因 2: 长时间运行容错**
- Solution Pro 20-40 分钟，Orchestrator Agent 一次跑完
- Deliver Pro 可能 1-2 小时（多 WP 串行/并行），Agent session 可能超时/中断
- Pulse 模式（cron 每 5min 触发 isolated session）天然容错（无长驻 session）

**根因 3: 并发控制**
- Solution Pro 不需要全局并发上限（模块内并行是固定的）
- Deliver Pro 需要 `MAX_IN_FLIGHT=8` + `MAX_SPAWN_PER_PULSE=5` 防止 429 风暴
- 这种资源控制适合 Python 确定性实现，不适合 LLM 决策

**合理性评估**: ✅ **合理**。双路径不是过度设计，而是解决真实问题：
- Agent 路径处理语义决策（analyze/validate 需要 LLM 理解）
- Python 路径处理确定性调度（分层/去重/预算/锁）
- 两者正交，不是重复

### 5.2 反模式识别

| # | 反模式 | 位置 | 严重性 | 说明 |
|---|--------|------|--------|------|
| 1 | **状态管理 DEPRECATED 代码未清理** | `deliver_pro/state_manager.py` | P2 | 标注 DEPRECATED 但仍保留 400+ 行代码，应删除 |
| 2 | **Prompt Registry 重复实现** | `deliver_pro/prompt_registry.py` vs `core/prompt_registry.py` | P2 | 域级 prompt_registry 应统一到 core |
| 3 | **Solution Pro 显式状态漂移风险** | `master_state.json` | P2 | Agent 可能写状态但没写文件（或反过来），应借鉴 derive 模式 |
| 4 | **Solution Pro 无原子写** | `BlackboardManager.write()` | P1 | 并发写可能截断，Deliver Pro 已有 `_atomic_write_json` |
| 5 | **Deliver Pro 未接入 prompt_utils** | `run_deliver_pro()` 直接 `read_text()` | P2 | Solution Pro 已用 `render_prompt` 做变量注入，Deliver Pro 用手动 `replace()` |
| 6 | **Solution Pro Orchestrator prompt 截断历史** | `__init__.py` 注释 | P3 | V3.4 修复了 task 超 500 chars 被截断的问题，改为最小引用模式。说明 prompt 注入机制不够健壮 |

### 5.3 技术债清单

| 域 | 技术债 | 影响 | 修复建议 |
|----|--------|------|---------|
| Solution Pro | `run_solution_pro_v1` 仍保留为兼容入口 | 维护两套代码路径 | 确认无调用方后删除 |
| Solution Pro | `frozen_spec.py` 标注 DEPRECATED 但仍被引用 | 新开发者可能误用 | 在代码中加 `raise DeprecationWarning` |
| Deliver Pro | `state_manager.py` DEPRECATED 未删除 | 代码噪音 | 删除文件 + 更新测试 |
| Deliver Pro | `_adapt_ship_pro_wp` 字符串 anchors 转换 | FixFlow R11 补丁，应上游修复 | 让 Ship Pro 直接输出 dict anchors |
| Both | Blackboard DAL 各自实现 | 接口不一致 | 抽象 `core/blackboard/domain_blackboard_base.py` |

---

## 6. 信息流对比

### 6.1 模块间通信方式

| 维度 | Solution Pro | Deliver Pro |
|------|-------------|-------------|
| **主要通信** | Blackboard 文件（`stages/*.json`） | Blackboard 文件（`stages/*.json` + `worker_outputs/*/MANIFEST.json`） |
| **通信粒度** | 模块级（每个 Module 读写一个大 JSON） | Task 级（每个 Worker 有独立目录 + MANIFEST） |
| **通信协议** | 隐式（约定文件名） | 半显式（MANIFEST.json schema + phase_deriver 推导） |
| **跨域通信** | `frozen_spec.md` → Ship Pro 消费 | `ship_package.json` ← Ship Pro 产出 |

### 6.2 Blackboard 目录结构对比

**Solution Pro**:
```
blackboard/{session_id}/
├── data/                    # 输入数据
│   ├── frozen_spec.md       # MD source of truth
│   └── living_spec.json
├── stages/                  # 模块产出
│   ├── meta_planning.json
│   ├── expert_plans/        # 多专家并行产出
│   ├── unified_constraints.json
│   ├── research_experts/
│   ├── research_consolidator.json
│   └── final_solution.md
├── v2/                      # 运行时状态
│   ├── master_state.json
│   └── {module}_output.json
├── planning_convergence.json  # 收敛点
├── research_convergence.json
└── .completed
```

**Deliver Pro**:
```
blackboard/{project_name}/
├── ship_pro/                # 上游输入
│   └── ship_package.json
├── deliver_pro/
│   ├── {wp_subdir}/         # 每个 WP 独立子目录
│   │   ├── data/wp.json
│   │   └── stages/
│   │       ├── execution_plan.json
│   │       ├── worker_outputs/{task_id}/MANIFEST.json
│   │       ├── integrated_draft/DELIVERABLE.md
│   │       ├── validation_result.json
│   │       └── final_deliverable/
│   ├── _pulse_state.json    # Pulse 调度状态
│   ├── _pulse_actions.json  # Pulse 产出
│   ├── _pulse.lock          # 单实例锁
│   └── .deliver_completed.json
└── batch_progress.json      # 跨 WP 进度
```

### 6.3 关键差异

| 差异 | Solution Pro | Deliver Pro | 分析 |
|------|-------------|-------------|------|
| **目录隔离** | 所有模块共享 `stages/` 目录 | 每个 WP 有独立子目录 | Deliver Pro 需要 WP 隔离（多 WP 并行写不同目录） |
| **收敛点文件** | 显式 `*_convergence.json` | 无（phase_deriver 从 artifact 推导） | Solution Pro 更显式但多维护 3 个文件 |
| **运行时状态** | `v2/` 子目录 | 项目根目录（`_pulse_*.json`） | Deliver Pro 的运行时状态更分散 |

---

## 7. 重构方向建议

### 7.1 短期（P1, 1-2 周）

| 重构项 | 收益 | 风险 |
|--------|------|------|
| **Deliver Pro 接入 `prompt_utils.render_prompt`** | 统一 prompt 变量注入，消除手动 `replace()` | 低 — 纯替换 |
| **提取 `_atomic_write_json` 到 `core/fs_utils.py`** | Solution Pro 也受益，防并发写截断 | 低 — 纯工具函数 |
| **删除 `state_manager.py`（DEPRECATED）** | 减少 400 行代码噪音 | 低 — 已标注无生产调用方 |

### 7.2 中期（P2, 2-4 周）

| 重构项 | 收益 | 风险 |
|--------|------|------|
| **统一 Prompt Registry 到 core** | 消除域级重复实现 | 中 — 需迁移调用方 |
| **Solution Pro 引入 phase_deriver 模式** | 消除 master_state.json 漂移风险 | 中 — 需要重新设计 Orchestrator 完成检测 |
| **统一 Pulse Report Schema 到 `contracts/shared/`** | 跨域 pulse 监控统一格式 | 中 — 两个域的 pulse 实现差异较大 |
| **抽象 `core/blackboard/domain_blackboard_base.py`** | 统一 Blackboard DAL 接口 | 中 — 两个域的 Blackboard 接口差异较大 |

### 7.3 长期（P3, 1-2 月）

| 重构项 | 收益 | 风险 |
|--------|------|------|
| **Solution Pro 迁移到 derive 模式** | 完全消除状态漂移可能性 | 高 — 需要重构 Orchestrator 完成检测逻辑 |
| **统一 Pulse Scheduler 框架** | 两个域共享 pulse 调度基础设施 | 高 — Solution Pro 的 cron watcher 和 Deliver Pro 的 pulse 差异很大 |
| **跨域可观测性统一** | 统一的 pipeline 监控/告警/报告 | 中 — 需要定义通用的 pipeline metrics schema |

---

## 8. 总结

### 8.1 架构成熟度对比

| 维度 | Solution Pro V4.0 | Deliver Pro V2 |
|------|-------------------|----------------|
| **调度架构** | ⭐⭐⭐⭐ 简洁清晰，纯 Agent 路径 | ⭐⭐⭐⭐ 双路径合理但复杂度高 |
| **状态管理** | ⭐⭐⭐ 显式状态有漂移风险 | ⭐⭐⭐⭐⭐ derive 模式是最佳实践 |
| **容错能力** | ⭐⭐⭐ 模块级降级 | ⭐⭐⭐⭐⭐ WP 级重试 + 孤儿恢复 + 锁管理 |
| **代码质量** | ⭐⭐⭐⭐ 经过多轮重构，较干净 | ⭐⭐⭐ 有 DEPRECATED 代码未清理 |
| **可观测性** | ⭐⭐⭐ Blackboard 文件可查 | ⭐⭐⭐⭐ Pulse Report + 告警体系 |
| **公共组件复用** | ⭐⭐⭐ 使用 core 但未完全接入 | ⭐⭐⭐ 独立实现较多 |

### 8.2 核心洞察

1. **"derive, don't sync" 是最有价值的模式** — Deliver Pro 的 phase_deriver 消除了状态漂移问题，Solution Pro 应借鉴。

2. **双路径不是过度设计** — Deliver Pro 的多 WP DAG 调度 + 长时间运行 + 并发控制需求决定了纯 Agent 路径不可行。

3. **公共组件提取的优先级应该是：工具函数 > Schema > 框架** — 先提取 `_atomic_write_json` 这种无争议的工具，再统一 Prompt Registry，最后考虑 Blackboard DAL 抽象。

4. **Solution Pro 的 "重分析" 和 Deliver Pro 的 "重执行" 是互补的** — 不应该试图统一它们的设计哲学，而应该让公共基础设施支撑不同的设计选择。

---

*分析完成。本文档为只读分析，未修改任何代码。*
