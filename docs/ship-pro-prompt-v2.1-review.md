# Ship Pro Prompt V2.1 检查清单评审报告

> 评审时间: 2026-07-29 13:20 CST
> 评审范围: orchestrator.md + consolidator.md
> 评审标准: Prompt Doctor V2.1 检查清单

---

## 一、逐项检查结果

### 1. Layer 1（必须通过）— 安全与可靠性

| # | 检查项 | orchestrator.md | consolidator.md | 判定 |
|---|--------|:---:|:---:|:---:|
| 1.1 | 有明确的"任务边界"声明（负责/不负责） | ✅ | ⚠️ | **部分通过** |
| 1.2 | 有显式的"状态转移表"（每个状态有出边） | ✅ | ❌ | **不通过** |
| 1.3 | 有"完成条件"声明（成功条件 + 无法恢复条件） | ✅ | ❌ | **不通过** |
| 1.4 | 有"恢复机制"定义（重试策略、降级策略、替代方案） | ⚠️ | ❌ | **不通过** |
| 1.5 | 有"错误分类"定义（瞬时/可恢复/不可恢复） | ⚠️ | ❌ | **不通过** |
| 1.6 | 有"中间产物持久化"定义（文件路径或 blackboard 位置） | ✅ | ❌ | **不通过** |
| 1.7 | ❌ 没有 Fail Fast 思维（此项为反向检查，有 Fail Fast = 通过） | ✅ | ❌ | **不通过** |
| 1.8 | ✅ 有契约笼子（输入契约 + 输出契约 + 错误处理契约） | ⚠️ | ⚠️ | **部分通过** |

**Layer 1 总结**: orchestrator 基本通过（2 项部分通过），consolidator **严重不通过**（6 项缺失）。

---

### 2. Layer 3（必须通过）— 数据流

| # | 检查项 | orchestrator.md | consolidator.md | 判定 |
|---|--------|:---:|:---:|:---:|
| 3.1 | 有明确的"输入源"定义 | ✅ | ✅ | **通过** |
| 3.2 | 有明确的"输出目标"定义 | ✅ | ✅ | **通过** |
| 3.3 | 有"中间产物"清单 | ✅ | ❌ | **部分通过** |

**Layer 3 总结**: orchestrator 完全通过。consolidator 输入/输出明确，但缺少中间产物清单。

---

### 3. Layer 2（推荐通过）— 质量保障

| # | 检查项 | orchestrator.md | consolidator.md | 判定 |
|---|--------|:---:|:---:|:---:|
| 2.1 | 有"质量预期"定义 | ⚠️ | ⚠️ | **部分通过** |
| 2.2 | 有"验证标准"定义 | ✅ | ❌ | **部分通过** |
| 2.3 | 有正面示例 + 负面示例 | ❌ | ❌ | **不通过** |

**Layer 2 总结**: 两个 prompt 都缺少正面/负面行为示例，这是共性弱点。

---

### 4. 通用检查

| # | 检查项 | 判定 | 说明 |
|---|--------|:---:|------|
| G.1 | Worker 执行契约由 Module Agent 注入 | ✅ | orchestrator 通过 `render_prompt` 注入 worker_module.md，Worker 不自己写契约 |
| G.2 | Consolidator 执行契约注入 | ⚠️ | consolidator.md 自身就是最终装配师，但其 prompt 也是由 orchestrator 通过 `render_prompt` 注入的 |

---

## 二、详细问题分析

### orchestrator.md 详细发现

#### ✅ 优势项
1. **状态机设计完备** — 14 个状态、16 条转移，每条转移有触发条件和动作，形成闭合图
2. **执行循环清晰** — EXEC → READ → JUDGE → ACT 四步循环，信号路由表明确
3. **断点恢复协议** — Step 0 自动检测已完成模块，支持从中间恢复
4. **Fail Fast 机制** — 专门的 🔴 Fail Fast 机制章节，MISSING/FAILED 立即结束
5. **Completion Event 处理** — 明确定义为"系统通知，不是控制信号"，有去重机制
6. **Blackboard 持久化** — 所有中间产物写入 blackboard，路径清晰

#### ⚠️ 问题项

**P1-orch-1: 恢复机制不完整 — Designer/Consolidator 无 retry**
- Workers 有 `WORKERS_FIX` 状态支持重试（retry < max）
- Designer 和 Consolidator 失败后直接 → FAILED，无 retry 路径
- **建议**: 至少为 Designer 增加一次 retry（Designer 是 LLM 生成，有随机性）

**P2-orch-2: 错误分类不够精细**
- 信号路由表有 `_OK / _MISSING / _FAILED` 三种信号
- 但 `_MISSING` 和 `_FAILED` 的区别未在错误分类框架中定义
- 缺少"瞬时故障"概念（如 timeout 是瞬时还是永久？）
- **建议**: 增加错误分类表：

