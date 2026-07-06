"""
DeepFlow 统一入口模块
支持多领域，契约驱动
"""

import sys
import importlib
from typing import Dict, Any, Optional
from dataclasses import dataclass

from core.config.path_config import PathConfig
from core.quality.entry_harness import EntryHarness

sys.path.insert(0, str(PathConfig.resolve().base_dir))

from core.cage.cage_loader import CageLoader
from core.cage.cage_validator import CageValidator


@dataclass
class DomainRegistry:
    """领域注册信息"""
    module: str
    class_name: str
    required_context: list


class UnifiedEntry:
    """
    DeepFlow 统一入口类
    
    使用方式:
        entry = UnifiedEntry()
        result = entry.run(domain="solution_pro", topic="设计一个智能物流系统", solution_type="architecture")
    """
    
    def __init__(self):
        """初始化统一入口"""
        self.loader = CageLoader()
        self.validator = CageValidator()
        self.domains = self._register_domains()
    
    def _register_domains(self) -> Dict[str, DomainRegistry]:
        """注册所有支持领域"""
        return {
            "solution_pro": DomainRegistry(
                module="domains.solution_pro.master_orchestrator",
                class_name="MasterOrchestrator",
                required_context=["topic"]
            ),
            # 预留扩展
            "code": DomainRegistry(
                module="domains.code",
                class_name="CodeOrchestrator",
                required_context=["file_path"]
            ),
            "general": DomainRegistry(
                module="domains.general",
                class_name="GeneralOrchestrator",
                required_context=["topic"]
            ),
            "research_pro": DomainRegistry(
                module="domains.research_pro.orchestrator",
                class_name="ResearchProOrchestrator",
                required_context=["query"]
            )
        }
    
    def list_domains(self) -> list:
        """列出所有支持的领域"""
        return list(self.domains.keys())
    
    def validate_context(self, domain: str, context: Dict[str, Any]) -> bool:
        """验证上下文是否符合领域要求"""
        domain_info = self.domains.get(domain)
        if not domain_info:
            raise ValueError(f"Unknown domain: {domain}. Supported: {self.list_domains()}")
        
        missing = []
        for field in domain_info.required_context:
            if field not in context:
                missing.append(field)
        
        if missing:
            raise ValueError(f"Domain '{domain}' requires: {missing}. Got: {list(context.keys())}")
        
        return True
    
    def run(self, domain: str, spawn_fn=None, **context) -> Dict[str, Any]:
        """
        统一运行入口（使用 EntryHarness）

        Args:
            domain: 领域标识
            spawn_fn: 注入的 spawn 函数（主Agent提供）
            **context: 领域特定上下文

        Returns:
            执行结果
        """
        # 1. 验证领域
        if domain not in self.domains:
            raise ValueError(f"Unknown domain: {domain}. Supported: {self.list_domains()}")

        # 2. 验证上下文
        self.validate_context(domain, context)

        # 3. 使用 EntryHarness 启动管线
        harness = EntryHarness()
        orchestrator = harness.validate_and_start(domain, context, spawn_fn)

        # 4. 执行管线
        result = orchestrator.run_pipeline()

        # 5. 添加元数据
        result["domain"] = domain
        result["entry_type"] = "unified"

        return result
    
    def run_legacy(self, domain: str, spawn_fn=None, **context) -> Dict[str, Any]:
        """
        传统运行入口（向后兼容）

        直接加载领域 Orchestrator 并运行，不使用 EntryHarness。
        适用于需要精细控制的场景。

        Args:
            domain: 领域标识
            spawn_fn: 注入的 spawn 函数
            **context: 领域特定上下文

        Returns:
            执行结果
        """
        # 1. 验证领域
        if domain not in self.domains:
            raise ValueError(f"Unknown domain: {domain}. Supported: {self.list_domains()}")

        # 2. 验证上下文
        self.validate_context(domain, context)

        # 3. 动态加载领域 Orchestrator
        domain_info = self.domains[domain]

        try:
            module = importlib.import_module(domain_info.module)
            OrchestratorClass = getattr(module, domain_info.class_name)
        except (ImportError, AttributeError) as e:
            raise RuntimeError(f"Failed to load orchestrator for domain '{domain}': {e}")

        # 4. 验证 spawn_fn
        if spawn_fn is None:
            raise RuntimeError(
                "spawn_fn 未注入：必须在主Agent环境中运行，"
                "或通过 spawn_fn 参数注入 sessions_spawn 工具。"
            )

        # 5. 创建实例并运行（注入 spawn_fn）
        orchestrator = OrchestratorClass(spawn_fn=spawn_fn)
        result = orchestrator.run(context)

        # 6. 添加元数据
        result["domain"] = domain
        result["entry_type"] = "unified_legacy"

        return result


# ============================================================================
# 便捷函数
# ============================================================================

def run(domain: str, spawn_fn=None, **context) -> Dict[str, Any]:
    """便捷函数：快速运行指定领域（使用 EntryHarness）"""
    entry = UnifiedEntry()
    return entry.run(domain, spawn_fn=spawn_fn, **context)


def run_legacy(domain: str, spawn_fn=None, **context) -> Dict[str, Any]:
    """便捷函数：使用传统方式运行指定领域"""
    entry = UnifiedEntry()
    return entry.run_legacy(domain, spawn_fn=spawn_fn, **context)


if __name__ == "__main__":
    main()
