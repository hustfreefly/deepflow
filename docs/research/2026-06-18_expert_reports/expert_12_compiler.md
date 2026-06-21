# 专家 12：编译器设计师报告

> **视角**: 编译器前端/后端/中间表示（IR）设计
> **日期**: 2026-06-18
> **类比框架**: DeepFlow ≈ 编译器架构（Solution Pro=前端, Ship Pro=编译器, Super Loop=VM）

---

## 一、核心类比映射

| DeepFlow 组件 | 编译器对应 | 说明 |
|:---|:---|:---|
| Solution Pro | **编译器前端（Frontend）** | 词法/语法/语义分析，输出 AST/IR |
| final_result.json | **源代码（Source Code）** | 存在 5 种"方言"（dialect） |
| `_ship_pro_hints` | **编译指示（Pragmas）** | 类似 `#pragma` 或 `__attribute__`，提供导航提示 |
| Ship Pro | **编译器中端+后端（Middle+Backend）** | IR 优化 + 目标代码生成 |
| ship_package.json | **目标代码（Object Code）** | 可执行的"机器码"格式 |
| Super Loop | **虚拟机（VM）** | 类似 JVM/BEAM，执行目标代码 |
| frozen_blueprint | **已编译二进制（Binary）** | 有损压缩，类似 stripped binary |

---

## 二、编译器理论视角分析

### 2.1 中间表示（IR）的必要性

**LLVM 的核心教训**：IR 是编译器的"灵魂"。它解耦前端和后端，使得：
- M 种源语言 × N 种目标架构 = M×N 问题 → M+N 组件
- 优化在 IR 层进行，前端和后端独立演进

**DeepFlow 现状**：
- "源代码"有 5 种方言（final_result 的 5 种结构）
- 没有正式的 IR —— Ship Pro 直接从"方言源代码"生成"目标代码"
- 这相当于**没有 IR 的编译器**（类似早期的 C-to-Machine-Code 单阶段编译器）

**是否需要正式 IR？**

| 选项 | 优点 | 缺点 |
|:---|:---|:---|
| **A. 不引入 IR** | 简单，当前方案可行 | 5 种前端逻辑散落在 Ship Pro 中，维护成本高 |
| **B. 引入轻量 IR** | 解耦前端解析和后端生成，便于扩展 | 增加一层抽象，需要定义 IR schema |
| **C. 引入完整 IR（类似 LLVM IR）** | 最大灵活性，支持多目标输出 | 过度工程，DeepFlow 只有 1 种"目标架构" |

**建议：选项 B — 轻量 IR**

定义 `SolutionIR` 作为中间表示：

```typescript
interface SolutionIR {
  // 语义层（从任意方言提取）
  components: Component[];        // 架构组件
  dataFlows: DataFlow[];          // 数据流
  techStack: TechStack[];         // 技术选型
  
  // 需求层（从 RTM 提取）
  requirements: Requirement[];    // 需求项
  acceptanceCriteria: AC[];       // 验收标准
  
  // 元数据层（从 execution_plan 提取）
  metadata: ProjectMetadata;      // 项目约束/利益相关者
  
  // 设计决策层（可选，从 living_blueprint 提取）
  designDecisions?: {
    tradeoffs: string[];
    rejectedAlternatives: string[];
  };
}
```

**实施信心：8/10**
- 信心高的原因：IR 是编译器设计的成熟模式，收益明确
- 扣 2 分原因：DeepFlow 只有 1 种"目标架构"（Super Loop），IR 的收益不如多目标场景明显

---

### 2.2 `_ship_pro_hints` 是符号表吗？

**编译器中的符号表**：
- 在语义分析阶段构建
- 存储标识符的类型、作用域、内存地址等
- 用于类型检查、作用域解析、函数重载决议

**`_ship_pro_hints` 的本质**：
- 它是**编译指示（Pragmas）**，不是符号表
- Pragmas 是源代码中的"提示"，告诉编译器如何处理，但不改变语义
- 类似 `#pragma once`、`__attribute__((packed))`

**符号表应该在语义分析阶段构建**：

```
源代码（final_result + RTM + execution_plan）
    ↓
[词法/语法分析] → 识别结构
    ↓
[语义分析] → 构建符号表（SolutionIR）
    ↓
[代码生成] → 使用符号表生成 ship_package.json
```

**建议**：
1. `_ship_pro_hints` 保持为 Pragmas（导航提示）
2. 在 Ship Pro 的"语义分析"阶段构建真正的符号表（SolutionIR）
3. 符号表包含：组件列表、依赖关系、技术约束、需求映射

**实施信心：9/10**
- 信心高：Pragmas vs 符号表的区分是编译器设计的基础概念
- 实现简单：hints 作为可选输入，IR 作为必选中间产物

