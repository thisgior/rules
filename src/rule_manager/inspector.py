"""Sanitized, read-only Clash/Mihomo configuration inspection."""

from pathlib import Path
from typing import Any, Dict, List

import yaml

from .errors import ConfigParseError, ConfigValidationError, FileAccessError
from .models import ConfigSummary, PolicyGroupSummary


MAX_CONFIG_BYTES = 32 * 1024 * 1024


def _require_list(config: Dict[str, Any], key: str) -> List[Any]:
    value = config.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConfigValidationError("字段 %s 必须是列表。" % key)
    return value


def _require_mapping(config: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = config.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigValidationError("字段 %s 必须是映射。" % key)
    return value


def inspect_config(path_value: str) -> ConfigSummary:
    """Read a regular YAML file and return only explicitly allowed metadata."""

    if not path_value.strip():
        raise FileAccessError("配置路径不能为空。")

    path = Path(path_value).expanduser()
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise FileAccessError("目标不是普通文件：%s" % resolved)
        size = resolved.stat().st_size
        if size > MAX_CONFIG_BYTES:
            raise FileAccessError("配置文件超过 32 MiB 安全上限。")
        text = resolved.read_text(encoding="utf-8-sig")
    except FileAccessError:
        raise
    except (OSError, UnicodeError) as exc:
        raise FileAccessError("无法读取配置文件：%s" % exc) from exc

    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        problem = getattr(exc, "problem", None) or "YAML 语法错误"
        mark = getattr(exc, "problem_mark", None)
        if mark is not None:
            problem = "%s（第 %d 行，第 %d 列）" % (problem, mark.line + 1, mark.column + 1)
        raise ConfigParseError(problem) from exc

    if not isinstance(loaded, dict):
        raise ConfigValidationError("Clash/Mihomo 配置顶层必须是映射。")

    proxies = _require_list(loaded, "proxies")
    groups = _require_list(loaded, "proxy-groups")
    rules = _require_list(loaded, "rules")
    providers = _require_mapping(loaded, "rule-providers")

    node_names: List[str] = []
    warnings: List[str] = []
    for index, proxy in enumerate(proxies, start=1):
        if not isinstance(proxy, dict) or not isinstance(proxy.get("name"), str):
            warnings.append("proxies 第 %d 项缺少有效名称，已忽略。" % index)
            continue
        node_names.append(proxy["name"])

    policy_groups: List[PolicyGroupSummary] = []
    for index, group in enumerate(groups, start=1):
        if not isinstance(group, dict) or not isinstance(group.get("name"), str):
            warnings.append("proxy-groups 第 %d 项缺少有效名称，已忽略。" % index)
            continue
        members = group.get("proxies", [])
        member_count = len(members) if isinstance(members, list) else 0
        if not isinstance(members, list):
            warnings.append("策略组 %s 的 proxies 不是列表。" % group["name"])
        policy_groups.append(
            PolicyGroupSummary(
                name=group["name"],
                type=str(group.get("type", "unknown")),
                member_count=member_count,
            )
        )

    return ConfigSummary(
        path=str(resolved),
        node_names=node_names,
        policy_groups=policy_groups,
        provider_names=[str(name) for name in providers.keys()],
        rule_count=len(rules),
        warnings=warnings,
    )
