#!/usr/bin/env python3
"""
Phase 1 Dry Run 测试脚本
验证 9 个 prompt 的 schema 兼容性和基础流程
"""

import json
import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
TESTS_DIR = Path(__file__).parent

def extract_json_schema_from_prompt(prompt_content: str) -> dict | None:
    """从 prompt 中提取 JSON schema 示例"""
    # 查找 ```json ... ``` 块
    pattern = r'```json\n(.*?)\n```'
    matches = re.findall(pattern, prompt_content, re.DOTALL)
    
    for match in matches:
        try:
            # 尝试解析为 JSON
            schema = json.loads(match)
            # 返回第一个有效的 JSON 块（通常是输出 schema）
            return schema
        except json.JSONDecodeError:
            continue
    
    return None

def validate_schema_compatibility(upstream_schema: dict, downstream_input_desc: str) -> list[str]:
    """验证上游输出 schema 是否与下游输入描述兼容"""
    issues = []
    
    if upstream_schema is None:
        issues.append("❌ 上游无有效 JSON schema")
        return issues
    
    # 检查关键字段是否存在
    required_fields = ["modules", "requirements", "principles", "sla_constraints", "data_flows"]
    
    for field in required_fields:
        if field not in upstream_schema:
            issues.append(f"⚠️ 上游 schema 缺少字段: {field}")
    
    return issues

def test_parser_schema():
    """测试 P1-1 Parser 的 schema"""
    print("\n=== 测试 P1-1 Parser ===")
    
    parser_prompt = (PROMPTS_DIR / "p1_parser.md").read_text()
    schema = extract_json_schema_from_prompt(parser_prompt)
    
    if schema:
        print("✅ Parser 输出 schema 提取成功")
        print(f"   字段: {list(schema.keys())}")
        
        # 验证关键字段
        required = ["format", "modules", "requirements", "principles", "sla_constraints", "data_flows"]
        missing = [f for f in required if f not in schema]
        if missing:
            print(f"⚠️ 缺少字段: {missing}")
        else:
            print("✅ 所有必需字段存在")
        
        return schema
    else:
        print("❌ 无法提取 Parser 输出 schema")
        return None

def test_explorer_schema():
    """测试 P1-2 Explorer 的 schema"""
    print("\n=== 测试 P1-2 Explorer ===")
    
    explorer_prompt = (PROMPTS_DIR / "p1_explorer.md").read_text()
    schema = extract_json_schema_from_prompt(explorer_prompt)
    
    if schema:
        print("✅ Explorer 输出 schema 提取成功")
        print(f"   字段: {list(schema.keys())}")
        
        # 验证关键字段
        required = ["findings", "hypotheses", "coverage_summary"]
        missing = [f for f in required if f not in schema]
        if missing:
            print(f"⚠️ 缺少字段: {missing}")
        else:
            print("✅ 所有必需字段存在")
        
        # 验证 finding 结构
        if "findings" in schema and schema["findings"]:
            finding = schema["findings"][0]
            required_finding = ["id", "category", "description", "evidence", "confidence", "type"]
            missing_finding = [f for f in required_finding if f not in finding]
            if missing_finding:
                print(f"⚠️ finding 缺少字段: {missing_finding}")
            else:
                print("✅ finding 结构完整")
        
        return schema
    else:
        print("❌ 无法提取 Explorer 输出 schema")
        return None

def test_architect_step1_schema():
    """测试 P1-3a Architect Step 1 的 schema"""
    print("\n=== 测试 P1-3a Architect Step 1 ===")
    
    architect_prompt = (PROMPTS_DIR / "p1_architect_step1.md").read_text()
    schema = extract_json_schema_from_prompt(architect_prompt)
    
    if schema:
        print("✅ Architect Step 1 输出 schema 提取成功")
        print(f"   字段: {list(schema.keys())}")
        
        # 验证关键字段
        required = ["work_packages", "orphan_modules", "coverage_check"]
        missing = [f for f in required if f not in schema]
        if missing:
            print(f"⚠️ 缺少字段: {missing}")
        else:
            print("✅ 所有必需字段存在")
        
        # 验证 WP 结构
        if "work_packages" in schema and schema["work_packages"]:
            wp = schema["work_packages"][0]
            required_wp = ["id", "title", "source_modules", "dependencies", "priority", "deliverable"]
            missing_wp = [f for f in required_wp if f not in wp]
            if missing_wp:
                print(f"⚠️ WP 缺少字段: {missing_wp}")
            else:
                print("✅ WP 结构完整")
        
        return schema
    else:
        print("❌ 无法提取 Architect Step 1 输出 schema")
        return None

