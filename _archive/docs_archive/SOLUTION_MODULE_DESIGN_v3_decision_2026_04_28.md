# Solution模块设计文档（V3.0 - 决策确认版）

> **版本**: v3.0  
> **日期**: 2026-04-28  
> **状态**: 决策确认，待开发  
> **目标**: 通用解决方案设计模块，支持Quick/Standard/Pro三种模式

---

## 1. 模块定位

### 1.1 三种模式

| 模式 | 适用场景 | 执行时间 | Agent数 | 特点 |
|:---|:---|:---:|:---:|:---|
| **Quick** | 方案预览、初步思路 | 2-3分钟 | 3个 | 快速、轻量 |
| **Standard** | 一般架构设计 | 8-15分钟 | 3-4个 | 平衡质量与时效 |
| **Pro** | 复杂企业级方案 | 58-70分钟 | 13+个 | 深度研究、多重质量保障 |

### 1.2 输入模式

- **用户提供**: 完备的需求文档（Markdown格式，字数不限）
- **可选提取**: 前缀（用于session命名）
- **约束条件**: 可选（预算、周期、合规等）
- **利益相关者**: 可选

---

## 2. 入口与调用方式

### 2.1 显式入口（已确认）

**Python API**:
```python
from domains.solution import SolutionExecutor

executor = SolutionExecutor(
    topic="需求文档内容",
    solution_type="architecture",  # 或 "business", "technology"
    mode="pro",  # 显式指定: "quick" | "standard" | "pro"
    session_prefix="项目名称",
    constraints=["约束1", "约束2"],
    stakeholders=["角色1", "角色2"]
)

result = await executor.run()
```

**CLI入口**（预留）:
```bash
# 未来支持
openclaw solution --mode=pro --file requirements.md
```

### 2.2 模式选择逻辑（未来增强）

```python
# 自动推荐（非MVP）
planner = PlannerAgent()
complexity = planner.assess_complexity(requirements)
# complexity: "simple" | "medium" | "complex"

if complexity == "complex":
    recommended_mode = "pro"
    print("建议使用Pro模式（复杂度：高）")
    # 用户确认后执行
```

---

## 3. 整体架构

### 3.1 架构层次

```
┌─────────────────────────────────────────────────────────────┐
│  主Agent（depth-0）                                          │
│  └─ sessions_spawn → SolutionExecutor Agent                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  SolutionExecutor（depth-1）                                 │
│  ├─ 模式选择（mode参数决定）                                 │
│  ├─ Agent调度（动态选择Agent组合）                          │
│  └─ sessions_spawn → Workers（depth-2）                     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Workers（depth-2）                                          │
│  └─ 真实执行 + Blackboard写入                               │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 核心组件

| 组件 | 职责 | 文件 |
|:---|:---|:---|
| **SolutionExecutor** | 入口、模式选择、Agent调度 | `domains/solution/executor.py` |
| **SolutionProPipeline** | Pro模式8阶段管线 | `domains/solution/pro_pipeline.py` |
| **Planner** | 元调度器、动态Agent选择 | `domains/solution/planner.py` |
| **AgentLibrary** | Agent配置库 | `domains/solution/agent_library.yaml` |
| **Harness** | 修复环节质量控制 | `domains/solution/harness_check_planner.py` |
| **ProgressTracker** | 进度跟踪 | `domains/solution/progress_tracker.py` |
| **Blackboard** | 数据持久化 | 复用 `blackboard_manager.py` |

---

## 4. Pro模式详细设计

### 4.1 8阶段流程

```
Stage 1: Planner定任务（3min，动态调整）
    ├─ 输入：需求文档
    ├─ 分析：任务特征、复杂度、关键领域
    ├─ 输出：任务计划 + Agent组合方案
    └─ 写入：Blackboard/stage_01/

Stage 2: 评审组并行（5min，3 Agent并行）
    ├─ 完备性评审Agent（需Search）
    ├─ 合理性评审Agent（需Search）
    └─ 权重评审Agent（2min，无需Search）
    └─ 输出：评审意见（P0/P1/P2/P3分级）

Stage 3: Planner修复 + Harness检查（5min）
    ├─ 修复P0/P1问题
    ├─ Harness检查（质量 + 防发散）
    └─ Harness失败 → 标记风险，继续执行
    └─ 输出：修复后的最终计划

Stage 4: Research组并行（10min，关键路径）
    ├─ 技术方案Researcher + Search
    ├─ 业界实践Researcher + Search
    ├─ 风险合规Researcher + Search
    └─ 输出：研究报告（带引用）

Stage 5: 专家汇总（5min，压缩）
    ├─ 整合3份Research报告
    ├─ 解决冲突、去重
    └─ 输出：统一研究报告

Stage 6: 审计组并行（10min，可与Stage 4部分并行）
    ├─ 架构审计Agent
    ├─ 技术审计Agent
    └─ 成本审计Agent
    └─ 输出：审计意见（P0/P1/P2/P3）

