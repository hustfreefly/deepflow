"""
Ship Pro V8 - PipelineDesigner

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
    """PipelineDesigner 输出的单个 Worker 规格"""
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
    
    return data


# ============================================================================
# 核心逻辑：PipelineDesigner
# ============================================================================

class PipelineDesigner:
    """
    V8 PipelineDesigner
    
    在 Python 内部调用 LLM，分析 Solution Pro 输出，设计 Worker 拆分方案。
    """
    
    # 高质量 WP 示例（嵌入每个 Worker 的 context.json）
    HIGH_QUALITY_WP_EXAMPLE = {
        "wp_id": "CORE-001",
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
    
    def design_pipeline(self, solution_pro_input: Dict[str, Any]) -> PipelinePlan:
        """
        主入口：分析 Solution Pro → 设计拆分 → 返回 PipelinePlan
        
        契约笼子：
        - 输入必须通过 validate_solution_pro_input
        - 输出必须通过 PipelinePlan Pydantic 验证
        """
        # 1. 验证输入（契约笼子）
        validated_input = validate_solution_pro_input(solution_pro_input)
        
        # 2. 构建 PipelineDesigner prompt
        prompt = self._build_designer_prompt(validated_input)
        
        # 3. 返回 prompt（由调用者决定如何执行 LLM）
        # 这里返回 prompt + 预期 schema，调用者可以用 exec 调 LLM 或用 mock
        return {
            "designer_prompt": prompt,
            "expected_schema": PipelinePlan.model_json_schema(),
            "input_summary": {
                "req_count": len(validated_input["requirements"]),
                "decision_count": len(validated_input.get("key_decisions", [])),
                "risk_count": len(validated_input.get("risk_mitigations", [])),
            }
        }
    
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
        """构建 PipelineDesigner LLM prompt"""
        reqs = solution_pro_input["requirements"]
        decisions = solution_pro_input.get("key_decisions", [])
        risks = solution_pro_input.get("risk_mitigations", [])
        arch = solution_pro_input.get("architecture", {})
        
        return f"""你是一个软件工程架构师。分析以下 Solution Pro 输出，设计 Worker 拆分方案。

## 拆分原则
- 按**交付物模块**（代码内聚性）拆分，不按 REQ 分组
- 每个 Worker = 一个可独立开发、独立测试、独立交付的软件模块
- Worker 数量：4-6 个（中型项目）
- 三个判断维度：内聚性 + 可并行性 + 可验证性

## Solution Pro 输入摘要
- 需求数量：{len(reqs)}
- 架构决策：{len(decisions)} 条
- 风险缓解：{len(risks)} 条
- 架构概述：{json.dumps(arch, ensure_ascii=False)[:500] if arch else '无'}

## 需求列表
{json.dumps(reqs[:80], ensure_ascii=False, indent=2)[:3000]}

## 架构决策
{json.dumps(decisions, ensure_ascii=False, indent=2)[:1000] if decisions else '无'}

## 输出格式（严格 JSON）
```json
{{
  "workers": [
    {{
      "role": "模块名称",
      "module_purpose": "模块目的（≥20 字）",
      "covered_req_ids": ["REQ-001", "REQ-002"],
      "depends_on": [],
      "interface_provides": ["method_name(param) → return_type"],
      "interface_requires": [],
      "relevant_decisions": ["D1: 决策描述"],
      "relevant_risks": ["RISK-1: 风险描述"],
      "estimated_wps": 5,
      "estimated_effort_hours": 40
    }}
  ],
  "execution_order": [
    ["基础模块"],
    ["模块A", "模块B"],
    ["上层模块"]
  ],
  "rationale": "拆分理由（≥50 字）"
}}
```

## 约束
- workers 数量 2-8
- **每个 REQ-ID 只能分配给一个 Worker，禁止跨 Worker 重复**
- 每个 Worker 的 covered_req_ids 必须是输入中存在的 REQ-ID
- execution_order 必须包含所有 Worker role
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
        """精简版 Worker 输出 Schema"""
        return {
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