```
| 错误类型 | 信号 | 是否可重试 | 示例 |
|---------|------|:---:|------|
| 前置条件缺失 | _MISSING | 否 | frozen_spec 不存在 |
| 执行失败-可重试 | _FAILED(retryable) | 是 | LLM 输出格式错误 |
| 执行失败-不可恢复 | _FAILED(fatal) | 否 | 文件系统不可写 |
| 超时 | _TIMEOUT | 视情况 | wait_for_module 超时 |
```

**P2-orch-3: 缺少完整执行路径的正面/负面示例**
- 信号路由表有信号级示例，但缺少端到端的执行路径示例
- **建议**: 增加一个"正常执行"示例 + 一个"Designer 失败"示例

**P2-orch-4: 契约笼子 — 错误处理契约分散**
- 错误处理逻辑分散在信号路由表、Fail Fast 机制、断点恢复协议三个章节
- 没有统一的"错误处理契约"声明
- **建议**: 增加一个汇总性的错误处理契约章节

---

### consolidator.md 详细发现

#### ✅ 优势项
1. **6 步法流程清晰** — Step 0-6 有序执行，每步有明确输入输出
2. **输出格式定义详细** — ShipPackage JSON schema 完整，含字段说明
3. **Semantic Anchors 透传** — 契约笼子意识强，MUST 标记突出
4. **WP 整合策略合理** — 互补/冲突/重复三种重叠处理策略
5. **领域自适应** — Step 0 根据 domain_analysis 选择组装策略

#### ❌ 严重缺失

**P0-con-1: 无状态转移表**
- 6 步法是顺序流程，但没有形式化的状态定义
- 没有状态名、没有转移条件、没有回退路径
- **影响**: 无法实现断点恢复，crash 后只能从头开始
- **建议**: 为 6 步法定义状态：

```
| 状态 | 出边 | 触发条件 |
|------|------|---------|
| CONS_INIT | → CONS_DOMAIN | 入口 |
| CONS_DOMAIN | → CONS_COLLECT | domain 判断完成 |
| CONS_COLLECT | → CONS_SEMANTIC | 文件读取成功 |
| CONS_COLLECT | → CONS_FAILED | 文件读取失败 |
| CONS_SEMANTIC | → CONS_CONFLICT | 整合完成 |
| CONS_CONFLICT | → CONS_DEPENDENCY | 冲突检测完成 |
| CONS_DEPENDENCY | → CONS_ANCHORS | 依赖图构建完成 |
| CONS_ANCHORS | → CONS_REVIEW | anchors 透传完成 |
| CONS_REVIEW | → CONS_ASSEMBLE | 用户视角检查通过 |
| CONS_ASSEMBLE | → CONS_DONE | ShipPackage 写入成功 |
| CONS_DONE | 无 | 终态 |
| CONS_FAILED | 无 | 终态 |
```

**P0-con-2: 无完成条件声明**
- 没有声明"什么情况下算成功完成"
- 没有声明"什么情况下无法恢复，必须失败"
- **建议**: 增加：

```
## 完成条件
### 成功条件
- ShipPackage JSON 写入 output_path
- semantic_anchors 和 anchor_coverage 字段存在
- work_packages 非空且每个 WP 有完整字段

### 无法恢复条件
- 所有 worker 输出文件均不存在或为空
- solution_pro_input_path 不存在
- output_path 不可写
```

**P0-con-3: 无错误分类定义**
- Step 1 文件读取失败时行为未定义
- Step 5 读取 solution_pro_input 失败时行为未定义
- JSON 解析失败时行为未定义
- **建议**: 增加错误分类表

**P0-con-4: 无恢复机制**
- 6 步法中任何一步失败，没有 retry、降级、替代方案
- **建议**: 至少定义关键步骤的降级策略：
  - Step 1 部分文件缺失 → 降级：处理已有文件，在 issues 中记录缺失
  - Step 5 solution_pro_input 不存在 → 降级：semantic_anchors 设为 []

**P0-con-5: 无中间产物持久化定义**
- 6 步处理过程中间结果（整合后的 WP 列表、冲突检测结果、依赖图）全部在内存中
- crash 后无法恢复，必须从头开始
- **建议**: 关键中间结果写入 blackboard：
  - `stages/consolidator_intermediate/collected_wps.json`
  - `stages/consolidator_intermediate/conflict_report.json`
  - `stages/consolidator_intermediate/dependency_graph.json`

**P0-con-6: 无 Fail Fast**
- Step 0 领域判断失败后，流程继续执行
- Step 1 文件全部缺失时，空列表继续处理
- **建议**: 每步增加前置检查和快速失败

