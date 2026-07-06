# Specifier Prompt 诊断

> **诊断日期**: 2026-06-19
> **诊断对象**: `ship_pro/prompts/specifier.md` (v3.0.0)
> **真实输出**: `test_output/real_case_crossborder/blackboard/specifier_output.json`
> **诊断视角**: Prompt Engineering 缺陷分析

---

## 诊断结论：根因是「注意力劫持 + Schema 失控」双重失败

**Specifier prompt 的根本缺陷不是"做太多事"，而是 prompt 的注意力分布严重失衡——AC Rubric 占据了 prompt 70% 的篇幅和认知权重，导致 Agent 把所有精力投入到 AC 质量上，完全忽略了其他字段。同时，Agent 甚至没有遵循 prompt 定义的输出 Schema，自行发明了一套新结构。**

具体说：
1. **AC Rubric 劫持了 Agent 的注意力**——prompt 用大量篇幅教 Agent "如何写好 AC"（四级量表、好坏示例、5个特征、3个信号），Agent 确实写出了 58 条高质量 AC，但完全忘记了还要填 budget/complexity/outputs 等字段。
2. **Agent 自行重构了输出 Schema**——prompt 定义 `work_packages[].budget/complexity/model_tier/outputs/context_files/acceptance_tests/requirements`，Agent 输出了 `work_package_specs[].acceptance_criteria`（嵌套对象而非字符串数组），其他字段全部消失。Prompt 的 Schema 约束力为零。
3. **其他字段缺乏同等的注意力权重和可执行指令**——"填 budget"只有一张表和三行说明；"填 outputs"只有一句"从模块职责推导"；"填 requirements"只有一句"从 blueprint 中找到"。这些指令既没有示例，也没有强制校验。

---

## Prompt 问题分析

| # | 问题 | 严重度 | 证据 |
|:---:|------|:---:|------|
| **P1** | **AC Rubric 注意力劫持**：AC 质量指导占 prompt ~70% 篇幅（四级量表+铁律+5好特征+3坏信号+示例），其他 6 个字段合计 ~15% | 🔴 致命 | 实际输出：58 条高质量 AC（72% L3+），但 budget/complexity/outputs/context_files/requirements/acceptance_tests 全部为空。Agent 完美执行了被强调的部分，完全跳过了被忽视的部分 |
| **P2** | **Schema 约束力为零**：prompt 定义了 `work_packages[]` 结构（含 budget/complexity/model_tier 等字段），Agent 输出了完全不同的 `work_package_specs[]` 结构（含 wp_id/source_modules/integration_checkpoint），prompt 定义的字段全部消失 | 🔴 致命 | prompt 输出 Schema: `work_packages[].budget.tokens`, `work_packages[].complexity`, `work_packages[].outputs[]`。实际输出: `work_package_specs[].acceptance_criteria[].ac_id`（嵌套对象结构，prompt 中从未定义） |
| **P3** | **outputs/context_files 信息不足 + 矛盾指令**：prompt 说"从模块职责推导 outputs"，但 blueprint 只有组件级描述（如"API网关层"），没有文件路径。F4 修复又说"禁止幻影引用""只引用已知文件""无法确定就留空数组"——Agent 选择了安全路径：全部留空 | 🔴 高 | blueprint 中没有任何具体文件路径（只有 `technology_stack: ["New API", "Go", "Docker", "PostgreSQL"]`），F4 规则说"禁止引用 docs/xxx.md 等不确定是否存在的文件"，Agent 合理地推断为空数组 |
| **P4** | **budget/complexity/model_tier 缺乏估算锚点**：prompt 给了 simple/medium/complex 的分类表，但没有告诉 Agent 如何从 blueprint 信息推断复杂度。7 个 WP 中哪些是 simple？哪些是 complex？没有判断标准 | 🟠 中 | prompt 的复杂度表：`simple=单文件修改/CRUD`, `medium=多文件协调/第三方集成`, `complex=跨服务事务/性能优化`。但 WP-002（API网关部署）是 simple 还是 complex？没有判断依据 |
| **P5** | **缺少负面示例（"不填就失败"）**：prompt 的自检规则说"所有必填字段是否都有值？"，但没有定义"如果 budget 为空，输出不合格"。没有硬性 gate 条件。Agent 可以在所有元数据字段为空的情况下仍然设置 `self_check.passed: true` | 🟠 中 | 实际输出的 self_check: `{"passed": true, "issues": []}`，但 budget/complexity/outputs/requirements 全空。自检规则没有阻止空字段输出 |
| **P6** | **requirements 关联缺乏映射指引**：prompt 说"从 blueprint.requirements_coverage 中找到该 WP 覆盖的需求"，但 blueprint 的 71 条需求全部标记为 `coverage: "covered"`，没有 REQ→COMP/WP 的映射关系。Agent 无法执行这个指令 | 🟠 中 | blueprint.requirements[] 只有 `{req_id, description, priority, coverage: "covered"}`，没有 `mapped_to: "COMP-001"` 之类的字段。Specifier 无法从输入中推导 REQ→WP 映射 |
| **P7** | **一个 prompt 做 6 件事，无分步执行指令**：prompt 要求同时完成 AC 生成 + 约束传递 + 交付物定义 + 复杂度估算 + 需求关联 + 风险传递，但没有给出分步执行顺序。Agent 自然优先执行最详细指导的任务（AC），跳过最模糊的任务 | 🟠 中 | prompt 的"核心工作"章节有 6 个子任务，但只有第 1 个（生成 AC）有详细的 rubric 和示例，其余 5 个各 3-5 行 |