def test_critics_schema():
    """测试 3 个 Critic 的 schema"""
    print("\n=== 测试 P1-4a/b/c 三个 Critic ===")
    
    critics = ["p1_coverage_critic.md", "p1_granularity_critic.md", "p1_feasibility_critic.md"]
    schemas = {}
    
    for critic_file in critics:
        print(f"\n--- {critic_file} ---")
        critic_prompt = (PROMPTS_DIR / critic_file).read_text()
        schema = extract_json_schema_from_prompt(critic_prompt)
        
        if schema:
            print(f"✅ {critic_file} 输出 schema 提取成功")
            print(f"   字段: {list(schema.keys())}")
            
            # 验证关键字段
            required = ["critic_id", "verdict", "issues"]
            missing = [f for f in required if f not in schema]
            if missing:
                print(f"⚠️ 缺少字段: {missing}")
            else:
                print("✅ 所有必需字段存在")
            
            # 验证 issue 结构
            if "issues" in schema and schema["issues"]:
                issue = schema["issues"][0]
                required_issue = ["id", "severity", "category", "description", "evidence", "affected_wps"]
                missing_issue = [f for f in required_issue if f not in issue]
                if missing_issue:
                    print(f"⚠️ issue 缺少字段: {missing_issue}")
                else:
                    print("✅ issue 结构完整")
            
            schemas[critic_file] = schema
        else:
            print(f"❌ 无法提取 {critic_file} 输出 schema")
    
    return schemas

def test_consolidator_schema():
    """测试 P1-Consolidator 的 schema"""
    print("\n=== 测试 P1-Consolidator ===")
    
    consolidator_prompt = (PROMPTS_DIR / "p1_consolidator.md").read_text()
    # Consolidator 有多个 JSON 块，第一个是输入（Critic 格式），第二个才是输出
    pattern = r'```json\n(.*?)\n```'
    matches = re.findall(pattern, consolidator_prompt, re.DOTALL)
    
    schema = None
    for match in matches:
        try:
            obj = json.loads(match)
            # 查找包含 status 字段的 schema（输出格式）
            if "status" in obj:
                schema = obj
                break
        except json.JSONDecodeError:
            continue
    
    if schema:
        print("✅ Consolidator 输出 schema 提取成功")
        print(f"   字段: {list(schema.keys())}")
        
        # 验证关键字段
        required = ["status", "work_packages", "dependency_graph", "approval_metadata"]
        missing = [f for f in required if f not in schema]
        if missing:
            print(f"⚠️ 缺少字段: {missing}")
        else:
            print("✅ 所有必需字段存在")
        
        return schema
    else:
        print("❌ 无法提取 Consolidator 输出 schema")
        return None

def test_schema_chain():
    """测试整个 schema 链的兼容性"""
    print("\n" + "="*60)
    print("=== Schema 链兼容性测试 ===")
    print("="*60)
    
    # 提取所有 schema
    parser_schema = test_parser_schema()
    explorer_schema = test_explorer_schema()
    architect_step1_schema = test_architect_step1_schema()
    critics_schemas = test_critics_schema()
    consolidator_schema = test_consolidator_schema()
    
    print("\n" + "="*60)
    print("=== 链式兼容性检查 ===")
    print("="*60)
    
    # 检查 Parser -> Explorer
    print("\n1. Parser -> Explorer:")
    if parser_schema and "modules" in parser_schema and "requirements" in parser_schema:
        print("   ✅ Parser 输出包含 Explorer 所需的 modules 和 requirements")
    else:
        print("   ❌ Parser 输出缺少 Explorer 所需字段")
    
    # 检查 Parser + Explorer -> Architect Step 1
    print("\n2. Parser + Explorer -> Architect Step 1:")
    if parser_schema and explorer_schema:
        if "modules" in parser_schema and "findings" in explorer_schema:
            print("   ✅ Architect Step 1 可以获取 modules 和 findings")
        else:
            print("   ❌ Architect Step 1 缺少所需输入")
    
    # 检查 Architect -> Critics
    print("\n3. Architect Step 1 -> 3 Critics:")
    if architect_step1_schema and "work_packages" in architect_step1_schema:
        print("   ✅ Critics 可以审计 work_packages")
    else:
        print("   ❌ Critics 无法获取 work_packages")
    
    # 检查 Critics -> Consolidator
    print("\n4. 3 Critics -> Consolidator:")
    all_critics_valid = all(
        "critic_id" in s and "verdict" in s and "issues" in s
        for s in critics_schemas.values()
    )
    if all_critics_valid:
        print("   ✅ 所有 Critic 输出格式与 Consolidator 输入兼容")
    else:
        print("   ❌ Critic 输出格式与 Consolidator 输入不兼容")
    
    print("\n" + "="*60)
    print("=== 测试完成 ===")
    print("="*60)

if __name__ == "__main__":
    test_schema_chain()
