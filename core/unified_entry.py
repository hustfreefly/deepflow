"""
DeepFlow 统一入口模块
支持多领域，契约驱动
"""

import sys
import importlib
from typing import Dict, Any, Optional
from dataclasses import dataclass

sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')

from core.cage_loader import CageLoader
from core.cage_validator import CageValidator


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
        result = entry.run(domain="investment", code="300604.SZ", name="长川科技")
    """
    
    def __init__(self):
        """初始化统一入口"""
        self.loader = CageLoader()
        self.validator = CageValidator()
        self.domains = self._register_domains()
    
    def _register_domains(self) -> Dict[str, DomainRegistry]:
        """注册所有支持领域"""
        # 硬编码领域注册（后续可从契约文件加载）
        return {
            "investment": DomainRegistry(
                module="domains.investment",
                class_name="InvestmentOrchestrator",
                required_context=["code", "name"]
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
    
    def run(self, domain: str, **context) -> Dict[str, Any]:
        """
        统一运行入口
        
        Args:
            domain: 领域标识
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
        
        # 4. 获取 sessions_spawn 函数（关键修复）
        spawn_fn = self._get_spawn_fn()
        
        if spawn_fn is None:
            raise RuntimeError(
                "sessions_spawn 不可用：必须在主Agent环境中运行。"
            )
        
        # 5. 创建实例并运行（注入 spawn_fn）
        orchestrator = OrchestratorClass(spawn_fn=spawn_fn)
        result = orchestrator.run(context)
        
        # 6. 添加元数据
        result["domain"] = domain
        result["entry_type"] = "unified"
        
        return result
    
    def _get_spawn_fn(self):
        """
        获取 sessions_spawn 函数
        
        优先级：
        1. 全局命名空间中的 sessions_spawn（主Agent工具调用）
        2. openclaw 模块中的 sessions_spawn（SDK）
        3. None（不可用）
        """
        import sys
        import inspect
        
        # 优先级 1：尝试从全局命名空间获取（主Agent环境）
        if 'sessions_spawn' in globals():
            return globals()['sessions_spawn']
        
        # 优先级 2：尝试从调用者作用域获取
        frame = inspect.currentframe()
        while frame:
            if 'sessions_spawn' in frame.f_globals:
                return frame.f_globals['sessions_spawn']
            frame = frame.f_back
        
        # 优先级 3：尝试 import openclaw
        try:
            from openclaw import sessions_spawn
            return sessions_spawn
        except ImportError:
            pass
        
        return None


# ============================================================================
# 便捷函数
# ============================================================================

def run(domain: str, **context) -> Dict[str, Any]:
    """便捷函数：快速运行指定领域"""
    entry = UnifiedEntry()
    return entry.run(domain, **context)


def list_domains() -> list:
    """便捷函数：列出支持的领域"""
    entry = UnifiedEntry()
    return entry.list_domains()


if __name__ == "__main__":
    main()
