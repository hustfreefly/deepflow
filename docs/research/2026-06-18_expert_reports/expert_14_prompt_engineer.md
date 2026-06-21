# 专家 14：LLM Prompt Engineer — Agent 任务设计分析

> **日期**: 2026-06-18  
> **角色**: LLM Prompt 工程师 / Agent 任务设计专家  
> **评审对象**: Ship Pro 架构重设计 V2（从 final_result.json 到 ship_package.json）

---

## 一、核心判断：一个 Agent vs 多个 Agent？

### 结论：**拆分为 3 个 Agent，Pipeline 串联**

"从 final_result 到 ship_package" **不是**一个完整的"理解单元"。它包含三个认知性质完全不同的子任务：

| 子任务 | 认知类型 | 难度来源 | 输入规模 |
|--------|---------|---------|---------|
| **格式解析与架构提取** | 模式匹配 + 信息抽取 | 5 种不同 JSON 结构，字段名不统一 | ~33KB（3 文件） |
| **工作包拆解与规划** | 创造性推理 + 领域知识 | 需要理解架构逻辑、合理拆分、估算工时 | 中等（提取后的架构摘要） |
| **输出组装与校验** | 格式化合规 + 完整性检查 | 严格 JSON Schema、字段完整性、交叉引用 | 中等（规划结果） |

### 为什么不能是一个 Agent？

1. **上下文窗口效率**：3 个源文件 ~33KB，如果全部塞进一个 prompt 再加上输出格式要求、示例、规则，prompt 会膨胀到 50KB+。研究表明，长 prompt 中后部的指令遵从率显著下降（"lost in the middle" 问题）。
2. **格式多变性 vs 推理深度的矛盾**：处理 5 种输入格式需要大量 few-shot 示例和条件分支逻辑，而工作包拆解需要深度推理。混在一起会互相干扰——LLM 会在"理解格式"和"做规划"之间反复切换注意力。
3. **质量保证难度**：单一 Agent 的输出质量高度依赖 prompt 的完整性。拆分后，每个 Agent 的 prompt 更短、更聚焦，指令遵从率更高。
4. **可调试性**：Pipeline 中每个节点的输出可独立检查，出问题时能快速定位是"解析错了"还是"规划错了"。

### 为什么不是更多 Agent（4-5 个）？

1. **Agent 间传递有信息损耗**：每增加一个 Agent，就多一次序列化/反序列化，信息必然损失。
2. **协调成本**：更多 Agent = 更多 handoff = 更多出错点。研究表明，多 Agent 系统的有效性高度依赖协调结构，而非 Agent 数量。
3. **"理解单元"边界**：工作包拆解和工时估算/依赖排序是强耦合的——你不能在不了解 WP 内容的情况下估算工时。它们必须在一个 Agent 内完成。

---

## 二、推荐的 Agent 拆分方案

### Pipeline 架构：3 Agent 串联

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Agent 1:       │     │  Agent 2:       │     │  Agent 3:       │
│  ARCHITECTURE   │────▶│  WORKPLANNER    │────▶│  ASSEMBLER      │
│  PARSER         │     │                 │     │                 │
│                 │     │                 │     │                 │
│ 输入:           │     │ 输入:           │     │ 输入:           │
│ final_result    │     │ ArchDigest      │     │ WorkPlan        │
│ + RTM           │     │ + RTM摘要       │     │ + RTM摘要       │
│ + exec_plan     │     │                 │     │                 │
│                 │     │ 输出:           │     │ 输出:           │
│ 输出:           │     │ WorkPlan        │     │ ship_package    │
│ ArchDigest      │     │                 │     │ .json           │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
   [格式归一化]            [创造性规划]            [合规校验]
