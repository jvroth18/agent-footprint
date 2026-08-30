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
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


STALE_SCRATCHPAD_DAYS = 7


def validate_scratchpad_path(raw_path, uid=None, tmp_roots=None, now=None):
    """Return a safe, currently stale scratchpad path or a rejection reason."""
    uid = os.getuid() if uid is None else uid
    now = time.time() if now is None else now
    roots = ([Path("/private/tmp"), Path("/tmp")] if tmp_roots is None
             else [Path(path) for path in tmp_roots])
    candidate = Path(raw_path).absolute()

    if candidate.is_symlink():
        return None, "path is a symbolic link"
    lexical_root = None
    lexical_relative = None
    for root in roots:
        try:
            lexical_relative = candidate.relative_to(root.absolute())
            lexical_root = root.absolute()
            break
        except ValueError:
            continue
    if lexical_root is None:
        return None, "path is outside the scratchpad roots"
    cursor = lexical_root
    for part in lexical_relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return None, "path contains a symbolic link"
        try:
            if cursor.stat().st_uid != uid:
                return None, "path is not owned by the current user"
        except OSError:
            return None, "path could not be inspected"

    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None, "path no longer exists"
    if not resolved.is_dir():
        return None, "path is not a directory"

    relative = None
    for root in roots:
        try:
            relative = resolved.relative_to(root.resolve(strict=True))
            break
        except (OSError, RuntimeError, ValueError):
            continue
    if relative is None:
        return None, "path is outside the scratchpad roots"

    parts = relative.parts
    expected_root = f"claude-{uid}"
    valid_root_name = parts and (
        parts[0] == expected_root or parts[0].startswith(f"{expected_root}-")
    )
    if len(parts) != 3 or not valid_root_name:
        return None, "path is not a Claude session scratchpad"

    try:
        age_days = (now - resolved.stat().st_mtime) / 86400
    except OSError:
        return None, "path could not be inspected"
    if age_days <= STALE_SCRATCHPAD_DAYS:
        return None, "path is no longer stale"
    return resolved, None


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
    stale = []
    rejected = []
    for record in scan["scratchpads"]:
        if not record.get("stale"):
            continue
        safe_path, reason = validate_scratchpad_path(record.get("path", ""))
        if safe_path is None:
            rejected.append((record.get("path", "(missing path)"), reason))
        else:
            stale.append({**record, "path": str(safe_path)})
    stale_bytes = sum(p["bytes"] for p in stale)
    deleted = 0
    if stale:
        print(f"Stale scratchpads (> 7 days, {fmt_bytes(stale_bytes)} total):")
        for p in stale:
            print(f"  - {fmt_bytes(p['bytes']):>9}  {p['age_days']:>5.1f}d  {p['path']}")
            if apply:
                safe_path, reason = validate_scratchpad_path(p["path"])
                if safe_path is None:
                    print(f"    skipped: {reason}")
                    continue
                shutil.rmtree(safe_path)
                deleted += 1
        if apply:
            print(f"  deleted {deleted} scratchpad(s).")
    else:
        print("No stale scratchpads.")

    if rejected:
        print("\nRejected unsafe or changed scratchpad paths:")
        for path, reason in rejected:
            print(f"  - {path}: {reason}")

    print(f"\nReclaimable from scratchpads: {fmt_bytes(stale_bytes)}")
    if not apply:
        print("Re-run with --apply to execute, then `agent-footprint scan` to refresh.")
