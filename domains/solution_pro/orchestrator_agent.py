"""
Solution Orchestrator V3，使用 BlackboardManager 和安全验证器

Version: 2.1.0
Author: DeepFlow Solution Pro
Date: 2026-06-01
"""

"""
Solution Orchestrator V3 - 需求覆盖完整性 + Harness评分体系重构
==========================================================

基于修复计划V3的6项改动:
1. data_collection扩展：输出collection.json + structured_requirements.json
2. Planning输入扩展：同时读取structured_requirements.json + collection.json
3. Worker task重构：primary_focus + cross_domain_alert（删除not_responsible_for）
4. Harness V2重构：定性红绿灯(green/yellow/red) + 与approval合并为quality_gate
5. Harness Final检查基准：基于structured_requirements.json做全局覆盖度检查
6. audit交叉验证：验证Worker自检诚实性

职责:
1. 生成 session_id
2. 创建 blackboard 目录
3. 生成所有 Worker Tasks(10 Stage + Harness V3)
4. (由主Agent)使用 sessions_spawn 创建 Workers

Harness V3 特性:
- 统一4维度:完整性(30%) / 必要性(20%) / 目标一致性(30%) / 全局影响(20%)
- Layer 1: 所有Worker基础约束
- Layer 2: Planner生成场景约束
- 质量节点: Planning/Consolidator内嵌 + Final独立门禁
- 结构化需求清单: structured_requirements.json作为权威需求来源
- Worker自检诚实性验证: audit阶段交叉验证

禁止: 直接调用 openclaw
"""

import sys
import os
import json
import re
import unicodedata
import glob
import warnings

from typing import Optional, List, Dict, Any, Callable

import core.bootstrap
from core.config.path_config import PathConfig

DEEPFLOW_BASE = str(PathConfig.resolve().base_dir)

from domains.solution_pro.task_builder import (
    build_data_collection_task,
    build_planner_task,
    build_researcher_task,
    build_reviewer_task,
    build_auditor_task,
    build_fixer_task_with_audit,
    build_harness_final_task,
    build_consolidator_task,
    build_fixer_expert_task,
    build_summarizer_task,
    inject_req_traceability,
    validate_stage_output,
    HARNESS_EXEMPT_STAGES,
    LAYER2_READ_INSTRUCTION,
)
from domains.solution_pro.blackboard import BlackboardManager, STAGE_PATH_REGISTRY
from domains.solution_pro.frozen_spec import write_frozen_spec
from domains.solution_pro.security_validator import SecurityValidator


STAGE_OUTPUT_PATHS = {
    "data_collection": STAGE_PATH_REGISTRY["data_collection"],
    "planning": STAGE_PATH_REGISTRY["planning"],
    "consolidator": STAGE_PATH_REGISTRY["consolidator"],
    "audit": STAGE_PATH_REGISTRY["audit"],
    "fix": STAGE_PATH_REGISTRY["fix"],
    "fixer_expert": STAGE_PATH_REGISTRY["fixer_expert"],
    "harness_final": STAGE_PATH_REGISTRY["harness_final"],
    "summarizer": STAGE_PATH_REGISTRY["summarizer"],
}


PARALLEL_OUTPUT_PATHS = {
    "reviewers": {
        "technical": STAGE_PATH_REGISTRY["reviewer_technical"],
        "business": STAGE_PATH_REGISTRY["reviewer_business"],
        "risk": STAGE_PATH_REGISTRY["reviewer_risk"],
    },
    "research": {
        "expert_1": STAGE_PATH_REGISTRY["research_expert_1"],
        "expert_2": STAGE_PATH_REGISTRY["research_expert_2"],
        "expert_3": STAGE_PATH_REGISTRY["research_expert_3"],
    },
}


