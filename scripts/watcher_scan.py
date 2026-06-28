#!/usr/bin/env python3
"""
Watcher Scan V3 — Deterministic file scanner + message renderer.

Architecture: Python does 100% deterministic work (scan, state, render).
LLM only routes the pre-rendered message + diagnoses failures.

Usage:
    python3 watcher_scan.py <base_path> <config_path> [options]

Options:
    --state <dir>         State directory (default: base_path)
    --run-start-at <ISO>  Run start timestamp for elapsed calc
    --cron-job-id <id>    Cron job ID (passed through to output)

Output: JSON to stdout
    {
        "action": "progress|completed|failed|timeout|circuit_break|still_running|noop",
        "message": "pre-rendered message text (or empty for noop)",
        "should_remove_cron": bool,
        "error": "error details for LLM failure diagnosis (or null)",
        "cron_job_id": "passed through from --cron-job-id",
        "stages": [...], "completed": {...}, "state": {...}
    }
"""
import argparse
import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Defensive helpers (ported from pipeline_watcher.py V2)
# ---------------------------------------------------------------------------

def atomic_write(path: Path, content: str) -> None:
    """Atomic write via tmp + os.replace. Prevents half-written state files."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(str(tmp), str(path))


def load_json(path: Path) -> Optional[Dict]:
    """Load JSON, None on any failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def parse_timestamp(ts: str) -> Optional[datetime]:
    """Parse ISO timestamp with tolerance. Uses LOCAL tz when unspecified."""
    if not ts:
        return None
    local_tz = datetime.now().astimezone().tzinfo
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=local_tz)
    except (ValueError, TypeError):
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(ts, fmt).replace(tzinfo=local_tz)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# State migration (V2 → V3 compat)
# ---------------------------------------------------------------------------

def _migrate_legacy_state(state_dir: Path) -> None:
    """Merge V2 state files into unified .watcher_state.json.

    V2 used separate files: .watcher_seen.json, .notified_stages.json,
    .cron_run_count, .watcher_no_output_count. V3 unifies into one.
    Only runs once (skips if .watcher_state.json already exists).
    """
    unified = state_dir / ".watcher_state.json"
    if unified.is_file():
        return  # Already migrated

    data: Dict[str, Any] = {"schema_version": "watcher_state/v3"}

    # Seen stages
    for name in (".watcher_seen.json", ".notified_stages.json"):
        d = load_json(state_dir / name)
        if isinstance(d, list):
            data["seen_stages"] = d
            break

    # Run count
    rc = load_json(state_dir / ".cron_run_count")
    if isinstance(rc, dict):
        data["run_count"] = rc.get("count", 0)
        data["run_start_at"] = rc.get("run_start_at", "")

    # No-output count
    noc = load_json(state_dir / ".watcher_no_output_count")
    if isinstance(noc, dict):
        data["no_output_count"] = noc.get("count", 0)

    if len(data) > 1:  # More than just schema_version
        atomic_write(unified, json.dumps(data, ensure_ascii=False))


# ---------------------------------------------------------------------------
# SafeDict for template rendering (prevents KeyError on missing keys)
# ---------------------------------------------------------------------------

class SafeDict(dict):
    """Dict that returns '{key}' for missing keys instead of raising KeyError."""
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


# ---------------------------------------------------------------------------
# Run counter + timeout
# ---------------------------------------------------------------------------

class RunCounter:
    def __init__(self, state: Dict, limits: Dict, run_start_at: str):
        self.max_runs = limits.get("max_runs", 20)
        self.timeout_min = limits.get("timeout_minutes", 60)
        self.run_start_at = run_start_at
        self.count = state.get("run_count", 0)

    def increment(self) -> int:
        self.count += 1
        return self.count

    def is_timeout(self) -> bool:
        start = parse_timestamp(self.run_start_at)
        if start and (datetime.now(start.tzinfo or timezone.utc) - start).total_seconds() / 60 > self.timeout_min:
            return True
        return self.count > self.max_runs


# ---------------------------------------------------------------------------
# Completion checker (with timestamp validation)
# ---------------------------------------------------------------------------

