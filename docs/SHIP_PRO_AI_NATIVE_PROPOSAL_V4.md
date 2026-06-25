# Ship Pro AI Native 改造方案 V4

> **日期**: 2026-06-25  
> **版本**: V4（基于 V3 + 第三轮专家评审 + 3 路业界趋势调研）  
> **作者**: 小满（AI Agent）  
> **决策者**: 姬忠礼  
> **状态**: 待评审  
> **V3 备份**: `SHIP_PRO_AI_NATIVE_PROPOSAL.md`  
> **调研支撑**: `research/` 目录 3 份报告 + `SYNTHESIS_V4_DIRECTION.md`

---

## 一、V3 → V4 核心变更

### 1.1 业界调研结论（3 路并行调研，2026-06-25）

| 调研方向 | 核心发现 | 对 V4 的影响 |
|---------|---------|-------------|
| **Agent 框架趋势** | 7 大框架全部是混合架构；图编排取代线性链；AutoGen（纯对话编排）被微软废弃 | V4 采用"LLM 规划 + 代码验证"，不是 waterfall 也不是纯 LLM |
| **全 LLM 控制 vs 混合** | Devin 15% 成功率证伪纯 LLM 控制；Anthropic 的单线程 master loop + 环境约束是最佳实践 | V4 保留 Python 护栏，但 LLM 拥有规划自主权 |
| **Goal 声明式 Prompt** | Goal + Constraints + Reference Plan 是 2025-2026 最佳模式；纯过程式已被淘汰 | V4 Orchestrator Prompt 重写为 Goal 声明式 |

### 1.2 V4 设计哲学

> **"LLM 声明式规划，代码验证护栏。不给 LLM 无限权力，也不把 LLM 当执行器。"**

```
┌─────────────────────────────────────────────────────┐
│  LLM 层（Orchestrator Agent）                        │
│  ├─ 读取 Living Spec + Capability Registry           │
│  ├─ 自主规划执行路径（可选、可并行、可跳过）            │
│  ├─ 每次决策 log-decision                            │
│  └─ 偏离 Reference Plan 时记录原因                    │
├─────────────────────────────────────────────────────┤
│  代码验证层（Python 护栏，不可被 LLM 覆盖）            │
│  ├─ validate-format: Schema 校验（硬约束）            │
│  ├─ validate-quality: Gate 函数（硬约束）             │
│  ├─ check-retry-limit: 重试上限（硬约束）             │
│  ├─ check-budget: 时间预算（硬约束）                  │
│  ├─ validate-coverage: 能力覆盖校验（硬约束）          │
│  └─ increment-retry: 原子重试计数（防竞态）            │
├─────────────────────────────────────────────────────┤
│  状态管理层（io_helper.py + blackboard）              │
│  ├─ pipeline_state.json: 唯一状态文件                 │
│  ├─ decisions.jsonl: 决策审计日志                     │
│  ├─ .heartbeat: 存活信号                              │
│  └─ resume-context: 断点恢复                          │
├─────────────────────────────────────────────────────┤
│  Judge 层（独立 Judge Worker）                        │
│  ├─ 差异化视角：下游可消费性（不是重复 Orchestrator）   │
│  ├─ 与 Python gate 交叉验证                          │
│  └─ 对抗性评估：找出 Top-3 风险                       │
└─────────────────────────────────────────────────────┘
```

### 1.3 V3 → V4 变更清单

| 维度 | V3 | V4 |
|------|-----|-----|
| **阶段定义** | `stage-dependencies.json`（5 个固定阶段 + 固定依赖） | `capability-registry.json`（能力注册表 + 覆盖约束 + 参考计划） |
| **Orchestrator Prompt** | Phase 1→5 过程式（~200 行） | Goal 声明式（System <50 行 + Reference Docs） |
| **阶段顺序** | 硬编码依赖关系，偏离需记录 | LLM 自主决定顺序，Reference Plan 仅供参考 |
| **required 检查** | `required: true` 不可跳过 | `required_coverage` 能力类别覆盖检查 |
| **并行执行** | 固定 `parallel_groups` | LLM 自主判断 + `parallel_hints` 建议 |
| **超时控制** | `runTimeoutSeconds`（参数不存在） | config 层设置 + `check-budget` 软超时 |
| **重试计数** | check-retry + write-status 非原子 | `increment-retry` 原子命令（flock） |
| **Judge 视角** | 与 Orchestrator 相同 5 维度 | 差异化：下游可消费性 + 对抗性 Top-3 风险 |
| **Prompt 架构** | 单文件 ~200 行 | 分层：System Prompt + Reference Docs + Few-shot |
| **Worker Prompt** | 无 `{failure_feedback}` | 增加重试反馈占位符 |
| **compact-history** | 纯提取，丢决策原因 | 保留 `key_decisions` 含 reason + alternatives |
| **log-decision** | 自由文本 type/outcome | 枚举合法值 |

