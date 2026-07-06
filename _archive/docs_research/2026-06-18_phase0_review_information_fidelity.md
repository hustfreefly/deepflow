# Phase 0 评审：信息保真度

> 评审日期：2026-06-18
> 评审视角：信息流审计 — Solution Pro final_result.json → Ship Pro V3 5-Agent 管线 → ship_package.json
> 评审对象：输入 Schema、输出 Schema、格式处理指南、开发计划、2 个真实样本

---

## 评审结论：PASS_WITH_CONCERNS

整体设计方向正确，blueprint.json 作为中间契约有效隔离了格式变体。但存在 3 个中等风险问题需要在 Phase 1 解决，否则会导致下游 WP 质量不稳定。

---

## 关键发现

### 1. 输入 Schema 覆盖缺口：Format B 变体未被完整覆盖

`final_result_v3.schema.json` 的 Format B（`oneOf[1]`）要求 `project` 和 `architecture` 为 required，且 `architecture.style` 为 required。但真实样本中：

- **跨境AI算力中转站**：无 `project` 对象（项目名在顶层 `project` 字段，是字符串而非对象），无 `architecture.style` 字段。组件在 `architecture.core_components[]` 而非 `architecture.components[]`。
- **企业级AI智能客服**：有 `project` 对象和 `architecture.style`，但组件同时在 `architecture.layers[]` 和 `architecture.components[]` 两个维度存在。

**结论**：跨境AI样本实际不匹配 Format B schema（`project` 是 string 不是 object，缺少 `architecture.style`）。Schema 校验会拒绝这个真实样本。

### 2. blueprint.json 归一化会丢失「专项架构深度信息」

企业级AI智能客服的 final_result 包含极其丰富的专项架构信息：
- `model_routing`（5 级分层路由，含流量比例/延迟/成本）
- `rag_architecture`（三层知识库 + 幻觉率保障公式）
- `human_handoff`（触发条件 + 上下文包 + 降级链）
- `high_availability`（9 项具体机制）
- `compliance`（GDPR/PIPL/EU AI Act 详细合规策略）
- `observability`（10 项关键指标）

这些信息在 blueprint.json 的归一化 schema 中被压缩为 `modules[].summary`（字符串）和 `dependencies[]`。专项架构的深度技术细节（如置信度公式 `0.4×intent_match + 0.3×rag_relevance + ...`）在 blueprint 中没有结构化存放位置。

**影响**：Specifier Agent 写 AC 时无法引用这些具体数值，导致 AC 偏向泛泛（如"响应快"而非"P99 < 2s"）。

### 3. 数据流/请求流信息在 blueprint 中缺乏结构化表达

所有真实样本都有丰富的数据流描述（字符串），但 blueprint 的 `dependencies[]` 只有 `{from, to, reason}` 三元组。数据流中的关键信息会丢失：
- 分层超时参数（意图 100ms / RAG 800ms / LLM 首 token 1.5s）
- 缓存命中路径（命中 < 50ms 返回）
- 转接触发条件（置信度 < 0.7 | 情绪 > 0.8）

这些是 Specifier Agent 写可验证 AC 的关键输入。

### 4. Format C/D 输入的充足性判定合理但缺少显式门控

开发计划提到 Format C/D（最小/空输入）应优雅降级。输入 Schema 的 `oneOf[3]`（Format D）用 `not` 排除了其他格式的标志，设计合理。但 `validate_input.py` 的充足性评估标准未在文档中明确定义——什么情况下应该拒绝输入而非标注 `[数据不足]`？

### 5. ship_package 输出 Schema 缺少「原始需求追溯」字段

`ship_package_v3.schema.json` 的 `project_context.requirements_coverage` 有 `items[].id` 和 `status`，但没有 `evidence` 字段。输入的 `requirement_evidence` 包含详细的证据文本，经过 5 个 Agent 后这些信息被丢弃。

---

## 信息损失风险矩阵

