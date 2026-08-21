"""Command-line interface for inspection, parsing, and rule projects."""

import argparse
import json
import sys
from typing import Optional, Sequence

from .environment import detect_environment
from .errors import RuleManagerError, UserInputError
from .inspector import inspect_config
from .models import ConfigSummary, EnvironmentSummary, ParseResult, ProjectResult
from .parser import parse_rules_file, parse_rules_text
from .version import __version__
from .workspace import add_rules, delete_rule, init_project, list_project, set_rule_enabled


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rule-manager", description="Debian 通用代理规则管理器")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect-config", help="只读检查 Clash/Mihomo 配置")
    inspect_parser.add_argument("path", help="本地 YAML 配置路径")
    inspect_parser.add_argument("--format", choices=("text", "json"), default="text")

    environment_parser = subparsers.add_parser("environment", help="检查 Debian、Python、root 与 sudo")
    environment_parser.add_argument("--format", choices=("text", "json"), default="text")

    parse_parser = subparsers.add_parser("parse-rules", help="只读解析普通域名和 URL 规则")
    parse_parser.add_argument("input", help="UTF-8 输入文件；使用 - 从标准输入读取")
    parse_parser.add_argument("--policy", required=True, help="普通输入的默认策略")
    parse_parser.add_argument("--override-policy", action="store_true", help="覆盖显式规则已有策略")
    parse_parser.add_argument("--format", choices=("text", "json"), default="text")

    init_parser = subparsers.add_parser("init-project", help="创建通用规则项目")
    init_parser.add_argument("project", help="规则项目目录")
    init_parser.add_argument("--format", choices=("text", "json"), default="text")

    add_parser = subparsers.add_parser("add-rules", help="解析并写入通用规则项目")
    add_parser.add_argument("project", help="规则项目目录")
    add_parser.add_argument("input", help="UTF-8 输入文件；使用 - 从标准输入读取")
    add_parser.add_argument("--policy", required=True, help="普通输入的默认策略")
    add_parser.add_argument("--override-policy", action="store_true", help="覆盖显式规则已有策略")
    add_parser.add_argument("--source-id", required=True, help="稳定的来源 ID")
    add_parser.add_argument(
        "--source-kind",
        choices=("manual", "local-file", "remote-url", "loyalsoldier", "geosite"),
        default="manual",
    )
    add_parser.add_argument("--source-label", help="可读来源名称；默认使用来源 ID")
    add_parser.add_argument("--location", help="可选来源位置；不要包含认证信息")
    add_parser.add_argument("--format", choices=("text", "json"), default="text")

    list_parser = subparsers.add_parser("list-rules", help="列出通用规则项目")
    list_parser.add_argument("project", help="规则项目目录")
    list_parser.add_argument("--enabled-only", action="store_true", help="只列出已启用规则")
    list_parser.add_argument("--format", choices=("text", "json"), default="text")

    for name, help_text in (
        ("delete-rule", "按 ID 删除规则"),
        ("enable-rule", "按 ID 启用规则"),
        ("disable-rule", "按 ID 禁用规则"),
    ):
        change_parser = subparsers.add_parser(name, help=help_text)
        change_parser.add_argument("project", help="规则项目目录")
        change_parser.add_argument("rule_id", help="list-rules 输出的规则 ID")
        change_parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _print_config_text(summary: ConfigSummary) -> None:
    print("配置文件：%s" % summary.path)
    print("只读检查：是")
    print("节点（%d）：%s" % (len(summary.node_names), "、".join(summary.node_names) or "无"))
    print("策略组（%d）：" % len(summary.policy_groups))
    for group in summary.policy_groups:
        print("  - %s [%s]，成员 %d 个" % (group.name, group.type, group.member_count))
    print("Rule Provider（%d）：%s" % (len(summary.provider_names), "、".join(summary.provider_names) or "无"))
    print("规则数量：%d" % summary.rule_count)
    if summary.warnings:
        print("警告：")
        for warning in summary.warnings:
            print("  - %s" % warning)
    print("未修改配置，未重载任何服务。")


def _print_environment_text(summary: EnvironmentSummary) -> None:
    print("系统：%s %s" % (summary.os_id, summary.os_version))
    print("Debian 11–13 支持：%s" % ("是" if summary.debian_supported else "否"))
    print("Python：%s" % summary.python_version)
    print("当前为 root：%s" % ("是" if summary.running_as_root else "否"))
    print("sudo 可用：%s" % ("是" if summary.sudo_available else "否"))


