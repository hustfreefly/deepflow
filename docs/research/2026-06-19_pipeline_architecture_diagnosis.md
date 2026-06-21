# 管线架构诊断

> **日期**: 2026-06-19
> **分析对象**: Ship Pro V3 管线（跨境AI算力中转站平台测试案例）
> **核心问题**: Specifier Agent 填不满 AI Coding 字段，是 Specifier 的问题还是架构的问题？

---

## 诊断结论：**根因是架构层面的信息流设计问题，不是 Specifier 单点故障**

Specifier Agent 填不满 `budget`、`complexity`、`model_tier`、`context_files`、`outputs`、`acceptance_tests`、`requirements` 这 7 个 AI Coding 字段，**根本原因是这些信息在管线中没有任何 Agent 负责生产**。Specifier 的输入（blueprint + wp_structure）中不包含推导这些字段所需的"实现级"信息，因此 Specifier 只能输出空值。这是信息流断裂，不是 Agent 能力不足。

**一句话总结**：Architect 产出的 blueprint 停留在"架构级"（模块做什么），从未下探到"实现级"（文件在哪、API 长什么样、用什么模型写）。下游所有 Agent 都在信息真空中工作。

---

## 信息流分析

### 逐字段追踪

| 字段 | 信息在输入中有没有 | 谁应该提取 | 当前谁负责 | 差距 |
|------|:---:|------|------|------|
| **`budget`** (token 预算) | ❌ 不存在 | 需要知道代码量和复杂度才能估算 | 无人负责 | 需要"估算"能力，但管线中无 Estimator 角色 |
| **`complexity`** (复杂度) | ❌ 不存在 | 需要从模块职责+技术栈推导 | 无人负责 | Architect 知道技术栈但未评估复杂度；Specifier 没有参照基准 |
| **`model_tier`** (模型选择) | ❌ 不存在 | 依赖 complexity + 成本策略 | 无人负责 | 需要 complexity 先就位，然后才能选模型 |
| **`context_files`** (读什么文件) | ❌ 不存在 | 需要定义项目文件结构 | **应该是 Architect** | Architect 从未定义项目目录结构/文件清单 |
| **`outputs`** (产出什么文件) | ❌ 不存在 | 需要定义每个 WP 的代码产出 | **应该是 Architect 或 Decomposer** | 模块职责→代码文件的映射从未执行 |
| **`acceptance_tests`** (可执行命令) | ⚠️ 部分可推导 | Specifier 可以从 AC 推导 | Specifier 未执行 | AC 文本丰富（55 条），但转化为可执行命令需要知道项目结构和技术栈细节 |
| **`requirements`** (关联需求) | ✅ 存在于输入中 | Architect 有 71 条需求+覆盖证据 | Architect 未传递 | final_result.json 有完整的 REQ→模块映射，但 Architect 输出中只保留了统计数字（71/71=100%），丢失了逐条关联 |

### 信息流断裂点图示

```
final_result.json
  ├── 71 条需求 + 逐条证据          ──→ Architect 只提取了统计数字 ❌ 断裂
  ├── 6 个组件 + 职责 + 技术栈      ──→ Architect 完整提取 ✅
  ├── 数据流 + 依赖关系             ──→ Architect 完整提取 ✅
  ├── 定价模型 + 财务预测           ──→ Architect 提取了定价，丢弃了财务预测 ⚠️
  ├── 实施计划（3 阶段 15 天）      ──→ Architect 提取为 implementation_hints ✅
  └── 项目结构/文件清单             ──→ ❌ 输入中就不存在！

Architect blueprint
  ├── 模块职责（做什么）             ──→ Decomposer 消费 ✅
  ├── 依赖关系                      ──→ Decomposer 消费 ✅
  ├── 技术栈                        ──→ 仅作为标签保留，未下探到实现 ❌
  └── 项目结构/文件清单             ──→ ❌ 从未定义

Decomposer wp_structure
  ├── 7 个 WP + 依赖排序            ──→ Specifier 消费 ✅
  ├── 集成检查点                    ──→ Specifier 消费 ✅
  └── 文件级信息                    ──→ ❌ 上游没给，无法凭空产生

Specifier wp_specs
  ├── 55 条 AC（质量不错，72% L3 级） ──→ ✅ 做得好
  ├── budget/complexity/model_tier    ──→ ❌ 全 null（无信息源）
  ├── context_files/outputs           ──→ ❌ 全空（无信息源）
  ├── acceptance_tests                ──→ ❌ 全空（可从 AC 推导但未执行）
  └── requirements                    ──→ ❌ 全空（上游丢失了映射关系）
```

