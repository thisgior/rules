from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import unittest

from rule_manager.cli import main


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "clash" / "mihomo.yaml"


class CliTests(unittest.TestCase):
    def test_inspect_config_text_is_sanitized(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            code = main(["inspect-config", str(SAMPLE)])
        self.assertEqual(code, 0)
        text = output.getvalue()
        self.assertIn("金融服务", text)
        self.assertIn("未修改配置", text)
        self.assertNotIn("127.0.0.1", text)
        self.assertNotIn("rules.example", text)

    def test_missing_file_uses_stable_io_exit_code(self) -> None:
        errors = StringIO()
        with redirect_stderr(errors):
            code = main(["inspect-config", "/definitely/missing/config.yaml"])
        self.assertEqual(code, 5)
        self.assertTrue(errors.getvalue().startswith("错误："))
