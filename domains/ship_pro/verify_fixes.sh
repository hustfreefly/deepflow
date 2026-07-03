#!/bin/bash
# Ship Pro V6 - 验证修复脚本

set -e

echo "=========================================="
echo "Ship Pro V6 - 验证修复"
echo "=========================================="
echo ""

cd /Users/allen/.openclaw/workspace/.deepflow

echo "1. 检查 StateState 是否有 updated_at 字段..."
if grep -q "updated_at: Optional\[str\]" domains/ship_pro/orchestrator/state_manager.py; then
    echo "   ✅ StageState 有 updated_at 字段"
else
    echo "   ❌ StageState 缺少 updated_at 字段"
    exit 1
fi
echo ""

echo "2. 检查 CompletenessGate 是否有辅助方法..."
if grep -q "_extract_req_ids" domains/ship_pro/contracts/gates.py; then
    echo "   ✅ CompletenessGate 有 _extract_req_ids 方法"
else
    echo "   ❌ CompletenessGate 缺少 _extract_req_ids 方法"
    exit 1
fi

if grep -q "_extract_covered_req_ids" domains/ship_pro/contracts/gates.py; then
    echo "   ✅ CompletenessGate 有 _extract_covered_req_ids 方法"
else
    echo "   ❌ CompletenessGate 缺少 _extract_covered_req_ids 方法"
    exit 1
fi
echo ""

echo "3. 检查 DependencyGraph 是否有 execution_layers 字段..."
if grep -q "execution_layers: List\[List\[str\]\]" domains/ship_pro/contracts/ship_package.py; then
    echo "   ✅ DependencyGraph 有 execution_layers 字段"
else
    echo "   ❌ DependencyGraph 缺少 execution_layers 字段"
    exit 1
fi
echo ""

echo "4. 重新生成 JSON Schemas..."
python3 << 'EOF'
import json
from pathlib import Path
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
    print(f"   ✅ Generated: {output_path}")

print()
EOF

echo "5. 运行 Dry Run..."
python3 domains/ship_pro/tests/dry_run.py
echo ""

echo "6. 运行单元测试..."
python3 -m pytest domains/ship_pro/tests/test_contracts.py -v
echo ""

echo "=========================================="
echo "✅ 所有验证通过！"
echo "=========================================="
