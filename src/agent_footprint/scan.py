"""Read-only scanner: inventories AI-agent activity and disk footprint.

Collects into <data_dir>/scan.json:
  - ~/.claude breakdown (plugins, projects, sessions per project, memory files)
  - Claude scratchpad dirs under /tmp (and /private/tmp on macOS)
  - Git worktrees across repos under the scan roots, classified by which agent
    created them, with prunable/missing/stale flags
  - Model caches (Ollama, HuggingFace, LM Studio, MLX)
  - Running AI-related processes
  - Scheduled agents (launchd on macOS, crontab, systemd user timers on Linux)

Stdlib only. Never modifies anything (cleanup lives in clean.py).
"""

import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .privacy import ensure_private_directory, write_private_text

HOME = Path.home()
CLAUDE_HOME = HOME / ".claude"
NOW = time.time()
STALE_SCRATCHPAD_DAYS = 7
STALE_WORKTREE_DAYS = 30
REPO_SCAN_DEPTH = 3

AI_PROCESS_KEYWORDS = ("claude", "ollama", "codex", "openclaw", "lmstudio",
                       "lm-studio", "mlx", "anthropic", "copilot", "aider")
AI_SCHEDULER_KEYWORDS = ("openclaw", "claude", "ollama", "agent", "codex",
                         "anthropic", "copilot", "aider")

SKIP_DIRS = {"node_modules", ".build", "Pods", "venv", ".venv", "__pycache__",
             "Library", "Applications", "Music", "Movies", "Pictures",
             ".Trash", "go", "target", "dist", "build"}


def run(cmd, timeout=30, cwd=None):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return out.stdout
    except (subprocess.TimeoutExpired, OSError):
        return ""


def du_kb(path):
    out = run(["du", "-sk", str(path)], timeout=120)
    try:
        return int(out.split()[0]) * 1024
    except (IndexError, ValueError):
        return 0


def mtime_iso(path):
    try:
        return datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).isoformat()
    except OSError:
        return None


def age_days(path):
    try:
        return round((NOW - os.path.getmtime(path)) / 86400, 1)
    except OSError:
        return None


# ---------------------------------------------------------------- ~/.claude

def scan_claude_home():
    subdirs = []
    if CLAUDE_HOME.is_dir():
        for entry in sorted(CLAUDE_HOME.iterdir()):
            subdirs.append({"name": entry.name, "bytes": du_kb(entry)})
    subdirs.sort(key=lambda d: -d["bytes"])

    projects = []
    proj_root = CLAUDE_HOME / "projects"
    if proj_root.is_dir():
        for proj in sorted(proj_root.iterdir()):
            if not proj.is_dir():
                continue
            sessions = []
            for jl in proj.glob("*.jsonl"):
                first_ts = None
                try:
                    with open(jl, "r", errors="replace") as f:
                        head = f.read(8192)
                    m = re.search(r'"timestamp"\s*:\s*"([^"]+)"', head)
                    if m:
                        first_ts = m.group(1)
                except OSError:
                    pass
                sessions.append({
                    "id": jl.stem,
                    "bytes": jl.stat().st_size,
                    "started": first_ts,
                    "last_active": mtime_iso(jl),
                })
            memory_dir = proj / "memory"
            memory_files = len(list(memory_dir.glob("*.md"))) if memory_dir.is_dir() else 0
            projects.append({
                "name": proj.name,
                "bytes": du_kb(proj),
                "session_count": len(sessions),
                "memory_files": memory_files,
                "last_active": mtime_iso(proj),
                "sessions": sorted(sessions, key=lambda s: s["last_active"] or "", reverse=True),
            })
    projects.sort(key=lambda p: -p["bytes"])
    return {"total_bytes": du_kb(CLAUDE_HOME) if CLAUDE_HOME.is_dir() else 0,
            "subdirs": subdirs, "projects": projects}


# ---------------------------------------------------------------- scratchpads

