# Depth-3 Worker 缺失诊断报告 — 执行记录分析

> 诊断时间: 2026-06-29 22:57 (Asia/Shanghai)
> 分析对象: 2.0.0 Orchestrator E2E 运行 (session: 8bf7b388)

---

## 1. Planning Module 实际执行步骤时间线

| 时间 (UTC) | 事件 | 来源 |
|---|---|---|
| 14:38:17 | 2.0.0 Orchestrator 收到 task（depth-1 subagent） | 8bf7b388.jsonl line 5 |
| 14:38:26 | Orchestrator 执行 Blackboard 初始化（master_state + frozen_spec） | exec tool call |
| 14:38:42 | Orchestrator **读取** v2_planning_module.md prompt 文件 | read tool call |
| 14:38:43 | Orchestrator **调用 sessions_spawn** 启动 Planning Module | spawn accepted, childSessionKey: `agent:main2:subagent:4762ee8f-2464-4499-9a09-ca1ae9d2a558` |
| 14:38:43 | Orchestrator 调用 sessions_yield 等待 Planning Module | yield |
| 14:45:33 | Orchestrator 恢复（Planning Module 完成信号到达） | 7分钟后 |
| 14:45:33 | Orchestrator 验证 planning_convergence → **PLANNING_OK** | exec tool call |
| 14:45:41 | Orchestrator 继续 spawn Research Module | 下一个模块 |

**关键发现**: Planning Module session 文件 `4762ee8f-2464-4499-9a09-ca1ae9d2a558.jsonl` **不存在于磁盘上**。session 已被清理或从未持久化为独立文件。

---

## 2. 每个 Tool Call 的记录（2.0.0 Orchestrator 完整执行链）

### Phase 1: 初始化
1. `exec` — Blackboard 初始化（master_state.json + frozen_spec.json）✅
2. `read` — 读取 `v2_planning_module.md` prompt 文件 ✅

### Phase 2: Spawn Planning Module
3. `sessions_spawn` — 启动 Planning Module
   - **label**: `v2_planning_module`
   - **task**: Orchestrator **自己编写的简化版 task**（不是 prompt 文件的完整内容）
   - **关键内容**: 见下方 §3 分析
   - **结果**: `status: "accepted"`, childSessionKey: `4762ee8f-...`
4. `sessions_yield` — 等待 Planning Module 完成

### Phase 3: 验证 Planning → Spawn Research
5. `exec` — 验证 `planning_convergence` → PLANNING_OK ✅
6. `exec` — 更新 master_state（completed_modules: ["planning"]）
7. `read` — 读取 `v2_research_module.md` prompt 文件
8. `sessions_spawn` — 启动 Research Module (childSessionKey: `4d6ef72d-...`)
9. `sessions_yield` — 等待 Research Module 完成

### Phase 4: 验证 Research → Spawn ReviewQC
10. `exec` — 验证 `research_convergence` → RESEARCH_OK ✅
11. `exec` — 更新 master_state（completed_modules: ["planning", "research"]）
12. `read` — 读取 `v2_reviewqc_module.md` prompt 文件
13. `sessions_spawn` — 启动 ReviewQC Module (childSessionKey: `782ff950-...`)
14. `sessions_yield` — 等待 ReviewQC Module 完成

### Phase 5: 验证 ReviewQC → 完成
15. `exec` — 验证 `review_qc_convergence` → REVIEWQC_OK ✅
16. `exec` — 更新 master_state（completed_modules: ["planning", "research", "review_qc"]）
17. `exec` — 写入 `.completed` 标记
18. **Orchestrator 结束 turn** — 总运行时间 ~13 分钟

---

## 3. 是否尝试过 sessions_spawn

### ❌ Planning Module 没有尝试 sessions_spawn

**根因**: 2.0.0 Orchestrator 给 Planning Module 的 task description 中明确写了：

```
## Important
- Use `exec` for all blackboard operations
- Do NOT use `sessions_spawn` - you are a leaf module    ← 🔴 根因
- Write results to blackboard, not to chat
```

**这行指令直接禁止了 Planning Module spawn 任何 depth-3 workers。**

### 矛盾分析

| 来源 | 指令 | 意图 |
|------|------|------|
| `v2_planning_module.md`（prompt 文件） | "按 Layer 0 → Layer 1 → Layer 2 顺序执行，每层 spawn Worker" | ✅ 正确的三层架构 |
| 2.0.0 Orchestrator 的 task description | "Do NOT use sessions_spawn - you are a leaf module" | ❌ 覆盖了 prompt 文件的指令 |

**2.0.0 Orchestrator 没有将 prompt 文件的完整内容传给 Planning Module**。它读取了 prompt 文件（read tool call），但实际传给 sessions_spawn 的 task 是**自己重新编写的简化版**，完全忽略了 prompt 文件中的 spawn 指令。

