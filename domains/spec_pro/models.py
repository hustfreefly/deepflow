"""
Spec Pro 数据模型
=================

契约: cage/active/spec_pro_v2.0.yaml (L3)
纯数据结构，无业务逻辑。

所有 Living Spec、质量报告、路由建议等的类型定义。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import yaml
from pathlib import Path
import logging
logger = logging.getLogger(__name__)



def _read_spec_pro_version() -> str:
    """从 config/spec_pro.yaml 读取版本号"""
    try:
        config_path = Path(__file__).parent / "config" / "spec_pro.yaml"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config.get('component_version', '2.1.0')
    except Exception as e:
        logger.debug(f"version read: {e}")
    return '2.1.0'  # fallback


class QualityLevel(Enum):
    """需求质量等级"""
    S = "S"    # 90-100: 卓越
    A = "A"    # 75-89: 良好
    B = "B"    # 60-74: 可用
    C = "C"    # <60: 不足


class Scenario(Enum):
    """Spec Pro 场景"""
    GENESIS = "genesis"
    SUPPLEMENT = "supplement"
    REFINE = "refine"
    PIVOT = "pivot"


class DialogState(Enum):
    """对话状态机"""
    START = "start"
    PARSING = "parsing"
    COLLECTING = "collecting"
    ASKING = "asking"
    CONFIRMING = "confirming"
    REVISING = "revising"
    COMPLETED = "completed"
    KILLED = "killed"
    FAILED = "failed"


class QuestionType(Enum):
    """苏格拉底六类问题"""
    CLARIFICATION = "clarification"
    PROBE_ASSUMPTION = "probe_assumption"
    PROBE_EVIDENCE = "probe_evidence"
    ALTERNATIVE_VIEW = "alternative_view"
    IMPLICATION = "implication"
    META = "meta"


class RoundAction(Enum):
    """Orchestrator 每轮输出动作"""
    QUESTIONS = "questions"
    SUMMARY = "summary"
    PROPOSAL = "proposal"  # D5 停滞检测: 向用户提议 Living Spec 草案
    DONE = "done"
    ERROR = "error"
    SAFETY_STOP = "safety_stop"


@dataclass
class LivingSpec:
    """
    Living Spec — Spec Pro 的核心产出

    三层结构:
    - confirmed: 用户已确认的需求（权威来源）
    - inferred: AI 推断的需求（标注置信度，待确认）
    - guardrails: 三层边界（always_do / ask_first / never_do）
    """
    meta: Dict[str, Any] = field(default_factory=lambda: {
        "engine": "spec_pro",
        "version": _read_spec_pro_version(),
        "spec_version": 1,
        "scenario": "genesis",
        "created_at": "",
        "updated_at": "",
        "conversation_rounds": 0,
        "quality_score": 0,
        "quality_level": "C",
    })

    confirmed: Dict[str, Any] = field(default_factory=lambda: {
        "objective": "",
        "pain_points": [],
        "success_metrics": [],
        "users": [],
        "key_scenarios": [],
        "capabilities": {
            "always_do": [],
            "should_do": [],
            "never_do": [],
        },
        "quality_attributes": [],
        "constraints": {},
        "integration": {
            "existing_systems": [],
            "requirements": [],
        },
        "risks_and_assumptions": {
            "risks": [],
            "assumptions": [],
            "dependencies": [],
        },
    })

    inferred: List[Dict[str, Any]] = field(default_factory=list)

    guardrails: Dict[str, List[str]] = field(default_factory=lambda: {
        "always_do": [],
        "ask_first": [],
        "never_do": [],
    })

    route_recommendation: Optional[Dict[str, Any]] = None
    solution_pro_hints: Optional[Dict[str, Any]] = None
    user_directives: List[Dict[str, Any]] = field(default_factory=list)

    # 契约笼子（2026-07-05）：与 Pydantic 版本对齐，确保信息守恒
    # 权威定义：contracts/living_spec.py (Pydantic + 字段校验)
    # 本文件是运行时轻量级镜像，必须与 Pydantic 版本保持字段同步
    core_summary: str = ""                    # 核心需求摘要（≤5KB）
    narrative: str = ""                       # 完整用户需求叙述
    requirement_index: List[Dict[str, Any]] = field(default_factory=list)  # REQ-ID 追溯索引
    semantic_anchors: List[Dict[str, Any]] = field(default_factory=list)   # 不可变语义锚点



@dataclass
class DimensionScore:
    """单维度评分"""
    dimension: str
    name: str
    weight: float
    score: float          # 0-100
    reasoning: str
    missing_items: List[str] = field(default_factory=list)


@dataclass
class QualityReport:
    """质量评估报告"""
    overall_score: float   # 0-100
    level: QualityLevel
    dimensions: List[DimensionScore]
    top_missing: List[str]
    recommendation: str


@dataclass
class TrajectoryPoint:
    """质量轨迹中的一个点（每轮一条）"""
    round: int
    overall_score: float
    level: str
    dimension_scores: Dict[str, float]
    delta: float           # 与上一轮的分数差
    questions_asked: int
    inferences_validated: int


@dataclass
class ConversationEntry:
    """对话日志中的一条记录（每轮一条）"""
    round: int
    timestamp: str
    phase: str             # init | collecting | confirmation
    questions: List[Dict[str, str]]
    user_response: str     # 截断500字
    parsed_updates_summary: str
    quality_before: float
    quality_after: float
    quality_delta: float
    inferences_created: int
    inferences_confirmed: int
    inferences_rejected: int


@dataclass
class RouteRecommendation:
    """路由建议"""
    suggested_engine: str    # solution_pro | lightweight | direct_answer
    suggested_mode: str      # quick | standard | rigorous
    reasoning: str
    confidence: float        # 0.0-1.0
    complexity_score: float  # 0-100
    complexity_factors: List[str] = field(default_factory=list)


@dataclass
class HarnessReport:
    """Harness Output Guard 报告"""
    harness_version: str
    dimensions: Dict[str, Any]
    overall_score: float
    gates: Dict[str, str]    # spec_quality / inference_audit / trajectory_audit
    final_decision: str      # PASS | WARN | SOFT_BLOCK | HARD_BLOCK
    final_reasoning: str
    improvements: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ============================================================================
# 模式配置常量
# ============================================================================

MODE_CONFIG: Dict[str, Dict[str, Any]] = {
    "quick": {"max_rounds": 5, "threshold": 60},
    "standard": {"max_rounds": 10, "threshold": 75},
    "deep": {"max_rounds": 15, "threshold": 85},
}

# 7维度权重
DIMENSION_WEIGHTS: Dict[str, float] = {
    "objective": 0.20,
    "users": 0.15,
    "capabilities": 0.15,
    "quality_attributes": 0.15,
    "constraints": 0.15,
    "integration": 0.10,
    "risks": 0.10,
}

# Harness 5维度权重
HARNESS_DIMENSION_WEIGHTS: Dict[str, float] = {
    "clarity": 0.25,
    "completeness": 0.25,
    "executability": 0.20,
    "consistency": 0.15,
    "downstream_fitness": 0.15,
}

# Worker 超时
WORKER_TIMEOUT: Dict[str, int] = {
    "parse_worker": 180,
    "question_worker": 180,
    "response_worker": 180,
    "assess_worker": 180,
    "structure_worker": 180,
    "harness_worker": 240,
    "coordinator": 600,
}
