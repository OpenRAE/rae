"""Fresh offline execution boundary for the reviewed finite producer."""

import base64
import binascii
import os
import signal
import subprocess
import sys
import tempfile
from contextlib import suppress
from pathlib import Path

from raes_contracts.errors import EvidenceIntegrityError, OperationalError, RaesError
from raes_contracts.operational_logging import run_application

from tools.bounded_tool_process import run_bounded
from tools.mcrl2_tool import require_mcrl2
from tools.verified_tool_installation import default_installation_root

from . import counterexample_corpus as corpus
from . import export
from . import machine_check as machine
from .ingress import read_bytes, safe_path

WORKER_ROOT = "/reproduction"
MODULE = "implementations.formal.participant_crossing.reproduction_sandbox"
MAX_WIRE_BYTES = 12 * 1024 * 1024
WALL_SECONDS = 2160
EXTRA_SOURCE_PATHS = (
    ".ground-control.yaml",
    "tools/policy/__init__.py",
    "implementations/tooling/action_policy_yaml.py",
    "implementations/python/packages/raes/__init__.py",
    "implementations/python/packages/raes/identifiers.py",
    "implementations/python/packages/raes/_identifiers.py",
    "implementations/formal/participant_crossing/reproduction_sandbox.py",
)


def git_output(root: Path, arguments: list[str]) -> str:
    """Read the declared checkout without ambient Git redirection or diff hooks."""
    argv = [
        "/usr/bin/git",
        "-C",
        str(root),
        "--no-pager",
        "-c",
        "core.fsmonitor=false",
        *arguments,
    ]
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        run_bounded(argv, stdout=stdout, stderr=stderr, wall_seconds=10)
        stdout.seek(0)
        payload = stdout.read(1024 * 1024 + 1)
    if len(payload) > 1024 * 1024:
        raise EvidenceIntegrityError("reproduction source inventory exceeds limit")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        raise EvidenceIntegrityError("invalid reproduction source inventory") from None


def package_source_paths(root: Path) -> tuple[str, ...]:
    """Select committed package sources, excluding untracked import overrides."""
    if git_output(
        root,
        [
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--name-only",
            "HEAD",
            "--",
            "implementations/python/packages",
        ],
    ).strip():
        raise EvidenceIntegrityError("reproduction package source is not committed")
    names = git_output(
        root, ["ls-files", "-z", "--", "implementations/python/packages"]
    ).split("\0")
    return tuple(name for name in names if name.endswith(".py"))


def stage_sources(root: Path, destination: Path) -> None:
    """Copy declared inputs, never workspace caches, bytecode or producer results."""
    destination.mkdir(mode=0o700, parents=True)
    retained, _ = corpus.load_retained(root)
    paths = {
        *machine.evidence.SOURCE_PATHS,
        *EXTRA_SOURCE_PATHS,
        *package_source_paths(root),
        *(
            path.relative_to(root).as_posix()
            for path in (root / "contracts").rglob("*.json")
        ),
        *(export.OUTPUT_PATH + "/" + name for name in export.build_bundle(root)),
        *(corpus.output_path(retained) + "/" + name for name in retained),
        *(corpus.MAPPING_ROOT + "/" + name for name in ("manifest.json", "cases.json")),
    }
    total = 0
    for name in sorted(paths):
        payload = read_bytes(root, name)
        total += len(payload)
        if total > 64 * 1024 * 1024:
            raise EvidenceIntegrityError("reproduction source inventory exceeds limit")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    (destination / machine.OUTPUT_ROOT).mkdir(parents=True, exist_ok=True)
    for project in ("implementations/python", "implementations/tooling/python"):
        (destination / project / ".venv").mkdir(parents=True, exist_ok=True)
    installations = destination / ".cache/raes-sdl/tooling/installations"
    installations.mkdir(mode=0o700, parents=True)
    (installations / "mcrl2").mkdir()
    for directory in (
        destination / ".cache",
        destination / ".cache/raes-sdl",
        destination / ".cache/raes-sdl/tooling",
    ):
        directory.chmod(0o700)


