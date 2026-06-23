"""
进度跟踪器，动态计算 timeout

Version: 2.1.0
Author: DeepFlow Solution Pro
Date: 2026-06-01
"""

#!/usr/bin/env python3
"""
进度跟踪模块
"""

import time
from typing import Dict, Any
import logging
logger = logging.getLogger(__name__)


DEFAULT_TOTAL_STAGES = 10


class ProgressTracker:
    """跟踪Pro模式执行进度"""
    
    def __init__(self, blackboard, session_id: str = None):
        self.blackboard = blackboard
        self.session_id = session_id or getattr(blackboard, 'session_id', None) or getattr(blackboard, '_session_id', 'unknown')
        self.start_time = time.time()
    
    def update(self, stage_num: int, stage_name: str, status: str, agents: Dict = None, total_stages: int = None):
        """
        更新进度
        
        Args:
            stage_num: 当前阶段号
            stage_name: 阶段名称
            status: pending/running/completed/failed
            agents: Agent状态字典（可选）
        """
        elapsed = time.time() - self.start_time
        
        # 动态计算总时长（从 config/solution.yaml 读取 timeout 总和）
        try:
            from domains.solution_pro.config import get_total_timeout_from_config
            total_estimated = get_total_timeout_from_config()
        except (ImportError, FileNotFoundError, Exception):
            # Fallback: 使用配置中的 stage timeout 总和
            total_estimated = 3480  # 58分钟 = 3480秒
        
        remaining = max(0, total_estimated - elapsed)
        
        resolved_total_stages = total_stages or self._resolve_total_stages()

        progress = {
            "session_id": self.session_id,
            "mode": "pro",
            "current_stage": stage_num,
            "total_stages": resolved_total_stages,
            "stage_name": stage_name,
            "status": status,
            "agents": agents or {},
            "elapsed_sec": int(elapsed),
            "estimated_remaining_sec": int(remaining),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        
        self.blackboard.write("progress.json", progress)
        return progress

    def _resolve_total_stages(self) -> int:
        """Resolve current Solution Pro stage count from config with a stable fallback."""
        try:
            from domains.solution_pro.config import get_enabled_stages
            stages = get_enabled_stages()
            if stages:
                return len(stages)
        except (ImportError, FileNotFoundError, AttributeError, TypeError) as e:
            logger.debug(f"resolve total stages: {e}")
        return DEFAULT_TOTAL_STAGES
