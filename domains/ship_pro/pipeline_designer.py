"""
Ship Pro - PipelineDesigner

职责：
1. 分析 Solution Pro 输出，设计 Worker 拆分方案
2. 为每个 Worker 裁剪上下文（context.json）
3. 确定依赖关系和执行顺序

契约笼子：
- 输入必须包含 requirements + key_decisions（raise ValueError 否则）
- 输出必须通过 PipelinePlan Pydantic 验证
- 裁剪后 context.json 大小 ≤ 3KB（raise ValueError 否则）
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


# ============================================================================
# 契约笼子：Pydantic Schemas
# ============================================================================

class WorkerSpec(BaseModel):
    """
    PipelineDesigner 输出的单个 Worker 规格（统一 Schema）
    
    统一了原 PipelinePlan.WorkerSpec 和 contracts.PlannerOutput.WorkerSpec 两套协议。
    字段说明：
    - module_purpose: 模块目的（≥20 字），替代原 task_description
    - covered_req_ids: 覆盖的 REQ-ID（semantic_anchors 追踪用）
    - must_constraints: 从 Solution Pro 继承的 MUST 约束（gates 验证用）
    - wp_id_prefix: WP ID 前缀（如 CORE-、LOOP-）
    """
    role: str = Field(..., min_length=3, description="Worker 角色名称")
    module_purpose: str = Field(..., min_length=20, description="模块目的（≥20 字）")
    covered_req_ids: List[str] = Field(..., min_length=1, description="覆盖的 REQ-ID 列表")
    depends_on: List[str] = Field(default_factory=list, description="依赖的其他 Worker role")
    interface_provides: List[str] = Field(default_factory=list, description="对外接口签名")
    interface_requires: List[str] = Field(default_factory=list, description="需要的接口签名")
    relevant_decisions: List[str] = Field(default_factory=list, description="相关架构决策（≤5）")
    relevant_risks: List[str] = Field(default_factory=list, description="相关风险（≤3）")
    estimated_wps: int = Field(..., ge=3, le=12, description="预估 WP 数量 3-12")
    estimated_effort_hours: int = Field(..., ge=10, le=200, description="预估工时 10-200h")
    # --- 从 PlannerOutput.WorkerSpec 合并的字段（gates/orchestrator 需要）---
    must_constraints: List[str] = Field(
        default_factory=list,
        description="从 Solution Pro 继承的 MUST 约束描述（语义描述，非 ID）"
    )
    wp_id_prefix: str = Field(
        default="WP",
        description="WP ID 前缀（如 CORE-、LOOP-），所有该 Worker 生成的 WP ID 必须以此为前缀"
    )
    needs_web_search: bool = Field(
        default=False,
        description="是否需要 web search 权限"
    )
    web_search_scope: Optional[str] = Field(
        default=None,
        description="搜索范围描述（如有权限）"
    )
    solution_pro_refs: List[str] = Field(
        default_factory=list,
        description="引用的 Solution Pro 具体字段路径"
    )

    @field_validator("relevant_decisions")
    @classmethod
    def max_decisions(cls, v: List[str]) -> List[str]:
        if len(v) > 5:
            raise ValueError(f"relevant_decisions 最多 5 个，实际 {len(v)}")
        return v

    @field_validator("relevant_risks")
    @classmethod
    def max_risks(cls, v: List[str]) -> List[str]:
        if len(v) > 3:
            raise ValueError(f"relevant_risks 最多 3 个，实际 {len(v)}")
        return v


class PipelinePlan(BaseModel):
    """PipelineDesigner 的完整输出"""
    domain_analysis: Optional[Dict[str, Any]] = Field(default=None, validate_default=True, description="领域分析（domain/end_users/deliverable_form/split_dimension/key_constraints）")
    workers: List[WorkerSpec] = Field(..., min_length=2, max_length=8, description="Worker 列表 2-8 个")
    execution_order: List[List[str]] = Field(..., min_length=1, description="分层执行顺序")
    rationale: str = Field(..., min_length=50, description="拆分理由（≥50 字）")

    @field_validator("execution_order")
    @classmethod
    def all_workers_in_order(cls, v: List[List[str]], info) -> List[List[str]]:
        """所有 Worker role 必须出现在 execution_order 中"""
        workers = info.data.get("workers", [])
        if workers:
            roles = {w.role for w in workers}
            ordered = set()
            for layer in v:
                ordered.update(layer)
            missing = roles - ordered
            if missing:
                raise ValueError(f"execution_order 缺少 Worker: {missing}")
        return v

    @field_validator("workers")
    @classmethod
    def wp_id_prefix_unique(cls, v):
        prefixes = [w.wp_id_prefix for w in v]
        if len(prefixes) != len(set(prefixes)):
            from collections import Counter
            dupes = [p for p, c in Counter(prefixes).items() if c > 1]
            raise ValueError(f"wp_id_prefix 必须唯一，重复: {dupes}")
        return v

    @field_validator("domain_analysis")
    @classmethod
    def domain_analysis_should_exist(cls, v):
        if v is None:
            import warnings
            warnings.warn(
                "domain_analysis 为空 — Planner 未识别领域。"
                "泛化能力降级：Worker 将无法推断产出模式。",
                UserWarning
            )
        return v


class WorkerContext(BaseModel):
    """裁剪后的 Worker 上下文（context.json）"""
    module_overview: str = Field(..., min_length=20, description="模块概述")
    module_reqs: List[Dict[str, Any]] = Field(..., min_length=1, description="本模块 REQ 列表")
    extracted_constraints: List[str] = Field(default_factory=list, description="从 Solution Pro 语义提取的隐含约束（LLM 推断）")
    relevant_decisions: List[str] = Field(default_factory=list, description="相关决策")
    relevant_risks: List[str] = Field(default_factory=list, description="相关风险")
    interface_contracts: Dict[str, Any] = Field(default_factory=dict, description="接口契约")
    output_schema: Dict[str, Any] = Field(default_factory=dict, description="输出 Schema")
    output_example: Dict[str, Any] = Field(default_factory=dict, description="高质量 WP 示例")
    domain_analysis: Optional[Dict[str, Any]] = Field(default=None, description="领域分析（来自 Planner，含 domain/end_users/deliverable_form/split_dimension）")
    # Semantic Anchors — 信息守恒实体，注入到每个 Worker 的 context.json
    semantic_anchors: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="语义锚点（来自 Living Spec / Frozen Spec，全链路透传）。"
                    "每条包含 name/category/constraint/source_quote，"
                    "Worker 在 WP 描述中应语义引用相关锚点。"
    )


# ============================================================================
# 契约笼子：输入验证
# ============================================================================

def validate_solution_pro_input(data: Dict[str, Any]) -> Dict[str, Any]:
    """验证 Solution Pro 输入，缺失关键字段时 raise ValueError"""
    required_fields = ["requirements"]
    for field in required_fields:
        if field not in data or not data[field]:
            raise ValueError(f"契约笼子: Solution Pro 输入缺少必需字段 '{field}'")
    
    # requirements 必须是列表且非空
    reqs = data["requirements"]
    if not isinstance(reqs, list) or len(reqs) == 0:
        raise ValueError(f"契约笼子: requirements 必须是非空列表，实际: {type(reqs).__name__}, len={len(reqs) if isinstance(reqs, list) else 'N/A'}")
    
    # 每个 requirement 必须有 id
    for i, req in enumerate(reqs):
        if not isinstance(req, dict) or "id" not in req:
            raise ValueError(f"契约笼子: requirements[{i}] 缺少 'id' 字段")
    
    # 契约笼子（2026-07-05 升级）：semantic_anchors 必须存在且类型正确
    if "semantic_anchors" not in data:
        raise ValueError(
            f"契约笼子: frozen_spec 缺少 'semantic_anchors' 字段。\n"
            f"  semantic_anchors 必须由 Solution Pro 从 living_spec 透传。\n"
            f"  请确认 Solution Pro 的 build_frozen_spec() 已包含透传逻辑。"
        )
    if not isinstance(data["semantic_anchors"], list):
        raise ValueError(
            f"契约笼子: semantic_anchors 必须是 list，实际: {type(data['semantic_anchors']).__name__}"
        )
    # AI Native 契约笼子：空 semantic_anchors 不 raise 但标记降级
    if len(data["semantic_anchors"]) == 0:
        import warnings
        warnings.warn(
            "契约笼子: semantic_anchors 为空列表。"
            "信息守恒降级 — Worker 将收到'无上游约束'提示。"
            "请检查 Spec Pro 是否提取了 semantic_anchors。",
            stacklevel=2,
        )
        data["_info_conservation_degraded"] = True
        data["_degradation_reason"] = "semantic_anchors 为空列表"
    else:
        data["_info_conservation_degraded"] = False
    
    return data


# ============================================================================
# 核心逻辑：PipelineDesigner
# ============================================================================

class PipelineDesigner:
    """
    PipelineDesigner
    
    在 Python 内部调用 LLM，分析 Solution Pro 输出，设计 Worker 拆分方案。
    """

    @staticmethod
    def verify_decision_coverage(planner_output: Dict[str, Any],
                                  solution_pro_input: Dict[str, Any]) -> None:
        """
        L0 契约笼子: 验证所有 key_decisions 被至少一个 Worker 引用。
        
        防止 "决策完全未分配" 的二元失败。
        raise ValueError 而非事后报告。
        """
        all_decisions = solution_pro_input.get("key_decisions", [])
        if not all_decisions:
            return  # 无决策则无需检查
        
        # 归一化: 提取每个决策的标识符（前 40 字符作为匹配 key）
        decision_keys = []
        for d in all_decisions:
            if isinstance(d, str):
                decision_keys.append(d[:40])
            elif isinstance(d, dict):
                desc = d.get("description", d.get("decision", str(d)))
                decision_keys.append(desc[:40])
            else:
                decision_keys.append(str(d)[:40])
        
        # 收集所有 Worker 引用的决策文本
        all_referenced = []
        for w in planner_output.get("workers", []):
            all_referenced.extend(w.get("relevant_decisions", []))
        
        # 检查: 每个决策 key 必须出现在至少一个 Worker 的 relevant_decisions 中
        uncovered = []
        for i, key in enumerate(decision_keys):
            found = any(key in ref for ref in all_referenced)
            if not found:
                # 也检查反向: ref 是否在 key 中（Planner 可能截断）
                found = any(ref in all_decisions[i] if isinstance(all_decisions[i], str)
                           else ref in str(all_decisions[i])
                           for ref in all_referenced)
            if not found:
                uncovered.append(f"D{i+1}: {key}...")
        
        if uncovered:
            raise ValueError(
                f"契约笼子 L0: {len(uncovered)}/{len(all_decisions)} 个关键决策未被任何 Worker 引用:\n"
                + "\n".join(f"  - {u}" for u in uncovered)
                + "\n\n修复: Planner 必须将每个 key_decision 分配给至少一个 Worker 的 relevant_decisions。"
            )

    
    # 高质量 WP 示例（嵌入每个 Worker 的 context.json）
    HIGH_QUALITY_WP_EXAMPLE = {
        "id": "CORE-001",
        "title": "Blackboard Manager — 中央共享状态引擎",
        "description": "实现 Blackboard 中央共享状态管理器，作为分形三层 Loop 架构的核心数据交换层。提供 thread-safe 的 read/write/get/set/delete 操作，支持按 stage 维度的命名空间隔离（project_loop / domain_loop / phase_loop 三层）。所有状态读写通过统一 JSON 序列化层进行，确保跨 Layer 数据格式一致。集成原子写入引擎保证崩溃安全，集成 per-stage 锁保证并发安全，集成审计日志记录每次状态变更。",
        "acceptance_criteria": [
            "AC1: 支持 create/read/update/delete/snapshot/restore 六种核心操作",
            "AC2: 三层命名空间隔离（project/domain/phase），各层互不干扰",
            "AC3: 所有读写操作经过 JSON 统一序列化层，无直接 pickle/marshal",
            "AC4: 崩溃恢复测试：kill -9 后重启，状态恢复到最近一次成功 checkpoint"
        ],
        "deliverables": ["blackboard_manager.py", "test_blackboard.py"],
        "effort_hours": 48,
        "dependencies": []
    }
    
    def __init__(self, blackboard_path: Path):
        self.blackboard_path = Path(blackboard_path)
        self.stages_dir = self.blackboard_path / "stages"
        self.stages_dir.mkdir(parents=True, exist_ok=True)
    
    def design_pipeline(self, solution_pro_input: Dict[str, Any], auto: bool = True, plan_output_dir: str = None) -> Dict[str, Any]:
        """
        主入口：分析 Solution Pro → 设计拆分 → 返回 PipelinePlan 或 prompt
        
        auto=True: 尝试内部调用 LLM 直接生成 plan（省去 Orchestrator 重复分析）
        auto=False: 只返回 prompt，由 Orchestrator 自行分析
        
        契约笼子：
        - 输入必须通过 validate_solution_pro_input
        - 输出必须通过 PipelinePlan Pydantic 验证
        """
        # 1. 验证输入（契约笼子）
        validated_input = validate_solution_pro_input(solution_pro_input)
        
        input_summary = {
            "req_count": len(validated_input["requirements"]),
            "decision_count": len(validated_input.get("key_decisions", [])),
            "risk_count": len(validated_input.get("risk_mitigations", [])),
        }
        
        # 2. 尝试自动设计（契约笼子：确定性 LLM 调用，非 prompt 委托）
        if auto:
            auto_result = self._auto_design(validated_input)
            if auto_result:
                result = {
                    "plan": auto_result.model_dump(),
                    "mode": "auto",
                    "expected_schema": PipelinePlan.model_json_schema(),
                    "input_summary": input_summary,
                    "plan_written": False,
                }
                # 契约笼子: auto 模式自动写 plan 到指定目录（消除 LLM 双调用）
                if plan_output_dir:
                    plan_dir = Path(plan_output_dir)
                    plan_dir.mkdir(parents=True, exist_ok=True)
                    plan_path = plan_dir / "pipeline_plan.json"
                    plan_path.write_text(
                        json.dumps(auto_result.model_dump(), ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                    result["plan_written"] = True
                    result["plan_path"] = str(plan_path)
                    logger.info(f"Auto-design: plan written to {plan_path}")
                return result
            logger.warning("Auto-design failed, falling back to prompt mode")
        
        # 3. Fallback：返回 prompt（Orchestrator 自行分析）
        prompt = self._build_designer_prompt(validated_input)
        return {
            "designer_prompt": prompt,
            "mode": "prompt",
            "expected_schema": PipelinePlan.model_json_schema(),
            "input_summary": input_summary,
        }
    
    # Multi-provider fallback chain: (env_key, model, api_url, payload_builder, response_parser)
    _LLM_PROVIDERS = [
        {
            "name": "dashscope",
            "env_key": "DASHSCOPE_API_KEY",
            "model": "qwen-plus",
            "api_url": "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
            "build_payload": lambda prompt, model: json.dumps({
                "model": model,
                "input": {"messages": [
                    {"role": "system", "content": "你是任务拆解与交付规划专家，输出纯 JSON，不要 markdown 包裹。"},
                    {"role": "user", "content": prompt}
                ]},
                "parameters": {"result_format": "message"}
            }).encode("utf-8"),
            "parse_response": lambda result: result["output"]["choices"][0]["message"]["content"],
        },
        {
            "name": "openai_compatible",
            "env_key": "OPENAI_API_KEY",
            "env_url": "OPENAI_BASE_URL",
            "model": "gpt-4o-mini",
            "api_url": None,  # resolved at runtime from env
            "build_payload": lambda prompt, model: json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是任务拆解与交付规划专家，输出纯 JSON，不要 markdown 包裹。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
            }).encode("utf-8"),
            "parse_response": lambda result: result["choices"][0]["message"]["content"],
        },
    ]

    def _auto_design(self, validated_input: Dict[str, Any]) -> Optional[PipelinePlan]:
        """内部调用 LLM 生成 PipelinePlan（契约笼子：确定性调用，失败不抛异常）

        多 provider 回退：按 _LLM_PROVIDERS 顺序尝试，首个可用 provider 成功即返回。
        所有 provider 均失败时返回 None（不抛异常）。
        """
        import os, urllib.request

        prompt = self._build_designer_prompt(validated_input)

        for provider in self._LLM_PROVIDERS:
            api_key = os.environ.get(provider["env_key"], "")
            if not api_key:
                continue

            # Resolve API URL (some providers use env-configured base URL)
            api_url = provider.get("api_url")
            if api_url is None and "env_url" in provider:
                api_url = os.environ.get(provider["env_url"], "")
                if api_url:
                    api_url = api_url.rstrip("/") + "/chat/completions"
            if not api_url:
                continue

            model = provider["model"]
            try:
                payload = provider["build_payload"](prompt, model)
                req = urllib.request.Request(
                    api_url,
                    data=payload,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                with urllib.request.urlopen(req, timeout=120) as response:
                    result = json.loads(response.read().decode("utf-8"))

                content = provider["parse_response"](result)
                from .orchestrator.ship_orchestrator import extract_json_from_completion
                data = extract_json_from_completion(content)
                if data is None:
                    logger.warning(f"Provider {provider['name']}: failed to extract JSON from completion")
                    continue

                return PipelinePlan(**data)
            except Exception as e:
                logger.warning(f"Provider {provider['name']} failed: {e}; trying next provider")
                continue

        logger.warning("All LLM providers exhausted without successful auto-design")
        return None
    
    def parse_designer_output(self, raw_output: str) -> PipelinePlan:
        """
        解析 PipelineDesigner LLM 输出 → PipelinePlan
        
        契约笼子：解析失败 raise ValueError
        """
        from .orchestrator.ship_orchestrator import extract_json_from_completion
        
        data = extract_json_from_completion(raw_output)
        if data is None:
            raise ValueError("契约笼子: PipelineDesigner 输出无法解析为 JSON")
        
        try:
            plan = PipelinePlan(**data)
        except Exception as e:
            raise ValueError(f"契约笼子: PipelineDesigner 输出不符合 PipelinePlan Schema: {e}")
        
        return plan
    
    def generate_worker_contexts(
        self,
        plan: PipelinePlan,
        solution_pro_input: Dict[str, Any]
    ) -> Dict[str, WorkerContext]:
        """
        为每个 Worker 裁剪上下文 → context.json
        
        契约笼子：
        - 每个 context.json 序列化后 ≤ 3KB
        - 每个 Worker 的 covered_req_ids 必须在 requirements 中存在
        """
        contexts = {}
        req_map = {r["id"]: r for r in solution_pro_input["requirements"]}
        
        # Semantic Anchors 提取（全链路透传，不改语义）
        # 从 Solution Pro 输出读取 semantic_anchors（主路，不允许旁路）
        # validate_solution_pro_input() 已保证 semantic_anchors 存在且是 list
        all_anchors = solution_pro_input["semantic_anchors"]
        for i, anchor in enumerate(all_anchors):
            if not isinstance(anchor, dict):
                raise ValueError(
                    f"契约笼子: semantic_anchors[{i}] 必须是 dict，实际: {type(anchor).__name__}"
                )
            if "name" not in anchor:
                raise ValueError(
                    f"契约笼子: semantic_anchors[{i}] 缺少 'name' 字段"
                )
            if "category" not in anchor:
                raise ValueError(
                    f"契约笼子: semantic_anchors[{i}] 缺少 'category' 字段"
                )
        
        # 契约笼子：REQ-ID 不重叠检查
        all_req_ids = []
        for worker in plan.workers:
            all_req_ids.extend(worker.covered_req_ids)
        seen = set()
        duplicates = set()
        for rid in all_req_ids:
            if rid in seen:
                duplicates.add(rid)
            seen.add(rid)
        if duplicates:
            raise ValueError(
                f"契约笼子: REQ-ID 被多个 Worker 重复分配: {sorted(duplicates)}。"
                f"每个 REQ-ID 只能分配给一个 Worker。"
            )
        
        for worker in plan.workers:
            # 验证 REQ-ID 存在性
            for req_id in worker.covered_req_ids:
                if req_id not in req_map:
                    raise ValueError(
                        f"契约笼子: Worker '{worker.role}' 引用的 REQ-ID '{req_id}' "
                        f"在 Solution Pro 输入中不存在"
                    )
            
            # 裁剪
            module_reqs = [req_map[rid] for rid in worker.covered_req_ids if rid in req_map]
            
            # 语义提取隐含约束（AI Native：从 key_decisions + architecture 推断）
            extracted_constraints = self._extract_implicit_constraints(
                worker, solution_pro_input
            )
            
            # Semantic Anchors 按需裁剪注入
            # 核心约束（applicable_to == ['all']）广播
            # 领域特定约束按 Worker role 裁剪
            worker_anchors = []
            if all_anchors:
                core_anchors = [
                    a for a in all_anchors
                    if a.get("applicable_to", ["all"]) == ["all"]
                ]
                specific_anchors = [
                    a for a in all_anchors
                    if a.get("applicable_to", ["all"]) != ["all"]
                    and worker.role in a.get("applicable_to", [])
                ]
                worker_anchors = core_anchors + specific_anchors
            
            context = WorkerContext(
                module_overview=worker.module_purpose,
                module_reqs=module_reqs,
                extracted_constraints=extracted_constraints,
                relevant_decisions=worker.relevant_decisions,
                relevant_risks=worker.relevant_risks,
                interface_contracts={
                    "provides": worker.interface_provides,
                    "requires": worker.interface_requires,
                    "downstream_consumers": self._find_downstream(worker.role, plan),
                },
                output_schema=self._get_worker_schema_compact(),
                output_example=self.HIGH_QUALITY_WP_EXAMPLE,
                domain_analysis=plan.domain_analysis,
                semantic_anchors=worker_anchors,
            )
            
            # 契约笼子：context 大小检查
            serialized = json.dumps(context.model_dump(), ensure_ascii=False)
            if len(serialized) > 3072:  # 3KB
                logger.warning(
                    f"Worker '{worker.role}' context.json 超过 3KB ({len(serialized)} bytes)，"
                    f"尝试裁剪 module_reqs"
                )
                # 自动裁剪：req description 截短 + extracted_constraints 限数 + risks 截短
                trimmed_reqs = [
                    {"id": r["id"], "description": r.get("description", "")[:40], "priority": r.get("priority", "P1")}
                    for r in module_reqs
                ]
                trimmed_constraints = [c[:80] for c in context.extracted_constraints[:3]] if context.extracted_constraints else []
                trimmed_risks = [r[:60] for r in context.relevant_risks[:2]]
                trimmed_decisions = [d[:60] for d in context.relevant_decisions[:3]]
                context = context.model_copy(update={
                    "module_reqs": trimmed_reqs,
                    "extracted_constraints": trimmed_constraints,
                    "relevant_risks": trimmed_risks,
                    "relevant_decisions": trimmed_decisions,
                })
                serialized = json.dumps(context.model_dump(), ensure_ascii=False)
                if len(serialized) > 8192:  # context.json 8KB 上限（prompt 3KB 限制在 __init__.py 执行）
                    raise ValueError(
                        f"契约笼子: Worker '{worker.role}' context.json 裁剪后仍超 8KB ({len(serialized)} bytes)"
                    )
            
            contexts[worker.role] = context
        
        return contexts
    
    def save_contexts(self, contexts: Dict[str, WorkerContext]) -> Dict[str, str]:
        """将 context.json 写入 blackboard"""
        paths = {}
        for role, ctx in contexts.items():
            safe_name = role.replace(" ", "_").replace("/", "_")
            path = self.stages_dir / f"context_{safe_name}.json"
            path.write_text(json.dumps(ctx.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
            paths[role] = str(path)
        return paths
    
    def get_execution_order(self, plan: PipelinePlan) -> List[List[str]]:
        """返回拓扑排序后的执行顺序"""
        return plan.execution_order
    
    # ============================================================================
    # 内部方法
    # ============================================================================
    
    def _build_designer_prompt(self, solution_pro_input: Dict[str, Any]) -> str:
        """构建 PipelineDesigner LLM prompt（领域无关版本）"""
        reqs = solution_pro_input["requirements"]
        decisions = solution_pro_input.get("key_decisions", [])
        risks = solution_pro_input.get("risk_mitigations", [])
        arch = solution_pro_input.get("architecture", {})

        return f"""你是任务拆解与交付规划专家。分析上游方案输出，设计 Worker 并行拆分方案。