---

## 具体修复建议

### 修复 1：拆分 prompt 为两阶段（解决 P1 + P7）

**问题**：一个 prompt 同时要求"高质量 AC 创作"和"元数据字段填充"，前者创作性高、后者结构化高，认知模式冲突。

**方案**：拆为 Specifier-AC + Specifier-Meta 两个阶段，或在一个 prompt 中用明确的执行顺序强制分步：

```markdown
## 执行顺序（必须严格按此顺序）

### Step 1: 元数据填充（先做这个，5分钟）
对每个 WP，依次填写：
1. complexity → 参照复杂度判定表
2. budget → 根据 complexity 查表
3. model_tier → 根据 complexity 查表
4. outputs → 从 WP 标题和 source_modules 推导文件路径
5. context_files → 从 dependencies 的上游 outputs 获取
6. requirements → 从 blueprint.requirements 按模块职责匹配
7. acceptance_tests → 将每条 AC 转化为可执行命令

### Step 2: AC 生成（后做这个）
[AC Rubric 内容]

### Step 3: 自检
[自检规则，增加字段非空校验]
```

**原理**：把结构化任务（填表）放在创作性任务（写 AC）之前，利用"先易后难"的认知顺序，确保元数据不被遗忘。

### 修复 2：Schema 强制约束（解决 P2）

**问题**：Agent 无视 prompt 定义的 JSON Schema，自行发明新结构。

**方案**：

```markdown
## 输出 Schema 铁律

你的输出 MUST 严格匹配以下 JSON Schema。任何偏差都是不合格输出。

**禁止**：
- ❌ 使用 `work_package_specs` 代替 `work_packages`
- ❌ 使用 `wp_id` 代替 `id`
- ❌ 将 `acceptance_criteria` 改为嵌套对象数组（必须是字符串数组）
- ❌ 添加 Schema 中不存在的字段（如 `integration_checkpoint`）

**验证方法**：输出前，逐字段对照上方 Schema，确认每个字段名和结构完全一致。
```

### 修复 3：为 outputs/context_files 提供推导规则（解决 P3）

**问题**：prompt 说"推导"但没给推导规则，F4 修复又禁止猜测，Agent 只能留空。

**方案**：提供明确的推导模板：

```markdown
## outputs 推导规则

根据 WP 的 source_modules 和职责描述，使用以下模板推导 outputs：

| 模块类型 | 预期 outputs 模板 |
|---------|------------------|
| API 网关 (COMP-001) | `src/gateway/`, `docker-compose.yml`, `config/routes.yaml` |
| 前端 (COMP-002) | `src/frontend/pages/`, `src/frontend/components/` |
| 支付 (COMP-003) | `src/payment/`, `src/webhooks/` |
| CDN (COMP-004) | `infra/cloudflare/`, `dns/records.yaml` |
| 供应商 (COMP-005) | `src/providers/`, `config/channels.yaml` |
| 监控 (COMP-006) | `config/monitoring/`, `scripts/health_check.sh` |

注意：这些是预期路径模板，Coding Agent 可根据实际项目结构调整。
标注 `[ESTIMATED]` 表示这是推导值而非确定值。
```

