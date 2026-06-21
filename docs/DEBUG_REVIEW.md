# 深度预演报告

## 已修复的问题

| 问题 | 修复 | 文件 |
|------|------|------|
| 启动方式错误 | 更新契约 + 文档 | cage/orchestrator_agent.yaml, docs/LAUNCH_PROTOCOL.md |
| 环境变量未传递 | 添加 env 参数 | docs/LAUNCH_PROTOCOL.md |
| _do_spawn_agent 参数错误 | agent_id → label | pipeline_engine.py |
| ConfigLoader 不支持 data_manager | 添加 SUPPORTED_ROLES | config_loader.py |
| DataManager task 构建不完整 | 添加 session_id 等参数 | pipeline_engine.py |

## 新发现的问题

### 问题 1: PipelineEngine 没有迭代循环（P0）

**现象**: `_run_pipeline()` 只有一个 `for stage in stages` 循环，没有外部迭代循环。

**后果**: 
- 所有 stages 只执行一次
- 没有 verifier → fixer → auditor 的迭代收敛
- max_iterations 配置无效

**代码位置**: pipeline_engine.py:215

```python
def _run_pipeline(self) -> PipelineResult:
    for stage in self._pipeline.stages:  # ← 只遍历一次
        result = self._execute_stage_with_resilience(stage)
        # ... 收敛检查 ...
        if converged:
            break
```

**预期行为**:
```python
def _run_pipeline(self) -> PipelineResult:
    for iteration in range(max_iterations):  # ← 迭代循环
        for stage in self._pipeline.stages:
            result = self._execute_stage_with_resilience(stage)
            # ... 收敛检查 ...
        if converged:
            break
```

**影响**: 这是 V2.0 的核心功能缺失。没有迭代收敛，质量无法保证。

### 问题 2: _run_parallel_stage 未实现并行（P1）

**现象**: `_run_parallel_stage()` 只 spawn 一个 Agent，没有等待多个 Agent。

**代码位置**: pipeline_engine.py:446

```python
def _run_parallel_stage(self, stage: PipelineStage) -> StageResult:
    agent_id = self.spawn_agent(stage)  # ← 只 spawn 一个
    return StageResult(...)
```

**预期行为**: spawn 多个 Agent，等待所有完成，合并结果。

### 问题 3: _wait_for_worker_completion 文件路径不一致（P1）

**现象**: 检查 `stages/{stage.id}_output.json`，但 DataManager 可能写入不同路径。

## 建议

1. **立即修复**: PipelineEngine 迭代循环（核心功能缺失）
2. **可选修复**: _run_parallel_stage 并行逻辑
3. **可选修复**: _wait_for_worker_completion 路径统一

## 修复方案

在 `_run_pipeline()` 中添加外部迭代循环：

```python
def _run_pipeline(self) -> PipelineResult:
    for iteration in range(self._domain_config.max_iterations):
        self._iteration = iteration
        
        for stage in self._pipeline.stages:
            # ... 执行 stage ...
            
        # 收敛检查
        if converged:
            break
```

但这会影响所有 stages 的执行顺序。需要更细致的设计：
- 第一轮：data_manager → planner → researchers → auditors → fixer → verifier
- 后续轮：fixer → verifier（跳过 data_manager/planner/researchers）

或者，将迭代逻辑限制在特定 stages（audit/fix/verify）。

## 结论

**当前状态**: PipelineEngine 可以顺序执行所有 stages（包括 DataManager），但没有迭代收敛。

**决策 needed**: 是否要现在修复迭代循环？还是先用单轮执行验证基本功能？
