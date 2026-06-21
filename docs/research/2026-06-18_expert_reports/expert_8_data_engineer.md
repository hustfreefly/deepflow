# 专家 8：数据工程师报告 — ETL 管道 + Schema 演化视角

> **日期**: 2026-06-18  
> **角色**: 资深数据工程师，专注 ETL/ELT 管道设计、Schema Evolution、Data Contract  
> **评估对象**: DeepFlow 架构重设计 V2 修正方案

---

## 一、行业最佳实践摘要

### 1.1 Schema Evolution 核心模式

| 模式 | 描述 | 适用场景 |
|------|------|---------|
| **Additive-Only Changes** | 只加新字段（optional + default），不删不改已有字段 | 最安全的演化策略 |
| **Schema Registry** | 集中管理 schema 版本，强制兼容性检查 | Kafka/Avro 生态 |
| **Transformation Layer** | 在管道内设映射/过滤/富化层，适配不同版本 | 多版本共存时 |
| **Self-Describing Formats** | Avro/Protobuf — schema 随数据走 | 跨系统传输 |

**兼容性黄金法则**：
- Backward compatible：新 schema 能读旧数据（消费者升级不影响）
- Forward compatible：旧 schema 能读新数据（生产者升级不影响）
- Full compatible = 两者兼得

### 1.2 Data Contract 模式

Data Contract = 生产者与消费者之间的**显式契约**：
- 技术规约：JSON Schema / Avro / Protobuf
- 版本管理：version number + deprecation notice + migration path
- 自动执行：CI/CD 集成 + schema validation + 自动化测试
- 质量约束：格式、值域、唯一性等

### 1.3 Adapter Pattern（适配器模式）

当上游格式不统一时：
- 为每种格式写一个 Adapter
- 所有 Adapter 输出统一的 Target Interface
- 下游只与 Target Interface 交互
- **好处**：解耦、可测试、新增源只需加 Adapter

### 1.4 Anti-Corruption Layer（防腐层）

ACL = "语义防火墙"：
- 保护核心系统不被外部系统的混乱模型"腐蚀"
- 翻译 + 验证 + 隔离
- 将外部语义漂移转化为内部统一模型

---

## 二、问题诊断：当前架构的数据工程本质

### 2.1 核心问题 = Schema-on-Read + 不稳定上游

```
Solution Pro (生产者)
  └─ final_result.json → 5 种不同结构（schema 不稳定）
  
Ship Pro (消费者/转换层)
  └─ ship_package.json → 稳定输出格式（目标 data contract）
  
Super Loop (最终消费者)
  └─ 只读 ship_package.json
```

**数据工程视角的诊断**：

1. **这是经典的"多源异构 → 统一输出"问题**
   - 5 种 final_result 结构 = 5 种"上游 schema 变体"
   - ship_package.json = 下游 data contract
   - Ship Pro = 转换层 / ACL

2. **但有一个根本区别**：传统 ETL 的上游格式是**已知且有限**的（CSV/XML/JSON 各有 parser），而这里上游格式是**LLM 生成的自然语言结构**，理论上变体数量是无限的。

3. **这不是 schema evolution（时间维度的版本演化），而是 schema variance（空间维度的结构差异）**。传统 schema evolution 处理的是"v1 → v2 → v3"，这里处理的是"案例 A 是结构 A，案例 B 是结构 B"。

### 2.2 为什么传统 Schema Registry 不适用

| 传统 ETL | DeepFlow 场景 |
|----------|-------------|
| 上游格式有限（3-5 种已知格式） | 上游格式理论无限（LLM 自由生成） |
| 格式变化可预测（版本升级） | 格式变化不可预测（每次 LLM 输出可能不同） |
| 可以用 JSON Schema 严格校验 | 无法预定义所有合法结构 |
| Adapter 可以硬编码 | Adapter 需要"理解"语义 |

**结论**：传统 data engineering 工具（Schema Registry、Avro、JSON Schema validation）在这里**不直接适用**，因为上游不是"有限种已知格式"，而是"LLM 自由生成的无限变体"。

---

## 三、对 Q1-Q5 的明确建议

### Q1: Ship Pro 用 LLM 还是确定性编译器？

**建议：LLM 引导编译器（修正方案的方向是对的），但必须加"输出校验层"。**

**数据工程类比**：
- LLM = Schema-on-Read 引擎（像 Spark SQL 读取半结构化数据）
- 确定性组装 = Target Interface 强制（像 ETL 的 Load 阶段写入目标 schema）

**具体架构**：

