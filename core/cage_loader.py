#!/usr/bin/env python3
"""
DeepFlow V2.0 - 笼子契约加载器
从 YAML 文件加载领域契约、阶段契约、Worker 契约和收敛规则
"""

import os
import sys
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')


# ============================================================================
# 数据类定义
# ============================================================================

@dataclass
class DomainContract:
    """领域契约"""
    cage_version: str
    domain: str
    interface: Dict[str, Any] = field(default_factory=dict)
    behavior: Dict[str, Any] = field(default_factory=dict)
    exceptions: Dict[str, Any] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def stages(self) -> List[str]:
        """获取阶段列表"""
        return self.behavior.get("stages", {}).get("required_order", [])
    
    @property
    def convergence(self) -> Dict[str, Any]:
        """获取收敛配置"""
        return self.behavior.get("convergence", {})
    
    @property
    def workers(self) -> Dict[str, Any]:
        """获取 Worker 配置"""
        return self.behavior.get("workers", {})


@dataclass
class StageContract:
    """阶段契约"""
    stage: str
    domain: str
    cage_version: str
    interface: Dict[str, Any] = field(default_factory=dict)
    behavior: Dict[str, Any] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def timeout(self) -> int:
        """获取超时时间"""
        return self.behavior.get("timeout", 120)
    
    @property
    def retry_config(self) -> Dict[str, Any]:
        """获取重试配置"""
        return self.behavior.get("retry", {})
    
    @property
    def output_schema(self) -> Dict[str, Any]:
        """获取输出 schema"""
        return self.interface.get("output", {}).get("schema", {})


@dataclass
class WorkerContract:
    """Worker 契约"""
    worker: str
    domain: str
    cage_version: str
    roles: List[str] = field(default_factory=list)
    interface: Dict[str, Any] = field(default_factory=dict)
    behavior: Dict[str, Any] = field(default_factory=dict)
    checks: Dict[str, Any] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def count(self) -> int:
        """获取 Worker 数量"""
        return self.behavior.get("count", 1)
    
    @property
    def parallel(self) -> bool:
        """是否并行执行"""
        return self.behavior.get("parallel", False)
    
    @property
    def timeout(self) -> int:
        """获取超时时间"""
        return self.behavior.get("timeout", 300)
    
    @property
    def max_concurrency(self) -> int:
        """获取最大并发数"""
        return self.behavior.get("max_concurrency", 1)


@dataclass
class ConvergenceRules:
    """收敛规则"""
    domain: str
    cage_version: str
    rules: Dict[str, Any] = field(default_factory=dict)
    validation: Dict[str, Any] = field(default_factory=dict)
    output: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def min_iterations(self) -> int:
        """最小迭代次数"""
        return self.rules.get("min_iterations", {}).get("value", 2)
    
    @property
    def max_iterations(self) -> int:
        """最大迭代次数"""
        return self.rules.get("max_iterations", {}).get("value", 10)
    
    @property
    def target_score(self) -> float:
        """目标分数"""
        return self.rules.get("target_score", {}).get("value", 0.92)
    
    @property
    def high_score_threshold(self) -> float:
        """高分阈值"""
        return self.rules.get("high_score", {}).get("threshold", 0.95)
    
    @property
    def stall_threshold(self) -> float:
        """停滞阈值"""
        return self.rules.get("target_score", {}).get("stall_threshold", 0.02)


# ============================================================================
# 契约加载器
# ============================================================================