### 实际执行结果

Planning Module 按照 "leaf module" 指令，**自己完成了所有规划工作**：
- 直接写入 `planning_convergence.json`（22KB）
- 没有写入任何中间 stages：
  - `stages/meta_planning` → **MISSING**
  - `stages/expert_*` → **MISSING**
  - `stages/planning_convergence` → **MISSING**（只有顶层 `planning_convergence`）

### 同样的问题影响所有三个模块

| 模块 | task 中的 "leaf module" 指令 | 实际行为 |
|------|------|------|
| Planning Module | "Do NOT use sessions_spawn - you are a leaf module" | 自己做规划，无 depth-3 workers |
| Research Module | "Do NOT use sessions_spawn - you are a leaf module" | 自己做研究，无 depth-3 workers |
| ReviewQC Module | "Do NOT use sessions_spawn - you are a leaf module" | 自己做审查，无 depth-3 workers |

---

## 4. 平台配置检查结果

### ✅ maxSpawnDepth 配置正确

```json
{
  "maxConcurrent": 20,
  "maxSpawnDepth": 4
}
```

`maxSpawnDepth: 4` 允许 depth-0 → depth-1 → depth-2 → depth-3 → depth-4 的 spawn 链，完全满足 2.0.0 架构需求。

### ✅ sessions_spawn 工具可用

2.0.0 Orchestrator（depth-1）成功调用了 `sessions_spawn`，Planning Module（depth-2）也被成功创建（childSessionKey 返回 `status: "accepted"`）。平台层面没有阻止 spawn。

### ⚠️ Planning Module session 文件缺失

`4762ee8f-2464-4499-9a09-ca1ae9d2a558.jsonl` 不存在于 `~/.openclaw/agents/main2/sessions/`。可能原因：
- session 完成后被自动清理（archiveAfterMinutes 配置）
- 或 session 数据存储在内存中未持久化

这不影响诊断结论，因为 Orchestrator 的执行记录已经完整展示了问题。

---

## 5. 根因结论

### 🔴 根因：2.0.0 Orchestrator 的 Prompt 设计缺陷

**不是平台限制问题，不是配置问题，是 Prompt 工程问题。**

#### 问题链

```
1. 2.0.0 Orchestrator prompt（v2_orchestrator.md）设计了一个"简化"执行模式
   ↓
2. Orchestrator 读取了模块 prompt 文件，但传给了 modules 一个自己编写的简化版 task
   ↓
3. 简化版 task 中包含 "Do NOT use sessions_spawn - you are a leaf module"
   ↓
4. Planning Module 遵守了这个指令，没有 spawn depth-3 workers
   ↓
5. 三层架构（Meta-Planner → Expert Planners → Convergence Planner）被扁平化为单层
```

#### 具体错误

| # | 错误 | 位置 |
|---|------|------|
| 1 | Orchestrator prompt 的 Step 2 说 "用 read 读取 Planning Module prompt"，但实际 spawn 时没有把 prompt 内容传给 task | `v2_orchestrator.md` Step 2 |
| 2 | Orchestrator 自己编写了简化版 task，添加了 "Do NOT use sessions_spawn" 指令 | 8bf7b388.jsonl line 8 (spawn call) |
| 3 | 三个模块都收到相同的 "leaf module" 限制，全部没有 spawn workers | 所有三个 spawn calls |

#### 修复方向

1. **2.0.0 Orchestrator prompt 必须明确要求**: "将 prompt 文件的**完整内容**作为 task 传给 sessions_spawn，不要修改或简化"
2. **删除 "leaf module" 指令**: 模块 prompt 文件已经包含了完整的 spawn 指令，Orchestrator 不应该覆盖
3. **或者重构 prompt**: 如果确实需要 leaf module 模式，那就在 prompt 文件中不要写 spawn 指令（当前存在矛盾）

---

## 附录：Blackboard 最终状态

| Stage | 状态 | 大小 |
|-------|------|------|
| `planning_convergence.json` | ✅ 存在 | 22KB（直接由 Planning Module 写入，无中间 stages） |
| `research_convergence.json` | ✅ 存在 | 29KB |
| `review_qc_convergence.json` | ✅ 存在 | 10KB |
| `stages/meta_planning` | ❌ 不存在 | — |
| `stages/expert_*` | ❌ 不存在 | — |
| `stages/planning_convergence` | ❌ 不存在 | — |
| `master_state` | ❌ 读取返回 MISSING | 可能 key 格式不匹配 |

**结论**: 整个 pipeline 以 "扁平化" 模式运行完成。三个模块都自己完成了工作（没有 spawn workers），输出直接写入顶层 stages。从输出质量看（22KB planning, 29KB research, 10KB review），内容是实质性的，但架构上没有实现设计的三层/多层深度 spawn 结构。
