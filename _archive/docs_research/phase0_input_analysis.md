# Phase 0 输入格式分析报告

> 分析日期：2026-06-18
> 分析目标：提取 final_result.json 中"模块/组件/架构"信息的深度结构，找出 Architect Agent 需要从每种格式中提取的核心信息模式。

---

## 1. 格式分类

### Format A: final_solution 嵌套型

- **样本**：智能简历生成系统、面向中小企业智能客服系统、Serenity Skills 迁移
- **特征**：
  - 顶层有 `status`、`session_id`、`generated_at` 等元数据
  - 核心方案包裹在 `final_solution.detailed_solution` 或 `final_solution` 下
  - 架构信息在 `final_solution.detailed_solution.architecture`
  - 组件列表在 `architecture.components`（数组，每项有 `id`/`name`/`summary`）
  - 有 `layer2_response` 完整性/必要性约束验证
  - 有 `quality_assurance` 详细评分
  - 有 `covered_req_ids` + `requirement_evidence` 需求追溯
- **模块信息路径**：`final_solution.detailed_solution.architecture.components[]`
- **依赖信息路径**：`final_solution.detailed_solution.architecture.data_flow` + `module_interactions`（部分样本）
- **技术栈路径**：组件内 `tier` 字段 + `architecture.design_pattern` + `implementation.phases[]`
- **需求覆盖路径**：`covered_req_ids[]` + `requirement_evidence{}`
- **实施计划路径**：`final_solution.detailed_solution.implementation.phases[]`

### Format B: 顶层扁平型

- **样本**：跨境AI算力中转站平台、企业级AI智能客服系统、电商订单系统
- **特征**：
  - 架构信息直接在顶层 `architecture` 下
  - 无 `final_solution` 包裹层
  - 组件描述方式多样：有的用 `core_components[]`，有的用 `components[]` + `layers[]`
  - 实施计划直接在顶层 `implementation_plan`
  - 需求覆盖有的用 `quality_assurance.requirement_coverage`，有的用 `req_coverage`
- **模块信息路径**：
  - 跨境AI：`architecture.core_components[]`（每项有 `name`/`component`/`role`/`deployment`/`license`）
  - 企业客服：`architecture.components[]` + `architecture.layers[]`
  - 电商订单：`architecture` 为扁平 key-value（tech stack 列表，无组件数组）
- **依赖信息路径**：`architecture.data_flow`（字符串描述）
- **技术栈路径**：`architecture` 各字段（如 `api_gateway`、`microservices_framework`、`cache`、`database` 等）
- **需求覆盖路径**：`quality_assurance.requirement_coverage` 或 `req_coverage.details`
- **实施计划路径**：`implementation_plan.phases[]`

### Format C: 最小型（仅元数据）

- **样本**：dryrun_solution、验证_PipelineOrchestra
- **特征**：
  - 仅包含 pipeline 执行元数据（`status`、`session_id`、`stages_completed`、`final_score`）
  - 无架构信息、无组件列表、无实施计划
  - dryrun 有 `summary` 字段记录各阶段状态
  - 验证样本仅有 `{"status": "completed"}`
- **模块信息路径**：❌ 无
- **依赖信息路径**：❌ 无
- **技术栈路径**：❌ 无
- **需求覆盖路径**：❌ 无
- **实施计划路径**：❌ 无

---

## 2. 各样本详细分析

### 样本 1: 跨境AI算力中转站平台

- **格式类型**：Format B（顶层扁平型）
- **文件行数**：422 行
- **模块列表**（`architecture.core_components[]`，6 个）：
  1. API网关层 — New API（Docker on Railway）
  2. 前端层 — Next.js（Vercel）
  3. 支付层 — Paddle MoR → Stripe
  4. CDN安全层 — Cloudflare
  5. 供应商层 — DeepSeek+Qwen+Zhipu
  6. 监控层 — UptimeRobot+Telegram Bot