**P1-con-7: 契约笼子不完整**
- 输入契约：有 worker_file_paths 和 solution_pro_input_path，但无格式验证
- 输出契约：ShipPackage JSON 格式定义完整 ✅
- 错误处理契约：❌ 完全缺失
- **建议**: 增加输入验证：

```
## 输入契约
- worker_file_paths 必须非空，每个文件必须存在且可解析为 JSON
- 每个 worker JSON 必须包含 work_packages 数组
- solution_pro_input_path 必须存在且可解析（如不存在 → 立即失败）
```

---

## 三、问题清单汇总

### P0（必须修复 — 阻塞发布）

| ID | 文件 | 问题 | 影响 |
|----|------|------|------|
| P0-con-1 | consolidator.md | 无状态转移表 | 无法断点恢复，无法形式化验证 |
| P0-con-2 | consolidator.md | 无完成条件声明 | 不知道何时算成功/失败 |
| P0-con-3 | consolidator.md | 无错误分类定义 | 错误处理靠 LLM 自由裁量 |
| P0-con-4 | consolidator.md | 无恢复机制 | 任何故障只能从头开始 |
| P0-con-5 | consolidator.md | 无中间产物持久化 | crash 后丢失所有中间结果 |
| P0-con-6 | consolidator.md | 无 Fail Fast | 错误会静默传播到下游 |

### P1（应该修复 — 影响可靠性）

| ID | 文件 | 问题 | 影响 |
|----|------|------|------|
| P1-orch-1 | orchestrator.md | Designer/Consolidator 无 retry | LLM 随机性导致的失败无法自愈 |
| P1-con-7 | consolidator.md | 输入契约无格式验证 | 错误格式的输入会导致不可预测行为 |
| P1-con-8 | consolidator.md | 无错误处理契约 | 错误时 LLM 自由裁量，行为不一致 |

### P2（建议修复 — 提升质量）

| ID | 文件 | 问题 | 影响 |
|----|------|------|------|
| P2-orch-2 | orchestrator.md | 错误分类不够精细 | 无法区分瞬时/永久故障 |
| P2-orch-3 | orchestrator.md | 缺少端到端正/负面示例 | LLM 可能对流程理解偏差 |
| P2-orch-4 | orchestrator.md | 错误处理契约分散 | 维护困难，容易遗漏 |
| P2-both-1 | 两者 | 缺少正面+负面行为示例 | LLM 行为边界不清晰 |
| P2-both-2 | 两者 | 质量预期定义模糊 | 无量化标准 |

---

## 四、修复建议优先级

### 第一优先级：consolidator.md 的 6 个 P0

consolidator.md 是 V2.1 检查清单的**重度不合格者**。它本质上是一个"流程描述文档"，不是一个"可形式化验证的 prompt"。需要补充：

1. **状态转移表**（P0-con-1）— 为 6 步法增加形式化状态定义
2. **完成条件**（P0-con-2）— 声明成功/无法恢复条件
3. **错误分类**（P0-con-3）— 定义错误类型和处理策略
4. **恢复机制**（P0-con-4）— 至少为 Step 1 增加降级策略
5. **中间产物持久化**（P0-con-5）— 关键中间结果写入 blackboard
6. **Fail Fast**（P0-con-6）— 每步增加前置检查

### 第二优先级：orchestrator.md 的 P1

7. **Designer retry**（P1-orch-1）— 增加 `DESIGNER_FIX` 状态或类似机制

### 第三优先级：P2 改进

8. 统一错误分类框架
9. 增加端到端示例
10. 集中错误处理契约

---

## 五、评分总结

| 维度 | orchestrator.md | consolidator.md |
|------|:---:|:---:|
| Layer 1 通过率 | 6/8 通过 + 2 部分通过 | 0/8 通过 + 2 部分通过 |
| Layer 3 通过率 | 3/3 通过 | 2/3 通过 + 1 缺失 |
| Layer 2 通过率 | 1/3 部分通过 | 0/3 通过 + 2 缺失 |
| 通用检查 | ✅ 通过 | ✅ 通过 |
| **综合评级** | **🟡 B+ (基本合格)** | **🔴 D (严重不合格)** |

### 核心结论

- **orchestrator.md** 是 V3.0 重构后的成熟 prompt，状态机完备、执行循环清晰、Fail Fast 到位。主要改进空间在错误分类精细度和 retry 机制覆盖。
- **consolidator.md** 仍然是一个"流程描述"级别的 prompt，缺少 V2.1 要求的所有关键可靠性机制。需要**结构性重写**，补充状态转移表、完成条件、错误分类、恢复机制、中间产物持久化、Fail Fast 六大模块。

---

*Report generated by Prompt Doctor V2.1 | Ship Pro domain review*
