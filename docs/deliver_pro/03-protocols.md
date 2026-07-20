# Deliver Pro V1 — 通信协议

> **版本**: V1.0.0 | **日期**: 2026-07-11
> **适用范围**: Deliver Pro 所有角色间数据流

---

## 一、Blackboard 文件结构

```
blackboard/{project_name}/deliver_pro/
├── data/
│   ├── wp.json                    # Work Package（输入，不可修改）
│   ├── ship_package.md            # Ship Pro 输出（MD source of truth，如有）
│   └── constraints.json           # 全局约束（可选）
├── stages/
│   ├── execution_plan.json        # Phase 1 输出
│   ├── worker_outputs/
│   │   ├── T-001/
│   │   │   ├── DELIVERABLE.md
│   │   │   ├── EVIDENCE.md
│   │   │   ├── ISSUES.md
│   │   │   └── MANIFEST.json
│   │   ├── T-002/
│   │   │   └── ...
│   │   └── _shared/
│   │       └── glossary.json      # 共享术语表（报告场景）
│   ├── integrated_draft/          # Phase 3 输出
│   │   ├── DELIVERABLE.md         # 组装后的主产物
│   │   ├── integration_report.json
│   │   └── ...
│   ├── validation_result.json     # Phase 4 输出
│   ├── final_deliverable/         # Phase 5 输出
│   │   └── ...
│   └── delivery_manifest.json     # Phase 5 元数据
├── delivery_state.json            # 流水线状态
├── .stage_progress                # 阶段进度
├── .completed                     # 完成标记
└── .failed                        # 失败标记
```

---

## 二、数据流方向（谁读谁写）

| Stage | 写入者 | 读取者 | 格式 |
|-------|--------|--------|------|
| `data/wp.json` | 外部（Ship Pro） | 所有角色 | JSON |
| `data/ship_package.md` | Ship Pro | SmartAssembler, Package | MD |
| `execution_plan.json` | Analyze Agent | Orchestrator, Worker, Integrate | JSON |
| `worker_outputs/{id}/` | Worker | Integrate, Validate, Package | 4 文件 |
| `MANIFEST.json` | Worker | Integrate, Orchestrator | JSON |
| `glossary.json` | Analyze Agent | Worker (报告场景) | JSON |
| `integrated_draft/` | Integrate | Validate, Package | 文件集 |
| `validation_result.json` | Validate Judge | Orchestrator, Integrate | JSON |
| `final_deliverable/` | Package | 用户 | 文件集 |
| `delivery_manifest.json` | Package | Orchestrator | JSON |

**数据流铁律**：
- 每个 stage 只有一个写入者
- 读取者不修改源文件
- 文件通过 Blackboard 传递，不通过 prompt 嵌入

---

## 三、Worker 输出文件规范

### 3.1 DELIVERABLE.md（主产物）

**编程场景**：
```markdown
# {task_title}

## 1. Architecture Overview
（组件关系图 / 数据流）

## 2. Implementation
### 2.1 文件清单
| 文件 | 用途 | 行数 |
### 2.2 代码
（完整代码，按文件分节）

## 3. Testing
### 3.1 测试策略
### 3.2 测试代码
### 3.3 测试执行结果（粘贴 exec 输出）

## 4. Usage
（安装/运行/API 调用示例）

## 5. Acceptance Criteria Mapping
| AC | 对应代码位置 | 测试覆盖 | 状态 |
```

**报告场景**：
```markdown
# {task_title}

## Executive Summary
（200字以内，核心结论 + 关键数据）

## 1. Background & Scope

## 2. Analysis
### 2.1 {分析维度1}
（数据 + 来源 + 分析 + 小结）

## 3. Findings & Recommendations
（每个建议：做什么 → 为什么 → 怎么做 → 预期效果）

## 4. Risks & Assumptions

## 5. Acceptance Criteria Mapping
| AC | 对应章节 | 支撑数据 | 状态 |
```

### 3.2 EVIDENCE.md（验证证据）

```markdown
# Evidence Log

## web_search Records
| # | Query | URL | Result Summary | Timestamp |
|---|-------|-----|----------------|-----------|
| 1 | ... | ... | ... | ISO8601 |

## exec Records（编程场景）
| # | Command | Output (truncated) | Pass? | Timestamp |
|---|---------|--------------------|-------|-----------|
| 1 | pytest tests/ -v | 8 passed in 0.34s | ✅ | ISO8601 |

## Data Source Citations（报告场景）
| # | Claim | Source URL | Confidence | Fetched At |
|---|-------|-----------|------------|------------|
| 1 | 全球半导体市场 6270 亿美元 | https://... | HIGH | ISO8601 |
```

