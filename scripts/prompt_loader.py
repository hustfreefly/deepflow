"""
Cage-based Prompt Loader
从契约定义加载分层Prompt
"""

import yaml
from pathlib import Path


class CagePromptLoader:
    """契约驱动的Prompt加载器"""
    
    def __init__(self, domain: str):
        self.domain = domain
        self.base_path = Path(f"/Users/allen/.openclaw/workspace/.deepflow")
        self.contract = self._load_contract()
        self.core_cache = None  # Core Layer缓存
    
    def _load_contract(self) -> dict:
        """加载Prompt分层契约"""
        contract_path = self.base_path / "cage" / "prompt_layers.yaml"
        with open(contract_path) as f:
            return yaml.safe_load(f)
    
    def load_core(self) -> str:
        """
        加载Core Layer Prompt
        
        Returns:
            Core Prompt内容字符串
        """
        if self.core_cache:
            return self.core_cache
        
        core_config = self.contract['layers']['core']
        core_file = self.base_path / core_config['file']
        
        if not core_file.exists():
            raise FileNotFoundError(f"Core prompt not found: {core_file}")
        
        with open(core_file, 'r', encoding='utf-8') as f:
            self.core_cache = f.read()
        
        return self.core_cache
    
    def load_step(self, step_name: str) -> str:
        """
        加载指定Step的Prompt
        
        Args:
            step_name: Step名称 (data_collection, search, worker_dispatch)
            
        Returns:
            Step Prompt内容字符串
        """
        steps = self.contract['layers']['steps']
        
        for step in steps:
            if step['name'] == step_name:
                step_file = self.base_path / step['file']
                
                if not step_file.exists():
                    raise FileNotFoundError(f"Step prompt not found: {step_file}")
                
                with open(step_file, 'r', encoding='utf-8') as f:
                    return f.read()
        
        raise ValueError(f"Step '{step_name}' not found in contract")
    
    def get_next_step(self, current_step: str) -> str:
        """
        根据当前Step获取下一个Step名称
        
        Args:
            current_step: 当前Step名称
            
        Returns:
            下一个Step名称，如果是最后一个则返回None
        """
        steps = self.contract['layers']['steps']
        
        for i, step in enumerate(steps):
            if step['name'] == current_step:
                if i + 1 < len(steps):
                    return steps[i + 1]['name']
                else:
                    return None
        
        raise ValueError(f"Step '{current_step}' not found in contract")
    
    def get_completion_signal(self, step_name: str) -> str:
        """
        获取指定Step的完成信号
        
        Args:
            step_name: Step名称
            
        Returns:
            完成信号字符串
        """
        steps = self.contract['layers']['steps']
        
        for step in steps:
            if step['name'] == step_name:
                return step.get('completion_signal', '')
        
        raise ValueError(f"Step '{step_name}' not found in contract")
    
    def get_worker_config(self, worker_type: str) -> dict:
        """
        获取Worker配置
        
        Args:
            worker_type: Worker类型 (researcher, auditor)
            
        Returns:
            Worker配置字典
        """
        workers = self.contract.get('workers', {})
        
        if worker_type not in workers:
            raise ValueError(f"Worker type '{worker_type}' not found in contract")
        
        return workers[worker_type]
    
    def get_convergence_rules(self) -> dict:
        """
        获取收敛规则
        
        Returns:
            收敛规则字典
        """
        return self.contract.get('convergence', {})
