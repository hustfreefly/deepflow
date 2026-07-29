# Ship Pro Prompt Doctor V2.1 检查报告

**检查时间**: 2026-07-29 13:11  
**检查范围**: Ship Pro 2 个核心 prompt  
**检查标准**: Prompt Doctor V2.1（稳健性优先 + 契约笼子）

---

## 检查结果汇总

| Prompt | Layer 1 | Layer 3 | Layer 2 | 通用 | 总体评级 |
|--------|---------|---------|---------|------|----------|
| orchestrator.md | ❌ 不通过 | ✅ 通过 | ⚠️ 部分 | ⚠️ 部分 | **C+** |
| consolidator.md | ❌ 不通过 | ✅ 通过 | ✅ 通过 | ⚠️ 部分 | **B-** |

**总体评级**: **C+**（Layer 1 存在严重问题）

---

## 详细检查结果

### 1. orchestrator.md

#### Layer 1 检查（必须通过）❌ 不通过

- ✅ **任务边界**: 有明确声明（"你是 Ship Pro V3.0 的薄层调度器"）
- ✅ **状态转移表**: 有显式定义（14 个状态，16 条转移）
- ✅ **完成条件**: 有明确声明（"PIPELINE_COMPLETED → 生成最终报告"）
- ❌ **恢复机制**: **缺失**（只有 Fail Fast，没有智能恢复）
- ❌ **错误分类**: **缺失**（没有区分瞬时故障/可恢复错误/不可恢复错误）
- ✅ **中间产物持久化**: 有明确定义（"stages/pipeline_plan.json"、"stages/ship_package.json"）
- ❌ **没有 Fail Fast 思维**: **❌ 违反**（"立即结束 turn。不继续。不写假数据。不尝试恢复。"）
- ❌ **有契约笼子**: **❌ 缺失**（没有输入契约、输出契约、错误处理契约）

**严重问题**:
1. **Fail Fast 思维**：任何阶段输出 MISSING 或 FAILED 时，立即结束 turn，不尝试恢复
2. **无错误分类**：没有区分瞬时故障（可重试）和不可恢复错误
3. **无恢复机制**：没有重试策略、降级策略、替代方案
4. **无契约笼子**：没有输入契约、输出契约、错误处理契约

#### Layer 3 检查（必须通过）✅ 通过

- ✅ **输入源**: 有明确定义（"data/living_spec.json"、"data/frozen_spec.json"）
- ✅ **输出目标**: 有明确定义（"stages/pipeline_plan.json"、"stages/ship_package.json"）
- ✅ **中间产物清单**: 有明确定义（MODULE_CONFIG 中的文件列表）

#### Layer 2 检查（推荐通过）⚠️ 部分通过

- ⚠️ **质量预期**: 部分定义（有文件大小要求，但没有质量验证标准）
- ⚠️ **验证标准**: 部分定义（只检查文件是否存在，没有 Schema 校验）
- ❌ **正面示例 + 负面示例**: 缺失

#### 通用检查 ⚠️ 部分通过

- ✅ **Prompt 结构清晰**: 分层 + 编号
- ✅ **关键约束放在顶部**: 执行循环在顶部
- ❌ **有负面示例**: 缺失
- ✅ **spawn task 使用文件引用**: 符合
- ❌ **Worker 执行契约由 Module Agent 注入**: **❌ 缺失**（spawn task 没有注入执行契约）

**改进建议**:
1. **P0**: 移除 Fail Fast 思维，添加智能恢复机制
2. **P0**: 添加错误分类（瞬时故障/可恢复错误/不可恢复错误）
3. **P0**: 添加恢复机制（重试策略、降级策略）
4. **P0**: 添加契约笼子（输入契约、输出契约、错误处理契约）
5. **P1**: 在 spawn task 中注入 Worker 执行契约
6. **P2**: 添加质量验证标准（Schema 校验）
7. **P2**: 添加正面示例 + 负面示例

---

### 2. consolidator.md

#### Layer 1 检查（必须通过）❌ 不通过

