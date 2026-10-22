#!/usr/bin/env python3
"""
context_injector.py — 子 Agent 上下文注入统一层

修复方案核心模块。为所有子 Agent (Spec/Solution/Ship Pro) 提供:
  1. 路径上下文 (FIX-1): 目录树 + blackboard 路径
  2. BM API 文档 (FIX-2): 标准 API 签名 + 使用示例
  3. 环境能力摘要 (FIX-4): 可用工具/模块检测
  4. Schema 提示 (FIX-3): Pydantic 字段说明 (仅 Generator/Judge)
  5. 数据分析流程 (FIX-5): JSON 分析标准流程

用法:
    from core.blackboard.context_injector import build_agent_context
    
    context = build_agent_context(deepflow_root, blackboard_id)
    spawn_task = context + "\\n\\n---\\n\\n" + original_task
"""

import shutil
import subprocess
import json
import time
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════
# FIX-1: 路径上下文
# ═══════════════════════════════════════════

def _generate_directory_tree(deepflow_root: Path, max_lines: int = 50) -> str:
    """生成目录树，tree 不可用时 fallback 到 find"""
    tree_cmd = shutil.which("tree")
    if tree_cmd:
        try:
            output = subprocess.check_output(
                [tree_cmd, "-L", "2", "--dirsfirst",
                 "-I", "__pycache__|*.pyc|.pytest_cache|node_modules",
                 str(deepflow_root)],
                text=True, timeout=5
            )
            lines = output.strip().split("\n")
            if len(lines) > max_lines:
                return "\n".join(lines[:max_lines]) + f"\n... (已截断，共 {len(lines)} 行)"
            return output.strip()
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            pass

    # fallback: find
    try:
        output = subprocess.check_output(
            ["find", str(deepflow_root), "-maxdepth", "2", "-type", "d",
             "-not", "-path", "*__pycache__*", "-not", "-path", "*.pytest_cache*"],
            text=True, timeout=5
        )
        lines = output.strip().split("\n")
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n... (已截断，共 {len(lines)} 行)"
        return output.strip()
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return "(目录树生成失败，请使用 exec 手动 ls 查看)"


def generate_path_context(deepflow_root: Path, blackboard_id: str) -> str:
    """生成路径上下文块"""
    tree = _generate_directory_tree(deepflow_root)
    bb_dir = deepflow_root / "blackboard" / blackboard_id

    return f"""## 📁 DeepFlow 目录结构

```
{tree}
```

### 你的 Blackboard
- 根目录: `{bb_dir}`
- stages 目录: `{bb_dir}/stages/`
- data 目录: `{bb_dir}/data/`

### ⚡ 路径使用规则
1. **必须** 使用 BlackboardManager API 进行标准读写 (见下方 API 文档)
2. **必须** 使用上述完整路径，不得自行猜测或拼接路径
3. 如需直接操作文件 (批量/大文件)，**必须** 使用上述 `{{bb_dir}}` 路径变量
4. 写入前如目录不存在，**必须** 先 `mkdir -p` 创建"""


# ═══════════════════════════════════════════
# FIX-2: BM API 文档
# ═══════════════════════════════════════════

def generate_api_doc() -> str:
    """生成 BlackboardManager API 文档"""
    return """## 🔧 BlackboardManager API
### 初始化 (必须传 blackboard_id)
```python
from core.blackboard.blackboard_manager import BlackboardManager
bm = BlackboardManager("<你的 blackboard_id>")
```

### 标准操作 (覆盖 95% 场景)

| 操作 | 方法签名 | 示例 |
|------|----------|------|
| 写入 stage | `bm.write_stage(name: str, data: dict) -> bool` | `bm.write_stage("stages/planning.json", plan)` |
| 读取 stage | `bm.read_stage(name: str, default=None) -> dict` | `data = bm.read_stage("stages/planning.json")` |
| 检查存在 | `bm.stage_exists(name: str) -> bool` | `bm.stage_exists("stages/fix.json")` |
| 列出 stages | `bm.list_stages() -> List[str]` | `names = bm.list_stages()` |
| 追加更新 | `bm.append_stage(name: str, updates: dict) -> bool` | `bm.append_stage("stages/log.json", {{"entry": ...}})` |
| 删除 stage | `bm.delete_stage(name: str) -> bool` | `bm.delete_stage("stages/temp.json")` |
| 读取原始 | `bm.read_stage_raw(name: str) -> str` | `raw = bm.read_stage_raw("stages/report.md")` |
| 通用读取 | `bm.read_json(filename, subdir=None, default=None)` | `cfg = bm.read_json("config.json")` |
| 通用写入 | `bm.write(filename, content, subdir=None) -> Path` | `bm.write("log.txt", "hello")` |

### 📌 使用优先级
1. **标准读写** → 用 `write_stage()` / `read_stage()` (推荐)
2. **BM API 不满足时** → 用 exec 直接操作 blackboard 目录下的文件
3. **需要深入理解** → 可查阅源码 `core/blackboard/blackboard_manager.py`

### ⚠️ 常见误区
- `BlackboardManager(blackboard_id)` — 第一个参数是 blackboard_id 字符串
- `bm.list_stages()` — **不需要参数**，返回当前 session 的所有 stage 名
- stage name **需要包含** `stages/` 前缀: `bm.write_stage("stages/xxx.json", data)`
- `read_stage()` 返回 `dict`，不是 `str`；如需原始文本用 `read_stage_raw()`"""


