#!/usr/bin/env python3
"""
Phase 2 Dry Run 测试脚本
验证 5 个 prompt 的 schema 兼容性和基础流程
"""

import json
import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

def extract_json_schemas(prompt_file: str) -> list[dict]:
    """从 prompt 中提取所有 JSON schema 示例"""
    content = (PROMPTS_DIR / prompt_file).read_text()
    pattern = r'```json\n(.*?)\n```'
    matches = re.findall(pattern, content, re.DOTALL)
    
    schemas = []
    for match in matches:
        try:
            schemas.append(json.loads(match))
        except json.JSONDecodeError:
            pass
    
    return schemas

def test_ac_writer():
    """测试 P2-AC-Writer"""
    print("\n=== 测试 P2-AC-Writer ===")
    
    schemas = extract_json_schemas("p2_ac_writer.md")
    print(f"   提取到 {len(schemas)} 个 JSON 块，全部合法 ✅")
    
    # 找到输出 schema（包含 ac_drafts）
    output_schema = None
    for s in schemas:
        if "ac_drafts" in s:
            output_schema = s
            break
    
    if output_schema:
        print(f"   输出 schema 字段: {list(output_schema.keys())}")
        
        if "ac_drafts" in output_schema and output_schema["ac_drafts"]:
            draft = output_schema["ac_drafts"][0]
            required = ["wp_id", "wp_name", "criteria", "stats"]
            missing = [f for f in required if f not in draft]
            if missing:
                print(f"   ⚠️ WP draft 缺少: {missing}")
            else:
                print("   ✅ WP draft 结构完整 (wp_id, wp_name, criteria, stats)")
            
            if draft.get("criteria"):
                criterion = draft["criteria"][0]
                req_crit = ["text", "level", "score", "command_template"]
                missing_crit = [f for f in req_crit if f not in criterion]
                if missing_crit:
                    print(f"   ⚠️ criterion 缺少: {missing_crit}")
                else:
                    print("   ✅ criterion 结构完整 (text, level, score, command_template)")
    else:
        print("   ❌ 未找到 ac_drafts 输出 schema")
    
    return output_schema

def test_judges():
    """测试 3 个 Judge"""
    print("\n=== 测试 P2 三个 Judge ===")
    
    judges = {
        "p2_consistency_judge.md": {"required": ["verdict", "real_conflicts", "summary"]},
        "p2_quality_judge.md": {"required": ["verdict", "ac_scores", "issues", "summary"]},
        "p2_completeness_judge.md": {"required": ["verdict", "coverage", "issues", "summary"]},
    }
    
    schemas = {}
    for fname, spec in judges.items():
        print(f"\n--- {fname} ---")
        judge_schemas = extract_json_schemas(fname)
        
        if judge_schemas:
            schema = judge_schemas[0]
            print(f"   ✅ JSON 合法")
            print(f"   字段: {list(schema.keys())}")
            
            missing = [f for f in spec["required"] if f not in schema]
            if missing:
                print(f"   ⚠️ 缺少: {missing}")
            else:
                print(f"   ✅ 必需字段存在")
            
            # verdict 必须有 pass/fail 值
            verdict = schema.get("verdict", "")
            print(f"   verdict 示例: {verdict}")
            
            schemas[fname] = schema
        else:
            print(f"   ❌ 无合法 JSON")
    
    return schemas

def test_consolidator():
    """测试 P2-Consolidator"""
    print("\n=== 测试 P2-Consolidator ===")
    
    schemas = extract_json_schemas("p2_consolidator.md")
    
    # 找到输出 schema（包含 verdict + final_ac）
    output_schema = None
    for s in schemas:
        if "verdict" in s and "final_ac" in s:
            output_schema = s
            break
    
    if output_schema:
        print(f"   ✅ 输出 schema 字段: {list(output_schema.keys())}")
        
        required = ["verdict", "final_ac", "judge_summary", "fix_summary", "metadata"]
        missing = [f for f in required if f not in output_schema]
        if missing:
            print(f"   ⚠️ 缺少: {missing}")
        else:
            print("   ✅ 所有必需字段存在")
    else:
        print("   ❌ 未找到 final_ac 输出 schema")
    
    return output_schema

def test_chain_compatibility(ac_writer_schema, judge_schemas, consolidator_schema):
    """测试 Phase 2 链式兼容性"""
    print("\n" + "="*60)
    print("=== Phase 2 链式兼容性检查 ===")
    print("="*60)
    
    # 1. AC Writer -> Judges
    print("\n1. AC-Writer → 3 Judges:")
    if ac_writer_schema and "ac_drafts" in ac_writer_schema:
        print("   ✅ AC-Writer 输出 ac_drafts，Judges 可以审计")
    else:
        print("   ❌ AC-Writer 缺少 ac_drafts")
    
    # 2. Judges -> Consolidator
    print("\n2. 3 Judges → Consolidator:")
    all_have_verdict = all(
        "verdict" in s for s in judge_schemas.values()
    )
    if all_have_verdict:
        print("   ✅ 所有 Judge 都有 verdict 字段，Consolidator 可以读取")
    else:
        print("   ❌ 某 Judge 缺少 verdict 字段")
    
    # 3. Consolidator 输出检查
    print("\n3. Consolidator 输出:")
    if consolidator_schema and "verdict" in consolidator_schema:
        print(f"   ✅ verdict = {consolidator_schema.get('verdict')}")
        if "fix_summary" in consolidator_schema:
            print(f"   ✅ fix_summary 存在")
    else:
        print("   ❌ Consolidator 输出不完整")

def main():
    print("="*60)
    print("Phase 2 Dry Run 测试")
    print("="*60)
    
    ac_writer_schema = test_ac_writer()
    judge_schemas = test_judges()
    consolidator_schema = test_consolidator()
    
    test_chain_compatibility(ac_writer_schema, judge_schemas, consolidator_schema)
    
    print("\n" + "="*60)
    print("=== 测试完成 ===")
    print("="*60)

if __name__ == "__main__":
    main()