- ✅ **任务边界**: 有明确声明（"你是 ShipPackage 装配师"）
- ❌ **状态转移表**: **缺失**（没有状态机定义）
- ❌ **完成条件**: **缺失**（没有明确的完成条件声明）
- ❌ **恢复机制**: **缺失**（没有错误处理策略）
- ❌ **错误分类**: **缺失**（没有区分错误类型）
- ✅ **中间产物持久化**: 有明确定义（"stages/ship_package.json"）
- ✅ **没有 Fail Fast 思维**: ✅ 没有 Fail Fast（但没有恢复机制）
- ❌ **有契约笼子**: **❌ 缺失**（没有输入契约、输出契约、错误处理契约）

**严重问题**:
1. **无状态转移表**：没有定义状态机，Agent 不知道如何一步步完成任务
2. **无完成条件**：没有明确的完成条件声明
3. **无恢复机制**：没有错误处理策略
4. **无契约笼子**：没有输入契约、输出契约、错误处理契约

#### Layer 3 检查（必须通过）✅ 通过

- ✅ **输入源**: 有明确定义（"stages/worker_outputs/worker_{role}.json"）
- ✅ **输出目标**: 有明确定义（"stages/ship_package.json"）
- ✅ **中间产物清单**: 有明确定义（6 步法的中间产物）

#### Layer 2 检查（推荐通过）✅ 通过

- ✅ **质量预期**: 有明确定义（"work_packages 必须包含每个 WP 的完整 description + acceptance_criteria + deliverables"）
- ✅ **验证标准**: 有明确定义（"MUST 契约"、"禁止行为"）
- ⚠️ **正面示例 + 负面示例**: 部分定义（有负面示例，但没有正面示例）

#### 通用检查 ⚠️ 部分通过

- ✅ **Prompt 结构清晰**: 分层 + 编号（6 步法）
- ✅ **关键约束放在顶部**: MUST 契约在顶部
- ✅ **有负面示例**: 有（"禁止行为"）
- ❌ **spawn task 使用文件引用**: 不适用（consolidator 是 Worker，不是 Module Agent）
- ❌ **Worker 执行契约由 Module Agent 注入**: **❌ 缺失**（consolidator 是 Worker，应该由 orchestrator 注入执行契约）

**改进建议**:
1. **P0**: 添加状态转移表（定义状态机）
2. **P0**: 添加完成条件（明确什么情况下算完成）
3. **P0**: 添加恢复机制（错误处理策略）
4. **P0**: 添加契约笼子（输入契约、输出契约、错误处理契约）
5. **P1**: 添加正面示例
6. **P2**: 由 orchestrator 在 spawn task 中注入执行契约

---

## 问题分类汇总

### P0 严重问题（必须修复）

| 问题 | 影响 | 修复建议 |
|------|------|----------|
| **orchestrator.md: Fail Fast 思维** | 系统稳健性差，瞬时故障导致整体失败 | 添加智能恢复机制（重试、降级） |
| **orchestrator.md: 无错误分类** | 无法区分瞬时故障和不可恢复错误 | 添加错误分类表 |
| **orchestrator.md: 无恢复机制** | 无法从错误中恢复 | 添加重试策略、降级策略 |
| **orchestrator.md: 无契约笼子** | 没有输入/输出/错误处理契约 | 添加契约笼子（输入契约、输出契约、错误处理契约） |
| **orchestrator.md: 无 Worker 执行契约注入** | Worker 不知道任务边界和完成条件 | 在 spawn task 中注入执行契约 |
| **consolidator.md: 无状态转移表** | Agent 不知道如何一步步完成任务 | 添加状态机定义 |
| **consolidator.md: 无完成条件** | Agent 不知道什么情况下算完成 | 添加完成条件声明 |
| **consolidator.md: 无恢复机制** | 无法从错误中恢复 | 添加错误处理策略 |
| **consolidator.md: 无契约笼子** | 没有输入/输出/错误处理契约 | 添加契约笼子 |

### P1 重要问题（建议修复）

| 问题 | 影响 | 修复建议 |
|------|------|----------|
| **orchestrator.md: 无质量验证标准** | 只检查文件存在，没有 Schema 校验 | 添加 Schema 校验 |
| **consolidator.md: 无正面示例** | Agent 不知道好的输出长什么样 | 添加正面示例 |

### P2 次要问题（可选修复）

| 问题 | 影响 | 修复建议 |
|------|------|----------|
| **orchestrator.md: 无正面/负面示例** | Agent 不知道好的/坏的输出长什么样 | 添加示例 |

---

## 与 Solution Pro 对比

