from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rule_manager.environment import detect_environment, parse_os_release


class EnvironmentTests(unittest.TestCase):
    def test_parse_os_release_quotes(self) -> None:
        values = parse_os_release('ID=debian\nVERSION_ID="12"\nPRETTY_NAME="Debian GNU/Linux 12"\n')
        self.assertEqual(values["ID"], "debian")
        self.assertEqual(values["VERSION_ID"], "12")

    def test_debian_11_to_13_are_supported(self) -> None:
        for version in ("11", "12", "13"):
            with self.subTest(version=version), TemporaryDirectory() as directory:
                path = Path(directory) / "os-release"
                path.write_text("ID=debian\nVERSION_ID=%s\n" % version, encoding="utf-8")
                self.assertTrue(detect_environment(path).debian_supported)

    def test_other_debian_version_is_not_supported(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "os-release"
            path.write_text("ID=debian\nVERSION_ID=10\n", encoding="utf-8")
            self.assertFalse(detect_environment(path).debian_supported)
