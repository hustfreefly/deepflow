"""Deliver Pro Pulse CLI — 脉冲调度的 exec 入口（Pulse V1, 2026-07-24）。

用法:
    python3 -m domains.deliver_pro.pulse_cli pulse --project "X"
        运行一次脉冲扫描，动作落盘 _pulse_actions.json 并打印到 stdout。
        exit code: 0=active/idle, 2=locked, 3=completed

    python3 -m domains.deliver_pro.pulse_cli confirm --project "X" --results '<json>'
        spawn 回执（A4 两阶段 dispatch / P1-1 回滚）。
        --results: JSON 数组字符串 '[{"wp_id":"...","label":"...","ok":true,"error":null}]'
        或用 --results-file <path> 从文件读取。

    python3 -m domains.deliver_pro.pulse_cli check --project "X"
        轻量检查（cron 点火前 / 人工检查用）：还有活 → exit 0；已完成或无 ship package → exit 1。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests


def _load_orchestrator(project: str):
    from domains.deliver_pro.orchestrator import DeliverOrchestrator

    return DeliverOrchestrator(project)


def _send_feishu_alert(alerts: list[dict], project: str) -> None:
    """发送飞书告警（仅发送 CRITICAL 级别）。
    
    INVESTIGATION-001: 告警推送通道，确保关键问题能被及时发现。
    
    双通道策略：
    1. 优先使用 FEISHU_WEBHOOK_URL（简单 webhook，无需认证）
    2. 回退使用飞书 API + app_id/app_secret（从 openclaw.json 读取）
    3. 两者都不可用时输出到 stderr（保底）
    """
    # 过滤 CRITICAL 告警
    critical_alerts = [a for a in alerts if a.get("severity") == "CRITICAL"]
    if not critical_alerts:
        return
    
    # 构建告警消息
    message_lines = [f"🚨 Deliver Pro 告警 - {project}", ""]
    for alert in critical_alerts[:5]:  # 最多显示 5 条
        code = alert.get("code", "UNKNOWN")
        msg = alert.get("message", "无详细信息")
        message_lines.append(f"• [{code}] {msg}")
    
    if len(critical_alerts) > 5:
        message_lines.append(f"\n... 还有 {len(critical_alerts) - 5} 条告警")
    
    message = "\n".join(message_lines)
    
    # 通道 1: Webhook（最简单，优先尝试）
    webhook_url = os.getenv("FEISHU_WEBHOOK_URL")
    if webhook_url:
        try:
            response = requests.post(
                webhook_url,
                json={"msg_type": "text", "content": {"text": message}},
                timeout=10,
            )
            if response.status_code == 200:
                print(f"INFO: 飞书告警已发送 (webhook, {len(critical_alerts)} 条)", file=sys.stderr)
                return
            else:
                print(f"WARNING: webhook 告警失败: HTTP {response.status_code}，尝试 API 通道", file=sys.stderr)
        except Exception as e:
            print(f"WARNING: webhook 告警异常: {e}，尝试 API 通道", file=sys.stderr)
    
    # 通道 2: 飞书 API（使用 app_id/app_secret）
    try:
        from core.config_loader import get_feishu_credentials
        
        creds = get_feishu_credentials()
        app_id = creds.get("app_id")
        app_secret = creds.get("app_secret")
        target_open_id = creds.get("target_open_id")
        
        if not app_id or not app_secret:
            print("WARNING: 飞书凭证未配置（app_id/app_secret），跳过 API 告警", file=sys.stderr)
            print(f"CRITICAL_ALERT: {message}", file=sys.stderr)
            return
        
        # 获取 tenant_access_token
        token_resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=10,
        )
        token_data = token_resp.json()
        if token_data.get("code") != 0:
            print(f"WARNING: 飞书 token 获取失败: {token_data.get('msg')}", file=sys.stderr)
            print(f"CRITICAL_ALERT: {message}", file=sys.stderr)
            return
        
        tenant_token = token_data["tenant_access_token"]
        
        # 发送消息
        # 优先发送到 target_open_id（私聊），否则发送到默认群
        if target_open_id:
            send_resp = requests.post(
                "https://open.feishu.cn/open-apis/im/v1/messages",
                params={"receive_id_type": "open_id"},
                json={
                    "receive_id": target_open_id,
                    "msg_type": "text",
                    "content": json.dumps({"text": message}),
                },
                headers={"Authorization": f"Bearer {tenant_token}"},
                timeout=10,
            )
        else:
            # 无 target_open_id 时，尝试发送到默认群（通过 chat_id）
            # 这里简化为输出到 stderr，实际应该配置 chat_id
            print("WARNING: 未配置 target_open_id，无法发送 API 告警", file=sys.stderr)
            print(f"CRITICAL_ALERT: {message}", file=sys.stderr)
            return
        
        send_data = send_resp.json()
        if send_data.get("code") == 0:
            print(f"INFO: 飞书告警已发送 (API, {len(critical_alerts)} 条)", file=sys.stderr)
        else:
            print(f"WARNING: 飞书 API 告警失败: {send_data.get('msg')}", file=sys.stderr)
            print(f"CRITICAL_ALERT: {message}", file=sys.stderr)
    
    except Exception as e:
        print(f"WARNING: 飞书告警发送异常: {e}", file=sys.stderr)
        print(f"CRITICAL_ALERT: {message}", file=sys.stderr)


def cmd_pulse(args) -> int:
    # === INVESTIGATION-001 代码护栏 ===
    # 检测是否在主 agent 中运行，阻止同步调用阻塞消息队列
    session_id = os.environ.get("OPENCLAW_SESSION_ID", "")
    if "main" in session_id.lower() and "cron" not in session_id.lower():
        print("ERROR: pulse 不应在主 agent 中同步执行", file=sys.stderr)
        print("原因：orch.pulse() 执行 30-60 秒，会阻塞用户消息响应", file=sys.stderr)
        print("解决方案：", file=sys.stderr)
        print("  1. 使用 cron + isolated session 模式（推荐）", file=sys.stderr)
        print("  2. 添加 --async 参数使用异步模式", file=sys.stderr)
        print("详见：.deepflow/docs/investigation-001-message-queue-blocking.md", file=sys.stderr)
        return 10  # 特殊退出码：被护栏拦截
    
    # === 写心跳 ===
    # 用于 watchdog 监控 pulse 是否正常运行
    try:
        from domains.deliver_pro import BLACKBOARD_ROOT
        from core.utils.atomic_io import atomic_write_json
        
        heartbeat_path = BLACKBOARD_ROOT / args.project / "_pulse_heartbeat.json"
        atomic_write_json(heartbeat_path, {
            "timestamp": time.time(),
            "pid": os.getpid(),
            "session_id": session_id
        })
    except Exception as e:
        # 心跳写入失败不阻塞 pulse 执行
        print(f"WARNING: 心跳写入失败: {e}", file=sys.stderr)
    
    orch = _load_orchestrator(args.project)
    report = orch.pulse()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    
    # === INVESTIGATION-001: 告警推送 ===
    # 检查是否有 CRITICAL 告警，如果有则发送飞书通知
    alerts = report.get("alerts", [])
    if alerts:
        _send_feishu_alert(alerts, args.project)
    
    status = report.get("status")
    if status == "locked":
        return 2
    if status == "completed":
        return 3
    return 0


def cmd_confirm(args) -> int:
    if args.results_file:
        results = json.loads(Path(args.results_file).read_text())
    elif args.results:
        results = json.loads(args.results)
    else:
        print("ERROR: --results or --results-file required", file=sys.stderr)
        return 1
    if not isinstance(results, list):
        print("ERROR: results must be a JSON array", file=sys.stderr)
        return 1

    # 契约笼子：回执必须通过 SpawnConfirmation 验证（A#2/DryRun R1: 逐条验证，
    # 单条格式错误不拖垮整批 — all-or-nothing 会让全部 spawn 变孤儿）
    from domains.deliver_pro.contracts.pulse_report import SpawnConfirmation

    validated = []
    validation_errors = []
    for i, r in enumerate(results):
        try:
            validated.append(SpawnConfirmation(**r).model_dump(mode="json"))
        except Exception as e:
            validation_errors.append({"index": i, "item": r, "error": str(e)})

    orch = _load_orchestrator(args.project)
    out = orch.confirm_dispatches(validated)
    if validation_errors:
        out["validation_errors"] = validation_errors
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_check(args) -> int:
    from domains.deliver_pro import BLACKBOARD_ROOT, find_ship_package_path
    from domains.deliver_pro.orchestrator import PULSE_COMPLETED_FILENAME

    project_dir = BLACKBOARD_ROOT / args.project
    if (project_dir / PULSE_COMPLETED_FILENAME).exists():
        print(f"completed: {args.project} pipeline 已终态（.deliver_completed.json 存在）")
        return 1
    try:
        find_ship_package_path(args.project)
    except FileNotFoundError:
        print(f"no_ship_package: {args.project} 无 ship package，无法调度")
        return 1
    print(f"work_remains: {args.project} 有待调度工作")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="deliver_pulse_cli")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("pulse", "confirm", "check"):
        p = sub.add_parser(name)
        p.add_argument("--project", required=True)
        if name == "confirm":
            p.add_argument("--results", default=None)
            p.add_argument("--results-file", default=None)

    args = parser.parse_args()
    if args.command == "pulse":
        return cmd_pulse(args)
    if args.command == "confirm":
        return cmd_confirm(args)
    return cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
