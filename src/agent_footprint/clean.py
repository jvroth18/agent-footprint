"""Cleaner: reclaims space from stale agent leftovers. Dry-run by default.

Targets (conservative on purpose):
  1. Prunable/missing git worktrees  -> `git worktree prune` per repo
     (git only drops registrations whose directories are already gone;
     it never deletes a live checkout)
  2. Stale scratchpad session dirs (> 7 days old) -> delete

Never touched: model caches, session transcripts, memory files, or any
worktree directory that still exists on disk.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path


def fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def clean(data_dir, apply=False):
    scan_path = Path(data_dir) / "scan.json"
    if not scan_path.exists():
        sys.exit(f"No {scan_path} - run `agent-footprint scan` first.")
    scan = json.loads(scan_path.read_text())

    mode = "APPLY" if apply else "DRY RUN"
    print(f"== agent-footprint clean ({mode}) ==\n")

    # 1. prunable worktrees, grouped by repo
    total_repos = 0
    for repo in scan["worktrees"]:
        prunable = [w for w in repo["worktrees"] if w["prunable"] or w["missing"]]
        if not prunable:
            continue
        total_repos += 1
        print(f"{repo['name']}  ({repo['repo']})")
        for w in prunable:
            state = "missing" if w["missing"] else "prunable"
            print(f"  - {w['branch']:<45} {state:<9} {w['path']}")
        if apply:
            r = subprocess.run(["git", "worktree", "prune", "-v"],
                               cwd=repo["repo"], capture_output=True, text=True)
            out = (r.stdout + r.stderr).strip()
            print(f"  pruned: {out or '(nothing reported)'}")
        print()
    if total_repos == 0:
        print("No prunable worktrees.\n")

    # 2. stale scratchpads
    stale = [p for p in scan["scratchpads"] if p["stale"]]
    stale_bytes = sum(p["bytes"] for p in stale)
    if stale:
        print(f"Stale scratchpads (> 7 days, {fmt_bytes(stale_bytes)} total):")
        for p in stale:
            print(f"  - {fmt_bytes(p['bytes']):>9}  {p['age_days']:>5.1f}d  {p['path']}")
            if apply:
                shutil.rmtree(p["path"], ignore_errors=True)
        if apply:
            print("  deleted.")
    else:
        print("No stale scratchpads.")

    print(f"\nReclaimable from scratchpads: {fmt_bytes(stale_bytes)}")
    if not apply:
        print("Re-run with --apply to execute, then `agent-footprint scan` to refresh.")
