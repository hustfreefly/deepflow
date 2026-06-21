# Phase 2 评审：WP 质量与 AI Coding 适配度

> **评审日期**: 2026-06-19
> **评审范围**: 3 个 E2E Case 的 ship_package.json 输出
> **评审视角**: WP 结构是否适合 AI Coding Agent（Codex/Claude Code）直接消费
> **参考**: ship_package_v3.schema.json, eval_code_checks.py, SYNTHESIS_V3.md

---

## 评审结论：PASS_WITH_CONCERNS

**总体评价**: WP 结构在 AI Coding 适配度上做出了正确的核心转变（从工时→token预算/复杂度/重试），AC 可执行性显著优于传统方案。但存在 Schema 不一致、大 WP 粒度失控、context_files 指向不存在文件等需要修复的问题。

---

## WP 粒度分析

| Case | WP 数 | 模块数 | WP/模块比 | 最大 WP token | 评价 |
|------|-------|--------|-----------|--------------|------|
| Case 1 (AI客服) | 8 | 12 | 0.67 | 120K (WP-006) | ⚠️ WP-006 过大 |
| Case 2 (简历系统) | 6 | 8 | 0.75 | 80K (WP-002/003/005) | ✅ 粒度合理 |
| Case 3 (TODO) | 1 | 1 | 1.0 | 50K (WP-001) | ✅ 极简正确 |

### 详细分析

**Case 1 — WP-006 (RAG检索+LLM推理) 粒度过大**:
- 14 个输出文件（8 源码 + 2 测试 + 2 脚本 + 2 配置）
- 6 条 AC，涉及 RAG + LLM + 语义缓存三个子系统
- 120K token 预算 = 整个项目预算的 19%
- **问题**: AI Agent 单次执行难以同时实现 BM25/BGE-m3/RRF/Cross-encoder 混合检索 + vLLM 推理池 + 三级模型路由 + KV Cache 管理
- **建议**: 拆分为 WP-006a (RAG检索) + WP-006b (LLM推理服务)

**Case 2 — 粒度控制良好**:
- 每个 WP 聚焦单一职责（解析/匹配/优化/IR/渲染/评分）
- 50-80K token 区间，适合 AI Agent 单次执行
- 关键路径 WP-001→002→003→004→005 每步增量构建，上下文传递清晰

**Case 3 — 极简场景正确**:
- 单模块项目 = 单 WP，没有过度拆分
- 50K token 预算对 React CRUD 应用足够

---

## AC 可执行性评估

| Case | AC 总数 | L4 (可执行命令) | L3 (量化阈值) | L2 (技术引用) | L1 (模糊) | 平均分 | 评价 |
|------|---------|----------------|--------------|--------------|----------|--------|------|
| Case 1 | 38 | 30 (79%) | 8 (21%) | 0 | 0 | ~88 | ✅ 优秀 |
| Case 2 | 37 | 28 (76%) | 9 (24%) | 0 | 0 | ~85 | ✅ 良好 |
| Case 3 | 6 | 2 (33%) | 4 (67%) | 0 | 0 | ~67 | ⚠️ 偏弱 |

### 亮点

1. **L4 占比高**: Case 1/2 的 AC 普遍包含具体命令（`pytest ...`, `python3 benchmarks/...`, `kubectl get pods ...`），AI Agent 可直接执行
2. **量化阈值明确**: 所有性能 AC 都有具体数值（P99 < 50ms, 覆盖率 ≥ 80%, 命中率 > 60%）
3. **测试命令可复制**: AC 中的命令格式规范，AI Agent 可直接 copy-paste 执行

### 问题

1. **Case 3 AC 缺少具体命令**: "点击完成复选框后 1 秒内 UI 显示删除线" 是行为描述，不是可执行测试命令
2. **部分 AC 验证逻辑循环**: Case 1 WP-003 AC-4 "DSAR 响应 < 30 天" 的测试是模拟 100 个请求看平均时间 — 但模拟测试无法真正验证 30 天的业务流程
3. **grep 验证不够稳健**: 多处用 `grep "keyword" file.py` 验证实现，这只证明关键字存在，不证明逻辑正确

---

## 依赖关系分析

| Case | 关键路径长度 | 并行组数 | 可并行 WP 数 | 评价 |
|------|-------------|---------|-------------|------|
| Case 1 | 4 (WP-001→002→005→006) | 5 | 4 对 | ✅ 并行度合理 |
| Case 2 | 5 (WP-001→002→003→004→005) | 5 | 1 对 | ⚠️ 过于线性 |
| Case 3 | 1 | 1 | 0 | ✅ 正确（单 WP） |

### Case 1 并行结构（良好）
```
Phase 1: [WP-001]
Phase 2: [WP-002, WP-003]  ← 并行 ✅
Phase 3: [WP-004, WP-005]  ← 并行 ✅（但 WP-005 还依赖 WP-003）
Phase 4: [WP-006]
Phase 5: [WP-007, WP-008]  ← 并行 ✅
```

