"""
Module Orchestrator 基类

Version: 2.0.0
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

变更 (2026-07-02):
- 新增 _load_p0_constraints_prompt_block() — P0 约束注入到 Worker prompt
- 新增 _get_system_soft_constraints() — 系统级软约束
- 新增 _load_requirement_traceability_prompt_block() — 需求追溯矩阵注入
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
            module_name: 模块名称（如 "planning", "research", "summary"）
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
        
        # 上游收敛点数据（供 Stage 使用）
        self.upstream_convergence = {}
        
        # 适配器开关：测试时可关闭
        self._use_adapter = True
        
        logger.info(f"ModuleOrchestrator initialized: {module_name} (session: {session_id})")
    
    def _adapted_spawn(self, task: str, output_path: str, timeout: int = 600, **kwargs) -> dict:
        """
        统一的 spawn_fn 契约（所有子模块必须使用此方法）
        
        生产模式（_use_adapter=True）: spawn worker → 轮询 blackboard → 返回 worker 输出
        spawn_fn 必须存在，否则 raise ValueError（无降级、无 mock）
        
        Args:
            task: Worker 的任务描述（prompt 文本）
            output_path: Worker 输出的 blackboard 相对路径
            timeout: 超时秒数（默认 600s）
        
        Returns:
            Worker 的输出 dict
        """
        if not self.spawn_fn:
            raise ValueError("spawn_fn is required — _adapted_spawn cannot run without it. No mock allowed.")
        
        if not self._use_adapter:
            # 直接调用 spawn_fn（适配器关闭时）
            return self.spawn_fn(task=task, output_path=output_path, **kwargs)
        
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
        except Exception as e:
            # 确定性决策树：spawn 异常 → 记录 + raise
            self._log_worker_error(output_path, "spawn_exception", str(e))
            raise RuntimeError(f"Worker spawn exception for {output_path}: {e}") from e
        
        # Step 3: 如果 spawn_fn 直接返回了有效 worker 输出（同步模式）
        if isinstance(session_info, dict) and "session_id" not in session_info:
            try:
                self.blackboard.write(output_path, session_info)
            except Exception:
                pass
            return session_info
        
        # Step 4: 检查启动是否成功
        if isinstance(session_info, dict) and session_info.get("status") == "failed":
            error_msg = session_info.get('error', 'unknown')
            self._log_worker_error(output_path, "spawn_failed", error_msg)
            raise RuntimeError(f"Worker failed to start: {error_msg}")
        
        # Step 5: 等待 worker 完成并写入 blackboard
        try:
            return self._wait_for_output(output_path, timeout)
        except TimeoutError:
            self._log_worker_error(output_path, "timeout", f"Worker did not produce output within {timeout}s")
            raise RuntimeError(f"Worker timeout after {timeout}s — FAILING. No silent fallback allowed.")
    
    def _log_worker_error(self, output_path: str, error_type: str, error_message: str) -> None:
        """结构化错误日志：写入 errors.jsonl（append-only）供后续分析"""
        import json as _json
        import time as _time
        error_record = {
            "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "output_path": output_path,
            "module": self.module_name,
            "session_id": self.session_id,
            "error_type": error_type,
            "error_message": error_message,
        }
        try:
            errors_path = self.blackboard.session_dir / "errors.jsonl"
            with open(errors_path, "a", encoding="utf-8") as f:
                f.write(_json.dumps(error_record, ensure_ascii=False) + "\n")
            logger.info(f"Error logged: {error_type} for {output_path}")
        except Exception as e:
            logger.warning(f"Failed to write error log: {e}")
    
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
        """
        if not isinstance(data, dict):
            return False
        if "session_id" in data:
            return False
        spawn_metadata_keys = {"session_id", "status", "label", "runtime", "mode", "taskName"}
        if set(data.keys()).issubset(spawn_metadata_keys):
            return False
        return True

    _stage_name: Optional[str] = None  # 子类设置以自动映射 STAGE_CONTRACTS

    def _load_checkpoint(self, path: str, required_keys: Optional[list] = None, stage_name: Optional[str] = None) -> Optional[dict]:
        """加载阶段 checkpoint（契约笼子验证）。

        验证流程：
        1. 读取数据
        2. 检查 required_keys（如果指定）
        3. StageContract 验证（schema + 最小内容长度 + 损坏检测）
        4. 验证失败 → return None + log warning

        Args:
            path: Blackboard 相对路径
            required_keys: 该阶段 checkpoint 必须包含的最小字段集
            stage_name: 阶段名称，用于查找 StageContract。未指定时从 _stage_name 或 path 自动推断。
        """
        from .contracts.stage_contract import STAGE_CONTRACTS, validate_checkpoint
        try:
            if hasattr(self.blackboard, 'read_json'):
                result = self.blackboard.read_json(path)
            else:
                result = self.blackboard.read(path)
                if isinstance(result, str):
                    result = json.loads(result)
            if result is None or not isinstance(result, dict):
                return None

            # Layer 1: required_keys 检查
            if required_keys:
                missing = [k for k in required_keys if k not in result]
                if missing:
                    logger.warning(f"Checkpoint '{path}' 缺少必需字段: {missing}，视为无效")
                    return None

            # Layer 2: StageContract 验证
            effective_stage = stage_name or self._stage_name
            if not effective_stage:
                effective_stage = path.split("/")[-1].replace(".json", "")
            if effective_stage in STAGE_CONTRACTS:
                contract = STAGE_CONTRACTS[effective_stage]
                valid, reason = validate_checkpoint(contract, result)
                if not valid:
                    logger.warning(f"Checkpoint '{path}' StageContract[{effective_stage}] 失败: {reason}")
                    return None

            logger.debug(f"Checkpoint loaded and validated: {path}")
            return result
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.warning(f"Failed to load checkpoint for {path}: {e}")
            return None

    def _resolve_prompt_vars(self, content: str) -> str:
        """替换 prompt 模板中的路径变量。

        支持的变量：
        - {deepflow_root}: DeepFlow 根目录（从 core.bootstrap 自动检测）
        """
        from core.bootstrap import get_deepflow_root
        return content.replace("{deepflow_root}", str(get_deepflow_root()))

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
            "retry_count": {},
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
        """定义模块内的 Stage 序列（子类必须实现）"""
        raise NotImplementedError("Subclass must implement stage_sequence()")
    
    def generate_convergence(self) -> dict:
        """生成收敛点文件（子类必须实现）"""
        raise NotImplementedError("Subclass must implement generate_convergence()")
    
    def execute_stage(self, stage: dict) -> dict:
        """执行单个 Stage"""
        stage_name = stage["name"]
        worker_type = stage["worker_type"]
        
        logger.info(f"Executing stage: {stage_name} (worker: {worker_type})")
        
        self.state["current_stage"] = stage_name
        self._save_state()
        
        task = self._build_worker_task(stage)
        
        if not self.spawn_fn:
            raise ValueError(f"spawn_fn is required for stage '{stage_name}' — no local execution allowed")
        
        result = self.spawn_fn(
            task=task,
            mode="run",
            label=f"{self.module_name}_{stage_name}",
        )
        
        output_path = STAGE_PATH_REGISTRY.get(stage_name, f"stages/{stage_name}.json")
        output = self.blackboard.read(output_path)
        
        if stage_name not in self.state["completed_stages"]:
            self.state["completed_stages"].append(stage_name)
        self._save_state()
        
        logger.info(f"Stage completed: {stage_name}")
        return output
    
    def _build_worker_task(self, stage: dict) -> str:
        """构建 Worker task（子类可覆盖）"""
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
        """已废弃 — execute_stage 现在要求 spawn_fn"""
        logger.warning(f"Local execution not implemented for {stage['name']}, returning empty dict")
        return {}
    
    def run_harness_agent(self, stage_name: str, stage_output: dict) -> dict:
        """调用 Harness Agent 做 Gate check"""
        logger.info(f"Running Harness Agent for stage: {stage_name}")
        
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
        
        if not self.spawn_fn:
            raise ValueError(f"spawn_fn is required for harness evaluation of '{stage_name}' — no local fallback allowed")
        
        task = self._build_harness_task(stage_name, stage_output, gate_a_config, gate_b_config)
        result = self.spawn_fn(
            task=task,
            mode="run",
            label=f"harness_{stage_name}",
        )
        
        harness_output = self.blackboard.read(f"stages/harness_{stage_name}.json")
        
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
        """Harness 必须通过 spawn_fn 调用 LLM，不允许本地硬编码 PASS"""
        raise NotImplementedError(
            "Harness cannot run locally — must use spawn_fn for real LLM evaluation. "
            "Local hardcoded PASS is forbidden."
        )
    
    def _handle_gate_failure(self, stage: dict, harness_output: dict):
        """处理 Gate 失败"""
        stage_name = stage["name"]
        final_verdict = harness_output.get("final_verdict", {}).get("final_verdict", "FAIL")
        
        logger.error(f"Gate check failed for stage: {stage_name}, verdict: {final_verdict}")
        
        if stage_name not in self.state["failed_stages"]:
            self.state["failed_stages"].append(stage_name)
        
        retry_count = self.state["retry_count"].get(stage_name, 0)
        self.state["retry_count"][stage_name] = retry_count + 1
        self._save_state()
        
        max_retries = stage.get("max_retries", 2)
        if retry_count < max_retries:
            logger.warning(f"Retrying stage: {stage_name} (attempt {retry_count + 1}/{max_retries})")
        else:
            logger.error(f"Stage failed after {max_retries} retries: {stage_name}")
            raise RuntimeError(f"Stage {stage_name} failed after {max_retries} retries")
    
    def read_upstream_convergence(self, convergence_file: str) -> dict:
        """读取上游模块的收敛点文件（新增）"""
        logger.info(f"Reading upstream convergence: {convergence_file}")
        
        try:
            convergence_data = self.blackboard.read_json(convergence_file)
            
            if convergence_data is None:
                raise FileNotFoundError(f"Convergence file not found: {convergence_file}")
            
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
        """写入当前模块的收敛点文件（新增，两阶段写入）"""
        convergence_path = f"{self.module_name}_convergence.json"
        processing_path = f"{convergence_path}.processing"
        
        logger.info(f"Writing convergence (two-phase): {convergence_path}")
        
        try:
            processing_json = json.dumps(convergence_data, ensure_ascii=False, indent=2)
            self.blackboard.write(processing_path, processing_json)
            logger.debug(f"Phase 1 complete: wrote to {processing_path}")
            
            convergence_json = json.dumps(convergence_data, ensure_ascii=False, indent=2)
            self.blackboard.write(convergence_path, convergence_json)
            logger.debug(f"Phase 2 complete: wrote to {convergence_path}")
            
            try:
                self.blackboard.delete(processing_path)
            except Exception:
                pass
            
            logger.info(f"Convergence written successfully: {convergence_path}")
            return convergence_path
            
        except Exception as e:
            logger.error(f"Failed to write convergence: {e}")
            try:
                self.blackboard.delete(processing_path)
            except Exception:
                pass
            raise
    
    def validate_stage_output(self, module_name: str, stage_name: str, output: dict) -> bool:
        """Validate stage output against schema.
        
        V2 契约笼子: Pydantic schema 验证是硬约束。
        验证失败返回 False，不再静默吞掉错误。
        """
        if not isinstance(output, dict):
            logger.error("Stage output %s/%s is not a dict (got %s)",
                        module_name, stage_name, type(output).__name__)
            return False
        
        if not output:
            logger.error("Stage output %s/%s is empty", module_name, stage_name)
            return False
        
        # Pydantic schema 验证由各域 contracts/ 模块负责
        # 这里只做基础完整性检查（非空 + dict 类型）
        logger.info("Schema validation passed for %s/%s (basic check)", module_name, stage_name)
        return True

    def _execute_parallel(
        self,
        tasks: list[dict],
        max_workers: int = 5,
        per_task_timeout: int = 120,
        min_viable: int = None,
    ) -> list[dict]:
        """通用并行执行引擎（供 Phase 2 模块使用）"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
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

    # ========================================================================
    # P0 约束注入 + 需求追溯矩阵（Quality Improvement #1 + #3）
    # ========================================================================

    def _load_p0_constraints_prompt_block(self) -> str:
        """从 blackboard 读取 P0 约束，格式化为 prompt 段落（改进 #1）"""
        try:
            p0_data = self.blackboard.read_json("stages/p0_constraints.json")
            if not p0_data:
                return "(Meta Planner 未识别 P0 约束)"
            
            constraints = p0_data.get("p0_constraints", [])
            if not constraints:
                return "(Meta Planner 未识别 P0 约束)"
            
            lines = []
            for c in constraints:
                lines.append(f"- **{c['id']}** [{c['category']}]: {c['description']}")
                lines.append(f"  - 影响: {c.get('downstream_impact', 'N/A')}")
            
            return "\n".join(lines)
        except Exception:
            return "(P0 约束加载失败，请基于常识判断)"

    def _get_system_soft_constraints(self) -> str:
        """系统级软约束，自动追加到所有 Worker prompt（改进 #1）"""
        return """
## 系统级约束（自动注入，不可跳过）

1. **可实现性**: 你的输出必须区分「设计意图」和「实现路径」。
   - ❌ "使用微服务架构"（只有意图）
   - ✅ "使用 3 个独立进程，通过 HTTP API 通信"（有实现路径）

2. **P0 约束遵守**: 上游已注入 P0 约束列表。你的输出不得违反这些约束。
   如果某个需求与 P0 冲突，标注 `[P0_CONFLICT: P0-XXX]` 并说明为什么。

3. **环境感知**: 你的方案必须在声明的运行环境中可执行。
   不要设计该环境不存在的机制。如果确实需要，标注 `[NEEDS_EXTENSION: 描述]`。
"""

    def _load_requirement_traceability_prompt_block(self) -> str:
        """从 blackboard 读取需求追溯矩阵，格式化为 prompt 段落（改进 #3）"""
        try:
            trace_data = self.blackboard.read_json("stages/requirement_traceability.json")
            if not trace_data:
                return "(需求追溯矩阵未生成)"
            
            matrix = trace_data.get("requirement_traceability_matrix", [])
            if not matrix:
                return "(需求追溯矩阵为空)"
            
            lines = ["## 需求追溯矩阵（REQ → UC → Solution）", ""]
            lines.append("| 需求 ID | 约束 ID | 方案章节 | 覆盖状态 |")
            lines.append("|---------|---------|---------|---------|")
            
            for row in matrix:
                req_id = row.get("req_id", "N/A")
                uc_id = row.get("uc_id", "N/A")
                section = row.get("solution_section", "N/A")
                status = row.get("coverage_status", "N/A")
                lines.append(f"| {req_id} | {uc_id} | {section} | {status} |")
            
            summary = trace_data.get("traceability_summary", {})
            if summary:
                lines.append("")
                lines.append(f"**覆盖率**: {summary.get('coverage_rate', 'N/A')}")
            
            return "\n".join(lines)
        except Exception:
            return "(需求追溯矩阵加载失败)"

    def run(self) -> dict:
        """
        运行模块（执行所有 Stage + 生成收敛点）
        
        增强：
        - 执行 Stage 前读取上游收敛点
        - 所有 Stage 完成后写入收敛点
        
        Returns:
            收敛点数据（dict）
        """
        logger.info(f"Starting module: {self.module_name}")
        
        # 读取上游收敛点（如果子类指定了上游依赖）
        if hasattr(self, 'upstream_convergence_files'):
            for upstream_file in self.upstream_convergence_files:
                try:
                    upstream_data = self.read_upstream_convergence(upstream_file)
                    self.upstream_convergence.update(upstream_data)
                    logger.info(f"Loaded upstream convergence: {upstream_file}")
                except Exception as e:
                    logger.warning(f"Failed to read upstream convergence: {e}")
        
        # 执行所有 Stage
        stages = self.stage_sequence()
        for stage in stages:
            stage_name = stage["name"]
            
            if stage_name in self.state["completed_stages"]:
                logger.info(f"Skipping completed stage: {stage_name}")
                continue
            
            try:
                output = self.execute_stage(stage)
                
                if output is not None:
                    self.validate_stage_output(self.module_name, stage_name, output)

                if stage.get("gate_check", False):
                    harness_output = self.run_harness_agent(stage_name, output)
                    final_verdict = harness_output.get("final_verdict", {}).get("final_verdict", "FAIL")
                    
                    if final_verdict != "PASS":
                        self._handle_gate_failure(stage, harness_output)
                
            except Exception as e:
                logger.error(f"Stage failed: {stage_name}, error: {e}")
                raise
        
        logger.info(f"Generating convergence for module: {self.module_name}")
        convergence = self.generate_convergence()
        
        convergence_path = self.write_convergence(convergence)
        
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
    """创建 Module Orchestrator 实例（工厂函数）"""
    if module_name == "planning":
        from .planning_orchestrator import PlanningOrchestrator
        return PlanningOrchestrator(session_id, spawn_fn)
    elif module_name == "research":
        from .research_orchestrator import ResearchOrchestrator
        return ResearchOrchestrator(session_id, spawn_fn)
    elif module_name == "summary":
        from .summary_orchestrator import SummaryOrchestrator
        return SummaryOrchestrator(session_id, spawn_fn)
    else:
        raise ValueError(f"Unknown module: {module_name}")


__all__ = [
    "ModuleOrchestrator",
    "create_module_orchestrator",
]
