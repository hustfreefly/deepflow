#!/usr/bin/env python3
"""ADR-009 Phase 3: 3 surgical edits to orchestrator.py (incorporating PlanMode Lite review)"""
import sys
from pathlib import Path

file_path = Path("/Users/allen/.openclaw/workspace/.deepflow/domains/deliver_pro/orchestrator.py")
content = file_path.read_text(encoding="utf-8")
original_len = len(content)

# ═══════════════════════════════════════════════════════════════════════════
# Edit 1: Add import after failure_recovery import
# ═══════════════════════════════════════════════════════════════════════════
import_marker = "from domains.deliver_pro.failure_recovery import WorkerFailureRecovery"
import_replacement = """from domains.deliver_pro.failure_recovery import WorkerFailureRecovery

# ADR-009: MD Track Extractor (optional — graceful fallback if core/ not in path)
try:
    from core.md_track_extractor import validate_md_structure, extract_track_json
    _HAS_TRACK_EXTRACTOR = True
except ImportError:
    _HAS_TRACK_EXTRACTOR = False"""

if "_HAS_TRACK_EXTRACTOR" in content:
    print("⚠️  Edit 1 SKIPPED: import already exists")
else:
    if import_marker not in content:
        print("❌ Edit 1 FAILED: import marker not found")
        sys.exit(1)
    content = content.replace(import_marker, import_replacement, 1)
    print("✅ Edit 1: import added")

# ═══════════════════════════════════════════════════════════════════════════
# Edit 2: Add generate_track_json() method before verify_package_output
# ═══════════════════════════════════════════════════════════════════════════
method_marker = "    def verify_package_output(self, manifest_path: Path) -> tuple[bool, str, DeliveryManifest | None]:"

new_method = '''    # ========================================================================
    # ADR-009: Track JSON Generation (Post-Phase 5)
    # ========================================================================

    def generate_track_json(self) -> None:
        """
        ADR-009: 从 DELIVERABLE.md 提取 track.json。

        在 Phase 5 (Package) 验证通过后、写入 .completed 之前调用。
        提取失败 → log warning，不阻断交付。
        """
        if not _HAS_TRACK_EXTRACTOR:
            logger.info("ADR-009: md_track_extractor not available, skipping track.json generation")
            return

        deliverable_path = self.stages_dir / "final_deliverable" / "DELIVERABLE.md"
        if not deliverable_path.exists():
            logger.warning("ADR-009: DELIVERABLE.md not found, skipping track.json")
            return

        try:
            md_content = deliverable_path.read_text(encoding="utf-8")

            # L1: Validate structure
            passed, msg, warnings = validate_md_structure(md_content, "deliver_pro")
            if not passed:
                logger.warning(f"ADR-009: MD validation failed: {msg}")
                return
            if warnings:
                logger.info(f"ADR-009: MD validation warnings: {warnings}")

            # L2: Extract track.json
            track_data = extract_track_json(md_content, "deliver_pro")

            # Write via direct file I/O (extractor is pure function)
            track_path = self.stages_dir / "deliver_track.json"
            track_path.write_text(
                json.dumps(track_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            logger.info(
                f"ADR-009: track.json generated — "
                f"req_count={track_data['metrics']['req_count']}, "
                f"sections={track_data['metrics']['section_count']}, "
                f"gate={track_data['gate_summary']}"
            )

        except ValueError as e:
            logger.warning(f"ADR-009: track extraction failed (ValueError): {e}")
        except Exception as e:
            logger.warning(f"ADR-009: unexpected error during track generation: {e}")

    def verify_package_output(self, manifest_path: Path) -> tuple[bool, str, DeliveryManifest | None]:'''

if "def generate_track_json" in content:
    print("⚠️  Edit 2 SKIPPED: method already exists")
else:
    if method_marker not in content:
        print("❌ Edit 2 FAILED: verify_package_output marker not found")
        sys.exit(1)
    content = content.replace(method_marker, new_method, 1)
    print("✅ Edit 2: generate_track_json() method added")

# ═══════════════════════════════════════════════════════════════════════════
# Edit 3: Add call BEFORE .completed marker (PlanMode Lite review: P1 #1)
# ═══════════════════════════════════════════════════════════════════════════
# 注意：专家建议将 track 生成移到 .completed 之前，确保状态一致性
completed_marker = """            # 写入完成标记
            (self.deliver_pro_dir / ".completed").write_text(
                datetime.now().isoformat(), encoding="utf-8"
            )

            logger.info("""

completed_replacement = """            # ADR-009: Generate track.json from DELIVERABLE.md (non-blocking)
            # 在 .completed 之前调用，确保 track 生成是完成标记的前置条件
            self.generate_track_json()

            # 写入完成标记
            (self.deliver_pro_dir / ".completed").write_text(
                datetime.now().isoformat(), encoding="utf-8"
            )

            logger.info("""

if "self.generate_track_json()" in content:
    print("⚠️  Edit 3 SKIPPED: call already exists")
else:
    if completed_marker not in content:
        print("❌ Edit 3 FAILED: .completed marker not found")
        sys.exit(1)
    content = content.replace(completed_marker, completed_replacement, 1)
    print("✅ Edit 3: generate_track_json() call added BEFORE .completed marker")

# ═══════════════════════════════════════════════════════════════════════════
# Final verification + write
# ═══════════════════════════════════════════════════════════════════════════
assert "_HAS_TRACK_EXTRACTOR" in content, "Edit 1 verification failed"
assert "def generate_track_json" in content, "Edit 2 verification failed"
assert "self.generate_track_json()" in content, "Edit 3 verification failed"

file_path.write_text(content, encoding="utf-8")
new_len = len(content)
print(f"\n✅ All 3 edits applied and verified.")
print(f"   File size: {original_len} → {new_len} (+{new_len - original_len} chars)")
