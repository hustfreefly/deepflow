#!/usr/bin/env python3
"""
Solution Pro 全链路监控程序

监控点：
1. spawn → 模块执行 → 完成确认 → 后置验证
2. 异常告警：stall/timeout/failure 实时通知

使用方式：
    python3 scripts/monitor_solution_pro.py <session_id> [--interval 10]
"""

import sys
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.blackboard.blackboard_manager import BlackboardManager


class SolutionProMonitor:
    """Solution Pro 全链路监控器"""
    
    # 模块执行顺序
    MODULES = ["planning", "research", "summary"]
    
    # 超时阈值（秒）
    TIMEOUTS = {
        "planning": 1800,  # 30分钟
        "research": 3600,  # 60分钟
        "summary": 3600,   # 60分钟
    }
    
    # Stall 检测阈值（秒）
    STALL_THRESHOLD = 300  # 5分钟无进展视为 stall
    
    def __init__(self, session_id: str, interval: int = 10):
        """
        初始化监控器
        
        Args:
            session_id: Solution Pro session ID
            interval: 轮询间隔（秒）
        """
        self.session_id = session_id
        self.interval = interval
        self.bb = BlackboardManager(session_id)
        self.start_time = datetime.now()
        
        # 模块状态追踪
        self.module_status = {
            module: {
                "started": False,
                "completed": False,
                "failed": False,
                "start_time": None,
                "end_time": None,
                "last_progress": None,
            }
            for module in self.MODULES
        }
        
        # 全局状态
        self.session_completed = False
        self.session_failed = False
        self.failure_reason = None
        
        print(f"🔍 Solution Pro 监控启动")
        print(f"   Session ID: {session_id}")
        print(f"   轮询间隔: {interval}秒")
        print(f"   启动时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print()
    
    def check_session_status(self) -> bool:
        """检查 session 整体状态"""
        # 检查是否完成
        if self.bb.stage_exists("final_solution"):
            self.session_completed = True
            print(f"✅ Session 完成！")
            return True
        
        # 检查是否失败
        if self.bb.stage_exists(".failed"):
            self.session_failed = True
            failed_data = self.bb.read_stage(".failed")
            self.failure_reason = failed_data.get("reason", "Unknown") if failed_data else "Unknown"
            print(f"❌ Session 失败: {self.failure_reason}")
            return True
        
        return False
    
    def check_module_progress(self, module: str) -> None:
        """检查模块执行进展"""
        status = self.module_status[module]
        
        # 检查模块是否开始
        prompt_file = f"{module}_prompt.md"
        if not status["started"] and self.bb.stage_exists(prompt_file):
            status["started"] = True
            status["start_time"] = datetime.now()
            status["last_progress"] = datetime.now()
            print(f"🚀 {module} 模块开始执行")
        
        # 检查模块是否完成
        output_files = {
            "planning": "planning_convergence.json",
            "research": "research_consolidator.json",
            "summary": "summary_consolidator.json",
        }
        
        output_file = output_files.get(module)
        if output_file and self.bb.stage_exists(output_file):
            if not status["completed"]:
                status["completed"] = True
                status["end_time"] = datetime.now()
                duration = (status["end_time"] - status["start_time"]).total_seconds()
                print(f"✅ {module} 模块完成 (耗时: {duration:.1f}秒)")
        
        # 检查 stall
        if status["started"] and not status["completed"]:
            # 检查 stages 目录下的文件修改时间
            stages_dir = self.bb.session_dir / "stages"
            if stages_dir.exists():
                latest_mtime = None
                for f in stages_dir.glob(f"{module}*"):
                    if f.is_file():
                        mtime = datetime.fromtimestamp(f.stat().st_mtime)
                        if latest_mtime is None or mtime > latest_mtime:
                            latest_mtime = mtime
                
                if latest_mtime:
                    status["last_progress"] = latest_mtime
                    time_since_progress = (datetime.now() - latest_mtime).total_seconds()
                    
                    if time_since_progress > self.STALL_THRESHOLD:
                        print(f"⚠️  {module} 模块可能 stall (无进展 {time_since_progress:.0f}秒)")
    
    def check_timeouts(self) -> None:
        """检查模块超时"""
        for module, status in self.module_status.items():
            if status["started"] and not status["completed"]:
                elapsed = (datetime.now() - status["start_time"]).total_seconds()
                timeout = self.TIMEOUTS[module]
                
                if elapsed > timeout:
                    print(f"⏰ {module} 模块超时 ({elapsed:.0f}秒 > {timeout}秒)")
    
    def print_status_summary(self) -> None:
        """打印状态摘要"""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        print(f"\n📊 状态摘要 (运行 {elapsed:.0f}秒)")
        print("-" * 60)
        
        for module in self.MODULES:
            status = self.module_status[module]
            
            if status["completed"]:
                icon = "✅"
                state = "完成"
            elif status["started"]:
                icon = "🔄"
                state = "执行中"
            else:
                icon = "⏳"
                state = "等待"
            
            print(f"  {icon} {module:12s} {state}")
        
        print("-" * 60)
    
    def run(self) -> None:
        """运行监控"""
        try:
            while not (self.session_completed or self.session_failed):
                # 检查 session 状态
                if self.check_session_status():
                    break
                
                # 检查各模块进展
                for module in self.MODULES:
                    self.check_module_progress(module)
                
                # 检查超时
                self.check_timeouts()
                
                # 打印状态摘要
                self.print_status_summary()
                
                # 等待下一轮
                time.sleep(self.interval)
        
        except KeyboardInterrupt:
            print("\n\n⚠️  监控被中断")
        
        finally:
            self.print_final_report()
    
    def print_final_report(self) -> None:
        """打印最终报告"""
        print("\n" + "=" * 60)
        print("📋 Solution Pro 执行报告")
        print("=" * 60)
        
        total_duration = (datetime.now() - self.start_time).total_seconds()
        print(f"总耗时: {total_duration:.1f}秒")
        print()
        
        if self.session_completed:
            print("状态: ✅ 成功")
        elif self.session_failed:
            print(f"状态: ❌ 失败")
            print(f"原因: {self.failure_reason}")
        else:
            print("状态: ⚠️  未完成")
        
        print()
        print("模块执行情况:")
        print("-" * 60)
        
        for module in self.MODULES:
            status = self.module_status[module]
            
            if status["completed"]:
                duration = (status["end_time"] - status["start_time"]).total_seconds()
                print(f"  ✅ {module:12s} 完成 (耗时: {duration:.1f}秒)")
            elif status["started"]:
                elapsed = (datetime.now() - status["start_time"]).total_seconds()
                print(f"  🔄 {module:12s} 执行中 (已耗时: {elapsed:.1f}秒)")
            else:
                print(f"  ⏳ {module:12s} 未开始")
        
        print("=" * 60)


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python3 monitor_solution_pro.py <session_id> [--interval 10]")
        sys.exit(1)
    
    session_id = sys.argv[1]
    interval = 10
    
    # 解析可选参数
    if "--interval" in sys.argv:
        idx = sys.argv.index("--interval")
        if idx + 1 < len(sys.argv):
            interval = int(sys.argv[idx + 1])
    
    monitor = SolutionProMonitor(session_id, interval)
    monitor.run()


if __name__ == "__main__":
    main()
