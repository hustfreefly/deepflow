#!/usr/bin/env python3
"""
Pipeline Orchestrator Agent（depth-1）

职责：
1. 读取 execution_plan.json
2. 按 phase 顺序执行
3. 并行 phase 同时 spawn 多个 Workers
4. 串行 phase 逐个 spawn
5. 等待 Worker 结果（Blackboard 轮询）
6. 更新 progress.json
7. 返回管线状态

设计原则：
- 接收 spawn_fn 注入，禁止模块级 import openclaw
- 每个 sessions_spawn 调用必须设置 label
- Worker 失败不阻断（容错）
- 向后兼容：旧调用方式仍然可用
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config.path_config import PathConfig
from core.blackboard.blackboard_manager import BlackboardManager

_DEEPFLOW_BASE = str(PathConfig.resolve().base_dir)

# ============================================================================
# P0-1 修复: Worker 名称 → 实际 Blackboard 输出路径映射
# 对齐 domains/solution/task_builder.py 中各 prompt 要求写入的文件名
# ============================================================================
WORKER_OUTPUT_PATH_MAP = {
    "data_collection": "data_collection.json",
    "planning": "planning.json",
    "reviewers": None,  # 并行子worker, 由执行时动态映射
    "research": None,   # 并行子worker, 由执行时动态映射
    "consolidator": "consolidator.json",
    "audit": "audit.json",
    "fix": "fix.json",
    "fixer_expert": "fixer_expert.json",
    "harness_final": "harness_final.json",
    "summarizer": "final_solution.md",
    # 并行子worker的命名约定
    "reviewer": "reviewer.json",        # reviewer_type → reviewer_{type}.json
    "research_expert_1": "research_expert_1.json",
    "research_expert_2": "research_expert_2.json",
    "research_expert_3": "research_expert_3.json",
    "technical": "reviewer_technical.json",
    "business": "reviewer_business.json",
    "risk": "reviewer_risk.json",
    "expert_1": "research_expert_1.json",
    "expert_2": "research_expert_2.json",
    "expert_3": "research_expert_3.json",
}


def resolve_worker_output_path(worker_name: str) -> str:
    """
    P0-1 修复: 根据 worker_name 解析实际的 Blackboard 输出文件路径

    优先级:
    1. 精确映射 (WORKER_OUTPUT_PATH_MAP)
    2. reviewer 类型映射 (reviewer_technical → reviewer_technical.json)
    3. expert 类型映射 (expert_N → research_expert_N.json)
    4. 回退到 {worker_name}.json
    """
    if worker_name in WORKER_OUTPUT_PATH_MAP:
        mapped = WORKER_OUTPUT_PATH_MAP[worker_name]
        if mapped is not None:
            return mapped

    # reviewer 子worker
    if worker_name.startswith("reviewer_"):
        return f"reviewer_{worker_name.split('_', 1)[1]}.json"

    # expert 子worker
    if worker_name.startswith("expert_"):
        return f"research_{worker_name}.json"

    # 回退: 直接使用 worker_name
    return f"{worker_name}.json"


class PipelineOrchestrator:
    """
    Pipeline Orchestrator Agent（depth-1）

    在主Agent环境中运行，接收 spawn_fn 注入。
    负责读取 execution_plan.json，按阶段 spawn Workers (depth-2)。
    """

    def __init__(
        self,
        domain: str,
        user_context: Dict[str, Any],
        spawn_fn=None,
        execution_plan_path: Optional[str] = None,
    ):
        """
        初始化 PipelineOrchestrator

        Args:
            domain: 领域标识（如 'solution', 'investment'）
            user_context: 用户提供的领域特定上下文
            spawn_fn: 注入的 sessions_spawn 函数（必须在主Agent环境中注入）
            execution_plan_path: execution_plan.json 文件路径
        """
        self.domain = domain
        self.user_context = user_context
        self._spawn_fn = None
        self._spawn_fn = spawn_fn or self._resolve_spawn_fn()
        self.execution_plan_path = execution_plan_path
        self.session_id = user_context.get("session_id", f"pipeline_{int(time.time())}")
        self.blackboard = None
        self.progress = {
            "phases_completed": 0,
            "phases_total": 0,
            "workers_spawned": 0,
            "workers_completed": 0,
            "workers_failed": 0,
        }

    def _resolve_spawn_fn(self) -> Optional[Any]:
        """解析 spawn 函数（同 InvestmentOrchestrator 模式）"""
        if self._spawn_fn:
            return self._spawn_fn
        # 禁止在 exec 环境自动 import openclaw
        # PipelineOrchestrator 必须在主Agent环境中运行，通过 spawn_fn 注入
        return None

    def run_pipeline(self, execution_plan_path: Optional[str] = None) -> Dict[str, Any]:
        """
        执行管线

        1. 读取 execution_plan.json
        2. 按 phase 顺序执行
        3. 并行 phase 同时 spawn 多个 Workers
        4. 串行 phase 逐个 spawn
        5. 等待 Worker 结果
        6. 更新 Blackboard 状态

        Args:
            execution_plan_path: execution_plan.json 路径（覆盖构造函数中的路径）

        Returns:
            {
                "status": "completed" | "failed" | "partial",
                "session_id": str,
                "phases": list,
                "workers": dict,
                "progress": dict,
                "errors": list
            }
        """
        plan_path = execution_plan_path or self.execution_plan_path
        if not plan_path:
            raise ValueError("execution_plan_path must be provided")

        # 验证 spawn_fn
        spawn = self._spawn_fn
        if not spawn:
            raise RuntimeError(
                "spawn_fn 未注入且无法解析，PipelineOrchestrator 无法运行。"
                "必须在主Agent环境中运行，或通过 spawn_fn 参数注入 sessions_spawn 工具。"
            )

        # 初始化 Blackboard
        self.blackboard = BlackboardManager(session_id=self.session_id)
        self.blackboard.init_session()

        # 读取 execution_plan
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)

        phases = plan.get("phases", [])
        self.progress["phases_total"] = len(phases)

        print(f"[PipelineOrchestrator] Session: {self.session_id}")
        print(f"[PipelineOrchestrator] Phases: {len(phases)}")
        print(f"[PipelineOrchestrator] Plan: {plan_path}")

        # 执行结果
        all_results = {}
        errors = []

        for phase_idx, phase in enumerate(phases):
            phase_num = phase_idx + 1
            stage_name = phase.get("stage", f"phase_{phase_num}")
            is_parallel = phase.get("parallel", False)
            workers = phase.get("workers", [])
            single_worker = phase.get("worker")
            timeout = phase.get("timeout", 300)

            print(f"\n[Phase {phase_num}/{len(phases)}] {stage_name}")
            print(f"  Parallel: {is_parallel}, Workers: {workers or single_worker}")

            # 确定 Worker 列表
            worker_list = workers if workers else ([single_worker] if single_worker else [])
            if not worker_list:
                print(f"  ⚠️ No workers defined, skipping")
                continue

            # 准备 worker tasks
            tasks = self._load_worker_tasks(plan, stage_name, worker_list)

            # 执行 phase
            try:
                if is_parallel and len(worker_list) > 1:
                    phase_results = self._execute_parallel(
                        stage_name, worker_list, tasks, timeout, spawn
                    )
                else:
                    phase_results = self._execute_serial(
                        stage_name, worker_list, tasks, timeout, spawn
                    )

                all_results[stage_name] = phase_results
                self.progress["phases_completed"] += 1

                # 统计 Worker 状态
                for worker_name, result in phase_results.items():
                    if result.get("success"):
                        self.progress["workers_completed"] += 1
                    else:
                        self.progress["workers_failed"] += 1

                # 写入 phase 结果到 Blackboard
                self.blackboard.write(
                    filename=f"phase_{phase_num}_{stage_name}_result.json",
                    content=phase_results,
                    subdir="stages",
                )

            except (RuntimeError, OSError, ValueError) as e:
                error_msg = f"Phase {stage_name} failed: {e}"
                print(f"  ❌ {error_msg}")
                errors.append(error_msg)
                all_results[stage_name] = {"error": error_msg}
                # Worker 失败不阻断，继续下一个 phase

            # 更新 progress.json
            self._save_progress()

        # 最终状态
        total_workers = self.progress["workers_completed"] + self.progress["workers_failed"]
        if self.progress["workers_failed"] == 0 and self.progress["phases_completed"] == len(phases):
            status = "completed"
        elif self.progress["workers_failed"] > 0 and self.progress["workers_completed"] > 0:
            status = "partial"
        else:
            status = "failed"

        result = {
            "status": status,
            "session_id": self.session_id,
            "domain": self.domain,
            "phases": list(all_results.keys()),
            "workers": all_results,
            "progress": self.progress,
            "errors": errors,
        }

        # 写入最终结果
        self.blackboard.write(filename="pipeline_result.json", content=result)

        print(f"\n[PipelineOrchestrator] Pipeline {status}")
        print(f"  Phases: {self.progress['phases_completed']}/{self.progress['phases_total']}")
        print(f"  Workers: {self.progress['workers_completed']} completed, {self.progress['workers_failed']} failed")

        return result

    def _load_worker_tasks(
        self, plan: Dict[str, Any], stage_name: str, worker_list: List[str]
    ) -> Dict[str, str]:
        """
        从 tasks.json 加载 Worker 任务描述

        Args:
            plan: execution_plan 字典
            stage_name: 阶段名称
            worker_list: Worker 名称列表

        Returns:
            {worker_name: task_string}
        """
        # 尝试从 blackboard 的 tasks.json 加载
        session_dir = self.blackboard.session_dir if self.blackboard else None
        if not session_dir:
            # 从 plan 推断路径
            session_dir = Path(_DEEPFLOW_BASE) / "blackboard" / self.session_id

        tasks_path = session_dir / "tasks.json"
        tasks = {}

        if tasks_path.exists():
            try:
                with open(tasks_path, "r", encoding="utf-8") as f:
                    all_tasks = json.load(f)

                # 尝试按 stage 查找
                stage_tasks = all_tasks.get(stage_name, {})
                if isinstance(stage_tasks, dict):
                    for worker_name in worker_list:
                        task = stage_tasks.get(worker_name)
                        if task and isinstance(task, str):
                            tasks[worker_name] = task
                        elif task and isinstance(task, dict):
                            # 如果 task 是字典，取 task 字段或整个字典的字符串表示
                            tasks[worker_name] = task.get("task", json.dumps(task, ensure_ascii=False))
                elif isinstance(stage_tasks, str):
                    # 整个 stage 只有一个 task
                    if len(worker_list) == 1:
                        tasks[worker_list[0]] = stage_tasks
            except (json.JSONDecodeError, OSError) as e:
                print(f"  ⚠️ Failed to load tasks.json: {e}")

        # 对于未加载到 task 的 worker，生成默认 task
        for worker_name in worker_list:
            if worker_name not in tasks:
                tasks[worker_name] = self._build_default_task(worker_name, stage_name)

        return tasks

    def _build_default_task(self, worker_name: str, stage_name: str) -> str:
        """构建默认 Worker 任务描述"""
        return f"""你是 {worker_name} Agent。

