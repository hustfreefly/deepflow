# R3 下游可消费性评估报告

> 评估角色：AI Coding Agent（模拟）
> 评估对象：Ship Pro v3.1.3 Specifier 输出
> 评估时间：2026-06-19
> 对比基线：v3.1.2（Case 4）

---

## 模拟场景

假设我是 AI Coding Agent，拿到 WP 后准备开始编码。我需要：
1. 理解项目结构和依赖（context_files）
2. 知道要产出什么文件（outputs）
3. 知道什么算完成（acceptance_criteria）
4. 知道有什么限制（constraints）
5. 直接开始写代码

---

## Case 2：电商平台（12 WPs）

### 1. context_files
- **包含**: blueprint.json, wp_structure.json, 上游 WP 的 outputs（如 gateway/kong.conf, services/user-service/**/*.go）
- **缺失**: 无项目现有代码文件（如已有的 .env、Makefile、CI 配置）
- **冗余**: context_files 列出了上游 WP 的 glob 模式（如 `services/user-service/**/*.go`），但 Agent 无法在编码前读取这些文件（因为它们还不存在）。这造成困惑——是让我参考已有代码，还是这些是我即将产出的？
- **评分**: 3/5

### 2. outputs
- **示例**: `gateway/kong.conf`, `services/user-service/**/*.go`, `services/order-service/src/**/*.java`
- **语义清晰度**: 高。路径直接映射到微服务目录结构，语言明确（Go/Java/Python）
- **问题**: 
  - glob 模式（`**/*.go`）作为 output 不够精确，Agent 不确定需要创建哪些具体文件
  - WP-005 (订单服务) 输出 Java，但 WP-002 (用户服务) 输出 Go——同一项目混用语言需要确认
- **评分**: 4/5

### 3. acceptance_criteria
- **示例 AC**: "并发 1000 请求/秒压测，限流策略触发后返回 429 状态码，限流阈值误差 < 5%"
- **可测试性**: 高。包含具体命令（`docker-compose up`、`curl`）、量化指标（<100ms、<50ms、≥99.9%）
- **标签**: 有 [SLA] 和 [RISK] 标签，但无 [SHIP_DERIVED] 标签
- **问题**: acceptance_tests 字段被截断为 "测试方向 1: ..." 的摘要形式，缺乏可执行的测试命令
- **评分**: 4/5

### 4. constraints
- **示例**: "使用 Kong（来自 blueprint COMP-01.technology_stack）"
- **具体性**: 高。明确引用 blueprint 来源，技术栈清晰
- **问题**: [RISK] 约束偏描述性（如 "分布式事务一致性: Saga 模式 + 补偿事务 + 对账系统"），不够操作化——Agent 需要知道具体用哪种 Saga 实现（编排式 vs 协调式）
- **评分**: 3.5/5

### 5. 整体可消费性
- **能否直接开始编码**: 需要澄清。WP-005 用 Java 而其他服务用 Go，需确认是否有意为之
- **需要的额外信息**: 项目初始化模板（go.mod / pom.xml 基础结构）、数据库 schema 设计
- **潜在困惑**: context_files 中的 glob 模式是输入还是输出？混用 Go/Java/Python 是架构决策还是疏忽？

---

## Case 3：半导体简历优化系统（7 WPs）

### 1. context_files
- **包含**: blueprint.json, wp_structure.json, 上游 WP 的具体文件（src/knowledge/terminology.py 等）
- **缺失**: 无外部依赖（如 text2vec 模型下载地址、半导体术语词典来源）
- **冗余**: 下游 WP 的 context_files 列出了上游所有文件（含 tests/），但测试文件对编码参考意义不大
- **评分**: 3.5/5

### 2. outputs
- **示例**: `src/knowledge/terminology.py`, `src/matching/jd_parser.py`, `src/optimizer/restructurer.py`
- **语义清晰度**: 高。文件名即功能，目录结构清晰（knowledge/matching/optimizer/ir/renderer/ats/fidelity）
- **问题**: 部分 output 为目录（如 `src/knowledge/`），不够精确
- **评分**: 4/5

### 3. acceptance_criteria
- **示例 AC**: "纯文本/Markdown 输入解析准确率 ≥ 95%（使用 10 份样本简历测试）"
- **可测试性**: 高。有 pytest 命令、覆盖率指标（≥80%）、准确率指标（≥95%、≥90%）
- **标签**: 有 [SLA] 和 [RISK] 标签，无 [SHIP_DERIVED]
- **亮点**: 保真度分级阈值（original≥95% / enhanced≥90% / restructured≥85%）非常具体
- **评分**: 4.5/5

### 4. constraints
- **示例**: "使用 text2vec-base-chinese（来自 blueprint COMP-02.technology_stack）"
- **具体性**: 高。模型名、算法名、库名都明确
- **问题**: [ARCH_INFERRED] 标签表示架构师推断，但 Agent 不确定这些是否可协商
- **评分**: 4/5

### 5. 整体可消费性
- **能否直接开始编码**: 基本可以。模块划分清晰，依赖链明确
- **需要的额外信息**: 半导体术语词典初始数据来源、text2vec 模型托管方式
- **潜在困惑**: [ARCH_INFERRED] 标签的约束是否硬性的？WP-003 的 LLM Rewriter 需要 `--confirm` 标志，但 CLI 框架尚未定义

---

## Case 4：API 网关转售平台（7 WPs）