---

### 2.3 多方言前端处理策略

**5 种 final_result 格式 = 5 种方言**

| 方言 | 特征 | 代表案例 |
|:---|:---|:---|
| Dialect-1 | `architecture.core_components` | 跨境算力中转站 |
| Dialect-2 | `final_solution.detailed_solution.architecture.components` | 智能简历系统 |
| Dialect-3 | `architecture.components` | 智能客服系统 |
| Dialect-4 | `architecture`（16 个技术组件字段） | 电商订单系统 |
| Dialect-5 | 类似 Dialect-2 | Serenity Skills |

**编译器处理多方言的三种策略**：

| 策略 | 实现 | 适用场景 |
|:---|:---|:---|
| **A. 多方言前端** | 每种方言一个 Parser，输出统一 IR | 方言差异大、语法复杂 |
| **B. 统一方言** | 强制标准化源代码格式 | 可控源代码生成 |
| **C. 模糊解析器** | 用 LLM 做"语义解析"，容忍格式差异 | 方言差异在"语义"层而非"语法"层 |

**DeepFlow 的特殊性**：
- 这 5 种"方言"的差异是**字段命名/嵌套结构**，不是语法差异
- 所有方言表达的是**同一语义**（架构组件、技术栈、数据流）
- 这更像"同一语言的不同编码格式"，而非"不同语言"

**建议：策略 C — LLM 模糊解析 + 确定性校验**

```
final_result.json（任意方言）
    ↓
[LLM 前端] → 提取语义（组件/数据流/技术栈）
    ↓
[确定性校验] → 检查 IR 完整性（必填字段、类型约束）
    ↓
SolutionIR（统一中间表示）
```

**为什么不用策略 A（多方言前端）？**
- 方言数量可能增长（Solution Pro 升级后可能产生新格式）
- 维护 5+ 个 Parser 的成本高于维护 1 个 LLM Prompt

**为什么不用策略 B（统一方言）？**
- Solution Pro 是 LLM，输出格式不完全可控
- 强制格式会增加 Solution Pro 的 prompt 复杂度

**实施信心：8/10**
- 信心高：LLM 做"语义解析"是当前 LLM-native 应用的标准模式
- 扣 2 分：需要设计完善的校验层，防止 LLM 幻觉导致 IR 错误

---

### 2.4 从确定性编译器到 LLM 引导编译器

**编译器理论中的对应**：

| 类型 | 特征 | DeepFlow 对应 |
|:---|:---|:---|
| **静态编译器（AOT）** | 确定性、可预测、离线 | 当前 1048 行 Python Ship Pro |
| **解释器** | 逐行执行、灵活、慢 | 不完全对应 |
| **JIT 编译器** | 运行时编译、混合确定性/动态 | LLM 引导的 Ship Pro |
| **Transpiler** | 源到源转换 | Ship Pro 本质是 Transpiler |

**LLM 引导编译器 = JIT + Transpiler 混合体**

```
传统 Transpiler:
  Source A → [Parser] → AST → [Generator] → Source B
  （确定性，可测试）

LLM-guided Transpiler:
  Source A → [LLM Parser] → IR → [Deterministic Generator] → Source B
  （模糊解析 + 确定性组装）
```

**关键洞察**：
- LLM 替代的是**前端解析**（因为源代码格式不统一）
- **后端生成**应该保持确定性（ship_package.json 格式固定）
- 这是**混合架构**，不是纯 LLM 或纯确定性

**代码量变化预估**：

| 组件 | 当前（确定性） | 修正后（LLM 引导） |
|:---|:---|:---|
| 前端解析 | ~200 行（多格式适配） | ~100 行 Prompt + ~50 行校验 |
| IR 构建 | 隐含在解析中 | ~100 行 Schema 定义 |
| 后端生成 | ~700 行 | ~400 行（更简单，因为 IR 统一） |
| 测试/校验 | ~150 行 | ~200 行（需要 LLM 输出校验） |
| **总计** | **~1050 行** | **~850 行 + Prompt** |

**风险**：
- 代码量减少，但**测试复杂度增加**（LLM 输出不确定性）
- 需要设计"校验层"确保 LLM 输出的 IR 符合 schema

**实施信心：7/10**
- 信心中等：架构方向正确，但 LLM 输出的不确定性增加测试难度
- 需要投入更多精力在"校验层"而非"生成层"

---

## 三、Q1-Q5 明确建议

### Q1: Ship Pro 用 LLM 还是确定性编译器？

**建议：混合架构 — LLM 前端 + 确定性后端**

