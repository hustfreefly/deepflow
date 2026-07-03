"""
Ship Pro V6 - Orchestrator

契约笼子的"执行"阶段：Orchestrator 核心实现。
遵循 AI Native 原则：
- Python 做验证（Gate 检查、状态管理）
- Agent 做调度（spawn/yield/状态机转换）
- spawn_fn 是 Agent tool，不是 Python callback

核心流程：
Phase 1: Planner (LLM 动态决策) → PlannerGate 验证
Phase 2: Workers × N (LLM 执行) → WorkerGate 验证（per worker）
Phase 3: Consolidator (LLM 整合) → InformationConservationGate + CompletenessGate + HarnessV3
"""
from pathlib import Path
from typing import Dict, Any, List, Optional
import json
import logging

from ..contracts import (
    PlannerGate,
    WorkerGate,
    InformationConservationGate,
    CompletenessGate,
    HarnessV3,
    GateResult
)

logger = logging.getLogger(__name__)


class ShipOrchestrator:
    """
    Ship Pro V6 Orchestrator
    
    职责：
    1. 管理 pipeline_state.json（单一真相源）
    2. 调用 Gate 验证每个阶段的输出
    3. 提供 spawn 参数（由 Agent 层调用 sessions_spawn）
    4. 管理状态转换（state machine）
    
    注意：
    - 本类不调用 sessions_spawn（那是 Agent 的职责）
    - 本类只返回 spawn 参数（dict），由 Agent 层实际调用
    """
    
    def __init__(self, blackboard_path: Path):
        """
        初始化 Orchestrator
        
        Args:
            blackboard_path: Blackboard 目录路径
        """
        from .state_manager import StateManager
        
        self.blackboard_path = Path(blackboard_path)
        self.state_manager = StateManager(blackboard_path)
        self.state = self.state_manager.state
        
        logger.info(f"ShipOrchestrator initialized: {blackboard_path}")
    
    # ========================================================================
    # Phase 1: Planner
    # ========================================================================
    
    def prepare_planner_spawn(self, solution_pro_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        准备 Planner 的 spawn 参数。
        
        Args:
            solution_pro_output: Solution Pro 的输出（final_solution.json）
        
        Returns:
            spawn_params: 传递给 sessions_spawn 的参数 dict
        """
        from ..contracts import get_planner_output_schema
        
        # 更新状态
        self.state_manager.update_stage("planner", "running")
        
        # 构建 prompt
        schema = get_planner_output_schema()
        prompt = self._build_planner_prompt(solution_pro_output, schema)
        
        # 返回 spawn 参数
        return {
            "runtime": "subagent",
            "mode": "run",
            "label": "ship_v6_planner",
            "task": prompt,
            "thinking": "high",
        }
    
    def verify_planner_output(self, planner_output: Dict[str, Any]) -> GateResult:
        """
        验证 Planner 输出。
        
        Args:
            planner_output: Planner 的输出（应该是 PlannerOutput dict）
        
        Returns:
            GateResult
        """
        result = PlannerGate.check(planner_output)
        
        if result.passed:
            self.state_manager.update_stage("planner", "completed")
            # 保存输出
            self.state_manager.write_stage("planner_output", planner_output)
            logger.info(f"Planner output verified: {len(planner_output['workers'])} workers")
        else:
            logger.warning(f"Planner output failed: {result.issues}")
        
        return result
    
    # ========================================================================
    # Phase 2: Workers
    # ========================================================================
    
    def prepare_workers_spawn(self, planner_output: Dict[str, Any], solution_pro_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        准备所有 Worker 的 spawn 参数。
        
        Args:
            planner_output: Planner 的输出
            solution_pro_output: Solution Pro 的输出
        
        Returns:
            List of spawn_params（每个 Worker 一个）
        """
        from ..contracts import get_worker_deliverable_schema
        
        # 更新状态
        self.state_manager.update_stage("build", "running")
        
        # 拓扑排序（分层执行）
        workers = planner_output["workers"]
        execution_layers = self._topological_sort(workers)
        
        # 为每个 Worker 构建 spawn 参数
        spawn_params_list = []
        schema = get_worker_deliverable_schema()
        
        for layer_idx, layer_workers in enumerate(execution_layers):
            for worker_spec in layer_workers:
                prompt = self._build_worker_prompt(worker_spec, solution_pro_output, schema)
                spawn_params = {
                    "runtime": "subagent",
                    "mode": "run",
                    "label": f"ship_v6_worker_{worker_spec['role']}",
                    "task": prompt,
                    "thinking": "high",
                }
                spawn_params_list.append(spawn_params)
        
        logger.info(f"Prepared {len(spawn_params_list)} workers in {len(execution_layers)} layers")
        return spawn_params_list
    
    def verify_worker_output(self, worker_spec: Dict[str, Any], worker_output: Dict[str, Any]) -> GateResult:
        """
        验证单个 Worker 的输出。
        
        Args:
            worker_spec: Worker 的规格（来自 PlannerOutput）
            worker_output: Worker 的输出（应该是 WorkerDeliverable dict）
        
        Returns:
            GateResult
        """
        result = WorkerGate.check(worker_spec, worker_output)
        
        if result.passed:
            # 保存输出
            stage_name = f"worker_{worker_spec['role']}"
            self.state_manager.write_stage(stage_name, worker_output)
            logger.info(f"Worker {worker_spec['role']} output verified")
        else:
            logger.warning(f"Worker {worker_spec['role']} output failed: {result.issues}")
        
        return result
    
    def complete_build_phase(self):
        """标记 Build 阶段完成"""
        self.state_manager.update_stage("build", "completed")
    
    # ========================================================================
    # Phase 3: Consolidator
    # ========================================================================
    
    def prepare_consolidator_spawn(self, planner_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        准备 Consolidator 的 spawn 参数。
        
        Args:
            planner_output: Planner 的输出
        
        Returns:
            spawn_params
        """
        from ..contracts import get_ship_package_schema
        
        # 更新状态
        self.state_manager.update_stage("shipper", "running")
        
        # 读取所有 Worker 输出
        worker_outputs = {}
        for worker_spec in planner_output["workers"]:
            stage_name = f"worker_{worker_spec['role']}"
            worker_output = self.state_manager.read_stage(stage_name)
            if worker_output:
                worker_outputs[worker_spec["role"]] = worker_output
        
        # 构建 prompt
        schema = get_ship_package_schema()
        prompt = self._build_consolidator_prompt(planner_output, worker_outputs, schema)
        
        return {
            "runtime": "subagent",
            "mode": "run",
            "label": "ship_v6_consolidator",
            "task": prompt,
            "thinking": "high",
        }
    
    def verify_ship_package(self, solution_pro_output: Dict[str, Any], ship_package: Dict[str, Any]) -> Dict[str, GateResult]:
        """
        验证 Ship Package（三层 Gate）。
        
        Args:
            solution_pro_output: Solution Pro 的输出
            ship_package: Consolidator 的输出（应该是 ShipPackage dict）
        
        Returns:
            Dict of GateResult（每个 Gate 一个）
        """
        results = {}
        
        # G1: 信息守恒检查
        results["information_conservation"] = InformationConservationGate.check(
            solution_pro_output, ship_package
        )
        
        # G2: 完整性检查
        results["completeness"] = CompletenessGate.check(
            solution_pro_output, ship_package
        )
        
        # G3: Harness V3
        results["harness_v3"] = HarnessV3.check(ship_package)
        
        # 综合判断
        all_passed = all(r.passed for r in results.values())
        
        if all_passed:
            self.state_manager.update_stage("shipper", "completed")
            self.state_manager.write_stage("ship_package", ship_package)
            logger.info("Ship Package verified and saved")
        else:
            failed_gates = [name for name, r in results.items() if not r.passed]
            logger.warning(f"Ship Package failed gates: {failed_gates}")
        
        return results
    
    # ========================================================================
    # Helper Methods
    # ========================================================================
    
    def _topological_sort(self, workers: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """
        拓扑排序（Kahn 算法），返回分层执行顺序。
        
        Args:
            workers: Worker 规格列表
        
        Returns:
            List of layers（每层是一个 Worker 列表）
        """
        worker_map = {w["role"]: w for w in workers}
        depends_on_map = {w["role"]: w.get("depends_on", []) for w in workers}
        
        # 计算入度
        in_degree = {role: 0 for role in worker_map}
        for role, deps in depends_on_map.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[role] += 1
        
        # 分层拓扑排序
        layers = []
        remaining = set(worker_map.keys())
        
        while remaining:
            # 找出所有入度为 0 的节点
            current_layer = [role for role in remaining if in_degree[role] == 0]
            
            if not current_layer:
                # 存在环，打破它（选择入度最小的节点）
                current_layer = [min(remaining, key=lambda r: in_degree[r])]
                logger.warning(f"Cycle detected, breaking at: {current_layer}")
            
            # 添加到当前层
            layers.append([worker_map[role] for role in current_layer])
            
            # 更新入度
            for role in current_layer:
                remaining.remove(role)
                for other_role, deps in depends_on_map.items():
                    if role in deps and other_role in remaining:
                        in_degree[other_role] -= 1
        
        return layers
    
    def _build_planner_prompt(self, solution_pro_output: Dict[str, Any], schema: Dict[str, Any]) -> str:
        """构建 Planner prompt"""
        prompt = f"""你是 Ship Pro V6 的 Planner。

## 你的任务

分析 Solution Pro 的输出，规划如何将其拆解为可执行的工作包。

## Solution Pro 输出

```json
{json.dumps(solution_pro_output, indent=2, ensure_ascii=False)}
```

## 约束笼子

### 任务边界
- 你只做"拆解+交付"，不做"设计+决策"
- Solution Pro 没说的不补充，说了的不修改

### 角色边界
- 你只规划"怎么拆"，不讨论"该不该拆"
- 不评价 Solution Pro 方案优劣

### 输出边界
- 输出必须符合 PlannerOutput Schema
- 额外建议标记为 optional_suggestion

## 输出格式（JSON Schema）

```json
{json.dumps(schema, indent=2, ensure_ascii=False)}
```

## 铁律

1. Worker 数量：2 <= N <= 8
2. 依赖图必须是无环 DAG
3. 每个 Worker 必须有约束引用（must_constraints 或 solution_pro_refs）
4. 角色名称自由命名（不需要从允许列表中选择）

## 输出

请直接输出 JSON，不要包含其他文字。
"""
        return prompt
    
    def _build_worker_prompt(self, worker_spec: Dict[str, Any], solution_pro_output: Dict[str, Any], schema: Dict[str, Any]) -> str:
        """构建 Worker prompt"""
        prompt = f"""你是 Ship Pro V6 的 Worker: {worker_spec['role']}

## 你的任务

{worker_spec['task_description']}

## Solution Pro 输出（参考）

```json
{json.dumps(solution_pro_output, indent=2, ensure_ascii=False)}
```

## 约束笼子

### 任务边界
- 你只做"拆解+交付"，不做"设计+决策"
- Solution Pro 没说的不补充，说了的不修改

### 角色边界
- 你的角色是 {worker_spec['role']}
- 只生成交付物，不讨论方案优劣
- 不修改其他 Worker 的产出

### 输出边界
- 输出必须符合 WorkerDeliverable Schema
- 额外建议标记为 optional_suggestion

## MUST 约束（从 Solution Pro 继承，不可违反）

{json.dumps(worker_spec.get('must_constraints', []), indent=2, ensure_ascii=False)}

## 输出格式（JSON Schema）

```json
{json.dumps(schema, indent=2, ensure_ascii=False)}
```

## 输出

请直接输出 JSON，不要包含其他文字。
"""
        return prompt
    
    def _build_consolidator_prompt(self, planner_output: Dict[str, Any], worker_outputs: Dict[str, Any], schema: Dict[str, Any]) -> str:
        """构建 Consolidator prompt"""
        prompt = f"""你是 Ship Pro V6 的 Consolidator。

## 你的任务

整合所有 Worker 的产出，生成最终的 Ship Package。

## Planner 的整合策略

{planner_output.get('integration_strategy', '（未指定）')}

## Worker 产出

{json.dumps(worker_outputs, indent=2, ensure_ascii=False)}

## 约束笼子

### 任务边界
- 你只做"整合"，不做"设计+决策"
- 不增加新 WP 或新需求
- 不删减已有产出

### 角色边界
- 你只汇总已有产出
- 冲突时选择与 Solution Pro 更一致的方案

### 输出边界
- 输出必须符合 ShipPackage Schema
- optional_suggestion 物理隔离到 metadata.optional_suggestions

## 输出格式（JSON Schema）

```json
{json.dumps(schema, indent=2, ensure_ascii=False)}
```

## 输出

请直接输出 JSON，不要包含其他文字。
"""
        return prompt
