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

from core.config.path_config import PathConfig

DEEPFLOW_BASE = str(PathConfig.resolve().base_dir)
sys.path.insert(0, DEEPFLOW_BASE)

from domains.solution.task_builder import (
    build_data_collection_task,
    build_planner_task,
    build_researcher_task,
    build_reviewer_task,
    build_auditor_task,
    build_fixer_task_with_audit,
    build_harness_final_task,
    build_consolidator_task,
    build_fixer_expert_task,
    build_summarizer_task
)


class SolutionOrchestratorV21:
    """Solution Orchestrator V2.1 - Harness V2"""

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
        self._spawn_fn = spawn_fn or self._resolve_spawn_fn()
        self.living_spec = living_spec  # Spec Pro Living Spec(可选)

    def _resolve_spawn_fn(self):
        """解析 spawn 函数(fallback 机制,契约笼子要求)"""
        try:
            from openclaw import sessions_spawn
            return sessions_spawn
        except ImportError:
            return None

    def _sanitize_topic(self, topic: str) -> str:
        """
        WARN-001: 清理topic,仅保留安全字符

        过滤规则:
        - 只保留字母、数字、下划线、中文字符、连字符
        - 移除控制字符、格式字符、代理字符等危险Unicode类别
        - 截断到30字符

        Args:
            topic: 原始主题字符串

        Returns:
            清理后的安全主题字符串
        """
        safe_topic = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', topic)
        safe_topic = ''.join(
            c for c in safe_topic
            if unicodedata.category(c) not in ['Cc', 'Cf', 'Cs', 'Co', 'Cn']
        )
        return safe_topic[:30]

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

    def _check_path_traversal(self, topic: str) -> None:
        """
        WARN-002: 检查topic中是否包含路径遍历模式

        检测的危险模式包括:
        - '..' (父目录引用)
        - '../' 或 '..\\' (相对路径遍历)
        - './' (当前目录引用)
        - '~' (用户主目录)
        - '/' 或 '\\' (绝对路径)

        Args:
            topic: 待检查的主题字符串

        Raises:
            ValueError: 当检测到路径遍历模式时抛出异常
        """
        dangerous_patterns = ['..', '../', '..\\', './', '~', '/', '\\']
        for pattern in dangerous_patterns:
            if pattern in topic:
                raise ValueError(f"Path traversal detected: '{pattern}'")

    def init(self) -> str:
        """初始化 session,生成 session_id 和目录结构"""
        # WARN-002: 路径遍历检测(先检查,再处理)
        self._check_path_traversal(self.topic)

        # V3 修复:使用短命名生成 session_id
        self.session_id = self._generate_session_id(
            self._sanitize_topic(self.topic)
        )
        self.base_path = f"{DEEPFLOW_BASE}/blackboard/{self.session_id}"

        os.makedirs(f"{self.base_path}/data", exist_ok=True)
        os.makedirs(f"{self.base_path}/stages", exist_ok=True)

        print(f"[SolutionOrchestratorV2] Session: {self.session_id}")
        print(f"[SolutionOrchestratorV2] Session length: {len(self.session_id)} chars")
        return self.session_id

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
            "reviewers",            # Stage 3: 三维度评审(并行×3)
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
                # Stage 3: 三维度评审(并行)
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
                for config in reviewer_configs:
                    tasks[stage][config["type"]] = build_reviewer_task(
                        self.session_id, self.topic,
                        config["type"], config["focus"],
                        {"plan": "from_planner"},  # 实际应从blackboard读取
                        living_spec=self.living_spec
                    )

            # elif stage == "harness_v3":
            #     # Stage 4: 中期质量检查(回滚中,暂不启用)
            #     pass

            elif stage == "research":
                # Stage 5: 动态生成 researcher tasks
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
                tasks[stage] = build_consolidator_task(
                    self.session_id, self.topic,
                    []  # 实际应从blackboard读取researcher outputs
                )

            elif stage == "design":
                tasks[stage] = build_designer_task(
                    self.session_id, self.topic,
                    {"type": self.solution_type, "constraints": self.constraints}
                )

            elif stage == "audit":
                # Stage 7: 审计
                tasks[stage] = build_auditor_task(
                    self.session_id, self.topic,
                    {"type": self.solution_type, "constraints": self.constraints}
                )

            elif stage == "fix":
                # Stage 8: 初步修正
                audit_path = f"{self.base_path}/stages/audit.json"
                tasks[stage] = build_fixer_task_with_audit(
                    self.session_id, self.topic, audit_path
                )

            elif stage == "fixer_expert":
                # Stage 9: 深度修正
                tasks[stage] = build_fixer_expert_task(
                    self.session_id, self.topic,
                    [],  # 实际应从blackboard读取audit findings
                    severity="critical"  # 处理Critical和Major问题
                )

            elif stage == "harness_final":
                # Stage 9: 最终质量门禁(独立Harness V2)
                tasks[stage] = build_harness_final_task(
                    self.session_id, self.topic,
                    living_spec=self.living_spec
                )

            elif stage == "summarizer":
                # Stage 10: 最终总结
                tasks[stage] = build_summarizer_task(
                    self.session_id, self.topic,
                    {},  # 实际应从blackboard读取all_outputs
                    living_spec=self.living_spec
                )

        return tasks

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
                    "workers": list(task.keys()),
                    "parallel": True,
                    "timeout": 300
                })
            else:
                # 串行阶段
                phases.append({
                    "phase": len(phases) + 1,
                    "stage": stage_name,
                    "worker": stage_name,
                    "parallel": False,
                    "timeout": 300
                })

        plan = {
            "session_id": self.session_id,
            "topic": self.topic,
            "solution_type": self.solution_type,
            "mode": self.mode,
            "version": "2.0",
            "phases": phases
        }

        plan_path = f"{self.base_path}/execution_plan.json"
        with open(plan_path, 'w', encoding='utf-8') as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)

        return plan

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
            raise RuntimeError(
                "spawn_fn 不可用。"
                "必须在主Agent环境中运行,并传入 spawn_fn=sessions_spawn。"
                "\n正确用法:orch.run_harness_v2(spawn_fn=sessions_spawn)"
            )

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

        # Step 2: 使用 EntryHarness 初始化并创建 PipelineOrchestrator
        from core.quality.entry_harness import EntryHarness
        harness = EntryHarness()

        orchestrator = harness.validate_and_start(
            domain="solution",
            context={
                "topic": self.topic,
                "solution_type": self.solution_type,
                "mode": self.mode,
                "constraints": self.constraints,
                "stakeholders": self.stakeholders,
                "session_id": self.session_id,
                "base_path": self.base_path,
                "session_prefix": self.session_prefix,
            },
            spawn_fn=spawn
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
        harness_path = f"{self.base_path}/stages/harness_final.json"

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
        harness_path = f"{self.base_path}/stages/harness_final.json"

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
            "请使用 domains/solution/SKILL.md 中的标准执行方式。",
            DeprecationWarning,
            stacklevel=2
        )
        
        orch = SolutionOrchestratorV21(
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

    def run_legacy(self) -> dict:
        """
        传统执行方式(方式2,用于调试和向后兼容)

        .. deprecated:: 2026-05-31
            此方法已废弃。请使用 domains/solution/SKILL.md 中的标准执行方式。

        一次性生成所有任务,不执行Harness V2闭环。
        适用于快速查看任务结构或测试。

        Returns:
            任务配置字典
        """
        warnings.warn(
            "SolutionOrchestratorV21.run_legacy() 已废弃 (2026-05-31)。"
            "请使用 domains/solution/SKILL.md 中的标准执行方式。",
            DeprecationWarning,
            stacklevel=2
        )
        
        session_id = self.init()
        tasks = self.get_all_tasks()
        plan = self.save_execution_plan()
        self.save_tasks()

        return {
            "success": True,
            "session_id": session_id,
            "tasks_count": len(tasks),
            "plan": plan,
            "mode": "legacy"
        }


    # ========== V3 修复: 分阶段执行方法 (修复计划V3 - 6项改动) ==========

    def _run_data_collection(self, blackboard: str, spawn_fn: Callable) -> dict:
        """
        改动1: data_collection扩展职责——输出collection.json + structured_requirements.json
        """
        if not spawn_fn:
            raise RuntimeError("spawn_fn不可用，无法执行data_collection")
        print(f"[V3][Stage 1] data_collection...")
        task = build_data_collection_task(self.session_id, self.topic, self.constraints)
        extended_task = f"""{task}

【V3扩展】将requirements.md转换为structured_requirements.json：
1. 按模块分解(2.1-2.6)
2. 每个需求分配唯一ID(REQ-001, REQ-002...)
3. 输出JSON到 {blackboard}/data/structured_requirements.json
格式：{{"source":"...","requirements":[{{"id":"REQ-001","module":"2.1","category":"functional","text":"..."}}],"modules":["2.1"..."2.6"],"stakeholders":["..."],"constraints":{{"technical":[...],"business":[...]}}}}
"""
        result = spawn_fn(runtime="subagent", mode="run", task=extended_task, timeout_seconds=600, cleanup="delete")
        collection_path = f"{blackboard}/data/collection.json"
        structured_path = f"{blackboard}/data/structured_requirements.json"
        if not os.path.exists(structured_path):
            print(f"[V3][WARN] structured_requirements.json未生成，创建回退版本...")
            fallback = self._generate_fallback_structured_requirements(blackboard)
            if fallback:
                with open(structured_path, 'w', encoding='utf-8') as f:
                    json.dump(fallback, f, ensure_ascii=False, indent=2)
        return {"collection_path": collection_path if os.path.exists(collection_path) else None, "structured_requirements_path": structured_path if os.path.exists(structured_path) else None}

    def _generate_fallback_structured_requirements(self, blackboard: str) -> dict:
        """生成回退版structured_requirements.json"""
        requirements_md_path = f"{blackboard}/data/requirements.md"
        if os.path.exists(requirements_md_path):
            try:
                with open(requirements_md_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                reqs = []
                req_id = 1
                for line in content.split('\n'):
                    line = line.strip()
                    if line and len(line) > 10 and not line.startswith('#'):
                        reqs.append({"id": f"REQ-{req_id:03d}", "module": "unknown", "category": "functional", "text": line[:200]})
                        req_id += 1
                if reqs:
                    return {"source": "requirements.md (fallback)", "requirements": reqs, "modules": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6"], "stakeholders": self.stakeholders or ["平台运营方", "供给方", "需求方"], "constraints": {"technical": ["性能", "安全", "可用性"], "business": ["成本", "合规"]}}
            except Exception as e:
                print(f"[V3][WARN] 读取requirements.md失败: {e}")
        return {"source": "topic+constraints (fallback)", "requirements": [{"id": "REQ-001", "module": "general", "category": "functional", "text": self.topic}] + [{"id": f"REQ-{i+2:03d}", "module": "constraint", "category": "constraint", "text": c} for i, c in enumerate(self.constraints or [])], "modules": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6"], "stakeholders": self.stakeholders or ["平台运营方", "供给方", "需求方"], "constraints": {"technical": [c for c in (self.constraints or []) if any(k in c for k in ["性能", "延迟", "并发", "可用", "安全"])] or ["性能达标"], "business": [c for c in (self.constraints or []) if any(k in c for k in ["成本", "价格", "抽成", "计费", "提现"])] or ["商业模式可行"]}}

    def _run_planning(self, blackboard: str, spawn_fn: Callable) -> dict:
        """改动2: Planning同时读取structured_requirements.json + collection.json"""
        if not spawn_fn:
            raise RuntimeError("spawn_fn不可用，无法执行planning")
        print(f"[V3][Stage 2] planning...")
        structured_path = f"{blackboard}/data/structured_requirements.json"
        collection_path = f"{blackboard}/data/collection.json"
        sr = {}
        if os.path.exists(structured_path):
            with open(structured_path, 'r', encoding='utf-8') as f:
                sr = json.load(f)
        coll = {}
        if os.path.exists(collection_path):
            with open(collection_path, 'r', encoding='utf-8') as f:
                coll = json.load(f)
        task = f"""基于以下两份输入生成规划方案：

【结构化需求清单】(权威来源，不可遗漏任何REQ-ID)：
{json.dumps(sr, ensure_ascii=False, indent=2)}

【行业调研数据】(参考信息)：
{json.dumps(coll, ensure_ascii=False, indent=2)}

【分配要求】
1. 提取全部REQ-ID，确保无遗漏
2. 每个REQ-ID分配给某个Worker
3. 未分配的标记为GAP
4. constraints覆盖全部，stakeholders数量正确

【分配质量要求】
**步骤1：语义理解**
- 不要只做关键词匹配，要做语义理解
- 对每个REQ-ID，完整阅读其text描述，理解技术领域
- 对易混淆术语进行澄清（如："隔离"可能指硬件资源隔离或数据安全隔离，需明确）

**步骤2：预分配**
- 根据语义理解，将REQ-ID分配给专长匹配的Worker

**步骤3：自我验证（对每个分配必须回答）**
a) 这个REQ-ID描述的技术领域是什么？
b) 这个Worker的专长领域是什么？
c) 两者是否匹配？如果不匹配，原因是什么？
d) 这个Worker是否有能力产出这个REQ-ID要求的内容？
e) 是否有其他Worker的匹配度更高？
f) 如果其他专家认为这个分配错误，你如何辩护？

**步骤4：写结构化分配理由（对每个分配必须包含）**
- 技术领域判定（1句，≤20字）
- 专长匹配逻辑（1-2句，≤40字）
- 产出能力评估（1句，≤20字）
- 反例说明：为什么不分配给expert_X（列出至少1个其他Worker及其不适合的原因）

**步骤5：置信度评分**
- 对每个分配给出1-10分的置信度评分
- ≤6分的分配必须重新考虑
- 低置信度分配标记为"需复核"

**步骤6：修正**
- 如果自我验证发现不合理，修正分配
- 如果涉及跨领域REQ，指定主导Worker和辅助Worker

**输出格式**
输出包含coverage_check字段和worker_assignments字段。
每个worker_assignment必须包含allocation_rationale（分配理由）。
保存到: {blackboard}/stages/planning.json"""
        result = spawn_fn(runtime="subagent", mode="run", task=task, timeout_seconds=600, cleanup="delete")
        planning_path = f"{blackboard}/stages/planning.json"
        planning_data = {}
        if os.path.exists(planning_path):
            with open(planning_path, 'r', encoding='utf-8') as f:
                planning_data = json.load(f)
        coverage = planning_data.get("coverage_check", {})
        gaps = coverage.get("gaps", [])
        if gaps:
            print(f"[V3][WARN] Planning发现{len(gaps)}个GAP: {[g['req_id'] for g in gaps]}")
        return {"planning_path": planning_path, "planning_data": planning_data, "coverage_check": coverage, "gaps": gaps}

    def _generate_worker_tasks(self, planning: dict, blackboard: str) -> List[dict]:
        """改动3: 删除not_responsible_for，改为primary_focus + cross_domain_alert"""
        if not isinstance(planning, dict):
            raise ValueError("planning必须是字典")
        assignments = planning.get("worker_assignments", []) or self._get_default_worker_assignments()
        tasks = []
        for assignment in assignments:
            wid = assignment.get("worker_id", "expert_1")
            focus = assignment.get("focus", "技术研究")
            l2 = assignment.get("layer2_constraints", [])
            reqs = assignment.get("assigned_req_ids", [])
            pf = assignment.get("primary_focus", [focus])
            if not isinstance(pf, list):
                pf = [pf]
            scope_boundary = {
                "primary_focus": pf,
                "collaboration_context": "你的产出将被consolidator与其他Worker整合为统一方案",
                "cross_domain_alert": "⚠️ 如果你发现任何与你工作强相关但似乎未被其他Worker覆盖的需求，请在quality_gate的global_impact中显式声明",
                "assigned_req_ids": reqs
            }
            tasks.append({
                "worker_id": wid,
                "task": {
                    "focus": focus,
                    "layer2_constraints": l2,
                    "scope_boundary": scope_boundary,
                    "quality_gate_requirement": {"dimensions": ["completeness", "necessity", "alignment", "global_impact"], "scale": "green/yellow/red", "yellow_red_must_have": "blocking_issues列表", "no_0_1_score": True}
                }
            })
        print(f"[V3] 生成{len(tasks)}个Worker tasks")
        return tasks

    def _get_default_worker_assignments(self) -> List[dict]:
        """默认Worker分配"""
        return [
            {"worker_id": "expert_1", "focus": "技术架构", "primary_focus": ["高并发架构", "性能优化"], "layer2_constraints": [], "assigned_req_ids": []},
            {"worker_id": "expert_2", "focus": "隐私计算", "primary_focus": ["TEE/MPC/FL", "数据不出域"], "layer2_constraints": [], "assigned_req_ids": []},
            {"worker_id": "expert_3", "focus": "业务模型", "primary_focus": ["商业模式", "计费结算"], "layer2_constraints": [], "assigned_req_ids": []},
            {"worker_id": "expert_4", "focus": "开发者平台", "primary_focus": ["API/SDK", "控制台"], "layer2_constraints": [], "assigned_req_ids": []},
            {"worker_id": "expert_5", "focus": "资源调度", "primary_focus": ["算力抽象", "自动发现"], "layer2_constraints": [], "assigned_req_ids": []},
            {"worker_id": "expert_6", "focus": "监控运维", "primary_focus": ["可观测性", "故障自愈"], "layer2_constraints": [], "assigned_req_ids": []},
            {"worker_id": "expert_7", "focus": "合规审计", "primary_focus": ["合规框架", "审计日志"], "layer2_constraints": [], "assigned_req_ids": []},
            {"worker_id": "expert_8", "focus": "用户体验", "primary_focus": ["交互设计", "多端适配"], "layer2_constraints": [], "assigned_req_ids": []},
            {"worker_id": "expert_9", "focus": "成本优化", "primary_focus": ["TCO分析", "资源利用率"], "layer2_constraints": [], "assigned_req_ids": []},
            {"worker_id": "expert_10", "focus": "开源生态", "primary_focus": ["开源策略", "社区建设"], "layer2_constraints": [], "assigned_req_ids": []}
        ]

    def _run_workers(self, tasks: List[dict], blackboard: str, spawn_fn: Callable) -> List[dict]:
        """改动4: Harness V2重构——定性红绿灯 + quality_gate"""
        if not spawn_fn:
            raise RuntimeError("spawn_fn不可用，无法执行workers")
        print(f"[V3] 启动{len(tasks)}个Worker...")
        results = []
        for tc in tasks:
            wid = tc["worker_id"]
            task = tc["task"]
            full_task = f"""【Worker任务】{json.dumps(task, ensure_ascii=False, indent=2)}

产出要求：包含quality_gate字段，格式：
{{"quality_gate": {{"decision": "PASS/WARNING/FAIL", "dimensions": {{"completeness": {{"status": "green|yellow|red", "reasoning": "..."}}, "necessity": {{"status": "green|yellow|red", "reasoning": "...", "blocking_issues": ["..."]}}, "alignment": {{"status": "green|yellow|red", "reasoning": "..."}}, "global_impact": {{"status": "green|yellow|red", "reasoning": "...", "blocking_issues": ["..."]}}}}, "blocking_issues": ["..."], "overall_reasoning": "..."}}}}
yellow/red必须附带blocking_issues，禁止0-1分。保存到: {blackboard}/stages/worker_{wid}.json"""
            result = spawn_fn(runtime="subagent", mode="run", task=full_task, timeout_seconds=600, cleanup="delete")
            worker_path = f"{blackboard}/stages/worker_{wid}.json"
            output = {}
            if os.path.exists(worker_path):
                try:
                    with open(worker_path, 'r', encoding='utf-8') as f:
                        output = json.load(f)
                except json.JSONDecodeError:
                    pass
            qg = output.get("quality_gate", {})
            if not qg:
                output["quality_gate"] = {"decision": "WARNING", "dimensions": {"completeness": {"status": "yellow", "reasoning": "未提供自检"}, "necessity": {"status": "yellow", "reasoning": "未提供自检"}, "alignment": {"status": "yellow", "reasoning": "未提供自检"}, "global_impact": {"status": "yellow", "reasoning": "未提供自检"}}, "blocking_issues": ["未提供自检"], "overall_reasoning": "自检缺失"}
            dims = output["quality_gate"].get("dimensions", {})
            for dn, dd in dims.items():
                st = dd.get("status", "")
                if isinstance(st, (int, float)) or st in ["0", "1", "0.5", "0.8", "0.9"]:
                    dd["status"] = "yellow"
                    dd["reasoning"] = dd.get("reasoning", "") + " [强制转换:禁止0-1分]"
                if dd.get("status") in ["yellow", "red"] and not dd.get("blocking_issues"):
                    dd["blocking_issues"] = [f"{dn}标记为{dd['status']}但未提供blocking_issues"]
            results.append({"worker_id": wid, "output": output, "path": worker_path})
        return results

    def _run_consolidator(self, worker_outputs: List[dict], blackboard: str, spawn_fn: Callable) -> dict:
        """整合Worker产出"""
        if not spawn_fn:
            raise RuntimeError("spawn_fn不可用")
        inputs = [{"worker_id": w["worker_id"], "output_summary": w["output"].get("summary", "")[:500]} for w in worker_outputs]
        task = build_consolidator_task(self.session_id, self.topic, inputs)
        task += f"\n\n保存到: {blackboard}/stages/consolidator.json"
        result = spawn_fn(runtime="subagent", mode="run", task=task, timeout_seconds=600, cleanup="delete")
        path = f"{blackboard}/stages/consolidator.json"
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _run_audit(self, consolidator_output: dict, blackboard: str, spawn_fn: Callable) -> dict:
        """改动6: audit增加worker_honesty_check"""
        if not spawn_fn:
            raise RuntimeError("spawn_fn不可用")
        worker_gates = {}
        for wf in glob.glob(f"{blackboard}/stages/worker_*.json"):
            try:
                with open(wf, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                wid = os.path.basename(wf).replace("worker_", "").replace(".json", "")
                worker_gates[wid] = data.get("quality_gate", {})
            except Exception:
                pass
        task = f"""审计整合方案质量，验证Worker自检诚实性。
整合方案: {json.dumps(consolidator_output, ensure_ascii=False, indent=2)[:2000]}
Worker自检: {json.dumps(worker_gates, ensure_ascii=False, indent=2)}
要求：1)发现P0/P1/P2问题 2)验证每个Worker的quality_gate诚实性(all_green但发现问题→false_positive; yellow/red匹配→honest; yellow/red无问题→over_cautious)
保存到: {blackboard}/stages/audit.json"""
        result = spawn_fn(runtime="subagent", mode="run", task=task, timeout_seconds=600, cleanup="delete")
        path = f"{blackboard}/stages/audit.json"
        output = {}
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                output = json.load(f)
        if "worker_honesty_check" not in output:
            output["worker_honesty_check"] = [{"worker_id": w, "quality_gate_status": "unknown", "audit_verdict": "unknown", "false_positive_count": 0, "missed_issues": [], "matched_issues": []} for w in worker_gates.keys()]
        return output

    def _run_fix(self, audit_output: dict, blackboard: str, spawn_fn: Callable) -> dict:
        """修复审计问题"""
        if not spawn_fn:
            raise RuntimeError("spawn_fn不可用")
        audit_path = f"{blackboard}/stages/audit.json"
        fix_task = build_fixer_task_with_audit(self.session_id, self.topic, audit_path)
        fix_task += f"\n保存到: {blackboard}/stages/fix.json"
        spawn_fn(runtime="subagent", mode="run", task=fix_task, timeout_seconds=600, cleanup="delete")
        findings = audit_output.get("audit_findings", [])
        critical = [f for f in findings if f.get("level") == "P0"]
        expert_task = build_fixer_expert_task(self.session_id, self.topic, findings, severity="critical")
        expert_task += f"\n保存到: {blackboard}/stages/fixer_expert.json"
        spawn_fn(runtime="subagent", mode="run", task=expert_task, timeout_seconds=600, cleanup="delete")
        return {"status": "completed", "p0_count": len(critical)}

    def _run_harness_final(self, fix_output: dict, blackboard: str, spawn_fn: Callable) -> dict:
        """改动5: Harness Final基于structured_requirements.json检查"""
        if not spawn_fn:
            raise RuntimeError("spawn_fn不可用")
        sr = {}
        sp = f"{blackboard}/data/structured_requirements.json"
        if os.path.exists(sp):
            with open(sp, 'r', encoding='utf-8') as f:
                sr = json.load(f)
        all_out = []
        for wf in glob.glob(f"{blackboard}/stages/worker_*.json"):
            try:
                with open(wf, 'r', encoding='utf-8') as f:
                    all_out.append(json.load(f))
            except Exception:
                pass
        for sf in ["consolidator.json", "fix.json", "fixer_expert.json"]:
            p = f"{blackboard}/stages/{sf}"
            if os.path.exists(p):
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        all_out.append(json.load(f))
                except Exception:
                    pass
        task = f"""作为最终质量门禁，基于structured_requirements.json检查：
检查基准: {json.dumps(sr, ensure_ascii=False, indent=2)}
待检查对象: {json.dumps([{"summary": str(o)[:200]} for o in all_out], ensure_ascii=False, indent=2)}
逻辑：1)遍历每个REQ-ID 2)检查是否覆盖 3)未覆盖→MISSING 4)矛盾→MISALIGNED 5)模块间自洽性
保存到: {blackboard}/stages/harness_final.json"""
        spawn_fn(runtime="subagent", mode="run", task=task, timeout_seconds=600, cleanup="delete")
        hp = f"{blackboard}/stages/harness_final.json"
        output = {}
        if os.path.exists(hp):
            with open(hp, 'r', encoding='utf-8') as f:
                output = json.load(f)
        for key in ["global_coverage_score", "missing_items", "misaligned_items"]:
            if key not in output:
                output[key] = 0.0 if key == "global_coverage_score" else []
        return output

    def _run_summarizer(self, harness_output: dict, blackboard: str, spawn_fn: Callable) -> dict:
        """生成最终交付物"""
        if not spawn_fn:
            raise RuntimeError("spawn_fn不可用")
        req_ids = []
        sp = f"{blackboard}/data/structured_requirements.json"
        if os.path.exists(sp):
            with open(sp, 'r', encoding='utf-8') as f:
                sr = json.load(f)
                req_ids = [r.get("id") for r in sr.get("requirements", [])]
        all_outputs = {}
        for sf in ["planning.json", "consolidator.json", "fix.json", "fixer_expert.json", "harness_final.json"]:
            p = f"{blackboard}/stages/{sf}"
            if os.path.exists(p):
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        all_outputs[sf.replace(".json", "")] = json.load(f)
                except Exception:
                    pass
        task = build_summarizer_task(self.session_id, self.topic, all_outputs)
        task += f"\n\nfinal_solution.md必须覆盖REQ-ID: {req_ids}，标注【覆盖:REQ-XXX】或【缺失:REQ-XXX-原因】"
        task += f"\n保存到: {blackboard}/final_solution.md"
        spawn_fn(runtime="subagent", mode="run", task=task, timeout_seconds=600, cleanup="delete")
        fp = f"{blackboard}/final_solution.md"
        out = {"final_path": fp}
        if os.path.exists(fp):
            with open(fp, 'r', encoding='utf-8') as f:
                content = f.read()
            out["content_length"] = len(content)
            covered = [rid for rid in req_ids if rid in content]
            out["req_coverage"] = f"{len(covered)}/{len(req_ids)}"
        return out

    def run_v3(self, spawn_fn: Callable = None) -> dict:
        """
        V3完整执行入口

        .. deprecated:: 2026-05-31
            此方法已废弃。请使用 domains/solution/SKILL.md 中的标准执行方式。
        """
        warnings.warn(
            "SolutionOrchestratorV21.run_v3() 已废弃 (2026-05-31)。"
            "请使用 domains/solution/SKILL.md 中的标准执行方式。",
            DeprecationWarning,
            stacklevel=2
        )
        
        spawn = spawn_fn or self._spawn_fn
        if not spawn:
            raise RuntimeError("spawn_fn不可用")
        if not self.session_id:
            self.init()
        bb = self.base_path
        dc = self._run_data_collection(bb, spawn)
        pl = self._run_planning(bb, spawn)
        tasks = self._generate_worker_tasks(pl.get("planning_data", {}), bb)
        workers = self._run_workers(tasks, bb, spawn)
        cons = self._run_consolidator(workers, bb, spawn)
        audit = self._run_audit(cons, bb, spawn)
        fix = self._run_fix(audit, bb, spawn)
        harness = self._run_harness_final(fix, bb, spawn)
        summary = self._run_summarizer(harness, bb, spawn)
        return {
            "status": "completed",
            "session_id": self.session_id,
            "base_path": bb,
            "v3": True,
            "stages": {
                "data_collection": dc,
                "planning": pl,
                "workers": {"count": len(workers)},
                "consolidator": {"has_output": bool(cons)},
                "audit": {"findings": len(audit.get("audit_findings", [])), "honesty_checks": len(audit.get("worker_honesty_check", []))},
                "fix": fix,
                "harness_final": {"coverage_score": harness.get("global_coverage_score", 0), "missing": len(harness.get("missing_items", [])), "misaligned": len(harness.get("misaligned_items", []))},
                "summarizer": summary
            }
        }

    # ========== 静态方法 ==========

def main():
    """入口"""
    orch = SolutionOrchestratorV21(
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
    print(f"   Harness: 3维度 (35/25/40) + Layer 1/2 + Final门禁")
    return session_id, tasks


if __name__ == "__main__":
    main()
