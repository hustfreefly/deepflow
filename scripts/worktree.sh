#!/usr/bin/env bash
# P1 weapon: isolated worktree with runtime-state sync.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARENT="$(cd "$ROOT/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: worktree.sh create <task-id> [base]
       worktree.sh remove <task-id>
       worktree.sh list

create  creates ../.deepflow-<task-id> from <base> (default main),
        syncs tracked + untracked + ignored runtime files, then verifies
        that pytest can collect. Collection errors are fatal.
EOF
}

case "${1:-}" in
  create)
    id="${2:?task id required}"
    base="${3:-main}"
    dest="$PARENT/.deepflow-$id"
    git -C "$ROOT" worktree add "$dest" -b "$id" "$base"
    rsync -a --exclude '.git' --exclude '/blackboard' --exclude 'test_results' \
      --exclude '__pycache__' --exclude '.pytest_cache' --exclude 'node_modules' \
      "$ROOT/" "$dest/"
    if ! (cd "$dest" && python3 -m pytest --collect-only -q >/tmp/worktree-collect.log 2>&1); then
      echo "ERROR: collection failed in $dest; see /tmp/worktree-collect.log" >&2
      exit 1
    fi
    echo "worktree ready: $dest"
    ;;
  remove)
    id="${2:?task id required}"
    dest="$PARENT/.deepflow-$id"
    # worktrees are disposable copies; runtime-state sync makes them dirty by design
    git -C "$ROOT" worktree remove --force "$dest"
    git -C "$ROOT" branch -d "$id" 2>/dev/null || true
    ;;
  list)
    git -C "$ROOT" worktree list
    ;;
  --help|-h)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac