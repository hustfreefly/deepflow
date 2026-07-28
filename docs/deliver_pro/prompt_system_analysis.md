# Deliver Pro Prompt 体系分析

> **分析日期**: 2026-07-28
> **分析范围**: Solution Pro (16 prompts, 250KB) vs Deliver Pro (7 prompts, 24KB)
> **分析目标**: 识别可复用模板、评估调度逻辑、发现 prompt-code 一致性问题

---

## 1. Prompt 清单对比

| # | Solution Pro | Deliver Pro | 功能 | 可复用性 |
|---|-------------|-------------|------|---------|
| 1 | `orchestrator.md` (9.4KB) | `deliver_orchestrator.md` (5.3KB) | 薄层调度器 | ⚠️ 结构相似但调度模式不同（wait_for vs yield+drive_all） |
| 2 | `planning_module.md` (21.7KB) | `deliver_analyze.md` (3.5KB) | 任务分解/规划 | ⚠️ 功能相似但粒度差异大 |
| 3 | `meta_planner.md` (8.9KB) | — | 元规划（选专家+配 Gate） | ❌ Deliver Pro 无此概念 |
| 4 | `expert_planner_base.md` (模板) | `deliver_worker_base.md` (4.6KB) | Worker 基础模板 | ✅ **高复用价值** |
| 5 | `convergence_planner.md` (8.8KB) | — | 约束收敛 | ❌ Deliver Pro 无需收敛 |
| 6 | `research_module.md` (18.5KB) | — | 研究模块编排 | ❌ Deliver Pro 无研究阶段 |
| 7 | `summary_module.md` (28.6KB) | — | 总结模块编排 | ❌ Deliver Pro 无总结阶段 |
| 8 | `reviewer_meta.md` (7.2KB) | `deliver_validate.md` (2.4KB) | 质量裁判 | ✅ **可复用评分框架** |
| 9 | `reviewer_convergence.md` (10.5KB) | — | 收敛审查 | ❌ |
| 10 | `_shared_subagent_rules.md` (共享规则) | — | 子 Agent 通用规则 | ✅ **应直接复用** |
| 11 | — | `deliver_integrate.md` (2.0KB) | 组装集成 | ❌ Deliver Pro 独有 |
| 12 | — | `deliver_package.md` (3.0KB) | 最终打包 | ❌ Deliver Pro 独有 |
| 13 | — | `deliver_pulse.md` (3.3KB) | 脉冲调度 | ❌ Deliver Pro 独有 |
| 14-16 | `summary_*` (6 个 summary prompts) | — | Summary 子阶段 | ❌ |

**关键发现**: Solution Pro 是 250KB/16 prompts 的"重型"体系，Deliver Pro 是 24KB/7 prompts 的"轻量"体系。Deliver Pro 缺少共享规则文件，导致每个 prompt 都要重复写铁律。

---

## 2. Prompt 质量评估

### 2.1 五要素覆盖度

| Prompt | Role | Context | Constraints | Examples | Output | 评分 |
|--------|------|---------|-------------|----------|--------|------|
| **Solution Pro** | | | | | | |
| orchestrator.md | ✅ | ✅ | ✅ | ❌ | ✅ (状态机) | 4/5 |
| planning_module.md | ✅ | ✅ | ✅ | ❌ | ✅ (文件路径) | 4/5 |
| meta_planner.md | ✅ | ✅ | ✅ | ✅ (3 场景) | ✅ (JSON Schema) | 5/5 |
| expert_planner_base.md | ✅ | ✅ | ✅ | ✅ (2 示例) | ✅ (JSON Schema) | 5/5 |
| convergence_planner.md | ✅ | ✅ | ✅ | ✅ (2 场景) | ✅ (JSON Schema) | 5/5 |
| research_module.md | ✅ | ✅ | ✅ | ❌ | ✅ | 4/5 |
| summary_module.md | ✅ | ✅ | ✅ | ❌ | ✅ | 4/5 |
| **Deliver Pro** | | | | | | |
| deliver_orchestrator.md | ✅ | ✅ | ✅ | ❌ | ✅ | 4/5 |
| deliver_analyze.md | ✅ | ✅ | ✅ | ❌ | ✅ (JSON Schema) | 4/5 |
| deliver_worker_base.md | ✅ | ✅ | ✅ | ❌ | ✅ (4 文件) | 4/5 |
| deliver_validate.md | ✅ | ✅ | ✅ | ❌ | ✅ (JSON Schema) | 4/5 |
| deliver_integrate.md | ✅ | ✅ | ✅ | ❌ | ✅ (JSON Schema) | 4/5 |
| deliver_package.md | ✅ | ✅ | ✅ | ❌ | ✅ (JSON Schema) | 4/5 |
| deliver_pulse.md | ✅ | ✅ | ✅ | ❌ | ✅ | 4/5 |

