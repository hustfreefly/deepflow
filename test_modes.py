#!/usr/bin/env python3
"""Test mode system initialization"""
import sys
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow')

from domains.solution import SolutionOrchestrator

print("="*60)
print("Testing Mode System Initialization")
print("="*60)

# Test 1: Quick mode
print("\n1. Testing QUICK mode...")
try:
    orch_quick = SolutionOrchestrator({
        "topic": "test quick mode", 
        "type": "architecture", 
        "mode": "quick"
    })
    stages = [s.name for s in orch_quick.domain_config.pipeline]
    max_iter = orch_quick.domain_config.convergence.max_iterations
    
    print(f"   Pipeline stages: {stages}")
    print(f"   Max iterations: {max_iter}")
    
    assert len(stages) == 3, f"Quick mode should have 3 stages, got {len(stages)}"
    assert stages == ['planning', 'design', 'deliver'], f"Quick mode stages mismatch: {stages}"
    assert max_iter == 1, f"Quick mode max_iterations should be 1, got {max_iter}"
    print("   ✅ QUICK mode PASSED")
except Exception as e:
    print(f"   ❌ QUICK mode FAILED: {e}")
    import traceback
    traceback.print_exc()

# Test 2: Standard mode
print("\n2. Testing STANDARD mode...")
try:
    orch_standard = SolutionOrchestrator({
        "topic": "test standard mode", 
        "type": "architecture", 
        "mode": "standard"
    })
    stages = [s.name for s in orch_standard.domain_config.pipeline]
    max_iter = orch_standard.domain_config.convergence.max_iterations
    
    print(f"   Pipeline stages: {stages}")
    print(f"   Max iterations: {max_iter}")
    
    assert len(stages) == 6, f"Standard mode should have 6 stages, got {len(stages)}"
    assert stages == ['planning', 'research', 'design', 'audit', 'fix', 'deliver'], \
        f"Standard mode stages mismatch: {stages}"
    assert max_iter == 2, f"Standard mode max_iterations should be 2, got {max_iter}"
    print("   ✅ STANDARD mode PASSED")
except Exception as e:
    print(f"   ❌ STANDARD mode FAILED: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Rigorous mode
print("\n3. Testing RIGOROUS mode...")
try:
    orch_rigorous = SolutionOrchestrator({
        "topic": "test rigorous mode", 
        "type": "architecture", 
        "mode": "rigorous"
    })
    stages = [s.name for s in orch_rigorous.domain_config.pipeline]
    max_iter = orch_rigorous.domain_config.convergence.max_iterations
    
    print(f"   Pipeline stages: {stages}")
    print(f"   Max iterations: {max_iter}")
    
    assert len(stages) == 6, f"Rigorous mode should have 6 stages, got {len(stages)}"
    assert stages == ['planning', 'research', 'design', 'audit', 'fix', 'deliver'], \
        f"Rigorous mode stages mismatch: {stages}"
    assert max_iter == 3, f"Rigorous mode max_iterations should be 3, got {max_iter}"
    print("   ✅ RIGOROUS mode PASSED")
except Exception as e:
    print(f"   ❌ RIGOROUS mode FAILED: {e}")
    import traceback
    traceback.print_exc()

# Test 4: Invalid mode (should raise InvalidModeError)
print("\n4. Testing INVALID mode...")
try:
    from domains.solution.orchestrator import InvalidModeError
    orch_invalid = SolutionOrchestrator({
        "topic": "test invalid mode", 
        "type": "architecture", 
        "mode": "invalid_mode"
    })
    print("   ❌ INVALID mode FAILED: Should have raised InvalidModeError")
except InvalidModeError as e:
    print(f"   ✅ INVALID mode PASSED: Correctly raised InvalidModeError")
except Exception as e:
    print(f"   ❌ INVALID mode FAILED with unexpected error: {e}")

print("\n" + "="*60)
print("All mode tests completed!")
print("="*60)