```
┌─────────────────────────────────────────────────────────────┐
│                      Ship Pro 架构                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [LLM 前端]                                                 │
│    - 输入: final_result + RTM + execution_plan              │
│    - 任务: 提取语义，输出 SolutionIR                        │
│    - 实现: Prompt Engineering + JSON Mode                   │
│                                                             │
│  [确定性校验层]                                              │
│    - 检查 SolutionIR schema 合规性                          │
│    - 必填字段验证（components, requirements）               │
│    - 类型检查（hours: number, dependencies: string[]）      │
│    - 失败时：重试或降级到人工                               │
│                                                             │
│  [确定性后端]                                                │
│    - 输入: 校验通过的 SolutionIR                            │
│    - 任务: 拆 WP、估算工时、生成 AC、组装 ship_package      │
│    - 实现: Python 确定性逻辑（可测试）                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**理由**：
1. LLM 处理"格式不统一"问题（前端模糊性）
2. 确定性逻辑处理"拆分/估算/组装"（后端确定性）
3. 校验层是安全网，防止 LLM 幻觉污染下游

**实施信心：8/10**

---

### Q2: Ship Pro 应该读 3 个文件还是更多？

**建议：3 个核心文件 + 1 个可选文件**

| 文件 | 优先级 | 内容 |
|:---|:---|:---|
| `final_result.json` | **必须** | 架构组件、技术栈、数据流 |
| `requirements_traceability_matrix.json` | **必须** | 需求覆盖、验收证据 |
| `execution_plan.json` | **必须** | 项目元数据（约束/利益相关者） |
| `living_blueprint.json` | **可选** | 设计决策（tradeoffs, rejected alternatives） |

**理由**：
1. 3 个核心文件包含 Ship Pro 需要的**全部必要信息**
2. `living_blueprint` 的 `design_decisions` 对"理解设计意图"有价值，但：
   - 结构不稳定（需要 LLM 解析）
   - 信息冗余（部分已在 final_result 中）
3. 建议：先读 3 个核心文件，如果 LLM 判断需要"设计背景"，再读 living_blueprint

**实施信心：9/10**

---

### Q3: `_ship_pro_hints` 约定是否可行？

**建议：可行，但保持最小化**

**设计原则**：
1. **可选**：Solution Pro 不输出 hints 时，Ship Pro 仍能工作（降级到全量解析）
2. **导航性**：hints 只指向位置，不包含语义（类似索引，不是内容）
3. **向后兼容**：hints 格式变化不应破坏 Ship Pro

**推荐格式**：

```json
{
  "_ship_pro_hints": {
    "architecture_location": "final_solution.detailed_solution.architecture.components",
    "tech_stack_location": "final_solution.detailed_solution.tech_stack",
    "implementation_plan_location": "implementation_plan",
    "req_coverage_location": "requirements_traceability_matrix.json"
  }
}
```

**风险与缓解**：
| 风险 | 缓解措施 |
|:---|:---|
| 增加 Solution Pro 复杂度 | hints 是"最佳努力"输出，不是强制 |
| hints 格式变化 | 定义 schema，Ship Pro 做兼容解析 |
| 过度耦合 | hints 只包含"位置"，不包含"内容" |

**实施信心：8/10**

---

### Q4: 砍掉 blueprint freezing 后，格式稳定性如何保证？

**建议：ship_package.json 的 JSON Schema 是新的"稳定契约"**

**类比**：
- frozen_blueprint = 旧的"二进制格式"（已废弃）
- ship_package.json = 新的"目标代码格式"
- JSON Schema = 新的"ABI 规范"

**实施步骤**：
1. 定义 `ship_package.schema.json`（严格类型定义）
2. Ship Pro 输出必须通过 schema 校验
3. Super Loop 只接受 schema-compliant 的 ship_package
4. Schema 版本化（v1.0, v1.1...），遵循语义化版本

**Schema 核心定义**：

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["work_packages", "metadata"],
  "properties": {
    "work_packages": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "title", "phase", "acceptance_criteria"],
        "properties": {
          "id": {"type": "string", "pattern": "^WP-\\d{3}$"},
          "title": {"type": "string", "minLength": 10},
          "phase": {"type": "integer", "minimum": 1},
          "estimated_hours": {"type": "number", "minimum": 1},
          "dependencies": {"type": "array", "items": {"type": "string"}},
          "acceptance_criteria": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["id", "criterion", "verification"]
            }
          }
        }
      }
    }
  }
}
```

**实施信心：9/10**
- JSON Schema 是成熟的格式稳定性方案
- 比 frozen_blueprint 更可靠（机器可验证）

---

### Q5: 从确定性到 LLM 引导，代码量和维护成本变化？

**代码量对比**：

