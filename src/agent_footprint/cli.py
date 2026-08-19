"""Command-line interface for agent-footprint."""

import argparse
import webbrowser
from pathlib import Path

from . import __version__
from .clean import clean
from .report import report
from .scan import scan

DEFAULT_DATA_DIR = Path.home() / ".cache" / "agent-footprint"


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="agent-footprint",
        description="See what AI coding agents are doing to your machine. "
                    "With no subcommand: scan, build the dashboard, and open it.")
    ap.add_argument("--version", action="version", version=f"agent-footprint {__version__}")
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                    help=f"where scan.json and dashboard.html live (default: {DEFAULT_DATA_DIR})")

    sub = ap.add_subparsers(dest="cmd")

    sp = sub.add_parser("scan", help="collect diagnostics into scan.json (read-only)")
    sp.add_argument("--roots", nargs="+", type=Path, default=[Path.home()],
                    help="directories to search for git repos (default: your home dir)")

    rp = sub.add_parser("report", help="render scan.json into dashboard.html")
    rp.add_argument("--open", action="store_true", dest="open_browser",
                    help="open the dashboard in your browser")

    cp = sub.add_parser("clean", help="prune dead worktrees and stale scratchpads")
    cp.add_argument("--apply", action="store_true",
                    help="actually prune/delete (default: dry run)")

    args = ap.parse_args(argv)

    if args.cmd == "scan":
        scan(args.roots, args.data_dir)
    elif args.cmd == "report":
        out = report(args.data_dir)
        if args.open_browser:
            webbrowser.open(out.as_uri())
    elif args.cmd == "clean":
        clean(args.data_dir, apply=args.apply)
    else:
        scan([Path.home()], args.data_dir)
        out = report(args.data_dir)
        webbrowser.open(out.as_uri())
        print(f"\nDashboard: {out}")


if __name__ == "__main__":
    main()