- **依赖信息**：`architecture.data_flow`（字符串："用户→Cloudflare CDN→New API网关→智能路由→中国AI供应商→..."）
- **技术栈**：每个组件的 `component`/`deployment`/`license` 字段
- **需求覆盖**：`quality_assurance.requirement_coverage`（71/71=100%）+ `covered_req_ids[]`（71个ID）+ `requirement_evidence[]`（每条有 req_id/status/evidence）
- **实施计划**：`implementation_plan.phases[]`（3 阶段，15天 MVP）
- **额外信息**：
  - `pricing_model` — 定价模型
  - `supplier_strategy` — 供应商策略
  - `risk_management` — 风险管理（高/中/低分级）
  - `financial_projections` — 财务预测
  - `recommendations` — 建议（immediate/short_term/long_term/governance）

### 样本 2: 智能简历生成系统

- **格式类型**：Format A（final_solution 嵌套型）
- **文件行数**：95 行
- **模块列表**（`final_solution.detailed_solution.architecture.components[]`，8 个）：
  1. COMP-01: 输入解析层
  2. COMP-02: JD解析与匹配引擎
  3. COMP-03: 内容优化器
  4. COMP-04: 统一中间表示层
  5. COMP-05: 双格式渲染管道
  6. COMP-06: ATS模拟评分器
  7. COMP-07: 保真度自检器
  8. COMP-08: 半导体封装行业知识库
- **依赖信息**：`architecture.tier_architecture`（三层可降级 Tier 1/2/3）+ 组件间数据流隐含在 `summary` 中
- **技术栈**：每个组件的 `tier` 字段 + `tier_architecture` 的 `deps` 字段（如 "≤6包/0API"）
- **需求覆盖**：`covered_req_ids[]`（6个）+ `requirement_evidence{}`（key=req_id, value=evidence text）
- **实施计划**：`final_solution.detailed_solution.implementation.phases[]`（3 阶段，5-8周）
- **额外信息**：
  - `layer2_response` — L2 完整性/必要性约束验证
  - `quality_assurance` — harness 评分 + 审计 + 质量轨迹
  - `recommendations[]` — 带优先级的建议

### 样本 3: 企业级AI智能客服系统

- **格式类型**：Format B（顶层扁平型）— 最丰富的变体
- **文件行数**：266 行
- **模块列表**：
  - `architecture.layers[]`（6 层）：交互渠道层、API网关层、会话引擎层、知识能力层、集成层、基础设施层
  - `architecture.components[]`（12 个组件）：API Gateway、Multi-Channel Adapter、Conversation Service、Intent Service、RAG Service、LLM Inference Service、Semantic Cache、Human Agent Service、Compliance Infrastructure、CRM Adapter、Observability、Data Layer
- **依赖信息**：`architecture.request_flow`（长字符串，完整请求链路）
- **技术栈**：每个组件的 `tech` 字段（如 "Kong/Higress"、"vLLM+PagedAttention"）
- **需求覆盖**：`requirements.items[]`（7个，每项有 id/category/priority/description/status）
- **实施计划**：`implementation_plan.phases[]`（5 阶段，9个月）
- **额外信息**（最丰富）：
  - `model_routing` — 三级分层模型路由（L0-L4）
  - `rag_architecture` — RAG 检索架构
  - `human_handoff` — 人工转接触发条件+上下文包
  - `high_availability` — 高可用设计（99.9% SLA）
  - `compliance` — GDPR/PIPL/EU AI Act 合规
  - `observability` — 可观测性栈
  - `cost_analysis` — CAPEX/OPEX 成本分析
  - `case_studies[]` — 案例研究
  - `quality_assurance.acceptance_criteria[]` — 验收标准

### 样本 4: 电商订单系统

- **格式类型**：Format B（顶层扁平型）— 技术栈导向变体
- **文件行数**：190 行
- **模块列表**：
  - `architecture` 为 key-value 结构（非组件数组），14 个技术域：
    - api_gateway: APISIX
    - microservices_framework: Spring Cloud Alibaba + gRPC + JDK 21
    - service_discovery: Nacos
    - distributed_transaction: Seata + Outbox Pattern
    - mq_transaction: RocketMQ 5.x
    - mq_analytics: Kafka 3.x
    - cache: Redis Cluster + Caffeine + 布隆过滤器
    - database: MySQL 8.0 + ShardingSphere-JDBC
    - search: Elasticsearch 8.x
    - distributed_id: Snowflake
    - rate_limit_circuit_breaker: Sentinel
    - observability: OpenTelemetry + Prometheus + Loki + Grafana + SkyWalking
    - container_orchestration: Kubernetes + HPA + ArgoCD
    - chaos_engineering: ChaosBlade
  - `deployment` 对象描述部署拓扑
