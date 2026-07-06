# 跨域压力测试：投资分析场景（VC 尽调方案）

> Agent D | 模型: kimi-for-coding | 耗时: ~6min

## 测试场景
散热材料公司 A 的 VC 尽调方案（专利分析/技术壁垒/市场竞争/核心团队/财务健康度）

## 端到端通过率评估：**~12%**（几乎不可用）

## 障碍汇总

### Step 1: Living Spec — 5 个障碍
| # | 严重度 | 障碍 |
|---|--------|------|
| 1.1 | MAJOR | `objective` 无法表达投资尽调的分析目标和判断标准 |
| 1.2 | MAJOR | `capabilities` always/should/never 不适合投资尽调的分析维度 |
| 1.3 | MAJOR | `quality_attributes` 无投资分析质量维度（尽调覆盖率/数据可靠性/估值方法适用性） |
| 1.4 | CRITICAL | 缺少投资分析专用字段（patent_portfolio/competitive_moat/team_assessment/financial_due_diligence） |
| 1.5 | MINOR | `integration` 无法表达数据源整合（专利数据库/财报/行业报告） |

### Step 2: Meta-Planner — 5 个障碍
| # | 严重度 | 障碍 |
|---|--------|------|
| 2.1 | 🔴 CRITICAL | `DOMAIN_CATEGORIES` Literal 无 "investment_analysis" |
| 2.2 | 🔴 CRITICAL | `EXPERT_TEMPLATE_REGISTRY` 无投资分析专家（专利律师/材料科学家/行业分析师/财务审计师） |
| 2.3 | 🔴 CRITICAL | meta_planner.md 三个示例全软件，LLM 会输出不合适的专家 |
| 2.4 | MAJOR | Gate B 检查项全软件（OWASP/API/OpenAPI） |
| 2.5 | MAJOR | P0 约束识别维度面向软件（平台/业务/技术），缺少"法规/市场/财务"维度 |

### Step 3: Expert Planners — 4 个障碍
| # | 严重度 | 障碍 |
|---|--------|------|
| 3.1 | MAJOR | 约束示例全软件（TLS/HTTPS/PostgreSQL），投资约束应为"专利有效期≥5年" |
| 3.2 | MAJOR | verification_method 面向软件命令 |
| 3.3 | MAJOR | 专家示例全软件（security/performance/data_architect） |
| 3.4 | MINOR | 投资分析的验收标准格式不同（"专利覆盖率≥80%"而非"API响应<200ms"） |

### Step 4: Research — 5 个障碍
| # | 严重度 | 障碍 |
|---|--------|------|
| 4.1 | 🔴 CRITICAL | "15次web_search"搜索方向全软件 |
| 4.2 | 🔴 CRITICAL | "具体技术名称+版本号"不适合投资（需要专利号+财务数据+市场份额） |
| 4.3 | MAJOR | `technology_recommendations` 字段名语义偏差（应为 `investment_recommendations`） |
| 4.4 | MAJOR | Finding 模板缺少"数据来源可信度"维度（专利数据库 vs 公司自述 vs 第三方报告） |
| 4.5 | MINOR | research_planner 示例全软件 |

### Step 5: Summary — 5 个障碍
| # | 严重度 | 障碍 |
|---|--------|------|
| 5.1 | 🔴 CRITICAL | 输出模板完全面向软件架构 |
| 5.2 | 🔴 CRITICAL | "技术选型必须有具体版本号"语义错位 |
| 5.3 | MAJOR | 投资报告结构应为：执行摘要→公司概览→专利分析→技术壁垒→市场格局→团队评估→财务分析→风险→投资建议 |
| 5.4 | MAJOR | Review Layer B 不含"投资逻辑验证"维度 |
| 5.5 | MAJOR | 缺少估值方法论和敏感性分析模块 |

### Step 6: 输出 Schema — 多个 CRITICAL
- ArchitectureSchema/DetailedDesignSchema 完全无法表达投资分析报告

## 统计
- CRITICAL: 7
- MAJOR: 12
- MINOR: 5
