"""
Unified URL opening utility that handles root-elevated contexts.

When running as root (e.g., via pkexec/sudo), the browser is spawned
as the original user via xdg-open to avoid sandbox/zygote errors like:
  "Running as root without --no-sandbox is not supported."

Follows the same pattern as user_paths.py: environment variable tunneling
with native Python stdlib, minimal external tools.
"""

import os
import pwd
import subprocess
import webbrowser
from lufus.lufus_logging import get_logger

log = get_logger(__name__)

ENV_OPEN_AS_USER = "LUFUS_OPEN_AS_USER"


def _resolve_user() -> tuple[str | None, int | None]:
    """Detect the original user under privilege elevation.

    Checks in order:
    1. ``LUFUS_OPEN_AS_USER`` env var (manual override)
    2. ``PKEXEC_UID`` env var (set by pkexec)
    3. ``SUDO_UID`` env var (set by sudo)
    4. ``/proc/self/loginuid`` (Linux audit — survives all escalation methods)

    Returns:
        (username, uid) of the original user, or (None, None) if undetectable.
    """
    manual_user = os.environ.get(ENV_OPEN_AS_USER)
    if manual_user:
        try:
            info = pwd.getpwnam(manual_user)
            return info.pw_name, info.pw_uid
        except KeyError:
            log.warning("LUFUS_OPEN_AS_USER=%r is not a valid user", manual_user)

    for var in ("PKEXEC_UID", "SUDO_UID"):
        uid_str = os.environ.get(var)
        if uid_str:
            try:
                uid = int(uid_str)
                info = pwd.getpwuid(uid)
                return info.pw_name, uid
            except (ValueError, KeyError):
                continue

    try:
        with open("/proc/self/loginuid") as f:
            raw = f.read().strip()
        uid = int(raw)
        if uid > 0:
            info = pwd.getpwuid(uid)
            return info.pw_name, uid
    except (FileNotFoundError, ValueError, KeyError, OSError):
        pass

    return None, None


def open_url(url: str) -> bool:
    """Open a URL in the system default browser.

    When running as root, the browser is launched as the original user
    to avoid chromium sandbox errors. Falls back to ``webbrowser.open()``
    in all other cases.

    Args:
        url: The URL to open.

    Returns:
        True if the URL was opened successfully, False otherwise.
    """
    if os.geteuid() != 0:
        return webbrowser.open(url)

    username, uid = _resolve_user()
    if not username:
        log.warning("Running as root but could not resolve original user")
        return webbrowser.open(url)

    info = pwd.getpwuid(uid)
    env = {
        "DISPLAY": os.environ.get("DISPLAY", ":0"),
        "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY", ""),
        "XDG_RUNTIME_DIR": f"/run/user/{uid}",
        "HOME": info.pw_dir,
        "PATH": "/usr/bin:/bin",
    }

    try:
        subprocess.Popen(
            ["runuser", "-u", username, "--", "xdg-open", url],
            env=env,
        )
        log.info("Opened URL as user %s: %s", username, url)
        return True
    except FileNotFoundError:
        log.error("runuser not found; falling back to webbrowser")
        return webbrowser.open(url)