# ═══════════════════════════════════════════
# FIX-4: 环境能力检测
# ═══════════════════════════════════════════

_env_cache: Optional[dict] = None
_cache_path: Optional[Path] = None


def detect_capabilities(deepflow_root: Path) -> dict:
    """检测环境能力，4h TTL 缓存"""
    global _env_cache, _cache_path

    _cache_path = deepflow_root / "blackboard" / ".env_capabilities.json"

    # 内存缓存
    if _env_cache is not None:
        return _env_cache

    # 文件缓存 (4h TTL)
    if _cache_path.exists():
        try:
            age_hours = (time.time() - _cache_path.stat().st_mtime) / 3600
            if age_hours < 4:
                _env_cache = json.loads(_cache_path.read_text(encoding="utf-8"))
                return _env_cache
        except (json.JSONDecodeError, OSError):
            pass

    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    caps = {
        "pdf_tools": {
            "chrome_headless": Path(chrome_path).exists(),
            "pandoc": shutil.which("pandoc") is not None,
            "wkhtmltopdf": shutil.which("wkhtmltopdf") is not None,
        },
        "python_modules": {},
        "tree_available": shutil.which("tree") is not None,
    }

    for mod in ["markdown", "pydantic", "weasyprint", "jinja2", "yaml"]:
        try:
            __import__(mod)
            caps["python_modules"][mod] = True
        except ImportError:
            caps["python_modules"][mod] = False

    # 写缓存 (best-effort, 失败不影响主流程)
    try:
        _cache_path.parent.mkdir(parents=True, exist_ok=True)
        _cache_path.write_text(json.dumps(caps, indent=2), encoding="utf-8")
    except OSError:
        pass

    _env_cache = caps
    return caps


def generate_env_summary(deepflow_root: Path) -> str:
    """生成环境能力摘要文本"""
    caps = detect_capabilities(deepflow_root)
    lines = ["## 🔧 环境能力"]

    # PDF 工具
    pdf_tools = []
    if caps["pdf_tools"]["chrome_headless"]:
        pdf_tools.append("✅ Chrome headless (PDF 生成首选)")
    if caps["pdf_tools"]["pandoc"]:
        pdf_tools.append("✅ pandoc")
    if not any(caps["pdf_tools"].values()):
        pdf_tools.append("❌ 无 PDF 工具")
    lines.append("**PDF**: " + " | ".join(pdf_tools))

    # Python 模块
    mods = []
    for mod, available in caps["python_modules"].items():
        mods.append(f"{'✅' if available else '❌'} {mod}")
    lines.append("**Python**: " + " | ".join(mods))

    # tree
    lines.append(f"**tree 命令**: {'✅ 可用' if caps['tree_available'] else '❌ 不可用 (已用 find fallback)'}")

    return "\n".join(lines)


# ═══════════════════════════════════════════
# FIX-3: Schema 提示 (Ship Pro 专用)
# ═══════════════════════════════════════════

