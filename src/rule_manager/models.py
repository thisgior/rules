"""Read-only data models used by the first development step."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


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