| 维度 | 当前（确定性） | 修正后（LLM 引导） | 变化 |
|:---|:---|:---|:---|
| 核心代码 | ~1050 行 Python | ~650 行 Python + ~200 行 Prompt | -20% 代码 |
| 测试代码 | ~150 行 | ~300 行 | +100% 测试 |
| Schema 定义 | 无 | ~100 行 JSON Schema | 新增 |
| **总维护量** | ~1200 行 | ~1250 行 | +4% |

**维护成本对比**：

| 维度 | 当前 | 修正后 | 说明 |
|:---|:---|:---|:---|
| 格式适配 | 高（硬编码多格式） | 低（LLM 自适应） | LLM 处理格式变化 |
| 测试复杂度 | 低（确定性） | 高（LLM 输出不确定） | 需要模糊测试/快照测试 |
| 调试难度 | 低（可追踪） | 中（LLM 黑盒） | 需要 LLM 输出日志 |
| 扩展成本 | 高（改代码） | 低（改 Prompt） | Prompt 工程迭代快 |

**关键洞察**：
- 代码量变化不大（-20% + 测试增加）
- **维护成本结构变化**：从"代码维护"转向"Prompt 维护 + 测试维护"
- 长期收益：格式适配成本大幅降低（Solution Pro 升级不需要改 Ship Pro）

**实施信心：7/10**
- 信心中等：LLM 输出的不确定性增加测试/调试成本
- 建议：先在小范围案例验证，再全面切换

---

## 四、盲点与风险

### 4.1 盲点：LLM 前端的"幻觉"风险

**问题**：LLM 可能"幻觉"出不存在的组件或依赖关系

**缓解**：
1. **交叉验证**：LLM 提取的组件必须在 final_result 中有原文依据
2. **引用追踪**：要求 LLM 输出每个提取项的"原文引用"
3. **置信度评分**：LLM 对每个提取项给出置信度，低于阈值时人工审核

### 4.2 风险：Solution Pro 输出格式的"长尾分布"

**问题**：目前发现 5 种格式，但未来可能出现第 6、7 种

**缓解**：
1. LLM 前端天然支持新格式（无需改代码）
2. 但需要监控 IR 校验失败率，及时发现"异常格式"

### 4.3 风险：ship_package.json 的"语义空洞"

**问题**：JSON Schema 只能验证"结构"，不能验证"语义合理性"

**例子**：
- Schema 能通过：`estimated_hours: 1`（1 小时完成一个 WP）
- 但语义不合理：一个包含 5 个组件的 WP 不可能 1 小时完成

**缓解**：
1. 在 Schema 中添加 `minimum`/`maximum` 约束
2. 添加"合理性检查"规则（如：hours > components.count * 2）
3. 或者接受 LLM 估算的不精确性，下游 Super Loop 做二次验证

---

## 五、替代方案（如果有更好的）

### 方案 X：完全确定性 + 格式标准化

**思路**：
1. 强制 Solution Pro 输出统一格式（修改 summarizer prompt）
2. Ship Pro 保持纯确定性编译器

**优点**：
- 可测试性强
- 无 LLM 幻觉风险

**缺点**：
- Solution Pro prompt 复杂度增加
- 新场景可能需要新格式，导致 prompt 频繁修改

**对比结论**：
- 当前阶段（快速迭代）：LLM 引导更灵活
- 成熟阶段（格式稳定后）：可以考虑切回确定性

---

## 六、总结与建议

### 核心建议

| 问题 | 建议 | 信心 |
|:---|:---|:---|
| 是否需要 IR？ | 是，轻量 SolutionIR | 8/10 |
| `_ship_pro_hints` 定位 | Pragmas（导航提示），不是符号表 | 9/10 |
| 多方言处理 | LLM 模糊前端 + 确定性校验 | 8/10 |
| 格式稳定性 | JSON Schema 作为新契约 | 9/10 |
| LLM vs 确定性 | 混合架构（LLM 前端 + 确定性后端） | 8/10 |

### 实施优先级

1. **P0（立即）**：定义 `ship_package.schema.json`
2. **P0（立即）**：设计 `SolutionIR` schema
3. **P1（短期）**：实现 LLM 前端 + 校验层
4. **P1（短期）**：实现 `_ship_pro_hints` 约定
5. **P2（中期）**：重构确定性后端，基于 SolutionIR

### 关键洞察

> **DeepFlow 不是传统的"源代码→机器码"编译器，而是"方案→执行计划"的 Transpiler。**
>
> 传统编译器的挑战是"优化"（如何生成更快的代码）。
> DeepFlow 的挑战是"理解"（如何从非结构化文本提取结构化语义）。
>
> LLM 在"理解"上有天然优势，这正是 LLM 引导架构的合理性所在。
>
> **但"理解"的不确定性需要"校验"来兜底——这是编译器设计中"类型检查"的等价物。**

---

*报告完成。编译器设计师视角：架构方向正确，关键在于"校验层"的设计。*
