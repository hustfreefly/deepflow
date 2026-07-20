"""E2E Pipeline Contract — 契约笼子：强制完整管线续行

设计意图：
  解决 E2E 测试中 Sol Pro 完成后 Orchestrator 直接终止的问题。
  用 Pydantic 强类型契约定义管线阶段，Python 代码验证续行。

  铁律：
  1. 每个阶段必须验证前序阶段产出存在
  2. 任何阶段失败 → raise ValueError，不静默跳过
  3. 管线不完整（缺少后续阶段）→ raise ValueError

Version: 1.0.0
Date: 2026-07-12
"""

from typing import Dict, List, Optional, Tuple
from pathlib import Path
from pydantic import BaseModel, Field


class PipelineStage(BaseModel):
    """管线阶段契约"""
    name: str = Field(..., description="阶段名称")
    domain: str = Field(..., description="所属域")
    entry_function: str = Field(..., description="入口函数名")
    required_produce: List[str] = Field(..., description="必须产出的文件列表")
    required_consume: List[str] = Field(default_factory=list, description="必须消费的前序文件")
    timeout_minutes: int = Field(default=15, description="超时分钟数")


class E2EPipelineContract(BaseModel):
    """E2E 完整管线契约"""
    version: str = "1.0.0"
    stages: List[PipelineStage] = Field(..., description="管线阶段列表（有序）")

    def get_stage(self, name: str) -> Optional[PipelineStage]:
        for stage in self.stages:
            if stage.name == name:
                return stage
        return None

    def get_next_stage(self, current: str) -> Optional[PipelineStage]:
        """获取当前阶段的下一个阶段"""
        for i, stage in enumerate(self.stages):
            if stage.name == current and i + 1 < len(self.stages):
                return self.stages[i + 1]
        return None


# ═══════════════════════════════════════════
# 标准 E2E 管线定义
# ═══════════════════════════════════════════

STANDARD_PIPELINE = E2EPipelineContract(
    stages=[
        PipelineStage(
            name="spec_pro",
            domain="spec_pro",
            entry_function="SpecProCoordinator.init_session()",
            required_produce=["spec/living_spec.md"],
            required_consume=[],
            timeout_minutes=10,
        ),
        PipelineStage(
            name="solution_pro",
            domain="solution_pro",
            entry_function="run_solution_pro()",
            required_produce=[
                "stages/final_solution.md",
                "data/frozen_spec.md",
            ],
            required_consume=["spec/living_spec.md"],
            timeout_minutes=15,
        ),
        PipelineStage(
            name="ship_pro",
            domain="ship_pro",
            entry_function="run_ship_pro()",
            required_produce=[
                "ship_pro/stages/ship_package.json",
            ],
            required_consume=[
                "data/frozen_spec.md",
            ],
            timeout_minutes=15,
        ),
        PipelineStage(
            name="deliver_pro",
            domain="deliver_pro",
            entry_function="run_deliver_pro()",
            required_produce=[
                "deliver_pro/DELIVERABLE.md",
            ],
            required_consume=[
                "ship_pro/stages/ship_package.json",
            ],
            timeout_minutes=15,
        ),
    ]
)


# ═══════════════════════════════════════════
# 契约验证器
# ═══════════════════════════════════════════

class E2EValidator:
    """E2E 管线契约验证器
    
    用法:
        validator = E2EValidator(project_blackboard)
        
        # Sol Pro 完成后调用
        result = validator.validate_stage_complete("solution_pro")
        if not result["ok"]:
            raise ValueError(f"Sol Pro 产出缺失: {result['missing']}")
        
        # 检查是否需要续行
        next_stage = validator.get_next_action("solution_pro")
        if next_stage:
            # 必须继续执行 next_stage["name"]
            ...
    """

    def __init__(self, project_blackboard: Path):
        self.bb = project_blackboard
        self.contract = STANDARD_PIPELINE

    def validate_stage_complete(self, stage_name: str) -> Dict:
        """验证阶段产出是否完整
        
        Returns:
            {"ok": bool, "produced": [...], "missing": [...]}
        """
        stage = self.contract.get_stage(stage_name)
        if not stage:
            return {"ok": False, "produced": [], "missing": [f"Unknown stage: {stage_name}"]}

        produced = []
        missing = []

        for file_path in stage.required_produce:
            full_path = self.bb / file_path
            if full_path.exists() and full_path.stat().st_size > 0:
                produced.append(file_path)
            else:
                missing.append(file_path)

        return {
            "ok": len(missing) == 0,
            "produced": produced,
            "missing": missing,
            "stage": stage_name,
        }

    def validate_prerequisites(self, stage_name: str) -> Dict:
        """验证阶段的前序依赖是否满足
        
        Returns:
            {"ok": bool, "satisfied": [...], "missing": [...]}
        """
        stage = self.contract.get_stage(stage_name)
        if not stage:
            return {"ok": False, "satisfied": [], "missing": [f"Unknown stage: {stage_name}"]}

        satisfied = []
        missing = []

        for file_path in stage.required_consume:
            full_path = self.bb / file_path
            if full_path.exists() and full_path.stat().st_size > 0:
                satisfied.append(file_path)
            else:
                missing.append(file_path)

        return {
            "ok": len(missing) == 0,
            "satisfied": satisfied,
            "missing": missing,
            "stage": stage_name,
        }

    def get_next_action(self, completed_stage: str) -> Optional[Dict]:
        """获取续行动作（契约笼子核心）
        
        如果当前阶段完成且后续阶段存在 → 返回下一阶段信息
        如果管线已完成 → 返回 None
        如果当前阶段产出不完整 → raise ValueError
        
        Returns:
            {"action": "continue", "stage": PipelineStage} or None
            
        Raises:
            ValueError: 当前阶段产出不完整（契约笼子阻断）
        """
        # 先验证当前阶段产出完整
        validation = self.validate_stage_complete(completed_stage)
        if not validation["ok"]:
            raise ValueError(
                f"契约笼子阻断: {completed_stage} 产出不完整。\n"
                f"  已产出: {validation['produced']}\n"
                f"  缺失: {validation['missing']}\n"
                f"  不允许续行到下一阶段。"
            )

        # 获取下一阶段
        next_stage = self.contract.get_next_stage(completed_stage)
        if next_stage is None:
            return None  # 管线已完成

        # 验证下一阶段的前序依赖
        prereq = self.validate_prerequisites(next_stage.name)
        return {
            "action": "continue",
            "stage": next_stage.name,
            "domain": next_stage.domain,
            "entry_function": next_stage.entry_function,
            "prerequisites_ok": prereq["ok"],
            "prerequisites_missing": prereq["missing"],
        }

    def check_pipeline_complete(self) -> Tuple[bool, Dict]:
        """检查完整管线是否已完成
        
        Returns:
            (is_complete, details)
        """
        details = {}
        all_ok = True

        for stage in self.contract.stages:
            validation = self.validate_stage_complete(stage.name)
            details[stage.name] = validation
            if not validation["ok"]:
                all_ok = False

        return all_ok, details
