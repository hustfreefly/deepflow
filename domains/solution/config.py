"""Solution Pro 配置管理"""
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional

from core.config.path_config import PathConfig


@dataclass
class SolutionConfig:
    """Solution Pro 任务配置"""
    session_id: str
    topic: str
    constraints: List[str]
    stakeholders: List[str]
    solution_type: str = "architecture"
    
    # Blackboard路径
    @property
    def blackboard_path(self) -> Path:
        try:
            config = PathConfig.resolve()
            return config.get_blackboard_path(self.session_id)
        except (ValueError, RuntimeError) as e:
            raise RuntimeError(f"Failed to resolve blackboard path for session {self.session_id}: {e}")
    
    # Stage配置
    @property
    def stages(self) -> List[dict]:
        return [
            {"num": 1, "name": "planner", "parallel": False, "timeout": 600, "agents": ["planner"]},
            {"num": 2, "name": "reviewers", "parallel": True, "timeout": 600, "agents": ["reviewer_completeness", "reviewer_architecture", "reviewer_feasibility"]},
            {"num": 3, "name": "fixer_planner", "parallel": False, "timeout": 600, "agents": ["fixer_planner"]},
            {"num": 4, "name": "researchers", "parallel": True, "timeout": 900, "agents": ["researcher_tech", "researcher_practice", "researcher_risk"]},
            {"num": 5, "name": "consolidator", "parallel": False, "timeout": 600, "agents": ["consolidator"]},
            {"num": 6, "name": "auditors", "parallel": True, "timeout": 900, "agents": ["auditor_completeness", "auditor_architecture", "auditor_risk"]},
            {"num": 7, "name": "fixer_expert", "parallel": False, "timeout": 900, "agents": ["fixer_expert"]},
            {"num": 8, "name": "summarizer", "parallel": False, "timeout": 600, "agents": ["summarizer"]},
        ]
    
    def get_input_data(self) -> dict:
        """生成Input JSON数据（用于Blackboard）"""
        return {
            "session_id": self.session_id,
            "topic": self.topic,
            "constraints": self.constraints,
            "stakeholders": self.stakeholders,
            "solution_type": self.solution_type
        }