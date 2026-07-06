# 专家 10：技术写作专家报告 — 文档即代码 + Specification 视角

> **日期**: 2026-06-18
> **角色**: 技术写作与规格文档专家（API 规格设计 / RFC / 可执行契约）
> **评估对象**: Solution Pro 输出作为"系统规格文档"的精确度与可用性

---

## 核心论点

**Solution Pro 的输出不是规格文档，而是"设计叙事"（Design Narrative）。**

这个区分至关重要。规格文档（Specification）是一种**可执行的契约**——它精确到可以机械验证、自动生成代码骨架、驱动测试用例。而设计叙事是一种**说服性文档**——它解释了"为什么这样做"和"做什么"，但留下了大量"怎么做"的空白。

当前的 final_result.json 是一份**优秀的商业计划书 + 技术选型文档**，但作为 Ship Pro 的输入规格，它的精确度**不够**。

---

## 一、final_result.json 作为"规格"的精确度评估

### 1.1 它有什么（信息丰富度：8/10）

以跨境AI算力中转站为例，final_result.json 包含：

| 维度 | 内容 | 质量 |
|------|------|------|
| 组件清单 | 6 个核心组件（New API / Next.js / Paddle / Cloudflare / 供应商 / 监控） | ✅ 清晰 |
| 组件角色 | 每个组件的职责描述 | ✅ 明确 |
| 部署位置 | Docker on Railway / Vercel / SaaS 等 | ✅ 具体 |
| 数据流 | 用户→CDN→网关→路由→供应商→回传→计量 | ✅ 完整 |
| 实施计划 | 3 阶段 15 天，每阶段有 tasks 和 milestones | ✅ 可执行 |
| 定价模型 | 免费层/Credit包/订阅，具体金额 | ✅ 精确 |
| 风险管理 | 高/中/低分级，有 mitigation | ✅ 完整 |
| 财务预测 | 100/1000/3000 用户的收入成本模型 | ✅ 量化 |

### 1.2 它缺什么（规格精确度：4/10）

对照 ADL（Architecture Description Language）的四大要素——**Components, Connectors, Configurations, Constraints**：

| ADL 要素 | 当前状态 | 缺失内容 |
|----------|----------|----------|
| **Components** | ✅ 有名称+角色 | ❌ 无接口定义、无数据 schema、无状态机 |
| **Connectors** | ⚠️ 数据流是 prose | ❌ 无协议定义（REST? SSE? WebSocket?）、无 API 契约 |
| **Configurations** | ⚠️ 部署位置有 | ❌ 无环境配置、无拓扑约束、无扩缩容规则 |
| **Constraints** | ⚠️ 业务约束有 | ❌ 无性能指标（P99 延迟？吞吐量？）、无 SLA 数值化 |

### 1.3 具体缺失清单（以"能否开始编码"为标准）

一个开发者拿到这份 final_result.json，以下问题**无法回答**：

1. **API 契约**：`/v1/chat/completions` 的 request/response schema 是什么？字段类型？必填/可选？
2. **数据模型**：User 表有哪些字段？Token 计量精度（整数？浮点？几位小数？）？
3. **状态机**：用户状态有哪些？（注册→已验证→已充值→活跃→欠费→停用？）状态转换条件？
4. **错误处理**：供应商超时返回什么？Credit 不足时 API 返回什么 HTTP 状态码？
5. **性能约束**：故障切换 <3s 是 P50 还是 P99？API 响应延迟目标是多少？
6. **并发模型**：Token 扣费是同步还是异步？如何防止超扣？
7. **安全边界**：API Key 的权限模型？Rate limit 的具体实现（固定窗口？滑动窗口？令牌桶？）？
8. **集成接口**：Paddle Webhook 的 payload 结构？New API 与 PostgreSQL 的交互模式？

**结论**：当前 final_result.json 精确到了"可以选技术栈"和"可以排项目计划"，但**没有精确到"可以开始写代码"**。

---

## 二、"规格"应该到什么粒度？

### 2.1 三层规格模型

借鉴 OpenAPI 的设计哲学，系统规格应该有三层：

