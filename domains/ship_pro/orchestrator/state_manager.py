"""
Ship Pro V6 - State Manager

状态管理器：管理 pipeline_state.json（单一真相源）。
遵循契约笼子原则：
- Pydantic 契约定义状态结构
- State Machine 规则保护状态转换
- 原子写入保证一致性
"""
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import json
import logging
import tempfile
import os

logger = logging.getLogger(__name__)


class StageState(BaseModel):
    """单个阶段的状态"""
    status: str = Field(default="pending", description="状态: pending/running/completed/failed")
    started_at: Optional[str] = Field(default=None, description="开始时间")
    completed_at: Optional[str] = Field(default=None, description="完成时间")
    retry_count: int = Field(default=0, description="重试次数")
    updated_at: Optional[str] = Field(default=None, description="更新时间")


class PipelineState(BaseModel):
    """Pipeline 状态（单一真相源）"""
    
    run_id: str = Field(..., description="运行 ID")
    status: str = Field(default="pending", description="整体状态")
    
    # 各阶段状态
    stages: Dict[str, StageState] = Field(
        default_factory=lambda: {
            "planner": StageState(),
            "build": StageState(),
            "shipper": StageState(),
        }
    )
    
    # 元数据
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    # 可选字段
    fix_rounds: int = Field(default=0, description="修复轮次")
    max_fix_rounds: int = Field(default=2, description="最大修复轮次")


class StateTransitionError(Exception):
    """非法状态转换异常"""
    pass


class StateManager:
    """
    状态管理器
    
    职责：
    1. 管理 pipeline_state.json
    2. 状态转换验证（State Machine）
    3. Blackboard 读写
    """
    
    # State Machine 规则
    VALID_TRANSITIONS = {
        "pending": ["running"],
        "running": ["completed", "failed"],
        "completed": ["pending"],  # 只允许 fix_and_rerun 时回退
        "failed": ["running"],
    }
    
    def __init__(self, blackboard_path: Path):
        """
        初始化 StateManager
        
        Args:
            blackboard_path: Blackboard 目录路径
        """
        self.blackboard_path = Path(blackboard_path)
        self.state_file = self.blackboard_path / "pipeline_state.json"
        self.stages_dir = self.blackboard_path / "stages"
        self.stages_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载或初始化状态
        if self.state_file.exists():
            with open(self.state_file) as f:
                data = json.load(f)
                self.state = PipelineState(**data)
            logger.info(f"Loaded existing state: {self.state.run_id}")
        else:
            # 初始化新状态
            run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.state = PipelineState(run_id=run_id)
            self._save_state()
            logger.info(f"Initialized new state: {run_id}")
    
    def update_stage(self, stage_name: str, status: str):
        """
        更新阶段状态（带 State Machine 验证）
        
        Args:
            stage_name: 阶段名称
            status: 新状态
        
        Raises:
            StateTransitionError: 非法状态转换
        """
        if stage_name not in self.state.stages:
            raise ValueError(f"Unknown stage: {stage_name}")
        
        stage = self.state.stages[stage_name]
        current_status = stage.status
        
        # 验证状态转换
        if status not in self.VALID_TRANSITIONS.get(current_status, []):
            raise StateTransitionError(
                f"Illegal state transition: {stage_name} {current_status} → {status}"
            )
        
        # 更新状态
        stage.status = status
        stage.updated_at = datetime.now().isoformat()
        
        if status == "running" and not stage.started_at:
            stage.started_at = datetime.now().isoformat()
        elif status in ["completed", "failed"]:
            stage.completed_at = datetime.now().isoformat()
        
        # 更新整体状态
        self._update_overall_status()
        
        # 保存
        self._save_state()
        logger.info(f"Stage {stage_name}: {current_status} → {status}")
    
    def increment_retry(self, stage_name: str):
        """
        增加重试次数
        
        Args:
            stage_name: 阶段名称
        """
        if stage_name not in self.state.stages:
            raise ValueError(f"Unknown stage: {stage_name}")
        
        stage = self.state.stages[stage_name]
        stage.retry_count += 1
        self._save_state()
        logger.info(f"Stage {stage_name} retry count: {stage.retry_count}")
    
    def write_stage(self, stage_name: str, data: Dict[str, Any]):
        """
        写入阶段输出到 Blackboard
        
        Args:
            stage_name: 阶段名称
            data: 输出数据
        """
        output_file = self.stages_dir / f"{stage_name}.json"
        
        # 原子写入
        with tempfile.NamedTemporaryFile(mode='w', dir=self.stages_dir, delete=False, suffix='.tmp') as tmp:
            json.dump(data, tmp, indent=2, ensure_ascii=False)
            tmp_path = tmp.name
        
        try:
            os.rename(tmp_path, output_file)
            logger.info(f"Stage output written: {output_file}")
        except Exception as e:
            logger.error(f"Failed to write stage output: {e}")
            os.unlink(tmp_path)
            raise
    
    def read_stage(self, stage_name: str) -> Optional[Dict[str, Any]]:
        """
        读取阶段输出
        
        Args:
            stage_name: 阶段名称
        
        Returns:
            阶段输出数据，或 None
        """
        output_file = self.stages_dir / f"{stage_name}.json"
        
        if not output_file.exists():
            return None
        
        # 契约笼子：文件存在但读取失败 → raise，不吞异常
        with open(output_file) as f:
            return json.load(f)
    
    def _update_overall_status(self):
        """更新整体状态"""
        stages = self.state.stages
        
        # 如果所有阶段都完成，整体状态为 completed
        if all(s.status == "completed" for s in stages.values()):
            self.state.status = "completed"
        # 如果有任何阶段失败，整体状态为 failed
        elif any(s.status == "failed" for s in stages.values()):
            self.state.status = "failed"
        # 如果有任何阶段运行中，整体状态为 running
        elif any(s.status == "running" for s in stages.values()):
            self.state.status = "running"
        # 否则为 pending
        else:
            self.state.status = "pending"
        
        self.state.updated_at = datetime.now().isoformat()
    
    def _save_state(self):
        """保存状态（原子写入）"""
        with tempfile.NamedTemporaryFile(mode='w', dir=self.blackboard_path, delete=False, suffix='.tmp') as tmp:
            json.dump(self.state.model_dump(), tmp, indent=2, ensure_ascii=False)
            tmp_path = tmp.name
        
        try:
            os.rename(tmp_path, self.state_file)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            os.unlink(tmp_path)
            raise
