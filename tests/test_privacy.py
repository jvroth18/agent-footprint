import json
import os
import stat
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from agent_footprint.clean import clean, validate_scratchpad_path
from agent_footprint.privacy import ensure_private_directory, write_private_text
from agent_footprint.report import sanitize_report_data
from agent_footprint.scan import scan_processes, summarize_cron_line


class PrivateOutputTests(unittest.TestCase):
    def test_private_directory_and_file_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary) / "data"
            data_dir.mkdir(mode=0o755)
            ensure_private_directory(data_dir)
            output = write_private_text(data_dir / "scan.json", "sensitive")

            self.assertEqual(stat.S_IMODE(data_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertEqual(output.read_text(), "sensitive")

    def test_private_write_replaces_symlink_instead_of_following_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.write_text("do not overwrite")
            output = root / "scan.json"
            output.symlink_to(target)

            write_private_text(output, "new report")

            self.assertEqual(target.read_text(), "do not overwrite")
            self.assertFalse(output.is_symlink())
            self.assertEqual(output.read_text(), "new report")


class CommandRedactionTests(unittest.TestCase):
    def test_process_arguments_are_not_recorded(self):
        ps = "\n".join([
            "USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND",
            "me 99999 1.0 0.1 100 2048 ? S 10:00 0:01 /usr/local/bin/codex --token secret-value",
        ])
        with patch("agent_footprint.scan.run", return_value=ps):
            processes = scan_processes()

        self.assertEqual(processes[0]["executable"], "codex")
        self.assertEqual(processes[0]["category"], "codex")
        self.assertNotIn("secret-value", json.dumps(processes))
        self.assertNotIn("command", processes[0])

    def test_cron_summary_excludes_command_and_secret(self):
        summary = summarize_cron_line(
            "0 2 * * * /usr/local/bin/codex --token secret-value"
        )
        self.assertEqual(summary, "0 2 * * * · codex")

    def test_unrelated_cron_entry_is_not_recorded(self):
        self.assertIsNone(summarize_cron_line("0 2 * * * /usr/bin/backup"))

    def test_report_removes_legacy_process_and_cron_commands(self):
        secret = "secret-value"
        data = {
            "processes": [{"command": f"codex --token {secret}"}],
            "schedulers": {"cron": [f"0 2 * * * codex --token {secret}"]},
        }

        sanitized = sanitize_report_data(data)

        self.assertNotIn(secret, json.dumps(sanitized))
        self.assertEqual(sanitized["processes"][0]["executable"], "unknown")
        self.assertEqual(sanitized["schedulers"]["cron"], [])


class CleanerValidationTests(unittest.TestCase):
    def make_session(self, root, uid=None, age_days=8):
        uid = os.getuid() if uid is None else uid
        session = root / f"claude-{uid}" / "project" / "session"
        session.mkdir(parents=True)
        modified = time.time() - age_days * 86400
        os.utime(session, (modified, modified))
        return session

    def test_accepts_only_currently_stale_session_shape(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = self.make_session(root)
            safe_path, reason = validate_scratchpad_path(
                session, tmp_roots=[root]
            )
            self.assertEqual(safe_path, session.resolve())
            self.assertIsNone(reason)

    def test_rejects_path_outside_scratchpad_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            allowed = base / "allowed"
            allowed.mkdir()
            session = self.make_session(base / "outside")
            safe_path, reason = validate_scratchpad_path(
                session, tmp_roots=[allowed]
            )
            self.assertIsNone(safe_path)
            self.assertIn("outside", reason)

    def test_rejects_fresh_or_symbolic_link_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fresh = self.make_session(root, age_days=1)
            safe_path, reason = validate_scratchpad_path(
                fresh, tmp_roots=[root]
            )
            self.assertIsNone(safe_path)
            self.assertIn("no longer stale", reason)

            link = root / "linked-session"
            link.symlink_to(fresh, target_is_directory=True)
            safe_path, reason = validate_scratchpad_path(
                link, tmp_roots=[root]
            )
            self.assertIsNone(safe_path)
            self.assertIn("symbolic link", reason)

    def test_rejects_intermediate_symbolic_link(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_project = root / f"claude-{os.getuid()}" / "real-project"
            session = real_project / "session"
            session.mkdir(parents=True)
            os.utime(session, (time.time() - 8 * 86400,) * 2)
            linked_project = root / f"claude-{os.getuid()}" / "linked-project"
            linked_project.symlink_to(real_project, target_is_directory=True)

            safe_path, reason = validate_scratchpad_path(
                linked_project / "session", tmp_roots=[root]
            )

            self.assertIsNone(safe_path)
            self.assertIn("symbolic link", reason)

    def test_tampered_scan_cannot_delete_arbitrary_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_dir = root / "data"
            victim = root / "important"
            victim.mkdir()
            os.utime(victim, (time.time() - 10 * 86400,) * 2)
            data_dir.mkdir()
            (data_dir / "scan.json").write_text(json.dumps({
                "worktrees": [],
                "scratchpads": [{
                    "path": str(victim),
                    "bytes": 1,
                    "age_days": 10,
                    "stale": True,
                }],
            }))

            with redirect_stdout(StringIO()) as output:
                clean(data_dir, apply=True)

            self.assertTrue(victim.is_dir())
            self.assertIn("Rejected unsafe", output.getvalue())


if __name__ == "__main__":
    unittest.main()
