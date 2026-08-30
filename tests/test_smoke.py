import unittest

from agent_footprint import __version__
from agent_footprint.cli import main


class SmokeTests(unittest.TestCase):
    def test_version_is_exposed(self):
        self.assertEqual(__version__, "0.1.0")

    def test_cli_reports_version(self):
        with self.assertRaises(SystemExit) as raised:
            main(["--version"])
        self.assertEqual(raised.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