### 3.3 ISSUES.md（问题记录）

```markdown
# Issues

## Blockers
（无 / 列出阻塞问题 + 原因 + 建议）

## Partial Completions
（无 / 列出未完成的 AC + 原因 + 置信度）

## Risks
（无 / 列出已识别的风险）
```

### 3.4 MANIFEST.json（元数据）

```json
{
  "task_id": "T-001",
  "wp_id": "WP-001",
  "scenario": "code | report",
  "status": "COMPLETE | PARTIAL | BLOCKED",
  "outputs": [
    {"path": "src/auth.py", "type": "code", "checksum": "sha256:..."}
  ],
  "interfaces": {
    "provides": [{"name": "auth_router", "type": "fastapi_router"}],
    "requires": [{"name": "db_session", "from_task": "T-001"}]
  },
  "quality_self_check": {
    "acceptance_criteria_met": true,
    "tests_passed": true,
    "lint_passed": true,
    "web_search_count": 3,
    "data_sources_cited": 5,
    "issues_count": 0
  },
  "tool_calls": {"exec": 4, "web_search": 2, "read": 3, "write": 5},
  "timestamp": "ISO8601"
}
```

---

## 四、Integrate 组装协议

### 4.1 组装前检查清单

```json
{
  "pre_assembly_checks": {
    "all_outputs_exist": true,
    "all_manifests_valid": true,
    "interface_alignment": {
      "coding": "MANIFEST provides vs requires 匹配",
      "report": "术语与 glossary.json 一致"
    },
    "no_missing_dependencies": true
  }
}
```

### 4.2 组装后验证

**编程场景**：
```bash
# 集成测试
exec: cd integrated_draft && pytest tests/ -v
# 全局 lint
exec: ruff check src/
# 类型检查
exec: mypy src/
```

**报告场景**：
```python
# 术语一致性扫描
for term in glossary.forbidden_synonyms:
    assert term not in DELIVERABLE.md

# 数据交叉引用检查
for ref in cross_refs:
    assert ref.value == authoritative_source[ref.key]
```

### 4.3 integration_report.json

```json
{
  "workers_integrated": 4,
  "workers_failed": 1,
  "consistency_checks_passed": true,
  "conflicts_found": [],
  "coverage": {
    "acceptance_criteria_total": 7,
    "covered": 6,
    "gaps": ["AC-5: Worker T-003 FAILED"]
  },
  "integration_test_result": "12 passed, 0 failed",
  "status": "READY_FOR_VALIDATE"
}
```

---

## 五、Validate 反馈格式

### validation_result.json

```json
{
  "round": 1,
  "verdict": "PASS | CONDITIONAL | FAIL",
  "scores": {
    "completeness": {"score": 4, "max": 5, "weight": 0.25},
    "correctness": {"score": 4, "max": 5, "weight": 0.25},
    "consistency": {"score": 3, "max": 5, "weight": 0.10},
    "credibility": {"score": 4, "max": 5, "weight": 0.20},
    "actionability": {"score": 4, "max": 5, "weight": 0.15},
    "professionalism": {"score": 3, "max": 5, "weight": 0.05}
  },
  "weighted_score": 3.8,
  "fix_directives": [
    {
      "target": "T-003",
      "issue": "缺少错误处理",
      "fix_instruction": "在 register() 中添加 try-except，处理 duplicate email 场景",
      "priority": "high",
      "estimated_effort": "10 min"
    }
  ],
  "has_fixable": true,
  "should_continue": true,
  "should_continue_reason": "有 1 个高优先级修复项，修复后预期 completeness 提升至 5/5"
}
```

### 门禁判定规则

| 条件 | 判定 |
|------|------|
| weighted_score ≥ 3.5 且无维度 < 3 | **PASS** |
| weighted_score ≥ 3.0 且无维度 < 2 | **CONDITIONAL**（修复后复审） |
| weighted_score < 3.0 或任意维度 < 2 | **FAIL** |

### should_continue 判断（LLM 决定）

```
should_continue = true 当：
  - has_fixable = true（有可修复项）
  - 本轮 score 比上轮有提升（有进展）
  - 修复成本合理（不超过 1 轮工作量）

should_continue = false 当：
  - has_fixable = false（所有问题不可修复）
  - 本轮 score 与上轮相同（无进展 = 死循环信号）
  - 已修复 3 轮仍有问题（边际收益为零）
```

