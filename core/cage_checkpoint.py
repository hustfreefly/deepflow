#!/usr/bin/env python3
"""
DeepFlow V2.0 - 笼子契约检查点管理器

核心原则：
1. 检查点格式必须符合数据契约
2. 支持从检查点恢复
3. 检查点存储路径由领域契约定义
"""

import os
import sys
import json
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime

sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')

from core.cage_loader import CageLoader


# ============================================================================
# 数据类定义
# ============================================================================

@dataclass
class CheckpointMetadata:
    """检查点元数据"""
    session_id: str
    domain: str
    checkpoint_id: str
    created_at: str  # ISO format timestamp
    iteration: int
    current_stage: str
    score: float
    pipeline_state: str  # RUNNING, CONVERGED, MAX_ITERATIONS, FAILED
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointMetadata":
        return cls(**data)


@dataclass
class CheckpointData:
    """检查点数据（符合数据契约）"""
    metadata: CheckpointMetadata
    stage_outputs: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "stage_outputs": self.stage_outputs,
            "context": self.context,
            "errors": self.errors
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointData":
        metadata = CheckpointMetadata.from_dict(data["metadata"])
        return cls(
            metadata=metadata,
            stage_outputs=data.get("stage_outputs", {}),
            context=data.get("context", {}),
            errors=data.get("errors", [])
        )


# ============================================================================
# 检查点管理器
# ============================================================================