```
final_result.json (5种结构)
    │
    ▼
[LLM 解析层] ← Schema-on-Read（理解语义，提取组件/技术栈/依赖）
    │
    ▼
[normalized_intermediate.json] ← 标准化中间格式（关键！）
    │
    ▼
[确定性组装层] ← 从 normalized 格式 → ship_package.json
    │
    ▼
[输出校验层] ← JSON Schema 验证 ship_package.json 是否符合 data contract
    │
    ▼
ship_package.json (稳定输出)
```

**为什么需要 normalized_intermediate**：
1. **可调试**：LLM 解析结果可检查，不是黑盒端到端
2. **可回退**：如果 LLM 解析出错，可以重新解析 intermediate 而不重跑全流程
3. **可测试**：normalized_intermediate 有固定 schema，可以写自动化测试
4. **解耦**：上游格式变化只影响 LLM 解析层，不影响组装层

**实施信心：7/10**
- 方向正确，但 LLM 解析的可靠性需要大量 case 验证
- normalized_intermediate 的 schema 设计是关键，设计不好会变成另一个 frozen_blueprint

---

### Q2: Ship Pro 应该读 3 个文件还是更多？

**建议：读 3 个文件（final_result + RTM + execution_plan），不读 living_blueprint。**

**数据工程理由**：

| 文件 | 角色 | 是否读 | 理由 |
|------|------|:------:|------|
| final_result.json | 主数据源 | ✅ | 架构核心内容 |
| RTM.json | 需求+验收证据 | ✅ | 结构稳定，信息不可替代 |
| execution_plan.json | 元数据 | ✅ | 结构稳定，项目上下文 |
| living_blueprint.json | design_decisions | ❌ | 结构不稳定，ROI 不够 |

**关于 living_blueprint 的 design_decisions**：

从数据工程角度，"为什么这样设计"的信息应该通过**元数据**而非**额外数据源**获取。建议：

1. **短期**：不读 living_blueprint。design_decisions 对 Ship Pro 拆 WP 的价值有限（Ship Pro 关心"是什么"，不关心"为什么"）。
2. **长期**：如果确实需要 tradeoff 信息，让 Solution Pro 在 final_result 里加一个 `design_decisions_summary` 字段（additive change，backward compatible）。

**实施信心：8/10**
- 3 文件方案简洁，符合"最小输入"原则
- living_blueprint 结构不稳定，读它增加解析复杂度但收益有限

---

### Q3: `_ship_pro_hints` 约定是否可行？

**建议：可行，但应该升级为"导航元数据"而非"提示字段"。**

**数据工程类比**：

`_ship_pro_hints` 本质上是**数据目录（Data Catalog）的简化版**——告诉消费者"关键数据在哪里"。这在数据工程中是成熟模式：

```json
{
  "_ship_pro_hints": {
    "architecture_location": "final_solution.detailed_solution.architecture.components",
    "tech_stack_location": "architecture.core_components[*].technology",
    "implementation_plan_location": "implementation_plan",
    "requirements_location": "requirements.items",
    "confidence": 0.85
  }
}
```

**设计原则**：

1. **hints 是 JSON Path，不是自然语言**：确定性可解析，不需要 LLM 再解析一次
2. **hints 是 optional 的**：没有 hints 时 Ship Pro 用 LLM 自行探索（fallback）
3. **hints 有 confidence 分数**：Solution Pro 自评导航准确度，低于阈值时 Ship Pro 全量 LLM 解析
4. **hints 不保证正确**：Ship Pro 应该有验证逻辑（路径存在？内容合理？）

**风险分析**：

| 风险 | 缓解措施 |
|------|---------|
| Solution Pro 输出错误 hints | Ship Pro 验证路径存在性 + 内容类型检查 |
| hints 格式本身不稳定 | 定义 hints 的 JSON Schema，CI 校验 |
| hints 增加 Solution Pro 复杂度 | hints 生成逻辑简单（就是记录 JSON Path），不增加实质复杂度 |

**实施信心：8/10**
- 这是一个低成本的改进，ROI 很高
- 关键：hints 必须是机器可解析的（JSON Path），不能是自然语言描述

---

### Q4: 砍掉 blueprint freezing 后，下游格式稳定性如何保证？

**建议：用"输出端 Data Contract"替代"输入端 Schema Freezing"。**

**数据工程视角的核心洞察**：

> **Schema Freezing 是一种"输入端稳定性"策略——强制上游不变，下游就安全。**  
> **Data Contract 是一种"输出端稳定性"策略——不管上游怎么变，输出必须符合契约。**

修正方案的逻辑是：
- ❌ 不再冻结输入（final_result 格式自由演化）
- ✅ 但严格约束输出（ship_package.json 必须符合 JSON Schema）

**这是正确的方向**，因为：
1. 冻结输入 = 限制 Solution Pro 的表达力 = 信息损失（frozen_blueprint 的 32% 保真度就是证据）
2. 约束输出 = 保护 Super Loop = 执行稳定性

**具体实施**：