---

## 关键发现

### 发现 1：Architect 的信息粒度停在"做什么"，从未进入"怎么做"

Architect 输出的模块信息是**功能级**的：
```json
{
  "id": "COMP-001",
  "name": "API网关层",
  "responsibilities": ["多供应商聚合", "智能路由", "自动故障切换<3s", "Token计量计费"],
  "technology_stack": ["New API", "Go", "Docker", "PostgreSQL"]
}
```

但对于 AI Coding Agent 来说，它需要的是**实现级**的信息：
- 项目目录结构是什么？（`src/gateway/router.go`? `src/api/handlers/`?）
- 有哪些关键接口/端点？（`POST /v1/chat/completions`、`GET /v1/models`）
- 数据模型是什么？（User 表、Token 表、API Key 表的 schema）
- 外部依赖的集成点在哪？（New API 的配置文件、Paddle Webhook endpoint）

**这些信息在整条管线中从未被生产。**

### 发现 2：新建项目 vs 已有项目的根本差异未处理

对于**从零开始**的项目（如本案例）：
- `context_files` 天然为空（没有现有代码库）
- `outputs` 需要从零定义（项目结构尚未存在）
- `acceptance_tests` 无法引用还不存在的测试框架

V3 架构设计（SYNTHESIS_V3.md §10.2）定义了这些字段的格式，但**没有区分"新建项目"和"已有项目"两种场景**。对于新建项目，Architect Agent 需要承担额外的"项目骨架设计"职责——定义目录结构、关键文件清单、技术接口规范。

### 发现 3：需求映射在 Architect 环节丢失

final_result.json 中有完整的 71 条需求 + 逐条证据（`requirement_evidence`），但 Architect 输出中只保留了：
```json
"requirements": [
  {"req_id": "REQ-001", "description": "...", "priority": "P1", "coverage": "covered"},
  ...
]
```

所有 71 条都标记为 `priority: "P1"`（未区分 P0/P1），且**没有关联到具体模块**。Reviewer 也指出了这个问题（`severity: low`），但仅标记为低优先级。

这导致 Specifier 无法将 REQ 关联到 WP，`requirements` 字段自然为空。

### 发现 4：Specifier 的"估算"能力缺失

`budget`、`complexity`、`model_tier` 三个字段本质上都是**估算**：
- `complexity`：这个 WP 的实现有多复杂？
- `budget.tokens`：预计消耗多少 token？
- `model_tier`：应该用哪个级别的模型？

这些估算需要：
1. 对代码量的判断（有多少文件、多少行代码）
2. 对技术难度的判断（Go 网关 vs CSS 样式）
3. 对上下文大小的判断（需要读多少文档/代码）

Specifier 当前的 prompt 没有引导它做这类估算，也没有提供参考基准（比如"一个中等复杂度的 Go 模块大约需要 X tokens"）。

### 发现 5：Reviewer 没有检查空字段

Reviewer 输出了 `PASS_WITH_CONDITIONS`，但它的 9 个 issue 全部聚焦于 AC 质量（L2 级别、缺乏量化条件），**完全没有提及 `budget`/`complexity`/`context_files`/`outputs`/`acceptance_tests`/`requirements` 全为空的问题**。

这说明 Reviewer 的审核清单中缺少对 AI Coding 字段的检查项。Reviewer 在审核"AC 写得好不好"，但没有审核"AI Agent 拿到这个 WP 能不能干活"。

---

## 架构改进建议

### 建议 1：增强 Architect Agent 职责，新增"实现蓝图"输出（推荐，优先级 P0）

在 Architect 的 blueprint.json 中新增 `implementation_blueprint` 部分：