| 层级 | 粒度 | 对应物 | 当前 final_result 覆盖度 |
|------|------|--------|------------------------|
| **L1: 系统架构规格** | 组件 + 连接器 + 配置 | 架构图的形式化描述 | ✅ 80% |
| **L2: 接口规格** | API 端点 + 数据 schema + 错误码 | OpenAPI spec | ❌ 0% |
| **L3: 行为规格** | 状态机 + 业务规则 + 约束条件 | BDD scenarios / 决策表 | ⚠️ 30%（散落在 prose 中） |

### 2.2 Solution Pro 应该覆盖到哪一层？

**建议：Solution Pro 应该覆盖 L1 完整 + L2 关键接口 + L3 核心行为。**

理由：
- **L1 完整**：这是 Solution Pro 的核心产出，当前已经做得不错，但需要从 prose 升级为结构化（见下文建议）
- **L2 关键接口**：不需要写完整 OpenAPI，但**核心数据流上的接口**必须有 schema 定义（比如 `/v1/chat/completions` 的转发格式、用户模型、计费模型）
- **L3 核心行为**：关键业务规则应该用**决策表**或**状态机**表达，而不是散文

### 2.3 不应该下探到函数级

**明确反对**函数级规格。原因：
1. Solution Pro 是架构层工具，不是详细设计工具
2. 函数级规格会过度约束实现（比如强制某种设计模式）
3. Ship Pro 的 LLM 完全有能力从接口规格推导出函数结构
4. 保持"规格→任务"的映射在 WP 级别，不要到 function 级别

---

## 三、`_ship_pro_hints` 评估

### 3.1 当前设计

```json
"_ship_pro_hints": {
  "architecture_location": "architecture.core_components",
  "implementation_plan_location": "implementation_plan.phases",
  "requirements_location": "quality_assurance.requirement_coverage"
}
```

### 3.2 评价：好的导航，但不够

**优点**：
- ✅ 解决了"格式不统一"的核心问题（5 种不同结构）
- ✅ 轻量级，不增加 Solution Pro 太多负担
- ✅ 让 Ship Pro 知道去哪里找数据

**不足**：
- ❌ 只是"位置导航"，不是"语义导航"——告诉你数据在哪，但不告诉你数据意味着什么
- ❌ 没有解决"数据精度不够"的问题——找到了组件列表，但组件列表本身不够详细
- ❌ 没有"缺失字段"的显式表达——如果某个关键规格缺失，Ship Pro 无法知道

### 3.3 建议：从"导航"升级为"规格摘要"

```json
"_spec_summary": {
  "components": [
    {
      "name": "API网关层",
      "type": "gateway",
      "interfaces": [
        {"name": "proxy_api", "protocol": "REST/SSE", "schema_ref": "openai_compatible"}
      ],
      "dependencies": ["PostgreSQL", "供应商API"],
      "constraints": ["故障切换<3s P95", "MIT License"]
    }
  ],
  "key_interfaces": [
    {
      "name": "openai_compatible",
      "description": "100% OpenAI 兼容的 /v1/chat/completions 接口",
      "request_schema": {"model": "string", "messages": "array", "stream": "boolean?"},
      "response_schema": {"choices": "array", "usage": "object"}
    }
  ],
  "missing_specs": [
    "user_state_machine",
    "token_billing_precision",
    "error_response_format"
  ]
}
```

这样 Ship Pro 不仅知道"数据在哪"，还知道"数据是什么"和"数据缺什么"。

---

## 四、Ship Pro 的工作本质：规格→任务 还是 规格→代码骨架？

### 4.1 答案：两者都不是。应该是"规格→可执行工作包"。

| 模式 | 输入 | 输出 | 问题 |
|------|------|------|------|
| 规格→任务拆解 | 架构规格 | 任务列表（做什么） | 缺少"怎么验证" |
| 规格→代码骨架 | 接口规格 | 代码框架（怎么组织） | 缺少"为什么这样做" |
| **规格→可执行工作包** | 架构+接口+行为规格 | WP（做什么+怎么验证+技术约束+集成检查点） | ✅ 完整 |

### 4.2 "可执行工作包"的定义

一个 WP 要成为"可执行的"，必须满足：

