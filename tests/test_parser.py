from pathlib import Path
import unittest

from rule_manager.parser import parse_rules_file, parse_rules_text


ROOT = Path(__file__).resolve().parents[1]


class ParserTests(unittest.TestCase):
    def test_manual_fixture_normalizes_and_deduplicates(self) -> None:
        result = parse_rules_file(str(ROOT / "examples" / "inputs" / "manual-rules.txt"), "默认策略")
        self.assertEqual(len(result.rules), 9)
        self.assertEqual(len(result.errors), 0)
        self.assertEqual([warning.code for warning in result.warnings], ["duplicate"])
        self.assertEqual(result.rules[0].value, "example.com")
        self.assertEqual(result.rules[1].type, "domain-suffix")

    def test_url_extracts_only_hostname_and_preserves_fragment_semantics(self) -> None:
        result = parse_rules_text("https://API.Example:8443/path?q=1#fragment\n", "代理")
        self.assertEqual(result.rules[0].value, "api.example")
        self.assertEqual(result.rules[0].type, "domain")
        self.assertEqual(result.errors, [])

    def test_url_credentials_are_redacted_in_model_and_json(self) -> None:
        result = parse_rules_text("https://alice:secret@auth.example/path\n", "代理")
        serialized = str(result.to_dict())
        self.assertIn("[redacted]@auth.example", serialized)
        self.assertNotIn("alice", serialized)
        self.assertNotIn("secret", serialized)

    def test_malformed_url_credentials_are_redacted_in_error(self) -> None:
        result = parse_rules_text("https://alice:secret@[invalid\n", "代理")
        serialized = str(result.to_dict())
        self.assertEqual(result.errors[0].code, "invalid-url")
        self.assertNotIn("alice", serialized)
        self.assertNotIn("secret", serialized)

    def test_idna_normalization_preserves_unicode_metadata(self) -> None:
        result = parse_rules_text("例子.测试\n", "代理")
        self.assertEqual(result.rules[0].value, "xn--fsqu00a.xn--0zwm56d")
        self.assertEqual(result.rules[0].unicode_value, "例子.测试")

    def test_safe_inline_comment(self) -> None:
        result = parse_rules_text("example.com  # comment\n", "代理")
        self.assertEqual(result.rules[0].value, "example.com")
        self.assertEqual(result.errors, [])

    def test_explicit_rule_preserves_policy_and_normalizes_options(self) -> None:
        result = parse_rules_text("DOMAIN-SUFFIX,.Example.COM,金融服务,NO-RESOLVE\n", "默认")
        rule = result.rules[0]
        self.assertEqual(rule.type, "domain-suffix")
        self.assertEqual(rule.value, "example.com")
        self.assertEqual(rule.policy, "金融服务")
        self.assertEqual(rule.options, ("no-resolve",))

    def test_override_policy_is_explicit(self) -> None:
        result = parse_rules_text("DOMAIN,api.example,旧策略\n", "新策略", override_policy=True)
        self.assertEqual(result.rules[0].policy, "新策略")

    def test_policy_conflict_is_not_silently_deduplicated(self) -> None:
        result = parse_rules_text("DOMAIN,api.example,A\nDOMAIN,API.EXAMPLE,B\n", "默认")
        self.assertEqual(len(result.rules), 2)
        self.assertEqual([warning.code for warning in result.warnings], ["policy-conflict"])

    def test_invalid_fixture_reports_original_line_numbers(self) -> None:
        result = parse_rules_file(str(ROOT / "examples" / "inputs" / "invalid-rules.txt"), "代理")
        self.assertEqual(len(result.rules), 0)
        self.assertEqual([issue.line_number for issue in result.errors], [2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(
            [issue.code for issue in result.errors],
            [
                "missing-url-host",
                "invalid-wildcard",
                "ip-not-supported",
                "ip-not-supported",
                "ambiguous-path",
                "missing-rule-value",
                "invalid-domain",
            ],
        )

    def test_repeated_execution_is_deterministic(self) -> None:
        text = "*.Example.com\nhttps://api.example/path\nEXAMPLE.COM.\n"
        first = parse_rules_text(text, "代理").to_dict()
        second = parse_rules_text(text, "代理").to_dict()
        self.assertEqual(first, second)

    def test_cidr_is_reported_as_unsupported_ip_input(self) -> None:
        result = parse_rules_text("100.64.0.0/10\n", "代理")
        self.assertEqual(result.errors[0].code, "ip-not-supported")
