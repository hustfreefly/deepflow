# 三方专家评审综合报告

> **日期**: 2026-07-07 | **评价**: CONDITIONAL（修复 7 阻塞后可执行）

## 专家团

| 专家 | 模型 | 视角 | 评价 |
|------|------|------|:----:|
| 🧠 AI Native 架构师 | Qwen 3.7 Plus | AI Native 纯度 + 能力正交 + 信息守恒 | CONDITIONAL |
| 🌐 泛化性验证师 | Qwen 3.7 Plus | 覆盖度 + 修复深度 + 链路完整性 | CONDITIONAL |
| 🔒 向后兼容审计师 | Qwen 3.7 Plus | Pydantic 兼容 + 引用链 + 测试覆盖 | CONDITIONAL |

## 7 个阻塞项（修复后方案可执行）

### B1: `infer_domain_id()` 必须 LLM 语义推断
- **问题**: dict.get() 回退 software = 静默降级
- **修复**: LLM 推断 + 显式声明优先 + 验证回退
- **影响 Phase**: Phase 0

### B2: Living Spec Schema 缺 `domain_type` 字段
- **问题**: 整个配置驱动机制的起点断裂
- **修复**: LivingSpecMeta 增加 domain_type + Spec Pro Prompt 修改
- **影响 Phase**: Phase 0

### B3: `frozen_spec.py:412-416` 优先级分层硬编码
- **问题**: 新领域 category 全部落入最低优先级 CONTEXT
- **修复**: 泛化优先级分层逻辑，从配置文件加载
- **影响 Phase**: Phase 1

### B4: `extract_semantic_anchors.py:36-62` Prompt 硬编码
- **问题**: LLM 被限制只产出 4 个固定 category
- **修复**: 更新提取 Prompt 为开放枚举
- **影响 Phase**: Phase 1

### B5: `coordinator.py:611,619` Prompt 硬编码
- **问题**: Spec Pro coordinator 同样限制 4 个分类
- **修复**: 更新 Prompt
- **影响 Phase**: Phase 1

### B6: `summary_orchestrator.py:577-578` 未归属
- **问题**: 输出模板硬编码无明确修复 Phase
- **修复**: 纳入 Phase 2，从 domain_cfg 加载 output_structure
- **影响 Phase**: Phase 2

### B7: Phase 4 字段重命名风险 > 收益
- **问题**: alias 行为复杂，引入 breaking change
- **修复**: 保留原字段名，只改 description
- **影响 Phase**: Phase 4（工时 3天 → 1天）

## 优先级调整

| Prompt | 原 P | 新 P | 理由 |
|--------|:----:|:----:|------|
| research_expert_base.md | P1 | **P0** | 阻塞点 6 是 CRITICAL |
| planning_expert_base.md | P1 | **P0** | Expert Planner 基类影响全部下游 |

## 新增工作量

| 项目 | 说明 |
|------|------|
| 20 个新测试 | 8 P0 + 7 P1 + 5 P2 |
| 医疗/法律场景 | Phase 6 增加 2 个压力测试 |
| category_rationale | SemanticAnchor 增加字段 |
| domain 配置透传 | frozen_spec 增加 domain_config |

## 采纳的改进建议

| # | 建议 | 来源 | 采纳方式 |
|---|------|------|---------|
| 1 | YAML 配置先落地，后续评估 Prompt 注入 | E1 | Phase 0 先用 YAML |
| 2 | SemanticAnchor 增加 category_rationale | E1 | Phase 1 实施 |
| 3 | domain 配置写入 frozen_spec | E1 | Phase 0 实施 |
| 4 | task_builder 全量 grep 扫描 | E2 | Phase 2 前置步骤 |
| 5 | 配置编写责任分配 | E2 | 用 LLM 辅助生成 |

## 修正后的时间线

```
Day 1-2:   Phase 0 — DAL + domain_type + frozen_spec 透传
Day 3-5:   Phase 1 — Pydantic + frozen_spec + extract_anchors + coordinator
Day 5-8:   Phase 2 — task_builder + summary_orchestrator（全量扫描后执行）
Day 8-13:  Phase 3 — 14 个 Prompt 泛化（2 个 P1 提升为 P0）
Day 13-14: Phase 4 — Schema description 泛化（简化，不改字段名）
Day 14-18: Phase 6 — 5 场景 E2E（+医疗/法律）
贯穿:       Phase 5 — AI Native 专家评审
Day 18-20: 新增 20 个测试 + 回归验证
```
