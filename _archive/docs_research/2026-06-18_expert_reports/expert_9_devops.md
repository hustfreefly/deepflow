# 专家 9：DevOps / CI-CD 专家评审报告

> **日期**: 2026-06-18
> **视角**: 构建管线 + 质量门禁 + Artifact 管理 + 可观测性
> **类比框架**: DeepFlow 管线 ≈ CI/CD Pipeline

---

## 管线类比映射

| DeepFlow 阶段 | CI/CD 类比 | 核心职责 |
|:---|:---|:---|
| Spec Pro | 代码提交（Commit） | 定义"要构建什么" |
| Solution Pro（10 阶段） | 构建 + 测试（Build + Test） | 生成方案 + 自验证 |
| Ship Pro | 打包（Package） | 将方案转化为可执行的部署包 |
| Super Loop | 部署（Deploy） | 执行编码/实际交付 |

---

## Q1: Ship Pro 作为"打包"阶段，需要什么输入 artifact？

### CI/CD 类比

在 CI/CD 中，打包阶段的输入是**构建产物**（compiled binary、test reports、dependency manifests）。打包阶段不关心代码怎么写的——它只关心"构建是否成功、测试是否通过、依赖是否明确"。

### 对 DeepFlow 的建议

Ship Pro 需要的输入 artifact 分三类：

| 类别 | 对应文件 | CI/CD 类比 | 必要性 |
|:---|:---|:---|:---|
| **方案主体** | `final_result.json` | 编译后的 binary | ✅ 必须 |
| **验收证据** | `requirements_traceability_matrix.json` | 测试报告 | ✅ 必须 |
| **元数据** | `execution_plan.json` | 构建配置（build manifest） | ✅ 应该读 |
| **设计决策** | `living_blueprint.json` 中的 `design_decisions` | 架构决策记录（ADR） | ⚠️ 可选但有价值 |

**关键建议**：

1. **`final_result.json` 是核心 artifact**，等价于 CI/CD 中的"构建产物"。Ship Pro 不应该尝试重新理解需求或重新设计方案——它只需要"打包"已有产物。

2. **RTM 是质量证明**，等价于测试报告。没有测试报告的打包在 CI/CD 中是不可想象的。Ship Pro 应该用 RTM 来验证方案的完整性（需求是否都有对应实现）。

3. **`execution_plan.json` 提供上下文**（topic、constraints、stakeholders），等价于构建配置中的环境变量。Ship Pro 需要知道约束条件才能做出合理的工时估算和优先级排序。

4. **`design_decisions`（tradeoffs、rejected_alternatives）是锦上添花**。在 CI/CD 中，这相当于"为什么选这个依赖"的文档。对打包阶段不是必须的，但对部署阶段（Super Loop）理解设计意图有帮助。

### 实施信心评分：8/10

> 输入 artifact 的选择是清晰的。唯一的不确定性是 `design_decisions` 的价值——如果 Super Loop 不需要理解"为什么这样设计"，可以不读。

---

## Q2: 管线中每个阶段的 artifact 应该如何管理？

### CI/CD 最佳实践

CI/CD 中的 artifact 管理遵循以下原则：

1. **不可变性（Immutability）**: 一旦 artifact 生成，就不修改。需要变更就重新构建。
2. **版本化（Versioning）**: 每个 artifact 有唯一标识，可追溯。
3. **保留策略（Retention Policy）**: 中间产物可以丢弃，最终产物必须保留。
4. **单一来源（Single Source of Truth）**: 每个信息只在一个地方存在。

### 对 DeepFlow 的建议

