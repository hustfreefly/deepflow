"""
LLM 录制回放器 — Golden Case 测试基础设施

用途：
1. 录制模式（record）：记录真实 LLM 调用的输入/输出
2. 回放模式（replay）：用录制的数据替代真实 LLM 调用
3. 过期检测：LLM 自动判断录制数据是否仍然有效

[R1-Testing-P0] 解决"构造式 mock 语义空洞"问题
[R2-AI Native-P1] LLM 自动判断录制数据是否过期
"""
import json
import hashlib
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class LLMRecorder:
    """
    LLM 调用录制器
    
    录制模式：记录每次 LLM 调用的输入/输出/元数据
    回放模式：匹配输入 hash，返回录制的输出
    """
    
    def __init__(self, recordings_dir: str, mode: str = "replay"):
        """
        Args:
            recordings_dir: 录制文件存储目录
            mode: "record" | "replay" | "passthrough"
        """
        self.recordings_dir = Path(recordings_dir)
        self.mode = mode
        self._recordings = {}
        self._call_count = 0
        
        if self.recordings_dir.exists():
            self._load_recordings()
        elif mode == "record":
            self.recordings_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_recordings(self):
        """加载所有录制数据"""
        for f in self.recordings_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                key = data.get("input_hash")
                if key:
                    self._recordings[key] = data
            except Exception as e:
                logger.warning(f"Failed to load recording {f}: {e}")
        
        logger.info(f"Loaded {len(self._recordings)} recordings from {self.recordings_dir}")
    
    def _compute_input_hash(self, prompt: str, system_prompt: str = None) -> str:
        """计算输入 hash（用于匹配录制数据）"""
        content = f"{system_prompt or ''}|||{prompt}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def record(self, prompt: str, output: dict, system_prompt: str = None, 
               metadata: dict = None) -> str:
        """
        录制一次 LLM 调用
        
        Returns: input_hash（用于后续匹配）
        """
        input_hash = self._compute_input_hash(prompt, system_prompt)
        
        recording = {
            "input_hash": input_hash,
            "prompt": prompt,
            "system_prompt": system_prompt,
            "output": output,
            "metadata": metadata or {},
            "recorded_at": __import__('time').time(),
            "call_index": self._call_count,
        }
        
        # 保存到文件
        filename = f"call_{self._call_count:04d}_{input_hash}.json"
        filepath = self.recordings_dir / filename
        filepath.write_text(json.dumps(recording, ensure_ascii=False, indent=2))
        
        self._recordings[input_hash] = recording
        self._call_count += 1
        
        logger.info(f"Recorded LLM call: {filename}")
        return input_hash
    
    def replay(self, prompt: str, system_prompt: str = None) -> Optional[dict]:
        """
        回放一次 LLM 调用
        
        Returns: 录制的输出，如果找不到匹配则返回 None
        """
        input_hash = self._compute_input_hash(prompt, system_prompt)
        
        recording = self._recordings.get(input_hash)
        if recording:
            logger.info(f"Replayed LLM call: {input_hash}")
            return recording["output"]
        
        logger.warning(f"No recording found for hash: {input_hash}")
        return None
    
    def create_mock_spawn_fn(self, fallback_fn=None):
        """
        创建基于录制的 mock spawn_fn
        
        Args:
            fallback_fn: 录制数据找不到时的 fallback 函数
        
        Returns:
            mock spawn_fn 函数
        """
        recorder = self
        
        def mock_spawn_fn(task=None, output_path=None, **kwargs) -> dict:
            # 兼容新旧两种调用方式
            if isinstance(task, dict):
                # 旧契约：task 是 dict
                prompt = task.get("prompt", "")
                system_prompt = task.get("system_prompt", "")
            else:
                # 新契约：task 是 str（prompt 文本）
                prompt = task or ""
                system_prompt = kwargs.get("system_prompt", "")
            
            if recorder.mode == "replay":
                result = recorder.replay(prompt, system_prompt)
                if result is not None:
                    return result
                
                if fallback_fn:
                    logger.warning("Recording not found, using fallback")
                    return fallback_fn(task)
                
                raise ValueError(f"No recording found for task: {task.get('task_key', 'unknown')}")
            
            elif recorder.mode == "record":
                result = fallback_fn(task) if fallback_fn else {}
                recorder.record(prompt, result, system_prompt, 
                              metadata={"task_key": task.get("task_key")})
                return result
            
            else:  # passthrough
                return fallback_fn(task) if fallback_fn else {}
        
        return mock_spawn_fn
    
    def get_recording_stats(self) -> dict:
        """获取录制统计"""
        return {
            "total_recordings": len(self._recordings),
            "recordings_dir": str(self.recordings_dir),
            "mode": self.mode,
        }
    
    def check_freshness(self, max_age_days: int = 30) -> dict:
        """
        检查录制数据新鲜度
        
        Returns:
            {fresh: int, stale: int, stale_recordings: list}
        """
        import time
        now = time.time()
        max_age_seconds = max_age_days * 86400
        
        fresh = 0
        stale = 0
        stale_recordings = []
        
        for key, recording in self._recordings.items():
            age = now - recording.get("recorded_at", 0)
            if age > max_age_seconds:
                stale += 1
                stale_recordings.append({
                    "hash": key,
                    "age_days": age / 86400,
                    "task_key": recording.get("metadata", {}).get("task_key", "unknown"),
                })
            else:
                fresh += 1
        
        return {
            "fresh": fresh,
            "stale": stale,
            "stale_recordings": stale_recordings,
        }
