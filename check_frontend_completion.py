"""
Contract validation for frontend completion.
"""
import sys
import ast
import json
from pathlib import Path

def check_file_exists(path: str) -> bool:
    """Check if file exists."""
    return Path(path).exists()

def check_syntax(path: str) -> tuple[bool, str]:
    """Check Python file syntax."""
    try:
        with open(path, 'r') as f:
            ast.parse(f.read())
        return True, "OK"
    except SyntaxError as e:
        return False, str(e)

def check_imports(path: str) -> tuple[bool, str]:
    """Check if file can be imported."""
    try:
        # Add parent to path for imports
        import importlib.util
        spec = importlib.util.spec_from_file_location("module", path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return True, "OK"
    except Exception as e:
        return False, str(e)

def check_line_count(path: str, max_lines: int) -> tuple[bool, int]:
    """Check file line count."""
    with open(path, 'r') as f:
        lines = len(f.readlines())
    return lines <= max_lines, lines

def main():
    """Run all contract checks."""
    print("=" * 60)
    print("Frontend Completion Contract Validation")
    print("=" * 60)
    
    checks = [
        # Phase 1: Task Queue Consumer
        ("File: consumer.py", "frontend/backend/routers/consumer.py", "exists"),
        ("Syntax: consumer.py", "frontend/backend/routers/consumer.py", "syntax"),
        ("Lines: consumer.py", "frontend/backend/routers/consumer.py", "lines", 250),
        
        # Phase 2: Blackboard Bridge
        ("File: blackboard_bridge.py", "core/blackboard_bridge.py", "exists"),
        ("Syntax: blackboard_bridge.py", "core/blackboard_bridge.py", "syntax"),
        ("Lines: blackboard_bridge.py", "core/blackboard_bridge.py", "lines", 200),
        
        # Phase 3: E2E Tests
        ("File: test_frontend_flow.py", "tests/e2e/test_frontend_flow.py", "exists"),
        ("Syntax: test_frontend_flow.py", "tests/e2e/test_frontend_flow.py", "syntax"),
    ]
    
    results = []
    
    for name, path, check_type, *args in checks:
        full_path = Path.home() / ".openclaw" / "workspace" / ".deepflow" / path
        
        if check_type == "exists":
            result = check_file_exists(full_path)
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} | {name}")
            results.append((name, result))
        
        elif check_type == "syntax":
            result, msg = check_syntax(full_path) if check_file_exists(full_path) else (False, "File not found")
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} | {name}: {msg if not result else 'OK'}")
            results.append((name, result))
        
        elif check_type == "lines":
            max_lines = args[0]
            if check_file_exists(full_path):
                result, count = check_line_count(full_path, max_lines)
                status = "✅ PASS" if result else "❌ FAIL"
                print(f"{status} | {name}: {count} lines (max {max_lines})")
                results.append((name, result))
            else:
                print(f"❌ FAIL | {name}: File not found")
                results.append((name, False))
    
    # Summary
    print("=" * 60)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"Results: {passed}/{total} passed")
    
    if passed == total:
        print("✅ ALL CHECKS PASSED")
        return 0
    else:
        print("❌ SOME CHECKS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