```
ship_package.json 的 Data Contract（JSON Schema）：

{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["work_packages", "metadata"],
  "properties": {
    "work_packages": {
      "type": "array",
      "items": {
        "required": ["id", "title", "phase", "acceptance_criteria"],
        "properties": {
          "id": {"type": "string", "pattern": "^WP-\\d{3}$"},
          "title": {"type": "string", "minLength": 5},
          "phase": {"type": "integer", "minimum": 1},
          "estimated_hours": {"type": "number", "minimum": 1},
          "dependencies": {"type": "array", "items": {"type": "string"}},
          "acceptance_criteria": {
            "type": "array",
            "minItems": 1,
            "items": {
              "required": ["id", "criterion", "verification"],
              ...
            }
          }
        }
      }
    }
  }
}
```

**校验时机**：
1. Ship Pro 生成后立即校验（生成时）
2. Super Loop 消费前校验（消费时）
3. 校验失败 → 拒绝 + 报错 + 不进入执行

**实施信心：9/10**
- 这是最成熟、最可靠的数据工程实践
- JSON Schema 是标准工具，实现成本极低
- 关键：schema 设计要覆盖所有必要字段，但不能过度约束（给 LLM 留出表达空间）

---

### Q5: 从确定性编译器切换到 LLM 引导编译器，代码量和维护成本变化？

**建议：代码量减少 60-70%，但测试成本增加 2-3 倍。**

**详细分析**：

| 维度 | 确定性编译器（当前 1048 行 Python） | LLM 引导编译器（修正后） |
|------|-------------------------------------|------------------------|
| **核心代码** | ~1000 行格式解析 + 映射逻辑 | ~300 行 LLM prompt + 输出组装 + schema 校验 |
| **维护触发** | 上游格式变化 → 改代码 | 上游格式变化 → LLM 自动适应（大部分情况） |
| **新增格式支持** | 写新 parser（天级） | 改 prompt / 加 hint（小时级） |
| **测试** | 单元测试（确定性，可重复） | 集成测试（LLM 输出非确定性，需要多次运行） |
| **调试** | 断点 + 日志（精确） | LLM 推理链 + intermediate 检查（模糊） |
| **失败模式** | 编译错误（明确） | 语义误解（隐蔽，需要校验层发现） |

**维护成本的长期趋势**：

```
确定性编译器：
  初始成本 ████████████████████ 高
  边际成本 ████ 低（格式变化才需要改）
  但：每次 Solution Pro 升级 → 可能破坏映射 → 维护成本阶梯式上升

LLM 引导编译器：
  初始成本 ████████████ 中（prompt 工程 + 校验层）
  边际成本 ██ 极低（格式变化 LLM 自动适应）
  但：LLM 升级/更换 → 需要重新验证所有 case → 维护成本偶发上升
```

**关键风险**：
1. **LLM 非确定性**：同样的 final_result，两次运行可能产出不同的 ship_package → 需要 golden case 测试
2. **LLM 幻觉**：可能"编造"不存在的组件或依赖 → 需要交叉验证（RTM ↔ ship_package）
3. **调试困难**：LLM 解析错误不像代码 bug 那样容易定位 → normalized_intermediate 是关键

**实施信心：6/10**
- 代码量确实减少，但"有效代码"（经过充分测试的代码）的开发周期可能更长
- 需要建立 golden case 库（至少 20+ 案例）才能有信心上线

---

## 四、盲点与风险

### 4.1 盲点 1：缺少 normalized_intermediate 格式定义

修正方案描述了"Ship Pro 读 final_result → 输出 ship_package"，但没有定义中间步骤。从数据工程角度，**缺少 normalized intermediate 是最大的架构风险**。

**建议**：定义 `parsed_architecture.json`：

```json
{
  "components": [
    {
      "name": "API网关",
      "type": "gateway",
      "technology": ["New API", "Docker"],
      "responsibilities": ["多供应商聚合", "智能路由"],
      "source_location": "architecture.core_components[0]",
      "confidence": 0.9
    }
  ],
  "dependencies": [...],
  "tech_stack": [...],
  "implementation_phases": [...],
  "_meta": {
    "parsed_from": "final_result.json",
    "parser": "llm",
    "hints_used": true,
    "parse_timestamp": "2026-06-18T..."
  }
}
```

### 4.2 盲点 2：没有考虑"格式漂移"的长期趋势

当前 5 种结构可能是 Solution Pro 不同版本/模型产生的。随着 Solution Pro 升级，格式会继续漂移。修正方案依赖 LLM 的适应能力来吸收漂移，但：

- **LLM 适应 ≠ 100% 可靠**：总有 edge case 解析失败
- **没有告警机制**：如果 Solution Pro 输出了一种全新结构，LLM 解析成功率下降，谁来发现？

