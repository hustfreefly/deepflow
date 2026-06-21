# 契约笼子 Step 1: path_config.py

## 声明

**目标**: 在 `path_config.py` 中新增 Blackboard V2 路径管理能力，不改现有方法。

**新增方法**:
1. `generate_slug(topic: str) -> str` — 从 topic 生成人类可读 slug
2. `get_project_path(slug: str) -> Path` — 获取项目目录路径
3. `get_run_path(slug: str, run_id: str) -> Path` — 获取运行目录路径
4. `is_v2_session_id(session_id: str) -> bool` — 判断 session_id 是否为新格式

**不改动**:
- `get_blackboard_path()` 保持原样
- `_sanitize_session_id()` 保持原样
- `resolve()` 保持原样

## 验证标准

| # | 验证项 | 方法 | 通过条件 |
|:---|:---|:---|:---|
| V1 | generate_slug 生成正确 | 运行测试 | slug 是 ASCII + hyphen，≤50 字符 |
| V2 | generate_slug 冲突处理 | 运行测试 | 同 topic 两次生成不同 slug（加 hash 后缀） |
| V3 | get_project_path 路径正确 | 运行测试 | 返回 `blackboard/projects/{slug}` |
| V4 | get_run_path 路径正确 | 运行测试 | 返回 `blackboard/projects/{slug}/runs/{run_id}` |
| V5 | is_v2_session_id 判断正确 | 运行测试 | 含 `/runs/` 返回 True，否则 False |
| V6 | 现有方法不受影响 | 运行现有测试 | test_path_config.py 全部通过 |
| V7 | 语法正确 | python3 -c import | 无语法错误 |