class CompletionChecker:
    def __init__(self, base_path: Path, detection: Dict, run_start_at: str):
        self.file = base_path / detection.get("completed_file", ".completed")
        self.ts_field = detection.get("completed_timestamp_field", "completed_at")
        self.run_start_at = run_start_at

    def check(self) -> Optional[Dict]:
        data = load_json(self.file)
        if not data or data.get("status") not in ("completed", "failed"):
            return None
        # Timestamp validation: reject stale .completed from previous runs
        ts = parse_timestamp(data.get(self.ts_field, ""))
        start = parse_timestamp(self.run_start_at)
        if ts and start and ts < start:
            return None
        return data


# ---------------------------------------------------------------------------
# Stage detector (glob + stale filter + merge_group)
# ---------------------------------------------------------------------------

class StageDetector:
    def __init__(self, base_path: Path, detection: Dict, run_start_at: str = ""):
        self.base_path = base_path
        self.scan_dirs = detection.get("scan_dirs", [])
        self.run_start_dt = parse_timestamp(run_start_at) if run_start_at else None
        self._all: List[Dict] = []

    def _is_stale(self, file_path: Path) -> bool:
        """Reject files created before this run started."""
        if not self.run_start_dt:
            return False
        try:
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
            return mtime < self.run_start_dt
        except (OSError, ValueError):
            return False

    def scan(self) -> List[Dict]:
        """Scan all configured directories, return stage info list.
        
        merge_group handling: if multiple files share the same merge_group,
        the stage is counted once (as completed) when ANY file in the group exists.
        """
        found: Dict[str, Dict] = {}
        merge_groups_seen: Set[str] = set()
        
        for sd in self.scan_dirs:
            dir_p = self.base_path / sd["path"] if sd["path"] != "." else self.base_path
            if not dir_p.is_dir():
                continue
            matches = (dir_p.rglob(sd.get("pattern", "*.json"))
                       if sd.get("dir_mode") == "nested"
                       else dir_p.glob(sd.get("pattern", "*.json")))
            for p in matches:
                if p.is_file() and not self._is_stale(p):
                    fname = p.name
                    if fname in sd.get("stage_files", {}):
                        info = sd["stage_files"][fname]
                        mg = info.get("merge_group")
                        if mg:
                            if mg not in merge_groups_seen:
                                merge_groups_seen.add(mg)
                                found[fname] = info  # First file in group
                        else:
                            found[fname] = info

        self._all = sorted(found.values(), key=lambda x: x.get("seq", 0))
        return self._all

    def all_stages(self) -> List[Dict]:
        return self._all


# ---------------------------------------------------------------------------
# Circuit breaker (consecutive no-output counter)
# ---------------------------------------------------------------------------

class CircuitBreaker:
    def __init__(self, state: Dict, limits: Dict):
        self.threshold = limits.get("circuit_breaker_threshold", 3)
        self.count = state.get("no_output_count", 0)

    def record_no_output(self) -> int:
        self.count += 1
        return self.count

    def reset(self) -> None:
        self.count = 0

    def should_break(self) -> bool:
        return self.count >= self.threshold


# ---------------------------------------------------------------------------
# Message rendering helpers (UI v3, ported from pipeline_watcher.py)
# ---------------------------------------------------------------------------

def _progress_bar(completed: int, total: int, width: int = 20) -> str:
    if total <= 0:
        return "░" * width
    filled = min(int(width * completed / total), width)
    return "█" * filled + "░" * (width - filled)


def _estimate_remaining(elapsed_min: int, completed: int, total: int) -> str:
    if completed <= 0 or elapsed_min <= 0:
        return "计算中"
    avg = elapsed_min / completed
    remaining = int(avg * (total - completed))
    if remaining < 1:
        return "即将完成"
    if remaining >= 60:
        return f"{remaining // 60}h{remaining % 60}m"
    return f"{remaining}m"