---

## 六、错误处理流程

### 6.1 Worker 故障恢复协议

```
Worker 失败
  ↓
Orchestrator 调用 LLM 诊断（不查表）：
  输入：错误信息 + WP 上下文 + 已尝试策略
  输出：{ diagnosis, recovery_action, specific_changes, confidence }
  ↓
代码执行恢复方案
  ↓
跟踪轮次（attempts < 3）
  ↓
3 轮仍失败 → 标记 FAILED + 写入 ISSUES.md
  ↓
继续其他 WP（不阻塞整体流程）
```

### 6.2 Validate Loop 错误处理

```
Validate FAIL
  ↓
检查 should_continue
  ↓
├─ true → 将 fix_directives 传给 Integrate → 修复 → 回到 Validate
├─ false → 进入 Phase 5（标记 unvalidated）
└─ 达到 5 轮 → 进入 Phase 5（标记 unvalidated）
```

### 6.3 状态机

```
INIT → ANALYZING → GENERATING → INTEGRATING → VALIDATING → PACKAGING → COMPLETED
                        ↓              ↓            ↓
                   WORKER_RETRY    FIX_LOOP    UNVALIDATED
                        ↓              ↓            ↓
                    FAILED_WP     MAX_ROUNDS     PACKAGING
                                                     ↓
                                              COMPLETED (with warnings)
                                                        ↓
                                                   FAILED (致命错误)
```

---

## 七、delivery_manifest.json（最终交付清单）

```json
{
  "wp_id": "WP-001",
  "delivery_status": "COMPLETE | PARTIAL | FAILED",
  "components": [
    {
      "task_id": "T-001",
      "title": "实现用户注册接口",
      "status": "PASS",
      "artifacts": ["src/auth/register.py", "tests/test_register.py"]
    },
    {
      "task_id": "T-003",
      "title": "实现 token 刷新",
      "status": "FAILED",
      "failure_reason": "Worker 超时，已尝试换模型重试 1 次仍失败",
      "user_actions": [
        "手动实现 token 刷新端点",
        "调整需求后重新执行",
        "仅重新执行 T-003"
      ]
    }
  ],
  "validation_summary": {
    "rounds_run": 2,
    "final_score": 3.6,
    "verdict": "CONDITIONAL"
  },
  "timestamp": "ISO8601"
}
```

---

## 八、Orchestrator 接口定义

### 8.1 核心接口

```python
class DeliverProOrchestrator:
    """Deliver Pro 调度器接口（对标 Solution Pro Coordinator）"""

    def run_pipeline(self, wp: WorkPackage) -> PipelineState:
        """启动流水线，返回最终状态"""

    def handle_worker_failure(
        self, task_id: str, error: WorkerError, attempts: int
    ) -> RecoveryAction:
        """Worker 失败时调用 LLM 诊断，返回恢复动作"""

    def decide_continue(self, validation: ValidationVerdict) -> bool:
        """判断是否继续 Validate Loop"""

    def spawn_workers(self, plan: ExecutionPlan) -> list[WorkerResult]:
        """按依赖图 + 滑动窗口 spawn Worker"""
```

### 8.2 核心数据结构

```python
@dataclass
class WorkerTask:
    """单个 Worker 任务定义（对标 Solution Pro AgentRequest）"""
    task_id: str
    wp_id: str
    title: str
    scenario: str  # "code" | "report"
    prompt: str  # 完整 prompt（含静态约束 + 动态任务）
    model: str  # 推荐模型
    timeout_seconds: int
    dependencies: list[str]  # 依赖的 task_id 列表
    forced_actions: list[str]  # 必须执行的动作
    expected_outputs: list[dict]  # 预期产出路径

@dataclass
class ValidationVerdict:
    """Validate Judge 的判定结果（对标 Solution Pro AgentResult）"""
    round: int
    verdict: str  # "PASS" | "CONDITIONAL" | "FAIL"
    scores: dict  # 6 维度评分
    weighted_score: float
    fix_directives: list[dict]  # 修复指令
    has_fixable: bool
    should_continue: bool
    should_continue_reason: str

@dataclass
class PipelineState:
    """流水线状态（对标 Solution Pro ExecutionStatus）"""
    state: str  # INIT|ANALYZING|GENERATING|INTEGRATING|VALIDATING|FIX_LOOP|PACKAGING|COMPLETED|FAILED
    wp_id: str
    current_phase: int
    completed_tasks: list[str]
    failed_tasks: list[str]
    pending_tasks: list[str]
    round_count: int
    validation_score: float | None
    error: str | None

@dataclass
class RecoveryAction:
    """Worker 恢复动作"""
    task_id: str
    diagnosis: str
    recovery_action: str  # "retry" | "switch_model" | "split_wp" | "simplify" | "skip"
    specific_changes: str
    confidence: float
```

