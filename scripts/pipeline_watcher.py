#!/usr/bin/env python3
"""Pipeline Watcher V2 — deterministic pipeline progress monitor."""
import argparse, fcntl, json, os, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

def atomic_write(path: Path, content: str) -> None:
    """Atomic write via tmp + os.replace."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(str(tmp), str(path))

def parse_timestamp(ts: str) -> Optional[datetime]:
    """Parse ISO timestamp with tolerance. None on failure."""
    if not ts: return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError): pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try: return datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
        except ValueError: continue
    return None

def load_json(path: Path) -> Optional[Dict]:
    """Load JSON, None on failure."""
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError): return None

def emit(action: str, message: str, should_remove: bool = False,
         progress: Optional[Dict] = None, fmt: str = "json") -> None:
    """Print result and exit 0."""
    r: Dict[str, Any] = {"action": action, "message": message, "should_remove_cron": should_remove}
    if progress: r["progress"] = progress
    print(f"[{action}] {message}" if fmt == "plain" else json.dumps(r, ensure_ascii=False))
    sys.exit(0)

def validate_config(cfg: Dict) -> List[str]:
    """Validate required fields."""
    errs: List[str] = []
    for k, t in [("pipeline_id", str), ("display_name", str), ("limits", dict), ("detection", dict)]:
        if k not in cfg: errs.append(f"Missing: {k}")
        elif not isinstance(cfg[k], t): errs.append(f"{k} must be {t.__name__}")
    if "limits" in cfg and isinstance(cfg["limits"], dict):
        for k in ("max_runs", "timeout_minutes"):
            if k not in cfg["limits"]: errs.append(f"Missing limits.{k}")
    if "detection" in cfg and isinstance(cfg["detection"], dict):
        for k in ("scan_dirs", "total_stages"):
            if k not in cfg["detection"]: errs.append(f"Missing detection.{k}")
    return errs

class RunCounter:
    """Tracks run count and timeout."""
    def __init__(self, state_dir: Path, limits: Dict, run_start_at: str):
        self.path, self.max_runs, self.timeout_min, self.run_start_at = state_dir / ".cron_run_count", limits.get("max_runs", 20), limits.get("timeout_minutes", 60), run_start_at
        self.count = 0
    def increment(self) -> int:
        data = load_json(self.path)
        self.count = (data["count"] + 1) if (data and isinstance(data.get("count"), int)) else 1
        atomic_write(self.path, json.dumps({"count": self.count, "run_start_at": self.run_start_at}))
        return self.count
    def is_timeout(self) -> bool:
        start = parse_timestamp(self.run_start_at)
        if start and (datetime.now(timezone.utc) - start).total_seconds() / 60 > self.timeout_min: return True
        return self.count > self.max_runs

class CompletionChecker:
    """Checks .completed with timestamp validation."""
    def __init__(self, base_path: Path, detection: Dict, run_start_at: str):
        self.file, self.ts_field, self.run_start_at = base_path / detection.get("completed_file", ".completed"), detection.get("completed_timestamp_field", "completed_at"), run_start_at
    def check(self) -> Optional[Dict]:
        data = load_json(self.file)
        if not data or data.get("status") not in ("completed", "failed"): return None
        ts, start = parse_timestamp(data.get(self.ts_field, "")), parse_timestamp(self.run_start_at)
        if ts and start and ts < start: return None
        return data

class StageDetector:
    """Glob scan + diff + merge_group."""
    def __init__(self, base_path: Path, detection: Dict, state_dir: Path):
        self.base_path, self.scan_dirs, self.notified_path, self._all = base_path, detection.get("scan_dirs", []), state_dir / ".notified_stages.json", []
    def scan(self) -> List[Dict]:
        notified_data = load_json(self.notified_path)
        notified = set(notified_data) if isinstance(notified_data, list) else set()
        found: Dict[str, Dict] = {}
        merge_groups: Dict[str, List[Dict]] = {}
        for sd in self.scan_dirs:
            dir_p = self.base_path / sd["path"] if sd["path"] != "." else self.base_path
            if not dir_p.is_dir(): continue
            matches = dir_p.rglob(sd.get("pattern", "*.json")) if sd.get("dir_mode") == "nested" else dir_p.glob(sd.get("pattern", "*.json"))
            present = {p.name for p in matches if p.is_file()}
            for fname, info in sd.get("stage_files", {}).items():
                if fname in present:
                    found[fname] = info
                    mg = info.get("merge_group")
                    if mg: merge_groups.setdefault(mg, []).append(info)
        self._all = sorted(found.values(), key=lambda x: x.get("seq", 0))
        new_files = set(found.keys()) - notified
        new_stages: List[Dict] = []
        seen_groups: set = set()
        for fn in sorted(new_files, key=lambda f: found[f].get("seq", 0)):
            info, mg = found[fn], info.get("merge_group")
            if mg:
                if mg not in seen_groups:
                    seen_groups.add(mg)
                    new_stages.append({"name": info["name"], "seq": info["seq"], "merge_group": mg})
            else: new_stages.append({"name": info["name"], "seq": info["seq"]})
        notified.update(found.keys())
        atomic_write(self.notified_path, json.dumps(sorted(notified)))
        return new_stages
    def all_stages(self) -> List[Dict]: return self._all

class CircuitBreaker:
    """Counts consecutive no-output runs."""
    def __init__(self, state_dir: Path, limits: Dict):
        self.path, self.threshold = state_dir / ".watcher_no_output_count", limits.get("circuit_breaker_threshold", 3)
    def _read(self) -> int:
        data = load_json(self.path)
        return data.get("count", 0) if isinstance(data, dict) else 0
    def record_no_output(self) -> int:
        c = self._read() + 1
        atomic_write(self.path, json.dumps({"count": c}))
        return c
    def reset(self) -> None: atomic_write(self.path, json.dumps({"count": 0}))
    def should_break(self) -> bool: return self._read() >= self.threshold

# ── Default templates — UI v3 (ported from pipeline_progress_notify.py) ──
_TPL = {
    "progress": "🟠 [{project_short}] {current_phase_name}\n{progress_bar} {completed}/{total} 阶段\n{icon_chain}\n⏱️ 已运行 {elapsed} · 预计剩余 {remaining}",
    "completed": "✅ [{project_short}] {display_name} 完成\n{progress_bar} {total}/{total} 阶段\n⏱️ 总耗时 {elapsed}\n📄 {artifact_count} 个交付物",
    "failed": "⚠️ {display_name}失败\n已完成: {completed}/{total}\n原因: {error}",
    "timeout": "⚠️ {display_name}运行超时（>{pipeline.timeout_min}分钟）\norchestrator 可能已崩溃。",
    "circuit_break": "⚠️ 连续{pipeline.failures}次巡检无输出\norchestrator 可能已停止。",
}
_SYM = {"done": "✅", "running": "⏳", "pending": "⬜"}

class _AttrDict(dict):
    """Dict that supports {parent.key} in str.format_map via attribute access."""
    def __getattr__(self, k: str) -> Any:
        try: return self[k]
        except KeyError: raise AttributeError(k)

class MessageFormatter:
    """Renders messages with {pipeline.xxx} placeholders.

    UI v3 enhancements (ported from pipeline_progress_notify.py):
    - progress_bar(): Unicode progress bar
    - build_icon_chain(): Phase icon chain (e.g. 📊✅ 📝⏳ 👁️○)
    - estimate_remaining(): Time remaining estimate
    - Default templates use UI v3 format; custom config templates still override.
    """
    def __init__(self, config: Dict, all_stages: List[Dict]):
        self.cfg, self.stages = config, all_stages
        self.tpl, self.sym = {**_TPL, **config.get("templates", {})}, {**_SYM, **config.get("stage_symbols", {})}

    # ── UI v3 helpers (ported from pipeline_progress_notify.py) ──

    @staticmethod
    def _progress_bar(completed: int, total: int, width: int = 20) -> str:
        """Unicode progress bar. Source: pipeline_progress_notify.py progress_bar()."""
        if total <= 0:
            return "░" * width
        filled = min(int(width * completed / total), width)
        return "█" * filled + "░" * (width - filled)

    @staticmethod
    def _estimate_remaining(elapsed_minutes: int, completed_count: int, total: int) -> str:
        """Estimate remaining time. Source: pipeline_progress_notify.py estimate_remaining()."""
        if completed_count <= 0 or elapsed_minutes <= 0:
            return "计算中"
        avg_per_phase = elapsed_minutes / completed_count
        remaining_phases = total - completed_count
        remaining_minutes = int(avg_per_phase * remaining_phases)
        if remaining_minutes < 1:
            return "即将完成"
        if remaining_minutes >= 60:
            h, m = remaining_minutes // 60, remaining_minutes % 60
            return f"{h}h{m}m"
        return f"{remaining_minutes}m"

    def _phase_defs(self) -> List[tuple]:
        """Extract unique (name, seq, icon) phases from config stage_files, sorted by seq."""
        seen: Dict[tuple, str] = {}
        for sd in self.cfg.get("detection", {}).get("scan_dirs", []):
            for _fname, info in sd.get("stage_files", {}).items():
                key = (info["name"], info.get("seq", 0))
                if key not in seen:
                    seen[key] = info.get("icon", "❓")
        return [(name, seq, icon) for (name, seq), icon in sorted(seen.items(), key=lambda x: x[0][1])]

    def _build_icon_chain(self, completed_seqs: set, current_seq: int) -> str:
        """Build phase icon chain: 📊✅ 📝⏳ 👁️○ 🔬○. Source: pipeline_progress_notify.py build_phase_icon_chain()."""
        parts = []
        for _name, seq, icon in self._phase_defs():
            if seq in completed_seqs:
                parts.append(f"{icon}✅")
            elif seq == current_seq:
                parts.append(f"{icon}⏳")
            else:
                parts.append(f"{icon}○")
        return " ".join(parts)

    def _project_short(self) -> str:
        """Extract short project name from base_path."""
        bp = str(self.cfg.get("base_path", ""))
        basename = os.path.basename(bp.rstrip("/"))
        parts = basename.split("_")
        if len(parts) >= 2:
            return parts[0]
        return basename[:12] if basename else "Pipeline"

    def _elapsed_minutes(self, run_start_at: str) -> int:
        """Elapsed minutes as integer (for estimate_remaining)."""
        s = parse_timestamp(run_start_at)
        if not s:
            return 0
        return max(0, int((datetime.now(timezone.utc) - s).total_seconds() / 60))

    def _elapsed_v3(self, run_start_at: str) -> str:
        """Compact elapsed time format for UI v3."""
        s = parse_timestamp(run_start_at)
        if not s:
            return "—"
        m = max(0, int((datetime.now(timezone.utc) - s).total_seconds() / 60))
        if m >= 60:
            h, mins = m // 60, m % 60
            return f"{h}h{mins}m"
        return f"{m}m"

    # ── Original helpers (unchanged) ──

    def _ctx(self, **kw: Any) -> Dict:
        inner = _AttrDict({
            "display_name": self.cfg.get("display_name", "Pipeline"),
            "completed": len(self.stages),
            "total": self.cfg["detection"]["total_stages"],
            "final_artifact": self.cfg["detection"].get("final_artifact", ""),
            "base_path": str(self.cfg.get("base_path", "")),
            **kw,
        })
        # Support both {pipeline.xxx} (default _TPL) and {xxx} (config templates)
        ctx = dict(inner)
        ctx["pipeline"] = inner
        return ctx
    def _elapsed(self, run_start_at: str) -> str:
        s = parse_timestamp(run_start_at)
        if not s: return "未知"
        m = int((datetime.now(timezone.utc) - s).total_seconds() / 60)
        return f"{m}分钟" if m < 60 else f"{m // 60}时{m % 60}分"
    def _stage_lines(self, new_stages: List[Dict]) -> str:
        done = {s["name"] for s in self.stages}
        lines = [f"  {self.sym['done']} {n}" for n in sorted(done)]
        lines += [f"  {self.sym['running']} {n}" for n in sorted({s["name"] for s in new_stages} - done)]
        return "\n".join(lines) if lines else "  (无阶段信息)"

    # ── Message renderers ──

    def progress(self, new_stages: List[Dict], run_start_at: str) -> str:
        # Compute UI v3 elements
        phase_defs = self._phase_defs()
        completed_seqs = {s.get("seq", 0) for s in self.stages}
        completed_count = len(completed_seqs)
        total = self.cfg["detection"]["total_stages"]
        # Current phase = first phase not yet completed
        current_name, current_seq = "完成", 0
        for name, seq, _icon in phase_defs:
            if seq not in completed_seqs:
                current_name, current_seq = name, seq
                break
        if current_seq == 0 and phase_defs:
            current_name, current_seq = phase_defs[-1][0], phase_defs[-1][1]
        elapsed_v3 = self._elapsed_v3(run_start_at)
        elapsed_min = self._elapsed_minutes(run_start_at)
        bar = self._progress_bar(completed_count, total)
        chain = self._build_icon_chain(completed_seqs, current_seq)
        remaining = self._estimate_remaining(elapsed_min, completed_count, total)
        return self.tpl["progress"].format_map(self._ctx(
            stage_lines=self._stage_lines(new_stages),
            elapsed=self._elapsed(run_start_at), elapsed_time=self._elapsed(run_start_at),
            # UI v3 variables
            progress_bar=bar, icon_chain=chain, remaining=remaining,
            project_short=self._project_short(), current_phase_name=current_name,
            artifact_count=len(self.stages),
        ))
    def completed(self, data: Dict, run_start_at: str) -> str:
        total = self.cfg["detection"]["total_stages"]
        bar = self._progress_bar(total, total)
        all_completed_seqs = {pd[1] for pd in self._phase_defs()}
        return self.tpl["completed"].format_map(self._ctx(
            elapsed=self._elapsed(run_start_at), elapsed_time=self._elapsed(run_start_at),
            score=data.get("score", "N/A"),
            # UI v3 variables
            progress_bar=bar, project_short=self._project_short(),
            artifact_count=len(self.stages) if self.stages else 0,
            icon_chain=self._build_icon_chain(all_completed_seqs, 0),
            elapsed_v3=self._elapsed_v3(run_start_at),
        ))
    def failed(self, data: Dict, run_start_at: str) -> str:
        return self.tpl["failed"].format_map(self._ctx(elapsed=self._elapsed(run_start_at), elapsed_time=self._elapsed(run_start_at), error=data.get("error", "未知")))
    def timeout(self) -> str: return self.tpl["timeout"].format_map(self._ctx(timeout_min=self.cfg["limits"].get("timeout_minutes", 60), timeout_minutes=self.cfg["limits"].get("timeout_minutes", 60)))
    def circuit_break(self, failures: int) -> str: return self.tpl["circuit_break"].format_map(self._ctx(failures=failures))

WRAPPER_PROMPT = """你是 DeepFlow 管线巡检执行器。严格按以下步骤执行：