- **依赖信息**：`executive_summary.solution_overview`（字符串描述四层架构）
- **技术栈**：`architecture` 本身就是技术栈清单
- **需求覆盖**：`req_coverage`（18/18=100%）+ `req_coverage.details{}`（key=req_id, value={category, description, status, solution}）
- **实施计划**：`executive_summary.implementation_timeline`（"9个月，4阶段"），但无 phases 数组
- **额外信息**：
  - `executive_summary.capacity_model` — 容量模型（normal/peak/extreme QPS）
  - `executive_summary.cost_estimate` — 成本估算
  - `quality_scores` — 多维度评分
  - `risk_register_count` — 风险统计
  - `known_gaps[]` — 已知缺口（P1/P2 分级）
  - `pipeline_metadata` — 管线元数据

### 样本 5: 面向中小企业的智能客服系统

- **格式类型**：Format A（final_solution 嵌套型）
- **文件行数**：193 行
- **模块列表**（`final_solution.detailed_solution.architecture.components[]`，10 项）：
  1. 多渠道接入层
  2. API网关
  3. 会话管理服务
  4. AI对话引擎Pipeline
  5. LLM代理网关
  6. 知识库服务
  7. 三级缓存层
  8. 人工客服工作台
  9. 数据分析看板
  10. 数据层
- **依赖信息**：`architecture.data_flow`（长字符串，完整请求链路+三级缓存+四级置信度校验）
- **技术栈**：散布在组件描述的字符串中（无独立 tech 字段）
- **需求覆盖**：无显式 `covered_req_ids`，需求覆盖信息在 `quality_assurance` 中隐含
- **实施计划**：`final_solution.detailed_solution.implementation.phases[]`（4 阶段，12周）+ `milestones[]` + `resources`
- **额外信息**：
  - `executive_summary` — 含 ROI 分析、投资预算
  - `risk_management` — 高/中/低分级风险
  - `layer2_response` — 完整性/必要性约束
  - `recommendations` — immediate/short_term/long_term/governance 分级建议

### 样本 6: Serenity Skills 迁移

- **格式类型**：Format A（final_solution 嵌套型）
- **文件行数**：314 行
- **模块列表**（`final_solution.detailed_solution.architecture.components[]`，7 个）：
  1. COMP-01: serenity-method（供应链瓶颈分析）
  2. COMP-02: serenity-alpha（阿尔法假设）
  3. COMP-03: bayesian-intrinsic-growth-valuation（贝叶斯估值）
  4. COMP-04: gf-dma-health-index（估值健康指数）
  5. COMP-05: tam-adj-peg（TAM调整PEG）
  6. COMP-06: serenity-radar（注意力雷达）
  7. COMP-07: serenity-data-integration（数据集成层）
- **依赖信息**：`architecture.module_interactions`（字符串："6个方法论模块通过serenity-data-integration的DataFetcher统一接口获取数据。模块间无直接依赖..."）
- **技术栈**：每个组件的 `tier`/`maturity`/`reference`/`path` 字段
- **需求覆盖**：`covered_req_ids[]`（5个）+ `requirement_evidence[]`（每项有 req_id/status/evidence）
- **实施计划**：`final_solution.detailed_solution.implementation.phases[]`（3 阶段，3周）+ `resources`
- **额外信息**：
  - 每个组件有 `maturity`（stable/beta/experimental）和 `path`（部署路径）
  - `requirement_evidence` 在顶层（与 `final_solution` 平级）
  - `layer2_response` — 完整性/必要性约束
  - `risk_management.identified_risks[]` — 带 id/probability/impact/mitigation/status

### 样本 7: dryrun_solution（不完整）

- **格式类型**：Format C（最小型）
- **文件行数**：41 行
- **内容**：仅 pipeline 执行元数据
  - `status`、`session_id`、`topic`、`solution_type`
  - `final_score`、`stages_completed`、`duration_seconds`
  - `output_files[]` — 各阶段输出文件列表
  - `summary` — 各阶段完成状态
- **模块/架构信息**：❌ 无
- **用途**：仅验证 pipeline 流程可运行

