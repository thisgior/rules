"""Validated, atomic storage for the generic rule project."""

import hashlib
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import yaml

from .errors import ConfigParseError, ConfigValidationError, FileAccessError, UserInputError
from .models import ParseIssue, ParseResult, ProjectResult, ProjectRule, RuleSource


SCHEMA_VERSION = 1
SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SOURCE_KINDS = {"manual", "local-file", "remote-url", "loyalsoldier", "geosite"}
PRIORITIES = {"domain": 100, "domain-suffix": 200, "domain-keyword": 300}
MAX_SOURCE_BYTES = 16 * 1024 * 1024


def _project_paths(project_value: str) -> Tuple[Path, Path]:
    project = Path(project_value).expanduser().resolve()
    sources = project / "sources"
    return project, sources


def init_project(project_value: str) -> ProjectResult:
    """Create an empty rule project without touching proxy configuration."""

    project, sources = _project_paths(project_value)
    try:
        project.mkdir(parents=True, exist_ok=True)
        if not project.is_dir():
            raise FileAccessError("规则项目路径不是目录：%s" % project)
        sources.mkdir(exist_ok=True)
        if not sources.is_dir() or sources.is_symlink():
            raise FileAccessError("sources 必须是规则项目内的普通目录。")
    except FileAccessError:
        raise
    except OSError as exc:
        raise FileAccessError("无法创建规则项目：%s" % exc) from exc
    return ProjectResult()


def _validate_source_id(source_id: str) -> None:
    if SOURCE_ID.fullmatch(source_id) is None:
        raise UserInputError("来源 ID 仅允许 1–64 位小写字母、数字、点、下划线和连字符。")


def _source_path(sources: Path, source_id: str) -> Path:
    _validate_source_id(source_id)
    return sources / (source_id + ".yaml")


def _load_source(path: Path) -> Tuple[RuleSource, List[ProjectRule]]:
    try:
        if path.is_symlink() or not path.is_file():
            raise FileAccessError("来源文件必须是普通文件：%s" % path)
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise FileAccessError("来源文件超过 16 MiB 安全上限：%s" % path)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileAccessError:
        raise
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        position = ""
        if mark is not None:
            position = "（第 %d 行，第 %d 列）" % (mark.line + 1, mark.column + 1)
        raise ConfigParseError("无法解析来源文件 %s%s" % (path, position)) from exc
    except (OSError, UnicodeError) as exc:
        raise FileAccessError("无法读取来源文件 %s：%s" % (path, exc)) from exc

    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ConfigValidationError("来源文件 schema_version 必须为 1：%s" % path)
    raw_source = data.get("source")
    raw_rules = data.get("rules")
    if not isinstance(raw_source, dict) or not isinstance(raw_rules, list):
        raise ConfigValidationError("来源文件必须包含 source 映射和 rules 列表：%s" % path)
    try:
        source = RuleSource(
            id=str(raw_source["id"]),
            kind=str(raw_source["kind"]),
            label=str(raw_source["label"]),
            location=raw_source.get("location"),
        )
        _validate_source_id(source.id)
        if path.stem != source.id or source.kind not in SOURCE_KINDS or not source.label.strip():
            raise ValueError
        rules: List[ProjectRule] = []
        for item in raw_rules:
            if not isinstance(item, dict):
                raise ValueError
            rule = ProjectRule(
                id=str(item["id"]),
                type=str(item["type"]),
                value=str(item["value"]),
                policy=str(item["policy"]),
                options=tuple(str(value) for value in item.get("options", [])),
                source_id=str(item["source_id"]),
                original=str(item.get("original", "")),
                enabled=item["enabled"],
                priority=int(item["priority"]),
                created_at=str(item["created_at"]),
                unicode_value=item.get("unicode_value"),
            )
            if (
                rule.source_id != source.id
                or rule.type not in PRIORITIES
                or not rule.value
                or not rule.policy.strip()
                or type(rule.enabled) is not bool
                or rule.priority != PRIORITIES[rule.type]
            ):
                raise ValueError
            rules.append(rule)
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigValidationError("来源文件字段无效：%s" % path) from exc
    return source, rules


def _load_project(project_value: str) -> Tuple[Path, List[RuleSource], List[ProjectRule]]:
    project, sources = _project_paths(project_value)
    if not project.is_dir() or not sources.is_dir() or sources.is_symlink():
        raise FileAccessError("规则项目不存在；请先运行 init-project：%s" % project)
    all_sources: List[RuleSource] = []
    all_rules: List[ProjectRule] = []
    for path in sorted(sources.glob("*.yaml")):
        source, rules = _load_source(path)
        all_sources.append(source)
        all_rules.extend(rules)
    ids = [rule.id for rule in all_rules]
    if len(ids) != len(set(ids)):
        raise ConfigValidationError("规则项目包含重复规则 ID。")
    return sources, all_sources, all_rules


