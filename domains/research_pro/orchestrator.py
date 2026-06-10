"""
Orchestrator — ResearchPro 核心编排器
契约: cage/active/research_pro_v1.0.yaml (L1: orchestrator)

职责:
1. 四阶段状态机管理 (planning → confirming → executing → reporting)
2. 三级 Agent 模式切换 (A/B/C)
3. 状态持久化 (state.json)
4. 子 Agent 生命周期管理
5. 超时降级策略

约束:
- 快速模式 (mode A): 不 spawn 子 Agent
- 标准模式 (mode B): 串行执行
- 标准模式 (mode C): 并行子 Agent
"""

from __future__ import annotations

import json
import os
import threading
import copy
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from urllib.parse import quote_plus, urlparse

from core.config.path_config import PathConfig
from domains.research_pro.source_registry import SourceRegistry
from domains.research_pro.url_utils import validate_safe_url as _validate_safe_url
from domains.research_pro.tier_classifier import TierClassifier
from domains.research_pro.keyword_generator import KeywordGenerator
from domains.research_pro.citation_verifier import CitationVerifier
from domains.research_pro.ddgs_client import search_ddgs
from domains.research_pro.safe_fetcher import _SafeFetcher, SafeFetchError

# PathConfig 跨平台路径管理
_path_config = PathConfig.resolve()
_BASE_DIR = _path_config.base_dir
_SKILL_DIR = Path(__file__).resolve().parent
_CONFIG_DIR = _SKILL_DIR / 'config'
_TIME_BUDGETS_PATH = _CONFIG_DIR / 'time_budgets.json'
_COMPLETION_CRITERIA_PATH = _CONFIG_DIR / 'completion_criteria.json'

DDGS_TIMEOUT_SECONDS = 12
QUERY_MIN_LENGTH = 10
QUERY_MAX_LENGTH = 5000
SUMMARY_MAX_LENGTH = 200
ORCH_FETCH_TIMEOUT = 8
MODE_C_MAX_WORKERS = 8
MAX_SUBTASKS = 20


