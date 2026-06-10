import os
import sys

# Get deepflow root (3 levels up from tests/)
_deepflow_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if _deepflow_root not in sys.path:
    sys.path.insert(0, _deepflow_root)