| 维度 | Solution Pro V4.1 | Ship Pro V3.0 | 差距 |
|------|-------------------|---------------|------|
| **契约笼子** | ✅ 已添加 | ❌ 缺失 | **严重落后** |
| **智能恢复** | ✅ 已实现 | ❌ Fail Fast | **严重落后** |
| **错误分类** | ✅ 已定义 | ❌ 缺失 | **严重落后** |
| **Worker 执行契约注入** | ✅ 已实现 | ❌ 缺失 | **严重落后** |
| **状态机** | ✅ 有 | ✅ 有（orchestrator） | 持平 |
| **Layer 3 上下文契约** | ✅ 通过 | ✅ 通过 | 持平 |
| **Layer 2 过程质量** | ⚠️ 部分通过 | ✅ 通过（consolidator） | Ship Pro 更好 |

**结论**: Ship Pro 在 Layer 1（流程可执行性）严重落后于 Solution Pro，需要立即修复。

---

## 修复优先级

### 第一优先级（P0，必须修复）

1. **orchestrator.md**: 移除 Fail Fast，添加智能恢复机制
2. **orchestrator.md**: 添加错误分类表
3. **orchestrator.md**: 添加契约笼子（输入契约、输出契约、错误处理契约）
4. **orchestrator.md**: 在 spawn task 中注入 Worker 执行契约
5. **consolidator.md**: 添加状态转移表
6. **consolidator.md**: 添加完成条件
7. **consolidator.md**: 添加契约笼子

### 第二优先级（P1，建议修复）

8. **orchestrator.md**: 添加质量验证标准（Schema 校验）
9. **consolidator.md**: 添加正面示例

### 第三优先级（P2，可选修复）

10. **orchestrator.md**: 添加正面/负面示例

---

## 修复方案

### orchestrator.md 修复方案

参考 Solution Pro V4.1 的 orchestrator.md，添加：

1. **契约笼子**（放在顶部）
```markdown
## 🔴 契约笼子（V3.1 新增 — 稳健性优先）

### 输入契约（模块输出必须满足）
- ✅ 文件必须存在且非空
- ✅ 文件大小必须 >= 配置的最小值
- ✅ 文件内容必须是有效 JSON
- ❌ 如果不满足 → 触发智能重试（不是直接失败）

### 错误处理契约（智能重试，不降级）
| 错误类型 | 特征 | 恢复策略 |
|---------|------|---------|
| **瞬时故障** | 文件不存在、文件为空 | 等待 30 秒后重试（最多 2 次）|
| **可恢复错误** | 文件大小不足、JSON 格式错误 | 从 checkpoint 恢复，重新执行模块（最多 2 次）|
| **不可恢复错误** | 模块 spawn 失败、checkpoint 损坏 | 报告详细失败原因 |
```

2. **移除 Fail Fast**
```markdown
# 删除：
## 🔴 Fail Fast 机制
任何阶段输出 `MISSING` 或 `FAILED` 时，**立即**执行以下操作...

# 替换为：
## 🔴 智能重试（V3.1 新增）
模块输出 MISSING 时的处理流程：
1. 检查错误类型（瞬时故障？可恢复错误？）
2. 重试 1：等待 30 秒 → 从 checkpoint 恢复 → 重新执行模块
3. 重试 2：等待 60 秒 → 从 checkpoint 恢复 → 重新执行模块
4. 如果 2 次重试后仍 MISSING → 报告详细失败原因
```

3. **在 spawn task 中注入 Worker 执行契约**
```python
sessions_spawn(
    task=f"""cd {_deepflow_root} && PYTHONPATH=.
你执行的所有 Python 命令必须以 cd {_deepflow_root} && PYTHONPATH=. 开头。

## 🔴 你的执行契约（Module Agent 注入）
- **任务边界**：你只负责 {worker_role}。你不负责重试、错误恢复、降级输出。
- **完成条件**：输出写入 blackboard 且通过 Schema 校验。
- **错误报告**：如果无法完成，写入 stages/.worker_failed.json，包含 {{"error_type": "unrecoverable", "error_message": "具体错误", "attempted_actions": ["已尝试的动作"]}}。
- **禁止行为**：不要自行重试，不要降级输出，不要跳过步骤。

## 你的完整指令
用 read 工具读取: {_prompt_path}

读取后按指令执行。"""
)
```

