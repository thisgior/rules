"""Stable application errors and exit codes."""


class RuleManagerError(Exception):
    """Base error that maps to a stable CLI exit code."""

    exit_code = 10


class UserInputError(RuleManagerError):
    """Invalid command argument or user input."""

    exit_code = 1


class ConfigParseError(RuleManagerError):
    """Configuration bytes could not be parsed."""

    exit_code = 2


class ConfigValidationError(RuleManagerError):
    """Parsed configuration has an invalid top-level structure."""

    exit_code = 3


class FileAccessError(RuleManagerError):
    """Configuration cannot be safely read."""

    exit_code = 5
