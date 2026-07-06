# Ship Pro AI Native Gate 实施报告

> **日期**: 2026-06-25  
> **状态**: ✅ Phase 1 完成（三层架构 + CLI 命令）  
> **验证**: 4/4 测试通过  

---

## 核心设计

### 三层 Gate 架构

```
Layer 1: 确定性检查（代码）
  ↓ 快速过滤格式错误（字段存在、依赖无环、Pydantic 验证）
Layer 2: LLM 语义检查（AI Native）
  ↓ Orchestrator Agent 用自己的 LLM 评估 Worker 输出
Layer 3: 综合决策
  ↓ 合并确定性 + 语义结果 → PASS / CONDITIONAL / FAIL
```

### 关键设计决策

| 决策 | 理由 |
|------|------|
| **Orchestrator 做语义检查** | Orchestrator 本身就是 LLM Agent，不需要额外 API 调用 |
| **Worker 零改动** | 不修改 Worker prompt 和输出格式 |
| **向后兼容** | 无 principles 时跳过语义检查，现有管线不受影响 |
| **确定性优先** | Layer 1 先过滤明显错误，Layer 2 只处理语义问题 |

---

## 新增文件

| 文件 | 用途 | 行数 |
|------|------|------|
| `domains/ship_pro/eval/llm_gate_checks.py` | LLM 语义检查函数 + Prompt 构建器 + 结果合并 | ~350 |
| `domains/ship_pro/eval/llm_caller.py` | LLM 调用封装（urllib，零依赖） | ~120 |
| `scripts/test_llm_gate_integration.py` | 集成测试（4 个测试用例） | ~180 |

## 修改文件

| 文件 | 改动 |
|------|------|
| `domains/ship_pro/scripts/run_pipeline.py` | 新增 `semantic-task` 和 `merge-semantic` CLI 命令；`check_gate` 增加 Layer 2 逻辑 |
| `scripts/start_ship_pro.py` | Orchestrator 模板增加 Step 3.5 语义检查流程 |

---

## CLI 命令

### 新增命令

```bash
# 生成语义评估任务（Orchestrator 用）
python3 run_pipeline.py semantic-task <agent_name> <output_dir>

# 合并语义评估结果
python3 run_pipeline.py merge-semantic <agent_name> <output_dir> <semantic_result_json>
```

### Orchestrator 工作流（更新后）

```
对于 architect/decomposer/specifier:

1. prepare
2. task → spawn Worker → 等待完成
3. gate（确定性检查）
   → 如果 needs_semantic_check=true:
     3.5a. semantic-task（生成评估 prompt）
     3.5b. Orchestrator 自己评估（用自己的 LLM）
     3.5c. merge-semantic（合并结果）
4. 如果 FAIL → feedback → 重试
5. update-status
```

---

## 语义检查覆盖的 Agent

| Agent | 检查维度 |
|-------|---------|
| **Architect** | 原则一致性、需求覆盖、模块完整性、职责合理性 |
| **Decomposer** | WP 粒度合理性、原则继承、需求分配 |
| **Specifier** | AC 可验证性、原则覆盖、AC 完整性 |
| Reviewer | ❌ 不检查（已经是 LLM 驱动） |
| Packager | ❌ 不检查（机械打包操作） |

---

## 验证结果

```
✅ Layer 1: 确定性检查 — PASS（模块非空、依赖无环、Pydantic 验证）
✅ Layer 2: LLM 语义检查 — 优雅降级（无 API key 时跳过）
✅ Layer 3: 合并结果 — FAIL（语义检查发现问题时正确拦截）
✅ 完整集成 — check_gate 正确返回 needs_semantic_check=True
```

---

## 下次 Ship Pro 运行时的预期效果

1. **Architect 阶段**：
   - 确定性检查 PASS（格式正确）
   - 语义检查：Orchestrator 评估"全 LLM 控制"原则是否被遵守
   - 如果 Architect 输出仍包含"令牌桶限流"等确定性逻辑 → FAIL
   - Worker 收到反馈："COMP-001 的 tech stack 包含确定性逻辑，应改为 LLM API 调用"
   - Worker 修正输出 → 重新 gate → PASS

2. **Decomposer 阶段**：
   - 语义检查：WP 粒度是否合理
   - 如果 16 个 WP 被合并为 9 个 → FAIL
   - Worker 收到反馈："COMP-007 有 4 条职责但只有 1 个 WP，应拆分"

3. **Specifier 阶段**：
   - 语义检查：AC 是否包含原则验证
   - 如果 9 个 WP 只有 1 个有原则 AC → FAIL

---

## 待改进

1. **Orchestrator prompt 优化**：当前语义评估 prompt 较长（~500 行），可能需要压缩
2. **语义检查结果缓存**：避免重复评估相同输出
3. **更多 Agent 覆盖**：未来可扩展到 Reviewer 和 Packager
4. **LLM 调用备选方案**：当前依赖 Orchestrator 自身 LLM，未来可支持外部 API

---

*AI Native 改造 Phase 1 完成。核心理念：LLM 评估 LLM，而非代码评估 LLM。*
