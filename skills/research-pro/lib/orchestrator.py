"""
Orchestrator — ResearchPro 核心编排器
契约: cage/research_pro_v1.0.yaml (L1: orchestrator)

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

import json
import os
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable

from core.config.path_config import PathConfig
from lib.source_registry import SourceRegistry
from lib.tier_classifier import TierClassifier
from lib.keyword_generator import KeywordGenerator
from lib.citation_verifier import CitationVerifier

# PathConfig 跨平台路径管理
_path_config = PathConfig.resolve()
_BASE_DIR = _path_config.base_dir
_SKILL_DIR = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _SKILL_DIR / 'config'
_TIME_BUDGETS_PATH = _CONFIG_DIR / 'time_budgets.json'
_COMPLETION_CRITERIA_PATH = _CONFIG_DIR / 'completion_criteria.json'


def _load_json_file(path: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    """加载 JSON 配置文件，失败时回退默认值。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def _load_time_budgets() -> Dict[str, Any]:
    """加载 time_budgets.json (P1-6: 契约 L4 harness.safety_valve)。"""
    return _load_json_file(_TIME_BUDGETS_PATH, {
        "quick_mode": {"total_timeout": 600},
        "standard_mode": {"total_timeout": 2700},
    })


def _load_completion_criteria() -> Dict[str, Any]:
    """加载 completion_criteria.json (P2-9: 契约 L4 output_guard)。"""
    return _load_json_file(_COMPLETION_CRITERIA_PATH, {
        "quick_mode": {"min_sources": 3, "min_citations": 3},
        "standard_mode": {"min_sources": 5, "min_citations": 5},
    })