def _phase_defs(cfg: Dict) -> List[Tuple[str, int, str]]:
    """Extract unique (name, seq, icon) phases from config."""
    seen: Dict[Tuple[str, int], str] = {}
    for sd in cfg.get("detection", {}).get("scan_dirs", []):
        for _fname, info in sd.get("stage_files", {}).items():
            key = (info["name"], info.get("seq", 0))
            if key not in seen:
                seen[key] = info.get("icon", "❓")
    return [(n, s, i) for (n, s), i in sorted(seen.items(), key=lambda x: x[0][1])]


def _build_icon_chain(completed_seqs: Set[int], current_seq: int, cfg: Dict) -> str:
    parts = []
    for _name, seq, icon in _phase_defs(cfg):
        if seq in completed_seqs:
            parts.append(f"{icon}✅")
        elif seq == current_seq:
            parts.append(f"{icon}⏳")
        else:
            parts.append(f"{icon}○")
    return " ".join(parts)


def _build_detail_list(completed_seqs: Set[int], failed_seqs: Set[int],
                       current_seq: int, cfg: Dict) -> str:
    phases = _phase_defs(cfg)
    if not phases:
        return ""
    max_name = max(len(n) for n, _s, _i in phases)
    lines = []
    for name, seq, icon in phases:
        if seq in failed_seqs:
            status = "❌ 失败"
        elif seq in completed_seqs:
            status = "✅ 完成"
        elif seq == current_seq:
            status = "⏳ 进行中"
        else:
            status = "○ 待开始"
        lines.append(f"  {icon} {name.ljust(max_name)}  {status}")
    return "\n".join(lines)


def _project_short(base_path: str) -> str:
    basename = os.path.basename(base_path.rstrip("/"))
    parts = basename.split("_")
    return parts[0] if len(parts) >= 2 else basename[:12] or "Pipeline"


def _elapsed_v3(run_start_at: str) -> str:
    s = parse_timestamp(run_start_at)
    if not s:
        return "—"
    m = max(0, int((datetime.now(s.tzinfo or timezone.utc) - s).total_seconds() / 60))
    if m >= 60:
        return f"{m // 60}h{m % 60}m"
    return f"{m}m"


def _elapsed_minutes(run_start_at: str) -> int:
    s = parse_timestamp(run_start_at)
    if not s:
        return 0
    return max(0, int((datetime.now(s.tzinfo or timezone.utc) - s).total_seconds() / 60))


def _get_completed_seqs(base: Path, cfg: Dict) -> Tuple[Set[int], Set[int], int]:
    """Read .stage_progress.json for completed/failed seqs + current phase.

    Falls back to empty sets if file missing.
    """
    # Try stages/.stage_progress.json first, then base/.stage_progress.json
    for sub in ("stages", ".", ""):
        sp_path = base / sub / ".stage_progress.json" if sub else base / ".stage_progress.json"
        sp = load_json(sp_path)
        if sp:
            completed = set(sp.get("completed_phases", []))
            failed = set(sp.get("failed_phases", []))
            current = sp.get("current_phase", 0)
            return completed, failed, current
    return set(), set(), 0


# ---------------------------------------------------------------------------
# Message renderers (Python format_map + SafeDict, from config templates)
# ---------------------------------------------------------------------------

_REQUIRED_TPL_KEYS = {"progress", "completed", "failed", "timeout", "circuit_break"}


def _render_ctx(cfg: Dict, completed_count: int, **kw: Any) -> SafeDict:
    """Build template context dict with SafeDict fallback."""
    total = cfg["detection"]["total_stages"]
    return SafeDict(
        display_name=cfg.get("display_name", "Pipeline"),
        completed=completed_count,
        total=total,
        final_artifact=cfg["detection"].get("final_artifact", ""),
        base_path=cfg.get("base_path", ""),
        project_short=_project_short(cfg.get("base_path", "")),
        **kw,
    )


