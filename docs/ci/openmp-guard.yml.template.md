# OpenMP 单运行时 CI 守卫（模板）

> 状态：模板。当前 Git 凭证缺少 `workflow` scope，不能直接提交 `.github/workflows/*`。
> 要启用：把本文件复制为 `.github/workflows/openmp-guard.yml`，并确保推送凭证具备 `workflow` 权限。

```yaml
name: openmp-guard

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

jobs:
  openmp-single-runtime:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install minimal deps for guard
        run: |
          python -m pip install --upgrade pip
          python -m pip install pytest numpy torch

      - name: Verify numpy/torch load a single libomp runtime
        run: |
          python -m pytest tests/test_environment/test_openmp_single_runtime.py -q --tb=short
```
