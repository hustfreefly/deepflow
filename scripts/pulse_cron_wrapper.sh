#!/usr/bin/env bash
# =============================================================================
# pulse_cron_wrapper.sh — Deliver Pro Pulse Cron 加固 wrapper（A+B）
#
# 解决的问题（2026-08-01 缺陷记录）:
#   pulse CLI 退出码: 0=有活/idle, 2=锁冲突(locked), 3=已完成(completed)
#   cron agentTurn 执行器把"非零退出码"一律当失败 → 项目完成后每 5min 误报
#   "Exec failed: python3 pulse" 刷屏飞书。
#
# 方案 A: 退出码归一化 — 2/3 视为正常结束，只保留真正失败码（1/10/其他）
# 方案 B: 完成即自停 — pulse 返回 completed 时，自动 disable 本项目的
#         deliver_pro_pulse_* cron，项目跑完 cron 自动消失。
#
# 用法:
#   bash scripts/pulse_cron_wrapper.sh <project_name> [cron_job_id]
#     project_name: blackboard 项目目录名
#     cron_job_id : 可选。显式指定要 disable 的 cron id；
#                   省略时自动按 "deliver_pro_pulse_<project>" 匹配。
#
# 输出:
#   stdout: pulse 原始输出（JSON，供 cron agent 解析 actions）
#   stderr: wrapper 自身状态（如 cron 自停提示）
#   exit  : 0=正常结束（含 completed/locked）; 非 0=真失败
# =============================================================================
set -u

PROJECT="${1:-}"
if [ -z "$PROJECT" ]; then
  echo "[pulse_cron_wrapper] ERROR: 缺少 project_name 参数" >&2
  exit 1
fi
CRON_ID="${2:-}"

# 定位 DeepFlow 根目录（脚本在 .deepflow/scripts/ 下）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEEPFLOW_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$DEEPFLOW_ROOT" || { echo "[pulse_cron_wrapper] ERROR: 无法进入 $DEEPFLOW_ROOT" >&2; exit 1; }

# ── 运行 pulse（捕获 stdout+stderr，保持 JSON 可见）──────────────────────
OUTPUT="$(PYTHONPATH=. python3 -m domains.deliver_pro.pulse_cli pulse --project "$PROJECT" 2>&1)"
CODE=$?
echo "$OUTPUT"

# ── 方案 A: 退出码归一化 ─────────────────────────────────────────────────
if [ "$CODE" -eq 2 ] || [ "$CODE" -eq 3 ]; then
  # 2=locked（另一个 pulse 持有锁） / 3=completed（全部完成）→ 都是正常结束
  if [ "$CODE" -eq 3 ]; then
    # ── 方案 B: 完成即自停 ───────────────────────────────────────────────
    if [ -z "$CRON_ID" ]; then
      CRON_ID="$(openclaw cron list 2>/dev/null | grep -F "deliver_pro_pulse_${PROJECT}" | awk '{print $1; exit}')"
    fi
    if [ -n "$CRON_ID" ]; then
      openclaw cron disable "$CRON_ID" >/dev/null 2>&1 && {
        echo "[pulse_cron_wrapper] pipeline completed → cron disabled: $CRON_ID" >&2
      } || {
        echo "[pulse_cron_wrapper] WARNING: 尝试禁用 cron $CRON_ID 失败（忽略）" >&2
      }
    else
      echo "[pulse_cron_wrapper] pipeline completed（未找到对应 pulse cron，跳过自停）" >&2
    fi
  else
    echo "[pulse_cron_wrapper] pulse locked（另一个实例持有锁，视为正常）" >&2
  fi
  exit 0
fi

# 0=还有活（cron 继续空转等待）; 1/10/其他 = 真失败（保留原退出码）
exit "$CODE"