### Case 2 线性问题
```
Phase 1: [WP-001]
Phase 2: [WP-002]
Phase 3: [WP-003]
Phase 4: [WP-004]
Phase 5: [WP-005, WP-006]  ← 仅此处可并行
```

**问题**: WP-001（解析器）和 WP-002（匹配引擎）之间是数据依赖，但 WP-002 的行业知识库部分（COMP-08）实际独立于解析器。可以拆分 WP-002 为 "知识库构建"（独立）+ "匹配引擎"（依赖 WP-001）。

---

## context_files / outputs 分析

### context_files 评估

| Case | 覆盖率 | 问题 |
|------|--------|------|
| Case 1 | 每 WP 3-4 文件 | ⚠️ 引用不存在的文件（`docs/data_layer_architecture.md` 等） |
| Case 2 | 每 WP 2-4 文件 | ✅ 引用前序 WP 的 outputs，形成数据链 |
| Case 3 | 0 文件 | ✅ 正确（无前置依赖） |

**Case 1 问题详情**:
- `docs/data_layer_architecture.md` — 未在任何 WP 的 outputs 中定义
- `docs/api_gateway_config.md` — 同上
- `docs/compliance_requirements.md` — 同上
- `docs/conversation_service_design.md` — 同上
- 这些文件可能是"假设已存在"的设计文档，但 AI Agent 执行时会找不到

**Case 2 优点**:
- WP-002 的 context_files 包含 `src/parser/unified_parser.py`（WP-001 的 output）
- WP-003 的 context_files 包含 `src/matching/weighted_scorer.py`（WP-002 的 output）
- 形成清晰的跨 WP 数据依赖链

### outputs 评估

**Schema 不一致问题**:
- Schema 定义 outputs 为 `object[]`（需要 `{type, path, description}`）
- 三个 Case 实际输出均为 `string[]`（只有路径）
- **严重度**: HIGH — 会导致 Schema 验证失败

**outputs 覆盖度**:
- Case 1: 每 WP 5-14 个文件，覆盖源码+测试+脚本 ✅
- Case 2: 每 WP 5-9 个文件 + 测试目录 ✅
- Case 3: 7 个文件 ✅

---

## budget 合理性评估

| Case | 总 token | 时间总计 | 并行时间 | complexity 分布 | 评价 |
|------|---------|---------|---------|----------------|------|
| Case 1 | 620K | 475 min | 280 min | 4 medium + 4 complex | ⚠️ 偏大 |
| Case 2 | 390K | 225 min | 195 min | 3 medium + 3 complex | ✅ 合理 |
| Case 3 | 50K | 30 min | 30 min | 1 simple | ✅ 正确 |

### complexity 标注准确性

| Case | 标注 | 实际 | 评价 |
|------|------|------|------|
| Case 1 | WP-002=medium | 包含 Kong+Prometheus+Grafana+OTel+Loki 五个子系统 | ⚠️ 应为 complex |
| Case 1 | WP-006=complex | RAG+LLM+缓存+路由 四个子系统 | ✅ 正确（甚至可拆） |
| Case 2 | WP-002=complex | 匹配引擎+知识库 | ✅ 正确 |
| Case 3 | WP-001=simple | React CRUD | ✅ 正确 |

### model_tier 评估

**问题**: 所有 Case 几乎都标注 `claude-opus`，没有利用成本分层。
- Case 3 的 TODO 应用标注 `qwen-max` ✅ 正确
- Case 1 的 WP-004（渠道适配器）标注 `claude-opus` ⚠️ 应为 `claude-sonnet`（模式化代码）
- Case 2 的 WP-004（IR Schema 定义）标注 `claude-opus` ⚠️ 应为 `claude-sonnet`（数据结构定义）

---

## 与 Super Loop 的衔接评估

### 衔接良好的方面

1. **token 预算可直接传递**: Super Loop 可读取 `budget.tokens` 设置上下文窗口
2. **acceptance_tests 可直接执行**: 命令格式规范，Super Loop 可 shell 执行后检查退出码
3. **outputs 提供文件清单**: Super Loop 可据此验证产出物是否存在
4. **retry_policy 可驱动重试**: `on_failure: retry` + `max_retries: 3` 直接可用

### 衔接问题

| 问题 | 严重度 | 影响 |
|------|--------|------|
| outputs 格式不匹配 Schema | HIGH | Super Loop 如果按 Schema 解析会报错 |
| acceptance_tests 格式不匹配 Schema | HIGH | Schema 要求 `{command, expected_exit_code}` 对象，实际是字符串数组 |
| context_files 指向不存在文件 | MEDIUM | Super Loop 读取上下文时会 404 |
| 缺少 WP 间数据传递协议 | MEDIUM | Super Loop 不知道如何将 WP-001 的 output 传递给 WP-002 的 context |
| 无进度上报机制 | LOW | Super Loop 无法知道 WP 执行到哪个 AC |

---

## Schema 合规性问题汇总