```

### Agent 1: Architecture Parser（架构解析器）

**职责**：从 5 种不同格式的 final_result 中提取统一的架构信息。

**为什么单独拆出来**：
- 这是整个 Pipeline 中**格式变异性最大**的环节
- 需要大量 few-shot 示例（每种格式至少 1 个）
- 它的输出是后续所有 Agent 的基础，必须高准确率
- 可以独立做回归测试（8 个案例 × 5 种格式）

**Prompt 设计原则**：
1. **角色定义**：你是一个 JSON 架构信息提取器。你的唯一任务是从不同格式的 JSON 中识别并提取架构组件、技术栈、依赖关系。
2. **格式识别先行**：先让 LLM 判断输入属于 5 种格式中的哪一种（通过要求它输出 `format_type` 字段），再按对应路径提取。这比让它隐式处理格式差异更可靠。
3. **显式字段映射**：对每种格式，给出明确的字段路径。例如："如果存在 `architecture.core_components`，提取该数组；如果存在 `final_solution.detailed_solution.architecture.components`，提取该数组。"
4. **输出严格约束**：使用 JSON Schema 定义 `ArchDigest` 的输出格式，启用 structured output / function calling 模式。
5. **不确定性标记**：对于无法确定归属的字段，要求 Agent 输出 `confidence: low` 而不是猜测。

**输入**：`final_result.json` + `requirements_traceability_matrix.json` + `execution_plan.json`（原始 3 文件）

**输出**：`ArchDigest`（标准化架构摘要）

```json
{
  "format_type": "core_components | detailed_solution | architecture_components | tech_components | mixed",
  "confidence": "high | medium | low",
  "project_meta": {
    "topic": "...",
    "constraints": ["..."],
    "stakeholders": ["..."]
  },
  "components": [
    {
      "name": "API Gateway",
      "description": "...",
      "tech_stack": ["Node.js", "Express"],
      "role": "backend",
      "key_details": "..."
    }
  ],
  "tech_stack_summary": ["Node.js", "PostgreSQL", "Redis", "Docker"],
  "existing_phases": [
    { "name": "Phase 1", "tasks": ["..."] }
  ],
  "requirements_coverage": {
    "covered": ["REQ-001", "REQ-002"],
    "total_count": 15
  },
  "design_decisions": [
    { "decision": "...", "rationale": "...", "alternatives_rejected": ["..."] }
  ],
  "integration_hints": ["..."]
}
```

---

### Agent 2: WorkPlanner（工作规划器）

**职责**：从标准化架构摘要中拆解工作包（WP），生成验收标准（AC），估算工时，排列依赖。

**为什么单独拆出来**：
- 这是**认知负荷最重**的环节，需要创造性推理
- 需要与格式解析完全不同的 prompt 风格（发散性 vs 收敛性）
- 是整个 Pipeline 中**最可能出错**的环节，需要最精细的 prompt 设计
- 独立拆分后可以针对规划质量做独立评估

**Prompt 设计原则**：
1. **角色定义**：你是一位资深技术项目经理，擅长将技术方案拆解为可执行的工作包。你遵循 SMART 原则（Specific, Measurable, Achievable, Relevant, Time-bound）。
2. **Chain-of-Thought 强制**：要求 Agent 在输出 JSON 前先输出一段推理过程（`<thinking>` 标签），包括：
   - 架构中有几个独立可交付的模块？
   - 哪些模块之间有强依赖？
   - 每个模块的复杂度如何？
   - 如何平衡工作包的粒度（太粗不可执行，太细增加管理开销）？
3. **WP 拆分规则**（显式编码在 prompt 中）：
   - 每个 WP 应该是一个**独立的、可测试的**交付单元
   - WP 粒度目标：8-80 小时（低于 8 小时太细，高于 80 小时太粗）
   - 每个 WP 必须有至少 1 个 P0 级别的 AC
   - Phase 划分遵循：基础设施 → 核心功能 → 集成测试 → 部署上线
4. **工时估算锚定**：在 prompt 中提供锚定参考：
   - 简单 CRUD 模块：8-16h
   - 中等复杂度服务（含业务逻辑）：24-40h
   - 复杂集成（多系统对接）：40-80h
   - 基础设施/DevOps：16-40h
5. **依赖关系约束**：要求 Agent 输出无环依赖图，并标注关键路径。
6. **输出格式**：使用 JSON Schema 约束 `WorkPlan` 输出。

**输入**：`ArchDigest` + `RTM 摘要`（不需要原始 3 文件）

**输出**：`WorkPlan`（工作包规划）

```json
{
  "thinking": "推理过程...",
  "work_packages": [
    {
      "id": "WP-001",
      "title": "...",
      "description": "...",
      "phase": 1,
      "component_mapping": ["API Gateway"],
      "estimated_hours": 40,
      "complexity": "high | medium | low",
      "dependencies": [],
      "acceptance_criteria": [
        {
          "id": "AC-001",
          "criterion": "...",
          "verification": "...",
          "priority": "P0 | P1 | P2"
        }
      ],
      "technical_constraints": ["..."],
      "deliverables": ["src/..."],
      "integration_checkpoints": [
        { "after": "WP-003", "check": "..." }
      ]
    }
  ],
  "dependency_graph": {
    "WP-002": ["WP-001"],
    "WP-003": ["WP-001"]
  },
  "critical_path": ["WP-001", "WP-003", "WP-005"],
  "total_estimated_hours": 200,
  "phase_summary": {
    "1": { "wps": ["WP-001", "WP-002"], "hours": 80 },
    "2": { "wps": ["WP-003", "WP-004"], "hours": 80 },
    "3": { "wps": ["WP-005"], "hours": 40 }
  }
}
```

---

### Agent 3: Assembler（组装器）

**职责**：将 WorkPlan 转换为最终的 `ship_package.json`，确保格式合规、字段完整、交叉引用正确。

**为什么单独拆出来**：
- 这是一个**收敛性、规则驱动**的任务，与 Planner 的发散性推理完全不同
- 可以做严格的 Schema 校验和自动修正
- 独立拆分后，如果输出格式需要变更，只需修改这个 Agent 的 prompt

**Prompt 设计原则**：
1. **角色定义**：你是一个 JSON 格式化和质量保证器。你的任务是确保工作包规划数据符合 ship_package.json 的 Schema 规范。
2. **Schema-first**：在 prompt 中嵌入完整的 `ship_package.json` JSON Schema，要求 Agent 逐字段对照填充。
3. **校验清单**：要求 Agent 在输出前逐项检查：
   - [ ] 每个 WP 的 id 唯一且格式为 WP-XXX
   - [ ] 每个 AC 的 id 唯一且格式为 AC-XXX
   - [ ] 所有 dependency 引用的 WP id 存在
   - [ ] 所有 integration_checkpoint 的 after 引用的 WP id 存在
   - [ ] estimated_hours 为合理正整数
   - [ ] phase 编号从 1 开始，连续递增
   - [ ] 每个 WP 至少有 1 个 P0 级别的 AC
   - [ ] deliverables 非空
4. **不修改内容**：明确告知 Agent 不要修改 WP 的内容、顺序或估算，只做格式转换和校验。
5. **错误处理**：如果发现不一致，输出 `validation_errors` 数组而不是自行修复（让上游 Agent 修正）。

**输入**：`WorkPlan`（来自 Agent 2）

**输出**：`ship_package.json`（最终格式）

---

## 三、Agent 间数据传递格式建议

### 核心原则：**结构化 JSON，逐步浓缩**

```
原始文件（~33KB）→ ArchDigest（~3-5KB）→ WorkPlan（~5-10KB）→ ship_package.json（~5-10KB）
```

### 为什么不用自然语言？

| 维度 | 自然语言 | 结构化 JSON |
|------|---------|------------|
| 信息损耗 | 高（LLM 摘要会丢失细节） | 低（字段级精确传递） |
| 下游可解析性 | 差（需要再次 LLM 解析） | 好（直接 JSON Schema 校验） |
| 确定性 | 低（每次表述不同） | 高（固定 Schema） |
| Token 效率 | 中（自然语言冗长） | 高（键值对紧凑） |

### 为什么不用原始数据直传？

- 原始 final_result.json ~20KB+，其中大量信息对下游无用
- 未归一化的字段名会导致下游 Agent 也需要处理格式变异性
- 违背"每个 Agent 只接收它需要的信息"原则

### 传递格式设计原则

1. **ArchDigest 是归一化层**：将 5 种格式统一为 1 种中间表示，后续 Agent 不再需要处理格式差异
2. **WorkPlan 是语义层**：包含推理结果（thinking）和结构化规划，但不包含原始架构数据
3. **每个 Agent 只看到它需要的**：Assembler 不需要看原始 final_result，只需要看 WorkPlan

### 关于 RTM 的传递

RTM（requirements_traceability_matrix.json）在 Agent 1 和 Agent 2 中都需要：
- Agent 1：提取 `covered_req_ids` 和需求描述
- Agent 2：确保 WP 的 AC 覆盖关键需求

建议：Agent 1 在 ArchDigest 中包含一个 `requirements_coverage` 摘要字段，Agent 2 基于这个摘要工作，而不是直接读原始 RTM 文件。

---

## 四、质量保证机制（Prompt 设计角度）

### 4.1 输入端质量保证

| 机制 | 实现方式 | 作用 |
|------|---------|------|
| **格式识别** | Agent 1 先输出 `format_type` | 确认输入格式被正确识别 |
| **置信度标记** | Agent 1 输出 `confidence` 字段 | 低置信度时触发人工审核 |
| **Schema 校验输入** | 对 ArchDigest 做 JSON Schema 校验 | 确保 Agent 1 输出格式正确 |

### 4.2 过程质量保证

| 机制 | 实现方式 | 作用 |
|------|---------|------|
| **Chain-of-Thought** | Agent 2 输出 `<thinking>` 块 | 强制推理过程可见，便于调试 |
| **Few-shot 示例** | 每个 Agent 配 2-3 个示例 | 锚定输出质量和风格 |
| **角色约束** | 每个 Agent 有明确的角色边界 | 防止越界处理 |
| **否定指令** | 明确告知"不要做什么" | 防止常见错误（如 Assembler 不要修改内容） |

### 4.3 输出端质量保证

| 机制 | 实现方式 | 作用 |
|------|---------|------|
| **JSON Schema 强制** | 使用 structured output / function calling | 输出 100% 符合 Schema |
| **交叉引用校验** | Assembler 检查所有 ID 引用 | 防止悬空引用 |
| **完整性检查** | 每个 WP 至少有 1 个 P0 AC | 防止遗漏关键验收标准 |
| **回归测试** | 8 个案例自动化测试 | 检测 prompt 修改导致的退化 |

### 4.4 跨 Agent 一致性保证

**关键设计**：在 Agent 2 的 prompt 中嵌入 Agent 1 的输出 Schema 说明，让 Agent 2 知道 ArchDigest 的字段结构。同样，Agent 3 的 prompt 中嵌入 WorkPlan 的 Schema 说明。这样每个 Agent 都理解上游数据的含义，但只通过结构化 JSON 交互。

**不一致时的回退策略**：
- 如果 Agent 3 发现 WorkPlan 有校验错误 → 输出 `validation_errors`，不生成 ship_package
- 编排层收到 `validation_errors` → 将错误信息反馈给 Agent 2 重新生成（最多重试 2 次）
- 如果 Agent 1 的 `confidence` 为 `low` → 编排层标记需要人工审核

---

## 五、与前一轮方案的对比

### 前一轮方案（从上下文推断）

前一轮可能是一个单一 Agent 方案，直接读 3 个文件输出 ship_package.json。

### 对比分析

| 维度 | 单一 Agent | 3-Agent Pipeline（本方案） |
|------|-----------|--------------------------|
| **Prompt 复杂度** | 极高（需覆盖格式解析+规划+格式化） | 低（每个 Agent 职责单一） |
| **格式适应性** | 差（5 种格式的 few-shot 示例挤占推理空间） | 好（Agent 1 专注格式处理） |
| **推理质量** | 中（注意力被格式问题分散） | 高（Agent 2 全力做规划） |
| **输出稳定性** | 低（长 prompt 指令遵从率低） | 高（短 prompt + Schema 强制） |
| **可调试性** | 差（出错不知道哪个环节） | 好（每个节点输出可独立检查） |
| **可测试性** | 差（只能端到端测试） | 好（每个 Agent 可独立测试） |
| **Token 成本** | 低（1 次 LLM 调用） | 中（3 次调用，但每次 prompt 更短） |
| **延迟** | 低（串行 1 次） | 中（串行 3 次，但总 token 可能更少） |
| **维护成本** | 高（改一个方面可能影响其他） | 低（Agent 间松耦合） |
| **信息损耗** | 无（全在一个上下文） | 低（结构化中间格式保留关键信息） |

### 净收益评估

- **Token 成本增加**：约 2-3x（3 次调用 vs 1 次），但由于每个 prompt 更短更聚焦，实际增加约 1.5x
- **质量提升**：显著。格式解析准确率、WP 规划质量、输出合规性都可独立优化
- **维护性提升**：显著。修改输出格式只需改 Agent 3，添加新输入格式只需改 Agent 1

---

## 六、实施信心评分

### 评分：**7.5 / 10**

### 信心来源

1. ✅ **研究支持**：窄职责 Agent 优于宽职责 Agent 是有充分研究支持的
2. ✅ **模式成熟**：Pipeline 模式是 multi-agent 系统中最成熟、最可预测的模式
3. ✅ **格式变异性是真实痛点**：5 种输入格式确实需要专门的处理逻辑
4. ✅ **结构化中间格式**：JSON Schema 强制输出是解决一致性问题的成熟方案
5. ✅ **可测试性**：8 个案例提供了良好的回归测试基础

### 风险与不确定性

1. ⚠️ **ArchDigest 的信息损耗**（-0.5）：从 33KB 压缩到 3-5KB 可能丢失微妙信息。需要精心设计 ArchDigest Schema 以保留所有关键细节。
2. ⚠️ **Agent 2 的工时估算准确性**（-0.5）：LLM 的工时估算天然不准确。建议增加"估算校准"步骤——用已知项目的工时数据做 few-shot 校准。
3. ⚠️ **Pipeline 串行延迟**（-0.5）：3 次 LLM 调用的串行延迟可能达到 30-60s。对于交互式使用场景可能需要优化（如 Agent 1 和 Agent 3 用更快的模型）。
4. ⚠️ **`_ship_pro_hints` 约定的交互**（-0.5）：如果 Solution Pro 的 `_ship_pro_hints` 字段与实际数据不一致，Agent 1 会产生错误提取。需要在 Agent 1 的 prompt 中处理 hints 与实际数据不匹配的情况。
5. ⚠️ **design_decisions 的归属**（-0.5）：living_blueprint 中的 design_decisions 信息对 WP 规划有价值，但结构不稳定。当前方案将其放入 ArchDigest 的 `design_decisions` 字段，但提取可靠性存疑。

### 建议的后续步骤

1. **先实现 Agent 1 并用 8 个案例回归测试**——这是整个 Pipeline 的基础
2. **为 Agent 2 构建工时校准数据集**——收集类似项目的实际工时数据作为 few-shot 示例
3. **定义 ArchDigest 和 WorkPlan 的 JSON Schema**——在写 prompt 之前先确定 Schema
4. **考虑 Agent 2 的模型选择**——这是最需要推理能力的环节，建议使用最强可用模型

---

## 七、补充建议

### 7.1 关于 `_ship_pro_hints` 约定

从 prompt 工程角度，这是一个好主意但需要谨慎实现：

**建议做法**：
- `_ship_pro_hints` 作为 Agent 1 的**可选输入**，不是必需输入
- Agent 1 的 prompt 应包含："如果输入中包含 `_ship_pro_hints`，优先使用它定位数据；如果 hints 指向的位置与实际数据不匹配，回退到自动检测模式"
- 这样即使 hints 出错，Pipeline 仍能工作

### 7.2 关于 living_blueprint 的 design_decisions

当前方案建议不读 living_blueprint。从 prompt 工程角度：

**建议**：将 living_blueprint 作为 Agent 1 的**可选输入**。如果存在，提取 `design_decisions` 字段放入 ArchDigest；如果不存在或格式不可解析，不影响 Pipeline 运行。这是一个"有则更好，无也可行"的信息源。

### 7.3 关于模型选择

不同 Agent 对模型能力的要求不同：

| Agent | 推荐模型等级 | 理由 |
|-------|------------|------|
| Agent 1 (Parser) | 中等模型 | 模式匹配任务，不需要最强推理 |
| Agent 2 (Planner) | 最强模型 | 创造性推理，最需要智能的环节 |
| Agent 3 (Assembler) | 轻量模型 | 格式化任务，规则驱动 |

这样可以在成本和质量之间取得平衡。

---

*报告完成。以上分析基于 LLM prompt 工程最佳实践、multi-agent 系统设计原则、以及 DeepFlow 的具体场景约束。*