### 样本 8: 验证_PipelineOrchestra（不完整）

- **格式类型**：Format C（最小型）— 极端情况
- **文件行数**：2 行
- **内容**：`{"status": "completed"}`
- **模块/架构信息**：❌ 无
- **用途**：仅验证 orchestrator 可完成

---

## 3. 共性信息提取

无论什么格式，Architect Agent 需要提取的核心信息：

### 3.1 必须提取（5 项）

| # | 信息类型 | 作用 | 存在时的典型路径 |
|---|---------|------|----------------|
| 1 | **模块/组件列表** | 系统由哪些部分组成 | `architecture.components[]` 或 `architecture.core_components[]` 或 `final_solution.detailed_solution.architecture.components[]` |
| 2 | **组件职责描述** | 每个组件做什么 | 组件内 `summary`/`role`/`description` 字段 |
| 3 | **数据流/请求流** | 请求如何在组件间流转 | `architecture.data_flow` 或 `architecture.request_flow`（字符串） |
| 4 | **技术选型** | 用了什么技术 | 组件内 `tech`/`component` 字段，或 `architecture` 的 key-value |
| 5 | **实施阶段** | 怎么分步实施 | `implementation_plan.phases[]` 或 `final_solution.detailed_solution.implementation.phases[]` |

### 3.2 应该提取（5 项）

| # | 信息类型 | 作用 | 存在时的典型路径 |
|---|---------|------|----------------|
| 6 | **需求覆盖** | 哪些需求被覆盖了 | `covered_req_ids[]` + `requirement_evidence` |
| 7 | **质量评分** | 方案质量如何 | `quality_assurance` 或 `quality_scores` |
| 8 | **风险清单** | 有哪些风险和缓解 | `risk_management` |
| 9 | **建议/下一步** | 后续该做什么 | `recommendations` |
| 10 | **约束/假设** | 方案的边界条件 | `executive_summary.key_constraints` 或 `layer2_response` |

### 3.3 可选提取（4 项）

| # | 信息类型 | 作用 | 存在时的典型路径 |
|---|---------|------|----------------|
| 11 | **成本估算** | 花多少钱 | `cost_analysis` 或 `financial_projections` 或 `executive_summary.cost_estimate` |
| 12 | **部署拓扑** | 怎么部署 | `deployment` 或组件内 `deployment` 字段 |
| 13 | **验收标准** | 怎么算完成 | `quality_assurance.acceptance_criteria[]` |
| 14 | **案例参考** | 业界怎么做的 | `case_studies[]` |

---

## 4. 格式变体处理策略

### 4.1 组件列表提取策略

组件列表是最大的格式变体。建议 Architect Agent 使用以下优先级链：

```
1. final_solution.detailed_solution.architecture.components[]     → Format A
2. architecture.core_components[]                                 → Format B (跨境AI)
3. architecture.components[]                                      → Format B (企业客服)
4. architecture (as key-value map)                                → Format B (电商订单)
5. executive_summary.solution_overview (parse text)               → fallback
```

### 4.2 组件字段归一化

不同样本的组件字段名不同，需要归一化：

| 标准字段 | 样本 1 | 样本 2 | 样本 3 | 样本 4 | 样本 5/6 |
|---------|--------|--------|--------|--------|----------|
| id | ❌ | `id` | ❌ | ❌ | `id` |
| name | `name` | `name` | `name` | (key) | `name` |
| description/role | `role` | `summary` | `role` | (value) | `summary` |
| technology | `component` | `tier` | `tech` | (value) | (in summary) |
| deployment | `deployment` | ❌ | ❌ | ❌ | `path` |

**建议归一化 schema**：
```json
{
  "id": "string (optional)",
  "name": "string (required)",
  "description": "string (required)",
  "technology": "string (optional)",
  "deployment": "string (optional)",
  "dependencies": ["string"]
}
```

### 4.3 数据流提取策略

数据流在所有格式中都是**字符串**（非结构化），需要 NLP 提取或保留原文：

```
优先级：
1. architecture.request_flow（最详细，样本3）
2. architecture.data_flow（样本1/2/5/6）
3. executive_summary.solution_overview（含数据流描述，样本4）
```

### 4.4 需求覆盖提取策略

