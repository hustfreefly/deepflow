# 第三轮评审报告：开发者体验专家

> **评审人**: 开发者体验专家（首次接触此方案）  
> **评审日期**: 2026-06-25  
> **评审对象**: V3 方案 + 当前 SKILL.md V3.2  
> **评审视角**: 一个普通 Agent 首次执行此方案时的体验

---

## 总评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **总评分** | **7/10** | 方案完整度高，但首次执行者面临信息过载和若干模糊地带 |
| SKILL.md 可读性 | 7/10 | 当前 SKILL.md 极简（仅 30 行），V5.0 设计未给出完整草稿 |
| Prompt 清晰度 | 7/10 | Orchestrator Prompt 结构清晰，但有几处歧义会导致卡住 |
| 调试体验 | 7/10 | dump-state + resume-context + decisions.jsonl 提供了可观测性，但缺少"出错第一步查什么"的指引 |
| 文档架构 | 7/10 | 章节组织合理，但方案本身 500+ 行，实施时需要拆分而非单文件 |

**核心判断**: 方案作为设计文档合格，但作为执行指南信息密度过高——一个首次执行的 Agent 需要同时理解 16 个命令、5 层流程、3 种验证机制，缺少"快速上手路径"。

---

## 发现的问题

### P0

| # | 问题 | 说明 | 建议 |
|---|------|------|------|
| P0-1 | **SKILL.md V5.0 没有完整草稿** | §7 改造清单说"写 SKILL.md V5.0（含入口守卫）"，但方案中只给了 §8.2 入口守卫片段和 §5.1 Orchestrator Prompt。实施者不知道 SKILL.md 最终长什么样——是把整个 §5.1 搬进去？还是精简版？当前 SKILL.md 仅 30 行，改造跨度太大，没有过渡 | 方案中应包含 SKILL.md V5.0 的完整目录结构 + 关键章节草稿（至少入口守卫 + 快速开始 + 命令速查表） |
| P0-2 | **Orchestrator Prompt 中 `build-prompt` 的调用时序不清晰** | §5.1 Phase 3 Step 1 说 `build-prompt <stage> <output_dir> --context-file <path>`，但 `<path>` 从哪来？Orchestrator 需要先 `echo '{...}' > /tmp/ctx-<stage>.json` 写临时文件，但这一步在 prompt 中没有明确写出。首次执行的 Agent 可能直接传 `--context` 字符串（V1 遗留习惯）导致报错 | 在 Phase 3 Step 1 增加明确的子步骤：① 写 context JSON 到临时文件 ② 调用 build-prompt 传入路径。给出完整示例 |

### P1

| # | 问题 | 说明 | 建议 |
|---|------|------|------|
| P1-1 | **缺少"快速开始"路径** | 方案 500+ 行，首次执行者需要通读全文才能开始工作。没有一个"5 分钟上手"的摘要路径 | 在文档开头增加 TL;DR 或 Quick Start：3-5 步概括核心流程，链接到详细章节 |
| P1-2 | **错误恢复策略菜单缺少决策树** | §5.1 的错误恢复是一个表格（7 行），但 Agent 需要的是一个决策流程：先判断什么 → 再判断什么 → 最终选哪个策略。表格形式需要 Agent 自行匹配，增加认知负担 | 将表格转换为 if-else 决策树或流程图（ASCII），让 Agent 逐步判断即可 |
| P1-3 | **`compact-history` 调用时机可能引起困惑** | "每完成 2 个阶段后调用一次"——如果 Orchestrator 自创了 8 个阶段，是第 2、4、6、8 阶段后各调用一次？还是累计完成 2 个后调用？另外，如果 compact 后发现自己需要之前的细节怎么办？ | 明确：每完成 N 个阶段（建议 N=2）调用一次。补充"compact 后如需回顾细节，用 read 命令直接读 blackboard 文件" |
| P1-4 | **Judge Worker 的 prompt 没有模板** | §5.1 Phase 4 给出了 Judge Worker 的 spawn 代码，但 task 内容是 `"你是 Ship Package 质量 Judge。请评估以下 Ship Package 是否满足 Living Spec 的要求：..."`，省略号部分没有给出模板。首次执行者不知道 Judge 需要哪些输入、输出什么格式 | 给出 Judge Worker 的完整 prompt 模板（类似 §5.2 Worker Prompt 模板），包含输入注入方式和输出 schema |
| P1-5 | **`validate-quality` 的 gate_fn 实现未给出** | 方案说"调用保留的 Python gate 函数（gate_architect, gate_decomposer 等）"，但这些函数的具体实现（检查什么、怎么算 pass）在方案中完全没提。实施者需要去 `run_pipeline.py` 里找，增加了上手成本 | 至少在方案中列出每个 gate_fn 的检查项清单（如 gate_architect: ① 模块数 ≥ 3 ② 无循环依赖 ③ 架构原则数 ≥ 2） |
| P1-6 | **并行执行的 sessions_yield 语义仍需注意** | 虽然 §5.1 说"一次 sessions_yield() 即可等待全部完成"，但如果并行 3 个 Worker，auto-announce 会逐个通知。Orchestrator 怎么知道"全部完成了"再进入验证步骤？缺少明确的"等待全部完成"的判断标准 | 补充说明：Orchestrator 收到所有并行 Worker 的 auto-announce 后（通过 label 匹配），再统一进入验证步骤。或建议默认串行以降低复杂度 |

