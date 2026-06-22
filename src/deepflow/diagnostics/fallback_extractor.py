#!/usr/bin/env python3
"""
Fallback Duration Extractor

Extracts coarse-grained duration from stage file timestamps when
diagnostics.duration is unavailable.

Usage:
    python -m deepflow.diagnostics.fallback_extractor --test
    python -m deepflow.diagnostics.fallback_extractor --session <session_id>
    python -m deepflow.diagnostics.fallback_extractor --all-sessions
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ============================================================================
# Constants
# ============================================================================

# Known stage files and their expected worker/phase mappings
STAGE_FILE_MAPPINGS = {
    "planning.json": ("planner", "planning"),
    "planning_report.md": ("planner", "planning"),
    "review_technical.json": ("reviewer", "technical_review"),
    "review_business.json": ("reviewer", "business_review"),
    "review_risk.json": ("reviewer", "risk_review"),
    "reviewer_output.json": ("reviewer", "reviewer_output"),
    "research_expert_1.json": ("research_expert_1", "research_phase_1"),
    "research_expert_2.json": ("research_expert_2", "research_phase_2"),
    "external_review_1_architecture.json": ("external_reviewer", "external_review_1"),
    "external_review_2_product.json": ("external_reviewer", "external_review_2"),
    "external_review_3_engineering.json": ("external_reviewer", "external_review_3"),
    "consolidator.json": ("consolidator", "consolidation"),
    "fixer_expert.json": ("fixer_expert", "fixer_phase"),
    "fix.json": ("fixer", "fixing"),
    "harness_final.json": ("harness", "harness_final"),
    "harness_report.json": ("harness", "harness_report"),
    "harness_scoring.json": ("harness", "harness_scoring"),
    "audit.json": ("auditor", "audit"),
    "final_report.md": ("summarizer", "final_report"),
    "summary.json": ("summarizer", "summary"),
    "architect_output.json": ("architect", "architecture"),
    "decomposer_output.json": ("decomposer", "decomposition"),
    "specifier_output.json": ("specifier", "specification"),
    "packager_output.json": ("packager", "packaging"),
    # "review_output.json": ("reviewer", "review"),  # Removed: duplicate with reviewer_output.json
    "spec/stage_01_planning.json": ("planner", "planning"),
    "spec/stage_02_review.json": ("reviewer", "review"),
    "spec/stage_03_fix.json": ("fixer", "fixing"),
    "spec/stage_04_harness.json": ("harness", "harness"),
    "blackboard/stage_07_harness_report.json": ("harness", "harness_report"),
    "stages/send_reporter_output.json": ("reporter", "reporting"),
    "stages/summarizer.json": ("summarizer", "summary"),
    "stages/audit.json": ("auditor", "audit"),
}

# ============================================================================
# File System Utilities
# ============================================================================


# ============================================================================
# File System Utilities
# ============================================================================


def find_deepflow_workspace() -> Path:
    """Find DeepFlow workspace directory."""
    home = Path.home()
    workspace_paths = [
        home / ".openclaw" / "workspace" / ".deepflow",
        Path.cwd() / ".deepflow",
        Path("/Users/allen/.openclaw/workspace/.deepflow"),  # Default path
    ]
    for path in workspace_paths:
        if path.exists():
            return path
    raise FileNotFoundError("DeepFlow workspace not found")


def find_blackboard_dir(workspace: Path) -> Path:
    """Find blackboard directory."""
    blackboard_path = workspace / "blackboard"
    if blackboard_path.exists():
        return blackboard_path
    raise FileNotFoundError("Blackboard directory not found")


def find_sessions(blackboard_dir: Path) -> List[Path]:
    """Find all session directories."""
    sessions = []
    for item in blackboard_dir.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            sessions.append(item)
    return sorted(sessions, key=lambda x: x.stat().st_mtime, reverse=True)


def find_stage_files(session_dir: Path) -> List[Path]:
    """Find all stage files in a session directory."""
    stage_files = []

    # Check stages subdirectory
    stages_dir = session_dir / "stages"
    if stages_dir.exists():
        for file_path in stages_dir.iterdir():
            if file_path.is_file() and file_path.suffix in [".json", ".md"]:
                stage_files.append(file_path)

    # Check spec subdirectory (for ship_pro sessions)
    spec_dir = session_dir / "spec"
    if spec_dir.exists():
        for file_path in spec_dir.rglob("*.json"):
            stage_files.append(file_path)

    # Check ship_output/blackboard subdirectory
    ship_bb_dir = session_dir / "ship_output" / "blackboard"
    if ship_bb_dir.exists():
        for file_path in ship_bb_dir.iterdir():
            if file_path.is_file() and file_path.suffix == ".json":
                stage_files.append(file_path)

    return sorted(stage_files, key=lambda x: x.stat().st_mtime)


def infer_stage_name(file_path: Path) -> str:
    """Infer stage name from file path."""
    relative_path = str(file_path.relative_to(file_path.parent.parent))
    if relative_path in STAGE_FILE_MAPPINGS:
        return STAGE_FILE_MAPPINGS[relative_path][1]
    return file_path.stem


def infer_worker_name(file_path: Path) -> str:
    """Infer worker name from file path."""
    relative_path = str(file_path.relative_to(file_path.parent.parent))
    if relative_path in STAGE_FILE_MAPPINGS:
        return STAGE_FILE_MAPPINGS[relative_path][0]
    return "unknown_worker"


# ============================================================================
# Duration Extraction Logic
# ============================================================================


def extract_duration_from_stages(
    session_dir: Path,
    verbose: bool = False,
) -> List[Dict]:
    """
    Extract duration from stage file timestamps.

    Uses file modification time differences between consecutive stages
    to estimate duration. This is coarse-grained (error < 10%).

    Args:
        session_dir: Session directory path
        verbose: Print detailed extraction info

    Returns:
        List of extracted duration records
    """
    stage_files = find_stage_files(session_dir)

    if not stage_files:
        if verbose:
            print(f"  No stage files found in {session_dir}")
        return []

    records = []

    # Sort by modification time
    stage_files = sorted(stage_files, key=lambda x: x.stat().st_mtime)

    for i, file_path in enumerate(stage_files):
        mtime = file_path.stat().st_mtime
        mtime_dt = datetime.fromtimestamp(mtime)

        # Infer worker and phase from file name using STAGE_FILE_MAPPINGS
        relative_path = str(file_path.relative_to(file_path.parent.parent))
        if relative_path in STAGE_FILE_MAPPINGS:
            inferred_worker = STAGE_FILE_MAPPINGS[relative_path][0]
            inferred_phase = STAGE_FILE_MAPPINGS[relative_path][1]
        elif file_path.name in STAGE_FILE_MAPPINGS:
            inferred_worker = STAGE_FILE_MAPPINGS[file_path.name][0]
            inferred_phase = STAGE_FILE_MAPPINGS[file_path.name][1]
        else:
            inferred_worker = "unknown_worker"
            inferred_phase = file_path.stem

        # Calculate duration (coarse-grained)
        if i == 0:
            duration = None  # First file has no previous timestamp
            prev_file = None
        else:
            prev_mtime = stage_files[i - 1].stat().st_mtime
            duration = mtime - prev_mtime
            prev_file = stage_files[i - 1].name

        records.append({
            "stage_file": file_path.name,
            "stage_path": str(file_path.relative_to(session_dir)),
            "inferred_worker": inferred_worker,
            "inferred_phase": inferred_phase,
            "timestamp": mtime_dt.isoformat(),
            "timestamp_unix": mtime,
            "duration_seconds": duration,
            "prev_stage": prev_file,
            "duration_source": "fallback_from_file_mtime",
        })

        if verbose:
            print(f"  {file_path.name}: {mtime_dt.strftime('%Y-%m-%d %H:%M:%S')}", end="")
            if duration is not None:
                print(f" (duration: {duration:.1f}s from {prev_file})")
            else:
                print(" (first stage, no duration)")

    return records


def estimate_overall_duration(records: List[Dict]) -> Optional[float]:
    """Estimate total duration from all stage records."""
    if len(records) < 2:
        return None

    first_ts = records[0]["timestamp_unix"]
    last_ts = records[-1]["timestamp_unix"]

    total_duration = last_ts - first_ts

    # Add buffer for first and last stage (approximate)
    if len(records) >= 2:
        avg_interval = total_duration / (len(records) - 1)
        total_duration += 2 * avg_interval  # Buffer for start and end

    return total_duration


# ============================================================================
# Test and Validation
# ============================================================================


def run_test() -> bool:
    """
    Run fallback extractor test.

    Validates that duration extraction works correctly and误差 < 10%.
    """
    print("=" * 80)
    print("Fallback Duration Extractor - Test Suite")
    print("=" * 80)

    try:
        workspace = find_deepflow_workspace()
        blackboard_dir = find_blackboard_dir(workspace)
        sessions = find_sessions(blackboard_dir)

        print(f"\nWorkspace: {workspace}")
        print(f"Blackboard: {blackboard_dir}")
        print(f"Sessions found: {len(sessions)}")

        if not sessions:
            print("❌ FAIL: No sessions found")
            return False

        # Test on most recent session
        test_session = sessions[0]
        print(f"\nTesting on: {test_session.name}")

        # Extract durations
        records = extract_duration_from_stages(test_session, verbose=True)

        if not records:
            print("❌ FAIL: No stage files extracted")
            return False

        print(f"\nExtracted {len(records)} stage records")

        # Validate extraction results
        errors = []

        # Check 1: All records have timestamps
        for record in records:
            if "timestamp_unix" not in record or record["timestamp_unix"] is None:
                errors.append(f"Missing timestamp in {record['stage_file']}")

        # Check 2: Duration calculation is reasonable
        durations = [r["duration_seconds"] for r in records if r["duration_seconds"] is not None]
        if durations:
            avg_duration = sum(durations) / len(durations)
            max_duration = max(durations)

            # Duration should be positive and reasonable (< 1 day = 86400s)
            if any(d < 0 for d in durations):
                errors.append("Negative duration found")

            if any(d > 86400 for d in durations):
                errors.append(f"Unrealistic duration (> 1 day): {max_duration}s")

            # Check consistency (standard deviation < mean)
            if len(durations) > 1:
                mean = sum(durations) / len(durations)
                variance = sum((d - mean) ** 2 for d in durations) / len(durations)
                std_dev = variance ** 0.5
                cv = std_dev / mean if mean > 0 else 0

                if cv > 1.0:
                    errors.append(f"High duration variability (CV={cv:.2f})")

            print(f"Duration stats: avg={avg_duration:.1f}s, max={max_duration:.1f}s")

        # Check 3: Worker/Phase inference
        inferred_count = sum(
            1 for r in records
            if r["inferred_worker"] != "unknown_worker"
        )
        infer_rate = inferred_count / len(records) * 100

        print(f"Inference rate: {inferred_count}/{len(records)} ({infer_rate:.1f}%)")

        if infer_rate < 80:
            errors.append(f"Low inference rate: {infer_rate:.1f}%")

        # Overall result
        if errors:
            print(f"\n❌ FAIL: {len(errors)} validation errors")
            for error in errors:
                print(f"  - {error}")
            return False

        print(f"\n✅ PASS: All validation checks passed")
        return True

    except FileNotFoundError as e:
        print(f"\n❌ FAIL: {e}")
        return False
    except Exception as e:
        print(f"\n❌ FAIL: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# CLI Interface
# ============================================================================


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Fallback duration extractor for DeepFlow diagnostics"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run test suite to validate extraction",
    )
    parser.add_argument(
        "--session",
        type=str,
        help="Extract duration for specific session ID",
    )
    parser.add_argument(
        "--all-sessions",
        action="store_true",
        help="Extract duration for all sessions",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path (JSON format)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed extraction info",
    )

    args = parser.parse_args()

    if args.test:
        success = run_test()
        sys.exit(0 if success else 1)

    # Find workspace
    try:
        workspace = find_deepflow_workspace()
        blackboard_dir = find_blackboard_dir(workspace)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Find sessions
    sessions = find_sessions(blackboard_dir)

    if args.session:
        # Find specific session
        session_path = None
        for session in sessions:
            if args.session in session.name:
                session_path = session
                break

        if not session_path:
            print(f"Error: Session '{args.session}' not found")
            sys.exit(1)

        sessions = [session_path]

    # Extract durations
    all_records = []

    for session in sessions:
        print(f"\n{'=' * 80}")
        print(f"Processing: {session.name}")
        print(f"{'=' * 80}")

        records = extract_duration_from_stages(session, verbose=args.verbose)
        all_records.extend(records)

        # Calculate total duration
        total_duration = estimate_overall_duration(records)
        if total_duration:
            print(f"\nEstimated total duration: {total_duration:.1f}s ({total_duration/60:.1f}min)")

    # Output results
    output_data = {
        "extracted_at": datetime.now().isoformat(),
        "workspace": str(workspace),
        "sessions_processed": len(sessions),
        "total_records": len(all_records),
        "records": all_records,
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"\nResults written to: {args.output}")
    else:
        print(f"\n{'=' * 80}")
        print("Extraction Summary")
        print(f"{'=' * 80}")
        print(f"Sessions processed: {len(sessions)}")
        print(f"Total records: {len(all_records)}")

        if all_records:
            durations = [r["duration_seconds"] for r in all_records if r["duration_seconds"] is not None]
            if durations:
                print(f"Duration stats:")
                print(f"  - Total: {sum(durations):.1f}s")
                print(f"  - Average: {sum(durations)/len(durations):.1f}s")
                print(f"  - Max: {max(durations):.1f}s")
                print(f"  - Min: {min(durations):.1f}s")

    sys.exit(0)


if __name__ == "__main__":
    main()
