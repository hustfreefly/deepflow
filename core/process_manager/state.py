"""
单源状态管理

解决 V37/V39 状态不一致问题：
- 之前：pipeline_state.json 和 .runs/*.run.json 双写 → 崩溃时死锁
- 现在：.runs/*.run.json 作为唯一真相源，pipeline_state 从 run.json 派生

契约笼方法：所有状态读取必须通过此模块，确保一致性。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .contracts import RunRecordContract
from .lifecycle import ModuleLifecycleManager


class SingleSourceStateManager:
    """
    单源状态管理器
    
    职责：
    - 从 .runs/*.run.json 派生模块状态
    - 提供统一的状态查询接口
    - 消除双写不一致问题
    """
    
    def __init__(self, session_dir: str | Path):
        self.session_dir = Path(session_dir)
        self.runs_dir = self.session_dir / ".runs"
        self.lifecycle = ModuleLifecycleManager(session_dir)
    
    def get_module_status(self, module: str) -> dict:
        """
        获取模块状态（从 .run.json 派生）
        
        Returns:
            {
                "status": "running" | "completed" | "failed" | "stalled",
                "run_id": "...",
                "attempt": N,
                "started_at": ...,
                "completed_at": ...,
            }
        """
        record = self.lifecycle._read_run(module)
        if not record:
            return {"status": "unknown", "run_id": None, "attempt": 0}
        
        # 验证契约
        try:
            RunRecordContract(**record)
        except Exception as e:
            # 契约验证失败，返回错误状态
            return {"status": "error", "error": str(e), "run_id": record.get("run_id")}
        
        return {
            "status": record.get("status", "unknown"),
            "run_id": record.get("run_id"),
            "attempt": record.get("attempt", 1),
            "started_at": record.get("started_at"),
            "completed_at": record.get("completed_at"),
            "last_heartbeat": record.get("last_heartbeat"),
        }
    
    def get_all_modules_status(self) -> dict:
        """
        获取所有模块状态
        
        Returns:
            {
                "planning": {...},
                "research": {...},
                "summary": {...},
            }
        """
        modules = ["planning", "research", "summary"]
        return {module: self.get_module_status(module) for module in modules}
    
    def is_module_completed(self, module: str) -> bool:
        """检查模块是否完成"""
        status = self.get_module_status(module)
        return status.get("status") == "completed"
    
    def is_module_stalled(self, module: str, threshold: int = 1800) -> bool:
        """检查模块是否 stall"""
        status = self.get_module_status(module)
        if status.get("status") != "running":
            return False
        
        import time
        last_heartbeat = status.get("last_heartbeat", 0)
        age = time.time() - last_heartbeat
        return age > threshold
    
    def get_pipeline_status(self) -> dict:
        """
        获取整个 pipeline 状态（从各模块状态派生）
        
        Returns:
            {
                "status": "running" | "completed" | "failed" | "stalled",
                "completed_modules": [...],
                "failed_modules": [...],
                "stalled_modules": [...],
            }
        """
        all_status = self.get_all_modules_status()
        
        completed = []
        failed = []
        stalled = []
        
        for module, status in all_status.items():
            if status.get("status") == "completed":
                completed.append(module)
            elif status.get("status") == "failed":
                failed.append(module)
            elif self.is_module_stalled(module):
                stalled.append(module)
        
        # 派生 pipeline 状态
        if failed:
            pipeline_status = "failed"
        elif stalled:
            pipeline_status = "stalled"
        elif len(completed) == 3:
            pipeline_status = "completed"
        else:
            pipeline_status = "running"
        
        return {
            "status": pipeline_status,
            "completed_modules": completed,
            "failed_modules": failed,
            "stalled_modules": stalled,
        }