---

## 九、状态机转换条件（形式化）

```
INIT → ANALYZING
  触发：Orchestrator.run_pipeline(wp) 被调用

ANALYZING → GENERATING
  触发：execution_plan.json 写入成功且 DAG 无环
  失败条件：execution_plan 缺失或 DAG 有环 → FAILED

GENERATING → WORKER_RETRY
  触发：任意 Worker 失败且 attempts < 3

WORKER_RETRY → GENERATING
  触发：Worker 恢复后重试

WORKER_RETRY → FAILED_WP
  触发：Worker 恢复 attempts ≥ 3 仍失败
  动作：标记 task.status = "FAILED"，继续其他 WP

GENERATING → INTEGRATING
  触发：所有 WP 完成（成功或 FAILED）

INTEGRATING → VALIDATING
  触发：integrated_draft/ 写入成功

VALIDATING → FIX_LOOP
  触发：verdict == CONDITIONAL 且 should_continue == true

FIX_LOOP → VALIDATING
  触发：Integrate 修复后重新写入 integrated_draft/

VALIDATING → PACKAGING
  触发：verdict == PASS
  或：should_continue == false
  或：round_count ≥ 5

PACKAGING → COMPLETED
  触发：final_deliverable/ + delivery_manifest.json 写入成功

任意状态 → FAILED
  触发：致命错误（Blackboard 不可写、wp.json 被篡改等）
```

---

## 十、错误传播协议

### 10.1 错误传播链

```
Worker 失败
  ↓
WorkerError(task_id, error_type, message, context)
  ↓
Orchestrator.handle_worker_failure()
  ↓
RecoveryAction(task_id, diagnosis, action, confidence)
  ↓
代码执行恢复方案
  ↓
成功 → WorkerResult 回到正常流程
失败 → attempts++ → 再次 handle_worker_failure()
  ↓
attempts ≥ 3 → FailedTask(task_id, reason, attempts, ISSUES.md 路径)
  ↓
Integrate 读取 FailedTask → 在 integration_report.json 中标记 gap
  ↓
Validate Judge 读取 gap → 影响 completeness 评分
```

### 10.2 错误对象 Schema

```json
{
  "error_type": "WORKER_FAILURE | INTEGRATION_CONFLICT | VALIDATION_FAIL | SYSTEM_ERROR",
  "task_id": "T-003",
  "message": "Worker 超时，未返回任何输出",
  "context": {
    "model": "qwen3.7-plus",
    "timeout_seconds": 300,
    "attempts": 2,
    "previous_strategies": ["retry_same", "switch_model"]
  },
  "recovery_history": [
    {"round": 1, "action": "retry_same", "result": "FAILED"},
    {"round": 2, "action": "switch_model", "result": "FAILED"}
  ]
}
```

---

## 十一、可观测性 + 检查点

### 11.1 日志级别

| 级别 | 内容 | 示例 |
|------|------|------|
| DEBUG | 每个 stage 输入输出 | "Worker T-001 输出: DELIVERABLE.md (2.3KB)" |
| INFO | 状态转换 + 分数变化 | "VALIDATING → FIX_LOOP (round 2, score 3.2→3.8)" |
| WARN | 重试 + 降级 | "Worker T-003 失败，第 2 次恢复" |
| ERROR | 致命失败 + 超时 | "Worker T-003 3 轮恢复全部失败" |

### 11.2 检查点机制

每个 stage 完成后写入 `checkpoints/stage_{name}.json`：

```json
{
  "stage": "GENERATING",
  "completed_at": "ISO8601",
  "output_path": "stages/worker_outputs/",
  "completed_tasks": ["T-001", "T-002"],
  "failed_tasks": ["T-003"],
  "state_hash": "sha256:..."
}
```

**断点续传**：如果流水线中断，Orchestrator 读取最新 checkpoint，从断点恢复。

### 11.3 调试入口

- `delivery_state.json` → 当前流水线状态
- `.stage_progress` → 阶段进度
- `worker_outputs/{id}/EVIDENCE.md` → Worker 工具调用记录
- `checkpoints/` → 各阶段快照

---

## 十二、典型执行流程示例