def _dump_source(source: RuleSource, rules: List[ProjectRule]) -> bytes:
    data = {
        "schema_version": SCHEMA_VERSION,
        "source": source.to_dict(),
        "rules": [rule.to_dict() for rule in rules],
    }
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False).encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    try:
        candidate = yaml.safe_load(payload.decode("utf-8"))
    except (UnicodeError, yaml.YAMLError) as exc:
        raise ConfigValidationError("生成的来源文件无法重新解析。") from exc
    if not isinstance(candidate, dict) or candidate.get("schema_version") != SCHEMA_VERSION:
        raise ConfigValidationError("生成的来源文件结构无效。")
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    descriptor = -1
    temporary = ""
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = ""
        directory_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise FileAccessError("无法原子写入来源文件 %s：%s" % (path, exc)) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _rule_id(source_id: str, rule_type: str, value: str, policy: str, options: Tuple[str, ...]) -> str:
    raw = "\0".join((source_id, rule_type, value, policy, "\0".join(options)))
    return "rule_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def list_project(project_value: str, enabled_only: bool = False) -> ProjectResult:
    """List validated sources and rules in deterministic order."""

    _, sources, rules = _load_project(project_value)
    if enabled_only:
        rules = [rule for rule in rules if rule.enabled]
    return ProjectResult(rules=rules, sources=sources)


def add_rules(
    project_value: str,
    parsed: ParseResult,
    source_id: str,
    source_kind: str,
    source_label: Optional[str] = None,
    location: Optional[str] = None,
    created_at: Optional[str] = None,
) -> ProjectResult:
    """Add valid parsed rules, skipping duplicates and preserving conflicts."""

    if parsed.errors:
        raise UserInputError("输入仍有解析错误，未写入规则项目。")
    _validate_source_id(source_id)
    if source_kind not in SOURCE_KINDS:
        raise UserInputError("不支持的来源类型：%s" % source_kind)
    if location:
        try:
            parsed_location = urlsplit(location)
        except ValueError as exc:
            raise UserInputError("来源位置格式无效。") from exc
        if parsed_location.username is not None or parsed_location.password is not None:
            raise UserInputError("来源位置不能包含用户名或密码。")
    sources_path, sources, all_rules = _load_project(project_value)
    path = _source_path(sources_path, source_id)
    existing_source = next((item for item in sources if item.id == source_id), None)
    label = (source_label or source_id).strip()
    if not label:
        raise UserInputError("来源标签不能为空。")
    source = existing_source or RuleSource(source_id, source_kind, label, location)
    if existing_source and (
        existing_source.kind != source_kind
        or (source_label is not None and existing_source.label != label)
        or (location is not None and existing_source.location != location)
    ):
        raise UserInputError("来源 ID 已存在且元数据不一致。")
    own_rules = [rule for rule in all_rules if rule.source_id == source_id]
    seen: Dict[Tuple[str, str, Tuple[str, ...]], List[ProjectRule]] = {}
    for rule in all_rules:
        seen.setdefault(rule.dedupe_key, []).append(rule)
    warnings: List[ParseIssue] = list(parsed.warnings)
    added: List[ProjectRule] = []
    timestamp = created_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for rule in parsed.rules:
        if not rule.policy or not rule.policy.strip():
            raise UserInputError("第 %d 行没有策略，未写入规则项目。" % rule.line_number)
        matches = seen.get(rule.dedupe_key, [])
        duplicate = next((item for item in matches if item.policy == rule.policy), None)
        if duplicate is not None:
            warnings.append(
                ParseIssue(rule.line_number, "project-duplicate", "与规则 %s 完全重复，已跳过。" % duplicate.id, rule.original)
            )
            continue
        if matches:
            warnings.append(
                ParseIssue(rule.line_number, "project-policy-conflict", "匹配相同但策略不同，已保留新规则且未覆盖原规则。", rule.original)
            )
        stored = ProjectRule(
            id=_rule_id(source_id, rule.type, rule.value, rule.policy, rule.options),
            type=rule.type,
            value=rule.value,
            policy=rule.policy,
            options=rule.options,
            source_id=source_id,
            original=rule.original,
            enabled=True,
            priority=PRIORITIES[rule.type],
            created_at=timestamp,
            unicode_value=rule.unicode_value,
        )
        if any(existing.id == stored.id for existing in all_rules + added):
            raise ConfigValidationError("规则 ID 发生冲突，未写入。")
        added.append(stored)
        seen.setdefault(stored.dedupe_key, []).append(stored)
    if added:
        _atomic_write(path, _dump_source(source, own_rules + added))
    _, final_sources, final_rules = _load_project(project_value)
    return ProjectResult(final_rules, final_sources, warnings, added_count=len(added))


def _replace_rule(project_value: str, rule_id: str, enabled: Optional[bool]) -> ProjectResult:
    sources_path, sources, all_rules = _load_project(project_value)
    matches = [rule for rule in all_rules if rule.id == rule_id]
    if not matches:
        raise UserInputError("未找到规则 ID：%s" % rule_id)
    target = matches[0]
    source = next(item for item in sources if item.id == target.source_id)
    own_rules = [rule for rule in all_rules if rule.source_id == source.id]
    if enabled is None:
        updated = [rule for rule in own_rules if rule.id != rule_id]
    else:
        updated = [
            ProjectRule(**{**rule.to_dict(), "options": rule.options, "enabled": enabled}) if rule.id == rule_id else rule
            for rule in own_rules
        ]
    _atomic_write(_source_path(sources_path, source.id), _dump_source(source, updated))
    _, final_sources, final_rules = _load_project(project_value)
    return ProjectResult(final_rules, final_sources, changed_count=1)


def delete_rule(project_value: str, rule_id: str) -> ProjectResult:
    return _replace_rule(project_value, rule_id, None)


def set_rule_enabled(project_value: str, rule_id: str, enabled: bool) -> ProjectResult:
    return _replace_rule(project_value, rule_id, enabled)
