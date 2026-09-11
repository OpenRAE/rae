"""Fixed bubblewrap command construction for offline Isabelle replay."""

from __future__ import annotations

from pathlib import Path

ISABELLE_SANDBOX_HOME = Path("/opt/isabelle")
ISABELLE_SANDBOX_SESSION_ROOT = Path("/workspace/session")
ISABELLE_SANDBOX_STATE_ROOT = Path("/state")
ISABELLE_SANDBOX_TEMP = Path("/") / "tmp"
ISABELLE_SYSTEM_RUNTIME_PATHS = (
    Path("/usr/bin"),
    Path("/usr/lib"),
    Path("/usr/lib64"),
    Path("/usr/share/locale"),
    Path("/usr/share/fontconfig"),
    Path("/usr/share/fonts"),
    Path("/usr/share/zoneinfo"),
    Path("/lib"),
    Path("/lib64"),
    Path("/etc/fonts"),
    Path("/etc/ld.so.cache"),
    Path("/var/cache/fontconfig"),
)


def proof_sandbox_command(
    *,
    bwrap: Path,
    home: Path,
    session_root: Path,
    state_root: Path,
    locale: str = "C.UTF-8",
) -> list[str]:
    """Build the fixed proof sandbox without exposing the host root or home."""

    command = [
        str(bwrap),
        "--unshare-net",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--dir",
        "/opt",
        "--dir",
        "/workspace",
        "--dir",
        "/usr",
        "--dir",
        "/usr/share",
        "--dir",
        "/etc",
        "--dir",
        "/var",
        "--dir",
        "/var/cache",
    ]
    for runtime_path in ISABELLE_SYSTEM_RUNTIME_PATHS:
        if runtime_path.exists():
            command.extend(("--ro-bind", str(runtime_path), str(runtime_path)))
    command.extend(
        (
            "--ro-bind",
            str(home),
            str(ISABELLE_SANDBOX_HOME),
            "--ro-bind",
            str(session_root),
            str(ISABELLE_SANDBOX_SESSION_ROOT),
            "--bind",
            str(state_root),
            str(ISABELLE_SANDBOX_STATE_ROOT),
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--tmpfs",
            str(ISABELLE_SANDBOX_TEMP),
            "--chdir",
            "/workspace",
            "--setenv",
            "PATH",
            "/usr/bin",
            "--setenv",
            "HOME",
            "/state/user",
            "--setenv",
            "USER_HOME",
            "/state/user",
            "--setenv",
            "ISABELLE_HOME_USER",
            "/state/isabelle-user",
            "--setenv",
            "TMPDIR",
            str(ISABELLE_SANDBOX_TEMP),
            "--setenv",
            "LANG",
            locale,
            "--setenv",
            "LC_ALL",
            locale,
            "--setenv",
            "TZ",
            "UTC",
            str(ISABELLE_SANDBOX_HOME / "bin" / "isabelle"),
            "build",
            "-o",
            "threads=2",
            "-o",
            "timeout=300",
            "-D",
            str(ISABELLE_SANDBOX_SESSION_ROOT),
        )
    )
    return command
