# DeepFlow 按功能模块开发恢复手册 — Part 7: 前端 + 跨域主题 + 文件清单

---

## 9. 前端

### 9.1 status_v2.py — 从JSON渲染报告

frontend/backend/routers/status_v2.py:
- 读取final_result.json
- 提取executive_summary（name, problem_statement, solution_overview）
- 提取detailed_solution.architecture.components
- 渲染为可读markdown格式
- 降级到report.md / final_report.md

原因: 前端需要从final_result.json渲染报告（不再依赖final_solution.md）

---

## 10. 跨域主题

### 10.1 AI Native 原则

核心原则（从讨论中提炼）:
1. 确定性优先: 能用代码做的不用LLM
2. 理解优于穷举: 用语义描述让LLM理解意图
3. 渐进交付: 分阶段实现
4. 不引入外部基础设施: SQLite存储
5. Worker零改动: 绝对红线
6. 代码的角色: 从"写代码"转变为"指导AI、设计规范、验证结果"
7. Karpathy四原则: Think Before Coding → Simplicity First → Surgical Changes → Goal-Driven Execution

忠礼多次强调: 当前做法"不够AI Native"，需要让AI在下意识层面就想到用AI Native方式做事。
搜索了Karpathy Software 3.0、Anthropic、OpenAI、Microsoft、Google 2025-2026 AI Native理念。

### 10.2 命名讨论

决策: 不用"DeepFlow"做产品名（DeepFlow是品牌，需另取名字）
格式: 形容词+动词 或 形容词+名词
不用"Deep"前缀

### 10.3 DeepFlow可观测性系统

作为Ship Pro的真实测试案例:
- 164行observability_requirement.md
- V1: 122 REQ全量 → Ship Pro PASS
- V3: 108 REQ部分去重 → Ship Pro FAIL
- 核心差异: Architect REQ坍塌(122→12)

可观测性系统设计要点:
- 事件协议动态适配（只认协议不认业务结构）
- SQLite存储（WAL模式+幂等写入+OTel兼容）
- Best-effort采集（不阻断管线）
- 数据生命周期: logs 7天/metrics 30天/traces 3天

### 10.4 Loop Engine方向

DeepFlow未来作为Loop Engine:
```
Loop Iteration #1: Spec → Solution → Ship → 运行 → 反馈
Loop Iteration #2: 基于反馈修改Spec → 重新Solution → 重新Ship → ...
```
每次迭代是一个完整的run，需要支持跨迭代的A/B对比。

### 10.5 契约笼子(Contract Cage)

声明-执行-验证方法论:
1. 声明: 定义目标+输入+输出+约束+成功标准
2. 执行: 按声明执行
3. 验证: 用声明验证执行结果

直接按长期方案搞，先专家评审再执行。

### 10.6 专家评审机制

忠礼要求: 按AI Native方式召集专家评审，5-6个不同模型的Agent并行评审。
忠礼批评: 专家评审"很业余"——给专家的提示词太差，发挥空间太小。

产出: docs/research/2026-06-18_expert_reports/ (16个专家报告) + SYNTHESIS V1/V2/V3

### 10.7 Super Loop

super_loop/README.md: Super Loop说明文档（新建）

---

## 11. 恢复优先级文件清单

### P0 — 核心基础设施（必须先恢复）

| # | 文件 | 类型 | 说明 |
|:---|:---|:---|:---|
| 1 | core/config/path_config.py | 修改 | V2 Blackboard方法 |
| 2 | core/orchestrator/pipeline_orchestrator.py | 修改 | summarizer路径 |
| 3 | core/unified_entry.py | 修改 | research_pro注册 |

### P0 — Ship Pro全部（全新域）

| # | 文件 | 类型 |
|:---|:---|:---|
| 4-27 | domains/ship_pro/ 下所有24个文件 | 新建 |

### P1 — Solution Pro管线

| # | 文件 | 类型 |
|:---|:---|:---|
| 28 | domains/solution/blackboard.py | 修改 |
| 29 | domains/solution/completion_handler.py | 修改 |
| 30 | domains/solution/orchestrator_agent.py | 修改 |
| 31 | domains/solution/task_builder.py | 修改 |
| 32 | domains/solution/prompts/summarizer.md | 修改 |
| 33 | domains/solution/prompts/planner.md | 修改 |
| 34 | domains/solution/prompts/consolidator.md | 修改 |
| 35 | domains/solution/prompts/reviewer.md | 修改 |
| 36 | domains/solution/prompts/pipeline_orchestrator.md | 修改 |
| 37 | domains/solution/prompts/orchestrator_completion.md | 修改 |
| 38 | domains/solution/eval/propagation_checker.py | 修改 |
| 39-42 | domains/solution/ 其他修改文件(4个) | 修改 |
| 43-49 | domains/solution/ 新建文件(7个) | 新建 |

### P1 — Spec Pro管线

| # | 文件 | 类型 |
|:---|:---|:---|
| 50 | domains/spec_pro/coordinator.py | 修改 |
| 51-55 | domains/spec_pro/prompts/ (5个) | 修改 |
| 56-59 | domains/spec_pro/ 其他修改文件(4个) | 修改 |

### P2 — 脚本

| # | 文件 | 类型 |
|:---|:---|:---|
| 60 | scripts/pipeline_watcher.py | 修改 |
| 61 | scripts/pipeline_progress_notify.py | 修改 |
| 62 | scripts/start_solution_pro.py | 修改 |
| 63 | scripts/golden_solution_pro_dry_run.py | 修改 |

### P2 — Research Pro（已修复完成，优先级低）

| # | 文件 | 类型 |
|:---|:---|:---|
| 64-76 | domains/research_pro/ 13个修改/新建文件 | 修改+新建 |

### P3 — 评估/文档

| # | 文件 | 类型 |
|:---|:---|:---|
| 77-81 | eval/ (5个文件) | 混合 |
| 82 | QUALITY_GUIDE.md | 新建 |
| 83 | tests/golden/verify_golden_case.py | 新建 |
| 84 | frontend/backend/routers/status_v2.py | 修改 |
| 85-86 | wiki/ (2个文件) | 修改 |
| 87-122 | docs/design/ + docs/research/ (约36个文件) | 新建 |

### 统计

| 类别 | 新建 | 修改 | 总计 |
|:---|:---|:---|:---|
| Ship Pro | 24 | 0 | 24 |
| Solution Pro | 7 | 19 | 26 |
| Spec Pro | 0 | 10 | 10 |
| Research Pro | 7 | 6 | 13 |
| Core | 0 | 3 | 3 |
| Scripts | 1 | 3 | 4 |
| Eval/Quality | 3 | 2 | 5 |
| Frontend | 0 | 1 | 1 |
| Docs | ~36 | 2 | ~38 |
| 其他 | 4 | 2 | 6 |
| **总计** | **~82** | **~48** | **~130** |

---

## 恢复建议

1. **先恢复P0**: path_config.py + pipeline_orchestrator.py + Ship Pro全部（27个文件）
2. **再恢复P1**: Solution Pro + Spec Pro管线的修改文件（29个文件）
3. **最后恢复P2/P3**: 脚本、Research Pro、评估、文档（这些相对独立）
4. **Research Pro**: 修复已完成，如果代码还在可以直接用
5. **Blackboard V2**: 设计完成但代码diff还没apply，可以作为下一步工作
