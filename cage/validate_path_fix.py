#!/usr/bin/env python3
import sys
import re

DEEPFLOW_BASE = '/Users/allen/.openclaw/workspace/.deepflow'

with open(f"{DEEPFLOW_BASE}/domains/solution/task_builder.py") as f:
    content = f.read()

# Find relative paths (blackboard/ not preceded by absolute path)
relative_pattern = r'(?<!/Users/allen/.openclaw/workspace/.deepflow/)blackboard/'
relative_matches = re.findall(relative_pattern, content)
relative_count = len(relative_matches)

# Count absolute paths
absolute_count = content.count('/Users/allen/.openclaw/workspace/.deepflow/blackboard/')

print(f'Relative paths: {relative_count}')
print(f'Absolute paths: {absolute_count}')

if relative_count > 0:
    print('FAIL: Found relative paths')
    sys.exit(1)
else:
    print('PASS: All paths are absolute')
    sys.exit(0)