Stage 7: 专家修复 + Harness检查（10min）
    ├─ 修复P0/P1问题
    ├─ Harness检查（质量 + 防发散）
    └─ Harness失败 → 标记风险，继续执行
    └─ 输出：修复后的最终方案

Stage 8: Summary输出（10min）
    ├─ 按模板格式化
    ├─ 固定部分 + 灵活内容
    └─ 输出：最终交付文档
```

**优化后总时长**: 58分钟（原70分钟）

### 4.2 并发控制

**最大并发**: 6个Agent

**并发分配**:
```python
MAX_CONCURRENT_AGENTS = 6
semaphore = asyncio.Semaphore(MAX_CONCURRENT_AGENTS)

# Stage 2: Reviewer组 3个并行
# Stage 4: Researcher组 3个并行  
# Stage 6: Auditor组 3个并行
# 其他阶段：串行
```

---

## 5. 错误处理与降级策略（已确认）

### 5.1 错误处理层级

| 层级 | 策略 | 处理方式 |
|:---|:---|:---|
| **Agent级** | 容忍单点失败 | 1个Reviewer失败，用剩余2个继续 |
| **阶段级** | 关键阶段失败终止 | Stage 4全部Researcher失败 → 流程终止 |
| **Harness级** | 失败标记风险 | Harness检查失败 → 标记风险，继续执行 |
| **整体级** | 终止并报告 | 返回已完成的中间结果 + 失败原因 |

### 5.2 降级策略（MVP后实现）

```python
# 当前：终止并报告
if critical_stage_failed:
    return {
        "status": "failed",
        "completed_stages": [...],
        "failed_stage": "stage_04",
        "reason": "All researchers failed",
        "partial_result": {...}  # 已完成的中间结果
    }

# 未来：支持降级到Standard模式
if pro_failed and user_allows_fallback:
    return run_standard_mode()  # 降级继续
```

### 5.3 熔断机制

```python
CIRCUIT_BREAKER_THRESHOLD = 3  # 连续3个阶段失败

if consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
    return {
        "status": "circuit_breaker_open",
        "message": "连续多个阶段失败，建议检查输入或降级到Standard模式"
    }
```

---

## 6. 输出交付机制（已确认）

### 6.1 MVP阶段

**Blackboard目录**:
```
blackboard/{session_id}/
├── stage_01_planner_output.json
├── stage_02_reviewers/
│   ├── reviewer_completeness_output.json
│   ├── reviewer_reasonableness_output.json
│   └── reviewer_weight_output.json
├── stage_03_fixer_planner_output.json
├── stage_04_researchers/
│   ├── researcher_tech_output.json
│   ├── researcher_practice_output.json
│   └── researcher_risk_output.json
├── stage_05_consolidator_output.json
├── stage_06_auditors/
│   ├── auditor_architecture_output.json
│   ├── auditor_technology_output.json
│   └── auditor_cost_output.json
├── stage_07_fixer_expert_output.json
├── stage_08_summarizer_output.md  # 最终报告
├── harness_check_planner.json     # Harness检查结果
├── harness_check_expert.json      # Harness检查结果
├── progress.json                  # 进度跟踪
└── final_result.json              # 汇总结果
```

**final_result.json**:
```json
{
  "status": "completed",  // or "failed", "partial"
  "mode": "pro",
  "session_id": "...",
  "total_duration_min": 58,
  "stages_completed": 8,
  "stages_failed": 0,
  "harness_warnings": [
    {"stage": 3, "issue": "P1修复率不足", "recommendation": "pass_with_warning"}
  ],
  "output_path": "blackboard/{session_id}/stage_08_summarizer_output.md",
  "report_url": "..."  // 飞书文档链接（未来）
}
```

### 6.2 未来增强

**自动创建飞书文档**:
```python
# 读取summarizer_output.md
# 调用feishu_doc创建文档
# 返回文档链接
```

---

## 7. 状态监控与进度反馈（已确认）

### 7.1 日志输出（复用Investment模式）

```
[Solution Pro] Session: xxx_architecture_abc123
[Solution Pro] Mode: pro, Estimated: 58min

[Stage 1/8] Planner定任务... ⏳
[Stage 1/8] ✅ Completed (3min)

[Stage 2/8] 评审组并行... ⏳
  [reviewer_completeness] Spawning...
  [reviewer_reasonableness] Spawning...
  [reviewer_weight] Spawning...
  [reviewer_completeness] ✅ Completed
  [reviewer_reasonableness] ✅ Completed
  [reviewer_weight] ✅ Completed
[Stage 2/8] ✅ Completed (5min)

...

