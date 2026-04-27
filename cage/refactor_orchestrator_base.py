#!/usr/bin/env python3
"""
重构 orchestrator_base.py，替换硬编码路径为 PathConfig
"""

import re

input_file = "/Users/allen/.openclaw/workspace/.deepflow/core/orchestrator_base.py"
output_file = "/Users/allen/.openclaw/workspace/.deepflow/core/orchestrator_base.py"

with open(input_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 添加 PathConfig 导入（在导入部分）
old_imports = """import os
import sys
import json
import uuid
import time
import asyncio
import copy
import yaml
from pathlib import Path"""

new_imports = """import os
import sys
import json
import uuid
import time
import asyncio
import copy
import yaml
from pathlib import Path

from core.config.path_config import PathConfig

# 从 PathConfig 获取基础目录（支持环境变量覆盖）
_DEEPFLOW_BASE = PathConfig.resolve().base_dir"""

content = content.replace(old_imports, new_imports)

# 2. 替换 sys.path.insert 硬编码路径
old_syspath = "sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')"
new_syspath = "sys.path.insert(0, str(_DEEPFLOW_BASE))"
content = content.replace(old_syspath, new_syspath)

# 3. 替换 PromptLoader 中的硬编码路径
old_promptloader = '''    def __init__(self, domain: str, base_path: Optional[str] = None):
        self.domain = domain
        self.base_path = Path(base_path or f"/Users/allen/.openclaw/workspace/.deepflow/prompts/{domain}")
        self.default_path = Path("/Users/allen/.openclaw/workspace/.deepflow/core/defaults")'''

new_promptloader = '''    def __init__(self, domain: str, base_path: Optional[str] = None):
        self.domain = domain
        self.base_path = Path(base_path or PathConfig.resolve().prompts_dir / domain)
        self.default_path = PathConfig.resolve().defaults_dir'''

content = content.replace(old_promptloader, new_promptloader)

# 4. 替换 run_orchestrator 中的硬编码路径
old_config_path = '''        module = __import__(module_name, fromlist=["DomainOrchestrator"])
        OrchestratorClass = module.DomainOrchestrator
    except ImportError:
        raise DomainConfigError(f"Unknown domain: {domain}. No orchestrator found at {module_name}")'''

new_config_path = '''        module = __import__(module_name, fromlist=["DomainOrchestrator"])
        OrchestratorClass = module.DomainOrchestrator
    except ImportError:
        raise DomainConfigError(f"Unknown domain: {domain}. No orchestrator found at {module_name}")'''

# 注意：DomainConfig.load 已经接收 config_path 参数，调用方应该传入正确的路径
# 但我们需要检查 run_orchestrator 函数中是否有硬编码路径

with open(output_file, 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ orchestrator_base.py 已重构")
print("- 添加 PathConfig 导入")
print("- 替换 sys.path 硬编码路径")
print("- 替换 PromptLoader 硬编码路径")