1. **有明确的完成标准**（Acceptance Criteria）——可验证
2. **有技术约束**（Technical Constraints）——不可违反
3. **有集成检查点**（Integration Checkpoints）——与其他 WP 的交互验证
4. **有交付物清单**（Deliverables）——具体的文件/模块
5. **有依赖关系**（Dependencies）——前置 WP 的完成是启动条件

### 4.3 当前 final_result 到 WP 的 gap

| WP 所需信息 | final_result 提供？ | Ship Pro 需要补？ |
|-------------|-------------------|-----------------|
| 做什么（What） | ✅ 有（组件+功能列表） | 不需要 |
| 怎么验证（AC） | ⚠️ 部分（RTM 有证据，但不是 AC 格式） | **需要** |
| 技术约束 | ⚠️ 散落（部署信息有，性能约束少） | **需要补充** |
| 集成检查点 | ❌ 无 | **需要推导** |
| 交付物清单 | ❌ 无 | **需要生成** |
| 依赖关系 | ⚠️ implementation_plan 有 phase 顺序 | **需要细化** |
| 工时估算 | ❌ 无 | **需要估算** |

**结论**：Ship Pro 的核心价值不是"格式转换"，而是**规格补全 + 工程化翻译**。它把"设计叙事"翻译成"可执行工作包"。

---

## 五、核心建议

### Q1: 当前 final_result.json 作为"规格"，精确度够吗？

**不够。** 作为 L1 架构规格基本合格（80%），但缺少 L2 接口规格和 L3 行为规格。

**建议**：
- 在 Solution Pro 的 summarizer prompt 中增加"关键接口定义"要求（不需要完整 OpenAPI，但核心数据流上的接口必须有 schema）
- 增加"核心状态机"要求（用户状态、订单状态、计费状态）
- 增加"性能约束量化"要求（延迟、吞吐量、可用性数值）

**实施信心：7/10** — 增加这些字段不会破坏 Solution Pro 的灵活性，但会增加 prompt 复杂度。

### Q2: "规格"应该到什么粒度？

**模块级 + 关键接口级。不到函数级。**

- L1（系统架构）：完整组件 + 连接器 + 配置 ✅
- L2（接口规格）：核心数据流上的接口 schema ✅
- L3（行为规格）：关键业务规则的决策表/状态机 ✅
- L4（函数规格）：❌ 不做，留给 Ship Pro + Super Loop

**实施信心：8/10** — 这是正确的抽象层级，与 OpenAPI 的设计哲学一致。

### Q3: `_ship_pro_hints` 是好的"规格导航"吗？

**方向对，但应该升级为 `_spec_summary`。**

不是简单的"数据在哪"导航，而是"数据是什么 + 数据缺什么"的语义摘要。这样 Ship Pro 可以：
1. 直接读取结构化的组件/接口信息（不需要从 5 种格式中解析）
2. 知道哪些规格缺失（可以主动要求补充或标记为风险）
3. 减少 LLM 解析的不确定性

**实施信心：7/10** — 需要 Solution Pro 和 Ship Pro 共同约定 `_spec_summary` 的 schema。

### Q4: Ship Pro 的工作本质是什么？

**"规格→可执行工作包"（Specification → Executable Work Packages）。**

不是简单的"任务拆解"（缺少验证维度），也不是"代码骨架"（过度约束实现）。Ship Pro 的核心价值是：
1. **规格补全**：把 L1 架构翻译成 L2/L3 细节
2. **工程化翻译**：把"组件"翻译成"WP"（带 AC、约束、检查点）
3. **集成验证设计**：定义 WP 之间的集成检查点

**实施信心：8/10** — 这明确了 Ship Pro 的定位，避免它退化为"格式转换器"。

### Q5: 砍掉 blueprint freezing 后，规格稳定性如何保证？

**不需要"格式稳定性"，需要"语义稳定性"。**

传统软件工程追求格式稳定（这样工具可以解析）。但 Ship Pro 是 LLM 引导的——LLM 可以处理格式变化，只要**语义**稳定。

语义稳定的保证：
1. `_spec_summary` 提供统一的语义入口（不管底层格式怎么变）
2. RTM 提供需求覆盖的验证锚点
3. Ship Pro 的 LLM 有足够的上下文理解能力