| Artifact | 生成阶段 | 消费阶段 | 保留策略 | 理由 |
|:---|:---|:---|:---|:---|
| `final_result.json` | Solution Pro | Ship Pro → Super Loop | ✅ 永久保留 | 核心方案，SSOT |
| `requirements_traceability_matrix.json` | Solution Pro | Ship Pro | ✅ 永久保留 | 验收证据链 |
| `execution_plan.json` | Solution Pro | Ship Pro | ✅ 永久保留 | 项目元数据 |
| `ship_package.json` | Ship Pro | Super Loop | ✅ 永久保留 | 最终打包产物 |
| `tasks.json` | Solution Pro（内部） | Solution Pro（内部） | ❌ 调试后可丢弃 | 10 阶段 prompt，~120KB |
| `control_contract.json` | Solution Pro（内部） | Solution Pro（内部） | ❌ 调试后可丢弃 | 执行契约 |
| `frozen_blueprint.json` | Solution Pro | Ship Pro | ❌ 停止生成 | 有损压缩，已被 final_result 替代 |
| `living_blueprint.json` | Solution Pro | Ship Pro（可选） | ⚠️ 按需保留 | 仅 design_decisions 有价值 |
| `ship_review_data.json` | Ship Pro（内部） | Ship Pro（内部） | ❌ 停止持久化 | 中间计算产物 |
| `domain_config.json` | Ship Pro（内部） | Ship Pro（内部） | ❌ 停止持久化 | 中间配置产物 |

**关键建议**：

1. **区分"对外 artifact"和"内部 artifact"**：
   - 对外：`final_result.json`、`RTM.json`、`ship_package.json` — 必须保留，有版本
   - 内部：`tasks.json`、`control_contract.json`、`ship_review_data.json` — 移到 `.internal/`，调试完可丢弃

2. **引入 artifact 版本化**：
   ```
   blackboard/
   ├── v1/
   │   ├── final_result.json
   │   ├── requirements_traceability_matrix.json
   │   └── execution_plan.json
   ├── v2/  (如果方案迭代)
   └── current -> v1/  (symlink)
   ```
   或者更简单：在文件名中加时间戳/hash。

3. **`frozen_blueprint.json` 的砍掉是正确的**：
   在 CI/CD 中，你不会把"编译中间产物"当作最终交付物。`frozen_blueprint` 就是有损压缩的中间产物，保真度只有 32%，相当于把 PNG 压缩成 JPEG 再压缩成 JPEG——信息损失不可接受。

### 实施信心评分：9/10

> Artifact 管理是 CI/CD 中最成熟的领域，最佳实践清晰。DeepFlow 的 artifact 相对简单（都是 JSON），不需要复杂的仓库系统。

---

## Q3: 质量门禁应该放在哪里？

### CI/CD 中的质量门禁模式

质量门禁（Quality Gates）在 CI/CD 中的典型位置：

| 门禁位置 | 检查内容 | 失败后果 |
|:---|:---|:---|
| 提交后（Post-Commit） | 代码风格、静态分析 | 阻止构建 |
| 构建后（Post-Build） | 编译成功、单元测试 | 阻止打包 |
| 打包后（Post-Package） | 依赖扫描、安全审计 | 阻止部署 |
| 部署前（Pre-Deploy） | 集成测试、性能测试 | 阻止上线 |

### 对 DeepFlow 的建议

**当前 Blueprint Freezing 本质上是一个质量门禁**——它验证"方案是否足够稳定，可以交给下游"。砍掉它后，需要在其他地方设置等价的质量门禁。

**建议的质量门禁布局**：

| 门禁 | 位置 | 检查内容 | 实施难度 |
|:---|:---|:---|:---|
| **G1: 方案完整性检查** | Solution Pro 结束时 | 所有 P0 需求有对应实现、RTM 覆盖率 ≥ 90% | 低 |
| **G2: 格式合规检查** | Ship Pro 输入时 | `final_result.json` 结构可解析、必要字段存在 | 低 |
| **G3: 打包完整性检查** | Ship Pro 结束时 | 每个 WP 有 AC、有工时估算、有依赖关系 | 中 |
| **G4: 可执行性检查** | Super Loop 开始时 | WP 的 AC 可验证、技术约束不矛盾 | 高 |

**具体建议**：

1. **G1（方案完整性）替代 Blueprint Freezing**：
   - 在 Solution Pro 的 summarizer 阶段加一个检查：遍历 RTM，确认每个需求的 `coverage_status` 不是 `uncovered`
   - 如果覆盖率 < 90%，触发重试或标记为"需要人工审查"
   - 这比 Blueprint Freezing 更好——它直接检查需求覆盖，而不是检查"方案是否稳定"

2. **G2（格式合规）是 Ship Pro 的前置条件**：
   - Ship Pro 读 `final_result.json` 前，先验证 JSON 结构
   - 如果关键字段缺失（如 `architecture` 或 `final_solution`），报错并请求 Solution Pro 重新生成
   - 这相当于 CI/CD 中的"构建产物完整性检查"