### 修复 4：为 budget/complexity 提供判定规则（解决 P4）

**问题**：有分类表但没有判定标准。

**方案**：

```markdown
## complexity 判定规则（逐条检查，满足任一即归类）

**complex**（满足任一）：
- WP 涉及 ≥3 个组件协调
- WP 在关键路径上且 dependencies ≥2
- WP 涉及外部商业协议/支付集成
- WP 标题包含"集成"、"事务"、"优化"

**simple**（满足任一）：
- WP 只涉及 1 个组件
- WP 是纯配置/部署任务（无代码修改）
- WP 标题包含"配置"、"部署"

**medium**（其余情况）：
- 不满足 simple 也不满足 complex
```

### 修复 5：增加硬性 gate 条件（解决 P5）

**问题**：自检规则没有阻止空字段输出。

**方案**：

```markdown
## 自检规则（增加硬性 gate）

在输出前，逐条检查以下条件。**任一不通过 → self_check.passed = false**：

1. **字段非空 gate**：以下字段不允许为空/null/空数组：
   - `budget` → 必须包含 tokens 和 time_minutes
   - `complexity` → 必须是 simple/medium/complex 之一
   - `model_tier` → 必须是非空字符串
   - `outputs` → 至少 1 项（可用 `[ESTIMATED]` 标注）
   - `acceptance_criteria` → 至少 2 条 L3+
   
2. **WP 全覆盖 gate**：wp_structure 中每个 WP 都必须出现

3. **需求关联 gate**：每个 WP 的 requirements 至少包含 1 个 REQ-ID
   （如确实无法关联，标注 `[REQ_GAP]` 但不能为空数组）
```

### 修复 6：为 requirements 关联提供显式映射（解决 P6）

**问题**：blueprint 的 requirements 没有 COMP/WP 映射。

**方案 A（改上游）**：让 Architect Agent 在 blueprint 中为每条 requirement 添加 `mapped_components: ["COMP-001"]`。

**方案 B（Specifier 自行推导）**：

```markdown
## requirements 关联规则

从 blueprint.requirements 中，根据以下关键词匹配 WP：

| WP | 匹配关键词 |
|----|-----------|
| WP-001 | CDN, DNS, SSL, DDoS, WAF, Bot, Cloudflare, ICP |
| WP-002 | 网关, 路由, 故障切换, OpenAI, 兼容, SSE, 计量 |
| WP-003 | 供应商, DeepSeek, Qwen, Zhipu, 通道, 商业协议 |
| WP-004 | 用户, 注册, 登录, API Key, 配额, GDPR |
| WP-005 | 支付, Credit, 订阅, Paddle, Stripe, Webhook |
| WP-006 | 前端, Landing, Dashboard, 文档, Vercel |
| WP-007 | 监控, 告警, UptimeRobot, Telegram, 状态页 |

对每条 requirement，检查 description 中是否包含该 WP 的关键词。
匹配成功 → 写入该 WP 的 requirements 字段。
```

---

## 总结：Prompt 设计的根本性缺陷

| 维度 | 现状 | 应有 |
|------|------|------|
| **注意力分配** | AC Rubric 70%，元数据 15%，格式 15% | AC 40%，元数据 40%，格式 20% |
| **Schema 约束** | 给了 JSON 示例但没有"禁止偏离"指令 | 需要显式 Schema 铁律 + 偏离检测 |
| **推导指引** | "从模块职责推导"（一句话） | 需要推导模板 + 示例 + `[ESTIMATED]` 标注机制 |
| **自检强度** | "是否都有值？"（软性建议） | "为空 = 不合格"（硬性 gate） |
| **任务编排** | 6 个任务平铺，无执行顺序 | 需要分步执行指令（先结构化，后创作性） |

**一句话总结**：Specifier prompt 的 AC 指导写得很好，但它太成功了——Agent 被 AC 质量吸引，忘记了其他一切。修复方向不是"写更多 prompt"，而是**重新平衡注意力分配 + 增加硬性 gate 条件 + 提供可执行的推导规则**。

---

*诊断完成: 2026-06-19*
*方法: Prompt 文本分析 + 输入输出对比 + 注意力分布推断*