### 1. context_files
- **包含**: blueprint.json, wp_structure.json（根 WP）；上游 outputs（下游 WP）
- **缺失**: 无 New API 的官方配置模板、Railway 部署配置
- **冗余**: 无明显冗余
- **对比 v3.1.2**: v3.1.2 包含了 `architect_output_v312.json`, `decomposer_output.json`, 以及具体配置文件路径。v3.1.3 简化为只列 blueprint + wp_structure + 上游 outputs
- **评分**: 2.5/5（v3.1.2 得 4/5）

### 2. outputs
- **示例**: `docker-compose.yml`, `Dockerfile`, `new-api-config/`, `frontend/`
- **语义清晰度**: 中。路径偏顶层，不够具体
- **问题**: 
  - WP-001 和 WP-002 的 outputs 完全相同（docker-compose.yml, Dockerfile, new-api-config/）——重复/冲突
  - `new-api-config/` 是目录，Agent 不知道里面需要什么文件
  - 对比 v3.1.2 的 `new-api/docker-compose.yml`, `new-api/config.yaml`, `scripts/verify-api.sh` 更精确
- **评分**: 2.5/5（v3.1.2 得 4/5）

### 3. acceptance_criteria
- **示例 AC**: "智能路由验证：加权随机算法分配请求到 3 家供应商，分配比例误差 < 5%"
- **可测试性**: 中高。有量化指标但缺少具体测试命令
- **标签**: 有 [SLA] 和 [RISK]，无 [SHIP_DERIVED]（v3.1.2 有 [SHIP_DERIVED] 标签）
- **对比 v3.1.2**: v3.1.2 每条 AC 带 [REQ-XXX] 追溯标签，v3.1.3 丢失了需求追溯
- **问题**: acceptance_tests 字段被截断为描述性文本，v3.1.2 有可执行命令
- **评分**: 3/5（v3.1.2 得 4/5）

### 4. constraints
- **示例**: WP-001 有 12 条 constraints，包含 6 条 [RISK]
- **具体性**: 低。[RISK] 约束过于冗长和描述性
- **问题**: 
  - WP-001 的 constraints 包含完整风险缓解方案（如 "Day 1并行申请商业协议+Partner Program备选+开发者Key interim mode（日限500次）+3+供应商冗余"），这不是约束而是项目计划
  - 同一 [RISK] 在多个 WP 中重复出现（如 "供应商ToS转售合规" 出现在 WP-001/002/006）
  - WP-001 列出 48 条 requirements——严重膨胀，Agent 无法判断哪些是核心需求
- **评分**: 2/5（v3.1.2 得 4/5）

### 5. 整体可消费性
- **能否直接开始编码**: 困难。WP-001 的 48 条 requirements 和 12 条 constraints 让 Agent 无法聚焦
- **需要的额外信息**: New API 的具体配置格式、Railway 部署参数、供应商 API 文档链接
- **潜在困惑**: 
  - WP-001 和 WP-002 产出相同文件，谁先写？冲突如何解决？
  - [RISK] 约束中的商业计划（如"Day 1并行申请"）是否需要在代码中实现？
  - 缺少 v3.1.2 中的验证脚本（verify-api.sh 等），Agent 不知道如何验证

---

## 综合评估

### v3.1.3 可消费性评分

| 维度 | Case 2 | Case 3 | Case 4 | 平均 |
|------|--------|--------|--------|------|
| context_files | 3/5 | 3.5/5 | 2.5/5 | 3.0 |
| outputs | 4/5 | 4/5 | 2.5/5 | 3.5 |
| acceptance_criteria | 4/5 | 4.5/5 | 3/5 | 3.8 |
| constraints | 3.5/5 | 4/5 | 2/5 | 3.2 |
| 整体可消费性 | 3.5/5 | 4/5 | 2.5/5 | 3.3 |

### 综合评分
- **可消费性**: 6.5/10
- **相比 v3.1.2 提升**: -1.5（退化）

### 关键改进（v3.1.3 相比 v3.1.2 做得好的）
1. ✅ constraints 明确引用 blueprint 来源（"来自 blueprint COMP-XX.technology_stack"）
2. ✅ [SLA] 和 [RISK] 标签系统化
3. ✅ acceptance_criteria 量化指标丰富
4. ✅ Case 2/3 的 WP 拆分合理，依赖链清晰

### 遗留问题（v3.1.3 的退化）
1. ❌ **acceptance_tests 被截断**: v3.1.2 有可执行测试命令，v3.1.3 只有描述性摘要
2. ❌ **丢失 [REQ-XXX] 追溯**: v3.1.2 每条 AC 关联需求编号，v3.1.3 丢失
3. ❌ **丢失 [SHIP_DERIVED] 标签**: v3.1.2 区分了来源，v3.1.3 未标注
4. ❌ **outputs 重复/冲突**: Case 4 的 WP-001 和 WP-002 产出相同文件
5. ❌ **requirements 膨胀**: Case 4 WP-001 有 48 条 requirements，失去聚焦
6. ❌ **[RISK] 约束过于冗长**: 包含商业计划而非技术约束，Agent 无法执行
7. ❌ **context_files 的 glob 模式**: 列出上游 outputs 的 glob 作为 context，但 Agent 无法在编码前读取（文件不存在）

### 建议修复优先级
1. **P0**: 恢复 acceptance_tests 的可执行命令格式
2. **P0**: 修复 Case 4 的 outputs 重复问题（WP-001/002 应有不同产出）
3. **P1**: 恢复 [REQ-XXX] 和 [SHIP_DERIVED] 标签
4. **P1**: 精简 requirements 列表（每个 WP ≤ 10 条核心需求）
5. **P2**: [RISK] 约束拆分为"技术实现约束"和"商业计划备注"
6. **P2**: context_files 区分"已有文件"和"上游产出文件"
