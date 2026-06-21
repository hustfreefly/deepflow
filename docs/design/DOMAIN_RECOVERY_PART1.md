# DeepFlow 按功能模块开发恢复手册

> **生成日期**: 2026-06-21
> **目的**: 为每个子领域提供完整的开发记录，便于恢复和继续开发
> **数据来源**: RECOVERY_DATA.md、CODE_CHANGES_JUNE18_21.md、DISCUSSIONS_JUNE18_21.md、session transcripts

---

## 目录

1. [Ship Pro（代码生成管线）](#1-ship-pro)
2. [Solution Pro（方案设计管线）](#2-solution-pro)
3. [Spec Pro（需求收集管线）](#3-spec-pro)
4. [Research Pro（深度研究）](#4-research-pro)
5. [Blackboard 系统（数据交换层）](#5-blackboard-系统)
6. [Pipeline Watcher（管线监控）](#6-pipeline-watcher)
7. [Core 基础设施](#7-core-基础设施)
8. [评估/质量体系](#8-评估质量体系)
9. [前端](#9-前端)
10. [跨域主题](#10-跨域主题)
11. [恢复优先级文件清单](#11-恢复优先级文件清单)

---

## 1. Ship Pro

### 1.1 概述

**全新域**，GitHub 6月11日版本中完全不存在。6月18-21日期间从零开发。

**定位**: Solution Pro 出方案，Ship Pro 把方案变成"施工图纸"（WP + AC + 工时 + 约束）。作为通用接口中间层。

**核心架构**: 5-Agent 管线，基于 `sessions_spawn` + `sessions_yield` 的 push-based 编排。

```
Depth 0: Main Agent（触发+交付）
  Depth 1: Ship Pro Orchestrator（解析+拆分+组装）
    Depth 2: WP Workers（并行细化）

5 Agent 管线:
Architect → Decomposer → Specifier → Reviewer → Packager
```

**配置**: `maxSpawnDepth: 2`，Workers 用便宜模型。小项目（≤3 WP）自动降级为单 Agent 模式。

### 1.2 源文件清单（24个，全部需要重建）

#### 核心定义
| 文件 | 说明 |
|:---|:---|
| `domains/ship_pro/SKILL.md` | Skill定义：触发流程、断点续接、Pipeline Watcher V2集成 |
| `domains/ship_pro/_overview.md` | 领域概览文档 |

#### prompts/ — Agent Prompts（7个）
| 文件 | 版本 | 说明 |
|:---|:---|:---|
| `prompts/architect.md` | v3.1.0 | 架构师 — Format A/B/C 归一化，YAML frontmatter |
| `prompts/decomposer.md` | v3.0.0 | 分解器 — 架构模块拆成可执行工作包 |
| `prompts/specifier.md` | v3.1.0 | 规格师 — 为WP写验收标准和技术约束 |
| `prompts/reviewer.md` | v3.1.0 | 评审 — 质量审核+领域内去重 |
| `prompts/packager.md` | v3.0.0 | 打包 — 组装标准化输出 |
| `prompts/ship_orchestrator.md` | — | 编排器 Agent Prompt |
| `prompts/cron_watcher.md` | — | Cron Watcher Prompt |

#### scripts/ — 脚本（8个）
| 文件 | 说明 |
|:---|:---|
| `scripts/run_pipeline.py` | 主运行脚本：prepare_pipeline返回spawn_params；V2 watcher配置 |
| `scripts/orchestrator.py` | 编排器：YAML frontmatter；类型注解 |
| `scripts/validate_input.py` | 输入验证：YAML frontmatter；类型注解 |
| `scripts/e2e_common.py` | E2E测试公共模块 |
| `scripts/e2e_prepare.py` | E2E测试准备 |
| `scripts/e2e_report.py` | E2E测试报告生成 |
| `scripts/e2e_test.py` | E2E集成测试 |
| `scripts/e2e_validate.py` | E2E测试验证 |

#### eval/ — 评估（4个）
| 文件 | 说明 |
|:---|:---|
| `eval/eval_code_checks.py` | L2代码检查：CamelCase大小写敏感；EXECUTABLE_SIGNALS扩展 |
| `eval/gates.py` | 质量门控定义 |
| `eval/test_eval_checks.py` | 评估检查测试 |
| `eval/test_gates.py` | 门控测试 |

#### schemas/ — JSON Schema（2个）
| 文件 | 说明 |
|:---|:---|
| `schemas/final_result_v3.schema.json` | V3最终结果Schema |
| `schemas/ship_package_v3.schema.json` | V3 Ship Package Schema |

#### cage/
| 文件 | 说明 |
|:---|:---|
| `cage/active/ship_pro_v3.0.yaml` | Ship Pro V3 Cage配置 |

### 1.3 关键决策

#### D1: Ship Pro 定位确认（6/18）
- **问题**: 忠礼质疑Ship Pro是否"脱裤子放屁"
- **结论**: 保留。Solution Pro出idea/方案（通用），Ship Pro负责方案变施工图纸（编码导向）
- **理由**: Ship Pro作为"通用接口中间层"，不挑输入，负责整合Solution Pro的各种输出

#### D2: Format A/B/C 归一化（6/18）
- **问题**: Solution Pro输出有三种格式变体
  - Format A（final_solution嵌套型）：架构信息在 `final_solution.detailed_solution.architecture`
  - Format B（顶层扁平型）：架构信息在顶层 `architecture`
  - Format C（最小型）：仅元数据
- **结论**: Architect Agent负责格式归一化+架构识别+模块依赖分析
- **备选方案**: 拆出FormatNormalizer作为前置步骤（确定性代码预处理）

#### D3: ENOENT三连修（6/19）
- **Fix-1**: 扩展`prepare_pipeline`的`.replace()`注入`{prompts_dir}`+`{deepflow_root}` → 解决20次ENOENT
- **Fix-2**: orchestrator prompt中增加"读取前先检查存在"的时序保护 → 解决6次ENOENT
- **Fix-3**: 验证逻辑增加"空文件/解析失败→等3秒重试" → 解决4次竞态ENOENT

#### D4: V1 vs V3 对比分析（6/21）
- **核心发现**: V3的REQ从108条坍塌到12条
- **根因**: Summarizer写final_result.json时没传播covered_req_ids；Architect在"信息荒漠"中只能自造12条高层需求
- **结论**: V3的Solution Pro去重（122→108）本身正确，问题在交接文件生成
- **修复**: Summarizer prompt v5.5.0加固REQ传播铁律

#### D5: WP结构AI化（6/20）
- **问题**: 当前WP结构对AI Coding Agent不够友好
- **结论**: 需要从"人类开发者思维"转向"AI Coding Agent思维"
- **核心问题**: outputs/context_files/acceptance_tests全空

#### D6: 信息保真度评审（6/20）
- **三维评估**: 信息增益 + 语义保真度 + 下游可消费性
- **Run A vs Run B**: B形式质量更高（AC L4级100%），但建立在错误前提上
- **结论**: 架构正确性 > 架构复杂度

### 1.4 V3.1.x 迭代记录

| 版本 | 改动 | 验证案例数 |
|:---|:---|:---|
| V3.1.1 | 初始版本 | 4 |
| V3.1.2 | 修复prompt问题 | 4 |
| V3.1.3 | 增加implementation_blueprint字段 | 4 |
| V3.1.4 | 修复打包器问题 | 4 |

### 1.5 待办

- [ ] 24个源文件全部需要重建
- [ ] Architect Prompt加固"REQ忠实传递"约束
- [ ] Packager Schema校验：acceptance_tests和constraints字段非空检查
- [ ] 技术栈锚定：Living Spec中明确指定语言（Python/TypeScript）
- [ ] V3 Ship Pro不应作为基线，需重跑