---

## 二、Capability Registry（替代 stage-dependencies.json）

### 2.1 设计原则

> **不定义执行顺序，只定义可用能力和约束。LLM 自主规划调用路径。**

灵感来源：Google A2A Agent Card 模式 — 声明能力，不声明流程。

### 2.2 Schema

```json
{
  "$schema": "capability-registry-v4",
  "capabilities": {
    "architect": {
      "id": "architect",
      "category": "architecture",
      "description": "将 Living Spec 转化为架构设计",
      "input_schema": {
        "required": ["living_spec"],
        "optional": ["existing_architecture", "constraints"]
      },
      "output_schema": {
        "file": "architecture_output.json",
        "fields": ["modules", "principles", "decisions", "risks"]
      },
      "max_retries": 3,
      "timeout_minutes": 10,
      "quality_dimensions": ["completeness", "consistency", "feasibility"],
      "gate_fn": "gate_architect",
      "worker_prompt": "prompts/worker_architect.md"
    },
    "decomposer": {
      "id": "decomposer",
      "category": "decomposition",
      "description": "将架构设计分解为可执行工作包",
      "input_schema": {
        "required": ["architecture_output"],
        "optional": ["living_spec"]
      },
      "output_schema": {
        "file": "decomposition_output.json",
        "fields": ["work_packages", "dependencies", "priorities"]
      },
      "max_retries": 3,
      "timeout_minutes": 10,
      "quality_dimensions": ["granularity", "dependency_clarity", "completeness"],
      "gate_fn": "gate_decomposer",
      "worker_prompt": "prompts/worker_decomposer.md"
    },
    "specifier": {
      "id": "specifier",
      "category": "specification",
      "description": "为工作包生成详细技术规格",
      "input_schema": {
        "required": ["decomposition_output"],
        "optional": ["architecture_output", "living_spec"]
      },
      "output_schema": {
        "file": "specification_output.json",
        "fields": ["specs", "interfaces", "contracts"]
      },
      "max_retries": 3,
      "timeout_minutes": 10,
      "quality_dimensions": ["precision", "testability", "completeness"],
      "gate_fn": "gate_specifier",
      "worker_prompt": "prompts/worker_specifier.md"
    },
    "reviewer": {
      "id": "reviewer",
      "category": "review",
      "description": "独立评审所有产出物的质量",
      "input_schema": {
        "required": ["architecture_output", "decomposition_output"],
        "optional": ["specification_output", "living_spec"]
      },
      "output_schema": {
        "file": "review_output.json",
        "fields": ["findings", "severity", "recommendations"]
      },
      "max_retries": 2,
      "timeout_minutes": 10,
      "quality_dimensions": ["thoroughness", "actionability"],
      "gate_fn": "gate_reviewer",
      "worker_prompt": "prompts/worker_reviewer.md"
    },
    "packager": {
      "id": "packager",
      "category": "package",
      "description": "打包最终 Ship Package",
      "input_schema": {
        "required": ["architecture_output", "decomposition_output", "review_output"],
        "optional": ["specification_output"]
      },
      "output_schema": {
        "file": "ship_package.json",
        "fields": ["manifest", "artifacts", "metadata"]
      },
      "max_retries": 2,
      "timeout_minutes": 5,
      "quality_dimensions": ["completeness", "consistency", "schema_compliance"],
      "gate_fn": "gate_packager",
      "worker_prompt": "prompts/worker_packager.md"
    }
  },
  "constraints": {
    "required_coverage": ["architecture", "review", "package"],
    "budget_minutes": 30,
    "max_total_retries": 15,
    "max_parallel_workers": 3
  },
  "reference_plans": {
    "standard": {
      "description": "标准管线（推荐路径，可偏离）",
      "steps": ["architect", "decomposer", "specifier", "reviewer", "packager"],
      "parallel_hints": [
        {"group": ["decomposer", "reviewer"], "note": "两者输入不冲突，可并行"}
      ],
      "skip_conditions": {
        "specifier": "当 Living Spec 已包含详细规格时可跳过",
        "decomposer": "当任务足够简单、无需分解时可跳过"
      }
    },
    "quick_review": {
      "description": "快速评审（仅适用于小改动）",
      "steps": ["reviewer", "packager"],
      "parallel_hints": [],
      "skip_conditions": {}
    },
    "full_with_iteration": {
      "description": "完整管线 + 迭代优化（适用于复杂需求）",
      "steps": ["architect", "decomposer", "specifier", "reviewer", "fix_issues", "reviewer", "packager"],
      "parallel_hints": [
        {"group": ["decomposer", "reviewer"], "note": "第一轮可并行"}
      ],
      "skip_conditions": {}
    }
  }
}
```

