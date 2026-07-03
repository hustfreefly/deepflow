"""
Solution Pro Pipeline State — 契约笼子 Phase 1

Pydantic 模型作为唯一真相源，所有状态写入必须经过验证。
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class StageProgress(BaseModel):
    """阶段进度状态"""
    stage_name: str
    status: Literal["pending", "running", "completed", "failed", "skipped"]
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    output_file: Optional[str] = None
    
    def mark_running(self):
        """标记为运行中"""
        self.status = "running"
        self.started_at = datetime.now().isoformat()
    
    def mark_completed(self, output_file: Optional[str] = None):
        """标记为完成"""
        self.status = "completed"
        self.completed_at = datetime.now().isoformat()
        if output_file:
            self.output_file = output_file
        if self.started_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.completed_at)
            self.duration_seconds = (end - start).total_seconds()


class ConvergenceState(BaseModel):
    """收敛状态"""
    module_name: str
    converged: bool = False
    convergence_file: Optional[str] = None
    gate_a_result: Optional[str] = None  # "PASS", "FAIL", "CONDITIONAL"
    gate_b_result: Optional[str] = None  # "PASS", "FAIL", "CONDITIONAL"
    overall_verdict: Optional[str] = None
    
    def mark_converged(self, gate_a: str, gate_b: str, verdict: str, file_path: str):
        """标记为已收敛"""
        self.converged = True
        self.gate_a_result = gate_a
        self.gate_b_result = gate_b
        self.overall_verdict = verdict
        self.convergence_file = file_path


class ModuleState(BaseModel):
    """模块状态"""
    module_name: str
    status: Literal["pending", "running", "completed", "failed"]
    stages: dict[str, StageProgress] = Field(default_factory=dict)
    convergence: Optional[ConvergenceState] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class SolutionProPipelineState(BaseModel):
    """
    Solution Pro Pipeline 统一状态
    
    这是唯一的真相源（pipeline_state.json）。
    所有状态更新必须通过此模型验证。
    """
    
    session_id: str
    status: Literal["preparing", "running", "completed", "failed"] = "preparing"
    
    # 模块状态
    modules: dict[str, ModuleState] = Field(default_factory=dict)
    
    # 时间戳
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # 收敛状态汇总
    all_modules_converged: bool = False
    
    # 补充轮次（用于记录 refinement 轮次）
    supplementary_rounds: int = 0
    supplementary_files: list[str] = Field(default_factory=list)
    
    def start_module(self, module_name: str):
        """启动模块"""
        if module_name not in self.modules:
            self.modules[module_name] = ModuleState(
                module_name=module_name,
                status="running",
                started_at=datetime.now().isoformat()
            )
        else:
            self.modules[module_name].status = "running"
            self.modules[module_name].started_at = datetime.now().isoformat()
        
        if not self.started_at:
            self.started_at = datetime.now().isoformat()
        
        self.status = "running"
    
    def update_stage_progress(self, module_name: str, stage_name: str, 
                             status: Literal["pending", "running", "completed", "failed", "skipped"],
                             output_file: Optional[str] = None):
        """更新阶段进度"""
        if module_name not in self.modules:
            self.start_module(module_name)
        
        module = self.modules[module_name]
        if stage_name not in module.stages:
            module.stages[stage_name] = StageProgress(
                stage_name=stage_name,
                status=status
            )
        
        stage = module.stages[stage_name]
        if status == "running":
            stage.mark_running()
        elif status == "completed":
            stage.mark_completed(output_file)
        else:
            stage.status = status
    
    def mark_module_converged(self, module_name: str, gate_a: str, gate_b: str, 
                             verdict: str, convergence_file: str):
        """标记模块收敛"""
        if module_name not in self.modules:
            raise ValueError(f"Module {module_name} not found")
        
        module = self.modules[module_name]
        if not module.convergence:
            module.convergence = ConvergenceState(module_name=module_name)
        
        module.convergence.mark_converged(gate_a, gate_b, verdict, convergence_file)
        
        # 检查是否所有模块都收敛了
        self.all_modules_converged = all(
            m.convergence and m.convergence.converged 
            for m in self.modules.values()
        )
    
    def complete_module(self, module_name: str):
        """完成模块"""
        if module_name in self.modules:
            self.modules[module_name].status = "completed"
            self.modules[module_name].completed_at = datetime.now().isoformat()
    
    def add_supplementary_round(self, file_path: str):
        """添加补充轮次"""
        self.supplementary_rounds += 1
        if file_path not in self.supplementary_files:
            self.supplementary_files.append(file_path)
    
    def mark_completed(self):
        """标记 pipeline 完成"""
        self.status = "completed"
        self.completed_at = datetime.now().isoformat()


# 导出模型供其他模块使用
__all__ = [
    "SolutionProPipelineState",
    "ModuleState", 
    "StageProgress",
    "ConvergenceState"
]
