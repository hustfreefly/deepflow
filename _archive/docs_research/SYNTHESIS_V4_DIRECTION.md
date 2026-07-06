# 调研综合报告 → V4 方向

> 日期：2026-06-25
> 来源：3 路并行调研（框架趋势 + 全LLM控制 + Goal声明式Prompt）

---

## 一、业界共识（3 份调研交叉验证）

### 1.1 "全 LLM 控制" ≠ 业界方向，"智能混合"才是

| 来源 | 结论 |
|------|------|
| 框架调研 | 7 大框架全部是混合架构，无一例外 |
| 控制模式调研 | Devin/Anthropic/OpenAI/SWE-Agent 全部是 LLM 规划 + 代码验证 |
| Prompt 调研 | 纯 Goal 声明式在生产中不稳定，Goal + 参考计划是最佳模式 |

**关键洞察**：业界的"混合"和 V3 的"混合"有本质区别：
- **V3 的混合**：LLM 被绑死在 Phase 1→5 流程中，只有"可以偏离"的有限自主权
- **业界的混合**：LLM 自主选择路径，但 Python 做验证和护栏（安全网，不是轨道）

### 1.2 能力注册表 > 阶段定义（Google A2A 启示）

Google A2A 的 Agent Card 模式：
```json
{
  "capabilities": [
    {"id": "architect", "input_schema": {...}, "output_schema": {...}},
    {"id": "reviewer", "input_schema": {...}, "output_schema": {...}}
  ],
  "constraints": {"max_retries": 3, "budget_minutes": 30}
}
```

**不定义执行顺序**，只定义可用能力和约束。Orchestrator 自主规划调用路径。

### 1.3 Goal + 参考计划 > 纯 Goal 声明式

纯 Goal 声明式的问题：
- LLM 可能生成低效计划（漏步骤、重复、死循环）
- 缺乏 few-shot 示例时，输出质量不稳定

Goal + 参考计划的优势：
- LLM 有"好的执行路径"示例，可以遵循或偏离
- 偏离时有 reason 记录，可追踪决策质量
- Anthropic/OpenAI/Devin 都用这种模式

### 1.4 分层 Prompt（<50 行 system + reference docs）

长 Prompt（>100 行）的遵循度随长度递减。业界最佳实践：
- **System Prompt**（<50 行）：Goal + Constraints + 核心规则
- **Reference Docs**（按需读取）：详细规则、恢复菜单、评估维度
- **Few-shot 示例**：1-2 个好的执行计划示例

---

## 二、V4 设计决策

### 2.1 P0-1 修复：stage-dependencies.json → capability-registry.json

**Before (V3)**：
```json
{
  "stages": {
    "architect": {"required": true, "depends_on": [], "max_retries": 3}
  }
}
```

**After (V4)**：
```json
{
  "capabilities": {
    "architect": {
      "description": "将 Living Spec 转化为架构设计",
      "input_schema": "living_spec",
      "output_schema": "architecture_output",
      "max_retries": 3,
      "quality_dimensions": ["completeness", "consistency", "feasibility"]
    }
  },
  "constraints": {
    "required_coverage": ["architecture", "review", "package"],
    "budget_minutes": 30,
    "max_total_retries": 10
  },
  "reference_plans": {
    "standard_pipeline": {
      "description": "标准 5 步管线（推荐路径，可偏离）",
      "steps": ["architect", "decomposer", "specifier", "reviewer", "packager"],
      "parallel_hints": [["decomposer", "reviewer"]]
    }
  }
}
```

**关键变化**：
- `required: true` → `required_coverage`（覆盖能力类别，不是固定阶段）
- `depends_on` → 删除（LLM 自主决定顺序）
- 新增 `reference_plans`（推荐路径，非强制）
- 新增 `parallel_hints`（并行建议，非强制）

### 2.2 P0-2 修复：Phase 1→5 → Goal 声明式 Prompt

**V3 Prompt 结构**：
```
Phase 1: 理解输入
Phase 2: 规划
Phase 3: 执行（循环）
Phase 4: 评估
Phase 5: 完成
```

**V4 Prompt 结构**：
```markdown
## Goal
将 Living Spec 转化为满足约束的 Ship Package

## Constraints
- 预算：30 分钟
- 必须覆盖：architecture, review, package
- 重试前必须 check-retry-limit
- 每次 spawn 必须传 cwd

## Available Capabilities
[从 capability-registry.json 注入]

## Reference Plan（推荐路径，你可以偏离）
standard_pipeline: architect → decomposer → specifier → reviewer → packager

## Your Autonomy
- 你可以跳过、合并、重排阶段
- 偏离参考计划时，log-decision 记录原因
- 简单任务可以只用 2-3 步完成

## Success Criteria
- 所有 required_coverage 已满足
- validate-quality 全部 pass
- Judge Worker 评估 pass
- check-budget 未超限
```

### 2.3 P0-3 修复：required → coverage validation

**V3**：`validate-plan --required architect,reviewer,packager`（硬编码）

**V4**：
```python
def validate_plan(output_dir):
    registry = load_capability_registry()
    required = registry["constraints"]["required_coverage"]
    # 检查计划是否覆盖了所需能力类别
    # 不是检查具体阶段名，而是检查能力类别
    plan = load_plan(output_dir)
    covered = set()
    for stage in plan["stages"]:
        covered.add(registry["capabilities"][stage]["category"])
    missing = set(required) - covered
    if missing:
        return {"valid": False, "missing_coverage": list(missing)}
    return {"valid": True}
```

### 2.4 实施性 P0 修复

| P0 | V3 问题 | V4 修复 |
|:---|:---|:---|
| runTimeoutSeconds | 参数不存在 | config 层设置 + check-budget 软超时 |
| TOCTOU 竞态 | check-retry + write-status 非原子 | `increment-retry` 原子命令（flock） |
| SKILL.md 草稿 | 缺失 | V4 包含完整 SKILL.md V5.0 草稿 |
| build-prompt 时序 | 缺子步骤 | Prompt 中包含完整示例 |

---

## 三、V4 vs V3 变更清单

| 文件 | 变更 |
|------|------|
| `capability-registry.json` | 新文件，替代 `stage-dependencies.json` |
| `stage-dependencies.json` | 废弃（保留兼容层） |
| Orchestrator Prompt | 重写为 Goal 声明式 |
| Worker Prompt 模板 | 增加 `{failure_feedback}` 占位符 |
| `io_helper.py` | 新增 `increment-retry` 命令 |
| `validate-plan` | 改为 coverage validation |
| `compact-history` | 增加 `key_decisions` 字段（含 reason） |
| SKILL.md V5.0 | 完整草稿（入口守卫 + 快速开始 + 命令速查） |
| Judge Worker Prompt | 差异化视角（下游可消费性，不是重复 Orchestrator 维度） |

---

## 四、风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| LLM 自主规划生成低效路径 | 中 | 中 | reference_plans 提供推荐路径 + few-shot 示例 |
| LLM 跳过必要步骤 | 低 | 高 | required_coverage 强制覆盖 + validate-plan 校验 |
| Prompt 过短导致 LLM 不知道怎么做 | 低 | 中 | reference docs 按需读取 + few-shot |
| 实施复杂度增加 | 中 | 中 | capability-registry 兼容旧 stage-dependencies |

---

*综合报告完成。基于此方向生成 V4 方案。*
