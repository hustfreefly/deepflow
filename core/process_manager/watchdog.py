"""
独立 Watchdog 进程

解决 V37/V39 "卡死 75 分钟无人知" 问题：
- 之前：心跳检测是被动轮询，无主动告警守护进程
- 现在：独立 watchdog（cron 1min）扫描心跳过期 + webhook 告警

契约笼方法：所有告警必须通过 WatchdogAlertContract 验证。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional
import requests

from .contracts import WatchdogAlertContract
from .state import SingleSourceStateManager


class Watchdog:
    """
    独立 Watchdog 进程
    
    职责：
    - 定期扫描 .runs/*.run.json 心跳过期
    - 检测 stall 并发送告警
    - 支持 webhook 通知
    """
    
    def __init__(
        self,
        session_dir: str | Path,
        webhook_url: Optional[str] = None,
        heartbeat_threshold: int = 1800,  # 30 分钟
    ):
        self.session_dir = Path(session_dir)
        self.webhook_url = webhook_url
        self.heartbeat_threshold = heartbeat_threshold
        self.state_manager = SingleSourceStateManager(session_dir)
        self.alerts_dir = self.session_dir / ".alerts"
        self.alerts_dir.mkdir(exist_ok=True)
    
    def scan_and_alert(self) -> list[dict]:
        """
        扫描所有模块，检测 stall 并发送告警
        
        Returns:
            告警列表
        """
        alerts = []
        
        # 扫描所有模块
        modules = ["planning", "research", "summary"]
        for module in modules:
            status = self.state_manager.get_module_status(module)
            
            # 检查是否 stall
            if status.get("status") == "running":
                last_heartbeat = status.get("last_heartbeat", 0)
                age = time.time() - last_heartbeat
                
                if age > self.heartbeat_threshold:
                    # 创建告警
                    alert = self._create_alert(
                        alert_type="stall",
                        module=module,
                        run_id=status.get("run_id"),
                        message=f"Module {module} stalled: heartbeat age {age:.0f}s > {self.heartbeat_threshold}s",
                        details={
                            "heartbeat_age": age,
                            "threshold": self.heartbeat_threshold,
                            "last_heartbeat": last_heartbeat,
                        },
                    )
                    alerts.append(alert)
                    
                    # 发送告警
                    self._send_alert(alert)
        
        return alerts
    
    def _create_alert(
        self,
        alert_type: str,
        module: Optional[str],
        run_id: Optional[str],
        message: str,
        details: dict,
    ) -> dict:
        """创建告警（通过契约验证）"""
        # 从 session_dir 提取 session_id
        session_id = self.session_dir.name
        
        alert_data = {
            "alert_type": alert_type,
            "session_id": session_id,
            "module": module,
            "run_id": run_id,
            "message": message,
            "timestamp": time.time(),
            "details": details,
        }
        
        # 契约验证
        alert_contract = WatchdogAlertContract(**alert_data)
        
        # 写入告警文件
        alert_file = self.alerts_dir / f"alert_{int(time.time())}_{alert_type}.json"
        alert_file.write_text(
            json.dumps(alert_contract.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        
        return alert_contract.model_dump()
    
    def _send_alert(self, alert: dict) -> None:
        """发送告警（webhook）"""
        if not self.webhook_url:
            print(f"WATCHDOG_ALERT: {alert['message']}", flush=True)
            return
        
        try:
            response = requests.post(
                self.webhook_url,
                json=alert,
                timeout=10,
            )
            if response.status_code == 200:
                print(f"WATCHDOG_ALERT_SENT: {alert['message']}", flush=True)
            else:
                print(f"WATCHDOG_ALERT_FAILED: HTTP {response.status_code}", flush=True)
        except Exception as e:
            print(f"WATCHDOG_ALERT_ERROR: {e}", flush=True)
    
    def get_recent_alerts(self, minutes: int = 60) -> list[dict]:
        """获取最近的告警"""
        cutoff = time.time() - (minutes * 60)
        alerts = []
        
        for alert_file in self.alerts_dir.glob("alert_*.json"):
            try:
                alert = json.loads(alert_file.read_text(encoding="utf-8"))
                if alert.get("timestamp", 0) > cutoff:
                    alerts.append(alert)
            except Exception:
                continue
        
        return sorted(alerts, key=lambda x: x.get("timestamp", 0), reverse=True)


def run_watchdog_once(session_dir: str, webhook_url: Optional[str] = None) -> None:
    """
    运行一次 watchdog 扫描（供 cron 调用）
    
    Usage:
        python -m core.process_manager.watchdog /path/to/session [webhook_url]
    """
    watchdog = Watchdog(session_dir, webhook_url)
    alerts = watchdog.scan_and_alert()
    
    if alerts:
        print(f"WATCHDOG_SCAN: {len(alerts)} alerts found", flush=True)
    else:
        print(f"WATCHDOG_SCAN: no alerts", flush=True)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m core.process_manager.watchdog <session_dir> [webhook_url]")
        sys.exit(1)
    
    session_dir = sys.argv[1]
    webhook_url = sys.argv[2] if len(sys.argv) > 2 else None
    
    run_watchdog_once(session_dir, webhook_url)
