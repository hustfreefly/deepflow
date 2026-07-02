# Solution Pro V2 回滚方案

> 版本: V3.0.0 | 日期: 2026-06-28 | 作者: DeepFlow Solution Pro

---

## 一、触发条件

满足以下**任一条件**即触发回滚评估：

| # | 触发条件 | 检测方式 | 阈值 |
|---|---------|---------|------|
| 1 | V2 连续执行失败 | `v2/pipeline_metrics.json` 中 `status=FAILED` 连续计数 | ≥ 3 次 |
| 2 | Gate A/B 连续 FAIL | ReviewQC 模块 `final_verdict=FAIL` 连续计数 | ≥ 3 次 |
| 3 | 方案质量下降投诉 | 用户反馈 / 评分低于 V1 基线 | 用户显式投诉 |
| 4 | 模块超时频繁 | 单模块超时降级占比 > 50% | 最近 5 次执行 |
| 5 | 数据一致性异常 | blackboard 文件损坏或 schema 不匹配 | 任意 1 次 |

### 自动检测逻辑

```python
# 伪代码：回滚触发检测
def should_rollback():
    metrics = load("v2/pipeline_metrics.json")
    
    # 条件 1: 连续 3 次失败
    if metrics.get("consecutive_failures", 0) >= 3:
        return True
    
    # 条件 2: Gate A/B 连续 FAIL
    review_qc = load("v2/review_qc_output.json")
    if review_qc.get("consecutive_fail verdicts", 0) >= 3:
        return True
    
    # 条件 3: 用户投诉（由主 Agent 捕获）
    if user_complaint_about_quality():
        return True
    
    return False
```

---

## 二、回滚步骤

### Step 1: 恢复 `__init__.py` 指向 V1

```bash
# 备份当前 V2 入口
cp domains/solution_pro/__init__.py domains/solution_pro/__init__.py.v2.bak

# 恢复 V1 入口（移除 run_solution_pro 导出）
# 手动编辑 __init__.py：
#   1. 将 __all__ 改回 ['run_solution_pro']
#   2. 注释掉 run_solution_pro 函数体（保留代码但不导出）
#   3. 或直接从 git 恢复 V1 版本
git checkout HEAD~1 -- domains/solution_pro/__init__.py
```

### Step 2: 恢复 SKILL.md 为 V4.4

```bash
# 如果 SKILL.md 已更新为 V5（V2 入口），恢复为 V4.4
git checkout HEAD~1 -- docs/skills/solution-pro/SKILL.md
# 或手动修改入口说明，将 run_solution_pro 改回 run_solution_pro
```

### Step 3: 通知用户

```python
# 通过飞书/消息通知用户回滚已执行
notification = {
    "type": "system_rollback",
    "module": "solution_pro",
    "from_version": "V2 (3.0.0)",
    "to_version": "V1 (2.2.0)",
    "reason": "连续执行失败 / 质量下降 / 用户投诉",
    "action_taken": "入口已恢复为 run_solution_pro()",
    "data_preserved": True,
}
# 调用 message tool 发送通知
```

### Step 4: 验证回滚成功

```bash
# 验证 V1 入口可用
cd .deepflow
python3 -c "from domains.solution_pro import run_solution_pro; print('V1 OK')"

# 验证 V2 入口已禁用（可选）
python3 -c "from domains.solution_pro import run_solution_pro" 2>&1 | grep -q "ImportError" && echo "V2 disabled OK"
```

---

## 三、数据一致性

### V2 已生成的 blackboard 文件处理

| 文件类型 | 处理方式 | 说明 |
|---------|---------|------|
| `v2/master_state.json` | **保留** | V2 状态文件，不影响 V1 |
| `v2/planning_output.json` | **保留** | V2 模块输出，V1 不读取 |
| `v2/research_output.json` | **保留** | V2 模块输出，V1 不读取 |
| `v2/review_qc_output.json` | **保留** | V2 模块输出，V1 不读取 |
| `v2/pipeline_metrics.json` | **保留** | V2 指标，可用于事后分析 |
| `execution_plan.json` (V1) | **保留** | V1 执行计划，V1 续跑使用 |
| `stages/` 目录 | **保留** | V1 阶段输出，V1 续跑使用 |
| `tasks.json` | **保留** | V1 任务定义 |
| `control_contract.json` | **保留** | V1 控制契约 |

### V1 续跑策略

V1 续跑时从 checkpoint 恢复，不依赖 V2 文件：

```python
# V1 续跑逻辑（已内置于 orchestrator_agent.py）
def resume_v1_from_checkpoint(session_id):
    """
    V1 续跑：从 execution_plan.json 和 stages/ 目录恢复
    不读取 v2/ 目录下的任何文件
    """
    bm = BlackboardManager(session_id, base_dir=...)
    
    # 读取 V1 执行计划
    plan = bm.read_json("execution_plan.json")
    
    # 检查已完成阶段
    completed_stages = []
    for stage in plan["stages"]:
        stage_dir = f"stages/{stage['stage_id']}"
        if bm.exists(f"{stage_dir}/output.json"):
            completed_stages.append(stage["stage_id"])
    
    # 从下一个未完成阶段继续
    return plan, completed_stages
```

### 隔离保证

- **V1 和 V2 的 blackboard 文件完全隔离**
  - V1: `execution_plan.json`, `stages/`, `tasks.json`, `control_contract.json`
  - V2: `v2/master_state.json`, `v2/*_output.json`, `v2/pipeline_metrics.json`
- **回滚不会丢失 V2 数据**（文件保留，只是入口切换回 V1）
- **V1 续跑不依赖 V2 数据**（V1 只读取自己的 checkpoint 文件）

---

## 四、回滚决策树

```
V2 执行失败
  ├─ 首次失败 → 重试（最多 2 次）
  ├─ 连续 2 次失败 → 检查错误日志，尝试修复
  ├─ 连续 3 次失败 → 触发回滚
  │   ├─ 通知用户
  │   ├─ 切换入口到 V1
  │   ├─ 保留 V2 blackboard 数据
  │   └─ V1 从 checkpoint 续跑
  └─ 用户投诉质量 → 立即回滚（不等 3 次）
```

---

## 五、回滚后恢复路径

回滚到 V1 后，如需重新尝试 V2：

1. 分析 V2 失败根因（查看 `v2/pipeline_metrics.json` 和错误日志）
2. 修复 V2 代码（不修改 V1 文件）
3. 在测试环境验证 V2 修复
4. 重新切换入口到 V2（`__init__.py` 导出 `run_solution_pro`）
5. 清理旧的 V2 blackboard 数据（可选）

---

> **记忆锚点**：
> "V2 失败三次就回滚，V1 续跑从 checkpoint"
> "数据隔离不丢失，入口切换保平安"
