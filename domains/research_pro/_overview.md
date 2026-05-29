# Research Pro — 深度研究引擎

## 职责
多源搜索 → 分层研究 → 引用验证 → 生成研究报告。

## 入口
- Orchestrator: `orchestrator.py` → `ResearchOrchestrator`

## 代码索引
| 文件 | 职责 |
|------|------|
| orchestrator.py | 主编排器 |
| citation_verifier.py | 引用验证（来源可信度） |
| keyword_generator.py | 搜索关键词生成 |
| source_registry.py | 数据源注册 |
| tier_classifier.py | 分层分类 |

## Prompts
| 文件 | 用途 |
|------|------|
| prompts/citation_verify.md | 引用验证 |
| prompts/finance_analysis.md | 金融分析 |
| prompts/planning.md | 研究规划 |
| prompts/search.md | 搜索执行 |

## 配置
| 文件 | 用途 |
|------|------|
| config/completion_criteria.json | 完成标准 |
| config/tier_domains.json | 分层域定义 |
| config/time_budgets.json | 时间预算 |

## 测试
| 文件 | 说明 |
|------|------|
| tests/test_orchestrator.py | 编排器测试 |
| tests/test_citation_verifier.py | 引用验证测试 |
| tests/test_keyword_generator.py | 关键词测试 |
| tests/test_source_registry.py | 数据源测试 |
| tests/test_tier_classifier.py | 分层测试 |