[Solution Pro] ✅ All stages completed (58min)
[Solution Pro] Output: blackboard/xxx/stage_08_summarizer_output.md
```

### 7.2 进度文件（增强）

**progress.json**（每阶段更新）:
```json
{
  "session_id": "xxx",
  "mode": "pro",
  "current_stage": 4,
  "total_stages": 8,
  "stage_name": "researchers",
  "status": "running",  // pending, running, completed, failed
  "agents": {
    "researcher_tech": {"status": "completed", "duration": 420},
    "researcher_practice": {"status": "running", "duration": 180},
    "researcher_risk": {"status": "pending"}
  },
  "elapsed_min": 18,
  "estimated_remaining_min": 40,
  "updated_at": "2026-04-28T22:30:00Z"
}
```

---

## 8. 资源配额与成本控制

### 8.1 Token上限（预留）

```python
PRO_MODE_TOKEN_LIMIT = 500_000  # 500K tokens

# 执行前预估
estimated_tokens = planner.estimate_cost(requirements)
if estimated_tokens > PRO_MODE_TOKEN_LIMIT:
    print(f"Warning: Estimated {estimated_tokens} tokens exceeds limit {PRO_MODE_TOKEN_LIMIT}")
    print("Options: 1) Proceed anyway 2) Use Standard mode")
```

### 8.2 超时控制

```python
STAGE_TIMEOUTS = {
    "planner": 300,           # 5min
    "reviewers": 300,         # 5min
    "fixer_planner": 300,     # 5min
    "researchers": 600,       # 10min
    "consolidator": 300,      # 5min
    "auditors": 600,          # 10min
    "fixer_expert": 600,      # 10min
    "summarizer": 600         # 10min
}
```

---

## 9. 测试策略

### 9.1 测试分层

| 层级 | 内容 | 工具 |
|:---|:---|:---|
| **单元测试** | 每个Agent独立测试 | pytest + mock |
| **集成测试** | 阶段间数据流测试 | pytest + temp Blackboard |
| **端到端测试** | 完整Pro流程 | 固定测试用例 |
| **基准测试** | Pro vs Standard质量对比 | 相同输入对比 |

### 9.2 固定测试用例

```python
TEST_CASES = [
    {
        "name": "电商平台",
        "requirements": "设计一个支持100万日活的跨境电商系统...",
        "expected_duration_range": [50, 70],  # minutes
        "expected_quality_score": ">=80"
    },
    {
        "name": "金融核心系统",
        "requirements": "设计一个银行核心账务系统...",
        "expected_duration_range": [50, 70],
        "expected_quality_score": ">=85"
    }
]
```

---

## 10. 复用组件（具体实现）

| 组件 | 来源 | 复用方式 | 具体实现 |
|:---|:---|:---|:---|
| **SolutionExecutor** | 本次重构 | 扩展支持Pro模式 | 新增`mode`参数，根据mode调用不同Pipeline |
| **SolutionOrchestratorV3** | 现有 | Planner阶段使用 | 复用`get_tasks()`方法，扩展动态Agent选择逻辑 |
| **BlackboardManager** | 现有 | 统一存储 | 复用`write()`/`read()`方法，路径：`blackboard/{session_id}/` |
| **web_fetch工具** | OpenClaw | Search替代方案 | Agent通过Prompt指令使用，非代码import |
| **sessions_spawn** | OpenClaw | Agent调用 | 标准spawn接口，timeout/scopes参数 |
| **ProgressTracker** | 新增 | 进度跟踪 | 写入progress.json，主Agent可轮询 |

---

## 11. 附录

### 11.1 Agent清单（13个）

| # | Agent ID | 阶段 | Search | 超时 |
|:---:|:---|:---:|:---:|:---:|
| 1 | planner_pro | 1 | ❌ | 5min |
| 2 | reviewer_completeness | 2 | ✅ | 5min |
| 3 | reviewer_reasonableness | 2 | ✅ | 5min |
| 4 | reviewer_weight | 2 | ❌ | 2min |
| 5 | fixer_planner | 3 | ❌ | 5min |
| 6 | researcher_tech | 4 | ✅ | 10min |
| 7 | researcher_practice | 4 | ✅ | 10min |
| 8 | researcher_risk | 4 | ✅ | 10min |
| 9 | consolidator | 5 | ❌ | 5min |
| 10 | auditor_architecture | 6 | ✅ | 10min |
| 11 | auditor_technology | 6 | ✅ | 10min |
| 12 | auditor_cost | 6 | ✅ | 10min |
| 13 | fixer_expert | 7 | ❌ | 10min |
| 14 | summarizer_pro | 8 | ❌ | 10min |

### 11.2 参考文档

- Agent与Prompt设计: `docs/SOLUTION_AGENT_PROMPT_DESIGN.md`
- Pro模式详细设计: `docs/SOLUTION_PRO_MODE_DESIGN.md`
- Harness检查脚本: `domains/solution/harness_check_planner.py`

---

**文档版本**: v3.0（决策确认版）  
**决策状态**: 已确认  
**下一步**: 开发实现