1. 运行: exec("python3 {deepflow_root}/scripts/pipeline_watcher.py --config {config_path} --base-path {base_path} --run-start-at {run_start_at} --cron-job-id {cron_job_id}")
2. 验证 stdout 是合法 JSON（先尝试 json.loads 解析）
3. 根据 action 字段：
   - "noop" → 回复 NO_REPLY
   - 其他 → 原样输出 message 字段的文本（delivery 自动推送）
4. 如果 should_remove_cron = true → 输出消息后执行 cron(action="remove", jobId="{cron_job_id}")

禁止：自行判断进度、编造消息、跳过步骤。如果 JSON 解析失败，输出错误信息。"""

def write_auto_chain(config: Dict, base_path: Path, completion: Dict) -> Optional[str]:
    """Write .auto_chain_trigger if configured. Returns next pipeline name or None."""
    ac, next_pl = config.get("auto_chain", {}), config.get("auto_chain", {}).get("next_pipeline")
    if not next_pl: return None
    trigger = {"source_pipeline": config["pipeline_id"], "completed_at": completion.get("completed_at", ""), "base_path": str(base_path)}
    atomic_write(base_path / ac.get("trigger_file", ".auto_chain_trigger"), json.dumps(trigger, ensure_ascii=False))
    return next_pl

def _mark_remove(state: Path, reason: str, cron_id: str) -> None:
    """Write .watcher_should_remove marker."""
    atomic_write(state / ".watcher_should_remove", json.dumps({"reason": reason, "cron_job_id": cron_id}))

def _run_pipeline(cfg: Dict, base: Path, state: Path, args: Any, fmt: str) -> None:
    """Core pipeline watch logic."""
    cron_id = args.cron_job_id
    rc = RunCounter(state, cfg["limits"], args.run_start_at)
    rc.increment()
    if rc.is_timeout():
        _mark_remove(state, "timeout", cron_id)
        emit("timeout", MessageFormatter(cfg, []).timeout(), should_remove=True, fmt=fmt)
    cc = CompletionChecker(base, cfg["detection"], args.run_start_at)
    comp = cc.check()
    if comp:
        fm, status = MessageFormatter(cfg, []), comp.get("status", "")
        if status == "completed":
            msg = fm.completed(comp, args.run_start_at)
            next_pl = write_auto_chain(cfg, base, comp)
            if next_pl: msg += f"\n\n🔗 已触发下游管线: {next_pl}"
            _mark_remove(state, "completed", cron_id)
            emit("completed", msg, should_remove=True, fmt=fmt)
        elif status == "failed":
            _mark_remove(state, "failed", cron_id)
            emit("failed", fm.failed(comp, args.run_start_at), should_remove=True, fmt=fmt)
    sd = StageDetector(base, cfg["detection"], state)
    new_stages = sd.scan()
    if new_stages:
        CircuitBreaker(state, cfg["limits"]).reset()
        fm = MessageFormatter(cfg, sd.all_stages())
        prog = {"completed": len(sd.all_stages()), "total": cfg["detection"]["total_stages"], "new_stages": [s["name"] for s in new_stages]}
        emit("progress", fm.progress(new_stages, args.run_start_at), progress=prog, fmt=fmt)
    cb = CircuitBreaker(state, cfg["limits"])
    count = cb.record_no_output()
    if cb.should_break():
        _mark_remove(state, "circuit_break", cron_id)
        emit("circuit_break", MessageFormatter(cfg, []).circuit_break(count), should_remove=True, fmt=fmt)
    emit("noop", "", fmt=fmt)

def main() -> None:
    ap = argparse.ArgumentParser(description="Pipeline Watcher V2")
    ap.add_argument("--config", required=True)
    ap.add_argument("--base-path", required=True)
    ap.add_argument("--run-start-at", required=True)
    ap.add_argument("--cron-job-id", required=True)
    ap.add_argument("--state-dir", default=None)
    ap.add_argument("--format", choices=["json", "plain"], default="json")
    ap.add_argument("--print-wrapper", action="store_true")
    args = ap.parse_args()
    if args.print_wrapper: print(WRAPPER_PROMPT); sys.exit(0)
    base, state = Path(args.base_path), Path(args.state_dir) if args.state_dir else Path(args.base_path)
    cfg = load_json(Path(args.config))
    if cfg is None: print(f"Error: cannot read config: {args.config}", file=sys.stderr); sys.exit(1)
    errs = validate_config(cfg)
    if errs: print("Config validation errors:\n" + "\n".join(f"  - {e}" for e in errs), file=sys.stderr); sys.exit(1)
    state.mkdir(parents=True, exist_ok=True)
    lock_f = open(state / ".pipeline_watcher.lock", "w")
    try: fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError: emit("noop", "Another watcher instance running", fmt=args.format)
    try: _run_pipeline(cfg, base, state, args, args.format)
    finally: fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN); lock_f.close()

if __name__ == "__main__": main()
