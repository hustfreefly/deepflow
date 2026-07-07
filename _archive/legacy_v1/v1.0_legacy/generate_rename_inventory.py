#!/usr/bin/env python3
"""
DeepClaw → Research Pro 改名清单生成器
契约编号: RENAME-RESEARCH-PRO-V1.0
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Set

WORKSPACE = Path("/Users/allen/.openclaw/workspace")
DEEPFLOW = WORKSPACE / ".deepflow"
SKILLS = WORKSPACE / "skills"

# 要搜索的变体
VARIANTS = ["DeepClaw", "deepclaw", "deep_claw", "DEEPCLAW", "Deep Claw", "deep claw"]

# 排除的目录
EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", "blackboard"}

# 排除的文件模式
EXCLUDE_PATTERNS = {".pyc", ".sqlite", ".db", ".log"}

def should_scan(path: Path) -> bool:
    """判断是否应该扫描该路径"""
    # 排除目录
    if any(exclude in path.parts for exclude in EXCLUDE_DIRS):
        return False
    
    # 排除文件类型
    if any(path.suffix == ext for ext in EXCLUDE_PATTERNS):
        return False
    
    # 只扫描特定类型
    return path.suffix in {".py", ".md", ".yaml", ".yml", ".json", ".txt"}

def scan_files() -> Dict[str, List[tuple]]:
    """扫描所有文件，返回包含 DeepClaw 的文件和行号"""
    results = {variant: [] for variant in VARIANTS}
    
    for root, dirs, files in os.walk(WORKSPACE):
        # 跳过排除的目录
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        for file in files:
            file_path = Path(root) / file
            
            if not should_scan(file_path):
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        for variant in VARIANTS:
                            if variant in line:
                                results[variant].append((str(file_path), line_num, line.strip()))
            except Exception:
                pass
    
    return results

def generate_rename_map() -> Dict[str, str]:
    """生成改名映射表"""
    return {
        "DeepClaw": "ResearchPro",
        "deepclaw": "research_pro",
        "deep_claw": "research_pro",
        "DEEPCLAW": "RESEARCH_PRO",
        "Deep Claw": "Research Pro",
        "deep claw": "research pro",
    }

def main():
    print("=" * 80)
    print("DeepClaw → Research Pro 改名清单")
    print("=" * 80)
    
    # 扫描文件
    print("\n[1/3] 扫描文件...")
    results = scan_files()
    
    # 统计
    total_matches = sum(len(matches) for matches in results.values())
    affected_files = set()
    for matches in results.values():
        for file_path, _, _ in matches:
            affected_files.add(file_path)
    
    print(f"   发现 {total_matches} 处匹配")
    print(f"   影响 {len(affected_files)} 个文件")
    
    # 按变体统计
    print("\n[2/3] 按变体统计:")
    for variant, matches in results.items():
        if matches:
            print(f"   {variant}: {len(matches)} 处")
    
    # 按文件统计
    print("\n[3/3] 按文件统计 (Top 20):")
    file_counts = {}
    for matches in results.values():
        for file_path, _, _ in matches:
            file_counts[file_path] = file_counts.get(file_path, 0) + 1
    
    for file_path, count in sorted(file_counts.items(), key=lambda x: -x[1])[:20]:
        print(f"   {count:3d} | {file_path.replace(str(WORKSPACE), '~')}")
    
    # 保存详细报告
    report_file = DEEPFLOW / "cage" / "rename_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            "total_matches": total_matches,
            "affected_files": len(affected_files),
            "by_variant": {k: len(v) for k, v in results.items()},
            "details": {k: v for k, v in results.items() if v}
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n详细报告已保存: {report_file}")
    
    # 生成改名映射
    print("\n" + "=" * 80)
    print("改名映射表:")
    print("=" * 80)
    rename_map = generate_rename_map()
    for old, new in rename_map.items():
        print(f"   {old:20s} → {new}")

if __name__ == "__main__":
    main()
