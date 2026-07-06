# Solution Pro V2 泛化性深度审计计划

> Goal: 检查 Solution Pro V2 在 Prompt/Schema/Flow/Input/Output 五维度的泛化性
> 日期: 2026-07-07
> 方法: 多轮、多Agent、多模型、多角度

---

## 审计维度（5 个）

| # | 维度 | 核心问题 | 审计方法 |
|---|------|---------|---------|
| D1 | **Prompt 泛化性** | Prompt 中是否有软件开发领域的硬编码假设？ | 全量 prompt 扫描 + 泛化评分 |
| D2 | **Schema 泛化性** | Pydantic Schema 字段是否假设了软件开发的特有概念？ | Schema 字段语义分析 |
| D3 | **Flow 泛化性** | 三阶段管线（Planning→Research→Summary）是否通用？ | 架构分析 + 跨域场景模拟 |
| D4 | **Input 泛化性** | Living Spec / Frozen Spec 格式是否通用？ | 输入契约分析 + 非软件域适配测试 |
| D5 | **Output 泛化性** | 输出格式（final_solution）是否通用？ | 输出 Schema + 跨域适用性评估 |

---

## 执行计划（4 轮）

### Round 1: 代码级静态审计（并行 3 Agent）
**目标**: 从代码和 Prompt 中提取所有"领域耦合点"

| Agent | 职责 | 审计范围 |
|-------|------|---------|
| A: Prompt 审计员 | 扫描所有 Solution Pro prompt | 30+ prompt 文件，识别硬编码领域术语 |
| B: Schema 审计员 | 扫描所有 Schema/Contract | schemas.py + contracts/ + frozen_spec.py |
| C: Code 审计员 | 扫描核心编排代码 | master/planning/research/summary orchestrator + convergence |

**产出**: `round1_findings.json` — 领域耦合点清单

### Round 2: 跨域场景压力测试（并行 3 Agent，不同模型）
**目标**: 用 3 个非软件域场景测试系统泛化性

| Agent | 场景 | 模型 |
|-------|------|------|
| D: 投资分析场景 | VC 尽调方案设计 | kimi/kimi-for-coding |
| E: 硬件产品场景 | 散热模组设计方案 | bailian2/qwen3.7-max |
| F: 商业策略场景 | 市场进入策略 | bailian2/kimi-k2.6 |

**方法**: 构造 Living Spec 输入 → 模拟通过 Solution Pro → 检查每层输出是否合理
**产出**: `round2_domain_tests.json` — 每个场景的泛化性评分 + 问题清单

### Round 3: 架构级深度评审（2 Agent 独立评审）
**目标**: 从架构设计层面评估泛化性

| Agent | 评审角度 |
|-------|---------|
| G: AI Native 架构师 | 三层管线是否为通用"方案设计"范式？哪些步骤是软件开发特有的？ |
| H: 系统工程专家 | 收敛层/Gate/信息守恒是否通用？哪些机制绑定了特定领域？ |

**产出**: `round3_architecture_review.json`

### Round 4: 综合报告 + 改进方案
**目标**: 整合前三轮发现，产出可操作改进清单

**整合方法**:
- 汇总所有发现 → 按严重度分类（CRITICAL / MAJOR / MINOR）
- 交叉验证：多个 Agent 独立发现的问题权重更高
- 产出具体的改进建议（代码级 + Prompt 级 + 架构级）

**最终产出**: `FINAL_REPORT.md`

---

## 测试场景

### 场景 1: 投资分析（VC 尽调方案设计）
- **输入**: "为散热材料公司 A 设计 VC 尽调方案，需覆盖专利分析、技术壁垒、市场竞争、团队评估"
- **预期输出**: 尽调框架 + 分析维度 + 数据采集计划 + 风险评估

### 场景 2: 硬件产品（散热模组设计）
- **输入**: "为新一代 GPU 服务器设计散热模组方案，需满足 TDP 450W、噪音 < 55dB、成本 < $200"
- **预期输出**: 热设计方案 + 材料选择 + 仿真计划 + 供应链方案

### 场景 3: 商业策略（市场进入）
- **输入**: "为 AI Agent 平台设计进入日本市场的策略方案，需考虑合规、本地化、渠道、竞品"
- **预期输出**: 市场分析 + 进入路径 + 合规方案 + 财务预测

---

## 评判标准

### 泛化性评分（1-10）

| 分数 | 含义 |
|------|------|
| 9-10 | 完全通用，无需修改即可适配任意领域 |
| 7-8 | 基本通用，少量术语需替换 |
| 5-6 | 部分通用，核心逻辑可用但需大量适配 |
| 3-4 | 领域绑定严重，仅核心框架可复用 |
| 1-2 | 完全绑定软件开发，无法泛化 |

### 问题严重度

| 级别 | 含义 | 处理 |
|------|------|------|
| CRITICAL | 阻止系统在其他领域运行 | 必须修复 |
| MAJOR | 严重影响其他领域的输出质量 | 强烈建议修复 |
| MINOR | 术语/示例级别的领域绑定 | 可选修复 |

---

## 文件结构

```
.deepflow/audit/solution-pro-generalizability/
├── PLAN.md                          ← 本文件
├── round1/
│   ├── prompt_audit.json            ← Agent A 产出
│   ├── schema_audit.json            ← Agent B 产出
│   └── code_audit.json              ← Agent C 产出
├── round2/
│   ├── investment_analysis.json     ← Agent D 产出
│   ├── hardware_product.json        ← Agent E 产出
│   └── business_strategy.json       ← Agent F 产出
├── round3/
│   ├── architecture_review_1.json   ← Agent G 产出
│   └── architecture_review_2.json   ← Agent H 产出
└── FINAL_REPORT.md                  ← 综合报告
```

---

*2026-07-07 | 小满 制定*