def scan_scratchpads():
    pads = []
    seen = set()
    uid = os.getuid()
    # /tmp is a symlink to /private/tmp on macOS — resolve to dedupe
    for tmp_root in (Path("/private/tmp"), Path("/tmp")):
        if not tmp_root.is_dir():
            continue
        for root in tmp_root.glob(f"claude-{uid}*"):
            for proj in root.iterdir() if root.is_dir() else []:
                if not proj.is_dir():
                    continue
                for session in proj.iterdir():
                    if not session.is_dir():
                        continue
                    real = os.path.realpath(session)
                    if real in seen:
                        continue
                    seen.add(real)
                    age = age_days(session)
                    pads.append({
                        "path": str(session),
                        "project": proj.name,
                        "bytes": du_kb(session),
                        "age_days": age,
                        "stale": age is not None and age > STALE_SCRATCHPAD_DAYS,
                    })
    pads.sort(key=lambda p: -p["bytes"])
    return pads


# ---------------------------------------------------------------- worktrees

def classify_worktree(path, branch=""):
    p = path.lower()
    b = (branch or "").lower()
    if "/.cursor/worktrees/" in p:
        return "cursor"
    if ".codex-worktrees" in p or b.startswith("codex/"):
        return "codex"
    if "/.claude/worktrees/" in p or "/claude-" in p:
        return "claude"
    if "/.openclaw/" in p or b.startswith("feat/coding-"):
        return "openclaw"
    if p.startswith("/private/tmp/") or p.startswith("/tmp/"):
        return "tmp"
    return "manual"


def find_repos(roots):
    repos = []
    for root in roots:
        root = Path(root).expanduser()
        if not root.is_dir():
            continue
        for dirpath, dirnames, _ in os.walk(root):
            depth = len(Path(dirpath).relative_to(root).parts)
            if depth >= REPO_SCAN_DEPTH:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames
                           if d not in SKIP_DIRS and not d.startswith(".")]
            if (Path(dirpath) / ".git").is_dir():
                repos.append(Path(dirpath))
    return repos


def scan_worktrees(roots):
    seen_mains = set()
    repos_out = []
    for repo in find_repos(roots):
        porcelain = run(["git", "worktree", "list", "--porcelain"], cwd=repo, timeout=15)
        if not porcelain.strip():
            continue
        entries = []
        cur = {}
        for line in porcelain.splitlines() + [""]:
            if not line.strip():
                if cur:
                    entries.append(cur)
                    cur = {}
                continue
            if line.startswith("worktree "):
                cur["path"] = line[len("worktree "):]
            elif line.startswith("branch "):
                cur["branch"] = line[len("branch "):].replace("refs/heads/", "")
            elif line == "detached":
                cur["branch"] = "(detached)"
            elif line.startswith("prunable"):
                cur["prunable"] = True
        if not entries:
            continue
        main = entries[0]["path"]
        if main in seen_mains:
            continue
        seen_mains.add(main)
        linked = []
        for e in entries[1:]:
            exists = os.path.isdir(e["path"])
            age = age_days(e["path"]) if exists else None
            linked.append({
                "path": e["path"],
                "branch": e.get("branch", "?"),
                "source": classify_worktree(e["path"], e.get("branch", "")),
                "prunable": e.get("prunable", False),
                "missing": not exists,
                "age_days": age,
                "stale": age is not None and age > STALE_WORKTREE_DAYS,
                "bytes": du_kb(e["path"]) if exists else 0,
            })
        if linked:
            repos_out.append({
                "repo": main,
                "name": Path(main).name,
                "worktrees": linked,
            })
    repos_out.sort(key=lambda r: -len(r["worktrees"]))
    return repos_out


# ---------------------------------------------------------------- caches

def scan_model_caches():
    candidates = {
        "Ollama models": HOME / ".ollama",
        "HuggingFace cache": HOME / ".cache" / "huggingface",
        "LM Studio": HOME / ".lmstudio",
        "Claude CLI cache": HOME / "Library" / "Caches" / "claude-cli-nodejs",
        "MLX cache": HOME / ".cache" / "mlx",
    }
    out = []
    for label, path in candidates.items():
        if path.exists():
            out.append({"name": label, "path": str(path), "bytes": du_kb(path)})
    out.sort(key=lambda c: -c["bytes"])

    ollama_models = []
    listing = run(["ollama", "list"], timeout=10)
    for line in listing.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 3:
            ollama_models.append({"name": parts[0], "size": " ".join(parts[2:4])})
    return {"caches": out, "ollama_models": ollama_models}


# ---------------------------------------------------------------- processes

