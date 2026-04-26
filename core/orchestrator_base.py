#!/usr/bin/env python3
"""
DeepFlow V2.0 - 通用化 Pipeline Orchestrator 基类
领域无关的执行引擎，通过配置驱动适配不同场景
"""

import os
import sys
import json
import uuid
import time
import asyncio
import copy
import yaml
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List, Tuple, TypeVar, Generic
from enum import Enum, auto
from abc import ABC, abstractmethod

sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')


# ============================================================================
# 异常定义
# ============================================================================

class CircuitBreakerOpen(Exception):
    """熔断器触发 - 所有模型耗尽"""
    pass


class ContractViolation(Exception):
    """契约违反异常"""
    pass


class DomainConfigError(Exception):
    """领域配置错误"""
    pass


# ============================================================================
# 状态机定义
# ============================================================================

class PipelineState(Enum):
    """管线状态（通用）"""
    INIT = auto()
    RUNNING = auto()
    WAITING_AGENT = auto()
    CONVERGED = auto()
    FAILED = auto()
    TIMEOUT = auto()
    EXHAUSTED = auto()
    STALLED = auto()
    CIRCUIT_BREAKER = auto()


# ============================================================================
# 配置类定义
# ============================================================================

@dataclass
class ConvergenceConfig:
    """收敛检测配置（通用）"""
    min_iterations: int = 2
    max_iterations: int = 10
    target_score: float = 0.92
    stall_threshold: float = 0.02
    oscillation_threshold: int = 3
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ConvergenceConfig':
        # 只提取支持的字段，忽略额外字段（如 metrics）
        supported_keys = {'min_iterations', 'max_iterations', 'target_score', 
                         'stall_threshold', 'oscillation_threshold'}
        filtered_data = {k: v for k, v in data.items() if k in supported_keys}
        return cls(**filtered_data)


@dataclass
class ModelChainConfig:
    """模型链配置"""
    primary: str = "bailian/qwen3.5-plus"
    fallback: str = "bailian/kimi-k2.5"
    emergency: str = "kimi/kimi-code"
    max_fallback_rounds: int = 3
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ModelChainConfig':
        return cls(**data)


@dataclass
class ConcurrencyConfig:
    """并发配置"""
    max_parallel_workers: int = 3
    worker_timeout: int = 300
    orchestrator_timeout: int = 600
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ConcurrencyConfig':
        return cls(**data)


@dataclass
class WorkerConfig:
    """Worker 配置"""
    role: str
    prompt: Optional[str] = None  # 可选，可由领域配置或默认值提供
    timeout: int = 300
    model: Optional[str] = None
    count: int = 1
    parallel: bool = False
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'WorkerConfig':
        # prompt 是可选的，如果未提供则设为 None
        if 'prompt' not in data:
            data['prompt'] = None
        return cls(**data)


@dataclass
class StageConfig:
    """阶段配置"""
    name: str
    stage_type: str  # 'data_manager', 'parallel_workers', 'single_worker', 'custom'
    workers: Optional[List[WorkerConfig]] = None
    config: Optional[str] = None  # 外部配置文件路径
    custom_handler: Optional[str] = None  # 自定义处理函数名
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'StageConfig':
        workers = [WorkerConfig.from_dict(w) for w in data.get('workers', [])]
        return cls(
            name=data['name'],
            stage_type=data['type'],
            workers=workers,
            config=data.get('config'),
            custom_handler=data.get('custom_handler')
        )


@dataclass
class DomainConfig:
    """领域配置（核心）"""
    domain: str
    name: str
    description: str
    context_schema: Dict[str, Any]  # 定义该领域需要的上下文字段
    pipeline: List[StageConfig]
    convergence: ConvergenceConfig
    model_chain: ModelChainConfig
    concurrency: ConcurrencyConfig
    modes: Optional[Dict[str, Any]] = None  # Mode 系统配置（可选）
    
    @classmethod
    def load(cls, config_path: str) -> 'DomainConfig':
        """从 YAML 文件加载领域配置"""
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        return cls(
            domain=data['domain'],
            name=data['name'],
            description=data['description'],
            context_schema=data.get('context', {}).get('schema', {}),
            pipeline=[StageConfig.from_dict(s) for s in data['pipeline']['stages']],
            convergence=ConvergenceConfig.from_dict(data['convergence']),
            model_chain=ModelChainConfig.from_dict(data.get('model_chain', {})),
            concurrency=ConcurrencyConfig.from_dict(data.get('concurrency', {})),
            modes=data.get('modes')  # 加载 modes 配置（如果存在）
        )


# ============================================================================
# Prompt 加载器（通用化）
# ============================================================================

class PromptLoadError(Exception):
    """Prompt加载失败"""
    pass