def resolve_worker_output_path(stage_name: str, worker_id: str) -> str:
    """Resolve parallel worker output paths through STAGE_PATH_REGISTRY."""
    if stage_name == "reviewers":
        registry_key = f"reviewer_{worker_id}"
    elif stage_name == "research":
        registry_key = f"research_{worker_id}"
    else:
        registry_key = f"{stage_name}_{worker_id}"
    return STAGE_PATH_REGISTRY.get(
        registry_key,
        PARALLEL_OUTPUT_PATHS.get(stage_name, {}).get(worker_id, f"stages/{stage_name}_{worker_id}.json"),
    )


class _SolutionDispatcher:
    """Solution Dispatcher - 内部实现，不要直接使用
    
    请使用 `from domains.solution_pro import run_solution_pro` 启动。
    """

    def __init__(self, topic: str, solution_type: str = "architecture",
                 mode: str = "standard", constraints: list = None,
                 stakeholders: list = None,
                 session_prefix: Optional[str] = None,
                 spawn_fn=None,
                 living_spec: Optional[dict] = None):
        """
        初始化 Solution Orchestrator V2.1

        Args:
            topic: 设计主题(必需)
            solution_type: 方案类型(architecture/business/technical)
            mode: 运行模式(standard/rigorous)
            constraints: 约束条件列表
            stakeholders: 利益相关者列表
            session_prefix: 会话前缀(可选)
            spawn_fn: 注入的 spawn 函数(契约笼子要求)
            living_spec: Spec Pro 产出的 Living Spec(可选,向后兼容)
        """
        # 输入验证
        if not topic or len(topic.strip()) == 0:
            raise ValueError("topic cannot be empty")
        if len(topic) < 5:
            raise ValueError(f"topic too short (minimum 5 characters): '{topic}'")
        if len(topic) > 200:
            raise ValueError(f"topic too long (maximum 200 characters): '{topic[:50]}...'")

        valid_types = ["architecture", "business", "technical"]
        if solution_type not in valid_types:
            raise ValueError(f"invalid solution type '{solution_type}', must be one of {valid_types}")

        valid_modes = ["standard", "rigorous"]
        if mode not in valid_modes:
            raise ValueError(f"invalid mode '{mode}', must be one of {valid_modes}")

        if constraints is not None and not isinstance(constraints, list):
            raise TypeError("constraints must be a list or None")

        if stakeholders is not None and not isinstance(stakeholders, list):
            raise TypeError("stakeholders must be a list or None")

        self.topic = topic
        self.solution_type = solution_type
        self.mode = mode
        self.constraints = constraints or []
        self.stakeholders = stakeholders or []
        self.session_prefix = session_prefix
        self.session_id = None
        self.base_path = None
        self.blackboard = None  # BlackboardManager 实例
        self._spawn_fn = spawn_fn or self._resolve_spawn_fn()
        self.living_spec = living_spec  # Spec Pro Living Spec(可选)
        self._security_validator = SecurityValidator()  # 安全验证器

    def _resolve_spawn_fn(self):
        """
        解析 spawn 函数。
        
        契约笼子约束：Python 代码禁止直接 import openclaw SDK。
        spawn_fn 必须由调用方显式注入，此处不再尝试 fallback。
        
        Returns:
            None — 调用方必须通过构造函数参数注入 spawn_fn
        """
        return None

    @staticmethod
    def extract_prefix(topic: str, max_len: int = 20) -> str:
        """
        从 topic 提取核心主题作为 session 前缀

        规则:
        1. 清理特殊字符(保留中文、字母、数字、连字符)
        2. 截断到 max_len(默认20,不超过30)
        3. 若截断后过短(<2),返回"topic"

        Args:
            topic: 原始主题字符串
            max_len: 最大前缀长度(默认20,硬上限30)

        Returns:
            清理后的前缀字符串
        """
        max_len = min(max_len, 30)
        safe = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', topic)
        safe = ''.join(
            c for c in safe
            if unicodedata.category(c) not in ['Cc', 'Cf', 'Cs', 'Co', 'Cn']
        )
        prefix = safe[:max_len].strip('_')
        if len(prefix) < 2:
            return "topic"
        return prefix

    def _generate_session_id(self, safe_topic: str) -> str:
        """
        生成 session_id,遵循短命名设计(V3 恢复)

        格式:
        - 有 session_prefix: {prefix}_{type}_{hash8}
        - 无 session_prefix: {topic_prefix20}_{type}_{hash8}

        确保总长度 <= 50 字符

        Args:
            safe_topic: 已清理的主题字符串(可作为后备)

        Returns:
            生成的 session_id
        """
        import hashlib

        topic_hash = hashlib.md5(self.topic.encode()).hexdigest()[:8]

        if self.session_prefix:
            # 显式传入前缀:清理后截断到20字符
            prefix = self.extract_prefix(self.session_prefix, max_len=20)
        else:
            # 未传入:从 topic 提取前20字符
            prefix = self.extract_prefix(self.topic, max_len=20)

        # 组合:{prefix}_{type}_{hash8}
        session_id = f"{prefix}_{self.solution_type}_{topic_hash}"

        # 最终安全检查:长度 <= 50
        if len(session_id) > 50:
            overflow = len(session_id) - 50
            prefix = prefix[:max(2, len(prefix) - overflow)]
            session_id = f"{prefix}_{self.solution_type}_{topic_hash}"

        return session_id

    def init(self) -> str:
        """初始化 session,生成 session_id 和目录结构"""
        # 先检查路径遍历（拒绝危险输入），再清理
        self._security_validator.check_path_traversal(self.topic)
        safe_topic = self._security_validator.sanitize_topic(self.topic)

        # V3 修复:使用短命名生成 session_id
        self.session_id = self._generate_session_id(safe_topic)
        
        # 初始化 BlackboardManager（统一路径管理）
        self.blackboard = BlackboardManager(self.session_id)
        self.base_path = str(self.blackboard.base_path)
        write_frozen_spec(self.base_path, self.topic, self.constraints, self.living_spec)

        print(f"[SolutionDispatcher] Session: {self.session_id}")
        print(f"[SolutionDispatcher] Session length: {len(self.session_id)} chars")
        return self.session_id

    def _read_dynamic_experts(self) -> list:
        """P1-1 修复: 从 planning.json 读取 Planner 动态生成的专家列表
        
        Returns:
            list: 专家列表，格式与 default_experts 一致
            空列表: 如果 planning.json 不存在或无 required_experts
        """
        if not self.base_path:
            return []
        planning_path = f"{self.base_path}/stages/planning.json"
        try:
            with open(planning_path, 'r', encoding='utf-8') as f:
                planning = json.load(f)
            experts_raw = planning.get("required_experts", [])
            if not experts_raw:
                return []
            # 转换为与 default_experts 一致的格式
            result = []
            for i, exp in enumerate(experts_raw, 1):
                result.append({
                    "id": exp.get("name", f"expert_{i}"),
                    "name": exp.get("name", f"expert_{i}"),
                    "angle": exp.get("angle", "综合分析"),
                    "reason": exp.get("reason", ""),
                })
            print(f"[SolutionDispatcher] P1-1: 使用 Planner 动态专家 ({len(result)} 个)")
            return result
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            print(f"[SolutionDispatcher] P1-1: planning.json 未找到，使用默认专家")
            return []

    def get_all_tasks(self) -> dict:
        """获取所有 Worker Tasks(11阶段完整管线)"""
        # 检查session_id是否已初始化
        if not self.session_id:
            raise RuntimeError(
                "Must call init() before get_all_tasks(). "
                f"Usage: orch = SolutionOrchestratorV2(...); orch.init(); tasks = orch.get_all_tasks()"
            )

        # 根据 mode 确定 pipeline
        # 删除 quick 模式,所有运行都使用完整 10 阶段 Harness V2
        pipeline = [
            "data_collection",      # Stage 1: 数据采集
            "planning",             # Stage 2: 规划(内嵌Harness自评)
            "reviewers",            # Stage 3: 三视角评审(并行×3)
            "research",             # Stage 4: 深度研究(并行×3)
            "consolidator",         # Stage 5: 成果整合(内嵌Harness检查)
            "audit",                # Stage 6: 审计
            "fix",                  # Stage 7: 初步修正
            "fixer_expert",         # Stage 8: 深度修正
            "harness_final",        # Stage 9: 最终质量门禁(独立Harness)
            "summarizer"            # Stage 10: 最终总结
        ]

        tasks = {}

        for stage in pipeline:
            if stage == "data_collection":
                tasks[stage] = build_data_collection_task(
                    self.session_id, self.topic, self.constraints,
                    living_spec=self.living_spec
                )

            elif stage == "planning":
                # Stage 2: 规划(内嵌Harness自评)
                tasks[stage] = build_planner_task(
                    self.session_id, self.topic, self.solution_type,
                    self.constraints, self.stakeholders,
                    living_spec=self.living_spec
                )

            elif stage == "reviewers":
                # Stage 3: 三视角评审(并行)
                tasks[stage] = {}
                reviewer_configs = [
                    {
                        "type": "technical",
                        "focus": "技术架构合理性、技术选型匹配度、性能指标可达性"
                    },
                    {
                        "type": "business",
                        "focus": "ROI合理性、市场竞争力、商业模式可行性"
                    },
                    {
                        "type": "risk",
                        "focus": "技术风险、业务连续性风险、合规风险"
                    }
                ]
                # P0-3 修复: 注入 Layer 2 读取指令，让 Reviewer 运行时读取 planning.json
                planning_path = f"{self.base_path}/stages/planning.json"
                for config in reviewer_configs:
                    base_task = build_reviewer_task(
                        self.session_id, self.topic,
                        config["type"], config["focus"],
                        {"plan": "from_planner"},
                        living_spec=self.living_spec
                    )
                    # P0-3: 追加 Layer 2 运行时读取指令
                    layer2_instruction = LAYER2_READ_INSTRUCTION.format(
                        planning_path=planning_path,
                        worker_role=f"reviewer_{config['type']}"
                    )
                    tasks[stage][config["type"]] = base_task + "\n" + layer2_instruction

            # elif stage == "harness_v3":
            #     # Stage 4: 中期质量检查(回滚中,暂不启用)
            #     pass

            elif stage == "research":
                # B 方案: 固定 10 阶段 + 固定 research worker 槽位。
                # Planning 完成后 control_contract.py 会把 Planner 生成的专家
                # 映射进 expert_1/expert_2/expert_3 的 prompt，不改变 worker 列表。
                experts = [
                    {
                        "id": "expert_1",
                        "name": "技术架构专家",
                        "angle": "高并发系统架构与性能优化",
                        "reason": "日均百万订单需要分析 QPS、延迟、吞吐量"
                    },
                    {
                        "id": "expert_2",
                        "name": "最佳实践专家",
                        "angle": "行业最佳实践与标杆案例分析",
                        "reason": "参考行业领先方案,避免重复造轮子"
                    },
                    {
                        "id": "expert_3",
                        "name": "风险评估专家",
                        "angle": "系统风险识别与容错设计",
                        "reason": "识别单点故障、级联故障等风险"
                    }
                ]

                tasks[stage] = {}
                for expert in experts:
                    tasks[stage][expert["id"]] = build_researcher_task(
                        expert["name"], self.session_id, self.topic,
                        {"type": self.solution_type, "constraints": self.constraints},
                        expert_id=expert["id"],
                        angle=expert["angle"],
                        reason=expert["reason"],
                        living_spec=self.living_spec
                    )

            elif stage == "consolidator":
                # Stage 6: 成果整合
                research_inputs = [
                    {
                        "worker_id": expert_id,
                        "path": str(self.blackboard.base_path / resolve_worker_output_path("research", expert_id)),
                    }
                    for expert_id in ("expert_1", "expert_2", "expert_3")
                ]
                tasks[stage] = build_consolidator_task(
                    self.session_id, self.topic,
                    research_inputs,
                    living_spec=self.living_spec
                )

            elif stage == "audit":
                # Stage 6: 审计
                # P0-3: 注入 Layer 2 运行时读取指令
                planning_path = f"{self.base_path}/stages/planning.json"
                base_task = build_auditor_task(
                    self.session_id, self.topic,
                    {"type": self.solution_type, "constraints": self.constraints},
                    living_spec=self.living_spec
                )
                layer2_instruction = LAYER2_READ_INSTRUCTION.format(
                    planning_path=planning_path,
                    worker_role="auditor"
                )
                tasks[stage] = base_task + "\n" + layer2_instruction

            elif stage == "fix":
                # Stage 7: 初步修正
                audit_path = str(self.blackboard.get_stage_path("audit"))
                # P0-3: 注入 Layer 2 运行时读取指令
                planning_path = f"{self.base_path}/stages/planning.json"
                base_task = build_fixer_task_with_audit(
                    self.session_id, self.topic, audit_path,
                    living_spec=self.living_spec
                )
                layer2_instruction = LAYER2_READ_INSTRUCTION.format(
                    planning_path=planning_path,
                    worker_role="fixer"
                )
                tasks[stage] = base_task + "\n" + layer2_instruction

            elif stage == "fixer_expert":
                # Stage 8: 深度修正
                # P0-3: 注入 Layer 2 运行时读取指令
                planning_path = f"{self.base_path}/stages/planning.json"
                base_task = build_fixer_expert_task(
                    self.session_id, self.topic,
                    [
                        {
                            "source": "audit",
                            "path": str(self.blackboard.get_stage_path("audit")),
                            "extract": "data.issues 或 data.audit_findings 中 severity/level 为 critical/P0 的问题",
                        },
                        {
                            "source": "fix",
                            "path": str(self.blackboard.get_stage_path("fix")),
                            "extract": "已完成的初步修复,用于避免重复修复并验证残留问题",
                        },
                    ],
                    severity="critical",
                    living_spec=self.living_spec
                )
                layer2_instruction = LAYER2_READ_INSTRUCTION.format(
                    planning_path=planning_path,
                    worker_role="fixer_expert"
                )
                tasks[stage] = base_task + "\n" + layer2_instruction

            elif stage == "harness_final":
                # Stage 9: 最终质量门禁(独立Harness V2)
                tasks[stage] = build_harness_final_task(
                    self.session_id, self.topic,
                    living_spec=self.living_spec
                )

            elif stage == "summarizer":
                # Stage 10: 最终总结
                upstream_outputs = {
                    name: str(self.blackboard.base_path / rel_path)
                    for name, rel_path in STAGE_PATH_REGISTRY.items()
                    if name in {
                        "data_collection",
                        "planning",
                        "reviewer_technical",
                        "reviewer_business",
                        "reviewer_risk",
                        "research_expert_1",
                        "research_expert_2",
                        "research_expert_3",
                        "consolidator",
                        "audit",
                        "fix",
                        "fixer_expert",
                        "harness_final",
                        "frozen_spec",
                        "structured_requirements",
                        "requirements_traceability_matrix",
                    }
                }
                tasks[stage] = build_summarizer_task(
                    self.session_id, self.topic,
                    upstream_outputs,
                    living_spec=self.living_spec
                )

        return self._inject_req_traceability(tasks)

    def _inject_req_traceability(self, tasks: dict) -> dict:
        """Append frozen-spec REQ-ID tracing instructions to every worker task."""
        enriched = {}
        for key, value in tasks.items():
            if isinstance(value, dict):
                enriched[key] = {
                    worker_id: inject_req_traceability(task, self.session_id)
                    for worker_id, task in value.items()
                }
            elif isinstance(value, str):
                enriched[key] = inject_req_traceability(value, self.session_id)
            else:
                enriched[key] = value
        return enriched

    def save_execution_plan(self):
        """保存执行计划"""
        tasks = self.get_all_tasks()

        # 构建 phases
        phases = []
        for stage_name, task in tasks.items():
            if isinstance(task, dict):
                # 并行阶段(如 research)
                phases.append({
                    "phase": len(phases) + 1,
                    "stage": stage_name,
                    "workers": [
                        {
                            "id": worker_id,
                            "task_key": f"{stage_name}.{worker_id}",
                            "expected_output_path": resolve_worker_output_path(stage_name, worker_id),
                            "timeout": 300,
                        }
                        for worker_id in task.keys()
                    ],
                    "parallel": True,
                    "timeout": 300
                })
            else:
                # 串行阶段
                phases.append({
                    "phase": len(phases) + 1,
                    "stage": stage_name,
                    "worker": stage_name,
                    "task_key": stage_name,
                    "parallel": False,
                    "timeout": 300,
                    "expected_output_path": STAGE_OUTPUT_PATHS.get(stage_name, f"stages/{stage_name}.json"),
                })

        plan = {
            "session_id": self.session_id,
            "topic": self.topic,
            "solution_type": self.solution_type,
            "mode": self.mode,
            "constraints": self.constraints,
            "stakeholders": self.stakeholders,
            "version": "2.1",
            "control_contract_path": "control_contract.json",
            "phases": phases
        }

        plan_path = f"{self.base_path}/execution_plan.json"
        with open(plan_path, 'w', encoding='utf-8') as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)

        self._ensure_initial_control_contract()
        return plan

    def _ensure_initial_control_contract(self) -> None:
        """Create the plan-referenced control contract before Planner output exists."""
        try:
            from domains.solution_pro.control_contract import build_control_contract

            contract_path = f"{self.base_path}/control_contract.json"
            contract = build_control_contract(self.base_path)
            with open(contract_path, 'w', encoding='utf-8') as f:
                json.dump(contract, f, ensure_ascii=False, indent=2)
        except (ImportError, OSError, TypeError, ValueError) as e:
            warnings.warn(f"Failed to create initial control_contract.json: {e}")

    def save_tasks(self):
        """保存所有 tasks"""
        tasks = self.get_all_tasks()
        tasks_path = f"{self.base_path}/tasks.json"
        with open(tasks_path, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
        return tasks

    # ========== Harness V2 完整闭环执行(Solution Pro 默认执行方式)==========

    def run_harness_v2(self, spawn_fn=None) -> dict:
        """
        使用 EntryHarness + PipelineOrchestrator 完整闭环执行 Solution Pro

        这是真正的默认执行方式(方式3):
        - EntryHarness 验证 + 初始化 + 生成执行计划
        - PipelineOrchestrator 按 phase 顺序 spawn Workers 并执行
        - 串行 phase 逐个 spawn,等待完成
        - 并行 phase(reviewers/research)同时 spawn
        - 每阶段完成后更新 Blackboard progress.json
        - Summarizer 验证闭环执行

        DeepFlow 基础契约:
        - 跨阶段依赖通过 Blackboard 传递
        - 错误处理有 fallback 机制(默认约束、空列表)
        - 状态变更可观测(日志记录)
        - 关键路径有验证检查点(Summarizer 验证)
        - 向后兼容(get_all_tasks 保持不变)

        Args:
            spawn_fn: 注入的 spawn 函数(主Agent提供,如 sessions_spawn)

        Returns:
            {
                "status": "completed" | "failed" | "partial" | "requires_human_review",
                "session_id": str,
                "base_path": str,
                "results": dict,          # PipelineOrchestrator 返回的完整结果
                "harness_v2": True,
            }

        Raises:
            RuntimeError: spawn_fn 未注入
        """
        # Step 0: 验证 spawn_fn(契约笼子:使用注入的 spawn_fn)
        spawn = spawn_fn or self._spawn_fn
        if not spawn:
            self.save_tasks()
            self.save_execution_plan()
            return {
                "status": "requires_main_agent",
                "session_id": self.session_id,
                "base_path": self.base_path,
                "plan_path": f"{self.base_path}/execution_plan.json",
                "harness_v2": False,
                "reason": (
                    "spawn_fn 不可用。已生成 tasks.json 和 execution_plan.json；"
                    "请在主 Agent 环境注入 spawn_fn 后执行完整管线。"
                ),
            }

        print("=" * 80)
        print("[Harness V2] 启动 Solution Pro 完整闭环执行")
        print("=" * 80)
        print(f"Session: {self.session_id}")
        print(f"Topic: {self.topic}")
        print(f"Mode: {self.mode}")
        print()

        # Step 1: 生成 execution_plan.json 和 tasks.json(必须先保存到 Blackboard)
        tasks = self.get_all_tasks()
        self.save_tasks()
        self.save_execution_plan()

        execution_plan_path = f"{self.base_path}/execution_plan.json"

        # Step 2: 直接创建 PipelineOrchestrator（跳过 EntryHarness，避免重复实例化）
        from core.orchestrator.pipeline_orchestrator import PipelineOrchestrator

        orchestrator = PipelineOrchestrator(
            domain="solution",
            user_context={
                "topic": self.topic,
                "solution_type": self.solution_type,
                "mode": self.mode,
                "constraints": self.constraints,
                "stakeholders": self.stakeholders,
                "session_id": self.session_id,
                "base_path": self.base_path,
                "session_prefix": self.session_prefix,
            },
            spawn_fn=spawn,
            execution_plan_path=execution_plan_path,
        )

        # Step 3: 执行管线(真正 spawn Workers)
        result = orchestrator.run_pipeline(execution_plan_path)

        # Step 4: 返回结果
        status = result.get("status", "unknown")
        print()
        print("=" * 80)
        print(f"[Harness V2] 管线执行完成 | 状态: {status}")
        print("=" * 80)
        print()

        return {
            "status": status,
            "session_id": self.session_id,
            "base_path": self.base_path,
            "results": result,
            "harness_v2": True,
        }

    def _read_harness_final_feedback(self) -> list:
        """
        读取Harness Final的反馈意见

        DeepFlow基础契约:
        - 跨阶段依赖通过Blackboard传递
        - 错误处理有fallback机制(返回空列表)
        """
        harness_path = str(self.blackboard.get_stage_path("harness_final"))

        try:
            with open(harness_path, 'r', encoding='utf-8') as f:
                harness_output = json.load(f)

            feedback = harness_output.get("feedback", [])
            print(f"[Harness Final] 从Blackboard读取到{len(feedback)}条反馈意见")
            return feedback

        except FileNotFoundError:
            print(f"[Harness Final] Warning: 输出文件不存在,使用空列表")
            return []

        except json.JSONDecodeError as e:
            print(f"[Harness Final] Error: 输出解析失败: {e}")
            return []

    def _read_harness_final_improvements(self) -> list:
        """
        读取Harness Final的改进建议

        DeepFlow基础契约:
        - 跨阶段依赖通过Blackboard传递
        - 错误处理有fallback机制
        """
        harness_path = str(self.blackboard.get_stage_path("harness_final"))

        try:
            with open(harness_path, 'r', encoding='utf-8') as f:
                harness_output = json.load(f)

            improvements = harness_output.get("improvements", [])
            return improvements

        except (FileNotFoundError, json.JSONDecodeError, IOError):
            return []

    # ========== 静态方法(V1兼容) ==========

    @staticmethod
    async def run(topic: str, solution_type: str = "architecture",
                  mode: str = "standard", constraints: list = None,
                  stakeholders: list = None, spawn_fn=None,
                  session_prefix: Optional[str] = None) -> dict:
        """
        执行完整 Solution 流程(Harness V2 完整闭环 - 默认执行方式)

        .. deprecated:: 2026-05-31
            此方法已废弃。请使用 domains/solution/SKILL.md 中的标准执行方式。

        这是 Solution Pro 的唯一执行入口,使用 EntryHarness + PipelineOrchestrator
        完整闭环:
        - EntryHarness 验证配置、初始化 Blackboard、生成执行计划
        - PipelineOrchestrator 按 phase 顺序 spawn Workers 并执行
        - 并行阶段(reviewers/research)同时 spawn
        - 串行阶段逐个 spawn,等待完成
        - Summarizer 验证闭环执行

        Args:
            topic: 设计主题（必需）
            solution_type: 方案类型（architecture/business/technical）
            mode: 运行模式（standard/rigorous）
            constraints: 约束条件列表
            stakeholders: 利益相关者列表
            spawn_fn: 注入的 spawn 函数（如 sessions_spawn）。
                     若提供，执行完整 Harness V2 管线；
                     若未提供，只生成任务配置并给出清晰提示。
            session_prefix: 会话前缀(可选)

        Returns:
            执行结果字典
        """
        warnings.warn(
            "SolutionOrchestratorV21.run() 已废弃 (2026-05-31)。"
            "请使用 run_solution_pro(topic=..., spawn_fn=...)。",
            DeprecationWarning,
            stacklevel=2
        )
        
        orch = _SolutionDispatcher(
            topic=topic,
            solution_type=solution_type,
            mode=mode,
            constraints=constraints,
            stakeholders=stakeholders,
            session_prefix=session_prefix
        )
        session_id = orch.init()

        # 保存 tasks 和 execution_plan(供 PipelineOrchestrator 读取)
        orch.save_tasks()
        orch.save_execution_plan()

        if spawn_fn:
            # Harness V2 完整闭环执行(PipelineOrchestrator 在主Agent进程中运行,使用注入的 spawn_fn)
            print(f"[Solution Pro] 使用 Harness V2 执行")
            result = orch.run_harness_v2(spawn_fn=spawn_fn)
            return {
                "success": result["status"] in ["completed", "partial"],
                "session_id": session_id,
                "status": result["status"],
                "base_path": result["base_path"],
                "harness_v2": True,
                "result": result
            }
        else:
            # 未提供 spawn_fn:只生成任务配置(向后兼容 / 调试模式)
            print(f"[Solution Pro] 未提供 spawn_fn,任务已生成但未执行")
            return {
                "success": True,
                "session_id": session_id,
                "status": "tasks_generated",
                "base_path": orch.base_path,
                "harness_v2": False,
                "note": (
                    "未提供 spawn_fn,任务已生成但未执行。"
                    "在主Agent中运行并传入 spawn_fn 以执行完整管线。"
                    "\n示例:await SolutionOrchestratorV21.run(..., spawn_fn=sessions_spawn)"
                )
            }

    # ========== 静态方法 ==========

def main():
    """入口"""
    orch = _SolutionDispatcher(
        topic="设计一个支持百万日订单的电商订单系统",
        solution_type="architecture",
        mode="standard",
        constraints=["日均百万订单", "99.99%可用性", "<200ms响应时间"],
        stakeholders=["技术团队", "产品团队", "运维团队"]
    )
    session_id = orch.init()
    tasks = orch.get_all_tasks()
    plan = orch.save_execution_plan()
    orch.save_tasks()
    print(f"\n✅ Solution Orchestrator V2.1 (Harness V2) 初始化完成")
    print(f"   Session: {session_id}")
    print(f"   Tasks: {len(tasks)} stages (10 Stage Pipeline)")
    print(f"   Harness: 4维度 (30/20/30/20) + Layer 1/2 + Final门禁")
    return session_id, tasks


if __name__ == "__main__":
    main()
