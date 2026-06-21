# Ship Pro V3

## 职责
AI Native 多 Agent 协作系统。消费 Solution Pro 输出的 final_result.json，通过 5 个 LLM Agent 协作，生成 ship_package.json（AI Coding 时代的工作包）。

## 架构
```
Architect → Decomposer → Specifier → Reviewer ↔ 反馈闭环 → Packager
```

## 入口
- Orchestrator: `scripts/orchestrator.py` → 准备 run_config.json
- 主 Agent: 按 run_config 中的 execution_order 调用 sessions_spawn

## 代码索引
| 文件 | 职责 |
|------|------|
| `scripts/orchestrator.py` | 编排准备（格式检测 + prompt 加载 + run_config 生成） |
| `scripts/e2e_test.py` | 端到端测试（prepare/validate/report） |
| `scripts/validate_input.py` | 输入验证（格式分类 + 充足性评估） |
| `eval/eval_code_checks.py` | L2 Code-Based Eval（AC 评分 + Schema + 依赖 + 去重） |
| `eval/test_eval_checks.py` | Eval 工具测试（80 项测试） |

## Prompts
| 文件 | Agent | 职责 |
|------|-------|------|
| `prompts/architect.md` | Architect | 架构提取（4 种格式 → 统一 blueprint） |
| `prompts/decomposer.md` | Decomposer | WP 拆分 + 依赖排序 |
| `prompts/specifier.md` | Specifier | AC 生成 + 技术约束传递 |
| `prompts/reviewer.md` | Reviewer | 质量审核 + 结构化反馈 |
| `prompts/packager.md` | Packager | 组装 ship_package + summary |

## Schemas
| 文件 | 用途 |
|------|------|
| `schemas/final_result_v3.schema.json` | 输入 Schema（4 种格式变体） |
| `schemas/ship_package_v3.schema.json` | 输出 Schema（AI Coding WP 结构） |

## 场景契约
- `cage/active/ship_pro_v3.0.yaml`

## 与 DeepFlow 其他模块的关系
- 上游：Solution Pro → final_result.json
- 下游：Super Loop → 消费 ship_package.json