**实施信心：6/10** — 这是最大的风险点。LLM 解析格式变化是可行的，但需要充分的测试覆盖。

---

## 六、盲点与风险

### 6.1 盲点 1：规格验证循环

当前架构是单向的：Solution Pro → Ship Pro → Super Loop。

但规格驱动开发的最佳实践要求**验证循环**：
- Ship Pro 发现规格缺失 → 反馈给 Solution Pro 补充？
- Super Loop 发现实现困难 → 反馈给 Ship Pro 调整 WP？

**建议**：增加一个轻量级的"规格质疑"机制——Ship Pro 可以输出一个 `spec_questions[]` 字段，列出需要 Solution Pro 澄清的问题。

### 6.2 盲点 2：规格版本化

如果 Solution Pro 重新运行（需求变更），final_result 会变化。Ship Pro 如何知道哪些 WP 需要更新？

**建议**：在 final_result 中增加 `spec_version` 字段（语义化版本号），Ship Pro 记录每个 WP 基于哪个 spec_version 生成。

### 6.3 风险 1：LLM 解析的不确定性

Ship Pro 用 LLM 解析 final_result → WP 的映射。同一个 final_result，两次运行可能产生不同的 WP 拆分。

**缓解**：
- 提供确定性的 WP 模板（强制输出格式）
- 增加 WP 输出的 schema 验证
- 关键 WP（如支付集成）手工审核

### 6.4 风险 2：规格膨胀

如果要求 Solution Pro 输出更多规格字段（接口 schema、状态机、性能约束），可能导致：
- Prompt 过长，影响 Solution Pro 质量
- 输出过大，增加 token 成本
- 规格冲突（不同字段描述不一致）

**缓解**：
- 只要求**核心数据流**上的接口规格（不是所有接口）
- 只要求**关键业务规则**的状态机（不是所有状态）
- `_spec_summary` 作为可选增强，不是必填

---

## 七、实施路线图建议

### Phase 1（立即）：定义 `_spec_summary` schema

- Solution Pro 和 Ship Pro 共同约定 `_spec_summary` 的 JSON schema
- 包含：components（结构化）、key_interfaces、missing_specs
- 向后兼容：不影响现有 final_result 格式

### Phase 2（短期）：增加 L2 接口规格模板

- 为核心数据流上的接口定义轻量 schema（不需要完整 OpenAPI）
- 格式：`{ "endpoint": "...", "method": "...", "request": {...}, "response": {...} }`
- 在 Solution Pro 的 summarizer prompt 中作为"建议字段"（非必填）

### Phase 3（中期）：Ship Pro 规格验证

- Ship Pro 输出 `spec_questions[]` 字段
- 如果关键规格缺失，Ship Pro 标记为风险而不是猜测
- 增加 spec_version 追踪

### Phase 4（长期）：规格→代码骨架自动生成

- 从 `_spec_summary` 自动生成项目骨架（目录结构、接口定义、数据模型）
- 这需要更形式化的规格，但当前阶段不需要

---

## 八、总结

| 维度 | 当前状态 | 目标状态 | Gap |
|------|----------|----------|-----|
| 架构规格（L1） | 80% 覆盖 | 95% 覆盖 | 需要结构化组件定义 |
| 接口规格（L2） | 0% 覆盖 | 60% 覆盖 | 核心接口需要 schema |
| 行为规格（L3） | 30% 覆盖 | 70% 覆盖 | 关键状态机需要形式化 |
| 规格导航 | `_ship_pro_hints`（位置） | `_spec_summary`（语义） | 需要升级 |
| Ship Pro 定位 | 格式转换器 | 规格→可执行WP | 需要明确 |

**最终判断**：Solution Pro 的输出是一份**优秀的"设计叙事"**，但作为**"可执行规格"还差一个抽象层级**。这个 gap 不需要 Solution Pro 独自填补——Ship Pro 的 LLM 引导编译器正是为此设计的。关键是明确两者的契约边界：Solution Pro 负责 L1+关键 L2，Ship Pro 负责补全 L2+L3 并翻译成 WP。

---

*报告完成。技术写作专家视角。2026-06-18*