### P2

| # | 问题 | 说明 | 建议 |
|---|------|------|------|
| P2-1 | **方案文档过长（500+ 行）** | 单文件包含背景、设计原则、io_helper 详细设计、依赖图、Prompt、可靠性、改造清单、迁移策略、评审追踪，信息密度高但阅读成本也高 | 实施阶段拆分为：① 设计概述（§1-2） ② io_helper 实现规格（§3-4） ③ Prompt 合集（§5） ④ 实施指南（§6-8） |
| P2-2 | **`log-decision` 的参数格式不明确** | §3.1 说 `log-decision` 接受 `timestamp, type, stage, reason, outcome`，但 §5.1 Phase 2 调用示例是 `log-decision <output_dir> plan "<计划摘要>"`，参数位置和数量不一致 | 统一：给出 `log-decision` 的完整 CLI 签名和各参数说明 |
| P2-3 | **`.heartbeat` 写入方式过于原始** | 用 `echo '...' > .heartbeat` 写入，没有通过 io_helper 封装。如果 Orchestrator 忘记写或格式写错，没有校验 | 考虑增加 `io_helper.py write-heartbeat <output_dir> <stage> <status>` 命令，保持一致性 |
| P2-4 | **回滚 SOP 步骤 4-5 描述模糊** | "pipeline_state.json 增加 version 标记"、"V4 prepare_pipeline --resume 模式：不清理已有阶段输出"——V4 的 resume 模式是否已存在？如果不存在，回滚 SOP 本身就依赖新功能 | 确认 V4 resume 模式现状，如果不存在，回滚 SOP 需要额外步骤 |
| P2-5 | **§5.2 Worker Prompt 模板中 `{orchestrator_quality_criteria}` 来源不清** | 这个占位符由 Orchestrator 通过 `--context-file` 提供，但 Orchestrator 怎么知道每个阶段的质量标准？是固定的还是动态生成的？ | 补充：质量标准的来源（从 stage-dependencies.json 读取？Orchestrator 自行生成？从 Living Spec 提取？） |

---

## V3 修复评估（从开发者体验角度）

### 修复得好的

| 修复项 | 评价 |
|--------|------|
| cwd 改用 `$DEEPFLOW_HOME` | ✅ 可移植性提升，首次执行不会因为路径不对而失败 |
| `--context-file` 替代 `--context` | ✅ 避免命令行长度问题，但需要补充写文件的步骤说明 |
| 入口守卫增加 `maxSpawnDepth` 检查 | ✅ 防止配置不对导致 spawn 失败，好的防错设计 |
| compact-history 保留最近 2 阶段失败细节 | ✅ 防止重复踩坑，对调试体验有直接帮助 |
| resume-context 文件扫描自动修正 | ✅ 减少"状态不一致"导致的困惑 |
| Judge 与 Python gate 交叉验证 | ✅ 给 Orchestrator 明确的判断规则，减少歧义 |

### 仍需关注的

| 问题 | 影响 |
|------|------|
| SKILL.md V5.0 没有完整草稿 | 实施者需要自行组织文档结构，可能偏离设计意图 |
| 首次执行路径不清晰 | 500+ 行文档，没有"先看这里"的引导 |
| 错误恢复是表格不是决策树 | Agent 需要额外推理才能选择正确策略 |

---

## 是否可以进入实施阶段？

- [x] **有条件进入**（修复 P0 后可进入）
- [ ] 需要第四轮

### 进入实施的条件

1. **P0-1**: 补充 SKILL.md V5.0 完整目录结构 + 关键章节草稿
2. **P0-2**: 补充 `build-prompt` 调用时序的完整子步骤示例

### 建议实施顺序（从开发者体验角度）

1. 先实现 `io_helper.py` 的 16 个命令 + 单元测试（可独立验证）
2. 写 `stage-dependencies.json`
3. 写 SKILL.md V5.0 完整草稿（含入口守卫 + 快速开始 + 命令速查）
4. 写 Orchestrator Prompt（基于 §5.1，补充 P0/P1 修复）
5. 更新 `start_ship_pro.py`
6. 端到端测试

---

*评审完成。总体评价：方案成熟度高，V2→V3 的 17 个 P2 修复全部到位。从开发者体验看，主要瓶颈是"信息量大 + 缺少快速上手路径"。修复 2 个 P0 后即可进入实施。*