## 你的架构位置
上游方案 → 【你(Planner)】→ Workers(并行) → Consolidator(组装) → 最终用户

## 第一步：领域分析（domain_analysis，强烈建议）
在拆分前，先回答 4 个问题：
1. **domain**: 这是什么领域？（软件/投资/创作/咨询/...）
2. **end_users**: 最终用户是谁？（谁消费最终交付物？）
3. **deliverable_form**: 最终交付物形态？（代码模块/分析报告/文章/方案/...）
4. **split_dimension**: 按什么维度拆分？（模块/分析维度/章节/阶段/...）
5. **key_constraints**: 关键约束？（≤3 条）

## 拆分原则
- 按**交付物组成单元**拆分，不按需求分组
- 每个 Worker = 一个可独立执行、独立验证、独立交付的工作单元
- Worker 数量：2-8 个
- 三个判断维度：内聚性 + 可并行性 + 可验证性

## 跨域示例

### 示例 1（软件开发）
domain_analysis: {{"domain": "软件开发", "end_users": ["开发者","运维"], "deliverable_form": "可部署代码模块+测试", "split_dimension": "按代码内聚性(模块)", "key_constraints": ["接口兼容","零宕机部署"]}}
workers: [CoreInfra(3WPs,0deps), UserInterface(4WPs,deps:[CoreInfra]), QAGate(2WPs,deps:[CoreInfra,UserInterface])]
execution_order: [["CoreInfra"],["UserInterface"],["QAGate"]]

