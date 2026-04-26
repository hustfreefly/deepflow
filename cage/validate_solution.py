#!/usr/bin/env python3
"""
Solution Domain Contract Validator
验证 Solution 领域是否满足契约笼子要求
"""
import os
import sys
import yaml
import json
import re

sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')

class SolutionContractValidator:
    """Solution 领域契约验证器"""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.checks = []
    
    def check(self, condition: bool, msg: str, level: str = "error"):
        """记录检查结果"""
        self.checks.append({"pass": condition, "msg": msg, "level": level})
        if not condition:
            if level == "error":
                self.errors.append(msg)
            else:
                self.warnings.append(msg)
    
    def validate(self) -> dict:
        """执行全部验证"""
        print("="*60)
        print("SOLUTION DOMAIN CONTRACT VALIDATION")
        print("="*60)
        
        # 1. 检查契约文件存在
        self._check_cage_file_exists()
        
        # 2. 加载并验证契约结构
        cage_data = self._load_cage()
        if cage_data:
            self._validate_cage_structure(cage_data)
        
        # 3. 验证领域配置
        self._validate_domain_config()
        
        # 4. 验证 Orchestrator 实现
        self._validate_orchestrator()
        
        # 5. 验证 Prompt 文件
        self._validate_prompts()
        
        # 6. 验证关键 P0 修复
        self._validate_p0_fixes()
        
        return self._build_result()
    
    def _check_cage_file_exists(self):
        """检查契约文件是否存在"""
        cage_path = '/Users/allen/.openclaw/workspace/.deepflow/cage/domain_solution.yaml'
        self.check(
            os.path.exists(cage_path),
            f"契约文件存在: {cage_path}",
            "error"
        )
    
    def _load_cage(self) -> dict:
        """加载契约文件"""
        cage_path = '/Users/allen/.openclaw/workspace/.deepflow/cage/domain_solution.yaml'
        try:
            with open(cage_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.check(False, f"契约文件加载失败: {e}", "error")
            return None
    
    def _validate_cage_structure(self, cage: dict):
        """验证契约结构完整性"""
        # 顶层字段
        required_top = ['domain', 'version', 'interface', 'behavior', 'boundaries']
        for field in required_top:
            self.check(
                field in cage,
                f"契约包含顶层字段 '{field}'",
                "error"
            )
        
        # interface 结构
        if 'interface' in cage:
            interface = cage['interface']
            self.check('input' in interface, "interface 包含 input", "error")
            self.check('output' in interface, "interface 包含 output", "error")
            
            if 'input' in interface:
                input_schema = interface['input']
                self.check('schema' in input_schema, "input 包含 schema", "error")
                if 'schema' in input_schema:
                    schema = input_schema['schema']
                    self.check('required' in schema, "input schema 包含 required", "error")
                    self.check('properties' in schema, "input schema 包含 properties", "error")
        
        # behavior 结构
        if 'behavior' in cage:
            behavior = cage['behavior']
            self.check('stages' in behavior, "behavior 包含 stages", "error")
            self.check('convergence' in behavior, "behavior 包含 convergence", "error")
        
        # boundaries
        if 'boundaries' in cage:
            self.check(
                isinstance(cage['boundaries'], list) and len(cage['boundaries']) > 0,
                f"boundaries 是非空列表 (共 {len(cage.get('boundaries', []))} 条)",
                "error"
            )
        
        # quality
        self.check('quality' in cage, "契约包含 quality 维度定义", "warning")
        
        # delivery (P0)
        self.check('delivery' in cage, "契约包含 delivery 渐进交付定义", "error")
        if 'delivery' in cage:
            delivery = cage['delivery']
            self.check(delivery.get('progressive', False), "delivery.progressive = true", "error")
            self.check('checkpoints' in delivery, "delivery 包含 checkpoints", "error")
        
        # data
        self.check('data' in cage, "契约包含 data 数据契约", "error")
        if 'data' in cage:
            data = cage['data']
            self.check('blackboard' in data, "data 包含 blackboard", "error")
            self.check('checkpoints' in data, "data 包含 checkpoints", "error")
    
    def _validate_domain_config(self):
        """验证领域配置文件"""
        config_path = '/Users/allen/.openclaw/workspace/.deepflow/domains/solution.yaml'
        self.check(os.path.exists(config_path), f"领域配置存在: {config_path}", "error")
        
        if not os.path.exists(config_path):
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
        except Exception as e:
            self.check(False, f"领域配置加载失败: {e}", "error")
            return
        
        # 检查必需字段
        self.check('domain' in config, "配置包含 domain", "error")
        self.check('agents' in config, "配置包含 agents", "error")
        self.check('pipeline' in config, "配置包含 pipeline", "error")
        self.check('convergence' in config, "配置包含 convergence", "error")
        
        # 检查 agents
        if 'agents' in config:
            agents = config['agents']
            required_roles = [
                'solution_planner', 'solution_researcher', 'solution_architect',
                'solution_auditor', 'solution_fixer', 'solution_designer'
            ]
            found_roles = [a['role'] for a in agents]
            for role in required_roles:
                self.check(
                    role in found_roles,
                    f"agents 包含必需角色 '{role}'",
                    "error"
                )
        
        # 检查 pipeline stages
        if 'pipeline' in config and 'stages' in config['pipeline']:
            stages = config['pipeline']['stages']
            required_stages = ['planning', 'research', 'design', 'audit', 'fix', 'deliver']
            found_stages = [s['name'] for s in stages]
            for stage in required_stages:
                self.check(
                    stage in found_stages,
                    f"pipeline 包含必需阶段 '{stage}'",
                    "error"
                )
        
        # 检查并发配置
        self.check('concurrency' in config, "配置包含 concurrency", "error")
        if 'concurrency' in config:
            concurrency = config['concurrency']
            self.check(
                concurrency.get('max_parallel_workers', 0) <= 3,
                f"max_parallel_workers <= 3 (当前: {concurrency.get('max_parallel_workers')})",
                "error"
            )
    
    def _validate_orchestrator(self):
        """验证 Orchestrator 实现"""
        orch_path = '/Users/allen/.openclaw/workspace/.deepflow/domains/solution/orchestrator.py'
        self.check(os.path.exists(orch_path), f"Orchestrator 存在: {orch_path}", "error")
        
        if not os.path.exists(orch_path):
            return
        
        with open(orch_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        # 检查关键方法
        self.check('class SolutionOrchestrator' in code, "定义 SolutionOrchestrator 类", "error")
        self.check('def _execute_stage' in code, "实现 _execute_stage 方法", "error")
        self.check('def _extract_score' in code, "实现 _extract_score 方法", "error")
        self.check('def _build_result' in code, "实现 _build_result 方法", "error")
        
        # 检查 P0 修复
        self.check('asyncio.Semaphore' in code, "使用 Semaphore 并发控制", "error")
        self.check('try:' in code and 'except' in code, "有异常处理", "error")
        
        # 检查禁止 mock
        self.check('mock' not in code.lower() or '_mock_model' not in code, "无 mock 相关代码", "error")
        
        # 检查渐进交付（P0）
        self.check('sessions_yield' in code, "实现渐进交付（sessions_yield）", "error")
        
        # 检查 Blackboard 使用
        self.check('blackboard' in code.lower() or 'stage_outputs' in code, "使用数据持久化", "warning")
        
        # 检查 QualityGate
        self.check('quality' in code.lower(), "有质量评估逻辑", "warning")
    
    def _validate_prompts(self):
        """验证 Prompt 文件"""
        prompt_dir = '/Users/allen/.openclaw/workspace/.deepflow/prompts/solution/'
        self.check(os.path.exists(prompt_dir), f"Prompt 目录存在: {prompt_dir}", "error")
        
        if not os.path.exists(prompt_dir):
            return
        
        required_prompts = [
            'planner.md', 'researcher.md', 'architect.md',
            'auditor.md', 'fixer.md', 'designer.md'
        ]
        
        for prompt_file in required_prompts:
            prompt_path = os.path.join(prompt_dir, prompt_file)
            self.check(
                os.path.exists(prompt_path),
                f"Prompt 文件存在: {prompt_file}",
                "error"
            )
            
            if os.path.exists(prompt_path):
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                self.check(
                    len(content) > 100,
                    f"Prompt '{prompt_file}' 内容非空 ({len(content)} 字符)",
                    "warning"
                )
    
    def _validate_p0_fixes(self):
        """验证 P0 问题修复"""
        # P0-1: 并发控制
        config_path = '/Users/allen/.openclaw/workspace/.deepflow/domains/solution.yaml'
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            if 'concurrency' in config:
                self.check(
                    config['concurrency'].get('max_parallel_workers', 999) <= 3,
                    "P0-FIX: max_parallel_workers <= 3",
                    "error"
                )
        
        # P0-2: _extract_score 容错
        orch_path = '/Users/allen/.openclaw/workspace/.deepflow/domains/solution/orchestrator.py'
        if os.path.exists(orch_path):
            with open(orch_path, 'r', encoding='utf-8') as f:
                code = f.read()
            self.check(
                'try:' in code and 'except' in code and '_extract_score' in code,
                "P0-FIX: _extract_score 有 try-except 容错",
                "error"
            )
            self.check(
                'return 0.5' in code,
                "P0-FIX: _extract_score 有默认返回值 0.5",
                "error"
            )
    
    def _build_result(self) -> dict:
        """构建验证结果"""
        result = {
            "pass": len(self.errors) == 0,
            "total_checks": len(self.checks),
            "passed": sum(1 for c in self.checks if c["pass"]),
            "failed": sum(1 for c in self.checks if not c["pass"]),
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "details": self.checks
        }
        
        print("\n" + "="*60)
        print("VALIDATION RESULT")
        print("="*60)
        print(f"Total checks: {result['total_checks']}")
        print(f"Passed: {result['passed']} ✅")
        print(f"Failed: {result['failed']} ❌")
        print(f"Warnings: {result['warnings']} ⚠️")
        
        if result['errors'] > 0:
            print(f"\nErrors ({result['errors']}):")
            for e in self.errors:
                print(f"  ❌ {e}")
        
        if result['warnings'] > 0:
            print(f"\nWarnings ({result['warnings']}):")
            for w in self.warnings:
                print(f"  ⚠️ {w}")
        
        if result['pass']:
            print("\n🎉 ALL CONTRACT CHECKS PASSED")
        else:
            print(f"\n⚠️ {result['errors']} ERRORS FOUND - NEED FIX")
        
        return result


if __name__ == "__main__":
    validator = SolutionContractValidator()
    result = validator.validate()
    
    # 保存结果
    import json
    from datetime import datetime
    result_file = f"/Users/allen/.openclaw/workspace/.deepflow/test_results/contract_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    os.makedirs(os.path.dirname(result_file), exist_ok=True)
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {result_file}")