class CageCheckpointManager:
    """
    笼子契约检查点管理器
    
    根据领域契约定义的路径存储和加载检查点
    """
    
    def __init__(self, cage_dir: str = None, base_dir: str = None):
        self.cage_dir = Path(cage_dir or "/Users/allen/.openclaw/workspace/.deepflow/cage")
        self.base_dir = Path(base_dir or "/Users/allen/.openclaw/workspace/.deepflow/blackboard")
        self.loader = CageLoader(cage_dir)
    
    def _get_checkpoint_dir(self, session_id: str) -> Path:
        """
        获取检查点目录
        
        Args:
            session_id: 会话 ID
            
        Returns:
            检查点目录路径
        """
        return self.base_dir / session_id / "checkpoints"
    
    def _get_checkpoint_path(self, session_id: str, checkpoint_id: str) -> Path:
        """
        获取检查点文件路径
        
        Args:
            session_id: 会话 ID
            checkpoint_id: 检查点 ID
            
        Returns:
            检查点文件路径
        """
        checkpoint_dir = self._get_checkpoint_dir(session_id)
        return checkpoint_dir / f"{checkpoint_id}.json"
    
    def save_checkpoint(
        self,
        session_id: str,
        domain: str,
        iteration: int,
        current_stage: str,
        score: float,
        pipeline_state: str,
        stage_outputs: Dict[str, Any],
        context: Dict[str, Any] = None,
        errors: List[str] = None
    ) -> Optional[str]:
        """
        保存检查点
        
        Args:
            session_id: 会话 ID
            domain: 领域名称
            iteration: 当前迭代次数
            current_stage: 当前阶段
            score: 当前分数
            pipeline_state: 流水线状态
            stage_outputs: 各阶段输出
            context: 上下文数据
            errors: 错误列表
            
        Returns:
            checkpoint_id 或 None（如果保存失败）
        """
        try:
            # 生成检查点 ID
            checkpoint_id = f"ckpt_{iteration:03d}_{int(time.time())}"
            
            # 创建元数据
            metadata = CheckpointMetadata(
                session_id=session_id,
                domain=domain,
                checkpoint_id=checkpoint_id,
                created_at=datetime.now().isoformat(),
                iteration=iteration,
                current_stage=current_stage,
                score=score,
                pipeline_state=pipeline_state
            )
            
            # 创建检查点数据
            checkpoint_data = CheckpointData(
                metadata=metadata,
                stage_outputs=stage_outputs,
                context=context or {},
                errors=errors or []
            )
            
            # 确保目录存在
            checkpoint_dir = self._get_checkpoint_dir(session_id)
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            checkpoint_path = self._get_checkpoint_path(session_id, checkpoint_id)
            with open(checkpoint_path, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data.to_dict(), f, indent=2, ensure_ascii=False)
            
            print(f"[CageCheckpoint] Saved checkpoint: {checkpoint_id}")
            return checkpoint_id
            
        except Exception as e:
            print(f"[CageCheckpoint] ERROR: Failed to save checkpoint: {e}")
            return None
    
    def load_checkpoint(self, session_id: str, checkpoint_id: str) -> Optional[CheckpointData]:
        """
        加载检查点
        
        Args:
            session_id: 会话 ID
            checkpoint_id: 检查点 ID
            
        Returns:
            CheckpointData 或 None
        """
        try:
            checkpoint_path = self._get_checkpoint_path(session_id, checkpoint_id)
            if not checkpoint_path.exists():
                print(f"[CageCheckpoint] WARNING: Checkpoint not found: {checkpoint_path}")
                return None
            
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            checkpoint_data = CheckpointData.from_dict(data)
            print(f"[CageCheckpoint] Loaded checkpoint: {checkpoint_id}")
            return checkpoint_data
            
        except Exception as e:
            print(f"[CageCheckpoint] ERROR: Failed to load checkpoint: {e}")
            return None
    
    def get_latest_checkpoint(self, session_id: str) -> Optional[CheckpointData]:
        """
        获取最新检查点
        
        Args:
            session_id: 会话 ID
            
        Returns:
            最新的 CheckpointData 或 None
        """
        try:
            checkpoint_dir = self._get_checkpoint_dir(session_id)
            if not checkpoint_dir.exists():
                return None
            
            # 查找所有检查点文件
            checkpoint_files = sorted(
                checkpoint_dir.glob("ckpt_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            if not checkpoint_files:
                return None
            
            # 加载最新的检查点
            latest_file = checkpoint_files[0]
            checkpoint_id = latest_file.stem
            
            return self.load_checkpoint(session_id, checkpoint_id)
            
        except Exception as e:
            print(f"[CageCheckpoint] ERROR: Failed to get latest checkpoint: {e}")
            return None
    
    def list_checkpoints(self, session_id: str) -> List[Dict[str, Any]]:
        """
        列出所有检查点
        
        Args:
            session_id: 会话 ID
            
        Returns:
            检查点元数据列表
        """
        try:
            checkpoint_dir = self._get_checkpoint_dir(session_id)
            if not checkpoint_dir.exists():
                return []
            
            checkpoints = []
            for checkpoint_file in sorted(checkpoint_dir.glob("ckpt_*.json")):
                try:
                    with open(checkpoint_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    checkpoints.append(data.get("metadata", {}))
                except Exception as e:
                    print(f"[CageCheckpoint] WARNING: Failed to read {checkpoint_file}: {e}")
            
            return checkpoints
            
        except Exception as e:
            print(f"[CageCheckpoint] ERROR: Failed to list checkpoints: {e}")
            return []
    
    def delete_checkpoint(self, session_id: str, checkpoint_id: str) -> bool:
        """
        删除检查点
        
        Args:
            session_id: 会话 ID
            checkpoint_id: 检查点 ID
            
        Returns:
            是否删除成功
        """
        try:
            checkpoint_path = self._get_checkpoint_path(session_id, checkpoint_id)
            if checkpoint_path.exists():
                checkpoint_path.unlink()
                print(f"[CageCheckpoint] Deleted checkpoint: {checkpoint_id}")
                return True
            else:
                print(f"[CageCheckpoint] WARNING: Checkpoint not found: {checkpoint_id}")
                return False
        except Exception as e:
            print(f"[CageCheckpoint] ERROR: Failed to delete checkpoint: {e}")
            return False
    
    def cleanup_old_checkpoints(self, session_id: str, retention_days: int = 7) -> int:
        """
        清理旧检查点
        
        Args:
            session_id: 会话 ID
            retention_days: 保留天数
            
        Returns:
            删除的检查点数量
        """
        try:
            checkpoint_dir = self._get_checkpoint_dir(session_id)
            if not checkpoint_dir.exists():
                return 0
            
            now = time.time()
            retention_seconds = retention_days * 24 * 3600
            deleted_count = 0
            
            for checkpoint_file in checkpoint_dir.glob("ckpt_*.json"):
                file_age = now - checkpoint_file.stat().st_mtime
                if file_age > retention_seconds:
                    checkpoint_file.unlink()
                    deleted_count += 1
            
            if deleted_count > 0:
                print(f"[CageCheckpoint] Cleaned up {deleted_count} old checkpoints")
            
            return deleted_count
            
        except Exception as e:
            print(f"[CageCheckpoint] ERROR: Failed to cleanup checkpoints: {e}")
            return 0
    
    def validate_checkpoint_schema(self, checkpoint_data: Dict[str, Any]) -> List[str]:
        """
        验证检查点数据是否符合契约 schema
        
        Args:
            checkpoint_data: 检查点数据
            
        Returns:
            错误列表
        """
        errors = []
        
        # 检查必需字段
        required_fields = ["metadata", "stage_outputs", "context", "errors"]
        for field_name in required_fields:
            if field_name not in checkpoint_data:
                errors.append(f"Missing required field: '{field_name}'")
        
        if errors:
            return errors
        
        # 验证 metadata
        metadata = checkpoint_data.get("metadata", {})
        metadata_required = ["session_id", "domain", "checkpoint_id", "created_at", 
                            "iteration", "current_stage", "score", "pipeline_state"]
        for field_name in metadata_required:
            if field_name not in metadata:
                errors.append(f"Missing metadata field: '{field_name}'")
        
        # 验证类型
        if "iteration" in metadata and not isinstance(metadata["iteration"], int):
            errors.append("metadata.iteration must be an integer")
        
        if "score" in metadata:
            score = metadata["score"]
            if not isinstance(score, (int, float)):
                errors.append("metadata.score must be a number")
            elif not (0 <= score <= 1):
                errors.append(f"metadata.score must be between 0 and 1, got {score}")
        
        if "pipeline_state" in metadata:
            valid_states = ["RUNNING", "CONVERGED", "MAX_ITERATIONS", "FAILED"]
            if metadata["pipeline_state"] not in valid_states:
                errors.append(f"metadata.pipeline_state must be one of {valid_states}")
        
        return errors


# ============================================================================
# 工具函数
# ============================================================================

def create_checkpoint_from_orchestrator_state(
    orchestrator_state: Dict[str, Any],
    checkpoint_manager: CageCheckpointManager
) -> Optional[str]:
    """
    从 Orchestrator 状态创建检查点
    
    Args:
        orchestrator_state: Orchestrator 的状态字典
        checkpoint_manager: 检查点管理器
        
    Returns:
        checkpoint_id 或 None
    """
    return checkpoint_manager.save_checkpoint(
        session_id=orchestrator_state.get("session_id", ""),
        domain=orchestrator_state.get("domain", ""),
        iteration=orchestrator_state.get("iteration", 0),
        current_stage=orchestrator_state.get("current_stage", ""),
        score=orchestrator_state.get("score", 0.0),
        pipeline_state=orchestrator_state.get("pipeline_state", "RUNNING"),
        stage_outputs=orchestrator_state.get("stage_outputs", {}),
        context=orchestrator_state.get("context", {}),
        errors=orchestrator_state.get("errors", [])
    )


def restore_orchestrator_state_from_checkpoint(
    checkpoint_data: CheckpointData
) -> Dict[str, Any]:
    """
    从检查点恢复 Orchestrator 状态
    
    Args:
        checkpoint_data: 检查点数据
        
    Returns:
        Orchestrator 状态字典
    """
    return {
        "session_id": checkpoint_data.metadata.session_id,
        "domain": checkpoint_data.metadata.domain,
        "iteration": checkpoint_data.metadata.iteration,
        "current_stage": checkpoint_data.metadata.current_stage,
        "score": checkpoint_data.metadata.score,
        "pipeline_state": checkpoint_data.metadata.pipeline_state,
        "stage_outputs": checkpoint_data.stage_outputs,
        "context": checkpoint_data.context,
        "errors": checkpoint_data.errors
    }


# ============================================================================
# 入口函数
# ============================================================================

if __name__ == "__main__":
    print("="*60)
    print("CAGE CHECKPOINT MANAGER TEST")
    print("="*60 + "\n")
    
    # 创建检查点管理器
    manager = CageCheckpointManager()
    
    # 测试保存检查点
    session_id = "investment_300604_sz_test_abc12345"
    checkpoint_id = manager.save_checkpoint(
        session_id=session_id,
        domain="investment",
        iteration=2,
        current_stage="research",
        score=0.85,
        pipeline_state="RUNNING",
        stage_outputs={
            "data_collection": {"success": True, "output": {"count": 3}},
            "search": {"success": True, "output": {"results": 10}}
        },
        context={"code": "300604.SZ", "name": "长川科技"},
        errors=[]
    )
    
    if checkpoint_id:
        print(f"\n✅ Checkpoint saved: {checkpoint_id}\n")
        
        # 测试加载检查点
        loaded = manager.load_checkpoint(session_id, checkpoint_id)
        if loaded:
            print(f"📄 Loaded checkpoint metadata:")
            print(f"   session_id: {loaded.metadata.session_id}")
            print(f"   iteration: {loaded.metadata.iteration}")
            print(f"   stage: {loaded.metadata.current_stage}")
            print(f"   score: {loaded.metadata.score}")
            print(f"   state: {loaded.metadata.pipeline_state}")
            print()
        
        # 测试验证 schema
        validation_errors = manager.validate_checkpoint_schema(loaded.to_dict())
        if validation_errors:
            print(f"❌ Validation errors:")
            for err in validation_errors:
                print(f"   - {err}")
        else:
            print(f"✅ Checkpoint schema validation passed\n")
        
        # 测试列出检查点
        checkpoints = manager.list_checkpoints(session_id)
        print(f"📋 Total checkpoints: {len(checkpoints)}\n")
        
        # 测试清理旧检查点
        cleaned = manager.cleanup_old_checkpoints(session_id, retention_days=0)
        print(f"🧹 Cleaned up {cleaned} checkpoints\n")
    
    print("="*60)
    print("✅ CAGE CHECKPOINT MANAGER TEST COMPLETED")
    print("="*60)