### 2.3 与 V3 的关键区别

| V3 `stage-dependencies.json` | V4 `capability-registry.json` |
|---|---|
| `depends_on: []` 硬编码依赖 | 无依赖声明，LLM 从 `input_schema` 推导 |
| `required: true` 不可跳过 | `required_coverage` 类别覆盖，具体阶段可跳 |
| `parallel_groups` 固定并行组 | `parallel_hints` 建议，LLM 自主判断 |
| 只有 1 种执行路径 | 多个 `reference_plans`，LLM 选择或自创 |
| `max_retries` 在阶段级 | `max_retries` 在能力级 + `max_total_retries` 全局约束 |

---

## 三、Goal 声明式 Orchestrator Prompt

### 3.1 设计原则

> **System Prompt < 50 行（核心约束前置+后置），详细规则外置为 Reference Docs。**

灵感来源：
- Anthropic 单线程 master loop + 环境约束
- OpenAI Codex `/goal` 模式
- 2025-2026 Prompt 工程最佳实践：结构化分段 + 关键约束前置后置

### 3.2 System Prompt（< 50 行）

```markdown
# Ship Pro Orchestrator v4

## Goal
将 Living Spec 转化为满足约束的 Ship Package。你自主规划执行路径。

## Core Constraints（不可违反）
1. 每次 spawn Worker 必须传 `cwd` 和 `agentId`
2. 重试前必须调用 `check-retry-limit`，allowed=false 时禁止重试
3. 每 5 分钟调用 `check-budget`，over_budget=true 时停止并汇总
4. 所有阶段完成后必须 spawn Judge Worker 独立评估
5. 偏离 Reference Plan 时，必须 `log-decision` 记录原因

## Available Capabilities
读取: `python3 $DEEPFLOW_HOME/scripts/io_helper.py list-capabilities <output_dir>`
每个 Capability 有 input_schema、output_schema、quality_dimensions、max_retries。

## Reference Plans
读取: `python3 $DEEPFLOW_HOME/scripts/io_helper.py list-plans <output_dir>`
推荐路径仅供参考，你可以选择任何 plan 或自创路径。

## Autonomy Scope
- ✅ 自主选择执行路径（遵循或偏离 Reference Plan）
- ✅ 自主判断并行执行（用 `can-parallel` 验证安全性）
- ✅ 自主跳过非必要阶段（用 `validate-coverage` 确认覆盖）
- ✅ 自主决定重试策略（受 `check-retry-limit` 约束）
- ❌ 不可跳过 required_coverage 类别
- ❌ 不可超过 budget_minutes
- ❌ 不可在 allowed=false 时重试

## Success Criteria
- `validate-coverage` 返回 valid=true
- 所有已执行阶段的 `validate-quality` 返回 pass
- Judge Worker 评估 pass
- `check-budget` 返回 over_budget=false

## Workflow
1. 读取 Living Spec + `resume-context`
2. 选择或自创执行计划 → `log-decision plan`
3. 按计划执行各 Capability（spawn Worker + validate）
4. 每完成 2 个阶段 → `compact-history`
5. 全部完成 → spawn Judge → 交叉验证
6. Judge pass → 写 `.completed`

## Reference Docs（按需读取）
- 错误恢复策略: `read $DEEPFLOW_HOME/docs/recovery_strategies.md`
- 质量评估维度: `read $DEEPFLOW_HOME/docs/quality_dimensions.md`
- Worker Prompt 模板: `read $DEEPFLOW_HOME/prompts/worker_{capability}.md`

## Few-shot: 好的执行计划示例

### 示例 1：标准需求
```json
{
  "plan": "standard",
  "reason": "Living Spec 包含完整需求，适合标准管线",
  "stages": ["architect", "decomposer", "specifier", "reviewer", "packager"],
  "parallel": [["decomposer", "reviewer"]],
  "skip": []
}
```

### 示例 2：简单改动
```json
{
  "plan": "custom",
  "reason": "仅需修改配置项，无需架构设计和分解",
  "stages": ["reviewer", "packager"],
  "parallel": [],
  "skip": ["architect", "decomposer", "specifier"],
  "skip_reasons": {
    "architect": "无架构变更",
    "decomposer": "单点修改无需分解",
    "specifier": "改动已在 Living Spec 中明确"
  }
}
```

## Reminder
- 重试前 → `check-retry-limit`
- 并行前 → `can-parallel`
- 跳过前 → `validate-coverage`
- 每 2 阶段 → `compact-history`
- 偏离计划 → `log-decision`
```

