#!/usr/bin/env python3
"""
DeepFlow V2.0 - 检查点管理器
负责保存、加载和恢复管线执行状态
"""

import os
import sys
import json
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from core.config.path_config import PathConfig

sys.path.insert(0, str(PathConfig.resolve().base_dir))


# ============================================================================
# 数据类定义
# ============================================================================

@dataclass
class Checkpoint:
    """检查点数据"""
    session_id: str
    stage: str
    timestamp: str
    state: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Checkpoint':
        return cls(**data)


@dataclass
class PipelineState:
    """管线状态（用于恢复）"""
    session_id: str
    current_stage: int = 0
    current_iteration: int = 0
    scores: List[float] = field(default_factory=list)
    stage_outputs: Dict[str, Any] = field(default_factory=dict)
    blackboard_path: str = ""
    last_checkpoint_time: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PipelineState':
        return cls(**data)


# ============================================================================
# 检查点管理器
# ============================================================================

class CheckpointManager:
    """
    检查点管理器
    
    功能：
    - 保存检查点到 checkpoints/{session_id}/{stage}.json
    - 加载最近的检查点
    - 从检查点恢复管线状态
    - 清理过期检查点
    """
    
    def __init__(self, base_dir: str = None):
        """
        Args:
            base_dir: 检查点根目录，默认为 .deepflow/checkpoints/
        """
        self.base_dir = Path(base_dir or PathConfig.resolve().base_dir / "checkpoints")
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_session_dir(self, session_id: str) -> Path:
        """获取会话检查点目录"""
        session_dir = self.base_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir
    
    def save_checkpoint(self, session_id: str, stage: str, state: dict):
        """
        保存检查点
        
        Args:
            session_id: 会话 ID
            stage: 阶段名称
            state: 状态数据（包含当前管线状态）
        """
        session_dir = self._get_session_dir(session_id)
        checkpoint_path = session_dir / f"{stage}.json"
        
        checkpoint = Checkpoint(
            session_id=session_id,
            stage=stage,
            timestamp=datetime.now().isoformat(),
            state=state
        )
        
        try:
            with open(checkpoint_path, 'w', encoding='utf-8') as f:
                json.dump(checkpoint.to_dict(), f, indent=2, ensure_ascii=False)
            print(f"💾 Checkpoint saved: {checkpoint_path}")
        except Exception as e:
            print(f"⚠️ Failed to save checkpoint: {e}")
            raise
    
    def load_checkpoint(self, session_id: str, stage: str = None) -> Optional[Checkpoint]:
        """
        加载检查点
        
        Args:
            session_id: 会话 ID
            stage: 阶段名称（可选，不指定则加载最近的检查点）
            
        Returns:
            Checkpoint 对象，如果不存在则返回 None
        """
        session_dir = self.base_dir / session_id
        
        if not session_dir.exists():
            return None
        
        if stage:
            # 加载指定阶段的检查点
            checkpoint_path = session_dir / f"{stage}.json"
            if not checkpoint_path.exists():
                return None
            return self._load_checkpoint_file(checkpoint_path)
        else:
            # 加载最近的检查点（按时间排序）
            checkpoints = list(session_dir.glob("*.json"))
            if not checkpoints:
                return None
            
            # 按修改时间排序，取最新的
            latest_checkpoint = max(checkpoints, key=lambda p: p.stat().st_mtime)
            return self._load_checkpoint_file(latest_checkpoint)
    
    def _load_checkpoint_file(self, path: Path) -> Optional[Checkpoint]:
        """从文件加载检查点"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return Checkpoint.from_dict(data)
        except Exception as e:
            print(f"⚠️ Failed to load checkpoint {path}: {e}")
            return None
    
    def resume_from_checkpoint(self, session_id: str) -> Optional[PipelineState]:
        """
        从检查点恢复管线状态
        
        Args:
            session_id: 会话 ID
            
        Returns:
            PipelineState 对象，如果不存在检查点则返回 None
        """
        checkpoint = self.load_checkpoint(session_id)
        
        if not checkpoint:
            print(f"ℹ️ No checkpoint found for session: {session_id}")
            return None
        
        # 从检查点状态中提取 PipelineState
        state_data = checkpoint.state
        
        pipeline_state = PipelineState(
            session_id=session_id,
            current_stage=state_data.get("current_stage", 0),
            current_iteration=state_data.get("current_iteration", 0),
            scores=state_data.get("scores", []),
            stage_outputs=state_data.get("stage_outputs", {}),
            blackboard_path=state_data.get("blackboard_path", ""),
            last_checkpoint_time=checkpoint.timestamp
        )
        
        print(f"🔄 Resumed from checkpoint: stage={checkpoint.stage}, "
              f"iteration={pipeline_state.current_iteration}, "
              f"time={checkpoint.timestamp}")
        
        return pipeline_state
    
    def list_checkpoints(self, session_id: str = None) -> List[Dict[str, Any]]:
        """
        列出所有检查点
        
        Args:
            session_id: 会话 ID（可选，不指定则列出所有会话）
            
        Returns:
            检查点信息列表
        """
        checkpoints = []
        
        if session_id:
            session_dirs = [self.base_dir / session_id]
        else:
            session_dirs = [d for d in self.base_dir.iterdir() if d.is_dir()]
        
        for session_dir in session_dirs:
            if not session_dir.exists():
                continue
            
            for checkpoint_file in sorted(session_dir.glob("*.json")):
                checkpoint = self._load_checkpoint_file(checkpoint_file)
                if checkpoint:
                    checkpoints.append({
                        "session_id": checkpoint.session_id,
                        "stage": checkpoint.stage,
                        "timestamp": checkpoint.timestamp,
                        "file": str(checkpoint_file)
                    })
        
        return checkpoints
    
    def delete_checkpoint(self, session_id: str, stage: str) -> bool:
        """
        删除指定检查点
        
        Args:
            session_id: 会话 ID
            stage: 阶段名称
            
        Returns:
            是否成功删除
        """
        checkpoint_path = self.base_dir / session_id / f"{stage}.json"
        
        if checkpoint_path.exists():
            try:
                checkpoint_path.unlink()
                print(f"🗑️ Deleted checkpoint: {checkpoint_path}")
                return True
            except Exception as e:
                print(f"⚠️ Failed to delete checkpoint: {e}")
                return False
        
        return False
    
    def cleanup_old_checkpoints(self, retention_days: int = 7):
        """
        清理过期检查点
        
        Args:
            retention_days: 保留天数，默认 7 天
        """
        cutoff_time = datetime.now() - timedelta(days=retention_days)
        deleted_count = 0
        
        for session_dir in self.base_dir.iterdir():
            if not session_dir.is_dir():
                continue
            
            for checkpoint_file in session_dir.glob("*.json"):
                try:
                    mtime = datetime.fromtimestamp(checkpoint_file.stat().st_mtime)
                    if mtime < cutoff_time:
                        checkpoint_file.unlink()
                        deleted_count += 1
                        print(f"🗑️ Deleted old checkpoint: {checkpoint_file}")
                except Exception as e:
                    print(f"⚠️ Failed to process {checkpoint_file}: {e}")
        
        print(f"🧹 Cleaned up {deleted_count} old checkpoints")
    
    def get_checkpoint_summary(self, session_id: str) -> Dict[str, Any]:
        """
        获取会话的检查点摘要
        
        Args:
            session_id: 会话 ID
            
        Returns:
            摘要信息
        """
        checkpoints = self.list_checkpoints(session_id)
        
        if not checkpoints:
            return {"session_id": session_id, "checkpoints": [], "total": 0}
        
        return {
            "session_id": session_id,
            "checkpoints": checkpoints,
            "total": len(checkpoints),
            "latest_stage": checkpoints[-1]["stage"],
            "latest_timestamp": checkpoints[-1]["timestamp"]
        }


# ============================================================================
# 工具函数
# ============================================================================

def create_checkpoint_from_orchestrator(orchestrator, stage: str) -> dict:
    """
    从 Orchestrator 实例创建检查点状态
    
    Args:
        orchestrator: BaseOrchestrator 实例
        stage: 阶段名称
        
    Returns:
        状态字典
    """
    return {
        "current_stage": orchestrator.context.current_stage,
        "current_iteration": orchestrator.context.current_iteration,
        "scores": orchestrator.context.scores,
        "stage_outputs": orchestrator.context.stage_outputs,
        "blackboard_path": fstr(PathConfig.resolve().base_dir / "blackboard/{orchestrator.session_id}/"),
        "state": orchestrator.state.name if hasattr(orchestrator, 'state') else "UNKNOWN"
    }


# ============================================================================
# 入口函数
# ============================================================================

if __name__ == "__main__":
    # 测试检查点管理器
    manager = CheckpointManager()
    
    # 模拟保存检查点
    test_state = {
        "current_stage": 2,
        "current_iteration": 1,
        "scores": [0.75, 0.82],
        "stage_outputs": {
            "data_collection": {"status": "completed"},
            "search": {"status": "completed"}
        },
        "blackboard_path": "/test/blackboard/"
    }
    
    manager.save_checkpoint("test_session_001", "stage_2_search", test_state)
    
    # 加载检查点
    checkpoint = manager.load_checkpoint("test_session_001", "stage_2_search")
    if checkpoint:
        print(f"\nLoaded checkpoint:")
        print(f"  Stage: {checkpoint.stage}")
        print(f"  Timestamp: {checkpoint.timestamp}")
        print(f"  State: {json.dumps(checkpoint.state, indent=2)}")
    
    # 恢复管线状态
    pipeline_state = manager.resume_from_checkpoint("test_session_001")
    if pipeline_state:
        print(f"\nResumed pipeline state:")
        print(f"  Current stage: {pipeline_state.current_stage}")
        print(f"  Current iteration: {pipeline_state.current_iteration}")
        print(f"  Scores: {pipeline_state.scores}")
    
    # 列出所有检查点
    all_checkpoints = manager.list_checkpoints()
    print(f"\nAll checkpoints: {len(all_checkpoints)}")
    
    # 清理过期检查点
    manager.cleanup_old_checkpoints(retention_days=7)
