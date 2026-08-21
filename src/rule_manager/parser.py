"""Strict parsing and normalization for ordinary domain rules."""

import ipaddress
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import SplitResult, urlsplit, urlunsplit

from .errors import FileAccessError
from .models import ParseIssue, ParseResult, Rule


SUPPORTED_TYPES = {
    "DOMAIN": "domain",
    "DOMAIN-SUFFIX": "domain-suffix",
    "DOMAIN-KEYWORD": "domain-keyword",
}
MAX_INPUT_BYTES = 8 * 1024 * 1024
DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
INLINE_COMMENT = re.compile(r"\s+#")


class LineParseError(ValueError):
    """Internal error carrying a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _sanitize_original(value: str) -> str:
    """Hide URL userinfo before input text enters reports or models."""

    stripped = value.strip()
    if not re.match(r"(?i)^https?://", stripped):
        return stripped
    stripped = re.sub(r"(?i)^(https?://)[^/@\s]+@", r"\1[redacted]@", stripped)
    try:
        parsed = urlsplit(stripped)
    except ValueError:
        return stripped
    if parsed.username is None and parsed.password is None:
        return stripped
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = "[%s]" % hostname
    port = ""
    try:
        if parsed.port is not None:
            port = ":%d" % parsed.port
    except ValueError:
        pass
    sanitized = SplitResult(parsed.scheme, "[redacted]@%s%s" % (hostname, port), parsed.path, parsed.query, parsed.fragment)
    return urlunsplit(sanitized)


def _remove_safe_inline_comment(value: str) -> str:
    stripped = value.strip()
    if re.match(r"(?i)^https?://", stripped):
        return stripped
    match = INLINE_COMMENT.search(stripped)
    if match is None:
        return stripped
    return stripped[: match.start()].rstrip()


def _normalize_domain(value: str, allow_suffix_marker: bool = False) -> Tuple[str, Optional[str]]:
    candidate = value.strip()
    if allow_suffix_marker:
        if candidate.startswith("*."):
            candidate = candidate[2:]
        elif candidate.startswith("."):
            candidate = candidate[1:]
    if "*" in candidate:
        raise LineParseError("invalid-wildcard", "只允许域名前缀使用 *. 通配符。")
    candidate = candidate.rstrip(".")
    if not candidate:
        raise LineParseError("empty-domain", "域名不能为空。")
    if any(character.isspace() for character in candidate):
        raise LineParseError("invalid-domain", "域名不能包含空白字符。")
    try:
        ipaddress.ip_address(candidate.strip("[]"))
    except ValueError:
        pass
    else:
        raise LineParseError("ip-not-supported", "当前步进不处理 IP 或 CIDR。")

    unicode_value = candidate if not candidate.isascii() else None
    try:
        ascii_value = candidate.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise LineParseError("invalid-idna", "域名无法转换为 IDNA。") from exc
    if len(ascii_value) > 253:
        raise LineParseError("domain-too-long", "域名总长度超过 253 个字符。")
    labels = ascii_value.split(".")
    if any(not label or len(label) > 63 or DOMAIN_LABEL.fullmatch(label) is None for label in labels):
        raise LineParseError("invalid-domain", "域名标签格式无效。")
    return ascii_value, unicode_value


def _normalize_keyword(value: str) -> str:
    keyword = value.strip().lower()
    if not keyword:
        raise LineParseError("empty-keyword", "域名关键词不能为空。")
    if any(character.isspace() for character in keyword):
        raise LineParseError("invalid-keyword", "域名关键词不能包含空白字符。")
    return keyword


def _parse_url(value: str) -> Tuple[str, Optional[str]]:
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise LineParseError("invalid-url", "URL 格式无效。") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise LineParseError("unsupported-url-scheme", "仅支持 http 和 https URL。")
    if not parsed.hostname:
        raise LineParseError("missing-url-host", "URL 缺少主机名。")
    try:
        parsed.port
    except ValueError as exc:
        raise LineParseError("invalid-url-port", "URL 端口无效。") from exc
    return _normalize_domain(parsed.hostname)


def _parse_explicit(
    line: str,
    line_number: int,
    default_policy: Optional[str],
    override_policy: bool,
) -> Rule:
    columns = [column.strip() for column in line.split(",")]
    rule_name = columns[0].upper()
    if rule_name not in SUPPORTED_TYPES:
        raise LineParseError("unsupported-rule-type", "暂不支持规则类型 %s。" % columns[0])
    if len(columns) < 2 or not columns[1]:
        raise LineParseError("missing-rule-value", "显式规则缺少匹配值。")
    policy = columns[2] if len(columns) >= 3 and columns[2] else default_policy
    if override_policy:
        policy = default_policy
    options = tuple(option.lower() for option in columns[3:] if option)
    internal_type = SUPPORTED_TYPES[rule_name]
    if internal_type == "domain-keyword":
        normalized = _normalize_keyword(columns[1])
        unicode_value = None
    else:
        normalized, unicode_value = _normalize_domain(
            columns[1], allow_suffix_marker=internal_type == "domain-suffix"
        )
    return Rule(
        line_number=line_number,
        type=internal_type,
        value=normalized,
        policy=policy,
        options=options,
        original=_sanitize_original(line),
        unicode_value=unicode_value,
    )


def _parse_ordinary(line: str, line_number: int, default_policy: Optional[str]) -> Rule:
    if re.match(r"(?i)^https?://", line):
        normalized, unicode_value = _parse_url(line)
        rule_type = "domain"
    elif "://" in line:
        raise LineParseError("unsupported-url-scheme", "仅支持 http 和 https URL。")
    elif "/" in line or "?" in line:
        try:
            ipaddress.ip_network(line, strict=False)
        except ValueError:
            pass
        else:
            raise LineParseError("ip-not-supported", "当前步进不处理 IP 或 CIDR。")
        raise LineParseError("ambiguous-path", "含路径的输入必须提供 http:// 或 https://。")
    else:
        rule_type = "domain-suffix" if line.startswith(("*.", ".")) else "domain"
        normalized, unicode_value = _normalize_domain(line, allow_suffix_marker=rule_type == "domain-suffix")
    return Rule(
        line_number=line_number,
        type=rule_type,
        value=normalized,
        policy=default_policy,
        original=_sanitize_original(line),
        unicode_value=unicode_value,
    )


def parse_rules_text(
    text: str,
    default_policy: Optional[str] = None,
    override_policy: bool = False,
) -> ParseResult:
    """Parse input deterministically, skipping exact duplicates only."""

    rules: List[Rule] = []
    errors: List[ParseIssue] = []
    warnings: List[ParseIssue] = []
    seen: Dict[Tuple[str, str, Tuple[str, ...]], Rule] = {}

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if line_number == 1:
            raw_line = raw_line.lstrip("\ufeff")
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        line = _remove_safe_inline_comment(raw_line)
        if not line:
            continue
        report_original = _sanitize_original(line)
        try:
            first_column = line.split(",", 1)[0].strip().upper()
            if "," in line or first_column in SUPPORTED_TYPES:
                rule = _parse_explicit(line, line_number, default_policy, override_policy)
            else:
                rule = _parse_ordinary(line, line_number, default_policy)
        except LineParseError as exc:
            errors.append(ParseIssue(line_number, exc.code, str(exc), report_original))
            continue

        previous = seen.get(rule.dedupe_key)
        if previous is not None and previous.policy == rule.policy:
            warnings.append(
                ParseIssue(
                    line_number,
                    "duplicate",
                    "与第 %d 行规范化后重复，已跳过。" % previous.line_number,
                    rule.original,
                )
            )
            continue
        if previous is not None and previous.policy != rule.policy:
            warnings.append(
                ParseIssue(
                    line_number,
                    "policy-conflict",
                    "与第 %d 行匹配相同但策略不同，暂时保留两条。" % previous.line_number,
                    rule.original,
                )
            )
        else:
            seen[rule.dedupe_key] = rule
        rules.append(rule)
    return ParseResult(rules=rules, errors=errors, warnings=warnings)


def parse_rules_file(
    path_value: str,
    default_policy: Optional[str] = None,
    override_policy: bool = False,
) -> ParseResult:
    """Read a bounded UTF-8 file and parse its ordinary rules."""

    path = Path(path_value).expanduser()
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise FileAccessError("规则输入不是普通文件：%s" % resolved)
        if resolved.stat().st_size > MAX_INPUT_BYTES:
            raise FileAccessError("规则输入超过 8 MiB 安全上限。")
        text = resolved.read_text(encoding="utf-8-sig")
    except FileAccessError:
        raise
    except (OSError, UnicodeError) as exc:
        raise FileAccessError("无法读取规则输入：%s" % exc) from exc
    return parse_rules_text(text, default_policy=default_policy, override_policy=override_policy)
