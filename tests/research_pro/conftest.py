import sys
import os

# 把 skills/deep-research 加入 sys.path
_deepflow_root = os.path.join(os.path.dirname(__file__), '..', '..', '..')
_skills_path = os.path.join(_deepflow_root, 'skills', 'deep-research')
if _skills_path not in sys.path:
    sys.path.insert(0, _skills_path)