**结论**: Solution Pro 的 meta_planner/expert_planner_base/convergence_planner 是五要素最完整的（5/5），因为它们有场景化示例。Deliver Pro 全部 4/5，缺少 Examples 是共性短板。

### 2.2 冗余/冲突指令

#### 2.2.1 Deliver Pro 铁律重复（严重）

以下铁律在 7 个 prompt 中重复出现：

| 铁律 | 出现次数 | 出现位置 |
|------|---------|---------|
| "不修改他人产出" | 5/7 | worker_base, analyze, integrate, validate, package |
| "不 spawn 子 Agent" | 5/7 | worker_base, analyze, integrate, validate, package |
| "❌ 禁止操作" 列表 | 6/7 | 除 pulse 外全部 |
| "第一行动硬约束" | 6/7 | 除 orchestrator 外全部 |
| "路径铁律" | 3/7 | worker_base, package, validate |

**问题**: 每个 prompt 重复写相同铁律 → token 浪费 + 维护成本（改一处需改 N 处）。
**根因**: Deliver Pro 缺少 `_shared_subagent_rules.md`。

#### 2.2.2 Solution Pro 冗余（中等）

| 冗余项 | 位置 | 说明 |
|--------|------|------|
| "Wake Response Protocol" | planning_module + research_module + summary_module | 三模块完全相同的 5 条规则 |
| "生命周期协议" | planning_module + research_module + summary_module | 相同的心跳/mark_completed 模板 |
| "Fail Fast" | 每个 module prompt | 相同的失败写入模板 |
| "Checkpoint Resume" | planning_module + research_module + summary_module | 相同的断点续跑逻辑 |

**问题**: 3 个 module prompt 合计 68.8KB，其中约 30% 是重复的"生存铁律"和"轮询协议"。

#### 2.2.3 冲突指令

| 冲突 | 位置 A | 位置 B | 说明 |
|------|--------|--------|------|
| yield 策略 | deliver_orchestrator.md: "spawn 后必须 sessions_yield()" | deliver_pulse.md: "绝不 sessions_yield()" | **架构冲突**：orchestrator 已废弃但仍在 prompts/ 目录，新架构是 pulse |
| 调度模式 | orchestrator.md: "wait_for 轮询" | deliver_orchestrator.md: "yield+drive_all" | **跨域不一致**：两个域用不同调度模式 |

### 2.3 task 长度风险

| Prompt | 大小 | 截断风险 | 说明 |
|--------|------|---------|------|
| summary_module.md | 28.6KB | 🔴 高 | 包含 9 步完整流程 + 所有 Python 代码模板，可能超 task 上限 |
| planning_module.md | 21.7KB | 🔴 高 | 包含 6 步 + 所有 spawn 模板 |
| research_module.md | 18.5KB | ⚠️ 中 | 包含 4 步 + spawn 模板 |
| summary_json_extractor.md | 15.4KB | ⚠️ 中 | 单 Worker prompt 最大 |
| summary_review_layer_b.md | 12.5KB | ⚠️ 中 | |
| deliver_pro 全部 | < 5.3KB | ✅ 低 | 轻量设计，无截断风险 |

**关键风险**: Solution Pro 的 module prompts 将"调度逻辑 + Python 代码模板 + 验证逻辑"全部内联在 prompt 中，导致 prompt 巨大。这些代码模板应该抽取为 Python 工具函数，prompt 只保留调用指令。

---

## 3. Agent 调度层级分析