def command(root: Path, output: Path, tool: Path) -> list[str]:
    """Use a fixed source mount and installed closures; never expose the host root."""
    argv = [
        "/usr/bin/bwrap",
        "--unshare-net",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--die-with-parent",
        "--new-session",
        "--clearenv",
    ]
    runtime_paths = {
        "/usr/bin",
        "/usr/lib",
        "/usr/lib64",
        "/lib",
        "/lib64",
        "/etc/ld.so.cache",
        str(Path(sys.base_prefix).resolve()),
    }
    for project in ("implementations/python", "implementations/tooling/python"):
        executable = root / project / ".venv/bin/python"
        if executable.is_symlink():
            target = executable.readlink()
            if target.is_absolute():
                prefix = target.parent.parent
                if (
                    target.parent.name != "bin"
                    or prefix == Path("/")
                    or prefix.resolve() != Path(sys.base_prefix).resolve()
                ):
                    raise OperationalError("reproduction Python closure mismatch")
                runtime_paths.add(str(prefix))
    for name in sorted(runtime_paths):
        if Path(name).exists():
            argv.extend(("--ro-bind", name, name))
    argv.extend(("--ro-bind", str(output.parent / "sources"), WORKER_ROOT))
    for project in ("implementations/python", "implementations/tooling/python"):
        argv.extend(
            (
                "--ro-bind",
                str(root / project / ".venv"),
                WORKER_ROOT + "/" + project + "/.venv",
            )
        )
    installations = WORKER_ROOT + "/.cache/raes-sdl/tooling/installations"
    argv.extend(
        (
            "--perms",
            "0700",
            "--dir",
            installations,
            "--ro-bind",
            str(tool),
            installations + "/mcrl2",
            "--bind",
            str(output),
            "/output",
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--tmpfs",
            "/tmp",
            "--chdir",
            WORKER_ROOT,
            "--setenv",
            "PATH",
            "/usr/bin",
            "--setenv",
            "LC_ALL",
            "C",
            "--setenv",
            "TZ",
            "UTC",
            "--setenv",
            "HOME",
            "/tmp",
            "--setenv",
            "UV_PYTHON_DOWNLOADS",
            "never",
            "--setenv",
            "PYTHONDONTWRITEBYTECODE",
            "1",
            "--setenv",
            "PYTHONPATH",
            WORKER_ROOT + "/implementations/python/packages:" + WORKER_ROOT,
            WORKER_ROOT + "/implementations/python/.venv/bin/python",
            "-s",
            "-B",
            "-m",
            MODULE,
        )
    )
    return argv


def decode_bundle(payload: bytes) -> dict[str, bytes]:
    try:
        document = corpus.decoded(payload)
        if set(document) not in (
            machine.INVENTORY,
            machine.INVENTORY | {"baseline.mcf"},
        ):
            raise EvidenceIntegrityError("invalid reproduction worker inventory")
        bundle = {
            name: base64.b64decode(value, validate=True)
            for name, value in document.items()
        }
        machine.validate_inventory(bundle)
        return bundle
    except (ValueError, TypeError, binascii.Error, RaesError):
        raise EvidenceIntegrityError("invalid reproduction worker output") from None


def run_worker(argv: list[str], stdout, stderr) -> None:
    """Bound the entire orchestration; each native comparison keeps its own limits."""
    limits = [
        "/usr/bin/prlimit",
        "--core=0",
        "--cpu=2100",
        "--as=2147483648",
        "--nofile=64",
        f"--fsize={MAX_WIRE_BYTES}",
        "--",
        *argv,
    ]
    child = None
    try:
        child = subprocess.Popen(
            limits,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            env={"PATH": "/usr/bin", "LC_ALL": "C"},
            start_new_session=True,
            close_fds=True,
        )
        if child.wait(timeout=WALL_SECONDS) != 0:
            raise OperationalError("reproduction worker failed")
    except (OSError, subprocess.TimeoutExpired):
        raise OperationalError("reproduction worker failed") from None
    finally:
        if child is not None:
            with suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
            child.wait()


def replay(root: Path) -> dict[str, bytes]:
    require_mcrl2(root)
    cache = safe_path(root, ".cache")
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="crossing-reproduction-", dir=cache
    ) as temporary:
        workspace = Path(temporary)
        stage_sources(root, workspace / "sources")
        output = workspace / "output"
        output.mkdir(mode=0o700)
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            run_worker(
                command(root, output, default_installation_root(root) / "mcrl2"),
                stdout,
                stderr,
            )
            if list(output.iterdir()):
                raise EvidenceIntegrityError("unexpected reproduction worker output")
            stdout.seek(0)
            payload = stdout.read(MAX_WIRE_BYTES + 1)
            if len(payload) > MAX_WIRE_BYTES:
                raise EvidenceIntegrityError("reproduction worker output exceeds limit")
            return decode_bundle(payload)


def main() -> int:
    try:
        bundle = machine.build_bundle(Path(__file__).resolve().parents[3])
        payload = corpus.encoded(
            {
                name: base64.b64encode(value).decode("ascii")
                for name, value in bundle.items()
            }
        )
        sys.stdout.buffer.write(payload)
    except OSError, RaesError:
        print("crossing reproduction: worker refused")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))
