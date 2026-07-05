# 评审报告：Solution Pro 2.0.0 LLM 路由重构方案

> **评审日期**: 2026-06-29
> **评审方式**: PlanMode Pro 多轮专家评审（3 轮，6 位专家）
> **最终裁决**: ✅ **通过（8/10）**
> **最终方案**: `refactor_llm_routing_v3.md`

---

## 1. 原始方案要点

**方案核心**：将 Solution Pro 2.0.0 中所有"绕过 OpenClaw 直调 LLM API"的代码统一重构为走 `spawn_fn`（→ `sessions_spawn`），实现零额外 API Key。

**5 个问题模块**：
| # | 文件 | 问题 | 严重度 |
|---|------|------|--------|
| P1 | e2e_test_runner.py | Spawn Bridge 文件中转 | P0 |
| P2 | compliance_checker.py | llm_judge_fn 来源不确定 | P1 |
| P3 | harness_scorer.py | 同上 | P1 |
| P4 | planner.py | 2.0.0 legacy 未清理 | P2 |
| P5 | ai_native_auditor.py | llm_judge_fn 同类问题 | P1 |

**原始方案关键设计**：
- LLMJudgeAdapter：将 spawn_fn 适配为 llm_judge_fn 接口
- 方案 A（生产）+ 方案 B（测试）共存
- SpawnResult Pydantic 契约验证
- 预计 4-5 小时工作量

---

## 2. 各轮专家意见摘要

### Round 1：全面评审（3 位专家，均分 5/10）

| 专家 | 评分 | 核心发现 |
|------|------|---------|
| OpenClaw 平台专家 | 5 | spawn_fn 返回值假设错误；并发控制缺失；exec 注入链路未说明 |
| AI Native 架构师 | 5 | LLMJudgeAdapter 是 Fake AI Native 反模式；缺少 Layer 2 语义验证 |
| 测试工程专家 | 5 | E2E 入口缺失；mock/real 接口不一致；CI/CD 策略不完整 |

**P0 问题汇总（5 个）**：
1. spawn_fn 返回值假设错误（dict vs str）
2. 并发控制完全缺失
3. judge() 是 async 但 spawn_fn 是同步
4. E2E 测试入口点设计缺失
5. 缺少子 Agent prompt 契约定义

### Round 2：聚焦修复（2 位专家，均分 4/10）

| 专家 | 聚焦领域 | 核心裁决 |
|------|---------|---------|
| spawn_fn 契约专家 | 返回值/注入/sync-async | spawn_fn 返回 str；注入通过 DI 非 exec；judge() 必须同步 |
| 测试集成专家 | E2E 入口/mock 接口/CI | 需要 run_e2e(spawn_fn)；需要 SpawnFnProtocol；双层测试策略 |

**关键发现**：
- spawn_fn 实际返回字符串（visible reply），不是 dict
- 文件桥接模式的根因不是模式本身错误，而是缺少轮询的 orchestrator
- mock_spawn_fn 签名泄漏了 spawn bridge 的 output_path 参数
- CI 中新场景无录制数据时应 FAIL 而非 SKIP

### Round 3：收敛裁决（1 位专家，8/10）

| 遗留问题 | 裁决 | 理由 |
|---------|------|------|
| Layer 2 语义验证 | 延期（P1，2 周内） | 合理但超出本次范围，强行加入扩大 blast radius |
| 原生工具集成 | 延期 | 与路由重构正交，独立 feature |
| prod spawn 校验 | 必须修复 | 3 行代码，防御性编程，防止静默 fallback |

**最终裁决**：✅ **通过**，修复 prod spawn 校验后可合并。

---

## 3. 采纳/不采纳清单

### ✅ 采纳（已体现在 2.0.0 方案中）

| # | 问题 | 修复内容 | 来源 |
|---|------|---------|------|
| 1 | spawn_fn 返回值 | 返回字符串，简化 _extract_output → 直接处理 str | R1 平台 + R2 契约 |
| 2 | sync/async | judge() 改为同步方法，移除 asyncio | R1 测试 + R2 契约 |
| 3 | 并发控制 | 批量评估串行分批，max_concurrent=3 | R1 平台 + R1 架构 |
| 4 | 注入链路 | 文档化 DI 注入 + depth 链路图 | R1 平台 + R2 契约 |
| 5 | SpawnFnProtocol | 定义 typing.Protocol 统一 mock/real 接口 | R1 测试 + R2 测试 |
| 6 | E2E 入口 | 添加 run_e2e(spawn_fn) 显式入口函数 | R1 测试 + R2 测试 |
| 7 | CI/CD 策略 | 双层测试：unit（mock）+ integration（真实） | R1 测试 + R2 测试 |
| 8 | 深度约束 | 文档化 depth-0 → depth-1 → depth-2 限制 | R1 平台 |
| 9 | 错误处理 | 重试机制 + 错误分类 | R1 平台 |
| 10 | Phase 顺序 | 契约定义前置到 Phase 0/1 | R1 测试 |
| 11 | prod spawn 校验 | master_orchestrator 初始化时强制检查 | R3 收敛 |
| 12 | ADR 文档 | 附录对比 Crew AI/AutoGen/LangGraph | R1 架构 |
| 13 | 录制数据迁移 | 基于 task_key 而非 prompt hash | R1 测试 |
| 14 | 工作量重估 | 从 4-5h 调整为 7-8h（含 Phase 0） | R1 架构 + R1 测试 |

