"""
Summary Orchestrator (Module 3) — 收敛模块

Version: 2.0.0
Date: 2026-07-01

设计来源:
- docs/design/summary_module_v3_architecture.md
- docs/design/role_specifications_v3.md §6

5+1 Phase 架构:
  Phase 1: Base Synthesis（运动员）→ base_solution
  Phase 2: Meta Summary Planner（裁判+导演）→ summary_plan
  Phase 3: Parallel Analysis ×N（含必含 Review Layer B）→ analysis_[name]
  Phase 4: Fix Judge → Fix Agent → Harness Check → fix_plan, refined_solution, verification_result
  Phase 5a: Document Generator → solution_document
  Phase 5b: JSON Extractor → final_solution

核心理念:
- 收敛而非发散（从大量知识收拢成最优方案）
- 先建后审（Phase 1 先产出，Phase 2 才规划审查）
- 运动员 ≠ 裁判（Base Synthesizer ≠ Meta Summary Planner）
- 输出分离（文档和 JSON 分两个 Agent）
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from .module_orchestrator_base import ModuleOrchestrator
from .contracts.stage_contract import STAGE_CONTRACTS, validate_checkpoint

logger = logging.getLogger(__name__)


class SummaryOrchestrator(ModuleOrchestrator):
    _stage_name = "summary"
    """
    Summary 模块编排器 — 5+1 Phase 收敛流程
    
    职责：从 Planning 约束 + Research 知识 → 最优方案（final_solution + solution_document）
    """

    PER_ANALYZER_TIMEOUT = 600
    PHASE_TIMEOUT = 900

    def __init__(
        self,
        session_id: str,
        spawn_fn: Optional[Callable] = None,
        base_dir: Optional[str] = None,
    ):
        super().__init__("summary", session_id, spawn_fn, base_dir=base_dir)
        
        # Load prompts
        self._prompts = {}
        for name in [
            "summary_base_synthesizer", "summary_meta_planner",
            "summary_analyzer_base", "summary_review_layer_b",
            "summary_harness_check", "summary_refiner",
            "summary_summarizer", "summary_json_extractor",
        ]:
            self._prompts[name] = self._load_prompt(f"{name}.md")
        
        logger.info("SummaryOrchestrator initialized (5+1 Phase)")

    def _load_prompt(self, filename: str) -> str:
        prompt_path = Path(__file__).parent / "prompts" / filename
        if prompt_path.exists():
            return self._resolve_prompt_vars(prompt_path.read_text())
        logger.debug(f"Prompt not found: {filename}, using empty")
        return ""

    def stage_sequence(self) -> list[dict]:
        return [
            {"name": "base_synthesis", "executor": "spawn"},
            {"name": "meta_summary_planner", "executor": "spawn"},
            {"name": "parallel_review", "executor": "spawn_parallel"},
            {"name": "refiner", "executor": "spawn"},
            {"name": "summarizer", "executor": "spawn"},
            {"name": "json_extractor", "executor": "spawn"},
        ]

    # ========================================================================
    # Main entry point
    # ========================================================================

    def run(
        self,
        frozen_spec: Optional[dict] = None,
        planning_output: Optional[dict] = None,
        research_output: Optional[dict] = None,
        spawn_fn: Optional[Callable] = None,
        living_spec: Optional[dict] = None,
    ) -> dict:
        """
        Summary 模块主入口
        
        Args:
            frozen_spec: Frozen spec (legacy)
            planning_output: planning_convergence.json content
            research_output: research_convergence.json / research_digest content
            spawn_fn: Optional spawn function override
            living_spec: Living Spec dict
        
        Returns:
            final_solution dict
        """
        if spawn_fn is not None:
            self.spawn_fn = spawn_fn
        
        # Store inputs
        self.frozen_spec = frozen_spec or {}
        self.planning_output = planning_output or {}
        self.research_output = research_output or {}
        self.living_spec = living_spec
        
        # Write inputs to blackboard for workers to read
        if frozen_spec:
            self.blackboard.write("frozen_spec.json", frozen_spec)
        if planning_output:
            self.blackboard.write("planning_convergence.json", planning_output)
        if living_spec:
            try:
                self.blackboard.write("data/living_spec.json", living_spec)
            except Exception:
                pass
        
        # Load from blackboard if not provided
        if not self.planning_output:
            self.planning_output = self.blackboard.read_json("planning_convergence.json") or {}
        if not self.research_output:
            # Try research_digest first, then research_convergence
            self.research_output = (
                self.blackboard.read_json("stages/research_digest.json")
                or self.blackboard.read_json("research_convergence.json")
                or {}
            )
        if not self.frozen_spec:
            self.frozen_spec = self.blackboard.read_json("frozen_spec.json") or {}
        if not self.living_spec:
            try:
                self.living_spec = self.blackboard.read_json("data/living_spec.json")
            except Exception:
                self.living_spec = None
        
        logger.info("Starting Summary module (5+1 Phase)")
        
        # Checkpoint
        checkpoint = self._load_checkpoint("stages/final_solution.json", required_keys=["schema_version"], stage_name="final_solution")
        if checkpoint:
            logger.info("Summary module already completed, loading from checkpoint")
            return checkpoint
        
        # ================================================================
        # Phase 1: Base Synthesis（运动员）
        # ================================================================
        logger.info("Phase 1: Base Synthesis")
        base_solution = self._run_base_synthesis()
        self._save_checkpoint("stages/base_solution.json", base_solution)
        
        # ================================================================
        # Phase 2: Meta Summary Planner（裁判 + 导演）
        # ================================================================
        logger.info("Phase 2: Meta Summary Planner")
        summary_plan = self._run_meta_summary_planner(base_solution)
        self._save_checkpoint("stages/summary_plan.json", summary_plan)
        
        # ================================================================
        # Phase 3: Parallel Review（多角度并行审查，含 Layer B + Harness）
        # ================================================================
        logger.info("Phase 3: Parallel Review")
        review_results = self._run_parallel_review(base_solution, summary_plan)
        
        # ================================================================
        # Phase 4: Refiner（判断 + 修复一步到位）
        # ================================================================
        logger.info("Phase 4: Refiner")
        refined_solution = self._run_refiner(base_solution, review_results)
        self._save_checkpoint("stages/refined_solution.json", refined_solution)
        
        # ================================================================
        # Phase 5a: Summarizer（总结成最终文档）
        # ================================================================
        logger.info("Phase 5a: Summarizer")
        solution_document = self._run_summarizer(
            refined_solution, review_results, summary_plan
        )
        self._save_checkpoint("stages/solution_document.json", solution_document)
        
        # ================================================================
        # Phase 5b: JSON Extractor
        # ================================================================
        logger.info("Phase 5b: JSON Extractor")
        verification_result = review_results.get("verification") if isinstance(review_results, dict) else None
        final_solution = self._run_json_extractor(solution_document, verification_result)
        self._save_checkpoint("stages/final_solution.json", final_solution)
        
        # Mark completed
        self.state["completed"] = True
        self._save_state()
        
        logger.info("Summary module completed")
        return final_solution

    # ========================================================================
    # Phase 1: Base Synthesis
    # ========================================================================

    def _run_base_synthesis(self) -> dict:
        """Phase 1: 运动员 — 吸收所有上游知识，产出完整基础方案"""
        checkpoint = self._load_checkpoint("stages/base_solution.json", required_keys=["content"], stage_name="base_solution")
        if checkpoint:
            return checkpoint
        
        # Build context for Base Synthesizer
        research_digest = self.research_output
        planning = self.planning_output
        
        # Read expert reports for full context
        expert_reports = self._read_expert_reports()
        
        task = self._build_phase_task(
            role="Base Synthesizer",
            role_desc="运动员 — 吸收所有上游知识，产出完整基础方案",
            prompt_key="summary_base_synthesizer",
            context={
                "planning_convergence": planning,
                "research_digest": research_digest,
                "expert_reports_summary": expert_reports,
                "living_spec": self.living_spec,
                "frozen_spec": self.frozen_spec,
            },
            output_stage="base_solution",
            instructions=(
                "## 你的职责\n"
                "1. 完整吸收 Research Digest 中的所有 Finding\n"
                "2. 在 Planning 约束框架内综合方案\n"
                "3. 产出一份可直接审视的完整基础方案\n\n"
                "## 关键约束\n"
                "- 必须覆盖 research_digest 中的所有重要 finding\n"
                "- 必须遵守 planning_convergence 中的 MUST 约束\n"
                "- 不做审查，不做对抗——只管产出最好的基础方案\n"
            ),
        )
        
        result = self._adapted_spawn(
            task=task,
            output_path="stages/base_solution.json",
            timeout=self.PHASE_TIMEOUT,
        )
        
        return result if isinstance(result, dict) else {"content": str(result or "")}

    # ========================================================================
    # Phase 2: Meta Summary Planner
    # ========================================================================

    def _run_meta_summary_planner(self, base_solution: dict) -> dict:
        """Phase 2: 裁判 + 导演 — 审视基础方案，动态规划 Phase 3-5 策略"""
        checkpoint = self._load_checkpoint("stages/summary_plan.json", required_keys=["content"], stage_name="summary_plan")
        if checkpoint:
            return checkpoint
        
        task = self._build_phase_task(
            role="Meta Summary Planner",
            role_desc="裁判 + 导演 — 审视基础方案，动态规划 Phase 3-5 策略",
            prompt_key="summary_meta_planner",
            context={
                "base_solution": base_solution,
                "planning_convergence": self.planning_output,
            },
            output_stage="summary_plan",
            instructions=(
                "## 你的职责\n"
                "1. 分析基础方案的强弱项\n"
                "2. 决定 Phase 3 需要哪些 Analyzer（不固定，动态决定）\n"
                "3. 为每个 Analyzer 定义审查焦点和具体问题\n"
                "4. 为 Phase 4 定义修复优先级和验证标准\n"
                "5. 为 Phase 5 定义最终收敛的文档结构\n\n"
                "## 🔴 Analyzer 面板必须使用固定格式\n"
                "```\n"
                "## Analyzer: [角色名]\n"
                "- focus: [审查焦点，一句话]\n"
                "- questions:\n"
                "  1. [具体问题 1]\n"
                "  2. [具体问题 2]\n"
                "- target_sections: [section_1, section_2]\n"
                "```\n\n"
                "## 必须包含的 Analyzer\n"
                "无论你怎么规划，必须包含一个 **review_layer_b** Analyzer（5 维度对抗性检查）\n\n"
                "## 关键约束\n"
                "- 不能修改 base_solution（你是裁判，不是运动员）\n"
                "- 分析面板必须针对基础方案的实际弱点\n"
            ),
        )
        
        result = self._adapted_spawn(
            task=task,
            output_path="stages/summary_plan.json",
            timeout=self.PHASE_TIMEOUT,
        )
        
        return result if isinstance(result, dict) else {"content": str(result or "")}

    # ========================================================================
    # Phase 3: Parallel Analysis
    # ========================================================================

    def _run_parallel_review(self, base_solution: dict, summary_plan: dict) -> list[dict]:
        """Phase 3: 多角度并行审查 — 从 summary_plan 提取 Reviewer 面板
        
        必含两个 Reviewer:
        - review_layer_b: 5 维度对抗性检查
        - harness_check: 需求覆盖 + 约束一致 + 信息守恒
        """
        # Extract reviewers from summary_plan
        analyzers = self._extract_analyzers(summary_plan)
        
        # 必含: review_layer_b
        has_layer_b = any(a.get("name", "").lower().find("review_layer_b") >= 0 for a in analyzers)
        if not has_layer_b:
            analyzers.append({
                "name": "review_layer_b",
                "focus": "5 维度对抗性质量检查（需求覆盖率、约束一致性、来源追溯、逻辑一致性、可操作性）",
                "questions": [
                    "P0 REQ 是否 100% 覆盖？",
                    "unified_constraints 是否完整保留？",
                    "关键决策是否有 source_experts 追溯？",
                    "方案中是否存在矛盾？",
                    "验证清单是否可执行？",
                ],
                "target_sections": ["all"],
            })
        
        # 必含: harness_check（需求覆盖 + 约束一致 + 信息守恒）
        has_harness = any(a.get("name", "").lower().find("harness") >= 0 for a in analyzers)
        if not has_harness:
            analyzers.append({
                "name": "harness_check",
                "focus": "Harness 业务验证（P0 覆盖率、架构一致性、Guardrails 遵守、信息守恒）",
                "questions": [
                    "frozen_spec/living_spec 中 P0 需求是否在方案中有对应实现？",
                    "方案是否与 unified_constraints 体系一致？",
                    "是否违反 never_do 约束？",
                    "Research 的关键 finding 是否在方案中体现？",
                ],
                "target_sections": ["all"],
            })
        
        logger.info(f"Phase 3: {len(analyzers)} reviewers: {[a['name'] for a in analyzers]}")
        
        # Parallel execution
        results = []
        if self.spawn_fn and len(analyzers) > 1:
            results = self._execute_analyzers_parallel(analyzers, base_solution, summary_plan)
        else:
            for analyzer in analyzers:
                result = self._run_single_analyzer(analyzer, base_solution, summary_plan)
                results.append(result)
        
        return results

    def _extract_analyzers(self, summary_plan: dict) -> list[dict]:
        """从 summary_plan 中提取 Analyzer 面板（固定格式解析）"""
        content = ""
        if isinstance(summary_plan, dict):
            content = summary_plan.get("content", "") or json.dumps(summary_plan, ensure_ascii=False)
        elif isinstance(summary_plan, str):
            content = summary_plan
        
        analyzers = []
        # Parse "## Analyzer: [name]" blocks
        pattern = r"## Analyzer:\s*(.+?)(?=\n## Analyzer:|\n## |$)"
        matches = re.findall(pattern, content, re.DOTALL)
        
        for match in matches:
            lines = match.strip().split("\n")
            name = lines[0].strip()
            
            focus = ""
            questions = []
            target_sections = []
            
            for line in lines[1:]:
                line = line.strip()
                if line.startswith("- focus:"):
                    focus = line.replace("- focus:", "").strip()
                elif line.startswith("- target_sections:"):
                    sections_str = line.replace("- target_sections:", "").strip()
                    target_sections = [s.strip().strip("[]") for s in sections_str.split(",")]
                elif re.match(r"\d+\.", line):
                    questions.append(re.sub(r"\d+\.\s*", "", line))
            
            analyzers.append({
                "name": name,
                "focus": focus,
                "questions": questions,
                "target_sections": target_sections,
            })
        
        if not analyzers:
            logger.warning("No analyzers found in summary_plan, using default set")
            analyzers = [
                {"name": "review_layer_b", "focus": "5 维度对抗性检查", "questions": [], "target_sections": ["all"]},
                {"name": "architecture_reviewer", "focus": "架构一致性审查", "questions": [], "target_sections": ["architecture"]},
            ]
        
        return analyzers

    def _execute_analyzers_parallel(
        self, analyzers: list[dict], base_solution: dict, summary_plan: dict
    ) -> list[dict]:
        """并行执行多个 Analyzer"""
        results = []
        min_viable = max(1, len(analyzers) // 2)
        
        with ThreadPoolExecutor(max_workers=len(analyzers)) as executor:
            futures = {}
            for analyzer in analyzers:
                future = executor.submit(
                    self._run_single_analyzer, analyzer, base_solution, summary_plan
                )
                futures[future] = analyzer
            
            for future in as_completed(futures, timeout=self.PHASE_TIMEOUT):
                analyzer = futures[future]
                try:
                    result = future.result(timeout=self.PER_ANALYZER_TIMEOUT)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Analyzer {analyzer['name']} failed: {e}")
        
        if len(results) < min_viable:
            logger.warning(f"Only {len(results)}/{len(analyzers)} analyzers succeeded")
        
        return results

    def _run_single_analyzer(
        self, analyzer: dict, base_solution: dict, summary_plan: dict
    ) -> dict:
        """执行单个 Analyzer"""
        name = analyzer["name"]
        output_path = f"stages/analysis_{name}.json"
        
        # Checkpoint
        checkpoint = self._load_checkpoint(output_path, required_keys=["content"])
        if checkpoint:
            return checkpoint
        
        is_layer_b = "review_layer_b" in name.lower()
        prompt_key = "summary_review_layer_b" if is_layer_b else "summary_analyzer_base"
        
        task = self._build_phase_task(
            role=f"Analyzer: {name}",
            role_desc=f"从 {analyzer.get('focus', name)} 角度审查基础方案",
            prompt_key=prompt_key,
            context={
                "base_solution": base_solution,
                "planning_convergence": self.planning_output,
                "analyzer_config": analyzer,
            },
            output_stage=f"analysis_{name}",
            instructions=(
                f"## 你的审查焦点\n{analyzer.get('focus', '全面审查')}\n\n"
                f"## 审查问题\n"
                + "\n".join(f"{i+1}. {q}" for i, q in enumerate(analyzer.get("questions", [])))
                + f"\n\n## 重点关注 section\n{analyzer.get('target_sections', ['all'])}\n\n"
                "## 输出格式\n"
                "### 发现\n"
                "每个问题：标题 + 详细分析 + 严重程度(高/中/低) + 具体修复建议\n"
                "### 整体评价\n"
                "维度得分(X/10) + 最关键改进点\n"
            ),
        )
        
        result = self._adapted_spawn(task=task, output_path=output_path, timeout=self.PER_ANALYZER_TIMEOUT)
        
        output = result if isinstance(result, dict) else {"content": str(result or ""), "analyzer": name}
        output["analyzer"] = name
        self._save_checkpoint(output_path, output)
        return output

    # ========================================================================
    # Phase 4: Fix Judge → Fix Agent → Harness Check
    # ========================================================================

    def _run_refiner(self, base_solution: dict, review_results: list[dict]) -> dict:
        """Phase 4: Refiner — 判断 + 修复一步到位
        
        读所有 Review 报告，判断采纳/拒绝/折中，直接在 base_solution 上执行修复。
        合并原 Fix Judge + Fix Agent + Harness Check 的职责。
        """
        checkpoint = self._load_checkpoint("stages/refined_solution.json", required_keys=["content"], stage_name="refined_solution")
        if checkpoint:
            return checkpoint
        
        task = self._build_phase_task(
            role="Refiner",
            role_desc="判断 + 修复一步到位 — 读所有审查报告，直接产出修复后的方案",
            prompt_key="summary_refiner",
            context={
                "base_solution": base_solution,
                "review_results": review_results,
                "planning_convergence": self.planning_output,
                "frozen_spec": self.frozen_spec,
                "living_spec": self.living_spec,
            },
            output_stage="refined_solution",
            instructions=(
                "## 你的职责\n"
                "1. 读所有 Reviewer 报告（含 review_layer_b + harness_check + 其他）\n"
                "2. 判断哪些建议采纳、哪些拒绝、哪些折中（全局最优 > 局部最优）\n"
                "3. 直接在 base_solution 上执行修复，产出 refined_solution\n\n"
                "## 输入\n"
                "- base_solution: 基础方案\n"
                "- review_results: 所有 Reviewer 的审查报告\n"
                "- planning_convergence: 约束体系（MUST 约束必须保留）\n\n"
                "## 输出\n"
                "完整的 refined_solution（修复后的方案，保持 base_solution 的完整性）\n\n"
                "## 关键约束\n"
                "- 全局最优 > 局部最优（Reviewer 建议可能互相矛盾）\n"
                "- MUST 约束不能删减\n"
                "- 只修该修的，保持未涉及部分不变\n"
            ),
        )
        
        result = self._adapted_spawn(
            task=task,
            output_path="stages/refined_solution.json",
            timeout=self.PHASE_TIMEOUT,
        )
        return result if isinstance(result, dict) else {"content": str(result or "")}

    # ========================================================================
    # Phase 5: Document Generator + JSON Extractor
    # ========================================================================

    def _run_summarizer(
        self, refined_solution: dict, review_results: list[dict], summary_plan: dict
    ) -> dict:
        """Phase 5a: Summarizer — 把所有上游工作总结成最终方案文档"""
        checkpoint = self._load_checkpoint("stages/solution_document.json", required_keys=["content"], stage_name="solution_document")
        if checkpoint:
            return checkpoint
        
        task = self._build_phase_task(
            role="Summarizer",
            role_desc="把所有上游工作总结成最终方案文档",
            prompt_key="summary_summarizer",
            context={
                "refined_solution": refined_solution,
                "review_results": review_results,
                "summary_plan": summary_plan,
            },
            output_stage="solution_document",
            instructions=(
                "## 你的职责\n"
                "把 refined_solution 总结成完整的方案文档，包含：\n"
                "- 方案概述\n- 架构设计\n- 技术选型（含对比）\n"
                "- 实施计划\n- 风险缓解\n- 约束覆盖追溯\n\n"
                "## 关键约束\n"
                "- 文档是大头，给足细节\n"
                "- 从 refined_solution 展开，不重新发明\n"
            ),
        )
        
        result = self._adapted_spawn(task=task, output_path="stages/solution_document.json", timeout=self.PHASE_TIMEOUT)
        return result if isinstance(result, dict) else {"content": str(result or "")}

    def _run_json_extractor(self, solution_document: dict, verification_result: dict) -> dict:
        """Phase 5b: 结构化提取 — 从方案文档中提取元数据"""
        checkpoint = self._load_checkpoint("stages/final_solution.json", required_keys=["schema_version"], stage_name="final_solution")
        if checkpoint:
            return checkpoint
        
        task = self._build_phase_task(
            role="JSON Extractor",
            role_desc="从方案文档中提取结构化元数据",
            prompt_key="summary_json_extractor",
            context={
                "solution_document": solution_document,
                "verification_result": verification_result,
            },
            output_stage="final_solution",
            instructions=(
                "## 你的职责\n"
                "从已写完的方案文档中提取结构化元数据\n\n"
                "## 输出格式 (JSON)\n"
                "```json\n"
                "{\n"
                '  "schema_version": "2.0.0",\n'
                '  "constraint_coverage": {"total": N, "covered": N, "ratio": 0.X, "uncovered": [...]},\n'
                '  "key_decisions": [...],\n'
                '  "implementation_phases": [...],\n'
                '  "risk_summary": [...],\n'
                '  "verification_status": {"passed": N, "failed": N},\n'
                '  "document_ref": "solution_document"\n'
                "}\n```\n\n"
                "## 关键约束\n"
                "- JSON 只放元数据，不放完整方案内容\n"
                "- 从已写完的文档中提取，不重新生成\n"
            ),
        )
        
        result = self._adapted_spawn(task=task, output_path="stages/final_solution.json", timeout=self.PHASE_TIMEOUT)
        return result if isinstance(result, dict) else {
            "schema_version": "2.0.0",
            "status": "EXTRACTION_FAILED",
            "document_ref": "solution_document",
        }

    # ========================================================================
    # Helpers
    # ========================================================================

    def _build_phase_task(
        self, role: str, role_desc: str, prompt_key: str,
        context: dict, output_stage: str, instructions: str,
    ) -> str:
        """构建 Worker task prompt（含 P0 约束 + 追溯矩阵注入）"""
        prompt_content = self._prompts.get(prompt_key, "")
        
        # Serialize context (cap large values)
        context_str = ""
        for key, value in context.items():
            if value is None:
                continue
            val_str = json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (dict, list)) else str(value)
            if len(val_str) > 15000:
                val_str = val_str[:15000] + f"\n... (truncated, {len(val_str)} chars total, read from blackboard for full content)"
            context_str += f"\n### {key}\n```json\n{val_str}\n```\n"
        
        # === Quality Improvement: P0 约束 + 追溯矩阵注入 ===
        p0_block = self._load_p0_constraints_prompt_block()
        soft_constraints = self._get_system_soft_constraints()
        trace_block = self._load_requirement_traceability_prompt_block()
        
        task = f"""# {role}