| 层级 | Solution Pro | Deliver Pro | 合理性 |
|------|-------------|-------------|--------|
| **depth-0** | Main Agent (触发) | Main Agent (触发) | ✅ 一致 |
| **depth-1** | Orchestrator (薄层调度) | Pulse Agent (脉冲调度) | ⚠️ 模式不同 |
| **depth-2** | Module Agents ×3 (Planning/Research/Summary) | Phase Agents ×5 (Analyze/Workers/Validate/Package/Pulse) | ⚠️ Deliver Pro 层级扁平 |
| **depth-3** | Worker Agents (Meta Planner, Expert Planners, etc.) | Worker Agents (每个 task 一个) | ✅ 一致 |
| **最大深度** | 4 层 (Main→Orch→Module→Worker) | 3 层 (Main→Pulse→Worker) | ✅ Deliver Pro 更浅 |

### 3.1 Solution Pro 调度分析

```
Main Agent
  └── Orchestrator (depth-1, 薄层)
        ├── Planning Module Agent (depth-2)
        │     ├── Meta Planner (depth-3)
        │     ├── Expert Planners ×N (depth-3, 并行)
        │     ├── Convergence Planner (depth-3)
        │     ├── Reviewer Meta (depth-3)
        │     └── Reviewer Convergence (depth-3)
        ├── Research Module Agent (depth-2)
        │     ├── Research Planner (depth-3)
        │     ├── Research Experts ×N (depth-3, 并行)
        │     └── Consolidator (depth-3)
        └── Summary Module Agent (depth-2)
              ├── Base Synthesizer (depth-3)
              ├── Meta Summary Planner (depth-3)
              ├── Analyzers ×N (depth-3, 并行)
              ├── Fix Judge (depth-3)
              ├── Refiner (depth-3)
              ├── Harness Check (depth-3)
              ├── Document Writer (depth-3)
              └── JSON Extractor (depth-3)
```

**优点**:
- Module Agent 是"厚编排器"，能处理复杂的多步流程
- 并行 Expert 提升效率
- 质量保障链完整（Analyzer→Fix Judge→Refiner→Harness Check）

**问题**:
- Module Agent prompt 过大（21-29KB），包含大量 Python 代码模板
- 4 层深度增加延迟和 token 消耗
- Module Agent 既是调度器又是验证器，职责不够单一

### 3.2 Deliver Pro 调度分析

```
Main Agent
  └── Pulse Agent (depth-1, 脉冲调度)
        ├── Analyze Agent (depth-2)
        ├── Worker Agents ×N (depth-2, 并行)
        ├── Integrate Agent (depth-2)
        ├── Validate Agent (depth-2)
        └── Package Agent (depth-2)
```

**优点**:
- 3 层深度，比 Solution Pro 浅
- Pulse 调度解耦了调度逻辑（Python 实现，prompt 只描述协议）
- 每个 Phase Agent prompt 轻量（2-5KB）

**问题**:
- 缺少 Module Agent 层 → Phase Agent 的编排逻辑在 Python 代码中而非 prompt
- Validate→(fix loop)→Integrate 的循环控制完全依赖 Python，prompt 无描述
- 5 个 Phase Agent 串行执行（除 Workers 并行），效率受限

### 3.3 调度合理性评估

| 维度 | Solution Pro | Deliver Pro | 建议 |
|------|-------------|-------------|------|
| 层级深度 | 4 层（偏深） | 3 层（合理） | Deliver Pro 更优 |
| 调度逻辑位置 | Prompt 内联（重） | Python 代码（轻） | Deliver Pro 更优 |
| 并行度 | Expert 并行 | Workers 并行 | 一致 |
| 质量保障 | 内置 4 步质量链 | 独立 Validate Agent | Solution Pro 更完整 |
| 断点续跑 | Module 级 checkpoint | Pulse 文件系统推导 | Deliver Pro 更优雅 |
| Prompt 大小 | 18-29KB（过大） | 2-5KB（合理） | Deliver Pro 更优 |

---

## 4. 可复用 Prompt 模板

### 4.1 高复用价值模板