def _print_parse_text(result: ParseResult) -> None:
    print("有效规则：%d" % len(result.rules))
    for rule in result.rules:
        policy = rule.policy or "未指定"
        options = ("," + ",".join(rule.options)) if rule.options else ""
        print("  第 %d 行：%s,%s,%s%s" % (rule.line_number, rule.type.upper(), rule.value, policy, options))
    if result.warnings:
        print("警告：%d" % len(result.warnings))
        for issue in result.warnings:
            print("  第 %d 行 [%s] %s" % (issue.line_number, issue.code, issue.message))
    if result.errors:
        print("错误：%d" % len(result.errors))
        for issue in result.errors:
            print("  第 %d 行 [%s] %s" % (issue.line_number, issue.code, issue.message))
    print("只完成解析，未写入任何规则或代理配置。")


def _print_project_text(result: ProjectResult, action: str) -> None:
    print("操作：%s" % action)
    print("来源：%d；规则：%d；已启用：%d" % (
        len(result.sources),
        len(result.rules),
        sum(1 for rule in result.rules if rule.enabled),
    ))
    if result.added_count:
        print("新增规则：%d" % result.added_count)
    if result.changed_count:
        print("变更规则：%d" % result.changed_count)
    for rule in result.rules:
        state = "启用" if rule.enabled else "禁用"
        options = ("," + ",".join(rule.options)) if rule.options else ""
        print("  %s [%s] %s,%s,%s%s（来源：%s）" % (
            rule.id, state, rule.type.upper(), rule.value, rule.policy, options, rule.source_id
        ))
    if result.warnings:
        print("警告：%d" % len(result.warnings))
        for issue in result.warnings:
            print("  第 %d 行 [%s] %s" % (issue.line_number, issue.code, issue.message))
    print("未修改代理配置，未重载任何服务。")


def _print_result(result: ProjectResult, output_format: str, action: str) -> None:
    if output_format == "json":
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_project_text(result, action)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect-config":
            result = inspect_config(args.path)
            if args.format == "json":
                print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            else:
                _print_config_text(result)
            return 0
        if args.command == "environment":
            environment = detect_environment()
            if args.format == "json":
                print(json.dumps(environment.to_dict(), ensure_ascii=False, indent=2))
            else:
                _print_environment_text(environment)
            return 0
        if args.command == "parse-rules":
            if not args.policy.strip():
                raise UserInputError("策略名称不能为空。")
            if args.input == "-":
                result = parse_rules_text(
                    sys.stdin.read(),
                    default_policy=args.policy,
                    override_policy=args.override_policy,
                )
            else:
                result = parse_rules_file(
                    args.input,
                    default_policy=args.policy,
                    override_policy=args.override_policy,
                )
            if args.format == "json":
                print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            else:
                _print_parse_text(result)
            return 2 if result.errors else 0
        if args.command == "init-project":
            result = init_project(args.project)
            _print_result(result, args.format, "创建规则项目")
            return 0
        if args.command == "add-rules":
            if not args.policy.strip():
                raise UserInputError("策略名称不能为空。")
            if args.input == "-":
                parsed = parse_rules_text(
                    sys.stdin.read(), default_policy=args.policy, override_policy=args.override_policy
                )
            else:
                parsed = parse_rules_file(
                    args.input, default_policy=args.policy, override_policy=args.override_policy
                )
            if parsed.errors:
                if args.format == "json":
                    print(json.dumps(parsed.to_dict(), ensure_ascii=False, indent=2))
                else:
                    _print_parse_text(parsed)
                return 2
            result = add_rules(
                args.project,
                parsed,
                source_id=args.source_id,
                source_kind=args.source_kind,
                source_label=args.source_label,
                location=args.location,
            )
            _print_result(result, args.format, "新增规则")
            return 0
        if args.command == "list-rules":
            result = list_project(args.project, enabled_only=args.enabled_only)
            _print_result(result, args.format, "列出规则")
            return 0
        if args.command == "delete-rule":
            result = delete_rule(args.project, args.rule_id)
            _print_result(result, args.format, "删除规则")
            return 0
        if args.command in {"enable-rule", "disable-rule"}:
            result = set_rule_enabled(args.project, args.rule_id, args.command == "enable-rule")
            _print_result(result, args.format, "启用规则" if args.command == "enable-rule" else "禁用规则")
            return 0
        parser.error("未知子命令")
    except RuleManagerError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return exc.exit_code
    return 10


if __name__ == "__main__":
    raise SystemExit(main())