## 任务
执行 {stage_name} 阶段的 {worker_name} 任务。

## 上下文
- Session ID: {self.session_id}
- Domain: {self.domain}
- User Context: {json.dumps(self.user_context, ensure_ascii=False)}

## 输出要求
请将你的分析和结论写入 Blackboard 文件：
- 路径: {_DEEPFLOW_BASE}/blackboard/{self.session_id}/stages/{resolve_worker_output_path(worker_name)}
- 格式: JSON

请确保输出包含真实内容，不要只返回元数据。"""

    def _execute_serial(
        self,
        stage_name: str,
        worker_list: List[str],
        tasks: Dict[str, str],
        timeout: int,
        spawn: Any,
    ) -> Dict[str, Any]:
        """
        串行执行 Worker（逐个 spawn 并等待）

        Args:
            stage_name: 阶段名称
            worker_list: Worker 列表
            tasks: {worker_name: task}
            timeout: 超时（秒）
            spawn: spawn 函数

        Returns:
            {worker_name: result_dict}
        """
        results = {}
        for worker_name in worker_list:
            task = tasks.get(worker_name, self._build_default_task(worker_name, stage_name))
            label = self._build_label(worker_name, stage_name)

            print(f"  [Serial] Spawning {worker_name} (label={label})...")
            result = self._spawn_and_wait(worker_name, label, task, timeout, spawn)
            results[worker_name] = result

            if result.get("success"):
                print(f"    ✅ {worker_name} completed")
            else:
                print(f"    ❌ {worker_name} failed: {result.get('error', 'unknown')}")

        return results

    def _execute_parallel(
        self,
        stage_name: str,
        worker_list: List[str],
        tasks: Dict[str, str],
        timeout: int,
        spawn: Any,
    ) -> Dict[str, Any]:
        """
        并行执行 Worker（同时 spawn，然后统一等待）

        Args:
            stage_name: 阶段名称
            worker_list: Worker 列表
            tasks: {worker_name: task}
            timeout: 超时（秒）
            spawn: spawn 函数

        Returns:
            {worker_name: result_dict}
        """
        results = {}
        spawned = {}

        # 第一阶段：同时 spawn 所有 Worker
        for worker_name in worker_list:
            task = tasks.get(worker_name, self._build_default_task(worker_name, stage_name))
            label = self._build_label(worker_name, stage_name)

            print(f"  [Parallel] Spawning {worker_name} (label={label})...")
            try:
                spawn_meta = spawn(
                    runtime="subagent",
                    mode="run",
                    label=label,
                    task=task,
                    timeout_seconds=timeout,
                )
                spawned[worker_name] = {
                    "meta": spawn_meta,
                    "label": label,
                    "start_time": time.time(),
                }
                self.progress["workers_spawned"] += 1
                print(f"    ⏳ {worker_name} spawned")
            except (RuntimeError, OSError, ValueError) as e:
                results[worker_name] = {
                    "success": False,
                    "error": f"Spawn failed: {e}",
                    "label": label,
                }
                print(f"    ❌ {worker_name} spawn failed: {e}")

        # 第二阶段：统一等待
        for worker_name, info in spawned.items():
            result = self._wait_for_worker(
                worker_name, info["label"], info["start_time"], timeout
            )
            results[worker_name] = result

            if result.get("success"):
                print(f"    ✅ {worker_name} completed")
            else:
                print(f"    ❌ {worker_name} failed: {result.get('error', 'unknown')}")

        return results

    def _spawn_and_wait(
        self,
        worker_name: str,
        label: str,
        task: str,
        timeout: int,
        spawn: Any,
    ) -> Dict[str, Any]:
        """
        Spawn 单个 Worker 并等待完成

        Args:
            worker_name: Worker 名称
            label: spawn label
            task: 任务描述
            timeout: 超时（秒）
            spawn: spawn 函数

        Returns:
            {"success": bool, "result": any, "error": str, "label": str}
        """
        try:
            spawn_meta = spawn(
                runtime="subagent",
                mode="run",
                label=label,
                task=task,
                timeout_seconds=timeout,
            )
            self.progress["workers_spawned"] += 1

            return self._wait_for_worker(worker_name, label, time.time(), timeout)
        except (RuntimeError, OSError, ValueError) as e:
            return {
                "success": False,
                "error": f"Spawn failed: {e}",
                "label": label,
            }

    def _wait_for_worker(
        self, worker_name: str, label: str, start_time: float, timeout: int
    ) -> Dict[str, Any]:
        """
        等待 Worker 完成（Blackboard 轮询）

        P0-1 修复: 使用 resolve_worker_output_path 解析实际输出路径

        策略：
        1. 轮询 Blackboard 文件（根据 worker_name 映射到实际路径）
        2. 超时后返回降级结果

        Args:
            worker_name: Worker 名称
            label: spawn label
            start_time: 开始时间戳
            timeout: 超时（秒）

        Returns:
            {"success": bool, "result": any, "error": str, "source": str}
        """
        poll_interval = 5.0
        # P0-1 修复: 不再硬编码 {worker_name}_output.json
        output_filename = resolve_worker_output_path(worker_name)
        blackboard_path = self.blackboard.session_dir / "stages" / output_filename

        print(f"    [{worker_name}] Waiting for {output_filename} (timeout={timeout}s)...")

        while time.time() - start_time < timeout:
            # 检查 Blackboard 文件
            if blackboard_path.exists():
                try:
                    with open(blackboard_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    # 验证不是 spawn 元数据
                    if self._is_valid_worker_output(data):
                        print(f"    [{worker_name}] ✅ Result from Blackboard ({output_filename})")
                        return {
                            "success": True,
                            "result": data,
                            "source": "blackboard",
                            "label": label,
                        }
                except (json.JSONDecodeError, OSError):
                    pass

            time.sleep(poll_interval)

        # 超时
        print(f"    [{worker_name}] ⏱️ Timeout after {timeout}s")
        return {
            "success": False,
            "error": f"Worker timed out after {timeout}s",
            "source": "timeout",
            "label": label,
        }

    def _is_valid_worker_output(self, data: Any) -> bool:
        """
        验证是否为有效的 Worker 输出（而非 spawn 元数据）

        Spawn 元数据特征：
        - 包含 "status": "accepted"
        - 包含 "childSessionKey"

        Worker 输出特征：
        - 包含 "analysis" 或 "executive_summary" 或 "plan" 等
        """
        if not isinstance(data, dict):
            return False

        # 排除 spawn 元数据
        if data.get("status") == "accepted":
            return False
        if "childSessionKey" in data:
            return False

        # 验证 Worker 输出字段
        content_keys = ["analysis", "executive_summary", "conclusions",
                       "key_findings", "plan", "report", "output",
                       "recommendation", "fixed_analysis", "research_plan",
                       "scenario_analysis", "audit_findings"]
        if any(k in data for k in content_keys):
            return True

        # P0-2 修复: 识别标准阶段输出格式 {"status": "completed", "stage": "...", "data": {...}}
        if data.get("status") in ("completed", "partial", "failed"):
            if "stage" in data or "data" in data:
                return True

        return False

    def _build_label(self, worker_name: str, stage_name: str) -> str:
        """
        构建 spawn label（遵循 label_naming.md 规范）

        格式: {worker_name} 或 {worker_name}_{stage}
        确保长度不超过 50 字符
        """
        label = f"{worker_name}"
        if len(label) > 50:
            label = label[:50]
        return label

    def _save_progress(self) -> None:
        """保存进度到 progress.json"""
        if self.blackboard:
            self.blackboard.write(
                filename="progress.json",
                content=self.progress,
            )

    def get_progress(self) -> Dict[str, Any]:
        """获取当前进度"""
        return self.progress.copy()


# ============================================================================
# 便捷函数
# ============================================================================

def run_pipeline(
    execution_plan_path: str,
    domain: str = "solution",
    user_context: Optional[Dict[str, Any]] = None,
    spawn_fn=None,
) -> Dict[str, Any]:
    """
    便捷函数：快速执行管线

    Args:
        execution_plan_path: execution_plan.json 路径
        domain: 领域标识
        user_context: 用户上下文
        spawn_fn: 注入的 spawn 函数

    Returns:
        管线执行结果
    """
    orchestrator = PipelineOrchestrator(
        domain=domain,
        user_context=user_context or {},
        spawn_fn=spawn_fn,
    )
    return orchestrator.run_pipeline(execution_plan_path)


if __name__ == "__main__":
    print("✅ pipeline_orchestrator.py loaded successfully")
    print("Available classes: PipelineOrchestrator")
    print("Available functions: run_pipeline")