| 模板 | 当前使用者 | 潜在使用者 | 泛化建议 |
|------|-----------|-----------|---------|
| `_shared_subagent_rules.md` | Solution Pro | **Deliver Pro（必须）** | 直接复制，Deliver Pro 应立即引入 |
| `expert_planner_base.md` | Solution Pro | Deliver Pro Worker | 泛化为 `worker_base_template.md`，去掉 expert 特定字段 |
| `reviewer_meta.md` (评分框架) | Solution Pro | Deliver Pro Validate | 6 维度评分 + 门禁规则可直接复用 |
| `convergence_planner.md` (合并逻辑) | Solution Pro | Deliver Pro Integrate | 语义去重 + 冲突解决逻辑可复用 |
| Module prompt 的 "Checkpoint Resume" 段 | Solution Pro | Deliver Pro（可选） | 泛化为 `checkpoint_resume_template.md` |
| Module prompt 的 "Fail Fast" 段 | Solution Pro | Deliver Pro（可选） | 泛化为 `fail_fast_template.md` |

### 4.2 `_shared_subagent_rules.md` 适用性分析

**当前内容**（Solution Pro 独有）:
- Preamble 规则（cd + PYTHONPATH）
- Blackboard 文件读取防御性编码
- BlackboardManager API 快速参考
- edit 工具使用约束
- 中文路径处理
- 禁止操作列表

**Deliver Pro 适用性**: ✅ **完全适用**

Deliver Pro 的每个 prompt 都在重复写类似的规则：
- `deliver_worker_base.md`: "所有输出文件必须写入上方绝对路径"
- `deliver_package.md`: "路径铁律（P0）"
- `deliver_orchestrator.md`: "exec preamble"、"Blackboard 文件读取"、"防御性编码规则"

**建议**: 将 Deliver Pro 的通用规则抽取到 `_shared_subagent_rules.md`，每个 prompt 只需引用。

### 4.3 `expert_planner_base.md` 泛化

**当前结构**:
```
Role (domain expert) → Input (spec data) → Output (ExpertPlanSchema) → Constraints → Examples
```

**Deliver Pro Worker 对比**:
```
Role (task executor) → Input (task details) → Output (4 files) → Constraints → Self-check
```

**泛化建议**: 创建 `worker_base_template.md`：
```markdown
# Worker Base Template

## 身份
- 角色: {role_name}
- 目标: {objective}
- 原则: {principles}

## 输入
{input_spec}

## 输出
{output_spec}

## 约束
{constraints}

## 示例（可选）
{examples}

## 自检
{self_check}
```

---

## 5. 重构建议

### 5.1 Deliver Pro 需要重写的 Prompt

| Prompt | 问题 | 重写建议 |
|--------|------|---------|
| `deliver_orchestrator.md` | 已废弃但仍存在，与 `deliver_pulse.md` 冲突 | **删除或归档**到 `_archive/` |
| `deliver_worker_base.md` | 缺少 Examples；铁律重复 | 引入 `_shared_subagent_rules.md` 后精简 |
| `deliver_analyze.md` | 缺少 Examples；输出 Schema 可更严格 | 添加 1-2 个示例 execution_plan |

### 5.2 可以合并的 Prompt

| 合并项 | 当前 | 建议 |
|--------|------|------|
| Solution Pro "生存铁律" ×3 | planning_module + research_module + summary_module 各写一遍 | 抽取到 `_shared_module_rules.md` |
| Solution Pro "轮询协议" ×3 | 三模块各写一遍 | 抽取到 `_shared_poll_protocol.md` |
| Deliver Pro 铁律 ×5 | worker_base + analyze + integrate + validate + package | 抽取到 `_shared_subagent_rules.md` |

### 5.3 Prompt-Code 一致性检查

#### 5.3.1 "Prompt 里写了但代码可能没实现"