| 信息类型 | 损失风险 | 影响 | 建议 |
|---------|---------|------|------|
| 组件列表结构 | **中** — Format B 的 `core_components[]` 不在 Schema 中 | Schema 校验拒绝真实样本 | Schema Format B 的 `architecture.properties` 增加 `core_components` 作为 `components` 的别名 |
| 专项架构深度参数 | **高** — model_routing/rag/handoff 等被压缩为 summary 字符串 | Specifier 无法写精确 AC | blueprint 增加 `domain_details` 字段（自由对象），保留原始专项架构 |
| 数据流参数 | **高** — 分层超时/缓存命中率/转接阈值等丢失 | AC 缺少性能指标 | blueprint 的 `dependencies` 增加 `sla` 子对象（latency/throughput/availability） |
| 需求证据文本 | **中** — requirement_evidence 的 evidence 字段未传递到 ship_package | 无法追溯需求→WP 映射 | ship_package 的 requirements_coverage.items 增加 `evidence` 字段 |
| 实施阶段信息 | **低** — implementation_hints 保留了阶段和模块关联 | 影响较小 | 可接受 |
| 成本/财务信息 | **低** — ship_package.summary 有 effort 估算 | 成本信息有替代路径 | 可接受 |
| 风险清单 | **低** — ship_package 有 risk_register | 风险有专门结构 | 可接受 |
| 案例研究 | **低** — 对 AI Coding 无直接价值 | 不影响 WP 生成 | 可丢弃 |

---

## 具体建议

### 建议 1：修复输入 Schema 对真实样本的兼容性（P0）

`final_result_v3.schema.json` Format B 需要调整：
- `project` 改为 `oneOf: [object, string]`（兼容跨境AI的字符串形式）
- `architecture.required` 移除 `style`（跨境AI无此字段）
- `architecture.properties` 增加 `core_components` 作为 `components` 的替代

**验证方式**：用 6 个真实完整样本跑 Schema 校验，全部通过。

### 建议 2：blueprint.json 增加 `domain_details` 和 `sla_constraints`（P1）

在 blueprint.json 归一化 schema 中增加：
```json
{
  "domain_details": {
    "type": "object",
    "description": "Domain-specific architecture details (model routing, RAG config, compliance, etc.)",
    "additionalProperties": true
  },
  "sla_constraints": {
    "type": "array",
    "items": {
      "type": "object",
      "properties": {
        "metric": { "type": "string" },
        "target": { "type": "string" },
        "scope": { "type": "string" }
      }
    }
  }
}
```

Architect Agent 从原始输入中提取这些深度信息，Specifier Agent 据此写精确 AC。

### 建议 3：ship_package 输出增加需求证据追溯（P1）

`ship_package_v3.schema.json` 的 `project_context.requirements_coverage.items[]` 增加：
```json
{
  "evidence": {
    "type": "string",
    "description": "How this requirement is covered by the work packages"
  },
  "covered_by_wps": {
    "type": "array",
    "items": { "type": "string", "pattern": "^WP-[0-9]+$" }
  }
}
```

### 建议 4：定义充足性门控标准（P1）

在 `validate_input.py` 中明确定义：
- **可处理**：至少有 1 个可识别的组件列表（任何格式路径）+ 至少 1 个实施阶段或数据流描述
- **降级处理**：有组件列表但无实施计划 → 标注 `overall_confidence: "low"`，生成 WP 时跳过阶段关联
- **拒绝处理**：无任何架构信息（Format C/D 且无 executive_summary）→ 输出错误报告，不生成 ship_package

### 建议 5：为 Architect Agent 的 few-shot 示例增加「深度信息提取」案例（P2）

当前 format_variants_guide.md 的 blueprint 示例只有 modules/dependencies/requirements/risks/implementation_hints。建议增加一个包含 `domain_details` 和 `sla_constraints` 的完整示例，展示如何从企业级AI智能客服样本中提取 model_routing 的 5 级分层和具体延迟指标。

---

## 附录：样本→Schema 匹配验证

| 样本 | 格式 | Schema 匹配 | 问题 |
|------|------|:-----------:|------|
| 企业级AI智能客服 | B | ✅ | — |
| 跨境AI算力中转站 | B | ❌ | `project` 是 string 非 object；缺 `architecture.style`；组件在 `core_components` 非 `components` |
| 智能简历生成系统 | A | ✅ | — |
| 中小企业智能客服 | A | ✅ | — |
| Serenity Skills 迁移 | A | ✅ | — |
| 电商订单系统 | C | ✅ | `pipeline_summary` + `executive_summary` 匹配 |
| dryrun_solution | D | ✅ | — |
| 验证_PipelineOrchestra | D | ✅ | — |

**匹配率**：7/8（87.5%）。跨境AI样本不匹配需要修复。