### 3.3 Prompt 架构对比

| 维度 | V3（过程式） | V4（Goal 声明式） |
|------|-------------|-----------------|
| 行数 | ~200 行 | System <50 行 + Reference Docs |
| 关键约束位置 | 淹没在 Phase 细节中 | 前置（Core Constraints）+ 后置（Reminder） |
| 执行路径 | 固定 Phase 1→5 | LLM 自主选择 |
| 详细规则 | 全部内嵌 | 外置 Reference Docs，按需读取 |
| Few-shot | 无 | 2 个示例（标准 + 简单） |
| 自主权声明 | "可以偏离但必须记录" | "你自主规划" + Autonomy Scope 明确边界 |

---

## 四、io_helper.py V4 变更

### 4.1 新增命令

| 命令 | 说明 |
|------|------|
| `list-capabilities <output_dir>` | 读取 capability-registry.json，输出可用能力列表 |
| `list-plans <output_dir>` | 输出可用的 Reference Plans |
| `increment-retry <output_dir> <stage>` | 原子自增重试计数（flock），返回 `{count, limit, allowed}` |
| `validate-coverage <output_dir>` | 检查执行计划是否覆盖 required_coverage 类别 |

### 4.2 变更命令

| 命令 | V3 | V4 |
|------|-----|-----|
| `validate-plan` | `--required architect,reviewer,packager` 硬编码 | 从 `capability-registry.json` 的 `required_coverage` 自动推导 |
| `log-decision` | 自由文本 type/outcome | 枚举 type: `plan/stage_start/stage_complete/retry/skip/parallel/escalation`；枚举 outcome: `pass/fail/skip/escalate/retry` |
| `compact-history` | 纯提取，丢决策原因 | 保留 `key_decisions` 含 `reason` + `alternatives_considered` |
| `can-parallel` | 查 `parallel_groups` | 基于 `input_schema` 依赖分析 + `parallel_hints` |

### 4.3 `increment-retry` 实现（解决 TOCTOU 竞态）

```python
def cmd_increment_retry(output_dir: str, stage: str) -> dict:
    """原子自增重试计数，使用 flock 防止竞态"""
    import fcntl
    
    state_file = os.path.join(output_dir, "pipeline_state.json")
    lock_file = os.path.join(output_dir, ".retry.lock")
    registry = load_capability_registry()
    
    with open(lock_file, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # 排他锁
        try:
            state = load_state(output_dir)
            current = state.get("stages", {}).get(stage, {}).get("retry_count", 0)
            limit = registry["capabilities"][stage]["max_retries"]
            new_count = current + 1
            allowed = new_count <= limit
            
            # 原子写入
            state.setdefault("stages", {}).setdefault(stage, {})["retry_count"] = new_count
            atomic_write(state_file, json.dumps(state, indent=2))
            
            return {
                "stage": stage,
                "retry_count": new_count,
                "max_retries": limit,
                "allowed": allowed
            }
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
```