def scan_processes():
    out = []
    ps = run(["ps", "aux"], timeout=15)
    my_pid = os.getpid()
    for line in ps.splitlines()[1:]:
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        raw_command = parts[10]
        low = raw_command.lower()
        category = next((k for k in AI_PROCESS_KEYWORDS if k in low), None)
        if category is None:
            continue
        if "grep" in low or int(parts[1]) == my_pid:
            continue
        try:
            executable = Path(shlex.split(raw_command)[0]).name
        except (IndexError, ValueError):
            executable = "unknown"
        out.append({
            "pid": int(parts[1]),
            "cpu_pct": float(parts[2]),
            "rss_mb": round(int(parts[5]) / 1024),
            "executable": executable[:80],
            "category": category,
        })
    out.sort(key=lambda p: -p["cpu_pct"])
    return out


def summarize_cron_line(line):
    """Return a non-sensitive schedule/category summary for an AI cron entry."""
    stripped = line.strip()
    low = stripped.lower()
    category = next((k for k in AI_SCHEDULER_KEYWORDS if k in low), None)
    if not stripped or stripped.startswith("#") or category is None:
        return None
    fields = stripped.split()
    if fields[0].startswith("@"):
        schedule = fields[0]
    elif len(fields) >= 6:
        schedule = " ".join(fields[:5])
    else:
        return None
    return f"{schedule} · {category}"


# ---------------------------------------------------------------- schedulers

def scan_schedulers():
    agents = []
    la_dir = HOME / "Library" / "LaunchAgents"
    if sys.platform == "darwin" and la_dir.is_dir():
        for plist in sorted(la_dir.glob("*.plist")):
            label = plist.stem
            agents.append({
                "label": label,
                "ai_related": any(k in label.lower() for k in AI_SCHEDULER_KEYWORDS),
            })
    if sys.platform.startswith("linux"):
        timers = run(["systemctl", "--user", "list-timers", "--all", "--no-pager"], timeout=10)
        for line in timers.splitlines():
            low = line.lower()
            if any(k in low for k in AI_SCHEDULER_KEYWORDS):
                agents.append({"label": line.strip()[:120], "ai_related": True})
    cron = [summary for line in run(["crontab", "-l"], timeout=10).splitlines()
            if (summary := summarize_cron_line(line)) is not None]
    return {"launch_agents": agents, "cron": cron}


# ---------------------------------------------------------------- entry point

def scan(roots, data_dir):
    data_dir = ensure_private_directory(data_dir)

    print("Scanning ~/.claude ...", file=sys.stderr)
    claude_home = scan_claude_home()
    print("Scanning scratchpads ...", file=sys.stderr)
    scratchpads = scan_scratchpads()
    print(f"Scanning git worktrees under {', '.join(str(r) for r in roots)} "
          "(this is the slow one) ...", file=sys.stderr)
    worktrees = scan_worktrees(roots)
    print("Scanning model caches ...", file=sys.stderr)
    caches = scan_model_caches()
    print("Scanning processes and schedulers ...", file=sys.stderr)
    processes = scan_processes()
    schedulers = scan_schedulers()

    all_wt = [w for r in worktrees for w in r["worktrees"]]
    summary = {
        "claude_home_bytes": claude_home["total_bytes"],
        "scratchpad_bytes": sum(p["bytes"] for p in scratchpads),
        "cache_bytes": sum(c["bytes"] for c in caches["caches"]),
        "worktree_count": len(all_wt),
        "worktree_bytes": sum(w["bytes"] for w in all_wt),
        "prunable_worktrees": sum(1 for w in all_wt if w["prunable"] or w["missing"]),
        "stale_worktrees": sum(1 for w in all_wt if w["stale"] and not (w["prunable"] or w["missing"])),
        "session_count": sum(p["session_count"] for p in claude_home["projects"]),
        "running_processes": len(processes),
    }

    doc = {
        "tool_version": __version__,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "host": os.uname().nodename,
        "roots": [str(r) for r in roots],
        "summary": summary,
        "claude_home": claude_home,
        "scratchpads": scratchpads,
        "worktrees": worktrees,
        "model_caches": caches,
        "processes": processes,
        "schedulers": schedulers,
    }

    out_path = data_dir / "scan.json"
    write_private_text(out_path, json.dumps(doc, indent=1))
    print(f"Wrote {out_path} ({out_path.stat().st_size // 1024} KB)", file=sys.stderr)
    return out_path
