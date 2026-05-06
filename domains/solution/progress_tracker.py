#!/usr/bin/env python3
"""
进度跟踪模块
"""

import time
from typing import Dict, Any


class ProgressTracker:
    """跟踪Pro模式执行进度"""
    
    def __init__(self, blackboard, session_id: str = None):
        self.blackboard = blackboard
        self.session_id = session_id or getattr(blackboard, 'session_id', None) or getattr(blackboard, '_session_id', 'unknown')
        self.start_time = time.time()
    
    def update(self, stage_num: int, stage_name: str, status: str, agents: Dict = None):
        """
        更新进度
        
        Args:
            stage_num: 当前阶段号
            stage_name: 阶段名称
            status: pending/running/completed/failed
            agents: Agent状态字典（可选）
        """
        elapsed = time.time() - self.start_time
        
        # 估算剩余时间（基于58分钟总时长）
        total_estimated = 58 * 60  # 58分钟
        remaining = max(0, total_estimated - elapsed)
        
        progress = {
            "session_id": self.session_id,
            "mode": "pro",
            "current_stage": stage_num,
            "total_stages": 8,
            "stage_name": stage_name,
            "status": status,
            "agents": agents or {},
            "elapsed_sec": int(elapsed),
            "estimated_remaining_sec": int(remaining),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        
        self.blackboard.write("progress.json", progress)
        return progress