### 4.4 `validate-coverage` 实现

```python
def cmd_validate_coverage(output_dir: str) -> dict:
    """检查执行计划是否覆盖 required_coverage 类别"""
    registry = load_capability_registry()
    required = set(registry["constraints"]["required_coverage"])
    
    state = load_state(output_dir)
    plan_stages = state.get("plan", {}).get("stages", [])
    
    covered = set()
    for stage_id in plan_stages:
        cap = registry["capabilities"].get(stage_id)
        if cap:
            covered.add(cap["category"])
    
    missing = required - covered
    
    return {
        "valid": len(missing) == 0,
        "required": list(required),
        "covered": list(covered),
        "missing": list(missing),
        "suggestion": f"需要覆盖以下能力类别: {', '.join(missing)}" if missing else "所有必需能力已覆盖"
    }
```

---

## 五、Judge Worker 差异化设计

### 5.1 V3 问题

V3 的 Judge 与 Orchestrator 使用相同 5 个评估维度 → "同一个 LLM 用同一个 prompt 评估两次" → 相同偏差。

### 5.2 V4 差异化

| 维度 | Orchestrator 自评 | Judge Worker |
|------|------------------|-------------|
| **关注点** | 产出是否满足 Living Spec | 产出是否能被**下游正确消费** |
| **评估方式** | 5 维度打分 | **对抗性**：找出 Top-3 风险 |
| **输出格式** | 维度分数 + 决策 | 风险清单 + 严重程度 + 修复建议 |

### 5.3 Judge Worker Prompt

```markdown
# Ship Package Judge

## Role
你是一个**对抗性评审员**。你的目标不是"评估质量"，而是**找出问题**。

## Task
审查以下 Ship Package，找出 **3 个最大风险**。

## Evaluation Perspective（与 Orchestrator 不同）
你不关注"产出是否满足 Living Spec"（Orchestrator 已经评估过了）。
你关注：
1. **下游可消费性**：工作包是否能被开发者直接执行？是否有遗漏的依赖或接口？
2. **单点故障**：架构中是否有单点故障？某个模块失败是否会导致整体崩溃？
3. **一致性裂缝**：不同阶段的产出之间是否存在矛盾？（如架构说用微服务，但工作包假设单体）

## Output Format
```json
{
  "verdict": "pass | conditional | fail",
  "risks": [
    {
      "id": "risk-1",
      "severity": "critical | major | minor",
      "description": "...",
      "affected_stages": ["architect", "decomposer"],
      "fix_suggestion": "..."
    }
  ],
  "cross_validation": {
    "python_gate_says": "pass | fail",
    "judge_agrees": true | false,
    "explanation": "..."
  }
}
```

## Decision Rules
- 0 critical + ≤1 major → `pass`
- 0 critical + 2+ major → `conditional`（列出修复条件）
- 1+ critical → `fail`

## Cross-Validation with Python Gate
1. 先运行 `validate-quality` 获取 Python gate 结果
2. 如果 gate=fail 但 judge=pass → 以 gate 为准（硬约束优先）
3. 如果 gate=pass 但 judge=fail → 以 judge 为准（语义问题 gate 检测不到）
4. 如果两者一致 → 直接采用

## Input
{ship_package_content}
```

---

## 六、Worker Prompt 模板 V4

### 6.1 变更：增加 `{failure_feedback}` 占位符

```markdown
# {capability_name} Worker

## Task
根据以下输入，完成 {capability_description}。

## Input
{worker_input}

## Quality Dimensions
{quality_dimensions}

## Output Format
{output_schema}

## Previous Attempt Feedback（仅重试时存在）
{failure_feedback}

如果存在上述反馈，请针对性修正，不要重复之前的错误。

## Constraints
- 输出必须严格符合 Output Format
- 不得引入 Input 中未提及的新需求
- 不确定的部分标注 `NEEDS_CLARIFICATION`
```

---

## 七、实施性 P0 修复

### 7.1 超时控制（分布式系统专家 P0-1）

**V3 问题**：`sessions_spawn(runTimeoutSeconds=300)` 参数不存在。

**V4 方案**：
- config 层：`start_ship_pro.py` 设置 `agents.defaults.subagents.runTimeoutSeconds=1800`
- 软超时：io_helper `check-budget` 中 `soft_limit_minutes` 参数
- 完成后恢复原值

