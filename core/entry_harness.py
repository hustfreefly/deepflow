#!/usr/bin/env python3
"""
Entry/Startup Harness

职责：
1. 验证配置完整性（检查必要文件、目录）
2. 验证 spawn_fn 可用性
3. 初始化 Blackboard
4. 生成 tasks.json + execution_plan.json
5. 创建并返回 PipelineOrchestrator 实例（注入 spawn_fn）

使用方式：
    harness = EntryHarness()
    orchestrator = harness.validate_and_start(domain, context, spawn_fn)
    result = orchestrator.run_pipeline()
"""

import json
from typing import Any, Dict

from core.config.path_config import PathConfig
from core.blackboard_manager import BlackboardManager
from core.pipeline_orchestrator import PipelineOrchestrator

_DEEPFLOW_BASE = PathConfig.resolve().base_dir


class EntryHarness:
    """
    Entry/Startup Harness

    负责启动前的验证、初始化和管线编排器创建。
    """

    def __init__(self):
        """初始化 EntryHarness"""
        self.errors = []
        self.warnings = []

    def validate_and_start(
        self,
        domain: str,
        context: Dict[str, Any],
        spawn_fn=None,
    ) -> PipelineOrchestrator:
        """
        验证配置并启动 PipelineOrchestrator

        步骤：
        1. 检查 domain 配置存在
        2. 检查 spawn_fn 可用（如不可用 raise RuntimeError）
        3. 初始化 session（生成 session_id）
        4. 生成 tasks.json + execution_plan.json
        5. 创建 PipelineOrchestrator 并注入 spawn_fn
        6. 返回 orchestrator

        Args:
            domain: 领域标识（如 'solution', 'investment'）
            context: 领域特定上下文（topic, constraints, code, name 等）
            spawn_fn: 注入的 spawn 函数（主Agent提供）

        Returns:
            配置完成的 PipelineOrchestrator 实例

        Raises:
            RuntimeError: spawn_fn 不可用或配置验证失败
            ValueError: domain 不支持或 context 缺失必要字段
        """
        print(f"[EntryHarness] Validating domain: {domain}")

        # Step 1: 检查 domain 配置存在
        self._validate_domain(domain)

        # Step 2: 检查 spawn_fn 可用性
        resolved_spawn = spawn_fn
        if not resolved_spawn:
            # 禁止在 exec 环境自动 import openclaw
            # 必须在主Agent环境中通过 spawn_fn 参数注入
            raise RuntimeError(
                "spawn_fn 未注入：EntryHarness 必须在主Agent环境中运行，"
                "并通过 spawn_fn 参数显式注入 sessions_spawn 工具。"
                "\n正确用法：harness.validate_and_start(domain, context, spawn_fn=sessions_spawn)"
            )

        # Step 3: 初始化 session（按领域生成 session_id）
        session_id = self._init_session(domain, context)
        context["session_id"] = session_id

        # Step 4: 生成 tasks.json + execution_plan.json
        # DeepFlow 契约: 若 context 已提供 execution_plan_path，直接使用
        execution_plan_path = context.get("execution_plan_path")
        if not execution_plan_path:
            execution_plan_path = self._generate_execution_plan(domain, context)

        # Step 5: 创建 PipelineOrchestrator 并注入 spawn_fn
        orchestrator = PipelineOrchestrator(
            domain=domain,
            user_context=context,
            spawn_fn=resolved_spawn,
            execution_plan_path=execution_plan_path,
        )

        print(f"[EntryHarness] Orchestrator ready for domain: {domain}")
        print(f"[EntryHarness] Session: {session_id}")
        print(f"[EntryHarness] Plan: {execution_plan_path}")

        return orchestrator

    def _validate_domain(self, domain: str) -> None:
        """
        验证 domain 是否支持

        Args:
            domain: 领域标识

        Raises:
            ValueError: domain 不支持
        """
        supported_domains = ["solution", "investment", "code", "general"]
        if domain not in supported_domains:
            raise ValueError(
                f"Unsupported domain: '{domain}'. "
                f"Supported: {supported_domains}"
            )

        # 检查领域配置目录存在
        domain_dir = _DEEPFLOW_BASE / "domains" / domain
        if not domain_dir.exists():
            self.warnings.append(f"Domain directory not found: {domain_dir}")
            # 不阻断，某些领域可能没有独立目录

        # 检查 cage 契约存在
        cage_path = _DEEPFLOW_BASE / "cage" / f"domain_{domain}.yaml"
        if not cage_path.exists():
            self.warnings.append(f"Domain contract not found: {cage_path}")

    def _init_session(self, domain: str, context: Dict[str, Any]) -> str:
        """
        初始化 session，生成 session_id 和 Blackboard 目录

        契约约束:
        - 若 context 中已提供 session_id，直接使用（不重新生成）
        - 否则按领域规则生成新的 session_id

        Args:
            domain: 领域标识
            context: 用户上下文

        Returns:
            session_id 字符串
        """
        # DeepFlow 契约: session_id 一致性
        # 若外层 Orchestrator 已生成 session_id，直接使用
        existing_session_id = context.get("session_id")
        if existing_session_id:
            print(f"[EntryHarness] 使用已存在的 session_id: {existing_session_id}")
            # 确保 Blackboard 目录存在
            bb = BlackboardManager(session_id=existing_session_id)
            bb.init_session()
            return existing_session_id

        if domain == "solution":
            from domains.solution.orchestrator_agent import SolutionOrchestratorV21

            topic = context.get("topic", "")
            solution_type = context.get("solution_type", "architecture")
            session_prefix = context.get("session_prefix")

            if not topic:
                raise ValueError("Domain 'solution' requires 'topic' in context")

            orch = SolutionOrchestratorV21(
                topic=topic,
                solution_type=solution_type,
                mode=context.get("mode", "standard"),
                constraints=context.get("constraints"),
                stakeholders=context.get("stakeholders"),
                session_prefix=session_prefix,
            )
            session_id = orch.init()

        elif domain == "investment":
            from domains.investment import InvestmentOrchestrator

            code = context.get("code", "")
            name = context.get("name", "")

            if not code or not name:
                raise ValueError("Domain 'investment' requires 'code' and 'name' in context")

            orch = InvestmentOrchestrator()
            # InvestmentOrchestrator 的 run() 生成 session_id，这里手动生成
            import re
            import uuid

            if not re.match(r"^\d{6}\.(SH|SZ|BJ)$", code):
                raise ValueError(f"Invalid code format: {code}")
            if not (2 <= len(name) <= 20):
                raise ValueError(f"Name length must be 2-20: {len(name)}")

            code_clean = code.replace(".", "_").lower()
            name_clean = name.lower().replace(" ", "_")[:10]
            hash_part = uuid.uuid4().hex[:8]
            session_id = f"inv_{name_clean}_{code_clean}_{hash_part}"

            # 创建 Blackboard
            bb = BlackboardManager(session_id=session_id)
            bb.init_session()

            # 保存基础上下文
            bb.write("context.json", {
                "domain": "investment",
                "code": code,
                "name": name,
                "session_id": session_id,
            })

        else:
            # 通用 domain
            import uuid
            topic = context.get("topic", "unknown")
            safe_topic = "".join(c for c in topic if c.isalnum() or c in "_- ")[:20]
            session_id = f"{domain}_{safe_topic}_{uuid.uuid4().hex[:8]}"

            bb = BlackboardManager(session_id=session_id)
            bb.init_session()
            bb.write("context.json", {"domain": domain, **context})

        return session_id

    def _generate_execution_plan(self, domain: str, context: Dict[str, Any]) -> str:
        """
        生成 execution_plan.json 和 tasks.json

        Args:
            domain: 领域标识
            context: 用户上下文（包含 session_id）

        Returns:
            execution_plan.json 的绝对路径
        """
        session_id = context["session_id"]
        session_dir = _DEEPFLOW_BASE / "blackboard" / session_id

        if domain == "solution":
            # 使用 SolutionOrchestratorV21 生成任务和计划
            from domains.solution.orchestrator_agent import SolutionOrchestratorV21

            topic = context.get("topic", "")
            solution_type = context.get("solution_type", "architecture")
            session_prefix = context.get("session_prefix")

            orch = SolutionOrchestratorV21(
                topic=topic,
                solution_type=solution_type,
                mode=context.get("mode", "standard"),
                constraints=context.get("constraints"),
                stakeholders=context.get("stakeholders"),
                session_prefix=session_prefix,
            )
            orch.init()
            tasks = orch.get_all_tasks()
            plan = orch.save_execution_plan()
            orch.save_tasks()

            # 返回 plan 文件路径
            plan_path = session_dir / "execution_plan.json"
            return str(plan_path)

        elif domain == "investment":
            # Investment 领域：构建简化版 execution_plan
            # 投资分析采用单轮执行，阶段固定
            phases = [
                {
                    "phase": 1,
                    "stage": "data_collection",
                    "worker": "data_manager",
                    "parallel": False,
                    "timeout": 300,
                },
                {
                    "phase": 2,
                    "stage": "search",
                    "worker": "search_engine",
                    "parallel": False,
                    "timeout": 300,
                },
                {
                    "phase": 3,
                    "stage": "research",
                    "workers": [
                        "researcher_finance",
                        "researcher_tech",
                        "researcher_market",
                    ],
                    "parallel": True,
                    "timeout": 300,
                },
                {
                    "phase": 4,
                    "stage": "audit",
                    "workers": [
                        "auditor_factual",
                        "auditor_upside",
                        "auditor_downside",
                    ],
                    "parallel": True,
                    "timeout": 300,
                },
                {
                    "phase": 5,
                    "stage": "summarize",
                    "worker": "summarizer",
                    "parallel": False,
                    "timeout": 300,
                },
            ]

            plan = {
                "session_id": session_id,
                "domain": "investment",
                "context": context,
                "phases": phases,
            }

            tasks = {
                "data_manager": f"投资数据采集：{context.get('name')} ({context.get('code')})",
                "search_engine": f"投资补充搜索：{context.get('name')}",
                "researcher_finance": f"财务研究：{context.get('name')}",
                "researcher_tech": f"技术研究：{context.get('name')}",
                "researcher_market": f"市场研究：{context.get('name')}",
                "auditor_factual": f"事实审计：{context.get('name')}",
                "auditor_upside": f"上行风险审计：{context.get('name')}",
                "auditor_downside": f"下行风险审计：{context.get('name')}",
                "summarizer": f"投资汇总：{context.get('name')}",
            }

            plan_path = session_dir / "execution_plan.json"
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=2)

            tasks_path = session_dir / "tasks.json"
            with open(tasks_path, "w", encoding="utf-8") as f:
                json.dump(tasks, f, ensure_ascii=False, indent=2)

            return str(plan_path)

        else:
            # 通用领域：最小执行计划
            phases = [
                {
                    "phase": 1,
                    "stage": "execution",
                    "worker": "general_worker",
                    "parallel": False,
                    "timeout": 300,
                }
            ]
            plan = {
                "session_id": session_id,
                "domain": domain,
                "context": context,
                "phases": phases,
            }

            tasks = {
                "general_worker": f"通用任务：{context.get('topic', 'unknown')}",
            }

            plan_path = session_dir / "execution_plan.json"
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=2)

            tasks_path = session_dir / "tasks.json"
            with open(tasks_path, "w", encoding="utf-8") as f:
                json.dump(tasks, f, ensure_ascii=False, indent=2)

            return str(plan_path)

    def get_validation_report(self) -> Dict[str, Any]:
        """获取验证报告"""
        return {
            "errors": self.errors,
            "warnings": self.warnings,
        }


# ============================================================================
# 便捷函数
# ============================================================================

def start_pipeline(
    domain: str,
    context: Dict[str, Any],
    spawn_fn=None,
) -> PipelineOrchestrator:
    """
    便捷函数：验证并启动管线编排器

    Args:
        domain: 领域标识
        context: 领域特定上下文
        spawn_fn: 注入的 spawn 函数

    Returns:
        配置完成的 PipelineOrchestrator 实例
    """
    harness = EntryHarness()
    return harness.validate_and_start(domain, context, spawn_fn)


if __name__ == "__main__":
    print("✅ entry_harness.py loaded successfully")
    print("Available classes: EntryHarness")
    print("Available functions: start_pipeline")