### 示例 2（投资分析）
domain_analysis: {{"domain": "投资分析", "end_users": ["投资决策者","投委会"], "deliverable_form": "完整投资分析报告", "split_dimension": "按分析维度", "key_constraints": ["数据可溯源","合规审查"]}}
workers: [IndustryAnalyst(3WPs,0deps), CompanyAnalyst(4WPs,deps:[IndustryAnalyst]), FinancialModeler(3WPs,deps:[CompanyAnalyst]), ValuationExpert(2WPs,deps:[FinancialModeler])]
execution_order: [["IndustryAnalyst"],["CompanyAnalyst"],["FinancialModeler"],["ValuationExpert"]]

### 示例 3（内容创作）
domain_analysis: {{"domain": "内容创作", "end_users": ["读者","编辑"], "deliverable_form": "完整文章", "split_dimension": "按章节结构", "key_constraints": ["风格统一","事实准确"]}}
workers: [Researcher(2WPs,0deps), OutlineWriter(1WP,deps:[Researcher]), ChapterWriter(3WPs,deps:[OutlineWriter])]
execution_order: [["Researcher"],["OutlineWriter"],["ChapterWriter"]]

## 上游方案输入摘要
- 需求数量：{len(reqs)}
- 关键决策：{len(decisions)} 条
- 风险缓解：{len(risks)} 条
- 架构/方案概述：{json.dumps(arch, ensure_ascii=False)[:500] if arch else '无'}