class PromptLoader:
    """支持多领域的分层 Prompt 加载器"""
    
    def __init__(self, domain: str, base_path: Optional[str] = None):
        self.domain = domain
        self.base_path = Path(base_path or f"/Users/allen/.openclaw/workspace/.deepflow/prompts/{domain}")
        self.default_path = Path("/Users/allen/.openclaw/workspace/.deepflow/core/defaults")
        
        # 内置兜底 Prompt（极简版）
        self.default_prompts = self._load_default_prompts()
    
    def _load_default_prompts(self) -> Dict[str, str]:
        """加载内置默认 Prompt"""
        return {
            "core": """# DeepFlow Orchestrator Core (Default)

## 身份
你是 DeepFlow Orchestrator Agent。

## 强制契约
- 禁止 mock Worker
- 禁止跳过收敛检测
- 必须使用 Blackboard 数据流
- 所有 spawn 必须设 label
- quota 耗尽必须 fallback

## 紧急模式
当前加载的是默认兜底Prompt，功能受限。
""",
            "step_data": "## STEP: 数据采集\n执行数据收集流程。",
            "step_dispatch": "## STEP: Worker调度\n执行Worker Agent调度。",
        }
    
    def load_core(self) -> str:
        """加载 Core Layer（领域特定）"""
        return self._load_with_fallback(
            self.base_path / "orchestrator" / "core.md",
            "core"
        )
    
    def load_step(self, step_name: str) -> str:
        """加载 Execution Layer（按阶段）"""
        return self._load_with_fallback(
            self.base_path / "orchestrator" / f"{step_name}.md",
            step_name
        )
    
    def load_worker(self, role: str) -> str:
        """加载 Worker Prompt"""
        return self._load_with_fallback(
            self.base_path / "workers" / f"{role}.md",
            role
        )
    
    def load_reference(self, name: str) -> str:
        """加载 Reference Layer（按需，可选）"""
        try:
            ref_path = self.base_path / "reference" / f"{name}.md"
            if ref_path.exists():
                return ref_path.read_text(encoding="utf-8")
        except Exception:
            pass
        return ""
    
    def _load_with_fallback(self, file_path: Path, default_key: str) -> str:
        """
        三层防护加载：
        1. 尝试读取标准文件
        2. 尝试读取 .bak 备份
        3. 使用内存默认值
        """
        # 第1层：标准文件
        try:
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                if self._validate_metadata(content):
                    return content
        except Exception as e:
            print(f"⚠️ 读取 {file_path} 失败: {e}")
        
        # 第2层：备份文件
        bak_path = file_path.with_suffix(".md.bak")
        try:
            if bak_path.exists():
                return bak_path.read_text(encoding="utf-8")
        except:
            pass
        
        # 第3层：内存默认
        print(f"🚨 使用默认兜底Prompt: {default_key}")
        return self.default_prompts.get(default_key, f"# Default: {default_key}\n")
    
    def _validate_metadata(self, content: str) -> bool:
        """验证 Prompt 元数据"""
        # 检查必须包含的章节
        required = ["## 身份", "## 强制契约"]
        return all(section in content for section in required)


#

# ============================================================================
# 收敛检测器
# ============================================================================

class ConvergenceDetector:
    """通用收敛检测器"""
    
    def __init__(self, config: ConvergenceConfig):
        self.config = config
        self.scores: List[float] = []
    
    def add_score(self, score: float):
        self.scores.append(score)
    
    def check(self) -> Tuple[bool, str]:
        """
        收敛检测
        
        Returns:
            (是否收敛, 原因)
        """
        scores = self.scores
        
        # 最少迭代次数
        if len(scores) < self.config.min_iterations:
            return False, f"至少 {self.config.min_iterations} 轮才能收敛 (当前 {len(scores)})"
        
        # 最大迭代次数
        if len(scores) >= self.config.max_iterations:
            return True, f"达到最大迭代次数 ({self.config.max_iterations})"
        
        current_score = scores[-1]
        
        # 高分快速收敛
        if current_score >= 0.95:
            return True, f"分数 ≥ 0.95 ({current_score:.2%})"
        
        # 目标分数 + 提升停滞
        if len(scores) >= 2:
            prev_score = scores[-2]
            improvement = current_score - prev_score
            
            if (current_score >= self.config.target_score and 
                abs(improvement) < self.config.stall_threshold):
                return True, f"达目标分 ({current_score:.2%}) 且提升停滞 (Δ{improvement:+.2%})"
        
        # 震荡检测
        if len(scores) >= self.config.oscillation_threshold:
            recent = scores[-self.config.oscillation_threshold:]
            if max(recent) - min(recent) < 0.02:
                return True, f"检测到震荡 (最近{self.config.oscillation_threshold}轮波动 < 0.02)"
        
        return False, f"继续迭代 (当前 {current_score:.2%})"


