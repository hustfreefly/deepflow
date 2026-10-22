#!/usr/bin/env bash
# DeepFlow CI — real gate entry.
# Rewritten 2026-10-22: the previous script pointed at non-existent paths
# (cage/validate.py, cage/check_standards.py) and set PROJECT_ROOT to scripts/ci.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

MODE="full"
for arg in "$@"; do
  case "$arg" in
    --quick) MODE="quick" ;;
    --contract) MODE="contract" ;;
    --unit) MODE="unit" ;;
    --coverage) MODE="coverage" ;;
    --full) MODE="full" ;;
    --help|-h)
      cat <<'EOF'
DeepFlow CI
  ./ci.sh              # full: contract gate + all tests
  ./ci.sh --contract   # G3 contract cage only
  ./ci.sh --quick      # all tests except slow
  ./ci.sh --unit       # domains + tests except slow
  ./ci.sh --coverage   # contract gate + full tests + coverage threshold
EOF
      exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

echo "== DeepFlow CI ($MODE) =="
echo "root: $PROJECT_ROOT"

run_contract() {
  echo "-- G3 contract gate --"
  python3 -m pytest tests/contracts -q
  echo "-- validator CLI consistency --"
  python3 scripts/validate.py --all
}

case "$MODE" in
  contract) run_contract ;;
  quick)
    run_contract
    echo "-- tests (excluding slow) --"
    python3 -m pytest -q -m "not slow"
    ;;
  unit)
    run_contract
    echo "-- unit/domain tests --"
    python3 -m pytest tests domains -q -m "not slow"
    ;;
  coverage)
    run_contract
    echo "-- coverage gate --"
    python3 -m pytest -q --cov=core --cov=domains --cov-report=term-missing --cov-fail-under="\${COVERAGE_MIN:-45}"
    ;;
  full)
    run_contract
    echo "-- full suite --"
    python3 -m pytest -q
    ;;
esac

echo "== CI PASS ($MODE) =="
