"""环境回归守卫：numpy/openblas 与 torch 不得同时加载两份 libomp。

背景：2026-09-06 本机 Python 多次 SIGABRT，根因是 pip torch 自带 libomp 与
Homebrew openblas 依赖的 libomp 同进程重复初始化。该测试在 torch 升级/重装后
应能再次捕获回归。
"""

import os
import platform
import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.skipif(platform.system() != "Darwin", reason="libomp 双加载守卫仅覆盖 macOS")
@pytest.mark.skipif(shutil.which("lsof") is None, reason="需要 lsof 检查已加载动态库")
def test_numpy_torch_load_single_libomp():
    child = r'''
import os
import subprocess
import numpy
import torch

pid = os.getpid()
out = subprocess.check_output(["lsof", "-p", str(pid)], text=True, errors="ignore")
paths = sorted({line.split()[-1] for line in out.splitlines() if "libomp.dylib" in line})
print("LIBOMP_PATHS", paths)
assert len(paths) <= 1, f"duplicate libomp loaded: {paths}"
'''
    env = os.environ.copy()
    env.pop("KMP_DUPLICATE_LIB_OK", None)
    subprocess.run([sys.executable, "-c", child], check=True, env=env, timeout=30)