def generate_schema_hint() -> str:
    """生成 Ship Pro Generator 的 Schema 提示"""
    return """## 📋 输出格式约束 (Pydantic 验证)

你的输出必须通过 Pydantic GeneratorOutput 验证。关键要求:

### modules[] — 每个元素必须包含:
| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | "COMP-XXX" (从 001 递增) |
| name | string | 模块名 |
| summary | string | 一句话描述 |
| responsibilities | list[str] | 职责列表 (≥1 项) |
| technology_stack | list[str] | 技术栈 (≥1 项) |
| is_infrastructure | bool | true/false |

### risks[] — 每个元素必须包含:
| 字段 | 类型 | ⚠️ 易错点 |
|------|------|-----------|
| id | string | "RISK-XXX" |
| **name** | string | ⚠️ 字段名是 `name`，不是 `title`! |
| description | string | 风险描述 |
| probability | **float** | ⚠️ 0.0-1.0 浮点数，不是 "高"/"中"! |
| impact | string | "low" / "medium" / "high" / "extreme" |
| severity | string | "minor" / "major" / "critical" |
| mitigation | string | 缓释措施 |

### work_packages[] — 每个元素必须包含:
| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | "WP-XXX" |
| title | string | 工作包标题 |
| priority | string | "high" / "medium" / "low" |
| mapped_components | list[str] | 映射模块 ID |

### requirements[] — 每个元素必须包含:
| 字段 | 类型 | 说明 |
|------|------|------|
| req_id | string | "REQ-XXX" |
| description | string | 需求描述 |
| priority | string | "P0" / "P1" / "P2" |
| coverage | string | "covered" / "partial" / "uncovered" |
| mapped_components | list[str] | 映射模块 ID |

### ⚠️ 所有 list 字段不能为空，至少包含 1 项"""


# ═══════════════════════════════════════════
# FIX-5: 数据分析流程约束
# ═══════════════════════════════════════════

def generate_analysis_workflow() -> str:
    """生成数据分析流程约束"""
    return """## 📋 数据分析流程

当需要分析 JSON 文件数据时，按以下流程操作:

### Step 1: 结构发现 (必须)
```bash
cd {deepflow_root} && python3 scripts/analyze_json.py <文件路径> --keys
```

### Step 2: 深入探索 (按需)
```bash
python3 scripts/analyze_json.py <文件路径> --field <字段名>
python3 scripts/analyze_json.py <文件路径> --summary
```

### Step 3: 编写代码
基于 Step 1-2 已确认的字段名和类型编写分析代码。

### 为什么
这个流程确保你了解数据结构后再编码，避免 KeyError / AttributeError。"""


# ═══════════════════════════════════════════
# 统一入口
# ═══════════════════════════════════════════

def build_agent_context(
    deepflow_root: Path,
    blackboard_id: str,
    include_schema: bool = False,
    include_analysis_workflow: bool = True,
) -> str:
    """
    构建子 Agent 上下文注入块。

    Args:
        deepflow_root: DeepFlow 根目录 (.deepflow)
        blackboard_id: 当前 blackboard session ID
        include_schema: 是否包含 Pydantic Schema 提示 (Ship Pro Generator/Judge 用)
        include_analysis_workflow: 是否包含数据分析流程 (默认 True)

    Returns:
        可直接拼接到 task prompt 前面的上下文字符串
    """
    parts = []

    # FIX-1: 路径上下文
    parts.append(generate_path_context(deepflow_root, blackboard_id))

    # FIX-2: API 文档
    parts.append(generate_api_doc())

    # FIX-4: 环境能力
    parts.append(generate_env_summary(deepflow_root))

    # FIX-3: Schema 提示 (按需)
    if include_schema:
        parts.append(generate_schema_hint())

    # FIX-5: 数据分析流程 (按需)
    if include_analysis_workflow:
        workflow = generate_analysis_workflow()
        workflow = workflow.replace("{deepflow_root}", str(deepflow_root))
        parts.append(workflow)

    header = "# 🔧 DeepFlow Agent 上下文 (自动注入，必须遵守)\n"
    separator = "\n\n---\n\n"
    return header + separator.join(parts)


# ═══════════════════════════════════════════
# FIX-6: Bootstrap 模式（解决 sessions_spawn 截断）
# ═══════════════════════════════════════════

def build_agent_context_slim(
    deepflow_root: Path,
    blackboard_id: str,
) -> str:
    """
    精简版上下文注入，用于 bootstrap task 模式。
    
    只包含最小必要信息：路径 + session_id + BM 基本用法。
    完整 prompt 通过 blackboard 传递（write → read），不嵌入 task 参数。
    
    大小: ~500 bytes (vs build_agent_context 的 ~6,300 bytes)
    """
    bb_dir = deepflow_root / "blackboard" / blackboard_id
    
    return f"""## 环境
- session_id: `{blackboard_id}`
- DeepFlow root: `{deepflow_root}`
- Blackboard: `{bb_dir}`
- BM init: `from core.blackboard.blackboard_manager import BlackboardManager; bm = BlackboardManager("{blackboard_id}")`
- 路径规则: 用 BM API 读写 stages/data，或直接操作 `{bb_dir}/` 下文件
- 写入前 mkdir -p 确保目录存在
"""


