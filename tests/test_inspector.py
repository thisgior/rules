from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rule_manager.errors import ConfigParseError, ConfigValidationError
from rule_manager.inspector import inspect_config


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "clash" / "mihomo.yaml"


class InspectorTests(unittest.TestCase):
    def test_inspects_expected_metadata(self) -> None:
        summary = inspect_config(str(SAMPLE))
        self.assertEqual(summary.node_names, ["本机测试节点"])
        self.assertEqual([group.name for group in summary.policy_groups], ["故障转移", "金融服务"])
        self.assertEqual(summary.provider_names, ["private-domains"])
        self.assertEqual(summary.rule_count, 4)
        self.assertTrue(summary.read_only)

    def test_summary_does_not_include_sensitive_configuration_values(self) -> None:
        serialized = str(inspect_config(str(SAMPLE)).to_dict())
        for forbidden in ("127.0.0.1", "1080", "rules.example", "generate_204"):
            self.assertNotIn(forbidden, serialized)

    def test_reports_yaml_line_and_column(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "broken.yaml"
            path.write_text("rules: [\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigParseError, "第 2 行"):
                inspect_config(str(path))

    def test_rejects_non_mapping_top_level(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "list.yaml"
            path.write_text("- item\n", encoding="utf-8")
            with self.assertRaises(ConfigValidationError):
                inspect_config(str(path))
