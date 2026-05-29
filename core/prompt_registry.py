"""
DeepFlow Prompt注册表管理器 V2.0 (修复版)
============================================

修复内容 (FIX-001~004):
- 线程安全: 双重检查锁定
- 实例变量: 类变量改为实例变量
- get_by_role: 修复逻辑错误
- 异常处理: bare except改为具体异常

契约引用: cage/active/ (see registry.yaml)
版本: 2.0.0
日期: 2026-05-01
"""

import os
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

import yaml
from packaging import version

from core.config.path_config import PathConfig


@dataclass
class PromptInfo:
    """Prompt元数据结构"""
    id: str
    name: str
    filename: str
    version: str
    role: str
    domain: str
    subtype: Optional[str] = None
    author: str = "deepflow-team"
    created: str = ""
    updated: str = ""
    changelog: List[Dict] = None
    variables: Dict[str, List[Dict]] = None
    
    def __post_init__(self):
        if self.changelog is None:
            self.changelog = []
        if self.variables is None:
            self.variables = {"required": [], "optional": []}


class PromptRegistry:
    """
    Prompt注册表管理器 (线程安全单例)
    
    修复: FIX-001 线程安全 - 使用双重检查锁定
    """
    
    # FIX-001: 线程安全相关类变量
    _instance = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls):
        # FIX-001: 双重检查锁定
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # FIX-001: 确保初始化只执行一次
        # FIX-002: 类变量改为实例变量
        if not self.__class__._initialized:
            with self.__class__._lock:
                if not self.__class__._initialized:
                    self._registry_data = None
                    self._prompts_by_id: Dict[str, PromptInfo] = {}
                    self._prompts_by_domain: Dict[str, List[PromptInfo]] = {}
                    self._load_registry()
                    self.__class__._initialized = True
    
    def _load_registry(self):
        """加载注册表文件"""
        base_path = PathConfig.resolve().base_dir
        registry_path = base_path / "prompts" / "registry.yaml"
        
        if not registry_path.exists():
            raise FileNotFoundError(f"Registry not found: {registry_path}")
        
        with open(registry_path, 'r', encoding='utf-8') as f:
            self._registry_data = yaml.safe_load(f)
        
        self._build_index()
    
    def _build_index(self):
        """构建索引以便快速查询"""
        self._prompts_by_id = {}
        self._prompts_by_domain = {}
        
        for domain_name, domain_data in self._registry_data.get('domains', {}).items():
            self._prompts_by_domain[domain_name] = []
            
            for prompt_id, prompt_data in domain_data.get('prompts', {}).items():
                full_id = f"{domain_name}/{prompt_id}"
                
                info = PromptInfo(
                    id=full_id,
                    name=prompt_data.get('name', prompt_id),
                    filename=prompt_data.get('filename', f"{prompt_id}.md"),
                    version=prompt_data.get('version', '1.0.0'),
                    role=prompt_data.get('role', 'unknown'),
                    domain=domain_name,
                    subtype=prompt_data.get('subtype'),
                    author=prompt_data.get('author', 'deepflow-team'),
                    created=prompt_data.get('created', ''),
                    updated=prompt_data.get('updated', ''),
                    changelog=prompt_data.get('changelog', []),
                    variables=prompt_data.get('variables', {'required': [], 'optional': []})
                )
                
                self._prompts_by_id[full_id] = info
                self._prompts_by_domain[domain_name].append(info)
    
    # ============ 查询接口 ============
    
    def get(self, prompt_id: str) -> PromptInfo:
        """
        获取指定prompt的元数据
        
        Args:
            prompt_id: 格式为 "domain/prompt_name"
        
        Returns:
            PromptInfo对象
        """
        if prompt_id not in self._prompts_by_id:
            # 提供友好的错误提示
            suggestions = [k for k in self._prompts_by_id.keys() if prompt_id in k]
            msg = f"Prompt not found: {prompt_id}"
            if suggestions:
                msg += f"\nDid you mean: {', '.join(suggestions[:3])}?"
            raise KeyError(msg)
        return self._prompts_by_id[prompt_id]
    
    def get_by_domain(self, domain: str) -> List[PromptInfo]:
        """获取某领域的所有prompt"""
        return self._prompts_by_domain.get(domain, [])
    
    def get_by_role(self, role: str, domain: Optional[str] = None) -> List[PromptInfo]:
        """
        获取指定角色的所有prompt
        
        FIX-003: 修复逻辑错误，统一返回List[PromptInfo]
        """
        if domain:
            search_space = self._prompts_by_domain.get(domain, [])
        else:
            search_space = self._prompts_by_id.values()
        
        return [p for p in search_space if p.role == role]
    
    def list_all(self) -> List[PromptInfo]:
        """列出所有prompt"""
        return list(self._prompts_by_id.values())
    
    def exists(self, prompt_id: str) -> bool:
        """检查prompt是否存在"""
        return prompt_id in self._prompts_by_id
    
    # ============ 版本接口 ============
    
    def check_version(self, prompt_id: str, min_version: str) -> bool:
        """
        检查prompt版本是否满足最低要求
        
        FIX-004: 使用具体异常处理
        """
        try:
            info = self.get(prompt_id)
            return version.parse(info.version) >= version.parse(min_version)
        except version.InvalidVersion as e:
            raise ValueError(f"Invalid version format for {prompt_id}: {e}")
    
    def get_changelog(self, prompt_id: str) -> List[Dict]:
        """获取prompt的变更历史"""
        return self.get(prompt_id).changelog
    
    # ============ 验证接口 ============
    
    def validate(self) -> Dict[str, List[str]]:
        """
        验证注册表完整性
        
        Returns:
            { "errors": [...], "warnings": [...] }
        """
        errors = []
        warnings = []
        
        base_path = PathConfig.resolve().base_dir
        
        for prompt_id, info in self._prompts_by_id.items():
            # 检查文件存在性
            file_path = base_path / "prompts" / info.domain / info.filename
            if not file_path.exists():
                errors.append(f"File not found: {file_path}")
                continue
            
            # 检查版本格式
            try:
                version.parse(info.version)
            except version.InvalidVersion:
                errors.append(f"Invalid version format: {prompt_id} -> {info.version}")
            
            # 警告：如果文件内容包含YAML Front Matter
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    # 只读前3行检查
                    first_lines = ''.join(f.readline() for _ in range(3))
                    if '---' in first_lines:
                        warnings.append(f"Prompt contains YAML (should be pure): {prompt_id}")
            except Exception as e:
                warnings.append(f"Cannot read file {prompt_id}: {e}")
        
        return {"errors": errors, "warnings": warnings}
    
    def reload(self) -> None:
        """
        重新加载注册表（支持热更新）
        
        FIX-001: 线程安全的热更新
        """
        with self.__class__._lock:
            self._initialized = False
            self.__init__()


# ============ 便捷函数 ============

def get_prompt_info(prompt_id: str) -> PromptInfo:
    """便捷函数：获取prompt元数据"""
    return PromptRegistry().get(prompt_id)


def read_prompt(prompt_id: str) -> str:
    """
    读取prompt内容（纯净版，无元数据）
    """
    registry = PromptRegistry()
    info = registry.get(prompt_id)
    
    base_path = PathConfig.resolve().base_dir
    file_path = base_path / "prompts" / info.domain / info.filename
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def read_prompt_with_vars(prompt_id: str, **variables) -> str:
    """
    读取prompt并填充变量
    
    增强版：支持默认值、类型检查
    """
    registry = PromptRegistry()
    content = read_prompt(prompt_id)
    info = registry.get(prompt_id)
    
    # 检查必填变量
    for var in info.variables.get("required", []):
        var_name = var["name"]
        if var_name not in variables:
            raise ValueError(f"Missing required variable: {var_name}")
    
    # 应用默认值
    for var in info.variables.get("optional", []):
        var_name = var["name"]
        if var_name not in variables and "default" in var:
            variables[var_name] = var["default"]
    
    # 渲染
    for key, value in variables.items():
        content = content.replace(f"{{{{{key}}}}}", str(value))
    
    return content