### ⏸️ 延期（记录为后续增强）

| # | 问题 | 延期理由 | 优先级 | 建议时间 |
|---|------|---------|--------|---------|
| 1 | Layer 2 LLM 语义验证 | 超出路由重构范围，独立 PR | P1 | 2 周内 |
| 2 | OpenClaw 原生工具集成 | 与路由重构正交，独立 feature | P2 | 按需 |
| 3 | LLM-as-Judge 验证测试用例 | 测试质量增强，非阻塞 | P2 | 按需 |

### ❌ 不采纳

| # | 建议 | 不采纳理由 |
|---|------|-----------|
| 1 | 保留文件桥接模式 | 2.0.0 选择更干净的 depth-1 orchestrator 模式，文件桥接是 workaround |
| 2 | asyncio.Semaphore 并发控制 | 改为串行分批更简单可靠，避免 sync/async 混合 |
| 3 | SpawnResult 作为实际返回类型 | spawn_fn 实际返回 str，SpawnResult 仅用于文档化 |

---

## 4. 最终修改后的方案要点（2.0.0）

### 4.1 架构变更

```
重构前：
  exec Python → 文件桥接 spawn_fn → requests/ → (无人轮询) → 失败

重构后：
  depth-0: 主 Agent → sessions_spawn
  depth-1: Orchestrator（注入 spawn_fn）→ spawn_fn
  depth-2: Worker（返回 visible reply 字符串）
```

### 4.2 核心代码变更

1. **LLMJudgeAdapter**（2.0.0 最终版）
   - 同步 `judge()` 方法（非 async）
   - spawn_fn 返回字符串，直接解析
   - 批量评估串行分批
   - 重试机制（max_retries=2）

2. **SpawnFnProtocol**
   - `__call__(task: str, ...) -> str`
   - mock_spawn_fn 和真实 spawn_fn 统一实现

3. **run_e2e(spawn_fn)**
   - 显式 E2E 测试入口
   - 支持 mock/real 模式切换

4. **prod spawn 校验**
   ```python
   if spawn_fn is None and os.getenv('ENV') == 'prod':
       raise ValueError('spawn_fn required in prod')
   ```

### 4.3 执行计划（2.0.0）

| Phase | 内容 | 工作量 |
|-------|------|--------|
| Phase 0 | 检查现有测试覆盖，建立 baseline | 30min |
| Phase 1 | 定义 SpawnFn Protocol + LLMJudgeAdapter | 1h |
| Phase 2 | 重构 3 个模块（compliance/harness/auditor） | 1.5h |
| Phase 3 | 重写 e2e_test_runner | 1.5h |
| Phase 4 | 移动 2.0.0 legacy | 15min |
| Phase 5 | 统一 mock_spawn_fn + 录制迁移 | 1h |
| Phase 6 | E2E 验证 | 1h |
| Phase 7 | 可观测性 + 文档 | 30min |
| **总计** | | **7-8h** |

---

## 5. 遗留问题

| # | 问题 | 状态 | 优先级 | 建议 |
|---|------|------|--------|------|
| 1 | Layer 2 LLM 语义验证 | 延期 | P1 | 2 周内独立 PR |
| 2 | OpenClaw 原生工具集成 | 延期 | P2 | 按需 |
| 3 | 批量评估性能瓶颈（>50 cases） | 待观察 | P2 | 监控后决定 |
| 4 | 录制数据版本控制 | 待实施 | P2 | 随 Phase 5 一起 |

---

## 6. 评审过程统计

| 指标 | 数值 |
|------|------|
| 总轮次 | 3 |
| 总专家数 | 6 |
| Round 1 专家 | 3（平台/架构/测试） |
| Round 2 专家 | 2（spawn 契约/测试集成） |
| Round 3 专家 | 1（收敛裁决） |
| 原始 P0 问题 | 5 |
| 原始 P1 问题 | 8 |
| 原始 P2 问题 | 5 |
| 最终 P0 残留 | 0 |
| 最终评分 | 8/10 |
| 方案版本 | 2.0.0 → 2.0.0 → 2.0.0 |
| 工作量重估 | 4-5h → 7-8h |

---

## 7. 结论

经过 3 轮 6 位专家的严格评审，方案从 2.0.0（5/10）迭代到 2.0.0（8/10）。所有 P0 问题已修复，架构清晰，符合 AI Native 原则。修复 prod spawn 校验（3 行代码）后即可合并执行。

**建议**：按 2.0.0 方案的 Phase 0-7 顺序执行，Phase 6 为关键验证点。Layer 2 语义验证作为后续 P1 优先级跟进。
