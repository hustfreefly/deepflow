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
        base_dir: Optional[str] = None,
    ):
        """
        初始化 Module Orchestrator
        
        Args:
            module_name: 模块名称（如 "planning", "research", "review_qc"）
            session_id: Session ID
            spawn_fn: spawn 函数（由主 Agent 注入，用于 spawn Worker）
            base_dir: Blackboard 基础目录（可选，默认使用系统默认路径）
        """
        self.module_name = module_name
        self.session_id = session_id
        self.spawn_fn = spawn_fn
        self._base_dir = base_dir
        
        # 初始化 BlackboardManager（支持自定义 base_dir 避免跨测试污染）
        self.blackboard = BlackboardManager(session_id, base_dir=base_dir)
        
        # 加载或初始化 state
        self.state = self._load_or_init_state()
        
        # V2: 上游收敛点数据（供 Stage 使用）
        self.upstream_convergence = {}
        
        # 适配器开关：测试时可关闭
        self._use_adapter = True
        
        logger.info(f"ModuleOrchestrator initialized: {module_name} (session: {session_id})")
    
    def _adapted_spawn(self, task: str, output_path: str, timeout: int = 600, **kwargs) -> dict:
        """
        统一的 spawn_fn 契约（所有子模块必须使用此方法）
        
        生产模式（_use_adapter=True）: spawn worker → 轮询 blackboard → 返回 worker 输出
        测试模式（_use_adapter=False 或 blackboard 不支持）: 直接调用 mock spawn_fn
        
        Args:
            task: Worker 的任务描述（prompt 文本）
            output_path: Worker 输出的 blackboard 相对路径
            timeout: 超时秒数（默认 600s）
        
        Returns:
            Worker 的输出 dict
        """
        if not self._use_adapter or not self.spawn_fn:
            # 测试模式：直接调用 mock spawn_fn
            if self.spawn_fn:
                return self.spawn_fn(task=task, output_path=output_path, **kwargs)
            return None
        
        # 生产模式：spawn + wait
        # Step 0: 检查 blackboard 是否支持 read_json（MockBlackboard 可能不支持）
        if not hasattr(self.blackboard, 'read_json'):
            logger.info("Blackboard does not support read_json, using direct spawn_fn")
            return self.spawn_fn(task=task, output_path=output_path, **kwargs)
        
        # Step 1: 检查断点续跑
        try:
            existing = self.blackboard.read_json(output_path)
            if existing and self._is_valid_worker_output(existing):
                logger.info(f"Checkpoint found: {output_path}, skipping spawn")
                return existing
        except (AttributeError, TypeError, Exception) as e:
            logger.debug(f"Checkpoint read failed: {e}, proceeding with fresh spawn")
        
        # Step 2: 调用 spawn_fn 启动 worker（传递 output_path 供 mock/路由使用）
        try:
            session_info = self.spawn_fn(task=task, output_path=output_path, **kwargs)
        except TypeError:
            try:
                session_info = self.spawn_fn(task=task, output_path=output_path)
            except TypeError:
                session_info = self.spawn_fn(task=task)
        
        # Step 3: 如果 spawn_fn 直接返回了有效 worker 输出（同步模式）
        # 判断逻辑：非 None 的 dict，且不含 session_id → 视为同步返回的 worker 输出
        # 注意：此处用宽松检查（只排除 session_id），不用 _is_valid_worker_output（更严格）
        # 原因：mock spawn_fn 可能返回 {"status": "PASS"} 等简单 dict，需接受
        if isinstance(session_info, dict) and "session_id" not in session_info:
            try:
                self.blackboard.write(output_path, session_info)
            except Exception:
                pass
            return session_info
        
        # Step 4: 检查启动是否成功
        if isinstance(session_info, dict) and session_info.get("status") == "failed":
            raise RuntimeError(f"Worker failed to start: {session_info.get('error')}")
        
        # Step 5: 等待 worker 完成并写入 blackboard
        try:
            return self._wait_for_output(output_path, timeout)
        except TimeoutError:
            logger.warning(f"Worker timeout after {timeout}s, returning None")
            return None
    
    def _wait_for_output(self, output_path: str, timeout: int) -> dict:
        """轮询 blackboard 等待 worker 写入输出"""
        import time
        poll_interval = 5.0
        deadline = time.time() + timeout
        
        while time.time() < deadline:
            try:
                data = self.blackboard.read_json(output_path)
                if data and self._is_valid_worker_output(data):
                    return data
            except (AttributeError, TypeError, Exception):
                pass
            time.sleep(poll_interval)
        
        raise TimeoutError(f"Worker output not available at {output_path} after {timeout}s")
    
    def _is_valid_worker_output(self, data) -> bool:
        """
        区分 worker 输出 vs sessions_spawn 返回的 session metadata。
        
        判断逻辑：
        1. 非 dict → 无效
        2. 含 session_id → session metadata（异步 spawn 返回）
        3. 所有 key 都是 metadata key → 无效（无实际 worker 输出）
        4. 其他 → 有效 worker 输出
        
        注意：如果未来有 spawn_fn 合法返回 {"session_id": ..., "output": {...}}，
        此方法会错误拒绝。当前无此场景。
        """
        if not isinstance(data, dict):
            return False
        # 含 session_id → 一定是 session metadata（异步 spawn 返回）
        if "session_id" in data:
            return False
        # 全是 metadata key → 不是有效 worker 输出
        spawn_metadata_keys = {"session_id", "status", "label", "runtime", "mode", "taskName"}
        if set(data.keys()).issubset(spawn_metadata_keys):
            return False
        return True
    
    def _load_or_init_state(self) -> dict:
        """加载或初始化 state.json"""
        state_path = f"module_{self.module_name}_state.json"
        
        try:
            state = self.blackboard.read(state_path)
            if state and isinstance(state, dict):
                logger.info(f"Loaded existing state for {self.module_name}")
                return state
        except Exception:
            pass
        
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
        try:
            self.blackboard.write(state_path, state)
        except Exception as e:
            logger.warning(f"Could not persist state: {e}")
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
    
    def read_upstream_convergence(self, convergence_file: str) -> dict:
        """
        读取上游模块的收敛点文件（V2 新增）
        
        Args:
            convergence_file: 上游收敛点文件路径（Blackboard 相对路径）
        
        Returns:
            收敛点数据（dict）
        
        Raises:
            FileNotFoundError: 如果收敛点文件不存在
            ValueError: 如果 schema 验证失败
        """
        logger.info(f"Reading upstream convergence: {convergence_file}")
        
        try:
            # 从 Blackboard 读取收敛点（使用 read_json 获取 dict）
            convergence_data = self.blackboard.read_json(convergence_file)
            
            if convergence_data is None:
                raise FileNotFoundError(f"Convergence file not found: {convergence_file}")
            
            # 验证 schema（如果可用）
            if hasattr(self, 'validate_convergence_schema'):
                try:
                    self.validate_convergence_schema(convergence_data)
                    logger.info(f"Schema validation passed for: {convergence_file}")
                except Exception as e:
                    logger.error(f"Schema validation failed: {e}")
                    raise ValueError(f"Convergence schema validation failed: {e}")
            
            logger.info(f"Successfully read upstream convergence: {convergence_file}")
            return convergence_data
            
        except Exception as e:
            logger.error(f"Failed to read upstream convergence: {e}")
            raise
    
    def write_convergence(self, convergence_data: dict) -> str:
        """
        写入当前模块的收敛点文件（V2 新增，两阶段写入）
        
        Args:
            convergence_data: 收敛点数据（dict）
        
        Returns:
            收敛点文件路径（str）
        """
        convergence_path = f"{self.module_name}_convergence.json"
        processing_path = f"{convergence_path}.processing"
        
        logger.info(f"Writing convergence (two-phase): {convergence_path}")
        
        try:
            # Phase 1: 写入 .processing 临时文件（使用 write_json）
            # 注意：Blackboard 可能没有 write_json，使用 write 写入 JSON 字符串
            import json
            processing_json = json.dumps(convergence_data, ensure_ascii=False, indent=2)
            self.blackboard.write(processing_path, processing_json)
            logger.debug(f"Phase 1 complete: wrote to {processing_path}")
            
            # Phase 2: 重命名为最终文件（原子操作）
            # 注意：Blackboard 可能不支持 rename，需要读取后重新写入
            # 这里简化为直接写入最终文件（实际实现可能需要文件系统操作）
            convergence_json = json.dumps(convergence_data, ensure_ascii=False, indent=2)
            self.blackboard.write(convergence_path, convergence_json)
            logger.debug(f"Phase 2 complete: wrote to {convergence_path}")
            
            # 清理临时文件（如果存在）
            try:
                self.blackboard.delete(processing_path)
            except Exception:
                pass  # 临时文件可能已不存在
            
            logger.info(f"Convergence written successfully: {convergence_path}")
            return convergence_path
            
        except Exception as e:
            logger.error(f"Failed to write convergence: {e}")
            # 清理临时文件
            try:
                self.blackboard.delete(processing_path)
            except Exception:
                pass
            raise
    
    def _execute_parallel(
        self,
        tasks: list[dict],
        max_workers: int = 5,
        per_task_timeout: int = 120,
        min_viable: int = None,
    ) -> list[dict]:
        """
        通用并行执行引擎（供 Phase 2 模块使用）
        
        Args:
            tasks: [{"task_key": "...", "spawn_fn": fn, ...}]
            max_workers: 最大并发数
            per_task_timeout: 单任务超时（秒）
            min_viable: 最小可行任务数（默认 len(tasks)）
        
        Returns:
            成功执行的任务结果列表
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import logging
        
        logger = logging.getLogger(__name__)
        
        if min_viable is None:
            min_viable = len(tasks)
        
        results = []
        failed = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(task["spawn_fn"], task): task
                for task in tasks
            }
            
            for future in as_completed(futures, timeout=600):
                task = futures[future]
                try:
                    result = future.result(timeout=per_task_timeout)
                    results.append(result)
                except Exception as e:
                    failed.append({"task_key": task.get("task_key"), "error": str(e)})
                    logger.error(f"Task {task.get('task_key')} failed: {e}")
        
        if len(results) < min_viable:
            raise RuntimeError(
                f"Insufficient tasks: {len(results)}/{len(tasks)} succeeded, "
                f"minimum viable is {min_viable}"
            )
        
        if failed:
            logger.warning(f"Degraded mode: {len(results)}/{len(tasks)} tasks succeeded")
        
        return results

    def run(self) -> dict:
        """
        运行模块（执行所有 Stage + 生成收敛点）
        
        V2 增强：
        - 执行 Stage 前读取上游收敛点
        - 所有 Stage 完成后写入收敛点
        
        Returns:
            收敛点数据（dict）
        """
        logger.info(f"Starting module: {self.module_name}")
        
        # V2: 读取上游收敛点（如果子类指定了上游依赖）
        if hasattr(self, 'upstream_convergence_files'):
            for upstream_file in self.upstream_convergence_files:
                try:
                    upstream_data = self.read_upstream_convergence(upstream_file)
                    # 合并到 self.upstream_convergence（子类可通过 self.upstream_convergence 访问）
                    self.upstream_convergence.update(upstream_data)
                    logger.info(f"Loaded upstream convergence: {upstream_file}")
                except Exception as e:
                    logger.warning(f"Failed to read upstream convergence: {e}")
                    # 不阻断执行，上游收敛点可选
        
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
        
        # V2: 使用两阶段写入收敛点
        convergence_path = self.write_convergence(convergence)
        
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