> {role_desc}

## Session ID
`{self.session_id}`

## 执行环境
cd ~/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 -c "..."

## P0 约束（不可违反）
{p0_block}

## 需求追溯矩阵
{trace_block}

## Prompt
{prompt_content[:5000] if prompt_content else "(使用以下指令)"}

## 上游上下文
{context_str}

## 指令
{instructions}

## 系统级软约束
{soft_constraints}

## 输出
将结果写入 Blackboard stage: `{output_stage}`
使用 blackboard.write("{output_stage}", result)
"""
        return task

    def _read_expert_reports(self) -> str:
        """读取所有 Expert 报告摘要"""
        reports = []
        try:
            # Try research_digest first
            digest = self.blackboard.read_json("stages/research_digest.json")
            if digest and isinstance(digest, dict):
                expert_summaries = digest.get("expert_summaries", [])
                if expert_summaries:
                    return json.dumps(expert_summaries, ensure_ascii=False)[:10000]
        except Exception:
            pass
        
        # Fallback: read individual expert reports
        try:
            stages_dir = self.blackboard.session_dir / "stages" / "research_experts"
            if stages_dir.exists():
                for f in sorted(stages_dir.glob("*.json")):
                    try:
                        data = json.loads(f.read_text())
                        name = data.get("expert_name", f.stem)
                        report = data.get("report", "")
                        reports.append(f"### {name}\n{report[:3000]}...")
                    except Exception:
                        pass
        except Exception:
            pass
        
        return "\n".join(reports)[:10000] if reports else "(No expert reports found)"

    # _load_checkpoint 已提升到 ModuleOrchestrator 基类（含 StageContract 契约笼子验证）

    def _save_checkpoint(self, path: str, result: dict):
        """Save checkpoint. Raises on failure."""
        self.blackboard.write(path, result)
