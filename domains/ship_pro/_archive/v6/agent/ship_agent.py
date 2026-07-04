"""
Ship Pro - Agent Layer

Agent 层负责：
1. 调用 Orchestrator 的各个方法
2. 使用 sessions_spawn 启动 sub-agent
3. 管理状态转换（pending → running → completed/failed）
4. 处理 Gate 失败（retry + fix_context）

AI Native 原则：
- Python 做验证（Orchestrator 的 Gate 检查）
- Agent 做调度（sessions_spawn + sessions_yield）
"""
from pathlib import Path
from typing import Dict, Any, Optional
import json
import logging

from ..orchestrator import ShipOrchestrator

logger = logging.getLogger(__name__)


class ShipAgent:
    """
    Ship Pro Agent 层
    
    职责：
    1. 加载 Solution Pro 输出
    2. 调用 Orchestrator 准备 spawn 参数
    3. 使用 sessions_spawn 启动 sub-agent
    4. 验证 sub-agent 输出
    5. 管理状态转换
    """
    
    def __init__(
        self,
        blackboard_path: Path,
        solution_pro_output_path: Path,
        spawn_fn=None,
        yield_fn=None
    ):
        """
        初始化 Ship Agent
        
        Args:
            blackboard_path: Blackboard 目录路径
            solution_pro_output_path: Solution Pro 输出文件路径
            spawn_fn: sessions_spawn 函数（由外部注入）
            yield_fn: sessions_yield 函数（由外部注入）
        """
        self.blackboard_path = Path(blackboard_path)
        self.solution_pro_output_path = Path(solution_pro_output_path)
        self.spawn_fn = spawn_fn
        self.yield_fn = yield_fn
        
        # 初始化 Orchestrator
        self.orchestrator = ShipOrchestrator(blackboard_path)
        
        # 加载 Solution Pro 输出
        with open(solution_pro_output_path, 'r', encoding='utf-8') as f:
            self.solution_pro_output = json.load(f)
        
        logger.info(f"Ship Agent initialized: {blackboard_path}")
    
    def run_phase1_planner(self) -> Dict[str, Any]:
        """
        Phase 1: Planner
        
        流程：
        1. 准备 Planner spawn 参数
        2. 启动 Planner sub-agent
        3. 等待 Planner 完成
        4. 验证 Planner 输出
        5. 如果失败，触发 retry
        """
        logger.info("=== Phase 1: Planner ===")
        
        # 更新状态
        self.orchestrator.state_manager.update_stage("planner", "running")
        
        # 准备 spawn 参数
        spawn_params = self.orchestrator.prepare_planner_spawn(
            self.solution_pro_output
        )
        
        # 启动 sub-agent
        logger.info(f"Spawning Planner: {spawn_params['label']}")
        if self.spawn_fn:
            self.spawn_fn(**spawn_params)
        
        # 等待完成
        if self.yield_fn:
            self.yield_fn()
        
        # 读取 Planner 输出
        planner_output = self.orchestrator.state_manager.read_stage("planner_output")
        
        if not planner_output:
            logger.error("Planner output not found")
            self.orchestrator.state_manager.update_stage("planner", "failed")
            raise RuntimeError("Planner output not found")
        
        # 验证输出
        gate_result = self.orchestrator.verify_planner_output(planner_output)
        
        if gate_result.passed:
            logger.info(f"✅ Planner Gate passed: {len(planner_output['workers'])} workers")
            self.orchestrator.state_manager.update_stage("planner", "completed")
            return planner_output
        else:
            logger.warning(f"❌ Planner Gate failed: {gate_result.issues}")
            
            # 检查重试次数
            state = self.orchestrator.state_manager.state
            if state.stages["planner"].retry_count < 2:
                logger.info("Triggering retry...")
                self.orchestrator.state_manager.increment_retry("planner")
                self.orchestrator.state_manager.update_stage("planner", "pending")
                return self.run_phase1_planner()  # 递归重试
            else:
                logger.error("Planner failed after 2 retries")
                self.orchestrator.state_manager.update_stage("planner", "failed")
                raise RuntimeError(f"Planner failed: {gate_result.issues}")
    
    def run_phase2_workers(self, planner_output: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Phase 2: Workers
        
        流程：
        1. 准备所有 Worker spawn 参数（拓扑排序）
        2. 按层级启动 Worker sub-agents
        3. 等待每层完成
        4. 验证每个 Worker 输出
        5. 如果失败，触发 retry 或 fix_context
        """
        logger.info("=== Phase 2: Workers ===")
        
        # 更新状态
        self.orchestrator.state_manager.update_stage("build", "running")
        
        # 准备 spawn 参数（拓扑排序分层）
        spawn_params_list = self.orchestrator.prepare_workers_spawn(
            planner_output,
            self.solution_pro_output
        )
        
        # 按层级启动
        logger.info(f"Spawning {len(spawn_params_list)} layers of Workers")
        
        worker_outputs = {}
        
        for layer_idx, layer_params in enumerate(spawn_params_list):
            logger.info(f"--- Layer {layer_idx + 1}/{len(spawn_params_list)} ---")
            
            # 启动当前层的所有 Worker
            for spawn_params in layer_params:
                logger.info(f"Spawning Worker: {spawn_params['label']}")
                if self.spawn_fn:
                    self.spawn_fn(**spawn_params)
            
            # 等待当前层完成
            if self.yield_fn:
                self.yield_fn()
            
            # 验证当前层的 Worker 输出
            for spawn_params in layer_params:
                # 提取 role（从 label 中）
                role = spawn_params['label'].replace('ship_worker_', '')
                
                # 读取 Worker 输出
                worker_output = self.orchestrator.state_manager.read_stage(f"worker_{role}")
                
                if not worker_output:
                    logger.error(f"Worker {role} output not found")
                    self.orchestrator.state_manager.update_stage("build", "failed")
                    raise RuntimeError(f"Worker {role} output not found")
                
                # 找到对应的 worker_spec
                worker_spec = next(
                    w for w in planner_output['workers']
                    if w['role'] == role
                )
                
                # 验证输出
                gate_result = self.orchestrator.verify_worker_output(worker_spec, worker_output)
                
                if gate_result.passed:
                    logger.info(f"✅ Worker {role} Gate passed")
                    worker_outputs[role] = worker_output
                else:
                    logger.warning(f"❌ Worker {role} Gate failed: {gate_result.issues}")
                    
                    # 检查重试次数
                    state = self.orchestrator.state_manager.state
                    if state.stages["build"].retry_count < 2:
                        logger.info(f"Triggering retry for Worker {role}...")
                        self.orchestrator.state_manager.increment_retry("build")
                        
                        # 重新 spawn 这个 Worker
                        if self.spawn_fn:
                            self.spawn_fn(**spawn_params)
                        if self.yield_fn:
                            self.yield_fn()
                        
                        # 重新验证
                        worker_output = self.orchestrator.state_manager.read_stage(f"worker_{role}")
                        gate_result = self.orchestrator.verify_worker_output(worker_spec, worker_output)
                        
                        if gate_result.passed:
                            logger.info(f"✅ Worker {role} Gate passed (retry)")
                            worker_outputs[role] = worker_output
                        else:
                            logger.error(f"❌ Worker {role} failed after retry")
                            self.orchestrator.state_manager.update_stage("build", "failed")
                            raise RuntimeError(f"Worker {role} failed: {gate_result.issues}")
                    else:
                        logger.error(f"Worker {role} failed after 2 retries")
                        self.orchestrator.state_manager.update_stage("build", "failed")
                        raise RuntimeError(f"Worker {role} failed: {gate_result.issues}")
        
        logger.info(f"✅ All {len(worker_outputs)} Workers completed")
        self.orchestrator.state_manager.update_stage("build", "completed")
        self.orchestrator.complete_build_phase()
        
        return worker_outputs
    
    def run_phase3_consolidator(
        self,
        planner_output: Dict[str, Any],
        worker_outputs: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Phase 3: Consolidator
        
        流程：
        1. 准备 Consolidator spawn 参数
        2. 启动 Consolidator sub-agent
        3. 等待完成
        4. 验证输出（三层 Gate）
        5. 如果失败，触发 fix_context + retry
        """
        logger.info("=== Phase 3: Consolidator ===")
        
        # 更新状态
        self.orchestrator.state_manager.update_stage("shipper", "running")
        
        # 准备 spawn 参数
        spawn_params = self.orchestrator.prepare_consolidator_spawn(planner_output)
        
        # 启动 sub-agent
        logger.info(f"Spawning Consolidator: {spawn_params['label']}")
        if self.spawn_fn:
            self.spawn_fn(**spawn_params)
        
        # 等待完成
        if self.yield_fn:
            self.yield_fn()
        
        # 读取 Consolidator 输出
        ship_package = self.orchestrator.state_manager.read_stage("ship_package")
        
        if not ship_package:
            logger.error("Consolidator output not found")
            self.orchestrator.state_manager.update_stage("shipper", "failed")
            raise RuntimeError("Consolidator output not found")
        
        # 验证输出（三层 Gate）
        gate_results = self.orchestrator.verify_ship_package(
            self.solution_pro_output,
            ship_package
        )
        
        # 检查所有 Gate
        all_passed = all(r.passed for r in gate_results.values())
        
        if all_passed:
            logger.info("✅ All Gates passed")
            self.orchestrator.state_manager.update_stage("shipper", "completed")
            return ship_package
        else:
            failed_gates = [name for name, r in gate_results.items() if not r.passed]
            logger.warning(f"❌ Gates failed: {failed_gates}")
            
            # 检查重试次数
            state = self.orchestrator.state_manager.state
            if state.stages["shipper"].retry_count < 2:
                logger.info("Triggering fix_context + retry...")
                self.orchestrator.state_manager.increment_retry("shipper")
                
                # 生成 fix_context
                fix_context = {
                    "failed_gates": failed_gates,
                    "issues": [issue for r in gate_results.values() for issue in r.issues]
                }
                self.orchestrator.state_manager.write_stage("fix_context", fix_context)
                
                # 重新 spawn Consolidator
                if self.spawn_fn:
                    self.spawn_fn(**spawn_params)
                if self.yield_fn:
                    self.yield_fn()
                
                # 重新验证
                ship_package = self.orchestrator.state_manager.read_stage("ship_package")
                gate_results = self.orchestrator.verify_ship_package(
                    self.solution_pro_output,
                    ship_package
                )
                
                all_passed = all(r.passed for r in gate_results.values())
                
                if all_passed:
                    logger.info("✅ All Gates passed (retry)")
                    self.orchestrator.state_manager.update_stage("shipper", "completed")
                    return ship_package
                else:
                    logger.error("❌ Gates failed after retry")
                    self.orchestrator.state_manager.update_stage("shipper", "failed")
                    failed_gates = [name for name, r in gate_results.items() if not r.passed]
                    raise RuntimeError(f"Gates failed: {failed_gates}")
            else:
                logger.error("Gates failed after 2 retries")
                self.orchestrator.state_manager.update_stage("shipper", "failed")
                raise RuntimeError(f"Gates failed: {failed_gates}")
    
    def run(self) -> Dict[str, Any]:
        """
        运行完整的 Ship Pro 流程
        
        Returns:
            ship_package: 最终的交付物
        """
        logger.info("🚀 Starting Ship Pro")
        
        try:
            # Phase 1: Planner
            planner_output = self.run_phase1_planner()
            
            # Phase 2: Workers
            worker_outputs = self.run_phase2_workers(planner_output)
            
            # Phase 3: Consolidator
            ship_package = self.run_phase3_consolidator(planner_output, worker_outputs)
            
            logger.info("✅ Ship Pro completed successfully")
            return ship_package
            
        except Exception as e:
            logger.error(f"❌ Ship Pro failed: {e}")
            raise
