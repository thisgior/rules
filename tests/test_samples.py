from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


class SampleValidationTests(unittest.TestCase):
    def test_required_samples_exist_and_are_nonempty(self) -> None:
        expected = (
            "inputs/manual-rules.txt",
            "inputs/invalid-rules.txt",
            "inputs/logic-rules.txt",
            "clash/mihomo.yaml",
            "clash/policy-cycle.yaml",
            "loon/loon.conf",
            "dae/route.dae",
        )
        for relative in expected:
            path = EXAMPLES / relative
            with self.subTest(path=relative):
                self.assertTrue(path.is_file())
                self.assertTrue(path.read_text(encoding="utf-8").strip())

    def test_clash_yaml_samples_parse(self) -> None:
        for name in ("mihomo.yaml", "policy-cycle.yaml"):
            with self.subTest(name=name):
                data = yaml.safe_load((EXAMPLES / "clash" / name).read_text(encoding="utf-8"))
                self.assertIsInstance(data, dict)
                self.assertIsInstance(data.get("proxy-groups"), list)
                self.assertIsInstance(data.get("rules"), list)

    def test_primary_clash_sample_references_exist(self) -> None:
        data = yaml.safe_load((EXAMPLES / "clash" / "mihomo.yaml").read_text(encoding="utf-8"))
        nodes = {item["name"] for item in data["proxies"]}
        groups = {item["name"] for item in data["proxy-groups"]}
        allowed = nodes | groups | {"DIRECT", "REJECT"}
        for group in data["proxy-groups"]:
            for member in group.get("proxies", []):
                self.assertIn(member, allowed)
        for rule in data["rules"]:
            self.assertIn(rule.rsplit(",", 1)[-1], allowed)

    def test_cycle_fixture_contains_expected_cycle(self) -> None:
        data = yaml.safe_load((EXAMPLES / "clash" / "policy-cycle.yaml").read_text(encoding="utf-8"))
        graph = {group["name"]: set(group.get("proxies", [])) for group in data["proxy-groups"]}
        self.assertIn("循环组-B", graph["循环组-A"])
        self.assertIn("循环组-A", graph["循环组-B"])

    def test_samples_do_not_contain_common_secret_markers(self) -> None:
        forbidden = re.compile(
            r"(?i)(BEGIN (?:RSA |OPENSSH )?PRIVATE KEY|gh[pousr]_[A-Za-z0-9]{20,}|"
            r"sk-[A-Za-z0-9]{20,}|token\s*[:=]\s*[^\s#]+)"
        )
        for path in EXAMPLES.rglob("*"):
            if path.is_file():
                with self.subTest(path=path.relative_to(ROOT)):
                    self.assertIsNone(forbidden.search(path.read_text(encoding="utf-8")))

    def test_loon_sections_and_final_rule(self) -> None:
        text = (EXAMPLES / "loon" / "loon.conf").read_text(encoding="utf-8")
        for section in ("[General]", "[Proxy]", "[Proxy Group]", "[Rule]"):
            self.assertIn(section, text)
        self.assertRegex(text, r"(?m)^FINAL,故障转移$")

    def test_dae_has_required_blocks_and_fallback(self) -> None:
        text = (EXAMPLES / "dae" / "route.dae").read_text(encoding="utf-8")
        for block in ("global {", "node {", "group {", "routing {"):
            self.assertIn(block, text)
        self.assertRegex(text, r"(?m)^\s*fallback:\s+direct$")


if __name__ == "__main__":
    unittest.main()
