"""
Blackboard 管理器，统一路径注册表（STAGE_PATH_REGISTRY）

Version: 2.1.0
Author: DeepFlow Solution Pro
Date: 2026-06-01
"""

"""Blackboard 管理 - 中心化写入（符合契约C）"""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

from core.config.path_config import PathConfig


# ============================================================================
# 路径注册表（唯一事实源）
# 所有 stage 文件路径必须从这里获取，禁止自行拼接
# ============================================================================
STAGE_PATH_REGISTRY = {
    "data_collection": "data/collection.json",
    "structured_requirements": "data/structured_requirements.json",
    "frozen_spec": "data/frozen_spec.json",
    "requirements_traceability_matrix": "requirements_traceability_matrix.json",
    "planning": "stages/planning.json",
    "reviewer_technical": "stages/reviewer_technical.json",
    "reviewer_business": "stages/reviewer_business.json",
    "reviewer_risk": "stages/reviewer_risk.json",
    "research_expert_1": "stages/research_expert_1.json",
    "research_expert_2": "stages/research_expert_2.json",
    "research_expert_3": "stages/research_expert_3.json",
    "design": "stages/design.json",
    "audit": "stages/audit.json",
    "fix": "stages/fix.json",
    "fixer_expert": "stages/fixer_expert.json",
    "consolidator": "stages/consolidator.json",
    "harness_final": "stages/harness_final.json",
    "summarizer": "stages/summarizer.json",
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


class BlackboardManager:
    """
    Blackboard 管理中心化写入
    
    契约C要求：
    - 子Agent返回JSON（不直接写入文件）
    - 主Agent统一调用 _save_to_blackboard() 写入
    """
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        try:
            config = PathConfig.resolve()
            self.base_path = config.get_blackboard_path(session_id)
            self.base_path.mkdir(parents=True, exist_ok=True)
        except (ValueError, RuntimeError) as e:
            raise RuntimeError(f"Failed to initialize blackboard for session {session_id}: {e}")
        
        # 创建stages子目录
        (self.base_path / "stages").mkdir(exist_ok=True)
    
    def get_stage_path(self, stage_name: str) -> Path:
        """
        获取 stage 文件的完整路径（从注册表获取）
        
        Args:
            stage_name: stage 名称，如 'planning', 'audit'
        
        Returns:
            Path: 完整路径
        
        Raises:
            ValueError: stage 名称不在注册表中
        """
        if stage_name not in STAGE_PATH_REGISTRY:
            raise ValueError(
                f"Unknown stage: {stage_name}. "
                f"Available: {list(STAGE_PATH_REGISTRY.keys())}"
            )
        return self.base_path / STAGE_PATH_REGISTRY[stage_name]
    
    def write_stage(self, stage_name: str, data: dict) -> Path:
        """
        写入 stage 输出（从注册表获取路径）
        
        Args:
            stage_name: stage 名称
            data: stage 输出数据
        
        Returns:
            Path: 写入的文件路径
        """
        path = self.get_stage_path(stage_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
    
    def read_stage(self, stage_name: str) -> Optional[dict]:
        """
        读取 stage 输出（从注册表获取路径）
        
        Args:
            stage_name: stage 名称
        
        Returns:
            dict | None: stage 数据，不存在时返回 None
        """
        path = self.get_stage_path(stage_name)
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    
    def list_all_stages(self) -> List[str]:
        """
        列出所有已写入的 stage 名称
        
        Returns:
            list[str]: stage 名称列表
        """
        return [
            name for name, rel_path in STAGE_PATH_REGISTRY.items()
            if (self.base_path / rel_path).exists()
        ]

    def write_input(self, data: dict) -> Path:
        """写入输入数据"""
        path = self.base_path / "input_plan.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
    
    def write_stage_output(self, stage_num: int, stage_name: str, agent_name: str, data: dict) -> Path:
        """写入Stage输出（中心化写入）"""
        filename = f"stage_{stage_num:02d}_{agent_name}_output.json"
        path = self.base_path / "stages" / filename
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
    
    def read_stage_output(self, stage_num: int, agent_name: str) -> Optional[dict]:
        """读取Stage输出"""
        filename = f"stage_{stage_num:02d}_{agent_name}_output.json"
        path = self.base_path / "stages" / filename
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    
    def write_progress(self, current_stage: int, status: str, message: str = "") -> Path:
        """更新进度"""
        progress = {
            "session_id": self.session_id,
            "current_stage": current_stage,
            "total_stages": len(PIPELINE_STAGES),
            "status": status,
            "message": message,
            "updated_at": datetime.now().isoformat()
        }
        path = self.base_path / "progress.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
        return path
    
    def write_final_result(self, result: dict) -> Path:
        """写入最终结果"""
        path = self.base_path / "final_result.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return path
    
    def list_outputs(self) -> list:
        """列出所有输出文件"""
        stages_dir = self.base_path / "stages"
        if stages_dir.exists():
            return [f.name for f in stages_dir.glob("*.json")]
        return []
