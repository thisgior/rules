"""Data models shared by inspection and ordinary rule parsing."""

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
