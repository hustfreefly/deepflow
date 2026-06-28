"""
Module Orchestrator 基类

Version: 1.0.0
Author: DeepFlow Solution Pro
Date: 2026-06-28

描述:
- 模块 Orchestrator 基类（代码驱动，非 LLM）
- 按顺序执行 Stage 序列
- 管理 state.json（当前 stage、retry 计数）
- 调用 Harness Agent 做 Gate check
- 生成收敛点文件

设计原则:
- 代码控制流程（确定性逻辑）
- LLM 负责内容（Stage 内部）
- 不直接调用 OpenClaw（由主 Agent spawn）
"""

import json
import logging
from typing import Any, Callable, Optional
from pathlib import Path

from .blackboard import BlackboardManager, STAGE_PATH_REGISTRY

logger = logging.getLogger(__name__)


class ModuleOrchestrator:
    """
    模块 Orchestrator 基类（代码驱动，非 LLM）
    
    职责：
    - 按顺序执行 Stage 序列
    - 管理 state.json（当前 stage、retry 计数）
    - 调用 Harness Agent 做 Gate check
    - 生成收敛点文件
    
    子类需实现：
    - stage_sequence(): 定义模块内的 Stage 序列
    - generate_convergence(): 生成收敛点文件
    """
    
    def __init__(
        self,
        module_name: str,
        session_id: str,
        spawn_fn: Optional[Callable] = None,
    ):
        """
        初始化 Module Orchestrator
        
        Args:
            module_name: 模块名称（如 "planning", "research", "review_qc"）
            session_id: Session ID
            spawn_fn: spawn 函数（由主 Agent 注入，用于 spawn Worker）
        """
        self.module_name = module_name
        self.session_id = session_id
        self.spawn_fn = spawn_fn
        
        # 初始化 BlackboardManager
        self.blackboard = BlackboardManager(session_id)
        
        # 加载或初始化 state
        self.state = self._load_or_init_state()
        
        logger.info(f"ModuleOrchestrator initialized: {module_name} (session: {session_id})")
    
    def _load_or_init_state(self) -> dict:
        """加载或初始化 state.json"""
        state_path = f"module_{self.module_name}_state.json"
        
        try:
            state = self.blackboard.read(state_path)
            logger.info(f"Loaded existing state for {self.module_name}")
            return state
        except Exception:
            # 初始化新 state
            state = {
                "module_name": self.module_name,
                "session_id": self.session_id,
                "current_stage": None,
                "completed_stages": [],
                "failed_stages": [],
                "retry_count": {},  # {stage_name: count}
                "convergence_generated": False,
            }
            self.blackboard.write(state_path, state)
            logger.info(f"Initialized new state for {self.module_name}")
            return state
    
    def _save_state(self):
        """保存 state.json"""
        state_path = f"module_{self.module_name}_state.json"
        self.blackboard.write(state_path, self.state)
    
    def stage_sequence(self) -> list[dict]:
        """
        定义模块内的 Stage 序列（子类必须实现）
        
        Returns:
            Stage 列表，每个 Stage 是 dict，包含：
            - name: Stage 名称
            - worker_type: Worker 类型（如 "meta_planner", "expert_planner"）
            - gate_check: 是否需要 Gate check（可选，默认 False）
            - parallel: 是否并行执行（可选，默认 False）
            - max_workers: 并行 Worker 最大数量（可选）
        
        Example:
            return [
                {"name": "data_collection", "worker_type": "data_collector"},
                {"name": "requirements", "worker_type": "requirements_analyzer"},
                {"name": "meta_planning", "worker_type": "meta_planner", "gate_check": True},
                {"name": "expert_planning", "worker_type": "expert_planner", "parallel": True, "max_workers": 5},
                {"name": "convergence_planning", "worker_type": "convergence_planner", "gate_check": True},
            ]
        """
        raise NotImplementedError("Subclass must implement stage_sequence()")
    
    def generate_convergence(self) -> dict:
        """
        生成收敛点文件（子类必须实现）
        
        Returns:
            收敛点数据（dict）
        """
        raise NotImplementedError("Subclass must implement generate_convergence()")
    
    def execute_stage(self, stage: dict) -> dict:
        """
        执行单个 Stage
        
        Args:
            stage: Stage 配置 dict
        
        Returns:
            Stage 输出数据（dict）
        """
        stage_name = stage["name"]
        worker_type = stage["worker_type"]
        
        logger.info(f"Executing stage: {stage_name} (worker: {worker_type})")
        
        # 更新 state
        self.state["current_stage"] = stage_name
        self._save_state()
        
        # 构建 Worker task（子类可覆盖）
        task = self._build_worker_task(stage)
        
        # Spawn Worker（如果提供了 spawn_fn）
        if self.spawn_fn:
            result = self.spawn_fn(
                task=task,
                mode="run",
                label=f"{self.module_name}_{stage_name}",
            )
            
            # 读取 Worker 输出
            output_path = STAGE_PATH_REGISTRY.get(stage_name, f"stages/{stage_name}.json")
            output = self.blackboard.read(output_path)
        else:
            # 本地执行（用于测试或简单 Stage）
            output = self._execute_local(stage)
        
        # 更新 state
        if stage_name not in self.state["completed_stages"]:
            self.state["completed_stages"].append(stage_name)
        self._save_state()
        
        logger.info(f"Stage completed: {stage_name}")
        return output
    
    def _build_worker_task(self, stage: dict) -> str:
        """
        构建 Worker task（子类可覆盖）
        
        Args:
            stage: Stage 配置 dict
        
        Returns:
            Worker task 字符串
        """
        # 默认实现：简单 task 模板
        stage_name = stage["name"]
        worker_type = stage["worker_type"]
        
        task = f"""
你是一个 {worker_type} Worker。

## 你的任务
执行 {stage_name} 阶段，并将输出写入 Blackboard。

## 输出路径
{STAGE_PATH_REGISTRY.get(stage_name, f"stages/{stage_name}.json")}

## Session ID
{self.session_id}

请完成任务并将输出写入指定路径。
"""
        return task
    
    def _execute_local(self, stage: dict) -> dict:
        """
        本地执行 Stage（子类可覆盖）
        
        Args:
            stage: Stage 配置 dict
        
        Returns:
            Stage 输出数据（dict）
        """
        # 默认实现：返回空 dict
        logger.warning(f"Local execution not implemented for {stage['name']}, returning empty dict")
        return {}
    
    def run_harness_agent(self, stage_name: str, stage_output: dict) -> dict:
        """
        调用 Harness Agent 做 Gate check
        
        Args:
            stage_name: Stage 名称
            stage_output: Stage 输出数据
        
        Returns:
            Harness Agent 输出（包含 gate_a, gate_b, final_verdict）
        """
        logger.info(f"Running Harness Agent for stage: {stage_name}")
        
        # 读取 Gate 配置（从 meta_planning 输出）
        try:
            expert_manifest = self.blackboard.read("stages/meta_planning.json")
            gate_a_config = expert_manifest.get("gate_a", {})
            gate_b_config = expert_manifest.get("gate_b", {})
            verdict_policy = expert_manifest.get("verdict_policy", {})
        except Exception as e:
            logger.warning(f"Failed to load Gate config: {e}, using defaults")
            gate_a_config = {}
            gate_b_config = {}
            verdict_policy = {}
        
        # Spawn Harness Agent（如果提供了 spawn_fn）
        if self.spawn_fn:
            task = self._build_harness_task(stage_name, stage_output, gate_a_config, gate_b_config)
            result = self.spawn_fn(
                task=task,
                mode="run",
                label=f"harness_{stage_name}",
            )
            
            # 读取 Harness Agent 输出
            harness_output = self.blackboard.read(f"stages/harness_{stage_name}.json")
        else:
            # 本地计算（用于测试）
            harness_output = self._run_harness_local(stage_output, gate_a_config, gate_b_config)
        
        return harness_output
    
    def _build_harness_task(
        self,
        stage_name: str,
        stage_output: dict,
        gate_a_config: dict,
        gate_b_config: dict,
    ) -> str:
        """构建 Harness Agent task"""
        task = f"""
你是一个 Harness Agent。你的任务是对 Stage 输出进行质量评估。

## Stage 名称
{stage_name}

## Stage 输出
```json
{json.dumps(stage_output, indent=2, ensure_ascii=False)}
```

## Gate A 配置
```json
{json.dumps(gate_a_config, indent=2, ensure_ascii=False)}
```

## Gate B 配置
```json
{json.dumps(gate_b_config, indent=2, ensure_ascii=False)}
```

## 你的任务
1. 计算 Gate A 评分（四维度加权分）
2. 评估 Gate B 检查项（动态检查）
3. 生成 final_verdict（Gate A PASS ∧ Gate B PASS）

## 输出路径
stages/harness_{stage_name}.json

请完成评估并将输出写入指定路径。
"""
        return task
    
    def _run_harness_local(
        self,
        stage_output: dict,
        gate_a_config: dict,
        gate_b_config: dict,
    ) -> dict:
        """本地运行 Harness（用于测试）"""
        # 简化实现：返回 PASS
        logger.warning("Running Harness locally (test mode), returning PASS")
        return {
            "gate_a": {"score": 0.9, "verdict": "PASS"},
            "gate_b": {"pass_rate": 1.0, "verdict": "PASS"},
            "final_verdict": {"final_verdict": "PASS"},
        }
    
    def _handle_gate_failure(self, stage: dict, harness_output: dict):
        """处理 Gate 失败"""
        stage_name = stage["name"]
        final_verdict = harness_output.get("final_verdict", {}).get("final_verdict", "FAIL")
        
        logger.error(f"Gate check failed for stage: {stage_name}, verdict: {final_verdict}")
        
        # 更新 state
        if stage_name not in self.state["failed_stages"]:
            self.state["failed_stages"].append(stage_name)
        
        # 增加 retry 计数
        retry_count = self.state["retry_count"].get(stage_name, 0)
        self.state["retry_count"][stage_name] = retry_count + 1
        self._save_state()
        
        # 如果 retry 次数 < 2，可以重试（子类可覆盖）
        max_retries = stage.get("max_retries", 2)
        if retry_count < max_retries:
            logger.warning(f"Retrying stage: {stage_name} (attempt {retry_count + 1}/{max_retries})")
            # 重试逻辑由子类决定
        else:
            logger.error(f"Stage failed after {max_retries} retries: {stage_name}")
            raise RuntimeError(f"Stage {stage_name} failed after {max_retries} retries")
    
    def run(self) -> dict:
        """
        运行模块（执行所有 Stage + 生成收敛点）
        
        Returns:
            收敛点数据（dict）
        """
        logger.info(f"Starting module: {self.module_name}")
        
        # 执行所有 Stage
        stages = self.stage_sequence()
        for stage in stages:
            stage_name = stage["name"]
            
            # 检查是否已完成（断点续跑）
            if stage_name in self.state["completed_stages"]:
                logger.info(f"Skipping completed stage: {stage_name}")
                continue
            
            # 执行 Stage
            try:
                output = self.execute_stage(stage)
                
                # Gate check（如果需要）
                if stage.get("gate_check", False):
                    harness_output = self.run_harness_agent(stage_name, output)
                    final_verdict = harness_output.get("final_verdict", {}).get("final_verdict", "FAIL")
                    
                    if final_verdict != "PASS":
                        self._handle_gate_failure(stage, harness_output)
                        # 如果 _handle_gate_failure 没有抛异常，继续执行
                
            except Exception as e:
                logger.error(f"Stage failed: {stage_name}, error: {e}")
                raise
        
        # 生成收敛点文件
        logger.info(f"Generating convergence for module: {self.module_name}")
        convergence = self.generate_convergence()
        
        # 写入收敛点
        convergence_path = f"{self.module_name}_convergence.json"
        self.blackboard.write(convergence_path, convergence)
        
        # 更新 state
        self.state["convergence_generated"] = True
        self._save_state()
        
        logger.info(f"Module completed: {self.module_name}")
        return convergence


# ============================================================================
# 便捷函数
# ============================================================================

def create_module_orchestrator(
    module_name: str,
    session_id: str,
    spawn_fn: Optional[Callable] = None,
) -> ModuleOrchestrator:
    """
    创建 Module Orchestrator 实例（工厂函数）
    
    Args:
        module_name: 模块名称
        session_id: Session ID
        spawn_fn: spawn 函数
    
    Returns:
        ModuleOrchestrator 实例（子类）
    """
    # 延迟导入，避免循环依赖
    if module_name == "planning":
        from .planning_orchestrator import PlanningOrchestrator
        return PlanningOrchestrator(session_id, spawn_fn)
    elif module_name == "research":
        from .research_orchestrator import ResearchOrchestrator
        return ResearchOrchestrator(session_id, spawn_fn)
    elif module_name == "review_qc":
        from .review_qc_orchestrator import ReviewQCOrchestrator
        return ReviewQCOrchestrator(session_id, spawn_fn)
    else:
        raise ValueError(f"Unknown module: {module_name}")


__all__ = [
    "ModuleOrchestrator",
    "create_module_orchestrator",
]