| 检查项 | Prompt 位置 | 代码实现 | 状态 |
|--------|-----------|---------|------|
| `lifecycle.heartbeat()` | planning_module.md, research_module.md, summary_module.md | `ModuleLifecycleManager.heartbeat()` | ✅ 已实现 |
| `lifecycle.mark_completed()` | 同上 | `ModuleLifecycleManager.mark_completed()` | ✅ 已实现 |
| `SingleSourceStateManager` | orchestrator.md | `core/process_manager.py` | ✅ 已实现 |
| `ProcessManager.wait_for()` | planning_module.md 等 | `core/process_manager.py` | ✅ 已实现 |
| Deliver Pro `DeliverOrchestrator.drive_all()` | deliver_orchestrator.md | `domains/deliver_pro/orchestrator.py` | ✅ 已实现 |
| Deliver Pro `pulse_cli pulse` | deliver_pulse.md | `domains/deliver_pro/pulse_cli.py` | ✅ 已实现 |
| Solution Pro `render_prompt()` | 所有 module prompts | `core/prompt_utils.py` | ✅ 已实现 |
| Deliver Pro Worker "4 文件输出" | deliver_worker_base.md | Worker 自行 write | ⚠️ 无代码强制校验 |
| Solution Pro "信息守恒约束" | research_module.md, summary_module.md | 无代码强制 | ⚠️ 仅 prompt 约束 |

#### 5.3.2 "代码做了但 Prompt 没提"

| 检查项 | 代码位置 | Prompt 提及 | 状态 |
|--------|---------|-----------|------|
| `domain_analysis.py` DomainProfile | SKILL.md 提及 | orchestrator.md 未提及 | ⚠️ 应补充 |
| `post_validator.py` | SKILL.md 提及 | orchestrator.md 明确说"已移除" | ✅ 一致 |
| Deliver Pro `auto_completed` 字段 | deliver_orchestrator.md 提到 | Python 代码 | ✅ 一致 |

### 5.4 优先级排序

| 优先级 | 行动 | 预期收益 |
|--------|------|---------|
| **P0** | Deliver Pro 引入 `_shared_subagent_rules.md` | 消除 5 个 prompt 的铁律重复，减少约 30% token |
| **P0** | 归档 `deliver_orchestrator.md` 到 `_archive/` | 消除与 `deliver_pulse.md` 的架构冲突 |
| **P1** | Solution Pro 抽取 `_shared_module_rules.md` | 3 个 module prompt 减少约 30% 重复 |
| **P1** | Deliver Pro 为每个 prompt 添加 Examples | 五要素覆盖度从 4/5 提升到 5/5 |
| **P2** | Solution Pro module prompts 的 Python 代码模板抽取为工具函数 | prompt 大小减少 40-50% |
| **P2** | 泛化 `expert_planner_base.md` → `worker_base_template.md` | 跨域复用 |

---

## 6. 总结

### 6.1 核心发现

1. **架构差异**: Solution Pro 是"重 prompt + 轻代码"（250KB prompts），Deliver Pro 是"轻 prompt + 重代码"（24KB prompts + Python orchestrator）。Deliver Pro 的架构更优。

2. **最大浪费**: Deliver Pro 缺少 `_shared_subagent_rules.md`，导致铁律在 5-6 个 prompt 中重复。Solution Pro 的 3 个 module prompt 有 30% 重复内容。

3. **调度演进**: Solution Pro 从 V2→V4 不断简化（13→10 状态），Deliver Pro 从 yield→pulse 演进。两者都在向"薄 prompt + 厚代码"方向发展。

4. **质量保障**: Solution Pro 的 4 步质量链（Analyzer→Fix Judge→Refiner→Harness Check）比 Deliver Pro 的独立 Validate Agent 更完整。Deliver Pro 可考虑引入类似机制。

### 6.2 立即行动

```
1. cp solution_pro/prompts/_shared_subagent_rules.md → deliver_pro/prompts/
2. mv deliver_pro/prompts/deliver_orchestrator.md → deliver_pro/prompts/_archive/
3. 每个 deliver_pro prompt 删除重复铁律，改为引用 _shared_subagent_rules.md
```

### 6.3 长期方向

- **Prompt 应该是"协作契约"**：声明 What + Why，不声明 How
- **How 应该在代码中**：调度逻辑、验证逻辑、重试逻辑都应该是 Python
- **Prompt 大小目标**: 单 prompt < 5KB（Deliver Pro 已达标，Solution Pro 需努力）