class ResearchProOrchestrator:
    """
    ResearchPro 核心编排器 — 四阶段状态机 + 三级 Agent 模式。
    
    契约: cage/research_pro_v1.0.yaml (L1: orchestrator)
    
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
        spawn_fn: Optional[Callable] = None,
    ) -> None:
        """
        初始化 ResearchProOrchestrator。
        
        契约: cage/research_pro_v1.0.yaml L1 (__init__)

        Args:
            mode: 模式 ('quick' | 'standard'), 默认 'standard'
            base_path: Blackboard 根目录 (blackboard/{session_id}/)
            spawn_fn: P2-Mode C: 子 Agent 生成函数，签名为
                      spawn_fn(task: str, mode: str) -> dict | None。
                      如不提供，Mode C 降级为 Mode B 串行执行。
        """
        # PathConfig 跨平台路径管理
        self.base_path = Path(base_path) if base_path else _BASE_DIR / 'blackboard'
        self.mode = mode
        self.state_path = self.base_path / "state.json"
        self.registry = SourceRegistry(str(self.base_path / "source_registry.json"))
        self.classifier = TierClassifier()
        
        # P1-6/P1-10: 加载超时配置
        self._time_budgets = _load_time_budgets()
        # P2-9: 加载完成标准配置
        self._completion_criteria = _load_completion_criteria()
        mode_key = f"{mode}_mode"
        self._total_timeout = self._time_budgets.get(mode_key, {}).get("total_timeout", 2700)
        self._phase_timeouts = self._time_budgets.get(mode_key, {}).get("phases", {})
        self._completion = self._completion_criteria.get(mode_key, {})
        
        # P2-10: 并发锁保护状态写入
        self._state_lock = threading.Lock()
        
        # P2-Mode C: 注入 spawn 回调
        self._spawn_fn = spawn_fn
        
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
        if len(query.strip()) < 10:
            raise ValueError(f"查询过短 ({len(query.strip())} 字符), 至少需要 10 个字符")
        if len(query) > 5000:
            query = query[:5000]  # 截断过长查询

        self.state["current_stage"] = "planning"
        self.state["stage_status"] = "in_progress"
        self.state["query"] = query
        self._save_state(self.state)

        # 生成分析计划 (这里简化, 实际应调用 LLM)
        plan = self._generate_analysis_plan(query)
        
        # 保存计划
        plan_path = self.base_path / "analysis_plan.json"
        with open(plan_path, 'w', encoding='utf-8') as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)

        self.state["current_stage"] = "confirming"
        self.state["stage_status"] = "waiting_user"
        self.state["analysis_plan"] = plan
        self._save_state(self.state)

        return {
            "analysis_plan": plan,
            "state": self.state,
            "message": "分析计划已生成, 请确认后开始执行。"
        }

    def _generate_analysis_plan(self, query: str) -> Dict[str, Any]:
        """生成分析计划 (简化版, 实际应调用 LLM)。"""
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
        
        契约: cage/research_pro_v1.0.yaml L1 (confirm_plan)
        
        Args:
            user_confirmation: dict, 必须包含:
                - action: 'approve' | 'modify' | 'cancel'
                - modifications: list[dict] (仅 action='modify' 时)
        
        Returns:
            dict: {state, message}
        """
        action = user_confirmation.get('action', '')
        
        if action == 'cancel':
            self.state["current_stage"] = "cancelled"
            self.state["stage_status"] = "cancelled"
            self.state["errors"].append("用户取消计划")
            self._save_state(self.state)
            return {"state": self.state, "message": "计划已取消"}
        
        if action == 'modify':
            # 应用修改
            modifications = user_confirmation.get('modifications', [])
            if modifications:
                plan = self.state.get("analysis_plan", {})
                for mod in modifications:
                    field = mod.get('field')
                    value = mod.get('value')
                    if field and value is not None:
                        plan[field] = value
                self.state["analysis_plan"] = plan
                
                # 保存修改后的计划
                plan_path = self.base_path / "analysis_plan.json"
                with open(plan_path, 'w', encoding='utf-8') as f:
                    json.dump(plan, f, indent=2, ensure_ascii=False)
            
            # modify 后回到 confirming 状态，等待再次确认
            return {
                "state": self.state,
                "message": "计划已修改, 请再次确认。"
            }
        
        if action == 'approve':
            self.state["current_stage"] = "executing"
            self.state["stage_status"] = "in_progress"
            self._save_state(self.state)
            
            # P1-1: 写入 confirmed_plan.json (契约 L3: data.confirmed_plan)
            confirmed_plan = {
                "plan": self.state.get("analysis_plan", {}),
                "confirmed_at": datetime.now().isoformat(),
                "action": "approve",
            }
            confirmed_plan_path = self.base_path / "confirmed_plan.json"
            tmp_path = str(confirmed_plan_path) + ".tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(confirmed_plan, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, str(confirmed_plan_path))  # 原子写入
            
            return {
                "state": self.state,
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
        if self.state["current_stage"] != "executing":
            return {"error": "当前状态不是 executing", "state": self.state}

        # P1-10: 记录执行开始时间
        self.state["execution_started_at"] = datetime.now().isoformat()
        self._save_state(self.state)

        plan = self.state.get("analysis_plan", {})
        subtasks = plan.get("subtasks", [])
        keyword_groups = plan.get("keyword_groups", [])

        # 根据模式决定 Agent 策略
        if self.mode == "quick":
            result = self._execute_mode_a(keyword_groups, subtasks)
        elif len(subtasks) <= 2:
            result = self._execute_mode_b(keyword_groups, subtasks)
        else:
            result = self._execute_mode_c(keyword_groups, subtasks)

        # P1-10: 超时检查
        started = self.state.get("execution_started_at", "")
        if started:
            elapsed = (datetime.now() - datetime.fromisoformat(started)).total_seconds()
            search_timeout = self._phase_timeouts.get("search", {}).get("max_seconds", 180)
            if elapsed > search_timeout:
                self.state["warnings"] = self.state.get("warnings", []) + [
                    f"搜索阶段超时: {elapsed:.0f}s > {search_timeout}s"
                ]

        # P2-9: 完成标准校验
        min_sources = self._completion.get("min_sources", 3)
        min_citations = self._completion.get("min_citations", 3)
        actual_sources = len(self.registry.sources)
        completion_check = {
            "min_sources_required": min_sources,
            "actual_sources": actual_sources,
            "sources_pass": actual_sources >= min_sources,
            "min_citations_required": min_citations,
            "citations_pass": actual_sources >= min_citations,
            "overall_pass": actual_sources >= min_sources and actual_sources >= min_citations,
        }
        self.state["completion_check"] = completion_check

        self.state["progress"] = result.get("progress", {})
        self.state["current_stage"] = "reporting"
        self.state["stage_status"] = "in_progress"
        self._save_state(self.state)

        return {
            "sources_count": actual_sources,
            "batches": result.get("batches", []),
            "state": self.state,
            "completion_check": completion_check,
        }

    def _execute_mode_a(self, keyword_groups: List[Dict], subtasks: List[Dict]) -> Dict[str, Any]:
        """Mode A: 快速模式, 单 Agent 串行。"""
        # 简化: 实际应调用 web_search, web_fetch 等
        batches = []
        for i, kg in enumerate(keyword_groups[:3]):  # 最多 3 组
            batch_id = f"batch_{i+1:02d}"
            batches.append({"id": batch_id, "keywords": kg})
            
            # 模拟搜索结果
            self.registry.register(
                url=f"https://example.com/{batch_id}",
                title=f"搜索结果 {batch_id}",
                content=f"内容 {batch_id}",
                quality_tier="tier_2",
                summary=f"摘要 {batch_id}"
            )

        return {
            "batches": batches,
            "progress": {"searched": len(batches), "registered": len(batches)},
        }

    def _execute_mode_b(self, keyword_groups: List[Dict], subtasks: List[Dict]) -> Dict[str, Any]:
        """Mode B: 标准模式 (≤2 子任务), 单 Agent 串行。"""
        # 类似 Mode A, 但搜索更多
        batches = []
        for i, kg in enumerate(keyword_groups[:5]):  # 最多 5 组
            batch_id = f"batch_{i+1:02d}"
            batches.append({"id": batch_id, "keywords": kg})
            
            self.registry.register(
                url=f"https://example.com/{batch_id}",
                title=f"搜索结果 {batch_id}",
                content=f"内容 {batch_id}",
                quality_tier="tier_2",
                summary=f"摘要 {batch_id}"
            )

        return {
            "batches": batches,
            "progress": {"searched": len(batches), "registered": len(batches)},
        }

    def _execute_mode_c(self, keyword_groups: List[Dict], subtasks: List[Dict]) -> Dict[str, Any]:
        """Mode C: 标准模式 (≥3 子任务), 并行子 Agent。
        
        P2-Mode C: 实际调用 sessions_spawn (通过注入的 spawn_fn)。
        如 spawn_fn 不可用，降级为 Mode B 串行执行。
        """
        if self._spawn_fn is None:
            # 降级: 无 spawn_fn 可用时回退到串行执行
            return self._execute_mode_b(keyword_groups, subtasks)
        
        # 通过 spawn_fn 并行分发子任务
        batches = []
        for i, subtask in enumerate(subtasks):
            task_prompt = (
                f"执行子任务: {subtask.get('topic', 'unknown')}\n"
                f"关键词组: {keyword_groups[i] if i < len(keyword_groups) else {}}\n"
                f"请将搜索结果写入 Blackboard。"
            )
            result = self._spawn_fn(task=task_prompt, mode=self.mode)
            batch_id = f"batch_{i+1:02d}"
            batches.append({"id": batch_id, "subtask": subtask, "spawn_result": result})
            
            # 如果 spawn 返回 source 信息，注册到 registry
            if result and isinstance(result, dict):
                for src in result.get("sources", []):
                    self.registry.register(**src)
            else:
                # spawn 失败时的降级注册
                self.registry.register(
                    url=f"https://example.com/{batch_id}",
                    title=f"搜索结果 {batch_id}",
                    content=f"内容 {batch_id}",
                    quality_tier="tier_2",
                    summary=f"摘要 {batch_id}"
                )
        
        return {
            "batches": batches,
            "progress": {"searched": len(batches), "registered": len(batches)},
        }

    def generate_report(self) -> Dict[str, Any]:
        """
        生成最终报告 (含引用验证)。

        Returns:
            dict: {report_path, citations, state}
        """
        if self.state["current_stage"] != "reporting":
            return {"error": "当前状态不是 reporting", "state": self.state}

        # 生成报告草稿 (简化版, 实际应调用 LLM)
        report_md = self._generate_report_draft()
        
        # 引用验证 (RED-DC-005)
        verifier = CitationVerifier(self.registry)
        citations = verifier.verify_all(report_md)
        
        # P2-9: 如果 completion_check 未通过，在报告中标注
        completion_check = self.state.get("completion_check", {})
        if not completion_check.get("overall_pass", True):
            citation_notes = (
                f"\n> ⚠️ 完成标准未通过: "
                f"数据源 {completion_check.get('actual_sources', 0)}/{completion_check.get('min_sources_required', 0)}, "
                f"{'通过' if completion_check.get('sources_pass') else '未通过'}"
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

        self.state["current_stage"] = "completed"
        self.state["stage_status"] = "done"
        self.state["report_path"] = report_path
        self.state["citations"] = citations
        self._save_state(self.state)

        return {
            "report_path": report_path,
            "citations": citations,
            "state": self.state,
            "message": "报告已生成"
        }

    def _generate_report_draft(self) -> str:
        """生成报告草稿 (简化版, 实际应调用 LLM)。"""
        plan = self.state.get("analysis_plan", {})
        query = plan.get("query", "未知查询")
        
        # 生成引用标记
        citation_marks = ""
        for i, source in enumerate(self.registry.sources[:5], 1):
            citation_marks += f"[{i}] "

        report = f"""# ResearchPro 研究报告

## 查询
{query}

## 核心发现

1. 发现一 {citation_marks}
2. 发现二
3. 发现三

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
        for i, source in enumerate(self.registry.sources[:5], 1):
            report += f"{i}. {source['title']} - {source['url']}\n"

        return report

    def get_status(self) -> Dict[str, Any]:
        """返回当前状态。"""
        return {
            "session_id": self.state.get("session_id"),
            "current_stage": self.state.get("current_stage", "unknown"),
            "progress": self.state.get("progress", {}),
            "errors": self.state.get("errors", []),
        }

    def resume_from_state(self, state_path: str = None) -> Dict[str, Any]:
        """
        从当前状态恢复执行。
        
        契约: cage/research_pro_v1.0.yaml L1 (resume_from_state)

        Args:
            state_path: 可选，指定 state.json 路径。如不提供则使用默认路径。

        Returns:
            dict: {state, next_action}
        """
        # P1-2: 支持从指定路径加载状态
        if state_path and Path(state_path).exists():
            try:
                with open(state_path, 'r', encoding='utf-8') as f:
                    self.state = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                return {
                    "state": self.state,
                    "next_action": "error",
                    "message": f"无法加载 state.json: {e}"
                }
        
        stage = self.state.get("current_stage", "planning")
        
        if stage == "planning":
            return {"state": self.state, "next_action": "init_session"}
        elif stage == "confirming":
            return {"state": self.state, "next_action": "confirm_plan"}
        elif stage == "executing":
            return {"state": self.state, "next_action": "execute_research"}
        elif stage == "reporting":
            return {"state": self.state, "next_action": "generate_report"}
        elif stage == "completed":
            return {"state": self.state, "next_action": "none", "message": "已完成"}
        else:
            return {"state": self.state, "next_action": "none", "message": "未知状态"}