### consolidator.md 修复方案

1. **添加状态转移表**
```markdown
## 🔴 状态机（必须严格遵循）

### 状态全集（7 个状态）

| 状态 | 含义 | 出边 |
|------|------|------|
| `INIT` | Consolidator 刚启动 | → `COLLECT` |
| `COLLECT` | 收集所有 Worker 输出 | → `INTEGRATE` |
| `INTEGRATE` | 语义整合 | → `CONFLICT_DETECT` |
| `CONFLICT_DETECT` | 冲突检测 | → `DEPENDENCY_GRAPH` |
| `DEPENDENCY_GRAPH` | 构建依赖图 | → `ANCHOR_PASSTHROUGH` |
| `ANCHOR_PASSTHROUGH` | Semantic Anchors 透传 | → `ASSEMBLE` |
| `ASSEMBLE` | 组装 ShipPackage | → `COMPLETED` |

### 转移表

| # | 当前状态 | 目标状态 | 触发条件 | 动作 |
|---|---------|---------|---------|------|
| T1 | `INIT` | `COLLECT` | 入口 | 读取 worker_outputs |
| T2 | `COLLECT` | `INTEGRATE` | 所有 WP 收集完成 | 语义整合 |
| T3 | `INTEGRATE` | `CONFLICT_DETECT` | 整合完成 | 冲突检测 |
| T4 | `CONFLICT_DETECT` | `DEPENDENCY_GRAPH` | 冲突检测完成 | 构建依赖图 |
| T5 | `DEPENDENCY_GRAPH` | `ANCHOR_PASSTHROUGH` | 依赖图构建完成 | Semantic Anchors 透传 |
| T6 | `ANCHOR_PASSTHROUGH` | `ASSEMBLE` | 透传完成 | 组装 ShipPackage |
| T7 | `ASSEMBLE` | `COMPLETED` | ShipPackage 写入成功 | 写 `.completed` |
```

2. **添加完成条件**
```markdown
## 🔴 完成条件

### 成功条件
- ✅ 所有 Worker 输出已收集
- ✅ 语义整合完成
- ✅ 冲突检测完成
- ✅ 依赖图构建完成
- ✅ Semantic Anchors 透传完成
- ✅ ShipPackage 写入成功

### 无法恢复条件
- ❌ 所有 Worker 输出文件不存在
- ❌ ShipPackage Schema 校验失败且无法修复
```

3. **添加契约笼子**
```markdown
## 🔴 契约笼子（V3.1 新增 — 稳健性优先）

### 输入契约（必须满足）
- ✅ 所有 Worker 输出文件必须存在
- ✅ 每个文件必须是有效 JSON
- ✅ 每个文件必须包含 `work_packages` 字段
- ❌ 如果不满足 → 报告详细失败原因

### 输出契约（必须满足）
- ✅ 输出必须通过 ShipPackageSchema 校验
- ✅ 必须包含 `semantic_anchors` 和 `anchor_coverage` 字段
- ✅ `work_packages` 必须包含所有 WP 的完整内容
- ❌ 如果不满足 → 报告详细失败原因

### 错误处理契约（智能恢复，不降级）
| 错误类型 | 恢复策略 |
|---------|----------|
| 瞬时故障 | 等待 15 秒后重试（最多 3 次）|
| 可恢复错误 | 尝试修复 → 重试 1 次 |
| 不可恢复错误 | 报告详细失败原因 |
```

---

## 总结

Ship Pro V3.0 在 Layer 1（流程可执行性）严重落后于 Solution Pro V4.1，存在 9 个 P0 严重问题，需要立即修复。

**核心问题**:
1. ❌ Fail Fast 思维（应该智能恢复）
2. ❌ 无错误分类（应该区分瞬时故障/可恢复错误/不可恢复错误）
3. ❌ 无恢复机制（应该添加重试策略、降级策略）
4. ❌ 无契约笼子（应该添加输入契约、输出契约、错误处理契约）
5. ❌ 无 Worker 执行契约注入（应该在 spawn task 中注入执行契约）

**修复优先级**: P0 > P1 > P2

**预计修复时间**: 2-3 小时

---

**报告生成时间**: 2026-07-29 13:11  
**检查工具**: Prompt Doctor V2.1  
**检查人员**: 小满（AI Agent）