**建议**：加一个"格式漂移监控"：
- 每次 Ship Pro 运行后，记录 `_meta.format_signature`（final_result 的 top-level key 集合）
- 如果 signature 与已知模式不匹配 → 告警
- 积累新 signature → 定期更新 hints 约定

### 4.3 盲点 3：ship_package.json 的 consumer 没有 voice

Data Contract 的核心是**生产者与消费者共同约定**。当前方案中：
- Solution Pro（生产者）有 input contract（final_result 自由格式）
- Ship Pro（转换层）有 output contract（ship_package.json schema）
- Super Loop（最终消费者）**没有参与 contract 定义**

**风险**：ship_package.json 的 schema 可能不符合 Super Loop 的实际需求，导致"符合 schema 但无法执行"。

**建议**：在 schema 设计时，让 Super Loop 的需求驱动字段定义，而不是 Ship Pro 单方面决定。

---

## 五、替代方案评估

### 5.1 方案 A：纯 LLM 端到端（不推荐）

```
final_result.json → LLM → ship_package.json
```

- 优点：最简单，代码量最少
- 缺点：不可调试、不可测试、不可回退
- **信心：3/10**

### 5.2 方案 B：LLM + normalized_intermediate + 确定性组装（推荐）

```
final_result.json → LLM → parsed_architecture.json → 确定性组装 → ship_package.json → schema 校验
```

- 优点：可调试、可测试、可回退、解耦
- 缺点：多一层中间格式
- **信心：8/10**

### 5.3 方案 C：多 Adapter + 规则引擎（不推荐）

```
final_result.json → 格式检测 → Adapter A/B/C/D/E → 统一格式 → 组装
```

- 优点：确定性，可测试
- 缺点：每次新格式都要写 Adapter（回到 frozen_blueprint 的老路）
- **信心：4/10**

### 5.4 方案 D：LLM + 投票机制（有趣但过度设计）

```
final_result.json → LLM_1 → parsed_1
                  → LLM_2 → parsed_2  → 投票 → 组装
                  → LLM_3 → parsed_3
```

- 优点：高可靠性
- 缺点：3x LLM 成本，延迟 3x，复杂度高
- **信心：5/10**（适合未来高可靠需求时考虑）

---

## 六、总结与建议

### 6.1 核心建议

| 优先级 | 建议 | 理由 |
|:------:|------|------|
| **P0** | 定义 normalized_intermediate 格式 | 解耦上下游，可调试可测试 |
| **P0** | 定义 ship_package.json 的 JSON Schema | Data Contract 是下游稳定性的保障 |
| **P1** | 实现 `_ship_pro_hints` 为 JSON Path 导航 | 低成本高 ROI，减少 LLM 探索空间 |
| **P1** | 建立 golden case 测试库（20+ 案例） | LLM 非确定性需要大量测试覆盖 |
| **P2** | 加格式漂移监控 | 长期可观测性 |
| **P2** | 让 Super Loop 参与 schema 设计 | 确保 output contract 满足 consumer 需求 |

### 6.2 对修正方案的总体评价

**方向正确，但缺少一层关键抽象。**

修正方案正确地识别了：
- ✅ 输入端不应该冻结（frozen_blueprint 必须死）
- ✅ LLM 是处理不稳定上游的合理选择（schema-on-read）
- ✅ 输出端需要严格约束（data contract）

但缺少：
- ❌ normalized_intermediate 格式（解耦层）
- ❌ 输出校验机制（schema validation）
- ❌ 格式漂移监控（长期可观测性）

**用数据工程的术语说**：修正方案设计了"从源到目标的管道"，但缺少"质量控制关卡"和"中间存储"。在传统 ETL 中，这相当于只有 Extract 和 Load，没有 Transform 阶段的分层设计。

### 6.3 实施信心总评

| 维度 | 信心 | 说明 |
|------|:----:|------|
| 整体方向 | **8/10** | LLM + data contract 的组合是对的 |
| 短期可行性（3 个案例） | **7/10** | 需要 prompt 迭代 |
| 中期可行性（20 个案例） | **6/10** | LLM 非确定性开始显现 |
| 长期可维护性 | **7/10** | 取决于 normalized_intermediate 设计质量 |
| 团队执行难度 | **7/10** | 概念清晰，但需要 prompt engineering 经验 |

---

## 七、一句话总结

> **"上游自由，中间标准化，输出契约化"——这是处理 LLM 时代 schema 不确定性的数据工程范式。修正方案方向对了，但需要补上 normalized_intermediate 和 output validation 两层，才能从"能跑"升级到"可信赖"。**

---

*报告完成。数据工程师视角：不要把 LLM 当成万能胶水——它是强大的 schema-on-read 引擎，但需要传统数据工程的质量护栏来约束它。*