class CageLoader:
    """
    笼子契约加载器
    
    从 YAML 文件加载契约定义，提供查询接口
    """
    
    def __init__(self, cage_dir: str = None):
        self.cage_dir = Path(cage_dir or "/Users/allen/.openclaw/workspace/.deepflow/cage")
        self._cache: Dict[str, Any] = {}
    
    def load_domain_contract(self, domain: str) -> Optional[DomainContract]:
        """
        加载领域契约
        
        Args:
            domain: 领域名称 (e.g., "investment")
            
        Returns:
            DomainContract 或 None
        """
        cache_key = f"domain_{domain}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        contract_file = self.cage_dir / f"domain_{domain}.yaml"
        if not contract_file.exists():
            print(f"[CageLoader] WARNING: Domain contract not found: {contract_file}")
            return None
        
        try:
            with open(contract_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            contract = DomainContract(
                cage_version=data.get("cage_version", "2.0"),
                domain=data.get("domain", domain),
                interface=data.get("interface", {}),
                behavior=data.get("behavior", {}),
                exceptions=data.get("exceptions", {}),
                data=data.get("data", {})
            )
            
            self._cache[cache_key] = contract
            return contract
            
        except Exception as e:
            print(f"[CageLoader] ERROR: Failed to load domain contract: {e}")
            return None
    
    def load_stage_contract(self, domain: str, stage: str) -> Optional[StageContract]:
        """
        加载阶段契约
        
        Args:
            domain: 领域名称
            stage: 阶段名称 (e.g., "data_collection")
            
        Returns:
            StageContract 或 None
        """
        cache_key = f"stage_{domain}_{stage}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        contract_file = self.cage_dir / f"stage_{stage}.yaml"
        if not contract_file.exists():
            print(f"[CageLoader] WARNING: Stage contract not found: {contract_file}")
            return None
        
        try:
            with open(contract_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            # 验证 domain 匹配
            if data.get("domain") != domain:
                print(f"[CageLoader] WARNING: Stage domain mismatch: expected '{domain}', got '{data.get('domain')}'")
                return None
            
            contract = StageContract(
                stage=data.get("stage", stage),
                domain=data.get("domain", domain),
                cage_version=data.get("cage_version", "2.0"),
                interface=data.get("interface", {}),
                behavior=data.get("behavior", {}),
                data=data.get("data", {})
            )
            
            self._cache[cache_key] = contract
            return contract
            
        except Exception as e:
            print(f"[CageLoader] ERROR: Failed to load stage contract: {e}")
            return None
    
    def load_worker_contract(self, domain: str, worker: str) -> Optional[WorkerContract]:
        """
        加载 Worker 契约
        
        Args:
            domain: 领域名称
            worker: Worker 名称 (e.g., "researcher")
            
        Returns:
            WorkerContract 或 None
        """
        cache_key = f"worker_{domain}_{worker}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        contract_file = self.cage_dir / f"worker_{worker}.yaml"
        if not contract_file.exists():
            print(f"[CageLoader] WARNING: Worker contract not found: {contract_file}")
            return None
        
        try:
            with open(contract_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            # 验证 domain 匹配
            if data.get("domain") != domain:
                print(f"[CageLoader] WARNING: Worker domain mismatch: expected '{domain}', got '{data.get('domain')}'")
                return None
            
            contract = WorkerContract(
                worker=data.get("worker", worker),
                domain=data.get("domain", domain),
                cage_version=data.get("cage_version", "2.0"),
                roles=data.get("roles", []),
                interface=data.get("interface", {}),
                behavior=data.get("behavior", {}),
                checks=data.get("checks", {}),
                data=data.get("data", {})
            )
            
            self._cache[cache_key] = contract
            return contract
            
        except Exception as e:
            print(f"[CageLoader] ERROR: Failed to load worker contract: {e}")
            return None
    
    def load_convergence_rules(self, domain: str) -> Optional[ConvergenceRules]:
        """
        加载收敛规则
        
        Args:
            domain: 领域名称
            
        Returns:
            ConvergenceRules 或 None
        """
        cache_key = f"convergence_{domain}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        contract_file = self.cage_dir / "convergence_rules.yaml"
        if not contract_file.exists():
            print(f"[CageLoader] WARNING: Convergence rules not found: {contract_file}")
            return None
        
        try:
            with open(contract_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            # 验证 domain 匹配
            if data.get("domain") != domain:
                print(f"[CageLoader] WARNING: Convergence domain mismatch: expected '{domain}', got '{data.get('domain')}'")
                return None
            
            rules = ConvergenceRules(
                domain=data.get("domain", domain),
                cage_version=data.get("cage_version", "2.0"),
                rules=data.get("rules", {}),
                validation=data.get("validation", {}),
                output=data.get("output", {})
            )
            
            self._cache[cache_key] = rules
            return rules
            
        except Exception as e:
            print(f"[CageLoader] ERROR: Failed to load convergence rules: {e}")
            return None
    
    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()
    
    def get_all_stages_for_domain(self, domain: str) -> List[str]:
        """
        获取领域的所有阶段
        
        Args:
            domain: 领域名称
            
        Returns:
            阶段名称列表
        """
        domain_contract = self.load_domain_contract(domain)
        if domain_contract:
            return domain_contract.stages
        return []
    
    def get_all_workers_for_domain(self, domain: str) -> List[str]:
        """
        获取领域的所有 Worker 类型
        
        Args:
            domain: 领域名称
            
        Returns:
            Worker 名称列表（从领域契约的 behavior.workers 中提取）
        """
        domain_contract = self.load_domain_contract(domain)
        if domain_contract:
            return list(domain_contract.workers.keys())
        return []


# ============================================================================
# 工具函数
# ============================================================================

def load_investment_contracts() -> Dict[str, Any]:
    """
    便捷函数：加载 investment 领域的所有契约
    
    Returns:
        {
            "domain": DomainContract,
            "stages": {stage_name: StageContract},
            "workers": {worker_name: WorkerContract},
            "convergence": ConvergenceRules
        }
    """
    loader = CageLoader()
    
    domain = loader.load_domain_contract("investment")
    if not domain:
        return {"error": "Failed to load domain contract"}
    
    result = {
        "domain": domain,
        "stages": {},
        "workers": {},
        "convergence": None
    }
    
    # 加载所有阶段契约
    for stage_name in domain.stages:
        stage_contract = loader.load_stage_contract("investment", stage_name)
        if stage_contract:
            result["stages"][stage_name] = stage_contract
    
    # 加载所有 Worker 契约
    for worker_name in domain.workers.keys():
        worker_contract = loader.load_worker_contract("investment", worker_name)
        if worker_contract:
            result["workers"][worker_name] = worker_contract
    
    # 加载收敛规则
    result["convergence"] = loader.load_convergence_rules("investment")
    
    return result


# ============================================================================
# 入口函数
# ============================================================================

if __name__ == "__main__":
    print("="*60)
    print("CAGE LOADER TEST - Investment Domain")
    print("="*60 + "\n")
    
    contracts = load_investment_contracts()
    
    if "error" in contracts:
        print(f"ERROR: {contracts['error']}")
        sys.exit(1)
    
    # 打印领域契约
    domain = contracts["domain"]
    print(f"📄 Domain Contract:")
    print(f"   cage_version: {domain.cage_version}")
    print(f"   domain: {domain.domain}")
    print(f"   stages: {domain.stages}")
    print(f"   convergence: min={domain.convergence.get('min_iterations')}, "
          f"max={domain.convergence.get('max_iterations')}, "
          f"target={domain.convergence.get('target_score')}")
    print()
    
    # 打印阶段契约
    print(f"📄 Stage Contracts ({len(contracts['stages'])} loaded):")
    for stage_name, stage_contract in contracts["stages"].items():
        print(f"   - {stage_name}: timeout={stage_contract.timeout}s")
    print()
    
    # 打印 Worker 契约
    print(f"📄 Worker Contracts ({len(contracts['workers'])} loaded):")
    for worker_name, worker_contract in contracts["workers"].items():
        print(f"   - {worker_name}: count={worker_contract.count}, "
              f"parallel={worker_contract.parallel}, "
              f"timeout={worker_contract.timeout}s")
    print()
    
    # 打印收敛规则
    conv = contracts["convergence"]
    if conv:
        print(f"📄 Convergence Rules:")
        print(f"   min_iterations: {conv.min_iterations}")
        print(f"   max_iterations: {conv.max_iterations}")
        print(f"   target_score: {conv.target_score}")
        print(f"   high_score_threshold: {conv.high_score_threshold}")
        print(f"   stall_threshold: {conv.stall_threshold}")
    print()
    
    print("="*60)
    print("✅ ALL CONTRACTS LOADED SUCCESSFULLY")
    print("="*60)