```
第 1 轮：启动 + 分析
├─ Orchestrator: run_pipeline(wp)
├─ 写入: data/wp.json
├─ spawn: Analyze Agent
├─ 产出: execution_plan.json (3 tasks, DAG: T-001 → T-003, T-002 → T-003)
└─ 状态: INIT → ANALYZING → GENERATING

第 2 轮：Worker 执行（滑动窗口 max=3）
├─ spawn: Worker T-001 (无依赖，立即启动)
├─ spawn: Worker T-002 (无依赖，立即启动)
├─ 等待: T-003 依赖 T-001 + T-002
├─ T-001 完成 → 写入 worker_outputs/T-001/
├─ T-002 完成 → 写入 worker_outputs/T-002/
├─ spawn: Worker T-003 (依赖已满足)
├─ T-003 失败 → handle_worker_failure() → LLM 诊断 → 重试
├─ T-003 重试成功 → 写入 worker_outputs/T-003/
└─ 状态: GENERATING → INTEGRATING

第 3 轮：集成 + 验证
├─ run: SmartAssembler (Python)
├─ 组装前检查: 3/3 outputs 存在, 接口对齐
├─ 组装后验证: exec pytest (12 passed, 0 failed)
├─ 产出: integrated_draft/ + integration_report.json
├─ spawn: Validate Judge
├─ 评分: 3.6/5.0 (CONDITIONAL)
├─ fix_directives: ["T-003 缺少错误处理"]
└─ 状态: INTEGRATING → VALIDATING → FIX_LOOP

第 4 轮：修复 + 复审
├─ run: SmartAssembler (定向重组)
├─ 修复: T-003 添加 try-except
├─ spawn: Validate Judge
├─ 评分: 4.2/5.0 (PASS)
└─ 状态: FIX_LOOP → VALIDATING → PACKAGING

第 5 轮：打包交付
├─ spawn: Package Agent
├─ 产出: final_deliverable/ + delivery_manifest.json
└─ 状态: PACKAGING → COMPLETED
```

---

## 十三、设计决策记录

| # | 决策 | 理由 | 替代方案 |
|---|------|------|----------|
| D1 | 文件 Blackboard 而非内存传递 | Agent 执行后内存丢失，文件可持久化 + 可观测 | 数据库（增加复杂度）、prompt 嵌入（截断风险） |
| D2 | 每个 stage 单一写入者 | 避免并发写冲突，数据血缘清晰 | 多写入者 + 锁机制（过度工程） |
| D3 | LLM 诊断错误而非规则查表 | 错误类型无限多，规则无法覆盖 | F1-F8 分类 + 查表（僵化，已被专家否决） |
| D4 | 4 文件输出而非单 JSON | 自由 markdown 保真率高（vs JSON 65% 保真率） | 单 JSON schema（信息丢失，Solution Pro 教训 10.4） |
| D5 | Validate Loop ≤ 5 轮 | 无限循环是设计缺陷（Solution Pro 教训） | 无上限（风险太高）、3 轮（复杂任务不够） |
| D6 | 组件级诚实交付而非降级 | "降级"是 euphemism，用户要的是诚实 | 4 级降级梯度（包装失败，用户反感） |
| D7 | cron wake 替代 sessions_yield | yield 唤醒后 LLM 可能生成文字而非 tool call | sessions_yield（有中断风险，Solution Pro 教训 10.1） |

---

## 十四、OpenClaw 约束映射

| OpenClaw 约束 | 对 Deliver Pro 的影响 | 协议层应对 |
|--------------|---------------------|------------|
| `sessions_spawn` 只能在 Agent 层调用 | Orchestrator 必须是 Agent (depth-1)，不能在 Python 中调用 | Orchestrator 用 LLM Agent 实现，Python 只做确定性工作 |
| 子 Agent 无 `openclaw` SDK | Worker 不能 `import openclaw` | Worker 通过 tool call 使用 exec/read/write，不通过 SDK |
| `sessions_yield` 唤醒风险 | 唤醒后第一个 action 必须是 tool call | 见 01-role-specifications.md §2 Yield 唤醒规则 |
| LCM 在子 Agent 不可用 | Worker 无法使用 lcm_grep/lcm_expand | Worker 不依赖 LCM，所有数据通过 Blackboard 文件传递 |
| `runTimeoutSeconds` 不可 per-call 设置 | Worker 超时由 prompt 中的 timeout 约束，非 API 参数 | Worker prompt 中包含 timeout 提示，Orchestrator 监控执行时间 |

---

*协议结束。配合 01-role-specifications.md 和 02-system-constraints.md 使用。*