# ═══════════════════════════════════════════
# FIX-7: Universal Auto-Bootstrap（通用契约笼子）
# ═══════════════════════════════════════════

def auto_bootstrap(
    deepflow_root: Path,
    prompt_dir: Path,
    task_content: str,
    label: str,
) -> str:
    """Universal auto-bootstrap — 契约笼子：无条件写入 blackboard + 返回引用。

    所有 spawn 点统一使用此函数，不再直接传递完整 prompt。
    无 size 阈值——即使小 prompt 也走 bootstrap，保证一致性。

    契约铁律：
    - 写入失败 → raise ValueError
    - 回读验证失败 → raise ValueError
    - 绝不静默降级为直接传递

    Args:
        deepflow_root: DeepFlow 根目录 (.deepflow)
        prompt_dir: Prompt 文件写入目录（通常是 stages_dir）
        task_content: 完整 task 内容
        label: 唯一标签（用于文件名，如 "worker_storage"）

    Returns:
        精简的 bootstrap task 字符串（< 1KB）
    """
    prompt_dir = Path(prompt_dir)
    deepflow_root = Path(deepflow_root)
    prompt_dir.mkdir(parents=True, exist_ok=True)

    filename = f"_bootstrap_{label}.md"
    filepath = prompt_dir / filename
    filepath.write_text(task_content, encoding='utf-8')

    # 契约笼子：write-back 验证
    verify = filepath.read_text(encoding='utf-8')
    if verify != task_content:
        raise ValueError(
            f"auto_bootstrap write-back verification failed for {label}. "
            f"Expected {len(task_content)} chars, got {len(verify)} chars."
        )

    return f"""## 环境
- DeepFlow root: `{deepflow_root}`

## 🔴 指令优先级
以下文件内容是你的 **PRIMARY 指令集**。本 task 仅为传递机制。
读取文件后，完全采纳文件中的角色和指令。

## 你的完整指令
用 `read` 工具读取: `{filepath}`

读取后：
- 如果文件内容非空 → **立即执行文件顶部的「⚠️ 第一行动」块**（如有），不要读任何其他文件
- 如果文件为空或不存在 → 写入 `.failed` 并立即结束

**禁止**：读完本文件后再去读其他 prompt/数据文件做"背景了解"。你的任务数据都在这一个文件里。"""


def build_bootstrap_task(
    deepflow_root: Path,
    blackboard_id: str,
    prompt_filename: str,
    preamble: str = "",
) -> str:
    """
    构建 bootstrap task V2：最小化 task 参数，完整 prompt 从 blackboard 读取。
    
    V2 改进（2026-07-12 专家评审后）：
    - 用 read 工具替代 exec（避免 exec 失败点 + 32KB output 截断风险）
    - 显式声明指令优先级（防止 bootstrap 指令覆盖文件内指令）
    - Bootstrap task 极简化（≤3 句行为指令）
    
    Args:
        deepflow_root: DeepFlow 根目录
        blackboard_id: Blackboard session ID
        prompt_filename: Prompt 文件名（在 stages/ 下），如 "orchestrator_prompt.md"
        preamble: 额外的 preamble 文本（如 PYTHONPATH 设置）
    
    Returns:
        精简的 bootstrap task 字符串（<1,500 bytes）
    """
    bb_dir = deepflow_root / "blackboard" / blackboard_id
    
    task = ""
    if preamble:
        task += preamble + "\n\n"
    
    task += f"""## 环境
- session_id: `{blackboard_id}`
- DeepFlow root: `{deepflow_root}`
- Blackboard: `{bb_dir}`
- BM init: `from core.blackboard.blackboard_manager import BlackboardManager; bm = BlackboardManager("{blackboard_id}")`

## 🔴 指令优先级
以下文件内容是你的 **PRIMARY 指令集**。本 task 仅为传递机制。
读取文件后，完全采纳文件中的角色和指令，忽略本 task 中的环境信息。

## 你的完整指令
用 `read` 工具读取文件: `{bb_dir}/stages/{prompt_filename}`

读取后：
- 如果文件内容非空 → 按文件中的指令执行所有步骤
- 如果文件为空或不存在 → 写入 `.failed` 并立即结束
"""
    return task