```json
{
  "implementation_blueprint": {
    "project_type": "greenfield",
    "project_structure": {
      "root": "crossborder-ai-platform/",
      "directories": [
        "src/gateway/        # API 网关核心（Go）",
        "src/gateway/router.go    # 智能路由逻辑",
        "src/gateway/proxy.go     # 供应商代理+故障切换",
        "src/gateway/metering.go  # Token 计量",
        "src/frontend/       # Next.js 前端",
        "src/frontend/app/        # 页面路由",
        "src/frontend/components/ # 共享组件",
        "src/frontend/lib/        # API 客户端+工具函数",
        "infra/              # 基础设施配置",
        "infra/docker-compose.yml",
        "infra/cloudflare/   # CDN/WAF 规则",
        "docs/               # 文档",
        "docs/api-spec.md    # API 规范",
        "tests/              # 测试"
      ],
      "key_interfaces": [
        {
          "name": "OpenAI 兼容 API",
          "endpoint": "POST /v1/chat/completions",
          "auth": "Bearer API_KEY",
          "features": ["streaming", "model routing"]
        },
        {
          "name": "用户管理 API",
          "endpoint": "New API 内置",
          "auth": "管理后台",
          "features": ["注册", "登录", "API Key 管理"]
        }
      ],
      "data_models": [
        {"name": "User", "key_fields": ["id", "email", "api_key", "balance", "created_at"]},
        {"name": "TokenUsage", "key_fields": ["user_id", "model", "prompt_tokens", "completion_tokens", "cost", "timestamp"]},
        {"name": "Payment", "key_fields": ["user_id", "amount", "type", "status", "provider_txn_id"]}
      ]
    },
    "wp_file_mapping": {
      "WP-001": {"outputs": ["infra/cloudflare/"], "context_files": []},
      "WP-002": {"outputs": ["src/gateway/", "infra/docker-compose.yml"], "context_files": ["docs/api-spec.md"]},
      "WP-003": {"outputs": ["src/gateway/providers/"], "context_files": ["src/gateway/router.go"]},
      "WP-004": {"outputs": ["src/gateway/auth/", "src/gateway/metering.go"], "context_files": ["src/gateway/"]},
      "WP-005": {"outputs": ["src/frontend/app/checkout/", "src/frontend/lib/payment.ts"], "context_files": ["src/frontend/"]},
      "WP-006": {"outputs": ["src/frontend/app/", "src/frontend/components/"], "context_files": ["src/frontend/lib/"]},
      "WP-007": {"outputs": ["infra/monitoring/"], "context_files": []}
    }
  }
}
```

**实现方式**：
- 修改 Architect Agent 的 prompt，增加"实现蓝图"生成步骤
- 要求 Architect 基于模块职责推导项目结构、关键接口、数据模型
- 要求 Architect 为每个模块标注预期的代码文件路径

**注意**：这些信息对 LLM 来说是可推导的——给定"New API + Go + Docker + PostgreSQL"的技术栈和模块职责，一个有能力的 Architect 可以输出合理的项目骨架。关键是**要在 prompt 中明确要求**。

### 建议 2：Specifier 增加"估算 + 映射"步骤（P0）

在 Specifier 的工作流中增加两个强制步骤：

**步骤 A：需求映射**
- 输入：Architect 的 71 条需求（需恢复逐条关联）
- 工作：将每条 REQ 关联到对应的 WP
- 输出：每个 WP 的 `requirements` 字段

**步骤 B：复杂度估算 + 模型选择**
- 输入：WP 的 AC 数量 + 技术栈 + 文件范围
- 工作：基于简单启发式规则估算复杂度
- 参考基准：
  - AC ≤ 5 条 + 配置类 → complexity: "low", model_tier: "sonnet"
  - AC 6-8 条 + 单语言 → complexity: "medium", model_tier: "opus"
  - AC > 8 条 + 多语言/多集成 → complexity: "high", model_tier: "opus"
- 输出：`complexity`、`model_tier`、`budget`

**步骤 C：可执行测试生成**
- 输入：AC 文本 + 项目结构
- 工作：将 AC 转化为可执行的测试命令或脚本描述
- 输出：`acceptance_tests`

### 建议 3：区分"新建项目"和"已有项目"模式（P1）

在 Ship Pro Orchestrator 中增加项目类型判断：

