# Solution Pro — 方案设计引擎

## 职责
10 阶段管线：理解需求 → 并行研究/评审 → 整合审计 → 质量门输出方案。

## 入口
- Orchestrator: `orchestrator_agent.py` → `SolutionOrchestrator`

## 代码索引
| 文件 | 职责 |
|------|------|
| orchestrator_agent.py | 主编排器 |
| task_builder.py | 任务构建 |
| harness_scorer.py | Harness 评分 |
| harness_validator.py | Harness 验证 |
| blackboard.py | Blackboard 管理 |
| planner.py | 规划器 |
| config.py | 配置 |
| security_validator.py | 安全验证 |
| prefix_extractor.py | 前缀提取 |
| check_contract.py | 契约检查 |
| harness_check_expert.py | Harness 专家 |
| progress_tracker.py | 进度追踪 |

## Prompts
| 目录 | 说明 |
|------|------|
| prompts/ | Worker prompts（10+ Stage） |

## 配置
| 文件 | 用途 |
|------|------|
| config/solution.yaml | 域配置 |

## 测试
| 位置 | 说明 |
|------|------|
| tests/ | 域内测试（待补充） |
