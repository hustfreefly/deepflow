"""
Solution Pro State Manager — 契约笼子 Phase 2

所有 Blackboard 状态写入必须通过此 Manager，确保：
1. 写入前 Pydantic 验证
2. 状态变更经过 state machine 规则
3. 收敛状态正确标记
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import logging

from pydantic import ValidationError

from .contracts.pipeline_state import (
    SolutionProPipelineState,
    ModuleState,
    StageProgress,
    ConvergenceState
)

logger = logging.getLogger(__name__)


class StateTransitionError(Exception):
    """非法状态转换"""
    pass


class SolutionProStateManager:
    """
    Solution Pro 状态管理器
    
    职责：
    1. 管理 pipeline_state.json（单一真相源）
    2. 所有写入经 Pydantic 验证
    3. 状态转换经过 state machine 规则
    4. 自动更新 stage_progress.json（兼容性文件）
    """
    
    VALID_TRANSITIONS = {
        "preparing": ["running", "failed"],
        "running": ["completed", "failed"],
        "completed": [],  # terminal
        "failed": ["running"],  # can retry
    }
    
    def __init__(self, blackboard_path: Path):
        """
        初始化状态管理器
        
        Args:
            blackboard_path: Blackboard 目录路径
        """
        self.blackboard_path = Path(blackboard_path)
        self.state_file = self.blackboard_path / "pipeline_state.json"
        self.state: Optional[SolutionProPipelineState] = None
        
        # 尝试加载现有状态
        self._load_or_init()
    
    def _load_or_init(self):
        """加载或初始化状态"""
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                self.state = SolutionProPipelineState(**data)
                logger.info(f"Loaded pipeline state: {self.state.session_id}")
            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning(f"Failed to load state, initializing new: {e}")
                self._init_new_state()
        else:
            self._init_new_state()
    
    def _init_new_state(self, session_id: Optional[str] = None):
        """初始化新状态"""
        self.state = SolutionProPipelineState(
            session_id=session_id or f"session_{int(datetime.now().timestamp())}",
            status="preparing"
        )
        self._save()
    
    def _save(self):
        """保存状态（Pydantic 验证）"""
        # Pydantic 自动验证
        data = self.state.model_dump(mode="json")
        
        # 写入 pipeline_state.json（原子操作）
        temp_file = self.state_file.with_suffix(".tmp")
        temp_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        temp_file.rename(self.state_file)
        
        # 同步写入 stage_progress.json（兼容性）
        self._sync_stage_progress()
        
        logger.debug(f"State saved: {self.state.status}")
    
    def _sync_stage_progress(self):
        """同步 stage_progress.json（兼容性文件）"""
        progress_file = self.blackboard_path / "stage_progress.json"
        
        progress_data = {
            "session_id": self.state.session_id,
            "status": self.state.status,
            "modules": {},
            "updated_at": datetime.now().isoformat()
        }
        
        for module_name, module in self.state.modules.items():
            module_data = {
                "status": module.status,
                "stages": {},
                "convergence": None
            }
            
            for stage_name, stage in module.stages.items():
                module_data["stages"][stage_name] = {
                    "status": stage.status,
                    "started_at": stage.started_at,
                    "completed_at": stage.completed_at,
                    "output_file": stage.output_file
                }
            
            if module.convergence:
                module_data["convergence"] = {
                    "converged": module.convergence.converged,
                    "gate_a": module.convergence.gate_a_result,
                    "gate_b": module.convergence.gate_b_result,
                    "verdict": module.convergence.overall_verdict,
                    "file": module.convergence.convergence_file
                }
            
            progress_data["modules"][module_name] = module_data
        
        # 写入 stage_progress.json
        temp_file = progress_file.with_suffix(".tmp")
        temp_file.write_text(json.dumps(progress_data, indent=2, ensure_ascii=False))
        temp_file.rename(progress_file)
    
    def start_module(self, module_name: str):
        """启动模块"""
        self.state.start_module(module_name)
        self._save()
        logger.info(f"Module started: {module_name}")
    
    def update_stage(self, module_name: str, stage_name: str, 
                    status: str, output_file: Optional[str] = None):
        """更新阶段状态"""
        self.state.update_stage_progress(
            module_name=module_name,
            stage_name=stage_name,
            status=status,
            output_file=output_file
        )
        self._save()
        logger.info(f"Stage updated: {module_name}/{stage_name} -> {status}")
    
    def mark_converged(self, module_name: str, gate_a: str, gate_b: str,
                      verdict: str, convergence_file: str):
        """标记模块收敛"""
        self.state.mark_module_converged(
            module_name=module_name,
            gate_a=gate_a,
            gate_b=gate_b,
            verdict=verdict,
            convergence_file=convergence_file
        )
        self._save()
        logger.info(f"Module converged: {module_name} (verdict={verdict})")
    
    def complete_module(self, module_name: str):
        """完成模块"""
        self.state.complete_module(module_name)
        self._save()
        logger.info(f"Module completed: {module_name}")
    
    def add_supplementary_round(self, file_path: str):
        """添加补充轮次"""
        self.state.add_supplementary_round(file_path)
        self._save()
        logger.info(f"Supplementary round added: {self.state.supplementary_rounds}")
    
    def mark_completed(self):
        """标记 pipeline 完成"""
        # 检查所有模块是否完成
        for module_name, module in self.state.modules.items():
            if module.status != "completed":
                raise StateTransitionError(
                    f"Cannot complete pipeline: module {module_name} is {module.status}"
                )
        
        self.state.mark_completed()
        self._save()
        logger.info("Pipeline completed")
    
    def get_state(self) -> SolutionProPipelineState:
        """获取当前状态"""
        return self.state
    
    def get_module_state(self, module_name: str) -> Optional[ModuleState]:
        """获取模块状态"""
        return self.state.modules.get(module_name)


# 导出
__all__ = ["SolutionProStateManager", "StateTransitionError"]
