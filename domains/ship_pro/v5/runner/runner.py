"""
Ship Pro V5 Runner - 执行引擎

职责:
1. 按固定顺序调用 Agent (Phase 1 → Phase 2)
2. 传递推理链
3. 执行 Gate 校验
4. 管理 Fix 循环

不做:
- 不决策 (所有决策由 LLM Agent 完成)
- 不生成内容 (只传递和校验)
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

# 支持直接运行本文件 (python runner.py) 和模块导入两种方式
if __name__ == "__main__" and __package__ is None:
    import os
    file_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, file_dir)
    from agent_caller import AgentCaller, MockAgentCaller
else:
    try:
        from .agent_caller import AgentCaller, MockAgentCaller
    except ImportError:
        from agent_caller import AgentCaller, MockAgentCaller

logger = logging.getLogger("ship_pro.v5.runner")


class ShipProV5Runner:
    """Ship Pro V5 端到端执行引擎"""

    def __init__(self, project_dir: Path, caller: AgentCaller | None = None):
        self.project_dir = Path(project_dir)
        self.output_dir = self.project_dir / "v5"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.caller = caller or MockAgentCaller()
        self.execution_log: List[Dict[str, Any]] = []

    # ────────────────────────────────
    # 公共接口
    # ────────────────────────────────

    def run_full_pipeline(self, input_path: Path) -> Dict[str, Any]:
        """端到端执行 Pipeline: Phase 1 → Gate → Phase 2 → Gate"""
        start_time = time.monotonic()
        logger.info("🚀 Ship Pro V5 Pipeline 启动 | input=%s", input_path)

        # Phase 1: Blueprint
        blueprint = self.run_phase1(input_path)

        # Gate 1
        gate1_passed, gate1_issues = self.gate_blueprint(blueprint)
        if not gate1_passed:
            logger.warning("🔴 Gate 1 未通过, issues=%d", len(gate1_issues))
            blueprint = self.fix_cycle(blueprint, gate1_issues, phase=1)
        else:
            logger.info("🟢 Gate 1 通过")

        # Phase 2: Delivery
        ship_package = self.run_phase2(blueprint)

        # Gate 2
        gate2_passed, gate2_issues = self.gate_ship_package(ship_package)
        if not gate2_passed:
            logger.warning("🔴 Gate 2 未通过, issues=%d", len(gate2_issues))
            ship_package = self.fix_cycle(ship_package, gate2_issues, phase=2)
        else:
            logger.info("🟢 Gate 2 通过")

        # 最终保存
        final_path = self.output_dir / "ship_package.json"
        self.save_json("ship_package", ship_package)

        elapsed = time.monotonic() - start_time
        logger.info("✅ Pipeline 完成 | 耗时=%.2fs | 输出=%s", elapsed, final_path)

        return ship_package

    # ────────────────────────────────
    # Phase 1: Blueprint
    # ────────────────────────────────

    def run_phase1(self, input_path: Path) -> Dict[str, Any]:
        """Phase 1: Parser → Explorer → Architect → 3 Critic → Consolidator"""
        logger.info("📘 Phase 1 启动: Blueprint")
        phase_start = time.monotonic()

        # P1-1 Parser
        parsed = self._call_agent("p1_parser", {"input_path": str(input_path)})
        self.save_output("p1_parser", parsed)

        # P1-2 Explorer
        findings = self._call_agent("p1_explorer", {"parsed": parsed})
        self.save_output("p1_explorer", findings)

        # P1-3 Architect (两步)
        wp_list = self._call_agent(
            "p1_architect_step1",
            {"parsed": parsed, "findings": findings},
        )
        rationale = self._call_agent(
            "p1_architect_step2",
            {"wp_list": wp_list},
        )
        blueprint_draft = {**wp_list, "rationale": rationale}
        self.save_output("p1_architect", blueprint_draft)

        # P1-4/5/6 Critics (并行)
        critics = self._call_agents_parallel(
            [
                ("p1_coverage_critic", {"blueprint": blueprint_draft}),
                ("p1_granularity_critic", {"blueprint": blueprint_draft}),
                ("p1_feasibility_critic", {"blueprint": blueprint_draft}),
            ]
        )
        self.save_output("p1_critics", critics)

        # P1-Consolidator
        consolidated = self._call_agent(
            "p1_consolidator",
            {"blueprint": blueprint_draft, "critics": critics},
        )
        self.save_output("p1_consolidator", consolidated)

        blueprint = consolidated.get("blueprint", consolidated)
        logger.info(
            "📘 Phase 1 完成 | 耗时=%.2fs", time.monotonic() - phase_start
        )
        return blueprint

    # ────────────────────────────────
    # Phase 2: Delivery
    # ────────────────────────────────

    def run_phase2(self, blueprint: Dict[str, Any]) -> Dict[str, Any]:
        """Phase 2: AC Writer → Propagator → DepGraph → 3 Judge → Consolidator"""
        logger.info("📗 Phase 2 启动: Delivery")
        phase_start = time.monotonic()

        # P2-1 AC Writer
        ac_drafts = self._call_agent("p2_ac_writer", {"blueprint": blueprint})
        self.save_output("p2_ac_writer", ac_drafts)

        # P2-2 Propagator (代码模块)
        constraints = self.run_propagator(blueprint)
        self.save_output("p2_propagator", constraints)

        # P2-3 DepGraph (代码模块)
        work_packages = ac_drafts.get("work_packages", ac_drafts)
        depgraph = self.run_depgraph(work_packages)
        self.save_output("p2_depgraph", depgraph)

        # 合并草稿
        draft_package = self.merge_draft(
            ac_drafts, constraints, depgraph, blueprint
        )

        # P2-4 Consistency Judge (代码 + LLM)
        conflicts = self.run_numeric_checker(draft_package)
        consistency_verdict = self._call_agent(
            "p2_consistency_judge", conflicts
        )

        # P2-5/6 Judges (并行)
        judges = self._call_agents_parallel(
            [
                ("p2_quality_judge", {"package": draft_package}),
                ("p2_completeness_judge", {"package": draft_package}),
            ]
        )
        judges["consistency"] = consistency_verdict
        self.save_output("p2_judges", judges)

        # P2-Consolidator
        consolidated = self._call_agent(
            "p2_consolidator",
            {"package": draft_package, "judges": judges},
        )
        self.save_output("p2_consolidator", consolidated)

        ship_package = consolidated.get("ship_package", consolidated)
        logger.info(
            "📗 Phase 2 完成 | 耗时=%.2fs", time.monotonic() - phase_start
        )
        return ship_package

    # ────────────────────────────────
    # 代码模块调用 (确定性计算)
    # ────────────────────────────────

    def run_propagator(self, blueprint: Dict[str, Any]) -> Dict[str, Any]:
        """调用约束传播代码模块"""
        try:
            from ..code.propagator import propagate_constraints

            return propagate_constraints(blueprint)
        except ImportError:
            logger.warning("propagator 模块未找到, 返回 mock 数据")
            return {"constraints": [], "source": "mock"}

    def run_depgraph(self, work_packages: List[Dict]) -> Dict[str, Any]:
        """调用依赖图构建代码模块"""
        try:
            from ..code.depgraph import build_dependency_graph

            return build_dependency_graph(work_packages)
        except ImportError:
            logger.warning("depgraph 模块未找到, 返回 mock 数据")
            return {"dependencies": [], "source": "mock"}

    def run_numeric_checker(self, package: Dict[str, Any]) -> Dict[str, Any]:
        """调用数值一致性检查代码模块"""
        try:
            from ..code.numeric_checker import (
                extract_numeric_claims,
                find_numeric_conflicts,
            )

            claims = extract_numeric_claims(package)
            conflicts = find_numeric_conflicts(claims)
            return {"claims": claims, "conflicts": conflicts}
        except ImportError:
            logger.warning("numeric_checker 模块未找到, 返回 mock 数据")
            return {"claims": [], "conflicts": [], "source": "mock"}

    # ────────────────────────────────
    # Gate 校验
    # ────────────────────────────────

    def gate_blueprint(
        self, blueprint: Dict[str, Any]
    ) -> Tuple[bool, List[Dict]]:
        """Gate 1: Blueprint 质量校验"""
        try:
            from ..contracts.gate import gate_blueprint

            return gate_blueprint(blueprint)
        except ImportError:
            logger.warning("gate 模块未找到, 执行基础校验")
            return self._default_gate_blueprint(blueprint)

    def gate_ship_package(
        self, package: Dict[str, Any]
    ) -> Tuple[bool, List[Dict]]:
        """Gate 2: Ship Package 质量校验"""
        try:
            from ..contracts.gate import gate_ship_package

            return gate_ship_package(package)
        except ImportError:
            logger.warning("gate 模块未找到, 执行基础校验")
            return self._default_gate_ship_package(package)

    def _default_gate_blueprint(
        self, blueprint: Dict[str, Any]
    ) -> Tuple[bool, List[Dict]]:
        """基础 Blueprint 校验 (fallback)"""
        issues: List[Dict] = []
        if not blueprint.get("work_packages"):
            issues.append(
                {
                    "severity": "blocker",
                    "rule": "has_work_packages",
                    "message": "blueprint 缺少 work_packages",
                }
            )
        if not blueprint.get("rationale"):
            issues.append(
                {
                    "severity": "warning",
                    "rule": "has_rationale",
                    "message": "blueprint 缺少 rationale",
                }
            )
        return len(issues) == 0, issues

    def _default_gate_ship_package(
        self, package: Dict[str, Any]
    ) -> Tuple[bool, List[Dict]]:
        """基础 Ship Package 校验 (fallback)"""
        issues: List[Dict] = []
        if not package.get("acceptance_criteria"):
            issues.append(
                {
                    "severity": "blocker",
                    "rule": "has_ac",
                    "message": "ship_package 缺少 acceptance_criteria",
                }
            )
        if not package.get("dependencies"):
            issues.append(
                {
                    "severity": "warning",
                    "rule": "has_deps",
                    "message": "ship_package 缺少 dependencies",
                }
            )
        return len(issues) == 0, issues

    # ────────────────────────────────
    # Fix 循环
    # ────────────────────────────────

    def fix_cycle(
        self,
        data: Dict[str, Any],
        issues: List[Dict],
        phase: int,
        max_rounds: int = 2,
        batch_size: int = 3,
    ) -> Dict[str, Any]:
        """分批修复 + 回归检查

        策略:
        1. 按 severity 排序 (blocker → warning → info)
        2. 分批处理, 每批最多 batch_size 个
        3. 修复后回归检查, 若 regression 更严重则回滚
        4. 最多 max_rounds 轮
        """
        logger.info(
            "🔧 Fix Cycle 启动 | phase=%d | issues=%d | max_rounds=%d",
            phase,
            len(issues),
            max_rounds,
        )

        severity_order = {"blocker": 0, "warning": 1, "info": 2}
        sorted_issues = sorted(
            issues, key=lambda x: severity_order.get(x.get("severity", "info"), 2)
        )
        batches = [
            sorted_issues[i : i + batch_size]
            for i in range(0, len(sorted_issues), batch_size)
        ]

        original_data = data
        current_data = dict(data)
        original_score = self.severity_sum(issues)

        for round_num in range(1, max_rounds + 1):
            logger.info("🔧 Fix Round %d/%d", round_num, max_rounds)

            for batch_idx, batch in enumerate(batches):
                logger.info(
                    "  └─ Batch %d/%d (%d issues)",
                    batch_idx + 1,
                    len(batches),
                    len(batch),
                )

                fixed = self._call_agent(
                    f"p{phase}_fix_agent",
                    {"data": current_data, "issues": batch},
                )

                # 回归检查
                if phase == 1:
                    _, new_issues = self.gate_blueprint(fixed)
                else:
                    _, new_issues = self.gate_ship_package(fixed)

                regressions = [i for i in new_issues if i not in issues]
                new_score = self.severity_sum(regressions)
                old_score = self.severity_sum(batch)

                if new_score > old_score:
                    logger.warning(
                        "  ⚠️ Regression 更严重 (new=%d > old=%d), 回滚",
                        new_score,
                        old_score,
                    )
                    continue

                current_data = fixed
                issues = new_issues

            # 收敛检查
            if phase == 1:
                passed, remaining = self.gate_blueprint(current_data)
            else:
                passed, remaining = self.gate_ship_package(current_data)

            if passed:
                logger.info("🟢 Fix Cycle 收敛 | 所有 issues 已解决")
                break

            # 更新批次用于下一轮
            sorted_issues = sorted(
                remaining,
                key=lambda x: severity_order.get(x.get("severity", "info"), 2),
            )
            batches = [
                sorted_issues[i : i + batch_size]
                for i in range(0, len(sorted_issues), batch_size)
            ]
            if not batches:
                break

        final_score = self.severity_sum(remaining)
        logger.info(
            "🔧 Fix Cycle 结束 | 原始 score=%d → 最终 score=%d",
            original_score,
            final_score,
        )
        return current_data

    @staticmethod
    def severity_sum(issues: List[Dict]) -> int:
        """计算 issues 严重程度总分"""
        weights = {"blocker": 10, "warning": 3, "info": 1}
        return sum(
            weights.get(i.get("severity", "info"), 1) for i in issues
        )

    # ────────────────────────────────
    # 合并与辅助
    # ────────────────────────────────

    def merge_draft(
        self,
        ac_drafts: Dict[str, Any],
        constraints: Dict[str, Any],
        depgraph: Dict[str, Any],
        blueprint: Dict[str, Any],
    ) -> Dict[str, Any]:
        """合并 Phase 2 各模块输出为 draft_package"""
        return {
            "acceptance_criteria": ac_drafts.get("acceptance_criteria", []),
            "constraints": constraints,
            "dependencies": depgraph,
            "blueprint_ref": blueprint.get("id", "unknown"),
            "work_packages": ac_drafts.get("work_packages", []),
        }

    # ────────────────────────────────
    # Agent 调用 (统一封装)
    # ────────────────────────────────

    def _call_agent(
        self, agent_name: str, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """同步调用单个 Agent"""
        logger.debug("🤖 调用 Agent: %s", agent_name)
        start = time.monotonic()
        try:
            result = self.caller.call_agent(agent_name, input_data)
            elapsed = time.monotonic() - start
            self.execution_log.append(
                {
                    "agent": agent_name,
                    "elapsed": elapsed,
                    "status": "ok",
                    "timestamp": time.time(),
                }
            )
            logger.debug("  ✅ %s 完成 | %.2fs", agent_name, elapsed)
            return result
        except Exception as exc:
            elapsed = time.monotonic() - start
            self.execution_log.append(
                {
                    "agent": agent_name,
                    "elapsed": elapsed,
                    "status": "error",
                    "error": str(exc),
                    "timestamp": time.time(),
                }
            )
            logger.error("  ❌ %s 失败 | %.2fs | %s", agent_name, elapsed, exc)
            raise

    def _call_agents_parallel(
        self, tasks: List[Tuple[str, Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """并行调用多个 Agent, 返回 {agent_name: result}"""
        logger.info("🤖 并行调用 %d Agents", len(tasks))
        start = time.monotonic()

        return asyncio.run(self._call_agents_parallel_async(tasks, start))

    async def _call_agents_parallel_async(
        self, tasks: List[Tuple[str, Dict[str, Any]]], start: float
    ) -> Dict[str, Any]:
        """async 并行调用实现"""

        async def _run_one(name: str, data: Dict[str, Any]) -> Tuple[str, Any]:
            loop = asyncio.get_running_loop()
            # 在线程池中运行同步调用
            result = await loop.run_in_executor(
                None, self._call_agent, name, data
            )
            return name, result

        results = await asyncio.gather(
            *(_run_one(name, data) for name, data in tasks),
            return_exceptions=True,
        )

        output: Dict[str, Any] = {}
        for (name, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                logger.error("  ❌ %s 并行调用失败: %s", name, result)
                raise result
            output[name] = result

        elapsed = time.monotonic() - start
        logger.info("  ✅ 并行完成 | %.2fs", elapsed)
        return output

    # ────────────────────────────────
    # 输出管理
    # ────────────────────────────────

    def save_output(self, agent_name: str, data: Dict[str, Any]) -> None:
        """保存 Agent 输出到 JSON (保留原始结构)"""
        output_path = self.output_dir / f"{agent_name}.json"
        self.save_json(agent_name, data, output_path)

    def save_json(
        self, name: str, data: Dict[str, Any], path: Path | None = None
    ) -> None:
        """保存 JSON 文件"""
        if path is None:
            path = self.output_dir / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        logger.debug("💾 保存: %s", path)

    def save_execution_log(self) -> Path:
        """保存执行日志"""
        log_path = self.output_dir / "execution_log.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.execution_log, f, indent=2, ensure_ascii=False)
        return log_path

    # ────────────────────────────────
    # 状态与报告
    # ────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """获取当前执行状态"""
        return {
            "project_dir": str(self.project_dir),
            "output_dir": str(self.output_dir),
            "execution_log": self.execution_log,
            "output_files": [
                str(p.name) for p in self.output_dir.glob("*.json")
            ],
        }


# ────────────────────────────────
# 内建测试
# ────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # 创建临时测试项目
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "test_project"
        project_dir.mkdir()

        # 创建测试输入
        input_path = project_dir / "input.json"
        input_path.write_text(
            json.dumps(
                {"task": "设计一个电商订单系统", "constraints": []},
                ensure_ascii=False,
            )
        )

        # 运行完整 Pipeline
        runner = ShipProV5Runner(project_dir)
        try:
            result = runner.run_full_pipeline(input_path)
            print("\n" + "=" * 50)
            print("🎉 测试通过!")
            print(f"输出文件: {runner.output_dir}")
            print(f"文件列表: {runner.get_status()['output_files']}")
            print(f"ship_package keys: {list(result.keys())}")
        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)