### 7.2 TOCTOU 竞态（分布式系统专家 P0-2）

**V3 问题**：check-retry + write-status 非原子。

**V4 方案**：`increment-retry` 命令（见 §4.3），flock + 原子写入。

### 7.3 Announce 丢失（分布式系统专家 P1-1）

**V3 问题**：Worker announce 在 gateway 重启时丢失 → Orchestrator 永久阻塞。

**V4 方案**：Orchestrator Prompt 中增加降级策略：
```
如果 sessions_yield 后超过 Worker 预期时间 2 倍未收到 announce：
1. 调用 subagents list 检查 Worker 状态
2. 如果 Worker 已完成 → 直接读取输出文件继续
3. 如果 Worker 仍在运行 → 继续等待
4. 如果 Worker 已失败 → 按错误恢复策略处理
```

### 7.4 重试幂等性（分布式系统专家 P1-2）

**V3 问题**：重试时可能读到旧的部分输出。

**V4 方案**：
- Worker 写入使用 temp+rename（原子写入）
- `resume-context` 对 `running`/`gate_fail` 状态阶段的输出文件标记为不可信
- 重试时 `build-prompt` 不注入不可信的输出

---

## 八、开发者体验 P0 修复

### 8.1 SKILL.md V5.0 完整草稿（开发者体验专家 P0-1）

```markdown
# Ship Pro SKILL.md V5.0

## 入口守卫（Step 0 — 防偏检查）
执行前检查：
1. `agentId` 不为空
2. `maxSpawnDepth >= 2`
3. `$DEEPFLOW_HOME` 环境变量已设置
4. `capability-registry.json` 存在且可解析
任何一项不通过 → 停止并报告用户。

## Quick Start（5 步上手）
1. 读取 Living Spec
2. 运行 `start_ship_pro.py` 获取 output_dir + watcher_cron_payload
3. spawn Orchestrator（task 包含 Goal 声明式 Prompt）
4. 创建 Watcher Cron（使用 watcher_cron_payload）
5. sessions_yield() 等待完成

## 命令速查表

### I/O 类
| 命令 | 用途 |
|------|------|
| `read-stage <dir> <stage>` | 读取阶段输出 |
| `write-stage <dir> <stage> <json>` | 写入阶段输出 |
| `read-state <dir>` | 读取 pipeline_state.json |
| `write-status <dir> <stage> <status>` | 更新阶段状态 |
| `list-capabilities <dir>` | 列出可用能力 |
| `list-plans <dir>` | 列出参考计划 |

### 护栏类
| 命令 | 用途 |
|------|------|
| `check-retry-limit <dir> <stage>` | 检查重试上限 |
| `increment-retry <dir> <stage>` | 原子自增重试计数 |
| `check-budget <dir>` | 检查时间预算 |
| `validate-format <dir> <stage>` | Schema 校验 |
| `validate-quality <dir> <stage>` | 质量门控 |
| `validate-coverage <dir>` | 能力覆盖校验 |
| `can-parallel <dir> <s1> <s2>` | 并行安全检查 |

### 恢复/调试类
| 命令 | 用途 |
|------|------|
| `resume-context <dir>` | 断点恢复上下文 |
| `compact-history <dir>` | 压缩历史 |
| `log-decision <dir> <type> <stage> <reason>` | 记录决策 |
| `dump-state <dir>` | 输出完整状态 |

## 详细文档
- 能力注册表: `$DEEPFLOW_HOME/domains/ship_pro/capability-registry.json`
- 错误恢复: `$DEEPFLOW_HOME/docs/recovery_strategies.md`
- 质量维度: `$DEEPFLOW_HOME/docs/quality_dimensions.md`
- Worker Prompts: `$DEEPFLOW_HOME/prompts/worker_*.md`
```

### 8.2 `build-prompt` 调用时序（开发者体验专家 P0-2）

完整示例：