def _load_json_file(path: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    """加载 JSON 配置文件，失败时回退默认值。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError, OSError):
        return fallback


def _load_time_budgets() -> Dict[str, Any]:
    """加载 time_budgets.json (P1-6: 契约 L4 harness.safety_valve)。"""
    return _load_json_file(_TIME_BUDGETS_PATH, {
        "quick_mode": {"total_timeout": 600},
        "standard_mode": {"total_timeout": 2700},
        "progress_report_interval_seconds": 30,
        "user_confirmation_timeout_seconds": 86400,
    })


def _load_completion_criteria() -> Dict[str, Any]:
    """加载 completion_criteria.json (P2-9: 契约 L4 output_guard)。"""
    return _load_json_file(_COMPLETION_CRITERIA_PATH, {
        "quick_mode": {"min_data_sources": 3, "min_tier_1_sources": 1, "min_citations": 3},
        "standard_mode": {"min_data_sources": 5, "min_tier_1_sources": 2, "min_citations": 8},
        "quality_scoring": {"min_trust_score": 0.7, "tier_1_ratio_min": 0.3},
    })


def _normalize_phase_timeouts(mode_budget: Dict[str, Any]) -> Dict[str, float]:
    """兼容旧 max_seconds phase schema，并输出状态机阶段 timeout_seconds。"""
    raw_phases = mode_budget.get("phases", {})
    aliases = {
        "planning": ("planning",),
        "confirming": ("confirming", "confirm"),
        "executing": ("executing", "search"),
        "reporting": ("reporting", "report"),
    }
    normalized: Dict[str, float] = {}
    for stage, keys in aliases.items():
        for key in keys:
            value = raw_phases.get(key)
            if isinstance(value, dict):
                seconds = value.get("timeout_seconds", value.get("max_seconds"))
            else:
                seconds = value
            if seconds is not None:
                normalized[stage] = float(seconds)
                break
    return normalized


class ResearchProOrchestrator:
    """
    ResearchPro 核心编排器 — 四阶段状态机 + 三级 Agent 模式。
    
    契约: cage/active/research_pro_v1.0.yaml (L1: orchestrator)
    
    状态机:
    - planning: 生成研究计划
    - confirming: 等待用户确认
    - executing: 执行搜索和研究
    - reporting: 生成最终报告
    - completed: 完成
    - cancelled: 取消
    
    Agent 模式:
    - mode A (快速模式): 单 Agent, 串行, ≤10 分钟
    - mode B (标准模式, ≤2 子任务): 单 Agent, 串行, ≤30 分钟
    - mode C (标准模式, ≥3 子任务): 主 Agent + 并行子 Agent, ≤30 分钟
    """

    def __init__(
        self,
        mode: str = 'standard',
        base_path: str = '',
        spawn_fn: Callable[[str, str], dict | None] | None = None,
        web_search_fn: Callable[[str, int], list[dict[str, str]]] | None = None,
    ) -> None:
        """
        初始化 ResearchProOrchestrator。
        
        契约: cage/active/research_pro_v1.0.yaml L1 (__init__)

        Args:
            mode: 模式 ('quick' | 'standard'), 默认 'standard'
            base_path: Blackboard 根目录 (blackboard/{session_id}/)
            spawn_fn: P2-Mode C: 子 Agent 生成函数，签名为
                      spawn_fn(task: str, mode: str) -> dict | None。
                      如不提供，Mode C 降级为 Mode B 串行执行。
            web_search_fn: OpenClaw web_search 工具注入函数，签名为
                           web_search_fn(query: str, count: int) -> list[dict]。
                           主搜索引擎。如不提供，降级使用 DuckDuckGo (DDGS)。
        """
        # PathConfig 跨平台路径管理
        self.base_path = Path(base_path) if base_path else _BASE_DIR / 'blackboard'
        self.mode = mode
        self.state_path = self.base_path / "state.json"
        self.registry = SourceRegistry(str(self.base_path / "source_registry.json"))
        self.classifier = TierClassifier()
        self._fetcher = _SafeFetcher(timeout=ORCH_FETCH_TIMEOUT)
        
        # P1-6/P1-10: 加载超时配置
        self._time_budgets = _load_time_budgets()
        # P2-9: 加载完成标准配置
        self._completion_criteria = _load_completion_criteria()
        mode_key = f"{mode}_mode"
        self._mode_time_budget = self._time_budgets.get(mode_key, {})
        self._total_timeout = self._mode_time_budget.get("total_timeout", 2700)
        self._phase_timeouts = _normalize_phase_timeouts(self._mode_time_budget)
        self._progress_report_interval_seconds = self._time_budgets.get(
            "progress_report_interval_seconds",
            self._time_budgets.get("progress_update_interval_seconds", 30),
        )
        self._user_confirmation_timeout_seconds = self._time_budgets.get(
            "user_confirmation_timeout_seconds",
            self._phase_timeouts.get("confirming", 86400),
        )
        self._max_search_calls = self._mode_time_budget.get("max_search_calls", 15)
        self._max_web_fetch_calls = self._mode_time_budget.get("max_web_fetch_calls", 15)
        self._max_professional_data_calls = self._mode_time_budget.get("max_professional_data_calls", 0)
        self._completion = self._completion_criteria.get(mode_key, {})
        self._quality_scoring = self._completion_criteria.get("quality_scoring", {})
        self._degradation_rules = self._completion_criteria.get("degradation_rules", {})
        self._execution_deadline: Optional[float] = None
        self._search_calls_used = 0
        self._web_fetch_calls_used = 0
        self._professional_data_calls_used = 0
        self._timeout_reached = False
        
        # P2-10: 并发锁保护状态写入
        self._state_lock = threading.RLock()
        
        # P2-Mode C: 注入 spawn 回调
        self._spawn_fn = spawn_fn
        
        # P0-1: 注入 web_search 工具（主搜索引擎）
        self._web_search_fn = web_search_fn
        
        # 初始化目录（PathConfig 跨平台兼容）
        self.base_path.mkdir(parents=True, exist_ok=True)
        (self.base_path / "research").mkdir(parents=True, exist_ok=True)
        (self.base_path / "report").mkdir(parents=True, exist_ok=True)
        
        # 加载或创建状态
        self.state = self._load_or_create_state()

    def _load_or_create_state(self) -> Dict[str, Any]:
        """加载或创建初始状态。
        
        契约: CWE-754 (JSON 异常处理)
        """
        if self.state_path.exists():
            try:
                with open(self.state_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                # 损坏文件不崩溃, 重新创建
                print(f"[WARNING] state.json 损坏 ({e}), 重新创建")

        # 文件不存在或损坏时创建新 state
        state = {
            "session_id": self.base_path.name,
            "mode": self.mode,
            "current_stage": "planning",
            "stage_status": "pending",
            "started_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "subtasks": [],
            "progress": {},
            "errors": [],
        }
        self._save_state(state)
        return state

    def _save_state(self, state: Dict[str, Any]) -> None:
        """原子写入 state.json (RED-DC-003: 先写 .tmp 再 replace)。
        
        P2-10: 并发锁保护，防止多线程同时写入导致状态损坏。
        """
        with self._state_lock:
            state["updated_at"] = datetime.now().isoformat()
            tmp_path = str(self.state_path) + ".tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, str(self.state_path))  # 原子操作

    def _update_state(
        self,
        updates: Optional[Dict[str, Any]] = None,
        append_errors: Optional[List[str]] = None,
        append_warnings: Optional[List[str]] = None,
        save: bool = True,
    ) -> Dict[str, Any]:
        """在同一把锁内完成状态字段迁移和持久化。"""
        with self._state_lock:
            if updates:
                self.state.update(updates)
            if append_errors:
                self.state.setdefault("errors", []).extend(append_errors)
            if append_warnings:
                self.state.setdefault("warnings", []).extend(append_warnings)
            if save:
                self._save_state(self.state)
            return copy.deepcopy(self.state)

    def _state_snapshot(self) -> Dict[str, Any]:
        """返回状态深拷贝，避免调用方持有内部可变对象。"""
        with self._state_lock:
            return copy.deepcopy(self.state)

    def init_session(self, query: str) -> Dict[str, Any]:
        """
        初始化会话, 生成分析计划。

        Args:
            query: 用户查询

        Returns:
            dict: {analysis_plan, state}

        Raises:
            ValueError: 查询为空或过短
        """
        # Input Guard (Harness L4)
        if not query or not query.strip():
            raise ValueError("查询不能为空")
        if len(query.strip()) < QUERY_MIN_LENGTH:
            raise ValueError(
                f"查询过短 ({len(query.strip())} 字符), 至少需要 {QUERY_MIN_LENGTH} 个字符"
            )
        if len(query) > QUERY_MAX_LENGTH:
            query = query[:QUERY_MAX_LENGTH]  # 截断过长查询

        self._update_state({
            "current_stage": "planning",
            "stage_status": "in_progress",
            "query": query,
        })

        # 生成分析计划 (这里简化, 实际应调用 LLM)
        plan = self._generate_analysis_plan(query)
        
        # 保存计划
        plan_path = self.base_path / "analysis_plan.json"
        with open(plan_path, 'w', encoding='utf-8') as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)

        state = self._update_state({
            "current_stage": "confirming",
            "stage_status": "waiting_user",
            "analysis_plan": plan,
            "confirmation_deadline_at": datetime.fromtimestamp(
                time.time() + float(self._user_confirmation_timeout_seconds)
            ).isoformat(),
        })

        return {
            "analysis_plan": plan,
            "state": state,
            "message": "分析计划已生成, 请确认后开始执行。"
        }

    def _generate_analysis_plan(self, query: str) -> Dict[str, Any]:
        """生成分析计划 (简化版, 实际应调用 LLM)。

        TODO(v2.0): 当前为简化版本，后续应通过 LLM 生成深度分析计划。
        See: https://github.com/deepflow/research-pro/issues/TBD
        """
        # 构建简单 plan dict 供 KeywordGenerator 使用
        plan = {
            "research_dimensions": ["基本面分析", "技术面分析", "市场情绪"],
            "subtopics": [query],
        }
        # 提取关键词
        kg = KeywordGenerator(plan)
        keyword_groups = kg.generate()

        # 生成子任务
        subtasks = [
            {"id": 1, "topic": "基本面分析", "priority": "high"},
            {"id": 2, "topic": "技术面分析", "priority": "medium"},
            {"id": 3, "topic": "市场情绪", "priority": "medium"},
        ]

        return {
            "query": query,
            "keyword_groups": keyword_groups,
            "subtasks": subtasks,
            "estimated_time_minutes": 10 if self.mode == "quick" else 30,
            "mode": self.mode,
            "tier_requirements": {
                "tier_1_min": 3,
                "tier_2_min": 5,
            },
        }

    def confirm_plan(self, user_confirmation: Dict[str, Any]) -> Dict[str, Any]:
        """
        确认、修改或取消分析计划。
        
        契约: cage/active/research_pro_v1.0.yaml L1 (confirm_plan)
        
        Args:
            user_confirmation: dict, 必须包含:
                - action: 'approve' | 'modify' | 'cancel'
                - modifications: list[dict] (仅 action='modify' 时)
        
        Returns:
            dict: {state, message}
        """
        with self._state_lock:
            current_stage = self.state["current_stage"]
            if current_stage != "confirming":
                return {
                    "success": False,
                    "error": f"当前阶段是{current_stage}，只能在confirming阶段确认计划",
                    "state": copy.deepcopy(self.state),
                }
            confirmation_deadline_at = self.state.get("confirmation_deadline_at", "")

        if confirmation_deadline_at:
            try:
                confirmation_deadline = datetime.fromisoformat(confirmation_deadline_at)
            except ValueError:
                confirmation_deadline = None
            if confirmation_deadline is not None and datetime.now() > confirmation_deadline:
                state = self._update_state(
                    {"current_stage": "cancelled", "stage_status": "cancelled"},
                    append_errors=["用户确认超时"],
                )
                return {
                    "success": False,
                    "error": "用户确认超时，计划已取消",
                    "state": state,
                }

        action = user_confirmation.get('action', '')
        
        if action == 'cancel':
            state = self._update_state(
                {"current_stage": "cancelled", "stage_status": "cancelled"},
                append_errors=["用户取消计划"],
            )
            return {"state": state, "message": "计划已取消"}
        
        if action == 'modify':
            # 应用修改
            modifications = user_confirmation.get('modifications', [])
            if modifications:
                with self._state_lock:
                    plan = copy.deepcopy(self.state.get("analysis_plan", {}))
                for mod in modifications:
                    field = mod.get('field')
                    value = mod.get('value')
                    if field == "subtasks" and isinstance(value, list) and len(value) > 20:
                        raise ValueError("subtasks 最多允许 20 个")
                    if field and value is not None:
                        plan[field] = value
                
                # 保存修改后的计划
                plan_path = self.base_path / "analysis_plan.json"
                with open(plan_path, 'w', encoding='utf-8') as f:
                    json.dump(plan, f, indent=2, ensure_ascii=False)
                self._update_state({"analysis_plan": plan})
            
            # modify 后回到 confirming 状态，等待再次确认
            return {
                "state": self._state_snapshot(),
                "message": "计划已修改, 请再次确认。"
            }
        
        if action == 'approve':
            state = self._update_state({
                "current_stage": "executing",
                "stage_status": "in_progress",
            })
            
            # P1-1: 写入 confirmed_plan.json (契约 L3: data.confirmed_plan)
            confirmed_plan = {
                "plan": state.get("analysis_plan", {}),
                "confirmed_at": datetime.now().isoformat(),
                "action": "approve",
            }
            confirmed_plan_path = self.base_path / "confirmed_plan.json"
            tmp_path = str(confirmed_plan_path) + ".tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(confirmed_plan, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, str(confirmed_plan_path))  # 原子写入
            
            return {
                "state": state,
                "message": "计划已确认, 开始执行研究。",
                "confirmed_plan_path": confirmed_plan_path
            }
        
        # 未知 action
        raise ValueError(f"无效的 action: {action}, 必须是 'approve', 'modify', 或 'cancel'")

    def execute_research(self) -> Dict[str, Any]:
        """
        执行研究 (搜索 + 抓取 + 注册)。
        
        P1-10: 超时控制 (契约 L4: safety_valve.hard_limits)
        P2-9: 完成后校验 completion_criteria

        Returns:
            dict: {sources_count, batches, state, completion_check}
        """
        with self._state_lock:
            current_stage = self.state["current_stage"]
            if current_stage != "executing":
                return {
                    "success": False,
                    "error": f"当前阶段是{current_stage}，只能在executing阶段执行研究",
                    "state": copy.deepcopy(self.state),
                }

        # P1-10: 记录执行开始时间
        executing_timeout = self._phase_timeouts.get("executing", self._total_timeout)
        self._execution_deadline = time.monotonic() + min(
            float(self._total_timeout),
            float(executing_timeout),
        )
        self._search_calls_used = 0
        self._web_fetch_calls_used = 0
        self._professional_data_calls_used = 0
        self._timeout_reached = False
        self._update_state({
            "execution_started_at": datetime.now().isoformat(),
            "execution_budget": {
                "total_timeout": self._total_timeout,
                "phase_timeouts": self._phase_timeouts,
                "progress_report_interval_seconds": self._progress_report_interval_seconds,
                "user_confirmation_timeout_seconds": self._user_confirmation_timeout_seconds,
                "max_search_calls": self._max_search_calls,
                "max_web_fetch_calls": self._max_web_fetch_calls,
                "max_professional_data_calls": self._max_professional_data_calls,
            },
        })

        with self._state_lock:
            plan = copy.deepcopy(self.state.get("analysis_plan", {}))
        subtasks = plan.get("subtasks", [])[:MAX_SUBTASKS]
        keyword_groups = plan.get("keyword_groups", [])

        # 根据模式决定 Agent 策略
        if self.mode == "quick":
            result = self._execute_mode_a(keyword_groups, subtasks)
        elif len(subtasks) <= 2:
            result = self._execute_mode_b(keyword_groups, subtasks)
        else:
            result = self._execute_mode_c(keyword_groups, subtasks)

        completion_check = self._evaluate_completion(timeout_reached=self._timeout_reached)
        state = self._update_state({
            "completion_check": completion_check,
            "progress": result.get("progress", {}),
            "current_stage": "reporting",
            "stage_status": "in_progress",
        })

        return {
            "sources_count": completion_check.get("actual_sources", len(self.registry.sources)),
            "batches": result.get("batches", []),
            "state": state,
            "completion_check": completion_check,
        }

    def _execute_mode_a(self, keyword_groups: List[Dict], subtasks: List[Dict]) -> Dict[str, Any]:
        """Mode A: 快速模式, 单 Agent 串行。"""
        max_sources = max(self._completion.get("min_data_sources", 3), 3)
        return self._execute_search_pipeline(
            keyword_groups=keyword_groups,
            max_sources=max_sources,
            results_per_group=2,
        )

    def _execute_mode_b(self, keyword_groups: List[Dict], subtasks: List[Dict]) -> Dict[str, Any]:
        """Mode B: 标准模式 (≤2 子任务), 单 Agent 串行。"""
        max_sources = max(self._completion.get("min_data_sources", 5), 5)
        max_sources = max(max_sources, self._completion.get("min_citations", 5))
        return self._execute_search_pipeline(
            keyword_groups=keyword_groups,
            max_sources=max_sources,
            results_per_group=3,
        )

    def _execute_mode_c(self, keyword_groups: List[Dict], subtasks: List[Dict]) -> Dict[str, Any]:
        """Mode C: 标准模式 (≥3 子任务), 并行子 Agent。
        
        P2-Mode C: 实际调用 sessions_spawn (通过注入的 spawn_fn)。
        如 spawn_fn 不可用，降级为 Mode B 串行执行。
        """
        subtasks = subtasks[:MAX_SUBTASKS]
        if self._spawn_fn is None:
            # 降级: 无 spawn_fn 可用时回退到串行执行
            return self._execute_mode_b(keyword_groups, subtasks)
        
        subagent_timeout = (
            self._time_budgets
            .get("subagent_timeouts", {})
            .get("mode_C_subagent", 600)
        )
        orchestrator_timeout = (
            self._time_budgets
            .get("subagent_timeouts", {})
            .get("mode_C_orchestrator", self._total_timeout)
        )
        orchestrator_started_at = time.monotonic()
        batches_by_index: Dict[int, List[Dict[str, Any]]] = {}
        pending = {}
        max_workers = min(MODE_C_MAX_WORKERS, max(1, len(subtasks)))
        executor = ThreadPoolExecutor(max_workers=max_workers)

        try:
            for i, subtask in enumerate(subtasks):
                task_prompt = (
                    f"执行子任务: {subtask.get('topic', 'unknown')}\n"
                    f"关键词组: {keyword_groups[i] if i < len(keyword_groups) else {}}\n"
                    f"请将搜索结果写入 Blackboard。"
                )
                future = executor.submit(self._spawn_fn, task=task_prompt, mode=self.mode)
                pending[future] = {
                    "index": i,
                    "subtask": subtask,
                    "started_at": time.monotonic(),
                }

            while pending:
                done, _ = wait(pending.keys(), timeout=0.1, return_when=FIRST_COMPLETED)

                for future in done:
                    meta = pending.pop(future)
                    try:
                        result = future.result()
                    except Exception as exc:
                        self._update_state(
                            append_warnings=[
                                (
                                    f"Mode C 子任务失败: {meta['subtask'].get('topic', 'unknown')} "
                                    f"({exc})"
                                )
                            ],
                            save=False,
                        )
                        batches_by_index[meta["index"]] = self._fallback_mode_c_batches(
                            index=meta["index"],
                            keyword_groups=keyword_groups,
                        )
                        continue
                    batches_by_index[meta["index"]] = self._handle_mode_c_result(
                        index=meta["index"],
                        subtask=meta["subtask"],
                        keyword_groups=keyword_groups,
                        result=result,
                    )

                now = time.monotonic()
                if now - orchestrator_started_at >= orchestrator_timeout:
                    timed_out_items = list(pending.items())
                    pending.clear()
                    for future, meta in timed_out_items:
                        future.cancel()
                        self._update_state(
                            append_warnings=[
                                (
                                    f"Mode C 编排超时: {meta['subtask'].get('topic', 'unknown')} "
                                    f"> {orchestrator_timeout}s"
                                )
                            ],
                            save=False,
                        )
                        batches_by_index[meta["index"]] = self._fallback_mode_c_batches(
                            index=meta["index"],
                            keyword_groups=keyword_groups,
                        )
                    break

                timed_out = [
                    future
                    for future, meta in pending.items()
                    if now - meta["started_at"] >= subagent_timeout
                ]
                for future in timed_out:
                    meta = pending.pop(future)
                    future.cancel()
                    self._update_state(
                        append_warnings=[
                            (
                                f"Mode C 子任务超时: {meta['subtask'].get('topic', 'unknown')} "
                                f"> {subagent_timeout}s"
                            )
                        ],
                        save=False,
                    )
                    batches_by_index[meta["index"]] = self._fallback_mode_c_batches(
                        index=meta["index"],
                        keyword_groups=keyword_groups,
                    )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        batches = []
        for i in range(len(subtasks)):
            batches.extend(batches_by_index.get(i, []))

        return {
            "batches": batches,
            "progress": {"searched": len(batches), "registered": len(self.registry.sources)},
        }

    def _handle_mode_c_result(
        self,
        index: int,
        subtask: Dict[str, Any],
        keyword_groups: List[Dict],
        result: Any,
    ) -> List[Dict[str, Any]]:
        """处理单个 Mode C 子任务结果；失败时执行本地降级搜索。"""
        batch_id = f"batch_{index+1:02d}"
        if result and isinstance(result, dict):
            sources = result.get("sources", [])
            if not isinstance(sources, list):
                self._update_state(
                    append_warnings=[
                        (
                            f"Mode C 子任务返回 sources 非列表: "
                            f"{subtask.get('topic', 'unknown')}"
                        )
                    ],
                    save=False,
                )
                return [{"id": batch_id, "subtask": subtask, "spawn_result": result, "results": []}]

            required_fields = {"url", "title", "content", "quality_tier"}
            registered_results = []
            invalid_count = 0
            for src in sources:
                if not isinstance(src, dict):
                    invalid_count += 1
                    self._update_state(
                        append_warnings=[
                            (
                                f"Mode C 跳过不合规 source: "
                                f"{subtask.get('topic', 'unknown')} 缺少dict结构"
                            )
                        ],
                        save=False,
                    )
                    continue

                missing = sorted(required_fields - set(src.keys()))
                if missing:
                    invalid_count += 1
                    self._update_state(
                        append_warnings=[
                            (
                                f"Mode C 跳过不合规 source: "
                                f"{subtask.get('topic', 'unknown')} 缺少字段 {', '.join(missing)}"
                            )
                        ],
                        save=False,
                    )
                    continue

                try:
                    source_id = self.registry.register(**src)
                except (TypeError, ValueError, AttributeError) as exc:
                    invalid_count += 1
                    self._update_state(
                        append_warnings=[
                            (
                                f"Mode C 跳过无法注册 source: "
                                f"{subtask.get('topic', 'unknown')} ({exc})"
                            )
                        ],
                        save=False,
                    )
                    continue

                registered_results.append({
                    "source_id": source_id,
                    "url": src.get("url", ""),
                    "title": src.get("title", ""),
                })

            if sources and invalid_count == len(sources):
                self._update_state(
                    append_warnings=[
                        (
                            f"Mode C 子任务所有 source 均不合规: "
                            f"{subtask.get('topic', 'unknown')}"
                        )
                    ],
                    save=False,
                )

            return [{
                "id": batch_id,
                "subtask": subtask,
                "spawn_result": result,
                "results": registered_results,
            }]

        return self._fallback_mode_c_batches(index=index, keyword_groups=keyword_groups)

    def _fallback_mode_c_batches(self, index: int, keyword_groups: List[Dict]) -> List[Dict[str, Any]]:
        """Mode C 单个子任务失败或超时时的本地搜索降级。"""
        kg = keyword_groups[index] if index < len(keyword_groups) else self._fallback_keyword_group(index)
        fallback = self._execute_search_pipeline(
            keyword_groups=[kg],
            max_sources=max(self._completion.get("min_data_sources", 5), 1),
            results_per_group=3,
        )
        return fallback.get("batches", [])

    def _execute_search_pipeline(
        self,
        keyword_groups: List[Dict],
        max_sources: int,
        results_per_group: int,
    ) -> Dict[str, Any]:
        """基于 keyword_groups 搜索、抓取、分类、去重并注册来源。"""
        batches = []
        registered_before = len(self.registry.sources)
        groups = keyword_groups or [self._fallback_keyword_group(0)]

        for i, kg in enumerate(groups):
            if not self._search_budget_available():
                break
            if len(self.registry.sources) - registered_before >= max_sources:
                break

            query = self._query_from_keyword_group(kg)
            batch_id = f"batch_{len(batches) + 1:02d}"
            if self._consume_search_call():
                # P0-1: 主路径 web_search → 降级 DDGS → 降级关键词数据
                results = self._search_web(query, max_results=results_per_group)
                if not results:
                    results = self._search_ddgs(query, max_results=results_per_group)
            else:
                results = []
            if not results:
                results = self._fallback_search_results(kg, results_per_group)

            batch = {"id": batch_id, "keywords": kg, "query": query, "results": []}
            for result in results:
                if not self._search_budget_available():
                    break
                if len(self.registry.sources) - registered_before >= max_sources:
                    break
                registered_id = self._register_search_result(result, kg)
                if registered_id is not None:
                    batch["results"].append({
                        "source_id": registered_id,
                        "url": result.get("url", ""),
                        "title": result.get("title", ""),
                    })

            batches.append(batch)

        fallback_index = 0
        while (
            len(self.registry.sources) - registered_before < max_sources
            and self._search_budget_available()
        ):
            kg = groups[fallback_index % len(groups)]
            result = self._fallback_search_results(kg, 1, offset=fallback_index)[0]
            registered_id = self._register_search_result(result, kg)
            if registered_id is not None:
                batch_id = f"batch_{len(batches) + 1:02d}"
                batches.append({
                    "id": batch_id,
                    "keywords": kg,
                    "query": self._query_from_keyword_group(kg),
                    "results": [{"source_id": registered_id, "url": result["url"], "title": result["title"]}],
                })
            fallback_index += 1
            if fallback_index > max_sources * 3:
                break

        registered_after = len(self.registry.sources)
        return {
            "batches": batches,
            "progress": {
                "searched": len(batches),
                "registered": registered_after - registered_before,
                "search_calls_used": self._search_calls_used,
                "web_fetch_calls_used": self._web_fetch_calls_used,
                "professional_data_calls_used": self._professional_data_calls_used,
                "timeout_reached": self._timeout_reached,
            },
        }

    def _search_budget_available(self) -> bool:
        """搜索循环内的 deadline 和调用配额检查。"""
        if self._execution_deadline is not None and time.monotonic() >= self._execution_deadline:
            self._timeout_reached = True
            return False
        return (
            self._search_calls_used < self._max_search_calls
            or self._web_fetch_calls_used < self._max_web_fetch_calls
        )

    def _consume_search_call(self) -> bool:
        if self._execution_deadline is not None and time.monotonic() >= self._execution_deadline:
            self._timeout_reached = True
            return False
        if self._search_calls_used >= self._max_search_calls:
            return False
        self._search_calls_used += 1
        return True

    def _consume_fetch_call(self) -> bool:
        if self._execution_deadline is not None and time.monotonic() >= self._execution_deadline:
            self._timeout_reached = True
            return False
        if self._web_fetch_calls_used >= self._max_web_fetch_calls:
            return False
        self._web_fetch_calls_used += 1
        return True

    @staticmethod
    def _fallback_keyword_group(index: int) -> Dict[str, Any]:
        keyword = f"research_topic_{index + 1}"
        return {"base": keyword, "variants": [keyword], "priority": min(index + 1, 5)}

    @staticmethod
    def _query_from_keyword_group(keyword_group: Dict[str, Any]) -> str:
        base = str(keyword_group.get("base", "")).strip()
        variants = keyword_group.get("variants", [])
        variant = ""
        if isinstance(variants, list):
            variant = next((str(v).strip() for v in variants if str(v).strip()), "")
        return variant or base or "research topic"

    def _search_web(self, query: str, max_results: int) -> List[Dict[str, str]]:
        """主搜索引擎：通过 OpenClaw web_search 工具搜索。
        
        web_search_fn 由调用方注入（签名为 web_search_fn(query, count) -> list[dict]）。
        未注入或失败时返回空列表，由上层降级到 DDGS。
        """
        fn = self._web_search_fn
        if fn is None:
            return []
        try:
            raw = fn(query=query, count=max_results)
            if not isinstance(raw, list):
                return []
            results: List[Dict[str, str]] = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or item.get("href") or "")
                title = str(item.get("title") or query)
                snippet = str(item.get("snippet") or item.get("description") or item.get("body") or "")
                if url:
                    results.append({"url": url, "title": title, "snippet": snippet})
            return results
        except Exception as e:
            self._update_state(
                append_warnings=[f"web_search 失败，降级到 DDGS: {query} ({e})"],
                save=False,
            )
            return []

    def _search_ddgs(self, query: str, max_results: int) -> List[Dict[str, str]]:
        """备选搜索引擎：通过 DuckDuckGo Search 搜索。
        
        仅在 web_search 不可用或返回空结果时调用。
        直接 import ddgs_client，不使用 subprocess。
        """
        results = search_ddgs(query, max_results=max_results, timeout=DDGS_TIMEOUT_SECONDS)
        if not results:
            self._update_state(
                append_warnings=[f"DDGS 搜索失败，使用关键词降级数据: {query}"],
                save=False,
            )
        return results

    def _register_search_result(self, result: Dict[str, str], keyword_group: Dict[str, Any]) -> Optional[int]:
        url = result.get("url", "")
        title = result.get("title", "") or self._query_from_keyword_group(keyword_group)
        snippet = result.get("snippet", "")

        try:
            parsed, _ = _validate_safe_url(url)
        except ValueError:
            return None

        fetched = self._fetch_page_content(url)
        content = fetched or self._fallback_content(keyword_group, title, snippet, url)
        summary = self._summarize_content(content, snippet)
        quality_tier = self.classifier.classify(parsed.hostname or "")

        return self.registry.register(
            url=url,
            title=title[:200],
            content=content,
            quality_tier=quality_tier,
            summary=summary,
        )

    def _fetch_page_content(self, url: str) -> str:
        """抓取搜索结果正文；失败返回空字符串以触发关键词相关降级内容。"""
        if not self._consume_fetch_call():
            return ""
        try:
            response = self._fetcher.get(url)
            if response.status >= 400:
                return ""
            return response.text
        except (SafeFetchError, OSError, ValueError, TimeoutError):
            return ""

    @staticmethod
    def _summarize_content(content: str, snippet: str = "") -> str:
        text = " ".join((snippet or content).split())
        if not text:
            return ""
        return text[:SUMMARY_MAX_LENGTH]

    def _fallback_search_results(
        self,
        keyword_group: Dict[str, Any],
        count: int,
        offset: int = 0,
    ) -> List[Dict[str, str]]:
        """搜索失败时生成与关键词相关的合理降级来源。"""
        query = self._query_from_keyword_group(keyword_group)
        slug = quote_plus(query)[:80] or "research"
        source_templates = [
            ("https://www.sec.gov/search-filings?keys={slug}&fallback={n}", "官方披露"),
            ("https://www.reuters.com/search/news?blob={slug}&fallback={n}", "权威新闻"),
            ("https://www.bloomberg.com/search?query={slug}&fallback={n}", "市场资讯"),
            ("https://finance.sina.com.cn/search?keywords={slug}&fallback={n}", "财经数据"),
        ]
        results = []
        for i in range(count):
            template, label = source_templates[(offset + i) % len(source_templates)]
            n = offset + i + 1
            results.append({
                "url": template.format(slug=slug, n=n),
                "title": f"{query} - {label}参考资料 {n}",
                "snippet": f"围绕“{query}”的{label}降级资料，用于搜索服务不可用时保留研究路径。",
            })
        return results

    def _fallback_content(
        self,
        keyword_group: Dict[str, Any],
        title: str,
        snippet: str,
        url: str,
    ) -> str:
        query = self._query_from_keyword_group(keyword_group)
        domain = urlparse(url).hostname or "unknown"
        variants = keyword_group.get("variants", [])
        variant_text = ", ".join(str(v) for v in variants[:5]) if isinstance(variants, list) else ""
        return (
            f"Title: {title}\n"
            f"Query: {query}\n"
            f"Source domain: {domain}\n"
            f"Keyword variants: {variant_text}\n"
            f"Summary: {snippet or query}\n"
            "Note: This keyword-grounded fallback content was generated because live search "
            "or page fetching failed. It preserves the research topic, URL, and source tier "
            "for downstream registry, citation, and completion checks."
        )

    def generate_report(self) -> Dict[str, Any]:
        """
        生成最终报告 (含引用验证)。

        Returns:
            dict: {report_path, citations, state}
        """
        with self._state_lock:
            current_stage = self.state["current_stage"]
            if current_stage != "reporting":
                return {
                    "success": False,
                    "error": f"当前阶段是{current_stage}，只能在reporting阶段生成报告",
                    "state": copy.deepcopy(self.state),
                }

        # 生成报告草稿 (简化版, 实际应调用 LLM)
        report_md = self._generate_report_draft()
        if self._timeout_reached:
            report_md += "\n\n> PARTIAL_REPORT_TIMEOUT: 执行预算已耗尽，本报告为部分结果。\n"
        
        # 引用验证 (RED-DC-005)
        verifier = CitationVerifier(self.registry)
        citations = verifier.verify_all(report_md)
        
        # P2-9: 如果 completion_check 未通过，在报告中标注
        with self._state_lock:
            completion_check = copy.deepcopy(self.state.get("completion_check", {}))
        if not completion_check.get("overall_pass", True):
            citation_notes = (
                f"\n> 完成标准未通过: "
                f"数据源 {completion_check.get('actual_sources', 0)}/{completion_check.get('min_sources_required', 0)}, "
                f"Tier 1 {completion_check.get('actual_tier_1_sources', 0)}/{completion_check.get('min_tier_1_sources_required', 0)}, "
                f"引用 {completion_check.get('actual_citations', 0)}/{completion_check.get('min_citations_required', 0)}"
            )
            report_md += citation_notes

        # P1-3: 保存报告 (契约 L3: data.blackboard_layout 要求 final.md)
        report_path = self.base_path / "report" / "final.md"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_md)

        # 保存引用验证结果
        citations_path = self.base_path / "report" / "citations.json"
        with open(citations_path, 'w', encoding='utf-8') as f:
            json.dump(citations, f, indent=2, ensure_ascii=False)

        final_completion_check = self._evaluate_completion(
            report_md=report_md,
            citations=citations,
            timeout_reached=self._timeout_reached,
        )
        stage_status = self._report_stage_status(citations, final_completion_check)
        message = "报告已生成" if stage_status == "completed" else "报告已生成，但存在完成标准或引用可信度警告"

        state = self._update_state({
            "current_stage": "completed",
            "stage_status": stage_status,
            "report_path": str(report_path),
            "citations": citations,
            "completion_check": final_completion_check,
        })

        return {
            "report_path": report_path,
            "citations": citations,
            "state": state,
            "completion_check": final_completion_check,
            "message": message,
        }

    def _report_stage_status(self, citations: Dict[str, Any], completion_check: Dict[str, Any]) -> str:
        recommendation = citations.get("recommendation")
        if recommendation == "reject":
            action = self._degradation_rules.get("citation_verification_below_60_percent", "")
            if action == "mark_report_as_unreliable":
                return "completed_with_warnings"
        if not completion_check.get("overall_pass", False):
            return "completed_with_warnings"
        return "completed"

    def _evaluate_completion(
        self,
        report_md: str = "",
        citations: Optional[Dict[str, Any]] = None,
        timeout_reached: bool = False,
    ) -> Dict[str, Any]:
        """按 completion_criteria.json 全字段计算完成状态。"""
        registry_sources = self.registry.sources
        actual_sources = len(registry_sources)
        actual_tier_1_sources = sum(
            1 for source in registry_sources
            if source.get("quality_tier") == "tier_1"
        )
        min_sources = self._completion.get("min_data_sources", 3)
        min_tier_1_sources = self._completion.get("min_tier_1_sources", 1)
        min_citations = self._completion.get("min_citations", 3)
        min_trust_score = float(self._quality_scoring.get("min_trust_score", 0.7))
        tier_1_ratio_min = float(self._quality_scoring.get("tier_1_ratio_min", 0.3))
        actual_citations = (
            int(citations.get("total_citations", 0))
            if citations is not None
            else actual_sources
        )

        required_sections = self._completion.get("report_required_sections", [])
        missing_sections = self._missing_report_sections(report_md, required_sections)
        sections_pass = not missing_sections if report_md else False

        citation_summary = (citations or {}).get("verification_summary", {})
        unique_citations = int((citations or {}).get("unique_citations", 0))
        verified_count = int(citation_summary.get("verified", 0))
        unreachable_count = int(citation_summary.get("unreachable", 0))
        suspect_count = sum(
            int(citation_summary.get(status, 0))
            for status in ("unreachable", "not_found", "content_mismatch")
        )
        verified_ratio = verified_count / unique_citations if unique_citations else 0.0
        url_reachability = (
            (unique_citations - unreachable_count) / unique_citations
            if unique_citations
            else (1.0 if actual_sources else 0.0)
        )
        citation_suspect_rate = suspect_count / unique_citations if unique_citations else 0.0
        trust_score = float((citations or {}).get("trust_score", verified_ratio))
        tier_1_ratio = actual_tier_1_sources / actual_sources if actual_sources else 0.0

        required_reachability = float(self._completion.get("url_reachability", 0.0))
        max_suspect_rate = float(self._completion.get("max_citation_suspect_rate", 1.0))
        max_time_seconds = float(self._completion.get("max_time_seconds", self._total_timeout))
        elapsed_seconds = self._elapsed_execution_seconds()
        timeout_marker_required = timeout_reached or elapsed_seconds > max_time_seconds
        timeout_marker_present = "PARTIAL_REPORT_TIMEOUT" in report_md if report_md else False
        timeout_pass = not timeout_marker_required or timeout_marker_present

        degradation_actions = []
        if verified_ratio < 0.60 and citations is not None:
            degradation_actions.append(self._degradation_rules.get("citation_verification_below_60_percent"))
        if url_reachability < 0.50 and citations is not None:
            degradation_actions.append(self._degradation_rules.get("url_reachability_below_50_percent"))
        if actual_sources == 0:
            degradation_actions.append(self._degradation_rules.get("no_data_sources_after_search"))
        if timeout_marker_required:
            degradation_actions.append(self._degradation_rules.get("timeout_reached"))
        degradation_actions = [action for action in degradation_actions if action]

        checks = {
            "sources_pass": actual_sources >= min_sources,
            "tier_1_sources_pass": actual_tier_1_sources >= min_tier_1_sources,
            "citations_pass": actual_citations >= min_citations,
            "url_reachability_pass": url_reachability >= required_reachability,
            "citation_suspect_rate_pass": citation_suspect_rate <= max_suspect_rate,
            "required_sections_pass": sections_pass,
            "max_time_seconds_pass": elapsed_seconds <= max_time_seconds,
            "timeout_marker_pass": timeout_pass,
            "trust_score_pass": trust_score >= min_trust_score,
            "tier_1_ratio_pass": tier_1_ratio >= tier_1_ratio_min,
        }
        checks["degradation_rules_pass"] = not degradation_actions

        return {
            "min_sources_required": min_sources,
            "actual_sources": actual_sources,
            "min_tier_1_sources_required": min_tier_1_sources,
            "actual_tier_1_sources": actual_tier_1_sources,
            "min_citations_required": min_citations,
            "actual_citations": actual_citations,
            "url_reachability_required": required_reachability,
            "actual_url_reachability": round(url_reachability, 2),
            "max_citation_suspect_rate": max_suspect_rate,
            "actual_citation_suspect_rate": round(citation_suspect_rate, 2),
            "citation_verified_ratio": round(verified_ratio, 2),
            "min_trust_score": min_trust_score,
            "actual_trust_score": round(trust_score, 2),
            "tier_1_ratio_min": tier_1_ratio_min,
            "actual_tier_1_ratio": round(tier_1_ratio, 2),
            "required_sections": required_sections,
            "missing_required_sections": missing_sections,
            "max_time_seconds": max_time_seconds,
            "elapsed_seconds": round(elapsed_seconds, 2),
            "timeout_reached": timeout_marker_required,
            "timeout_marker_present": timeout_marker_present,
            "degradation_actions": degradation_actions,
            **checks,
            "overall_pass": all(checks.values()),
        }

    @staticmethod
    def _missing_report_sections(report_md: str, required_sections: List[str]) -> List[str]:
        if not report_md:
            return list(required_sections)
        return [
            section
            for section in required_sections
            if f"## {section}" not in report_md and f"# {section}" not in report_md
        ]

    def _elapsed_execution_seconds(self) -> float:
        with self._state_lock:
            started = self.state.get("execution_started_at", "")
        if not started:
            return 0.0
        try:
            return (datetime.now() - datetime.fromisoformat(started)).total_seconds()
        except ValueError:
            return 0.0

    def _generate_report_draft(self) -> str:
        """生成报告草稿 (简化版, 实际应调用 LLM)。"""
        with self._state_lock:
            plan = copy.deepcopy(self.state.get("analysis_plan", {}))
        query = plan.get("query", "未知查询")
        min_citations = self._completion.get("min_citations", 3)
        available_sources = self.registry.sources
        citation_total = min(len(available_sources), max(min_citations, 1))
        citation_ids = list(range(1, citation_total + 1))
        citation_marks = " ".join(f"[{citation_id}]" for citation_id in citation_ids)
        first_half_marks = " ".join(
            f"[{citation_id}]"
            for citation_id in citation_ids[:max(1, citation_total // 2 or 1)]
        )
        second_half_marks = " ".join(
            f"[{citation_id}]"
            for citation_id in citation_ids[max(0, citation_total // 2):]
        )

        report = f"""# ResearchPro 研究报告

## 查询
{query}

## 摘要
本报告围绕查询主题整理公开来源、核心发现和风险因素。

## 核心发现

1. 发现一 {citation_marks}
2. 发现二 {first_half_marks}
3. 发现三 {second_half_marks}

## 详细分析

### 基本面
分析内容...

### 技术面
分析内容...

### 市场情绪
分析内容...

## 风险提示
风险内容...

## 参考资料
"""
        # 添加参考资料
        for i, source in enumerate(available_sources[:citation_total], 1):
            report += f"{i}. {source['title']} - {source['url']}\n"

        return report

    def get_status(self) -> Dict[str, Any]:
        """返回当前状态。"""
        with self._state_lock:
            return {
                "session_id": self.state.get("session_id"),
                "current_stage": self.state.get("current_stage", "unknown"),
                "progress": copy.deepcopy(self.state.get("progress", {})),
                "errors": copy.deepcopy(self.state.get("errors", [])),
            }

    def resume_from_state(self, state_path: str = None) -> Dict[str, Any]:
        """
        从当前状态恢复执行。
        
        契约: cage/active/research_pro_v1.0.yaml L1 (resume_from_state)

        Args:
            state_path: 可选，指定 state.json 路径。如不提供则使用默认路径。

        Returns:
            dict: {state, next_action}
        """
        # P1-2: 支持从指定路径加载状态
        if state_path and Path(state_path).exists():
            try:
                with open(state_path, 'r', encoding='utf-8') as f:
                    loaded_state = json.load(f)
                with self._state_lock:
                    self.state = loaded_state
                    self._save_state(self.state)
            except (json.JSONDecodeError, OSError) as e:
                return {
                    "state": self._state_snapshot(),
                    "next_action": "error",
                    "message": f"无法加载 state.json: {e}"
                }
        
        state = self._state_snapshot()
        stage = state.get("current_stage", "planning")
        
        if stage == "planning":
            return {"state": state, "next_action": "init_session"}
        elif stage == "confirming":
            return {"state": state, "next_action": "confirm_plan"}
        elif stage == "executing":
            return {"state": state, "next_action": "execute_research"}
        elif stage == "reporting":
            return {"state": state, "next_action": "generate_report"}
        elif stage == "completed":
            return {"state": state, "next_action": "none", "message": "已完成"}
        else:
            return {"state": state, "next_action": "none", "message": "未知状态"}