def render_progress(cfg: Dict, stages: List[Dict], run_start_at: str) -> str:
    """Render progress message using config template."""
    phase_defs = _phase_defs(cfg)
    completed_seqs, failed_seqs, current_seq = _get_completed_seqs(
        Path(cfg.get("base_path", "")), cfg)

    # Fallback: if no stage_progress, use scanned stages
    if not completed_seqs and stages:
        completed_seqs = {s.get("seq", 0) for s in stages}

    completed_count = len(completed_seqs)
    total = cfg["detection"]["total_stages"]

    # Current phase name
    current_name = "运行中"
    for name, seq, _icon in phase_defs:
        if seq not in completed_seqs:
            current_name = name
            break

    elapsed_min = _elapsed_minutes(run_start_at)
    bar = _progress_bar(completed_count, total)
    chain = _build_icon_chain(completed_seqs, current_seq, cfg)
    remaining = _estimate_remaining(elapsed_min, completed_count, total)
    detail = _build_detail_list(completed_seqs, failed_seqs, current_seq, cfg)

    ctx = _render_ctx(cfg, completed_count,
                      stage_lines="",  # legacy compat
                      elapsed=_elapsed_v3(run_start_at),
                      elapsed_time=_elapsed_v3(run_start_at),
                      progress_bar=bar,
                      icon_chain=chain,
                      remaining=remaining,
                      current_phase_name=current_name,
                      detail_list=detail,
                      artifact_count=len(stages))
    tpl = cfg.get("templates", {}).get("progress", "{display_name} {progress_bar} {completed}/{total}")
    return tpl.format_map(ctx)


def render_completed(cfg: Dict, comp_data: Dict, run_start_at: str) -> str:
    total = cfg["detection"]["total_stages"]
    all_seqs = {s for _n, s, _i in _phase_defs(cfg)}
    bar = _progress_bar(total, total)
    ctx = _render_ctx(cfg, total,
                      elapsed=_elapsed_v3(run_start_at),
                      elapsed_time=_elapsed_v3(run_start_at),
                      score=comp_data.get("score", "N/A"),
                      progress_bar=bar,
                      icon_chain=_build_icon_chain(all_seqs, 0, cfg),
                      error=comp_data.get("error", "未知"))
    tpl = cfg.get("templates", {}).get("completed", "✅ {display_name} 完成！")
    return tpl.format_map(ctx)


def render_failed(cfg: Dict, comp_data: Dict, run_start_at: str) -> str:
    completed_seqs, _, _ = _get_completed_seqs(Path(cfg.get("base_path", "")), cfg)
    ctx = _render_ctx(cfg, len(completed_seqs),
                      elapsed=_elapsed_v3(run_start_at),
                      elapsed_time=_elapsed_v3(run_start_at),
                      error=comp_data.get("error", "未知"))
    tpl = cfg.get("templates", {}).get("failed", "⚠️ {display_name}失败")
    return tpl.format_map(ctx)


def render_timeout(cfg: Dict) -> str:
    ctx = _render_ctx(cfg, 0,
                      timeout_min=cfg["limits"].get("timeout_minutes", 60),
                      timeout_minutes=cfg["limits"].get("timeout_minutes", 60))
    tpl = cfg.get("templates", {}).get("timeout", "⚠️ {display_name}超时")
    return tpl.format_map(ctx)


def render_circuit_break(cfg: Dict, failures: int) -> str:
    ctx = _render_ctx(cfg, 0, failures=failures)
    tpl = cfg.get("templates", {}).get("circuit_break", "⚠️ 连续 {failures} 次无输出")
    return tpl.format_map(ctx)


def render_still_running(cfg: Dict, stages: List[Dict], run_start_at: str) -> str:
    """Render 'still running' message when circuit breaker resets."""
    phase_defs = _phase_defs(cfg)
    completed_seqs, failed_seqs, current_seq = _get_completed_seqs(
        Path(cfg.get("base_path", "")), cfg)
    if not completed_seqs and stages:
        completed_seqs = {s.get("seq", 0) for s in stages}

    completed_count = len(completed_seqs)
    total = cfg["detection"]["total_stages"]
    current_name = "运行中"
    for name, seq, _icon in phase_defs:
        if seq not in completed_seqs:
            current_name = name
            break

    bar = _progress_bar(completed_count, total)
    detail = _build_detail_list(completed_seqs, failed_seqs, current_seq, cfg)
    ctx = _render_ctx(cfg, completed_count,
                      elapsed=_elapsed_v3(run_start_at),
                      elapsed_time=_elapsed_v3(run_start_at),
                      progress_bar=bar,
                      remaining=_estimate_remaining(
                          _elapsed_minutes(run_start_at), completed_count, total),
                      current_phase_name=current_name,
                      detail_list=detail)
    # Use progress template with a "still running" prefix
    tpl = cfg.get("templates", {}).get("progress", "{display_name} {progress_bar} {completed}/{total}")
    return f"🟡 {tpl.format_map(ctx)}"


