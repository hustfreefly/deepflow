"""
Solution Pro 路径注册表

Version: 3.2.0
Author: DeepFlow Solution Pro
Date: 2026-06-28

变更:
- V3.2: 新增 V2 架构 Stage 路径（Planning V2 三层 + 收敛点）
- V3.2: 新增 DEPRECATED_STAGE_ALIASES 向后兼容映射
- V3.1: STAGE_PATH_REGISTRY 标记 @deprecated，推荐使用 V6 read_stage/write_stage
- 瘦身为纯 Registry 定义，读写逻辑委托给 core.BlackboardManager
- 本地 BlackboardManager 实现（已废弃）
"""

import core.bootstrap  # 契约笼子: 通过 bootstrap 自动加入 sys.path
from typing import Type

from core.blackboard.registry_base import DomainRegistry
from core.blackboard.blackboard_manager import BlackboardManager as CoreBlackboardManager


# ============================================================================
# 路径注册表（唯一事实源）— @deprecated
# 推荐使用 V6 API: read_stage / write_stage / stage_exists / list_stages
# 所有 stage 文件路径必须从这里获取，禁止自行拼接
# ============================================================================

# 使用 helper 构建 stage 路径，避免硬编码路径模式
_S = "stages"
_J = ".json"


def _sp(name: str) -> str:
    """构建 stage 相对路径"""
    return f"{_S}/{name}{_J}"


# @deprecated: 推荐使用 BlackboardManager V6 API (read_stage / write_stage)
# V1 架构 Stage 路径（保留向后兼容）
STAGE_PATH_REGISTRY_V1 = {
    "data_collection": "data/collection.json",
    "structured_requirements": "data/structured_requirements.json",
    "frozen_spec": "data/frozen_spec.json",
    "requirements_traceability_matrix": "requirements_traceability_matrix.json",
    "planning": _sp("planning"),
    "reviewer_technical": _sp("reviewer_technical"),
    "reviewer_business": _sp("reviewer_business"),
    "reviewer_risk": _sp("reviewer_risk"),
    "research_expert_1": _sp("research_expert_1"),
    "research_expert_2": _sp("research_expert_2"),
    "research_expert_3": _sp("research_expert_3"),
    "design": _sp("design"),
    "audit": _sp("audit"),
    "fix": _sp("fix"),
    "fixer_expert": _sp("fixer_expert"),
    "consolidator": _sp("consolidator"),
    "harness_final": _sp("harness_final"),
    "summarizer": "final_result.json",
}

# ============================================================================
# V2 架构 Stage 路径（Planning V2 三层 + 收敛点）
# ============================================================================
STAGE_PATH_REGISTRY_V2 = {
    # Module 1: Planning V2 三层架构
    "meta_planning": _sp("meta_planning"),
    "expert_plans": "stages/expert_plans/",  # 目录，包含 N 个 expert_plan_{name}.json
    "convergence_planning": _sp("convergence_planning"),
    "unified_constraints": _sp("unified_constraints"),
    "verification_checklist": _sp("verification_checklist"),
    
    # Module 2: Research（扩展为动态 M 个专家）
    "research_experts": "stages/research_experts/",  # 目录，包含 M 个 research_expert_{name}.json
    "research_consolidator": _sp("research_consolidator"),
    "architecture": _sp("architecture"),
    "detailed_design": _sp("detailed_design"),
    
    # Module 3: Review & QC（Fix Loop 替代 Audit+Fix+Fixer）
    "consolidation": _sp("consolidation"),
    "harness_report": _sp("harness_report"),
    "fix_loop_state": _sp("fix_loop_state"),
    
    # 收敛点文件（Module 间通信契约）
    "planning_convergence": "planning_convergence.json",
    "research_convergence": "research_convergence.json",
    "final_convergence": "final_convergence.json",
    
    # 信息守恒契约
    "information_contract": _sp("information_contract"),
}

# ============================================================================
# 合并 V1 + V2 路径注册表
# ============================================================================
STAGE_PATH_REGISTRY = {
    **STAGE_PATH_REGISTRY_V1,
    **STAGE_PATH_REGISTRY_V2,
}

# ============================================================================
# Deprecated Stage Aliases（向后兼容映射）
# V1 旧 Stage 名 → V2 新 Stage 名
# ============================================================================
DEPRECATED_STAGE_ALIASES = {
    # V1 Planning → V2 Meta-Planning
    "planning": "meta_planning",
    
    # V1 固定 3 Reviewer → V2 Reviewer_Meta（合并）
    "reviewer_technical": "meta_planning",  # Reviewer 职责并入 Meta-Planner
    "reviewer_business": "meta_planning",
    "reviewer_risk": "meta_planning",
    
    # V1 固定 3 Research Expert → V2 动态 M 个（目录）
    "research_expert_1": "research_experts",
    "research_expert_2": "research_experts",
    "research_expert_3": "research_experts",
    
    # V1 Design → V2 Architecture + Detailed Design
    "design": "detailed_design",
    
    # V1 Audit + Fix + Fixer → V2 Fix Loop
    "audit": "fix_loop_state",
    "fix": "fix_loop_state",
    "fixer_expert": "fix_loop_state",
    
    # V1 Consolidator → V2 Consolidation
    "consolidator": "consolidation",
    
    # V1 Harness Final → V2 Harness Report
    "harness_final": "harness_report",
}


PIPELINE_STAGES = (
    "data_collection",
    "planning",
    "reviewers",
    "research",
    "consolidator",
    "audit",
    "fix",
    "fixer_expert",
    "harness_final",
    "summarizer",
)


# ============================================================================
# Solution Pro Registry（继承 DomainRegistry）— @deprecated
# ============================================================================
class SolutionRegistry(DomainRegistry):
    """Solution Pro 路径注册表 — @deprecated: 推荐使用 BlackboardManager V6 API"""
    STAGE_PATH_REGISTRY = STAGE_PATH_REGISTRY


# ============================================================================
# BlackboardManager 别名（向后兼容）
# ============================================================================
# 旧代码: from domains.solution_pro.blackboard import BlackboardManager
# 新代码: 自动委托给 core.BlackboardManager，预配置 SolutionRegistry
# ============================================================================
class BlackboardManager(CoreBlackboardManager):
    """
    Solution Pro BlackboardManager（向后兼容）

    自动配置 SolutionRegistry，无需手动 set_registry()
    """

    def __init__(self, session_id: str, base_dir=None):
        super().__init__(session_id, base_dir=base_dir, registry=SolutionRegistry)

    def write(self, filename: str, content, subdir=None):
        """
        重写 write() 以支持 list 类型（V2 增强）
        
        原 core 实现只支持 dict 和 str，这里扩展为 dict/list → JSON，str → 文本
        """
        import json
        import os
        import tempfile
        from pathlib import Path
        
        target = self._resolve(filename, subdir)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            if isinstance(content, (dict, list)):
                data = json.dumps(content, ensure_ascii=False, indent=2).encode()
            else:
                data = content.encode()
            os.write(fd, data)
            os.fsync(fd)
            os.close(fd)
            Path(tmp).rename(target)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            Path(tmp).unlink(missing_ok=True)
            raise
        return target