# ============================================================================
# 模型链（Fallback 机制）
# ============================================================================

class ModelChain:
    """三级模型 Fallback 链"""
    
    def __init__(self, config: ModelChainConfig):
        self.config = config
        self.fallback_chain = [config.primary, config.fallback, config.emergency]
    
    async def call(self, prompt: str, timeout: int = 300) -> Dict[str, Any]:
        """
        调用模型链，自动处理 Fallback
        
        Raises:
            CircuitBreakerOpen: 所有模型耗尽时触发
        """
        last_error = None
        
        for round_num in range(self.config.max_fallback_rounds):
            for model in self.fallback_chain:
                try:
                    result = await self._call_single(model, prompt, timeout)
                    return {
                        "success": True,
                        "result": result,
                        "model_used": model,
                        "fallback_count": round_num
                    }
                except Exception as e:
                    last_error = e
                    error_msg = str(e).lower()
                    
                    # 可恢复错误：继续 fallback
                    if any(kw in error_msg for kw in ["quota", "rate_limit", "timeout", "network"]):
                        print(f"⚠️ Model {model} failed (recoverable): {e}")
                        continue
                    # 不可恢复错误：立即失败
                    else:
                        print(f"❌ Model {model} failed (fatal): {e}")
                        raise
        
        # 所有模型耗尽
        raise CircuitBreakerOpen(f"All models exhausted after {self.config.max_fallback_rounds} rounds. Last error: {last_error}")
    
    async def _call_single(self, model: str, prompt: str, timeout: int) -> str:
        """单次模型调用"""
        from openclaw import sessions_spawn
        
        # 契约检查：禁止 mock
        if "mock" in prompt.lower() and "禁止" not in prompt.lower():
            raise ContractViolation("Mock detected in prompt - contract violation")
        
        result = sessions_spawn(
            runtime="subagent",
            mode="run",
            label=f"orchestrator_{model.replace('/', '_')}",
            task=prompt,
            timeout_seconds=timeout,
            model=model,
        )
        return result


# ============================================================================
# 上下文管理
# ============================================================================

@dataclass
class ExecutionContext:
    """执行上下文（通用）"""
    session_id: str
    domain: str
    domain_config: DomainConfig
    user_context: Dict[str, Any]  # 用户提供的领域特定上下文
    
    # 运行时状态
    current_stage: int = 0
    current_iteration: int = 0
    scores: List[float] = field(default_factory=list)
    stage_outputs: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "domain": self.domain,
            "current_stage": self.current_stage,
            "current_iteration": self.current_iteration,
            "scores": self.scores,
            **self.user_context
        }


# ============================================================================
# 基类定义（核心）
# ============================================================================