3. **G3（打包完整性）是 Ship Pro 的出口检查**：
   - 每个 WP 必须有：`id`、`title`、`acceptance_criteria`（至少 1 条）、`estimated_hours`
   - 如果缺失，Ship Pro 应该补充而不是跳过
   - 这相当于"打包后检查箱子是否封好"

4. **G4（可执行性）是 Super Loop 的入口检查**：
   - 检查 WP 的 AC 是否有 `verification` 字段
   - 检查依赖关系是否有环
   - 检查技术约束是否矛盾（如"必须用 AWS" vs "必须用阿里云"）
   - 这相当于"部署前检查配置是否正确"

### 实施信心评分：7/10

> 质量门禁的设计是清晰的，但实施难度在于：
> - G1 需要 Solution Pro 的 summarizer 配合
> - G4 需要理解"可执行性"的含义，这对 LLM 来说是挑战
> 建议先实施 G1-G3，G4 可以后续迭代。

---

## Q4: 管线的可观测性如何保证？

### CI/CD 中的可观测性三支柱

| 支柱 | CI/CD 含义 | DeepFlow 含义 |
|:---|:---|:---|
| **Logging** | 构建日志、测试输出 | 每个阶段的执行记录 |
| **Tracing** | 构建耗时、阶段依赖图 | 方案从需求到打包的全链路追踪 |
| **Metrics** | 构建成功率、测试覆盖率 | 方案质量指标、需求覆盖率 |

### 对 DeepFlow 的建议

**当前问题**：如果 Ship Pro 产出质量差（如 WP 拆分不合理、工时估算离谱），如何定位问题？

**建议的可观测性方案**：

1. **结构化日志（Logging）**：
   ```
   blackboard/.logs/
   ├── solution_pro.log       # Solution Pro 执行日志
   ├── ship_pro.log           # Ship Pro 解析日志
   └── quality_gates.log      # 质量门禁检查结果
   ```
   - 每个阶段记录：输入文件 hash、处理时间、输出文件 hash、质量门禁通过/失败
   - 这相当于 CI/CD 中的"构建日志"

2. **链路追踪（Tracing）**：
   - 为每个方案生成一个 `trace_id`（可以是 execution_plan 中的 topic hash）
   - 所有 artifact 都带上 `trace_id`，可以追踪"这个 WP 是从哪个需求来的"
   - 这相当于 CI/CD 中的"构建溯源"

3. **质量指标（Metrics）**：
   | 指标 | 含义 | 告警阈值 |
   |:---|:---|:---|
   | `req_coverage_rate` | 需求覆盖率 | < 90% |
   | `wp_ac_completeness` | WP 的 AC 完整率 | < 100% |
   | `wp_dependency_cycles` | 依赖环数量 | > 0 |
   | `ship_pro_parse_confidence` | Ship Pro 解析置信度 | < 0.7 |
   | `gate_failure_count` | 质量门禁失败次数 | > 0 |

4. **故障定位流程**：
   ```
   Ship Pro 产出质量差
   ↓
   检查 quality_gates.log — 哪个门禁失败了？
   ↓
   如果 G2 失败 → final_result.json 格式问题 → 查 Solution Pro 日志
   如果 G3 失败 → Ship Pro 解析问题 → 查 Ship Pro 日志
   如果 G4 失败 → 方案本身不可执行 → 查 Solution Pro 设计决策
   ```

### 实施信心评分：8/10

> 可观测性的设计是成熟的，CI/CD 领域有大量最佳实践。DeepFlow 的实现相对简单——主要是日志 + 质量门禁检查结果。
> 关键是要**先定义好日志格式**，不要事后补。

---

## Q5: 从确定性编译器切换到 LLM 引导编译器，管线的可重复性如何保证？

### CI/CD 中的可重复性原则

CI/CD 的核心原则之一是**可重复构建（Reproducible Builds）**：给定相同的输入，应该得到相同的输出。

LLM 的引入打破了这个原则——相同的输入，LLM 可能给出不同的输出。

### 对 DeepFlow 的建议

**问题**：Ship Pro 用 LLM 解析 `final_result.json`，每次运行可能得到不同的 `ship_package.json`。这如何保证质量？

