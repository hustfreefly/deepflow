"""
配置管理，动态加载 config/solution.yaml

Version: 2.0.0
Author: DeepFlow Solution Pro
Date: 2026-06-01
"""

"""
This file is part of pipeline (10-stage architecture).
uses MasterOrchestrator + PlanningOrchestrator + ResearchOrchestrator + SummaryOrchestrator.
Do not import this file for new workflows.
"""

"""Solution Pro 配置管理"""
import sys as _sys; _p=__import__('pathlib').Path(__file__).resolve(); _r=next((d for d in _p.parents if (d/'core'/'blackboard').is_dir()),None); _sys.path.insert(0,str(_r)) if _r and str(_r) not in _sys.path else None  # 契约笼子: 自动发现 .deepflow 根目录
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import yaml

from core.config.path_config import PathConfig


CURRENT_PIPELINE_STAGES = [
    {"num": 1, "name": "data_collection", "parallel": False, "timeout": 300, "agents": ["data_collection"]},
    {"num": 2, "name": "planning", "parallel": False, "timeout": 300, "agents": ["planning"]},
    {"num": 3, "name": "reviewers", "parallel": True, "timeout": 300, "agents": ["technical", "business", "risk"]},
    {"num": 4, "name": "research", "parallel": True, "timeout": 300, "agents": ["expert_1", "expert_2", "expert_3"]},
    {"num": 5, "name": "consolidator", "parallel": False, "timeout": 300, "agents": ["consolidator"]},
    {"num": 6, "name": "audit", "parallel": False, "timeout": 300, "agents": ["audit"]},
    {"num": 7, "name": "fix", "parallel": False, "timeout": 300, "agents": ["fix"]},
    {"num": 8, "name": "fixer_expert", "parallel": False, "timeout": 300, "agents": ["fixer_expert"]},
    {"num": 9, "name": "harness_final", "parallel": False, "timeout": 300, "agents": ["harness_final"]},
    {"num": 10, "name": "summarizer", "parallel": False, "timeout": 300, "agents": ["summarizer"]},
]


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
        return [dict(stage) for stage in CURRENT_PIPELINE_STAGES]
    
    def get_input_data(self) -> dict:
        """生成Input JSON数据（用于Blackboard）"""
        return {
            "session_id": self.session_id,
            "topic": self.topic,
            "constraints": self.constraints,
            "stakeholders": self.stakeholders,
            "solution_type": self.solution_type
        }


def load_solution_yaml_config() -> Dict[str, Any]:
    """
    加载 config/solution.yaml 配置
    
    Returns:
        dict: 完整的配置字典
    """
    config_path = Path(__file__).parent / "config" / "solution.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Solution config not found: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_pipeline_stages_from_config() -> List[str]:
    """
    从 config/solution.yaml 读取 pipeline stages 名称列表
    
    Returns:
        list[str]: stage 名称列表，如 ['data_collection', 'planning', 'research', ...]
    """
    config = load_solution_yaml_config()
    pipeline = config.get("pipeline", {})
    stages = pipeline.get("stages", [])
    return [s["name"] for s in stages if "name" in s]


def get_enabled_stages() -> List[str]:
    """Return the active fixed 10-stage Solution Pro pipeline."""
    stages = get_pipeline_stages_from_config()
    return stages or [stage["name"] for stage in CURRENT_PIPELINE_STAGES]


def get_total_timeout_from_config() -> int:
    """
    从 config/solution.yaml 计算所有 stage 的 timeout 总和（秒）
    
    Returns:
        int: 总 timeout（秒）
    """
    config = load_solution_yaml_config()
    pipeline = config.get("pipeline", {})
    stages = pipeline.get("stages", [])
    
    total = 0
    for stage in stages:
        stage_type = stage.get("type", "")
        workers = stage.get("workers", [])
        
        if stage_type == "parallel_workers":
            # 并行取最大 timeout
            if workers:
                total += max(w.get("timeout", 0) for w in workers)
        else:
            # 串行累加所有 worker timeout
            for w in workers:
                total += w.get("timeout", 0)
    
    return total
