from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import yaml

from rule_manager.errors import ConfigValidationError, UserInputError
from rule_manager.parser import parse_rules_text
from rule_manager.workspace import add_rules, delete_rule, init_project, list_project, set_rule_enabled


class WorkspaceTests(unittest.TestCase):
    def test_init_creates_sources_directory(self) -> None:
        with TemporaryDirectory() as directory:
            project = Path(directory) / "rules-project"
            result = init_project(str(project))
            self.assertTrue((project / "sources").is_dir())
            self.assertEqual(result.rules, [])

    def test_add_persists_traceable_source_and_rules(self) -> None:
        with TemporaryDirectory() as directory:
            project = Path(directory) / "rules-project"
            init_project(str(project))
            result = add_rules(
                str(project), parse_rules_text("example.com\n*.example.org\n", "代理"),
                "manual-finance", "manual", "金融规则", created_at="2026-08-21T00:00:00+00:00",
            )
            self.assertEqual(result.added_count, 2)
            self.assertEqual(result.rules[0].source_id, "manual-finance")
            self.assertEqual(result.rules[0].priority, 100)
            payload = yaml.safe_load((project / "sources" / "manual-finance.yaml").read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["source"]["label"], "金融规则")
            self.assertEqual(payload["rules"][0]["created_at"], "2026-08-21T00:00:00+00:00")

    def test_project_duplicate_is_skipped_across_sources(self) -> None:
        with TemporaryDirectory() as directory:
            project = Path(directory) / "rules-project"
            init_project(str(project))
            parsed = parse_rules_text("example.com\n", "代理")
            add_rules(str(project), parsed, "first", "manual")
            result = add_rules(str(project), parsed, "second", "local-file")
            self.assertEqual(result.added_count, 0)
            self.assertEqual(len(result.rules), 1)
            self.assertEqual(result.warnings[-1].code, "project-duplicate")
            self.assertFalse((project / "sources" / "second.yaml").exists())

    def test_policy_conflict_preserves_both_rules(self) -> None:
        with TemporaryDirectory() as directory:
            project = Path(directory) / "rules-project"
            init_project(str(project))
            add_rules(str(project), parse_rules_text("example.com\n", "A"), "a", "manual")
            result = add_rules(str(project), parse_rules_text("EXAMPLE.COM\n", "B"), "b", "manual")
            self.assertEqual(len(result.rules), 2)
            self.assertEqual(result.warnings[-1].code, "project-policy-conflict")
            self.assertEqual({rule.policy for rule in result.rules}, {"A", "B"})

    def test_disable_enable_and_delete_by_id(self) -> None:
        with TemporaryDirectory() as directory:
            project = Path(directory) / "rules-project"
            init_project(str(project))
            added = add_rules(str(project), parse_rules_text("example.com\n", "代理"), "manual", "manual")
            rule_id = added.rules[0].id
            self.assertFalse(set_rule_enabled(str(project), rule_id, False).rules[0].enabled)
            self.assertEqual(list_project(str(project), enabled_only=True).rules, [])
            self.assertTrue(set_rule_enabled(str(project), rule_id, True).rules[0].enabled)
            self.assertEqual(delete_rule(str(project), rule_id).rules, [])

    def test_invalid_input_never_creates_source(self) -> None:
        with TemporaryDirectory() as directory:
            project = Path(directory) / "rules-project"
            init_project(str(project))
            with self.assertRaises(UserInputError):
                add_rules(str(project), parse_rules_text("not/a/domain\n", "代理"), "bad", "manual")
            self.assertEqual(list((project / "sources").iterdir()), [])

    def test_source_id_cannot_escape_sources_directory(self) -> None:
        with TemporaryDirectory() as directory:
            project = Path(directory) / "rules-project"
            init_project(str(project))
            with self.assertRaises(UserInputError):
                add_rules(str(project), parse_rules_text("example.com\n", "代理"), "../escape", "manual")

    def test_location_rejects_embedded_credentials(self) -> None:
        with TemporaryDirectory() as directory:
            project = Path(directory) / "rules-project"
            init_project(str(project))
            with self.assertRaises(UserInputError):
                add_rules(
                    str(project), parse_rules_text("example.com\n", "代理"), "remote", "remote-url",
                    location="https://user:secret@example.com/rules.txt",
                )

    def test_corrupt_source_is_rejected_before_listing(self) -> None:
        with TemporaryDirectory() as directory:
            project = Path(directory) / "rules-project"
            init_project(str(project))
            (project / "sources" / "bad.yaml").write_text("schema_version: 9\n", encoding="utf-8")
            with self.assertRaises(ConfigValidationError):
                list_project(str(project))

    def test_atomic_write_leaves_no_temporary_file(self) -> None:
        with TemporaryDirectory() as directory:
            project = Path(directory) / "rules-project"
            init_project(str(project))
            add_rules(str(project), parse_rules_text("example.com\n", "代理"), "manual", "manual")
            self.assertEqual([path.name for path in (project / "sources").iterdir()], ["manual.yaml"])