class BaseOrchestrator(ABC):
    """
    Pipeline Orchestrator 抽象基类
    
    子类需要实现：
    - _execute_stage(): 阶段执行逻辑
    - _extract_score(): 从结果中提取分数
    - _build_result(): 构建最终结果
    """
    
    def __init__(self, domain: str, user_context: Dict[str, Any]):
        """
        Args:
            domain: 领域标识（如 'investment', 'code'）
            user_context: 用户提供的领域特定上下文
        """
        self.domain = domain
        self.user_context = user_context
        
        # 加载领域配置
        config_path = f"/Users/allen/.openclaw/workspace/.deepflow/domains/{domain}.yaml"
        self.domain_config = DomainConfig.load(config_path)
        
        # 生成 session_id
        self.session_id = self._generate_session_id()
        
        # 初始化组件
        self.loader = PromptLoader(domain)
        self.models = ModelChain(self.domain_config.model_chain)
        self.convergence = ConvergenceDetector(self.domain_config.convergence)
        self.semaphore = asyncio.Semaphore(self.domain_config.concurrency.max_parallel_workers)
        
        # 执行上下文
        self.context = ExecutionContext(
            session_id=self.session_id,
            domain=domain,
            domain_config=self.domain_config,
            user_context=user_context
        )
        
        # 状态机
        self.state = PipelineState.INIT
        
        print(f"[Orchestrator] Domain: {domain}")
        print(f"[Orchestrator] Session: {self.session_id}")
        print(f"[Orchestrator] State: {self.state.name}")
    
    def _generate_session_id(self) -> str:
        """生成 session_id（可由子类覆盖）"""
        return f"{self.domain}_{uuid.uuid4().hex[:8]}_{int(time.time())}"
    
    def build_prompt(self, stage_name: str, additional_context: Dict = None) -> str:
        """
        动态组装 Prompt
        
        Args:
            stage_name: 阶段名称（如 'step1_data', 'step3_dispatch'）
            additional_context: 额外上下文
        """
        parts = []
        
        # Layer 1: Core
        parts.append(self.loader.load_core())
        
        # Layer 2: Execution (阶段特定)
        parts.append(self.loader.load_step(stage_name))
        
        # Layer 3: 动态上下文
        context = self.context.to_dict()
        if additional_context:
            context.update(additional_context)
        
        parts.append(f"\n## 当前上下文\n```json\n{json.dumps(context, indent=2, ensure_ascii=False)}\n```\n")
        
        return "\n\n".join(parts)
    
    @abstractmethod
    async def _execute_stage(self, stage: StageConfig) -> Dict[str, Any]:
        """
        执行单个阶段（子类必须实现）
        
        Args:
            stage: 阶段配置
            
        Returns:
            {"success": bool, "output": any, "error": str}
        """
        pass
    
    @abstractmethod
    def _extract_score(self, result: Any) -> float:
        """
        从阶段结果中提取分数（子类必须实现）
        
        Args:
            result: 阶段输出
            
        Returns:
            0.0-1.0 的分数
        """
        pass
    
    @abstractmethod
    def _build_result(self, **kwargs) -> Dict[str, Any]:
        """
        构建最终结果（子类必须实现）
        """
        pass
    
    async def run(self) -> Dict[str, Any]:
        """
        主执行流程 - 通用管线状态机
        """
        self.state = PipelineState.RUNNING
        
        try:
            # 遍历 pipeline 中的每个 stage
            for stage_idx, stage in enumerate(self.domain_config.pipeline):
                self.context.current_stage = stage_idx
                
                print(f"\n{'='*60}")
                print(f"STAGE {stage_idx + 1}/{len(self.domain_config.pipeline)}: {stage.name}")
                print(f"Type: {stage.stage_type}")
                print(f"{'='*60}")
                
                # 执行阶段
                result = await self._execute_stage(stage)
                
                if not result.get("success"):
                    self.state = PipelineState.FAILED
                    return self._build_result(error=result.get("error"))
                
                # 保存阶段输出
                self.context.stage_outputs[stage.name] = result.get("output")
                
                # 如果是迭代阶段，处理收敛检测
                if stage.stage_type == "iterative":
                    score = self._extract_score(result.get("output"))
                    self.context.scores.append(score)
                    self.convergence.add_score(score)
                    
                    converged, reason = self.convergence.check()
                    print(f"  Score: {score:.2%}, Converged: {converged} ({reason})")
                    
                    if converged:
                        self.state = PipelineState.CONVERGED
                        return self._build_result(
                            iterations=self.context.current_iteration,
                            final_score=score,
                            convergence_reason=reason
                        )
            
            # 所有阶段完成但未收敛
            self.state = PipelineState.STALLED
            return self._build_result(
                iterations=self.context.current_iteration,
                final_score=self.context.scores[-1] if self.context.scores else 0,
                convergence_reason="pipeline_completed_without_convergence"
            )
            
        except CircuitBreakerOpen as e:
            self.state = PipelineState.CIRCUIT_BREAKER
            return self._build_result(error=str(e))
        except asyncio.TimeoutError:
            self.state = PipelineState.TIMEOUT
            return self._build_result(error="Pipeline timeout")
        except Exception as e:
            self.state = PipelineState.FAILED
            import traceback
            traceback.print_exc()
            return self._build_result(error=str(e))


# ============================================================================
# 工具函数
# ============================================================================

def validate_context(domain_config: DomainConfig, user_context: Dict[str, Any]) -> bool:
    """
    验证用户提供的上下文是否符合领域 schema
    
    Args:
        domain_config: 领域配置
        user_context: 用户上下文
        
    Returns:
        是否通过验证
    """
    required_fields = domain_config.context_schema.get("required", [])
    for field in required_fields:
        if field not in user_context:
            raise DomainConfigError(f"Missing required context field: {field}")
    return True


# ============================================================================
# 入口函数
# ============================================================================

def run_orchestrator(domain: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    通用入口函数
    
    Args:
        domain: 领域标识
        context: 领域特定上下文
        
    Returns:
        执行结果
    """
    # 动态导入领域特定的 Orchestrator
    try:
        module_name = f"domains.{domain}.orchestrator"
        module = __import__(module_name, fromlist=["DomainOrchestrator"])
        OrchestratorClass = module.DomainOrchestrator
    except ImportError:
        raise DomainConfigError(f"Unknown domain: {domain}. No orchestrator found at {module_name}")
    
    # 创建实例并运行
    orchestrator = OrchestratorClass(context)
    return asyncio.run(orchestrator.run())


if __name__ == "__main__":
    # 测试基类导入
    print("✅ orchestrator_base.py loaded successfully")
    print(f"Available classes: DomainConfig, BaseOrchestrator, PromptLoader, ModelChain, ConvergenceDetector")
