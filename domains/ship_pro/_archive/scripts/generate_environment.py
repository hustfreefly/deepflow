#!/usr/bin/env python3
"""
Deterministic environment spec generator (0 LLM).

Scans work_package context_files for import statements,
filters stdlib, outputs EnvironmentSpec.
"""
import ast
import json
import sys
from pathlib import Path


def generate_environment(work_packages: list[dict], context_dir: str | None = None) -> dict:
    """
    Generate EnvironmentSpec deterministically from work packages.
    
    0 LLM calls. Pure code.
    """
    # Collect all import references
    third_party = set()
    
    # Scan WP context_files for imports
    for wp in work_packages:
        for ctx_file in wp.get("context_files", []):
            if context_dir:
                file_path = Path(context_dir) / ctx_file
                if file_path.exists():
                    third_party.update(_scan_imports(file_path))
        
        # Also scan constraints for mentioned packages
        for constraint in wp.get("constraints", []):
            # Look for package-like patterns
            for token in constraint.split():
                token = token.strip("'\"").lower()
                if _looks_like_package(token):
                    third_party.add(token)
    
    # Filter stdlib
    stdlib = set(sys.stdlib_module_names) if hasattr(sys, 'stdlib_module_names') else set()
    third_party -= stdlib
    
    # Remove common non-package tokens
    false_positives = {"os", "sys", "json", "pathlib", "typing", "datetime", 
                       "collections", "functools", "itertools", "logging",
                       "unittest", "pytest", "asyncio"}
    third_party -= false_positives
    
    return {
        "python": ">=3.10",
        "dependencies": sorted(third_party),
        "test_dependencies": ["pytest>=7.0"],
        "test_runner": "pytest",
        "test_command": "pytest -v",
    }


def _scan_imports(file_path: Path) -> set[str]:
    """Extract top-level import names from a Python file."""
    imports = set()
    try:
        tree = ast.parse(file_path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
    except (SyntaxError, UnicodeDecodeError):
        pass
    return imports


def _looks_like_package(token: str) -> bool:
    """Heuristic: does this token look like a Python package name?"""
    if len(token) < 3 or len(token) > 30:
        return False
    if not token[0].isalpha():
        return False
    if not all(c.isalnum() or c in "-_" for c in token):
        return False
    return True


if __name__ == "__main__":
    # CLI usage
    if len(sys.argv) < 2:
        print("Usage: generate_environment.py <packager_output.json>")
        sys.exit(1)
    
    with open(sys.argv[1]) as f:
        packager_output = json.load(f)
    
    wps = packager_output.get("work_packages", [])
    result = generate_environment(wps)
    print(json.dumps(result, indent=2))