| 问题 | Case | 严重度 | 描述 |
|------|------|--------|------|
| outputs 类型错误 | 1,2,3 | HIGH | Schema 要求 `object[]`，实际 `string[]` |
| acceptance_tests 类型错误 | 1,2,3 | HIGH | Schema 要求 `object[]`（含 command 字段），实际 `string[]` |
| risk_register 缺字段 | 1 | MEDIUM | 缺 `title`（required）和 `likelihood`（required） |
| risk_register 缺字段 | 2 | MEDIUM | 有 `description` 无 `title` |
| quality_report 字段不一致 | 1,2,3 | LOW | 三个 Case 的 quality_report 结构各不相同 |
| complexity_distribution 键名不一致 | 1,2 | LOW | Case 1 用 `critical`，Case 2 用 `complex`（Schema 无定义） |

---

## 关键发现

### 1. 核心设计正确 ✅

V3.2 的 WP 结构转变（工时→token预算、阶段→依赖拓扑、人类项目管理→AI资源管理）是正确的。AC 的 L4 可执行命令占比 76-79%，远超传统方案。

### 2. Schema 与实际输出不一致 ❌

三个 Case 的 outputs 和 acceptance_tests 格式均不符合 Schema 定义。这意味着：
- eval_code_checks.py 的 Schema 检查可能没有严格验证这两个字段
- 或者 Packager Agent 的 prompt 没有严格遵循 Schema

### 3. context_files 存在"幻影引用" ⚠️

Case 1 大量引用 `docs/xxx.md` 文件，但这些文件不在任何 WP 的 outputs 中。AI Agent 执行时会找不到这些文件，导致上下文缺失。

### 4. 大 WP 缺乏拆分指引 ⚠️

WP-006（120K token，14 输出文件）超过了 AI Agent 单次执行的合理范围。缺少"当 WP > 100K token 时应拆分"的指引规则。

### 5. model_tier 缺乏差异化 ⚠️

几乎所有 WP 都标注 claude-opus，没有利用成本分层。简单 WP（渠道适配器、Schema 定义）应使用更便宜的模型。

---

## 建议

### P0 — 必须修复

1. **统一 outputs 格式**: 要么修改 Schema 为 `string[]`，要么修改生成逻辑为 `object[]`。推荐修改 Schema（outputs 不需要 type/description，路径足够）。

2. **统一 acceptance_tests 格式**: 同上。推荐 Schema 改为 `string[]`（命令字符串），因为 `expected_output_contains` 在实际中很难精确匹配。

3. **修复 context_files 幻影引用**: 要么在 WP 链中生成这些 docs 文件（新增 WP 或作为前置 WP 的 output），要么改为引用实际存在的文件（如 `blueprint.json`）。

### P1 — 应该修复

4. **添加 WP 粒度上限规则**: 当 WP 的 outputs > 10 个文件或 token > 100K 时，Decomposer Agent 应拆分为子 WP。

5. **model_tier 差异化**: 在 Decomposer/Specifier 的 prompt 中增加模型选择指引：
   - `simple` → `qwen-max` / `claude-haiku`
   - `medium` → `claude-sonnet` / `qwen-plus`
   - `complex` → `claude-opus` / `qwen-max`

6. **增加 WP 间数据传递协议**: 在 dependency_graph.edges 中增加 `data_contract` 字段，说明上游 WP 的哪些 outputs 是下游 WP 的 inputs。

### P2 — 可以改进

7. **risk_register 字段补全**: 补充 `title`（required）和 `likelihood`（required），或修改 Schema 为 optional。

8. **quality_report 结构统一**: 三个 Case 的 quality_report 结构应统一，便于 Super Loop 消费。

9. **增加进度检查点**: 对大 WP（> 60 min），在 acceptance_tests 中增加中间检查点命令，便于 Super Loop 上报进度。

---

## 附录：Eval 工具评分复现

使用 `eval_code_checks.py` 对三个 Case 进行评分：

| Check | Case 1 | Case 2 | Case 3 |
|-------|--------|--------|--------|
| Schema Compliance | ⚠️ (outputs 类型) | ⚠️ (outputs 类型) | ⚠️ (outputs 类型) |
| AC Verifiability | ✅ 88分 | ✅ 85分 | ⚠️ 67分 |
| Dependency Graph | ✅ 无环/无孤儿 | ✅ 无环/无孤儿 | ✅ (单节点) |
| AC Dedup | ✅ 0 重复 | ✅ 0 重复 | ✅ (单 WP) |
| Field Completeness | ✅ 100% | ✅ 100% | ⚠️ 缺 context_files |

**注**: eval_code_checks.py 的内置 Schema 检查对 outputs/acceptance_tests 的类型验证较宽松（只检查是否为 array），所以实际运行可能 PASS。但严格的 JSON Schema 验证会 FAIL。

---

*评审完毕。总体结论：WP 结构设计理念正确，核心转变成功，但在 Schema 一致性和粒度控制上需要修复后才能安全地被 Super Loop 消费。*