**建议的应对策略**：

1. **种子固定（Seed Fixing）**：
   - 如果 LLM 支持 seed 参数，固定 seed 以获得可重复输出
   - 这是最简单的方案，但不是所有 LLM 都支持

2. **输出校验（Output Validation）**：
   - 不要求 LLM 输出完全相同，但要求输出**通过相同的校验**
   - 即：无论 LLM 怎么解析，`ship_package.json` 必须通过 G3 门禁（WP 完整性检查）
   - 这相当于 CI/CD 中的"构建产物必须符合规范"

3. **多次运行取最优（N-of-M）**：
   - 运行 Ship Pro 3 次，取"质量指标"最好的那次
   - 质量指标可以是：AC 覆盖率、依赖关系合理性、工时估算一致性
   - 这相当于 CI/CD 中的"多次构建取最稳定的"

4. **人类审查（Human-in-the-Loop）**：
   - 对于关键项目，Ship Pro 产出后由人类审查
   - 审查通过后才交给 Super Loop
   - 这相当于 CI/CD 中的"生产部署需要人工审批"

**推荐方案**：**输出校验 + 人类审查**（方案 2 + 4）
- 输出校验是自动化的，可以保证基本质量
- 人类审查是可选的，用于高风险项目

### 实施信心评分：6/10

> LLM 引入的不确定性是真实的风险。输出校验可以缓解，但不能完全消除。
> 建议先实施"输出校验"，观察一段时间后再决定是否需要"多次运行取最优"。

---

## 盲点与风险

### 1. 管线的"回滚"能力

CI/CD 中，如果部署失败，可以回滚到上一个版本。DeepFlow 中，如果 Super Loop 执行失败，如何回滚？

**建议**：保留 `ship_package.json` 的版本历史，支持"重新打包"（用相同的输入重新运行 Ship Pro）。

### 2. 管线的"增量构建"能力

CI/CD 中，如果只改了一个文件，不需要重新构建整个项目。DeepFlow 中，如果只改了一个需求，是否需要重新运行整个 Solution Pro？

**建议**：当前不需要考虑增量构建（DeepFlow 的运行时间主要在 LLM 调用，不在计算）。但如果未来运行时间成为瓶颈，可以考虑"需求级别的增量更新"。

### 3. 管线的"并行执行"能力

CI/CD 中，独立的构建任务可以并行执行。DeepFlow 中，Solution Pro 的 10 个阶段是串行的。

**建议**：当前串行是合理的（每个阶段依赖前一个阶段的输出）。但如果未来需要加速，可以考虑"阶段内的并行"（如多个需求同时分析）。

---

## 总结与建议

| 维度 | 建议 | 信心评分 |
|:---|:---|:---|
| Ship Pro 输入 artifact | 读 final_result + RTM + execution_plan（3 个文件） | 8/10 |
| Artifact 管理 | 区分对外/内部 artifact，对外永久保留，内部可丢弃 | 9/10 |
| 质量门禁 | 4 个门禁（G1-G4），替代 Blueprint Freezing | 7/10 |
| 可观测性 | 结构化日志 + 链路追踪 + 质量指标 | 8/10 |
| 可重复性 | 输出校验 + 可选人类审查 | 6/10 |

**总体建议**：

1. ✅ 修正方案的 artifact 设计是合理的，符合 CI/CD 最佳实践
2. ✅ 砍掉 Blueprint Freezing 是正确的，但需要用 G1（方案完整性检查）替代
3. ⚠️ LLM 引入的不确定性需要"输出校验"来缓解
4. ⚠️ 可观测性需要"先设计后实施"，不要事后补日志

**优先级排序**：
1. **P0**: 实施 G1-G3 质量门禁（替代 Blueprint Freezing）
2. **P0**: 确定 Ship Pro 的输入 artifact（3 个文件）
3. **P1**: 实施结构化日志
4. **P2**: 实施链路追踪
5. **P3**: 考虑增量构建/并行执行

---

*报告完成。DevOps 视角的核心信息：DeepFlow 管线需要像 CI/CD 一样有明确的质量门禁和 artifact 管理。砍掉 Blueprint Freezing 是对的，但必须有替代方案（G1 质量门禁）。*
