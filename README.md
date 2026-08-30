# agent-footprint

See what AI coding agents are doing to your machine.

Claude Code, Codex, Cursor, and friends leave things behind: git worktrees
nobody remembers creating, per-session scratch directories, multi-gigabyte
model caches, background processes that never exited. `agent-footprint`
inventories all of it into a local dashboard, and ships a deliberately
conservative cleaner for the safe-to-remove leftovers.

Zero dependencies (Python 3.9+ stdlib only). Nothing leaves your machine —
the scan writes a local JSON file and the dashboard is a self-contained HTML
page with the data embedded.

## Quick start

```sh
uvx agent-footprint            # or: pipx run agent-footprint
```

That scans your home directory (a minute or two), builds the dashboard, and
opens it in your browser. Or run the steps individually:

```sh
agent-footprint scan --roots ~/code ~/work   # collect (read-only)
agent-footprint report --open                # render dashboard.html
agent-footprint clean                        # dry run: what would be reclaimed
agent-footprint clean --apply                # actually do it
```

Everything lives in `~/.cache/agent-footprint/` (override with `--data-dir`).
The data directory is restricted to the current user, and generated files are
written with owner-only permissions.

> [!CAUTION]
> `scan.json` and `dashboard.html` contain local diagnostic information such
> as hostnames, filesystem paths, repository names, and scheduled task labels.
> Process arguments are not recorded. Do not publish generated files without
> reviewing them first.

## What it scans

| Area | Source |
|---|---|
| Claude home | `~/.claude` — per-subdir sizes, per-project sessions, memory files |
| Scratchpads | `/tmp/claude-<uid>/…` per-session temp dirs |
| Git worktrees | every repo under the scan roots (depth ≤ 3), `git worktree list --porcelain`, classified by creator |
| Model caches | Ollama, HuggingFace, LM Studio, MLX |
| Processes | `ps aux` filtered to agent/AI keywords, grouped in the dashboard |
| Scheduled agents | launchd (macOS), crontab, systemd user timers (Linux) |

## What `clean` touches — and what it never touches

Targets, dry-run by default:

1. **Dead worktree registrations** — `git worktree prune` per repo. Git only
   drops registrations whose directories are already gone; it never deletes a
   live checkout.
2. **Stale scratchpads** — per-session temp dirs untouched for more than 7 days.
   Paths and modification times are revalidated immediately before deletion.

Never touched: model caches, session transcripts, memory files, or any
worktree directory that still exists on disk. Removing big items — unused
Ollama models, months-old worktree checkouts — is a human decision; the
dashboard exists to inform it.

## How "creator" classification works

A heuristic, by path pattern and branch prefix:

| Creator | Signal |
|---|---|
| cursor | path contains `.cursor/worktrees` |
| codex | path contains `.codex-worktrees`, or branch starts with `codex/` |
| claude | path contains `.claude/worktrees` or `claude-` |
| openclaw | path contains `.openclaw`, or branch starts with `feat/coding-` |
| tmp | path under `/tmp` |
| manual | everything else |

If your agent leaves a different fingerprint, PRs welcome —
`classify_worktree()` in `src/agent_footprint/scan.py` is the place.

## Staleness thresholds

Scratchpads count as stale after **7 days**, worktrees after **30 days**
without modification. (Flags to tune these are on the roadmap.)

## License

MIT
