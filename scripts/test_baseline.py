#!/usr/bin/env python3
"""DeepFlow 分片测试基线 runner。

目的：把一次巨型 pytest 拆成按文件的独立小运行，单文件超时/崩溃不再拖死整轮。
无第三方依赖；每个测试文件生成独立 log + junit xml，最后汇总 summary。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKIP = {
    "domains/research_pro/tests/test_orchestrator.py",  # 已知挂起嫌疑，先隔离
}
SKIP_DIRS = {
    ".git", ".pytest_cache", "__pycache__", ".venv", "venv", "blackboard",
    "docs", "projects", "output", "test_results", "verification", "ARCHIVED", "_archived",
}


def rel(p: Path) -> str:
    return str(p.resolve().relative_to(ROOT))


def discover(paths: list[str]) -> list[Path]:
    if paths:
        out = []
        for raw in paths:
            p = (ROOT / raw).resolve()
            if p.is_dir():
                out.extend(sorted(p.rglob("test_*.py")))
            elif p.is_file():
                out.append(p)
            else:
                raise SystemExit(f"path not found: {raw}")
        return unique_files(out)

    roots = [ROOT / "tests", ROOT / "domains", ROOT / "core"]
    out: list[Path] = []
    for base in roots:
        if not base.exists():
            continue
        for p in base.rglob("test_*.py"):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if "fixtures" in p.parts:
                continue
            out.append(p)
    return unique_files(out)


def unique_files(files: list[Path]) -> list[Path]:
    seen = set()
    out = []
    for p in files:
        r = str(p.resolve())
        if r not in seen:
            seen.add(r)
            out.append(p.resolve())
    return sorted(out, key=lambda p: str(p))


def parse_junit(xml_path: Path) -> dict:
    if not xml_path.exists():
        return {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "time": 0.0}
    try:
        root = ET.parse(xml_path).getroot()
    except Exception:
        return {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "time": 0.0}
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    agg = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "time": 0.0}
    for s in suites:
        for k in ("tests", "failures", "errors", "skipped"):
            agg[k] += int(float(s.attrib.get(k, 0)))
        agg["time"] += float(s.attrib.get("time", 0) or 0)
    return agg


def run_one(path: Path, timeout: int, outdir: Path) -> dict:
    name = rel(path)
    safe = name.replace("/", "__")
    log_path = outdir / f"{safe}.log"
    xml_path = outdir / f"{safe}.xml"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        name,
        "-q",
        "--tb=short",
        "--disable-warnings",
        f"--junitxml={xml_path}",
    ]
    env = os.environ.copy()
    env.pop("KMP_DUPLICATE_LIB_OK", None)  # 修复后不得再依赖危险绕过
    started = time.time()
    try:
        cp = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        rc = cp.returncode
        if rc == 0:
            status = "pass"
        elif rc == 5:
            status = "no_tests"
        else:
            status = "fail"
        output = cp.stdout + ("\n" + cp.stderr if cp.stderr else "")
    except subprocess.TimeoutExpired as e:
        rc = 124
        status = "timeout"
        output = (e.stdout or "") + ("\n" + (e.stderr or "") if e.stderr else "")
        output += f"\n[TIMEOUT] > {timeout}s\n"
    log_path.write_text(output, encoding="utf-8", errors="replace")
    agg = parse_junit(xml_path)
    agg.update(
        {
            "file": name,
            "status": status,
            "rc": rc,
            "wall_time": round(time.time() - started, 3),
            "log": str(log_path.relative_to(ROOT)),
            "xml": str(xml_path.relative_to(ROOT)) if xml_path.exists() else None,
        }
    )
    return agg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", nargs="*", default=[], help="只跑这些文件/目录；默认 tests domains core")
    ap.add_argument("--timeout", type=int, default=120, help="单文件超时秒数，默认 120")
    ap.add_argument("--skip", action="append", default=[], help="额外跳过的测试文件，可重复")
    ap.add_argument("--include-known-hang", action="store_true", help="连默认隔离的挂起测试也跑")
    ap.add_argument("--out", default="test_results/baseline", help="输出目录")
    args = ap.parse_args()

    skip = set(args.skip)
    if not args.include_known_hang:
        skip |= DEFAULT_SKIP

    files = [p for p in discover(args.paths) if rel(p) not in skip]
    outdir = (ROOT / args.out).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    started = time.time()
    results = []
    for i, p in enumerate(files, 1):
        name = rel(p)
        print(f"[{i}/{len(files)}] {name}", flush=True)
        r = run_one(p, args.timeout, outdir)
        results.append(r)
        print(f"  -> {r['status']} rc={r['rc']} tests={r['tests']} fail={r['failures']} err={r['errors']} skip={r['skipped']} time={r['wall_time']}s", flush=True)

    summary = {
        "root": str(ROOT),
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime(started)),
        "wall_time": round(time.time() - started, 3),
        "timeout_per_file": args.timeout,
        "skipped_files": sorted(skip),
        "files": len(results),
        "pass_files": sum(1 for r in results if r["status"] == "pass"),
        "fail_files": sum(1 for r in results if r["status"] == "fail"),
        "timeout_files": sum(1 for r in results if r["status"] == "timeout"),
        "no_tests_files": sum(1 for r in results if r["status"] == "no_tests"),
        "tests": sum(r["tests"] for r in results),
        "failures": sum(r["failures"] for r in results),
        "errors": sum(r["errors"] for r in results),
        "skipped": sum(r["skipped"] for r in results),
        "results": results,
    }
    (outdir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# DeepFlow 分片测试基线",
        "",
        f"- files: {summary['files']}（pass {summary['pass_files']} / fail {summary['fail_files']} / timeout {summary['timeout_files']} / no_tests {summary['no_tests_files']}）",
        f"- tests: {summary['tests']}（failures {summary['failures']} / errors {summary['errors']} / skipped {summary['skipped']}）",
        f"- wall_time: {summary['wall_time']}s；单文件超时: {args.timeout}s",
        f"- skipped_files: {', '.join(summary['skipped_files']) or '(none)'}",
        "",
        "| file | status | rc | tests | fail | err | skip | time | log |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['file']} | {r['status']} | {r['rc']} | {r['tests']} | {r['failures']} | {r['errors']} | {r['skipped']} | {r['wall_time']} | {r['log']} |"
        )
    (outdir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nSUMMARY: {summary['pass_files']}/{summary['files']} files pass; no_tests={summary['no_tests_files']}; tests={summary['tests']} failures={summary['failures']} errors={summary['errors']} skipped={summary['skipped']}")
    print(f"OUT: {outdir / 'summary.md'}")
    return 0 if summary["fail_files"] == 0 and summary["timeout_files"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
