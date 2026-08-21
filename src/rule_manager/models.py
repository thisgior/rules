"""Data models shared by inspection, parsing, and rule projects."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class PolicyGroupSummary:
    """Non-sensitive policy group metadata."""

    name: str
    type: str
    member_count: int


@dataclass(frozen=True)
class ConfigSummary:
    """A sanitized, read-only Clash/Mihomo configuration summary."""

    path: str
    node_names: List[str] = field(default_factory=list)
    policy_groups: List[PolicyGroupSummary] = field(default_factory=list)
    provider_names: List[str] = field(default_factory=list)
    rule_count: int = 0
    warnings: List[str] = field(default_factory=list)
    read_only: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe representation without source configuration values."""

        return asdict(self)


@dataclass(frozen=True)
class EnvironmentSummary:
    """Runtime compatibility and permission facts."""

    os_id: str
    os_version: str
    debian_supported: bool
    python_version: str
    running_as_root: bool
    sudo_available: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Rule:
    """A normalized ordinary rule with traceable, sanitized input metadata."""

    line_number: int
    type: str
    value: str
    policy: Optional[str]
    options: Tuple[str, ...] = ()
    original: str = ""
    unicode_value: Optional[str] = None

    @property
    def dedupe_key(self) -> Tuple[str, str, Tuple[str, ...]]:
        return (self.type, self.value, self.options)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ParseIssue:
    """A line-specific parse error, duplicate notice, or policy conflict."""

    line_number: int
    code: str
    message: str
    original: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ParseResult:
    """Deterministic result for a batch of ordinary input lines."""

    rules: List[Rule] = field(default_factory=list)
    errors: List[ParseIssue] = field(default_factory=list)
    warnings: List[ParseIssue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rules": [rule.to_dict() for rule in self.rules],
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
            "summary": {
                "rule_count": len(self.rules),
                "error_count": len(self.errors),
                "warning_count": len(self.warnings),
            },
        }


@dataclass(frozen=True)
class ProjectRule:
    """A persisted rule with stable identity and source metadata."""

    id: str
    type: str
    value: str
    policy: str
    options: Tuple[str, ...]
    source_id: str
    original: str
    enabled: bool
    priority: int
    created_at: str
    unicode_value: Optional[str] = None

    @property
    def dedupe_key(self) -> Tuple[str, str, Tuple[str, ...]]:
        return (self.type, self.value, self.options)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["options"] = list(self.options)
        return data


@dataclass(frozen=True)
class RuleSource:
    """Traceable metadata for one managed source file."""

    id: str
    kind: str
    label: str
    location: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProjectResult:
    """Result of a rule-project read or mutation."""

    rules: List[ProjectRule] = field(default_factory=list)
    sources: List[RuleSource] = field(default_factory=list)
    warnings: List[ParseIssue] = field(default_factory=list)
    added_count: int = 0
    changed_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sources": [source.to_dict() for source in self.sources],
            "rules": [rule.to_dict() for rule in self.rules],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "summary": {
                "source_count": len(self.sources),
                "rule_count": len(self.rules),
                "enabled_count": sum(1 for rule in self.rules if rule.enabled),
                "added_count": self.added_count,
                "changed_count": self.changed_count,
                "warning_count": len(self.warnings),
            },
        }
