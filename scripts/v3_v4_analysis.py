#!/usr/bin/env python3
"""V3/V4 代码识别分析脚本"""

import os
import re
import json
from pathlib import Path
from datetime import datetime

# 配置
WORKSPACE = Path("/Users/allen/.openclaw/workspace")
OUTPUT_FILE = WORKSPACE / ".deepflow/cage/review_v3_v4_identification.json"

# V3 标识
V3_INDICATORS = [
    "PipelineEngine", "Coordinator", "QualityGate", "ResilienceManager",
    "WAITING_AGENT", "resume()", "DeepDiveCoordinator", "HITLState"
]

# V4 标识
V4_INDICATORS = [
    "MasterAgent", "DataManagerWorker", "TaskBuilder", "sessions_spawn",
    "blackboard", "PipelineOrchestrator", "PipelineConfig", "DeepDiveResult"
]

# V4 core 目录中的文件
V4_CORE_FILES = [
    "critic_manager.py", "execution_engine.py", "orchestrator.py",
    "protection_layer.py", "report_generator.py", "result_processor.py",
    "state_manager.py", "utils.py"
]

# V4 skills 完整 core
V4_SKILLS_CORE = [
    "__init__.py", "auto_fix_cycle.py", "blackboard.py", "circuit_breaker.py",
    "config_manager.py", "convergence.py", "critic_manager.py", "domain_config.py",
    "event_bus.py", "exceptions.py", "execution_engine.py", "executor.py",
    "fallback.py", "merger.py", "metrics.py", "mock_generator.py",
    "orchestrator.py", "protection_layer.py", "report_generator.py",
    "result_processor.py", "test_runner.py", "timeout_config.py", "utils.py",
    "verifier.py"
]

def analyze_file(filepath: Path) -> dict:
    """分析单个文件"""
    result = {
        "filename": filepath.name,
        "v3_indicators": [],
        "v4_indicators": [],
        "used_by_v4": False,
        "duplicate_in_core": False,
        "verdict": "uncertain",
        "action": "keep",
        "confidence": 0.5,
        "notes": ""
    }
    
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
        
        # 检查 V3 标识
        for indicator in V3_INDICATORS:
            if indicator in content:
                result["v3_indicators"].append(indicator)
        
        # 检查 V4 标识
        for indicator in V4_INDICATORS:
            if indicator in content:
                result["v4_indicators"].append(indicator)
        
        # 检查是否被 V4 导入 (根目录的core/下的文件)
        if filepath.name in V4_CORE_FILES:
            result["used_by_v4"] = True
            result["duplicate_in_core"] = True
            result["notes"] = f"根目录core/下的文件，与skills/deep-dive-v2.6/core/重复"
        
        # 检查是否被其他文件导入
        if filepath.name == "pipeline_engine.py":
            result["used_by_v4"] = True
            result["notes"] = "被coordinator.py导入"
        elif filepath.name == "coordinator.py":
            result["used_by_v4"] = True
            result["notes"] = "被多个run_*.py文件导入"
        
        # 判定
        v3_count = len(result["v3_indicators"])
        v4_count = len(result["v4_indicators"])
        
        if v3_count > 0 and v4_count == 0:
            if result["used_by_v4"]:
                result["verdict"] = "v3_but_used"
                result["action"] = "migrate"
                result["confidence"] = 0.8
            else:
                result["verdict"] = "v3_legacy"
                result["action"] = "delete"
                result["confidence"] = 0.9
        elif v4_count > 0 and v3_count == 0:
            result["verdict"] = "v4_current"
            result["action"] = "keep"
            result["confidence"] = 0.85
        elif v3_count > 0 and v4_count > 0:
            result["verdict"] = "mixed"
            result["action"] = "review"
            result["confidence"] = 0.7
        else:
            # 无明确标识，检查文件名模式
            if filepath.name.startswith("test_"):
                result["verdict"] = "test_file"
                result["action"] = "review"
                result["confidence"] = 0.6
            elif "run_" in filepath.name or "deep" in filepath.name.lower():
                result["verdict"] = "likely_v3"
                result["action"] = "review"
                result["confidence"] = 0.5
            else:
                result["verdict"] = "uncertain"
                result["action"] = "review"
                result["confidence"] = 0.5
        
    except Exception as e:
        result["notes"] = f"Error reading file: {e}"
    
    return result

def main():
    # 获取所有根目录的.py文件
    py_files = sorted(WORKSPACE.glob("*.py"))
    
    files_analysis = []
    
    for filepath in py_files:
        analysis = analyze_file(filepath)
        files_analysis.append(analysis)
    
    # 统计
    summary = {
        "total_files": len(files_analysis),
        "v3_legacy": sum(1 for f in files_analysis if f["verdict"] == "v3_legacy"),
        "v4_current": sum(1 for f in files_analysis if f["verdict"] == "v4_current"),
        "v3_but_used": sum(1 for f in files_analysis if f["verdict"] == "v3_but_used"),
        "mixed": sum(1 for f in files_analysis if f["verdict"] == "mixed"),
        "test_file": sum(1 for f in files_analysis if f["verdict"] == "test_file"),
        "likely_v3": sum(1 for f in files_analysis if f["verdict"] == "likely_v3"),
        "uncertain": sum(1 for f in files_analysis if f["verdict"] == "uncertain"),
    }
    
    # 构建输出
    output = {
        "review_type": "v3_v4_identification",
        "timestamp": datetime.now().isoformat(),
        "files": files_analysis,
        "summary": summary
    }
    
    # 写入文件
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"Analysis complete. Written to {OUTPUT_FILE}")
    print(f"Summary: {summary}")

if __name__ == "__main__":
    main()
