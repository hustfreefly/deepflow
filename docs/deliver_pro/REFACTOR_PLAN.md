# Deliver Pro 重构方案 — 4 专家联合复盘

> **日期**: 2026-07-28
> **专家团**: 架构对比 / 稳健性分析 / 公共组件整合 / Prompt 系统
> **结论来源**: 4 份独立分析报告

---

## 📊 总览：Deliver Pro 现状评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 调度架构 | ⭐⭐⭐⭐ | 双路径（Agent + Python Pulse）合理，多 WP DAG 调度必需 |
| 状态管理 | ⭐⭐⭐⭐⭐ | "derive, don't sync" 是最佳实践，无状态漂移风险 |
| 容错能力 | ⭐⭐⭐⭐ | Pulse 调度 V1 覆盖核心场景，82% 自主完成率 |
| 代码质量 | ⭐⭐⭐ | 有 DEPRECATED 代码未清理、20+ 处原子写重复 |
| Prompt 体系 | ⭐⭐⭐⭐ | 轻量设计优于 Solution Pro 的重型 prompt，但缺共享规则 |
| 公共组件复用 | ⭐⭐⭐ | 独立实现较多，与 Solution Pro 有大量可整合空间 |

---

## 🔑 核心结论

### 1. 双路径设计是正确的，不需要改成 Solution Pro 的纯 Agent 模式

| 因素 | Solution Pro | Deliver Pro |
|------|-------------|-------------|
| 工作单元 | 固定 3 模块 | 动态 N 个 WP（1-20+） |
| 依赖关系 | 固定线性 | DAG 依赖（需拓扑排序） |
| 执行时长 | 20-40 min | 10-120+ min |
| 并发需求 | 模块内并行 | 跨 WP 并行 + 全局在途上限 |

**结论**: Deliver Pro 的多 WP DAG 依赖 + 长时间运行 + 并发控制，决定了纯 Agent 模式不可行。双路径不是过度设计。

### 2. 最大浪费：20+ 处原子写重复 + 铁律在 prompt 中重复 5-6 次

- 原子写 JSON 在 7+ 文件中出现 20+ 次，实现微妙不同
- Deliver Pro 缺少 `_shared_subagent_rules.md`，铁律在每个 prompt 中重复

### 3. 最大断头路：failure_recovery.py 设计完善但从未被 Pulse 模式调用

- 模块设计了 LLM 诊断 + 策略历史 + 启发式降级
- 但 Pulse 调度走的是 `_prepare_worker_retries`（直接重派），不经过 LLM 诊断
- 重试是"盲重派"而非"诊断后重派"，成功率低

### 4. Deliver Pro 的 "derive, don't sync" 模式比 Solution Pro 的显式状态更先进

- Solution Pro 的 `master_state.json` 有状态漂移风险
- Deliver Pro 从文件系统推导 phase，天然支持断点续跑
- **建议**: Solution Pro 应借鉴此模式

---

## 🎯 重构路线图

### Phase 0: 基础设施提取（P0，1-2 天）

| 行动 | 收益 | 风险 |
|------|------|------|
| 创建 `core/utils/atomic_io.py` | 消除 20+ 处重复（~200 行→60 行模块） | 极低 |
| 创建 `deliver_pro/prompts/_shared_subagent_rules.md` | 消除 5-6 个 prompt 的铁律重复，减少 ~30% token | 低 |
| 归档 `deliver_orchestrator.md` 到 `_archive/` | 消除与 `deliver_pulse.md` 的架构冲突 | 极低 |

### Phase 1: 替换原子写 + 精简 Prompt（P1，3-5 天）

| 行动 | 收益 | 风险 |
|------|------|------|
| 逐文件替换原子写为 `atomic_io` 调用 | 统一实现，bug 修复 7x→1x | 中低 |
| Deliver Pro 每个 prompt 删除重复铁律，改为引用共享规则 | prompt 体积减少 30% | 低 |
| 删除 `state_manager.py`（DEPRECATED） | 消除 224 行死代码 | 低 |

### Phase 2: 接入故障诊断 + 统一 Pulse 契约（P1，1 周）

| 行动 | 收益 | 风险 |
|------|------|------|
| 将 failure_recovery 接入 pulse 重试路径（第 2 次重试触发 LLM 诊断） | 重试成功率从 ~30% 提升到 ~60% | 中 |
| 创建 `core/blackboard/pulse_contracts.py`（BasePulseAlert/SpawnConfirmation） | 统一 Pulse 接口，新 Pro 域模板代码减少 50% | 低 |
| 信息守恒硬门禁：semantic_anchors 丢失率 > 50% → validate auto FAIL | 防止交付丢失核心决策依据的文档 | 低 |

### Phase 3: 增强自主完成能力（P2，1-2 周）

| 行动 | 收益 | 风险 |
|------|------|------|
| Worker heartbeat 机制（定期 touch .heartbeat → 活性检测替代盲等） | 大任务超时判定从"盲等"变为"活性检测" | 中 |
| Package 失败分级（区分可重试/不可重试） | 减少因临时错误导致的 terminal_failed | 低 |
| 复用 `core.quality_utils` | 消除重复实现，统一阈值 | 低 |
| 循环依赖告警升级为 CRITICAL | 提高可观测性 | 低 |

### Phase 4: 长期演进（P3，1-2 月）

| 行动 | 收益 | 风险 |
|------|------|------|
| Solution Pro 引入 derive 模式 | 消除 master_state.json 漂移风险 | 高 |
| 统一 Pulse Scheduler 框架 | 两域共享 pulse 基础设施 | 高 |
| 评估 DeliverProBlackboard → core.BlackboardManager 迁移 | 统一 Blackboard API | 高 |
| 提取 `core/utils/prompt_loader.py` | 新 Pro 域可复用 | 低 |

---

## 📋 重构原则

1. **不改调度架构** — 双路径是正确的，保持 Agent + Python Pulse
2. **提取公共基础设施** — 原子写、Pulse 契约、共享规则提到 core 层
3. **接入已有模块** — failure_recovery.py 已设计好，接入即可
4. **对标 Solution Pro 的质量保障** — 信息守恒硬门禁、后置验证持久化
5. **保持 derive, don't sync** — 这是 Deliver Pro 最先进的模式，不要回退

---

## 📈 预期收益

| 指标 | 当前 | 重构后 |
|------|------|--------|
| 代码行数 | ~5630 行 | ~5266 行（净减 364 行） |
| 原子写 bug 修复点 | 7+ 文件 | 1 文件 |
| Prompt token 浪费 | 铁律重复 5-6 次 | 共享规则引用 |
| 自主完成能力 | 82% | ~90%（接入故障诊断 + heartbeat） |
| 新 Pro 域模板代码 | 从零搭建 | 减少 50% |

---

## 📁 详细报告索引

| 报告 | 路径 |
|------|------|
| 架构对比分析 | `.deepflow/docs/deliver_pro/architecture_comparison.md` |
| 稳健性分析 | `.deepflow/docs/deliver_pro/robustness_analysis.md` |
| 公共组件整合方案 | `.deepflow/docs/deliver_pro/component_integration_plan.md` |
| Prompt 体系分析 | `.deepflow/docs/deliver_pro/prompt_system_analysis.md` |