## 需求列表
{json.dumps(reqs[:80], ensure_ascii=False, indent=2)[:3000]}

## 关键决策
{json.dumps(decisions, ensure_ascii=False, indent=2)[:1000] if decisions else '无'}

## 输出格式（严格 JSON，PipelinePlan Schema）
{{
  "domain_analysis": {{
    "domain": "领域名称",
    "end_users": ["用户角色1", "用户角色2"],
    "deliverable_form": "最终交付物形态",
    "split_dimension": "拆分维度",
    "key_constraints": ["约束1", "约束2"]
  }},
  "workers": [
    {{
      "role": "Worker 角色名",
      "module_purpose": "工作单元目的（≥20 字）",
      "covered_req_ids": ["REQ-001", "REQ-002"],
      "depends_on": [],
      "interface_provides": ["输出接口描述"],
      "interface_requires": [],
      "relevant_decisions": ["D1: 决策描述"],
      "relevant_risks": ["RISK-1: 风险描述"],
      "estimated_wps": 5,
      "estimated_effort_hours": 40,
      "must_constraints": ["继承的硬约束"],
      "wp_id_prefix": "ABC"
    }}
  ],
  "execution_order": [
    ["基础 Worker"],
    ["Worker A", "Worker B"],
    ["上层 Worker"]
  ],
  "rationale": "拆分理由（≥50 字，需解释为什么这样拆分对最终用户最优）"
}}