| 维度 | 新建项目 (greenfield) | 已有项目 (brownfield) |
|------|---------------------|---------------------|
| `context_files` | 空（无现有代码） | 由 Architect 扫描代码库提取 |
| `outputs` | 由 Architect 定义项目骨架 | 由 Architect 定位需修改的文件 |
| Architect 额外职责 | 设计项目结构 + 接口规范 | 分析现有代码 + 识别修改点 |
| Specifier `acceptance_tests` | 基于 curl/CLI 的外部测试 | 可引用现有测试框架 |

### 建议 4：Reviewer 增加"AI Coding 可用性"审核维度（P1）

在 Reviewer 的审核清单中新增：

```
□ 每个 WP 的 context_files 是否非空？（或新建项目有合理说明）
□ 每个 WP 的 outputs 是否非空？
□ 每个 WP 的 budget/complexity/model_tier 是否已填写？
□ 每个 WP 的 acceptance_tests 是否至少有一条可执行命令？
□ 每个 WP 的 requirements 是否至少关联一条 REQ？
□ AI Agent 拿到这个 WP，能否不依赖额外信息就开始工作？
```

### 建议 5：反馈闭环自然修复（P2，自动生效）

如果建议 1-4 落地，反馈闭环将自然发挥作用：
- Reviewer 发现空字段 → 反馈给 Specifier
- Specifier 发现缺少项目结构信息 → 反馈给 Architect
- Architect 补充实现蓝图 → Specifier 重新填充

但如果建议 1-4 不落地，反馈闭环**无法修复这个问题**——因为 Reviewer 自己也不知道该填什么。

---

## 是否建议增加 Agent

### 结论：**不需要增加 Estimator Agent**

| 候选方案 | 优点 | 缺点 | 判定 |
|---------|------|------|:---:|
| 新增 Estimator Agent | 职责专一 | 增加管线复杂度+延迟+token 成本；估算依赖上下文信息，Estimator 同样面临信息不足问题 | ❌ |
| Architect 扩展职责 | 信息源头解决；Architect 已有技术栈+模块职责，推导复杂度/文件结构最自然 | Architect prompt 更复杂 | ✅ 推荐 |
| Specifier 扩展职责 | 估算结果更贴近 AC 细节 | Specifier 缺乏全局视角 | ⚠️ 部分推荐 |

**推荐方案**：
- **complexity / model_tier / budget** → 由 Architect 在 `implementation_blueprint` 中提供模块级估算，Specifier 细化到 WP 级
- **context_files / outputs** → 由 Architect 定义（它最了解技术栈和模块划分）
- **acceptance_tests** → 由 Specifier 生成（它最了解 AC 细节）
- **requirements** → 由 Architect 传递原始映射，Specifier 细化关联

这样不需要新增 Agent，只需要**让 Architect 多做一些事**。

---

## 总结：三层修复策略

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: 信息源修复（Architect 增强）                            │
│  ├── 新增 implementation_blueprint（项目结构+接口+数据模型）       │
│  ├── 恢复 REQ→模块 逐条映射                                      │
│  └── 新增 wp_file_mapping（WP→文件路径映射）                      │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: 消费端修复（Specifier 增强）                            │
│  ├── 强制步骤：需求映射（REQ→WP）                                │
│  ├── 强制步骤：复杂度估算 + 模型选择                              │
│  ├── 强制步骤：AC→可执行测试转化                                  │
│  └── 新建项目模式下 context_files 可为空但 outputs 必须有值        │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3: 验证端修复（Reviewer 增强）                             │
│  ├── 新增"AI Coding 可用性"审核维度                              │
│  ├── 空字段 = 自动 FAIL（不是 condition）                        │
│  └── 最终检验：AI Agent 拿到 WP 能否直接开工？                    │
└─────────────────────────────────────────────────────────────────┘
```

**核心洞察**：问题不在 Specifier 一个 Agent，而是整条管线的信息粒度不够。Architect 产出的 blueprint 是"给人看的架构文档"，不是"给 AI 用的执行规格"。需要将 blueprint 从"架构级"下沉到"实现级"，才能让下游所有 Agent 受益。

---

*诊断完毕。建议优先实施 Layer 1（Architect 增强），这是信息流的源头，修复后 Layer 2 和 Layer 3 的问题会大幅减少。*
