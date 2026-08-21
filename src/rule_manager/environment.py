"""Debian, Python, root and sudo detection."""

import os
import platform
import shutil
from pathlib import Path
from typing import Dict, Optional

from .models import EnvironmentSummary


SUPPORTED_DEBIAN_MAJORS = {"11", "12", "13"}


def parse_os_release(text: str) -> Dict[str, str]:
    """Parse the simple KEY=VALUE format used by /etc/os-release."""

    result: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        result[key] = value
    return result


def detect_environment(os_release_path: Optional[Path] = None) -> EnvironmentSummary:
    """Return runtime facts without changing the host."""

    path = os_release_path or Path("/etc/os-release")
    values: Dict[str, str] = {}
    try:
        values = parse_os_release(path.read_text(encoding="utf-8"))
    except OSError:
        pass

    os_id = values.get("ID", "unknown")
    os_version = values.get("VERSION_ID", "unknown")
    major = os_version.split(".", 1)[0]
    return EnvironmentSummary(
        os_id=os_id,
        os_version=os_version,
        debian_supported=os_id == "debian" and major in SUPPORTED_DEBIAN_MAJORS,
        python_version=platform.python_version(),
        running_as_root=hasattr(os, "geteuid") and os.geteuid() == 0,
        sudo_available=shutil.which("sudo") is not None,
    )
