"""
Ship Pro V7 - State Manager

State manager: manages pipeline_state.json (single source of truth).
V7 change: relaxed state transitions (warn instead of raise).
"""
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import json
import logging
import tempfile
import os

logger = logging.getLogger(__name__)


class StageState(BaseModel):
    """Stage state"""
    status: str = Field(default="pending", description="pending/running/completed/failed")
    started_at: Optional[str] = Field(default=None)
    completed_at: Optional[str] = Field(default=None)
    retry_count: int = Field(default=0)
    updated_at: Optional[str] = Field(default=None)


class PipelineState(BaseModel):
    """Pipeline state (single source of truth)"""
    run_id: str = Field(..., description="Run ID")
    status: str = Field(default="pending")
    stages: Dict[str, StageState] = Field(
        default_factory=lambda: {
            "planner": StageState(),
            "build": StageState(),
            "shipper": StageState(),
        }
    )
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    fix_rounds: int = Field(default=0)
    max_fix_rounds: int = Field(default=2)


class StateTransitionError(Exception):
    pass


class StateManager:
    """
    V7: State manager with relaxed transitions.
    - Same-state transitions are silently skipped
    - Unusual transitions log a warning instead of raising
    - Unknown stages are auto-created
    """

    VALID_TRANSITIONS = {
        "pending": ["running"],
        "running": ["completed", "failed"],
        "completed": ["pending"],
        "failed": ["running"],
    }

    def __init__(self, blackboard_path: Path):
        self.blackboard_path = Path(blackboard_path)
        self.state_file = self.blackboard_path / "pipeline_state.json"
        self.stages_dir = self.blackboard_path / "stages"
        self.stages_dir.mkdir(parents=True, exist_ok=True)

        if self.state_file.exists():
            with open(self.state_file) as f:
                data = json.load(f)
                self.state = PipelineState(**data)
            logger.info(f"Loaded existing state: {self.state.run_id}")
        else:
            run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.state = PipelineState(run_id=run_id)
            self._save_state()
            logger.info(f"Initialized new state: {run_id}")

    def update_stage(self, stage_name: str, status: str):
        """
        V7: Update stage status (relaxed mode).
        - Same state: skip silently
        - Unknown stage: auto-create
        - Invalid transition: warn, not raise
        """
        if stage_name not in self.state.stages:
            self.state.stages[stage_name] = StageState()
            logger.info(f"Auto-created stage: {stage_name}")

        stage = self.state.stages[stage_name]
        current_status = stage.status

        if current_status == status:
            logger.debug(f"Stage {stage_name} already {status}, skipping")
            return

        if status not in self.VALID_TRANSITIONS.get(current_status, []):
            logger.warning(
                f"Unusual transition: {stage_name} {current_status} -> {status} (allowed)"
            )

        stage.status = status
        stage.updated_at = datetime.now().isoformat()

        if status == "running" and not stage.started_at:
            stage.started_at = datetime.now().isoformat()
        elif status in ["completed", "failed"]:
            stage.completed_at = datetime.now().isoformat()

        self._update_overall_status()
        self._save_state()
        logger.info(f"Stage {stage_name}: {current_status} -> {status}")

    def increment_retry(self, stage_name: str):
        if stage_name not in self.state.stages:
            raise ValueError(f"Unknown stage: {stage_name}")
        stage = self.state.stages[stage_name]
        stage.retry_count += 1
        self._save_state()

    def write_stage(self, stage_name: str, data: Dict[str, Any]):
        output_file = self.stages_dir / f"{stage_name}.json"
        with tempfile.NamedTemporaryFile(
            mode='w', dir=self.stages_dir, delete=False, suffix='.tmp'
        ) as tmp:
            json.dump(data, tmp, indent=2, ensure_ascii=False)
            tmp_path = tmp.name
        try:
            os.rename(tmp_path, output_file)
            logger.info(f"Stage output written: {output_file}")
        except Exception as e:
            logger.error(f"Failed to write stage output: {e}")
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def read_stage(self, stage_name: str) -> Optional[Dict[str, Any]]:
        output_file = self.stages_dir / f"{stage_name}.json"
        if not output_file.exists():
            return None
        with open(output_file) as f:
            return json.load(f)

    def _update_overall_status(self):
        stages = self.state.stages
        if all(s.status == "completed" for s in stages.values()):
            self.state.status = "completed"
        elif any(s.status == "failed" for s in stages.values()):
            self.state.status = "failed"
        elif any(s.status == "running" for s in stages.values()):
            self.state.status = "running"
        else:
            self.state.status = "pending"
        self.state.updated_at = datetime.now().isoformat()

    def _save_state(self):
        with tempfile.NamedTemporaryFile(
            mode='w', dir=self.blackboard_path, delete=False, suffix='.tmp'
        ) as tmp:
            json.dump(self.state.model_dump(), tmp, indent=2, ensure_ascii=False)
            tmp_path = tmp.name
        try:
            os.rename(tmp_path, self.state_file)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
