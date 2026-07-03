#!/usr/bin/env python3
"""
Ship Pro - 启动脚本

用法:
    python3 run_ship_pro.py \
        --solution-pro-output /path/to/solution_pro_output.json \
        --blackboard-path /path/to/blackboard
"""
import argparse
import json
import logging
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from domains.ship_pro.agent import ShipAgent

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Ship Pro 启动脚本')
    parser.add_argument(
        '--solution-pro-output',
        type=str,
        required=True,
        help='Solution Pro 输出文件路径（JSON）'
    )
    parser.add_argument(
        '--blackboard-path',
        type=str,
        required=True,
        help='Blackboard 目录路径'
    )
    
    args = parser.parse_args()
    
    # 验证输入文件
    solution_pro_output_path = Path(args.solution_pro_output)
    if not solution_pro_output_path.exists():
        logger.error(f"Solution Pro 输出文件不存在: {solution_pro_output_path}")
        sys.exit(1)
    
    # 验证 Blackboard 路径
    blackboard_path = Path(args.blackboard_path)
    blackboard_path.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"🚀 Starting Ship Pro")
    logger.info(f"  Solution Pro Output: {solution_pro_output_path}")
    logger.info(f"  Blackboard Path: {blackboard_path}")
    
    try:
        # 初始化 Agent
        agent = ShipAgent(
            blackboard_path=blackboard_path,
            solution_pro_output_path=solution_pro_output_path
        )
        
        # 运行完整流程
        ship_package = agent.run()
        
        logger.info(f"✅ Ship Pro completed successfully")
        logger.info(f"  Output: {blackboard_path / 'stages' / 'ship_package.json'}")
        
        # 输出摘要
        print("\n" + "=" * 70)
        print("📦 Ship Package Summary")
        print("=" * 70)
        print(f"  Solution Name: {ship_package.get('solution_name', 'N/A')}")
        print(f"  Work Packages: {len(ship_package.get('work_packages', []))}")
        print(f"  Dependencies: {len(ship_package.get('dependency_graph', {}).get('edges', []))}")
        print(f"  Optional Suggestions: {len(ship_package.get('optional_suggestions', []))}")
        print("=" * 70)
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Ship Pro failed: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