# ---------------------------------------------------------------------------
# Auto-chain trigger writer
# ---------------------------------------------------------------------------

def write_auto_chain(cfg: Dict, base_path: Path, comp_data: Dict) -> Optional[str]:
    ac = cfg.get("auto_chain", {})
    next_pl = ac.get("next_pipeline")
    if not next_pl or not ac.get("enabled", False):
        return None

    trigger = {
        "source_pipeline": cfg["pipeline_id"],
        "completed_at": comp_data.get("completed_at", ""),
        "base_path": str(base_path),
    }
    atomic_write(base_path / ac.get("trigger_file", ".auto_chain_trigger"),
                 json.dumps(trigger, ensure_ascii=False))
    return next_pl


# ---------------------------------------------------------------------------
# JSON output helper
# ---------------------------------------------------------------------------

def emit(action: str, message: str = "", should_remove: bool = False,
         error: str = None, cron_job_id: str = "", **extra: Any) -> None:
    """Print JSON result and exit."""
    result: Dict[str, Any] = {
        "action": action,
        "message": message,
        "should_remove_cron": should_remove,
        "error": error,
        "cron_job_id": cron_job_id,
    }
    result.update(extra)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    sys.exit(0)


# ---------------------------------------------------------------------------
# Main pipeline logic
# ---------------------------------------------------------------------------

def _run(cfg: Dict, base: Path, state_dir: Path, args: Any) -> None:
    cron_id = args.cron_job_id
    run_start_at = args.run_start_at

    # ── Migrate V2 state files if needed ──
    _migrate_legacy_state(state_dir)

    # ── Load unified state ──
    state_path = state_dir / ".watcher_state.json"
    state = load_json(state_path) or {"schema_version": "watcher_state/v3"}

    # ── Inject base_path into config for template rendering ──
    cfg["base_path"] = str(base)

    # ── Validate templates ──
    config_templates = cfg.get("templates", {})
    missing = _REQUIRED_TPL_KEYS - set(config_templates.keys())
    if missing:
        emit("failed", error=f"watcher_config.json 缺少必需模板: {missing}",
             should_remove=True, cron_job_id=cron_id)

    # ── Run counter + timeout ──
    rc = RunCounter(state, cfg["limits"], run_start_at)
    rc.increment()
    if rc.is_timeout():
        msg = render_timeout(cfg)
        _save_state(state_path, state, rc, None)
        emit("timeout", msg, should_remove=True, cron_job_id=cron_id)

    # ── Completion check ──
    cc = CompletionChecker(base, cfg["detection"], run_start_at)
    comp = cc.check()
    if comp:
        status = comp.get("status", "")
        if status == "completed":
            msg = render_completed(cfg, comp, run_start_at)
            next_pl = write_auto_chain(cfg, base, comp)
            if next_pl:
                msg += f"\n\n🔗 自动触发下游管线: {next_pl}"
            _save_state(state_path, state, rc, None)
            emit("completed", msg, should_remove=True, cron_job_id=cron_id)
        elif status == "failed":
            msg = render_failed(cfg, comp, run_start_at)
            error_detail = comp.get("error", "unknown")
            _save_state(state_path, state, rc, None)
            emit("failed", msg, should_remove=True,
                 error=error_detail, cron_job_id=cron_id)

    # ── Stage detection ──
    sd = StageDetector(base, cfg["detection"], run_start_at)
    all_stages = sd.scan()

    # ── Diff against seen stages ──
    seen = set(state.get("seen_stages", []))
    current_names = {s["name"] for s in all_stages}
    new_names = current_names - seen
    has_new = len(new_names) > 0

    if has_new:
        # Reset circuit breaker on new stage detection
        cb = CircuitBreaker(state, cfg["limits"])
        cb.reset()
        msg = render_progress(cfg, all_stages, run_start_at)
        state["seen_stages"] = sorted(seen | current_names)
        state["no_output_count"] = cb.count
        _save_state(state_path, state, rc, None)
        # Deduplicate stages by (name, seq) for merge_group support
        seen_phase_keys: set = set()
        unique_stages = []
        for s in all_stages:
            key = (s["name"], s["seq"])
            if key not in seen_phase_keys:
                seen_phase_keys.add(key)
                unique_stages.append({"name": s["name"], "seq": s["seq"], "icon": s.get("icon", "📄")})
        emit("progress", msg, cron_job_id=cron_id,
             stages=unique_stages,
             completed_count=len({s.get("seq", 0) for s in all_stages}))

    # ── Circuit breaker ──
    cb = CircuitBreaker(state, cfg["limits"])
    no_output_count = cb.record_no_output()

    if cb.should_break():
        # Check if orchestrator is still running before breaking
        sp_path = base / "stages" / ".stage_progress.json"
        sp = load_json(sp_path)
        if sp and sp.get("status") == "running":
            cb.reset()
            msg = render_still_running(cfg, all_stages, run_start_at)
            state["no_output_count"] = cb.count
            _save_state(state_path, state, rc, None)
            emit("still_running", msg, cron_job_id=cron_id)

        msg = render_circuit_break(cfg, no_output_count)
        state["no_output_count"] = no_output_count
        _save_state(state_path, state, rc, None)
        emit("circuit_break", msg, should_remove=True, cron_job_id=cron_id)

    # ── No-op ──
    state["no_output_count"] = no_output_count
    _save_state(state_path, state, rc, None)
    emit("noop", cron_job_id=cron_id)


