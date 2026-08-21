from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
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

    def test_parse_rules_returns_parse_exit_code_with_line_report(self) -> None:
        output = StringIO()
        invalid = ROOT / "examples" / "inputs" / "invalid-rules.txt"
        with redirect_stdout(output):
            code = main(["parse-rules", str(invalid), "--policy", "代理"])
        self.assertEqual(code, 2)
        self.assertIn("第 2 行", output.getvalue())
        self.assertIn("未写入任何规则", output.getvalue())

    def test_parse_rules_rejects_empty_policy(self) -> None:
        errors = StringIO()
        manual = ROOT / "examples" / "inputs" / "manual-rules.txt"
        with redirect_stderr(errors):
            code = main(["parse-rules", str(manual), "--policy", "  "])
        self.assertEqual(code, 1)
        self.assertIn("策略名称不能为空", errors.getvalue())

    def test_rule_project_cli_lifecycle(self) -> None:
        with TemporaryDirectory() as directory:
            project = Path(directory) / "rules-project"
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["init-project", str(project)]), 0)
                self.assertEqual(main([
                    "add-rules", str(project), str(ROOT / "examples" / "inputs" / "manual-rules.txt"),
                    "--policy", "代理", "--source-id", "manual",
                ]), 0)
                self.assertEqual(main(["list-rules", str(project)]), 0)
            self.assertIn("来源：manual", output.getvalue())
            self.assertIn("未修改代理配置", output.getvalue())

    def test_add_rules_with_parse_error_does_not_write(self) -> None:
        with TemporaryDirectory() as directory:
            project = Path(directory) / "rules-project"
            invalid = ROOT / "examples" / "inputs" / "invalid-rules.txt"
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init-project", str(project)]), 0)
                code = main([
                    "add-rules", str(project), str(invalid), "--policy", "代理", "--source-id", "bad",
                ])
            self.assertEqual(code, 2)
            self.assertEqual(list((project / "sources").iterdir()), [])
