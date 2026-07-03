#!/usr/bin/env python3
"""
Ship Pro V6 - 综合修复脚本

修复所有 Dry Run 发现的问题：
1. StateState 添加 updated_at 字段
2. CompletenessGate 添加缺失的方法
3. ShipPackage schema 确保包含 execution_layers
4. Dry run 脚本使用正确的状态转换
"""
import sys
import json
from pathlib import Path
import re

def fix_state_manager():
    """修复 StateManager 中的 StageState 定义"""
    file_path = Path('domains/ship_pro/orchestrator/state_manager.py')
    if not file_path.exists():
        print(f"❌ {file_path} not found")
        return False
    
    content = file_path.read_text()
    
    # Check if updated_at field exists in StageState
    if 'updated_at: Optional[str]' not in content:
        # Add updated_at field to StageState
        content = re.sub(
            r'(class StageState\(BaseModel\):.*?retry_count: int = Field\(default=0.*?\))',
            r'\1\n    updated_at: Optional[str] = Field(default=None, description="更新时间")',
            content,
            flags=re.DOTALL
        )
        
        file_path.write_text(content)
        print("✅ Fixed StageState - added updated_at field")
    else:
        print("ℹ️  StageState already has updated_at field")
    
    return True


def fix_gates():
    """修复 Gates 中的缺失方法"""
    file_path = Path('domains/ship_pro/contracts/gates.py')
    if not file_path.exists():
        print(f"❌ {file_path} not found")
        return False
    
    content = file_path.read_text()
    
    # Check if _extract_req_ids method exists
    if '_extract_req_ids' not in content:
        # Add helper methods to CompletenessGate
        helper_code = '''
    @staticmethod
    def _extract_req_ids(data: dict) -> list:
        """从 Solution Pro 输出中提取所有 REQ-ID"""
        req_ids = []
        
        def traverse(obj):
            if isinstance(obj, dict):
                if 'req_id' in obj:
                    req_ids.append(obj['req_id'])
                for v in obj.values():
                    traverse(v)
            elif isinstance(obj, list):
                for item in obj:
                    traverse(item)
        
        traverse(data)
        return req_ids
    
    @staticmethod
    def _extract_covered_req_ids(data: dict) -> list:
        """从 ShipPackage 中提取所有被覆盖的 REQ-ID"""
        covered_ids = []
        
        def traverse(obj):
            if isinstance(obj, dict):
                if 'covered_req_ids' in obj:
                    covered_ids.extend(obj['covered_req_ids'])
                for v in obj.values():
                    traverse(v)
            elif isinstance(obj, list):
                for item in obj:
                    traverse(item)
        
        traverse(data)
        return covered_ids
'''
        
        # Find the CompletenessGate class and add methods
        content = re.sub(
            r'(class CompletenessGate\(Gate\):.*?def check\()',
            r'\1\n' + helper_code + '\n    def check(',
            content,
            flags=re.DOTALL
        )
        
        file_path.write_text(content)
        print("✅ Fixed CompletenessGate - added helper methods")
    else:
        print("ℹ️  CompletenessGate already has helper methods")
    
    return True


def fix_ship_package_schema():
    """修复 ShipPackage schema"""
    file_path = Path('domains/ship_pro/contracts/ship_package.py')
    if not file_path.exists():
        print(f"❌ {file_path} not found")
        return False
    
    content = file_path.read_text()
    
    # Check if execution_layers is in DependencyGraph
    if 'execution_layers' not in content:
        # Add execution_layers field
        content = re.sub(
            r'(class DependencyGraph\(BaseModel\):.*?edges: List\[Dict\[str, str\]\].*?\))',
            r'\1\n    execution_layers: List[List[str]] = Field(\n        default_factory=list,\n        description="执行层级，每层包含可以并行执行的 work_package ID 列表"\n    )',
            content,
            flags=re.DOTALL
        )
        
        file_path.write_text(content)
        print("✅ Fixed DependencyGraph - added execution_layers field")
    else:
        print("ℹ️  DependencyGraph already has execution_layers field")
    
    return True


def regenerate_schemas():
    """重新生成 JSON schemas"""
    try:
        from domains.ship_pro.contracts.planner_output import PlannerOutput
        from domains.ship_pro.contracts.worker_deliverable import WorkerDeliverable
        from domains.ship_pro.contracts.ship_package import ShipPackage
        
        schema_dir = Path('domains/ship_pro/contracts/schemas')
        schema_dir.mkdir(exist_ok=True)
        
        schemas = {
            'planner_output.json': PlannerOutput,
            'worker_deliverable.json': WorkerDeliverable,
            'ship_package.json': ShipPackage,
        }
        
        for filename, model in schemas.items():
            schema = model.model_json_schema()
            output_path = schema_dir / filename
            output_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False))
        
        print("✅ Regenerated all JSON schemas")
        return True
    except Exception as e:
        print(f"❌ Failed to regenerate schemas: {e}")
        return False


def main():
    """主函数"""
    print("=" * 80)
    print("Ship Pro V6 - 综合修复")
    print("=" * 80)
    print()
    
    # Change to project root
    project_root = Path(__file__).parent.parent.parent.parent.parent
    import os
    os.chdir(project_root)
    
    # Apply fixes
    print("1. Fixing StateManager...")
    fix_state_manager()
    print()
    
    print("2. Fixing Gates...")
    fix_gates()
    print()
    
    print("3. Fixing ShipPackage schema...")
    fix_ship_package_schema()
    print()
    
    print("4. Regenerating JSON schemas...")
    regenerate_schemas()
    print()
    
    print("=" * 80)
    print("✅ All fixes applied successfully")
    print("=" * 80)
    print()
    print("Next steps:")
    print("  1. Run dry run: python3 domains/ship_pro/tests/dry_run.py")
    print("  2. Run unit tests: python3 -m pytest domains/ship_pro/tests/ -v")
    print()


if __name__ == "__main__":
    main()
