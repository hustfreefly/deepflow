"""Blackboard 管理 - 中心化写入（符合契约C）"""
import json
from pathlib import Path
from typing import Dict, Any, Optional

from core.config.path_config import PathConfig


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
            "total_stages": 8,
            "status": status,
            "message": message,
            "updated_at": str(Path().stat().st_mtime if Path().exists() else "")
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