## 约束
- workers 数量 2-8
- execution_order 必须构成 DAG 无环图
- **每个 REQ-ID 只能分配给一个 Worker，禁止跨 Worker 重复**
- 每个 Worker 的 covered_req_ids 必须是输入中存在的 REQ-ID
- execution_order 必须包含所有 Worker role
- wp_id_prefix 每个 Worker 唯一（如 IND-、FIN-、VAL-）
- relevant_decisions ≤ 5 个
- relevant_risks ≤ 3 个

只输出 JSON，不要其他文字。"""
    
    def _extract_implicit_constraints(
        self,
        worker: WorkerSpec,
        solution_pro_input: Dict[str, Any]
    ) -> List[str]:
        """
        AI Native 语义提取：从 Solution Pro 输出中推断每个 Worker 的隐含约束。
        
        不依赖上游显式声明 must_constraints，而是从：
        - key_decisions 中的技术决策（如"统一 JSON 序列化"）
        - architecture 中的架构约束（如"分层架构"）
        - guardrails / must_constraints（如果存在）
        中语义提取与本 Worker 相关的约束。
        """
        constraints = []
        
        # 从 key_decisions 提取
        decisions = solution_pro_input.get("key_decisions", [])
        for d in decisions:
            if isinstance(d, str):
                constraints.append(f"技术决策: {d}")
            elif isinstance(d, dict):
                desc = d.get("description", d.get("decision", str(d)))
                constraints.append(f"技术决策: {desc}")
        
        # 从 architecture 提取
        arch = solution_pro_input.get("architecture", {})
        if isinstance(arch, dict):
            pattern = arch.get("pattern", arch.get("style", ""))
            if pattern:
                constraints.append(f"架构约束: {pattern}")
            layers = arch.get("layers", [])
            if layers:
                constraints.append(f"架构约束: 分层架构 {', '.join(str(l) for l in layers[:3])}")
        
        # 从 guardrails / must_constraints 提取（如果存在）
        for field in ["guardrails", "must_constraints", "constraints"]:
            items = solution_pro_input.get(field, [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, str):
                        constraints.append(f"硬约束: {item}")
                    elif isinstance(item, dict):
                        desc = item.get("description", item.get("constraint", str(item)))
                        constraints.append(f"硬约束: {desc}")
        
        # 限制数量（避免 context 膨胀）
        return constraints[:10]
    
    def _find_downstream(self, role: str, plan: PipelinePlan) -> List[str]:
        """找到依赖当前 Worker 的下游 Worker"""
        downstream = []
        for worker in plan.workers:
            if role in worker.depends_on:
                downstream.append(worker.role)
        return downstream
    
    def _get_worker_schema_compact(self) -> Dict[str, Any]:
        """精简版 Worker 输出 Schema（P2-2-FIX: object 而非 array）"""
        return {
            "type": "object",
            "properties": {
                "worker_role": "string (当前 Worker 角色名)",
                "wp_id_prefix": "string (WP ID 前缀，如 CORE-、LOOP-)",
                "work_packages": {
                    "type": "array",
                    "items": {
                        "wp_id": "string (格式: {prefix}-NNN)",
                        "title": "string",
                        "description": "string (≥100 字，包含技术实现细节)",
                        "acceptance_criteria": ["string (≥2 条，每条可测试)"],
                        "deliverables": ["string (≥1 项)"],
                        "effort_hours": "number",
                        "dependencies": ["string (其他 WP ID)"]
                    }
                }
            },
            "required": ["worker_role", "wp_id_prefix", "work_packages"]
        }