def _save_state(state_path: Path, state: Dict, rc: RunCounter,
                cb: Optional[CircuitBreaker]) -> None:
    """Persist unified state atomically."""
    state["run_count"] = rc.count
    state["run_start_at"] = rc.run_start_at
    if cb:
        state["no_output_count"] = cb.count
    state["last_updated"] = datetime.now().astimezone().isoformat()
    atomic_write(state_path, json.dumps(state, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="DeepFlow Watcher Scan V3")
    ap.add_argument("base_path", help="Pipeline output directory")
    ap.add_argument("config_path", help="watcher_config.json path")
    ap.add_argument("--state", default=None, help="State dir (default: base_path)")
    ap.add_argument("--run-start-at", default="", help="Run start ISO timestamp")
    ap.add_argument("--cron-job-id", default="", help="Cron job ID (pass-through)")
    args = ap.parse_args()

    base = Path(args.base_path)
    state_dir = Path(args.state) if args.state else base

    # Load config
    cfg = load_json(Path(args.config_path))
    if cfg is None:
        emit("failed", error=f"Cannot read config: {args.config_path}",
             should_remove=False, cron_job_id=args.cron_job_id)

    # Validate required fields
    for key in ("pipeline_id", "display_name", "limits", "detection"):
        if key not in cfg:
            emit("failed", error=f"Config missing required field: {key}",
                 should_remove=False, cron_job_id=args.cron_job_id)

    # Ensure state dir exists
    state_dir.mkdir(parents=True, exist_ok=True)

    # File lock (prevent concurrent watcher runs)
    lock_f = open(state_dir / ".watcher_scan.lock", "w")
    try:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        emit("noop", cron_job_id=args.cron_job_id)  # Another instance running

    try:
        _run(cfg, base, state_dir, args)
    except Exception as e:
        import traceback
        emit("failed", error=f"Watcher scan error: {e}\n{traceback.format_exc()}",
             should_remove=False, cron_job_id=args.cron_job_id)
    finally:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
        lock_f.close()


if __name__ == "__main__":
    main()
