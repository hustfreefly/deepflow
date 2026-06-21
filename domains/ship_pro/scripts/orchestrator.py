#!/usr/bin/env python3
"""
Ship Pro V3 Orchestrator — 准备 Agent 执行环境

用法:
    python3 orchestrator.py <path/to/final_result.json> <output_dir>

输出:
    <output_dir>/run_config.json — 所有 Agent 的 task prompt + 配置
    <output_dir>/blackboard/ — Agent 间数据传递目录

注意：此脚本不直接调用 sessions_spawn（那是主 Agent 的工作），
而是准备所有 Agent 的 prompt 和输入数据，供主 Agent 读取 run_config.json 后调用。
"""

import json
import sys
import os
import hashlib
from pathlib import Path
from datetime import datetime


def detect_format(data: dict) -> str:
    """
    检测输入格式类型
    
    Format A: final_solution 存在（完整方案）
    Format B: project + architecture 存在（扁平领域描述）
    Format C: pipeline_summary 或 executive_summary 存在（管线摘要）
    Format D: 其他（最小化输入）
    """
    if "final_solution" in data:
        return "A"
    elif "project" in data and "architecture" in data:
        return "B"
    elif "pipeline_summary" in data or "executive_summary" in data:
        return "C"
    else:
        return "D"


def load_prompt(agent_name: str) -> str:
    """加载 Agent prompt 模板"""
    prompt_dir = Path(__file__).parent.parent / "prompts"
    prompt_file = prompt_dir / f"{agent_name}.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_file}")
    return prompt_file.read_text()


def compute_prompt_sha(prompt_path: Path) -> str:
    """计算 prompt 文件的 SHA256"""
    return hashlib.sha256(prompt_path.read_bytes()).hexdigest()


def get_dependencies(agent_name: str) -> list:
    """获取 Agent 的依赖（执行顺序）"""
    deps = {
        "architect": [],
        "decomposer": ["architect"],
        "specifier": ["architect", "decomposer"],
        "reviewer": ["architect", "decomposer", "specifier"],
        "packager": ["architect", "specifier", "reviewer"]
    }
    return deps.get(agent_name, [])


def get_agent_model(agent_name: str) -> str:
    """获取 Agent 推荐模型层级"""
    # Reviewer 必须用不同模型（避免共谋）
    models = {
        "architect": "strong",      # 强模型（opus/kimi-k2）
        "decomposer": "strong",     # 强模型
        "specifier": "strong",      # 强模型
        "reviewer": "different",    # 不同模型（避免共谋）
        "packager": "fast"          # 中/快模型
    }
    return models.get(agent_name, "strong")


def get_agent_timeout(agent_name: str) -> int:
    """获取 Agent 超时时间（秒）"""
    timeouts = {
        "architect": 300,
        "decomposer": 300,
        "specifier": 300,
        "reviewer": 300,
        "packager": 180
    }
    return timeouts.get(agent_name, 300)


def prepare_agent_task(agent_name: str, input_format: str, run_id: str,
                       input_data: dict, blackboard_dir: str) -> dict:
    """
    准备单个 Agent 的完整 task prompt
    
    包含：
    1. Agent prompt 模板
    2. 输入数据（JSON）
    3. 运行信息（run_id, blackboard_dir, 输出路径）
    4. 格式提示（仅 Architect）
    """
    prompt = load_prompt(agent_name)
    
    # 计算 prompt SHA
    prompt_path = Path(__file__).parent.parent / "prompts" / f"{agent_name}.md"
    prompt_sha = compute_prompt_sha(prompt_path)
    
    # Format hint for Architect（其他 Agent 不需要）
    format_hint = ""
    if agent_name == "architect":
        format_hint = f"\n\n**输入格式已预检测为 Format {input_format}**。请按照 Format {input_format} 的提取规则处理。"
    
    # 构建完整 task prompt
    task = f"""## Agent: {agent_name.title()}

{prompt}
{format_hint}

## 输入数据

```json
{json.dumps(input_data, indent=2, ensure_ascii=False)}
```

## 运行信息

- run_id: {run_id}
- blackboard_dir: {blackboard_dir}
- 请将输出写入: {blackboard_dir}/{agent_name}_output.json
- prompt_sha: {prompt_sha}

## 输出要求

1. 输出必须是合法的 JSON
2. 写入到指定的输出文件
3. 在 _meta 中记录 prompt_sha、model_id、run_id、round
"""
    
    return {
        "agent": agent_name,
        "task": task,
        "timeout_seconds": get_agent_timeout(agent_name),
        "model": get_agent_model(agent_name),
        "depends_on": get_dependencies(agent_name),
        "output_file": f"{blackboard_dir}/{agent_name}_output.json",
        "prompt_sha": prompt_sha
    }


def main():
    if len(sys.argv) < 3:
        print("用法: python3 orchestrator.py <final_result.json> <output_dir>")
        print("\n示例:")
        print("  python3 orchestrator.py /path/to/final_result.json /tmp/ship_pro_run")
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    
    if not input_path.exists():
        print(f"错误: 输入文件不存在: {input_path}")
        sys.exit(1)
    
    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 读取输入
    with open(input_path) as f:
        input_data = json.load(f)
    
    # 检测格式
    fmt = detect_format(input_data)
    print(f"✅ 检测到输入格式: Format {fmt}")
    
    # 生成 run_id
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{fmt.lower()}"
    print(f"✅ Run ID: {run_id}")
    
    # 创建 blackboard
    bb_dir = output_dir / "blackboard"
    bb_dir.mkdir(exist_ok=True)
    
    # 复制输入到 blackboard
    with open(bb_dir / "final_result.json", "w") as f:
        json.dump(input_data, f, indent=2, ensure_ascii=False)
    
    # 准备所有 Agent 的 task
    agents = ["architect", "decomposer", "specifier", "reviewer", "packager"]
    run_config = {
        "run_id": run_id,
        "input_format": fmt,
        "input_file": str(input_path),
        "blackboard_dir": str(bb_dir),
        "agents": {},
        "execution_order": agents,
        "generated_at": datetime.now().isoformat()
    }
    
    for agent in agents:
        task_config = prepare_agent_task(
            agent, fmt, run_id, input_data, str(bb_dir)
        )
        run_config["agents"][agent] = task_config
        print(f"✅ 准备 {agent} task (timeout={task_config['timeout_seconds']}s, model={task_config['model']})")
    
    # 写入 run_config
    config_path = output_dir / "run_config.json"
    with open(config_path, "w") as f:
        json.dump(run_config, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ 运行配置已写入: {config_path}")
    print(f"📋 Agent 执行顺序: {' → '.join(agents)}")
    print(f"📁 Blackboard 目录: {bb_dir}")
    print(f"\n下一步: 主 Agent 读取 run_config.json，按 execution_order 依次调用 sessions_spawn")


if __name__ == "__main__":
    main()
