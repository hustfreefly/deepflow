"""Deliver Pro Pulse CLI — 脉冲调度的 exec 入口（Pulse V1, 2026-07-24）。

用法:
    python3 -m domains.deliver_pro.pulse_cli pulse --project "X"
        运行一次脉冲扫描，动作落盘 _pulse_actions.json 并打印到 stdout。
        exit code: 0=active/idle/blocked/frozen（blocked/frozen 是结构化已知状态，非失败）,
                   2=locked, 3=completed

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
    
    # === P1-C (2026-08-14): 熔断保护 ===
    # CircuitBreakerTripped 可能发生在构造器（ship_package 加载）或 pulse 内任意
    # SafeJsonLoader 加载点 → 写冻结标记 + 结构化 frozen 报告（一次性 CRITICAL 告警）。
    # 后续 pulse 走 frozen 快速通道，直到人工 `unfreeze`。
    from domains.deliver_pro.utils.safe_json_loader import CircuitBreakerTripped

    try:
        orch = _load_orchestrator(args.project)
        report = orch.pulse()
    except CircuitBreakerTripped as e:
        from domains.deliver_pro.orchestrator import circuit_breaker_freeze
        report = circuit_breaker_freeze(args.project, e)
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
    # active/idle/blocked/frozen → 0（已处理状态；2026-08-14 前前置缺失直接崩 ValueError
    # → launchd 每 5 分钟误报失败，现为结构化状态）
    return 0


def cmd_confirm(args) -> int:
    # P1-D (2026-08-14): worker 回执 JSON 显式处理解析失败（不裸 traceback）
    try:
        if args.results_file:
            results = json.loads(Path(args.results_file).read_text())  # safe-json: JSONDecodeError 下方显式处理
        elif args.results:
            results = json.loads(args.results)  # safe-json: CLI 字符串输入，JSONDecodeError 下方显式处理
        else:
            print("ERROR: --results or --results-file required", file=sys.stderr)
            return 1
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: results JSON 解析/读取失败: {e}", file=sys.stderr)
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
    from domains.deliver_pro.orchestrator import (
        PULSE_BLOCKED_FILENAME,
        PULSE_CIRCUIT_BREAKER_FILENAME,
        PULSE_COMPLETED_FILENAME,
    )

    project_dir = BLACKBOARD_ROOT / args.project
    if (project_dir / PULSE_COMPLETED_FILENAME).exists():
        print(f"completed: {args.project} pipeline 已终态（.deliver_completed.json 存在）")
        return 1
    if (project_dir / PULSE_CIRCUIT_BREAKER_FILENAME).exists():
        print(f"frozen: {args.project} 已熔断冻结（_circuit_breaker.json），排查后 pulse_cli unfreeze 解除")
        return 1
    if (project_dir / PULSE_BLOCKED_FILENAME).exists():
        print(f"blocked: {args.project} 前置条件缺失（_pulse_blocked.json），补齐 living_spec 后自愈")
        return 1
    try:
        find_ship_package_path(args.project)
    except FileNotFoundError:
        print(f"no_ship_package: {args.project} 无 ship package，无法调度")
        return 1
    print(f"work_remains: {args.project} 有待调度工作")
    return 0


def cmd_unfreeze(args) -> int:
    """解除熔断冻结（2026-08-14 P1-C）：删除冻结标记 + 全部损坏计数器。

    注意：不修复损坏源（LLM 持续产出坏 JSON / 并发写入）的话，
    解冻后连续 3 次损坏会再次触发熔断。
    """
    from domains.deliver_pro import BLACKBOARD_ROOT
    from domains.deliver_pro.orchestrator import (
        PULSE_BLOCKED_FILENAME,
        PULSE_CIRCUIT_BREAKER_FILENAME,
    )

    project_dir = BLACKBOARD_ROOT / args.project
    if not project_dir.exists():
        print(f"ERROR: 项目目录不存在: {project_dir}", file=sys.stderr)
        return 1
    marker = project_dir / PULSE_CIRCUIT_BREAKER_FILENAME
    removed_marker = False
    if marker.exists():
        marker.unlink()
        removed_marker = True
    counters = [p for p in project_dir.rglob(".*.corrupt_count") if p.is_file()]
    for c in counters:
        try:
            c.unlink()
        except OSError:
            pass
    if args.clear_blocked:
        blocked = project_dir / PULSE_BLOCKED_FILENAME
        if blocked.exists():
            blocked.unlink()
            print(f"unfreeze: 同时清除了阻塞标记 _pulse_blocked.json")
    if not removed_marker and not counters:
        print(f"not_frozen: {args.project} 无熔断标记/损坏计数器，无需操作")
        return 0
    print(f"unfrozen: {args.project} 已解除冻结（标记移除={removed_marker}，清理计数器 {len(counters)} 个）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="deliver_pulse_cli")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("pulse", "confirm", "check", "unfreeze"):
        p = sub.add_parser(name)
        p.add_argument("--project", required=True)
        if name == "confirm":
            p.add_argument("--results", default=None)
            p.add_argument("--results-file", default=None)
        if name == "unfreeze":
            p.add_argument("--clear-blocked", action="store_true",
                           help="同时清除 _pulse_blocked.json 阻塞标记")

    args = parser.parse_args()
    if args.command == "pulse":
        return cmd_pulse(args)
    if args.command == "confirm":
        return cmd_confirm(args)
    if args.command == "unfreeze":
        return cmd_unfreeze(args)
    return cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