```bash
# Step 1: 准备 context JSON 文件
echo '{"living_spec": "...", "previous_outputs": {"architect": {...}}, "quality_criteria": [...]}' > /tmp/ctx-decomposer.json

# Step 2: 调用 build-prompt 生成 Worker Prompt
python3 $DEEPFLOW_HOME/scripts/io_helper.py build-prompt decomposer $OUTPUT_DIR --context-file /tmp/ctx-decomposer.json

# Step 3: 如果需要注入重试反馈
echo '{"previous_errors": ["wp-3 缺少依赖声明", "粒度不均匀"], "retry_count": 2}' > /tmp/feedback-decomposer.json
python3 $DEEPFLOW_HOME/scripts/io_helper.py build-prompt decomposer $OUTPUT_DIR --context-file /tmp/ctx-decomposer.json --feedback-file /tmp/feedback-decomposer.json

# Step 4: spawn Worker
sessions_spawn(task=<Step 2 的输出>, cwd=$DEEPFLOW_HOME, agentId=..., label="ship-decomposer")
```

---

## 九、错误恢复决策树（替代 V3 表格）

```
Worker 执行失败
├─ validate-format 失败？
│   ├─ YES → 必须重试（硬约束，不可覆盖）
│   │   └─ check-retry-limit → allowed?
│   │       ├─ YES → increment-retry → 带 feedback 重试
│   │       └─ NO → escalation（报告用户）
│   └─ NO ↓
├─ validate-quality 失败？
│   ├─ YES → 必须重试（硬约束，不可覆盖）
│   │   └─ check-retry-limit → allowed?
│   │       ├─ YES → increment-retry → 带 feedback 重试
│   │       └─ NO → 降级：format-only 通过 + 标记质量风险
│   └─ NO ↓
├─ Orchestrator 自评失败？
│   ├─ YES → 可选重试（软约束）
│   │   └─ check-retry-limit → allowed?
│   │       ├─ YES → increment-retry → 带 feedback 重试
│   │       └─ NO → 接受当前结果 + log-decision
│   └─ NO ↓
├─ 全部通过 → 进入下一阶段
│
└─ 特殊情况：
    ├─ check-budget over_budget → 停止 + 汇总已完成部分
    ├─ 同一阶段连续 3 次相同错误 → escalation
    ├─ announce 超时 → subagents list 检查 → 读取输出 / 继续等待
    └─ 并行阶段部分失败 → 保留成功结果 → 仅重做失败阶段
```

---

## 十、迁移策略（一步到位）

### 10.1 忠礼决策：一步到位，不搞渐进迁移

| 步骤 | 操作 | 风险 |
|------|------|------|
| 1 | 创建 `capability-registry.json` | 低（新文件） |
| 2 | 重写 Orchestrator Prompt（Goal 声明式） | 中（核心变更） |
| 3 | io_helper.py 新增 4 个命令 + 修改 4 个命令 | 中 |
| 4 | 写 Judge Worker Prompt（差异化视角） | 低 |
| 5 | 写 Worker Prompt 模板（含 failure_feedback） | 低 |
| 6 | 更新 `start_ship_pro.py` | 低 |
| 7 | 更新 SKILL.md V5.0 | 低 |
| 8 | 端到端测试（3 个场景） | 验证步骤 |
| 9 | 删除 `stage-dependencies.json`（不再保留兼容层） | 低 |

### 10.2 回滚方案

如果 V4 出现严重问题：
1. `git checkout` 回退到 V3 的 `stage-dependencies.json` + 过程式 Prompt
2. `start_ship_pro.py` 回退到 V3 版本
3. io_helper.py 保留 V4 新增命令（向后兼容）

---

## 十一、与忠礼决策的对齐检查

| 忠礼决策（AI Native Loop 研讨会） | V4 是否兑现 | 说明 |
|------|:---:|------|
| "全 LLM 控制，Python 不做控制流" | ✅ | LLM 自主规划路径，Python 只做验证和护栏（安全网，不是轨道） |
| "一步到位，不分阶段演进" | ✅ | 直接替换 stage-dependencies → capability-registry，无过渡期 |
| "LLM 做所有决策，Python 只做工具执行" | ✅ | 执行路径由 LLM 决定，Python 只做输入/输出验证 |
| "不懂的技术问题自己 web search" | ✅ | 3 路调研已覆盖框架趋势、控制模式、Prompt 设计 |

---

*V4 方案完成。核心改进：从"给 waterfall 加 LLM 调度器"变为"LLM 声明式规划 + 代码验证护栏"。*
