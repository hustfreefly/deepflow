# Investment — 投资分析引擎

## 职责
投资研究管线：数据收集 → 多维分析 → 审计 → 投资简报生成。

## 入口
- Orchestrator: `cage_orchestrator.py` → `InvestmentOrchestrator`

## 代码索引
| 文件 | 职责 |
|------|------|
| cage_orchestrator.py | 主编排器（V2.0 PipelineOrchestrator） |

## Prompts
| 目录 | 说明 |
|------|------|
| prompts/ | 多维 Worker prompts（宏观/市场/财务/技术等） |

## 配置
| 文件 | 用途 |
|------|------|
| config/investment.yaml | 数据源配置 |

## 数据源适配器
| 文件 | 说明 |
|------|------|
| core/data/data_providers/investment.py | 投资数据提供者 |

## 测试
| 位置 | 说明 |
|------|------|
| tests/ | 域内测试（待补充） |