```
优先级：
1. covered_req_ids[] + requirement_evidence[]  → 最完整（样本1/2/6）
2. covered_req_ids[] + requirement_evidence{}  → key-value 变体（样本2）
3. req_coverage.details{}                      → 含 solution 字段（样本4）
4. requirements.items[]                        → 含 status 字段（样本3）
5. quality_assurance.requirement_coverage      → 仅统计数字（样本1）
```

### 4.5 Format C 处理

对于仅有元数据的样本（dryrun/验证），Architect Agent 应：
- 跳过架构提取
- 仅记录 pipeline 执行状态（score/stages/duration）
- 标记为"不可用于架构分析"

---

## 5. 可用测试案例评估

| 案例 | 完整度 | 格式类型 | 组件数 | 行数 | 推荐用途 |
|------|--------|---------|--------|------|---------|
| 跨境AI算力中转站 | ✅ 完整 | Format B | 6 | 422 | 测试"层式组件"提取（每层有 name/component/role/deployment/license） |
| 智能简历生成系统 | ✅ 完整 | Format A | 8 | 95 | 测试"带 ID 组件"提取（COMP-01..08）+ tier 架构 |
| 企业级AI智能客服 | ✅ 完整 | Format B | 12+6层 | 266 | 测试"最丰富格式"提取（双维度：layers + components + 多个专项架构） |
| 电商订单系统 | ✅ 完整 | Format B-tech | 14 tech域 | 190 | 测试"key-value 技术栈"提取（无组件数组，只有 tech 列表） |
| 中小企业智能客服 | ✅ 完整 | Format A | 10 | 193 | 测试"字符串组件描述"提取（无独立 tech 字段，信息嵌在 summary 中） |
| Serenity Skills 迁移 | ✅ 完整 | Format A | 7 | 314 | 测试"带成熟度标记"组件提取（maturity + path + reference） |
| dryrun_solution | ❌ 不完整 | Format C | 0 | 41 | 测试"空输入"容错 |
| 验证PipelineOrchestra | ❌ 不完整 | Format C | 0 | 2 | 测试"极端最小输入"容错 |

### 推荐测试矩阵

| 测试目标 | 首选案例 | 备选案例 |
|---------|---------|---------|
| 组件列表提取 | 企业级AI智能客服（12组件+6层） | 智能简历生成系统（8组件带ID） |
| 数据流提取 | 跨境AI算力中转站 | 中小企业智能客服 |
| 技术栈提取 | 电商订单系统（14个tech域） | 跨境AI算力中转站 |
| 需求覆盖提取 | 跨境AI算力中转站（71个REQ） | 智能简历生成系统（6个REQ） |
| 实施计划提取 | 企业级AI智能客服（5阶段9月） | 中小企业智能客服（4阶段12周） |
| 容错/空输入 | 验证PipelineOrchestra | dryrun_solution |
| 全功能端到端 | 企业级AI智能客服 | 跨境AI算力中转站 |

---

## 6. 关键发现与建议

### 6.1 格式不一致的核心问题

1. **组件列表位置不统一**：有的在 `final_solution` 下，有的在顶层
2. **组件字段名不统一**：`role` vs `summary` vs `description`，`component` vs `tech` vs `technology`
3. **组件结构不统一**：有的是结构化数组，有的是 key-value map，有的是纯字符串
4. **需求覆盖格式不统一**：数组 vs 对象 vs 统计数字

### 6.2 对 Architect Agent 的建议

1. **实现多路径探测**：按优先级链逐个探测组件列表位置
2. **字段归一化**：将不同字段名映射到统一 schema
3. **容忍纯文本**：对于 key-value 格式或纯字符串，用 LLM 提取结构化信息
4. **优雅降级**：Format C 输入直接跳过架构提取，不报错
5. **保留原文**：数据流/请求流保留原始字符串，同时尝试提取结构化依赖

### 6.3 对上游 Pipeline 的建议

长期应推动 `final_result.json` 格式标准化：
- 统一组件列表路径为 `architecture.components[]`
- 统一组件字段为 `{id, name, description, technology, dependencies}`
- 统一需求覆盖为 `{covered_req_ids[], requirement_evidence[]}`
- 统一实施计划为 `implementation_plan.phases[]`
