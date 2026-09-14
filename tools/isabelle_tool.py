from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import isabelle_sandbox  # noqa: E402
from tools.tool_versions import ISABELLE_VERSION  # noqa: E402

if TYPE_CHECKING:
    from tools.tooling_policy_gate import LockedArtifactSelection

ISABELLE_SYSTEM_RUNTIME_PATHS = isabelle_sandbox.ISABELLE_SYSTEM_RUNTIME_PATHS
_proof_sandbox_command = isabelle_sandbox.proof_sandbox_command

ISABELLE_ARCHIVE_NAME = f"Isabelle{ISABELLE_VERSION}_linux.tar.gz"
ISABELLE_DISTRIBUTION_ROOT = f"Isabelle{ISABELLE_VERSION}"
ISABELLE_SESSION = "Participant_Opacity"
ISABELLE_SESSION_RELATIVE_PATH = Path("specs/formal/participant-semantics/isabelle")
ISABELLE_LOCALE = "C.UTF-8"
ISABELLE_BUILD_TIMEOUT_SECONDS = 600
ISABELLE_OUTPUT_LIMIT_BYTES = 64 * 1024
ISABELLE_FILE_LIMIT_BYTES = 4 * 1024 * 1024 * 1024
ISABELLE_PROCESS_ADDRESS_SPACE_LIMIT_MIB = 32768
ISABELLE_JAVA_MAX_HEAP_MIB = 2048
ISABELLE_ML_MAX_HEAP_MIB = 2048
ISABELLE_BUBBLEWRAP_PATH = Path("/usr/bin/bwrap")
ISABELLE_REQUIRED_FONTCONFIG_PATHS = (
    Path("/etc/fonts"),
    Path("/usr/share/fonts"),
)
ISABELLE_FONTCONFIG_LIST = Path("/usr/bin/fc-list")
ISABELLE_FONTCONFIG_QUERY_TIMEOUT_SECONDS = 10
ISABELLE_LOCALE_LIST = Path("/usr/bin/locale")
ISABELLE_LOCALE_QUERY_TIMEOUT_SECONDS = 10
ISABELLE_LOCALE_OUTPUT_LIMIT_BYTES = 64 * 1024
PROOF_PREREQUISITE_IDS = (
    "bubblewrap",
    "fontconfig",
    "fonts",
    "locale-c-utf-8",
    "isabelle-installation",
)


class IsabelleToolError(RuntimeError):
    """A bounded operational failure from the pinned proof tool."""


def isabelle_cache_root(repo_root: Path = REPO_ROOT) -> Path:
    return repo_root / ".cache" / "raes-sdl" / "tooling"


def isabelle_archive_path(repo_root: Path = REPO_ROOT) -> Path:
    """Return the legacy shared archive path, a migration carrier only."""

    return isabelle_cache_root(repo_root) / "archives" / ISABELLE_ARCHIVE_NAME


def _legacy_home(repo_root: Path) -> Path:
    return isabelle_cache_root(repo_root) / "isabelle" / ISABELLE_DISTRIBUTION_ROOT


def _legacy_marker(repo_root: Path) -> Path:
    return _legacy_home(repo_root).parent / f"{ISABELLE_DISTRIBUTION_ROOT}.archive.sha256"


def _load_selection(*, require_installed_tree: bool = True) -> LockedArtifactSelection:
    """Load the exact reviewed Isabelle selection before any local or network state."""

    from tools.tooling_policy_gate import load_tooling_artifact_selection

    selection = load_tooling_artifact_selection(
        artifact_id="isabelle",
        version=ISABELLE_VERSION,
        platform_id="linux-x86_64",
        profile_id="proof-linux-x86_64",
    )
    installed = selection.installed_manifest
    if (
        len(selection.raw_manifest) != 1
        or len(installed) != 1
        or not installed[0].executable
        or installed[0].path != f"{ISABELLE_DISTRIBUTION_ROOT}/bin/isabelle"
        or (require_installed_tree and selection.installed_tree is None)
        or len(selection.locator_refs) != len(selection.source_urls)
    ):
        raise IsabelleToolError(
            "Isabelle lock selection must contain one raw archive, its executable, and its installed tree"
        )
    return selection


def _require_supported_platform() -> None:
    if platform.system() != "Linux" or platform.machine().lower() not in {
        "x86_64",
        "amd64",
    }:
        raise IsabelleToolError("the pinned Isabelle proof tool supports Linux x86_64 only")


def _selected_source_url(selection: LockedArtifactSelection, locator_ref: str | None) -> str:
    """Return the reviewed locator the operator selected; there is no failover loop."""

    selected = selection.locator_refs[0] if locator_ref is None else locator_ref
    if selected not in selection.locator_refs:
        raise IsabelleToolError("the selected Isabelle locator is not approved by the reviewed lock")
    return selection.source_urls[selection.locator_refs.index(selected)]


def acquire_isabelle(
    repo_root: Path = REPO_ROOT,
    *,
    local_input: Path | None = None,
    locator_ref: str | None = None,
    installation_root: Path | None = None,
) -> Path:
    """Admit the pinned distribution through the maintained client or a local input."""

    from tools import verified_tree_installation as tree_installation
    from tools.maintained_client_acquisition import (
        LARGE_OBJECT_TRANSFER_BUDGET,
        acquire_locked_file,
    )

    selection = _load_selection()
    _require_supported_platform()
    source_url = _selected_source_url(selection, locator_ref)
    raw = selection.raw_manifest[0]

    def acquire_raw(destination: Path) -> None:
        acquire_locked_file(
            artifact_id="Isabelle",
            source_url=source_url,
            expected=raw,
            destination=destination,
            local_input=local_input,
            budget=LARGE_OBJECT_TRANSFER_BUDGET,
        )

    legacy = None
    if installation_root is None:
        legacy = tree_installation.LegacyTreeInputs(
            raw_carrier=isabelle_archive_path(repo_root),
            derived_paths=(_legacy_home(repo_root), _legacy_marker(repo_root)),
        )
    try:
        tree = tree_installation.ensure_verified_tree_installation(
            repo_root,
            selection,
            acquire_raw=acquire_raw,
            legacy=legacy,
            installation_root=installation_root,
        )
    except IsabelleToolError:
        raise
    except RuntimeError as exc:
        raise IsabelleToolError(str(exc)) from None
    return tree / ISABELLE_DISTRIBUTION_ROOT


def require_isabelle(repo_root: Path = REPO_ROOT, *, installation_root: Path | None = None) -> Path:
    """Resolve and completely reverify an acquired distribution without network access."""

    from tools import verified_tree_installation as tree_installation

    selection = _load_selection()
    _require_supported_platform()
    try:
        tree = tree_installation.require_verified_tree_installation(
            repo_root,
            selection,
            installation_root=installation_root,
        )
    except RuntimeError as exc:
        if str(exc) == "tool-installation: installation-missing":
            raise IsabelleToolError("pinned Isabelle is not acquired; run the acquire command first") from None
        raise IsabelleToolError(f"pinned Isabelle installation is invalid ({exc})") from None
    return tree / ISABELLE_DISTRIBUTION_ROOT


def describe_isabelle_tree(local_input: Path) -> dict[str, object]:
    """Return the reviewable installed-tree identity of a lock-verified archive."""

    from tools import verified_tree_installation as tree_installation

    selection = _load_selection(require_installed_tree=False)
    try:
        return tree_installation.describe_archive_tree(local_input, selection.raw_manifest[0])
    except RuntimeError as exc:
        raise IsabelleToolError(str(exc)) from None


def _proof_process_limits() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(
        resource.RLIMIT_CPU,
        (ISABELLE_BUILD_TIMEOUT_SECONDS, ISABELLE_BUILD_TIMEOUT_SECONDS),
    )
    resource.setrlimit(resource.RLIMIT_FSIZE, (ISABELLE_FILE_LIMIT_BYTES, ISABELLE_FILE_LIMIT_BYTES))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    address_space_bytes = ISABELLE_PROCESS_ADDRESS_SPACE_LIMIT_MIB * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (address_space_bytes, address_space_bytes))


def _read_bounded_output(path: Path) -> str:
    with path.open("rb") as stream:
        payload = stream.read(ISABELLE_OUTPUT_LIMIT_BYTES + 1)
    if len(payload) > ISABELLE_OUTPUT_LIMIT_BYTES:
        raise IsabelleToolError("Isabelle build output exceeded the verification bound")
    return payload.decode("utf-8", errors="replace")


def expected_isabelle_result() -> dict[str, object]:
    result: dict[str, object] = {
        "prover": "Isabelle/HOL",
        "prover_version": f"Isabelle{ISABELLE_VERSION}",
        "session": ISABELLE_SESSION,
        "result": "kernel-checked",
        "network": "blocked-by-bubblewrap-network-namespace",
        "filesystem": "allowlisted-runtime-session-and-private-state-only",
        "locale": ISABELLE_LOCALE,
        "platform_boundary": "linux-x86_64",
    }
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    result["result_digest"] = f"sha256:{hashlib.sha256(encoded).hexdigest()}"
    return result


def _fontconfig_has_fonts(font_list: Path = ISABELLE_FONTCONFIG_LIST) -> bool:
    """Return whether the fixed host fontconfig tool finds an installed font."""

    if not font_list.is_file() or not os.access(font_list, os.X_OK):
        return False
    try:
        completed = subprocess.run(
            [str(font_list), "--format=%{file}\\n"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=ISABELLE_FONTCONFIG_QUERY_TIMEOUT_SECONDS,
            env={"LANG": ISABELLE_LOCALE, "LC_ALL": ISABELLE_LOCALE},
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and bool(completed.stdout.strip())


def _require_fontconfig_runtime(
    paths: tuple[Path, ...] = ISABELLE_REQUIRED_FONTCONFIG_PATHS,
    *,
    font_query: Callable[[], bool] = _fontconfig_has_fonts,
) -> None:
    """Fail before sandbox entry when the pinned prover's font runtime is absent."""

    if any(not path.is_dir() for path in paths) or not font_query():
        raise IsabelleToolError("fontconfig runtime is required for offline proof replay")


def _locale_is_available(locale_list: Path = ISABELLE_LOCALE_LIST) -> bool:
    """Return whether the fixed host locale tool reports the pinned C.UTF-8 locale."""

    if not locale_list.is_file() or not os.access(locale_list, os.X_OK):
        return False
    try:
        completed = subprocess.run(
            [str(locale_list), "-a"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=ISABELLE_LOCALE_QUERY_TIMEOUT_SECONDS,
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if completed.returncode != 0 or len(completed.stdout) > ISABELLE_LOCALE_OUTPUT_LIMIT_BYTES:
        return False
    available = {line.strip().lower() for line in completed.stdout.decode("utf-8", errors="replace").splitlines()}
    return bool(available & {"c.utf8", "c.utf-8"})


def _require_locale_runtime(locale_query: Callable[[], bool] | None = None) -> None:
    """Fail before sandbox entry when the pinned proof locale is absent."""

    if not (locale_query or _locale_is_available)():
        raise IsabelleToolError("C.UTF-8 locale is required for offline proof replay")


def proof_host_preflight(
    repo_root: Path = REPO_ROOT,
    *,
    bwrap: Path = ISABELLE_BUBBLEWRAP_PATH,
    font_query: Callable[[], bool] = _fontconfig_has_fonts,
    locale_query: Callable[[], bool] = _locale_is_available,
) -> dict[str, object]:
    """List every missing logical proof prerequisite without network or execution.

    The installation is resolved only through the complete no-network
    reverification; no imported Isabelle content is executed.
    """

    fontconfig_present = all(path.is_dir() for path in ISABELLE_REQUIRED_FONTCONFIG_PATHS) and (
        ISABELLE_FONTCONFIG_LIST.is_file() and os.access(ISABELLE_FONTCONFIG_LIST, os.X_OK)
    )
    observed = {
        "bubblewrap": _is_executable_file(bwrap),
        "fontconfig": fontconfig_present,
        "fonts": fontconfig_present and font_query(),
        "locale-c-utf-8": locale_query(),
    }
    try:
        _require_supported_platform()
        require_isabelle(repo_root)
    except IsabelleToolError:
        observed["isabelle-installation"] = False
    else:
        observed["isabelle-installation"] = True
    missing = [prerequisite for prerequisite in PROOF_PREREQUISITE_IDS if not observed[prerequisite]]
    return {
        "outcome": "failed" if missing else "passed",
        "missing": missing,
        "platform_boundary": "linux-x86_64",
    }


def _bubblewrap_setup_failed(output: str) -> bool:
    """Return whether bubblewrap failed before the fixed prover could start."""

    return output.lstrip().startswith("bwrap:")


def _is_executable_file(path: Path) -> bool:
    """Return whether a fixed host capability is a regular file the user can execute."""

    return path.is_file() and os.access(path, os.X_OK)


def _require_bubblewrap(bwrap: Path = ISABELLE_BUBBLEWRAP_PATH) -> Path:
    """Fail before any proof work when the offline isolation boundary is unavailable."""

    if not _is_executable_file(bwrap):
        raise IsabelleToolError("bubblewrap is required to enforce offline proof replay")
    return bwrap


def run_isabelle_build(repo_root: Path = REPO_ROOT, *, bwrap: Path = ISABELLE_BUBBLEWRAP_PATH) -> dict[str, object]:
    """Kernel-check the fixed session in a network-isolated, bounded process."""

    # The platform boundary and host isolation capabilities are diagnosed before
    # the distribution is resolved, so an unsupported host fails explicitly.
    _require_supported_platform()
    bwrap = _require_bubblewrap(bwrap)
    _require_fontconfig_runtime()
    _require_locale_runtime()
    home = require_isabelle(repo_root)
    session_root = (repo_root / ISABELLE_SESSION_RELATIVE_PATH).resolve()
    if not session_root.is_dir() or repo_root.resolve() not in session_root.parents:
        raise IsabelleToolError("the fixed Isabelle session root is unavailable")

    with tempfile.TemporaryDirectory(prefix="isabelle-proof-") as temporary:
        state_root = Path(temporary).resolve()
        output_path = state_root / "build-output.log"
        user_home = state_root / "user"
        isabelle_user = state_root / "isabelle-user"
        user_home.mkdir()
        isabelle_user.mkdir()
        (isabelle_user / "etc").mkdir()
        (isabelle_user / "etc" / "settings").write_text(
            f'ISABELLE_TOOL_JAVA_OPTIONS="-Djava.awt.headless=true -Xms256m -Xmx{ISABELLE_JAVA_MAX_HEAP_MIB}m -Xss8m"\n'
            f'ML_OPTIONS="--minheap 256 --maxheap {ISABELLE_ML_MAX_HEAP_MIB}"\n',
            encoding="ascii",
        )
        command = _proof_sandbox_command(
            bwrap=bwrap,
            home=home,
            session_root=session_root,
            state_root=state_root,
            locale=ISABELLE_LOCALE,
        )
        try:
            with output_path.open("wb") as output:
                completed = subprocess.run(  # noqa: S603 - fixed checksum-verified tool and argv
                    command,
                    cwd=repo_root,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    check=False,
                    timeout=ISABELLE_BUILD_TIMEOUT_SECONDS,
                    env={},
                    preexec_fn=_proof_process_limits,
                )
        except subprocess.TimeoutExpired as exc:
            raise IsabelleToolError("Isabelle proof replay exceeded its wall-time bound") from exc
        output = _read_bounded_output(output_path)
        if completed.returncode != 0:
            if _bubblewrap_setup_failed(output):
                raise IsabelleToolError("bubblewrap network isolation is unavailable for offline proof replay")
            failure_tail = output.strip()[-4096:]
            detail = f":\n{failure_tail}" if failure_tail else ""
            raise IsabelleToolError(f"Isabelle kernel rejected the fixed proof session{detail}")
        if "Unfinished session(s)" in output or f"Finished {ISABELLE_SESSION}" not in output:
            raise IsabelleToolError("Isabelle build did not report a finished proof session")

    return expected_isabelle_result()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Acquire or replay the pinned participant-opacity proof tool.")
    commands = parser.add_subparsers(dest="command", required=True)
    acquire = commands.add_parser("acquire", help="admit the pinned distribution into a verified private tree")
    acquire.add_argument(
        "--local-input",
        type=Path,
        help="explicit pre-seeded archive admitted by exact identity",
    )
    acquire.add_argument("--locator-ref", help="approved same-byte locator selected for this invocation")
    describe = commands.add_parser("describe-tree", help="print the reviewable installed-tree identity")
    describe.add_argument("--local-input", type=Path, required=True)
    commands.add_parser(
        "preflight",
        help="list missing proof prerequisites without network or execution",
    )
    commands.add_parser("verify", help="kernel-check the fixed session offline")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if args.command == "acquire":
            acquire_isabelle(local_input=args.local_input, locator_ref=args.locator_ref)
            print(f"acquired Isabelle{ISABELLE_VERSION}")
        elif args.command == "describe-tree":
            print(json.dumps(describe_isabelle_tree(args.local_input), sort_keys=True))
        elif args.command == "preflight":
            result = proof_host_preflight()
            print(json.dumps(result, sort_keys=True))
            return 0 if result["outcome"] == "passed" else 1
        else:
            print(json.dumps(run_isabelle_build(), ensure_ascii=False, sort_keys=True))
    except RuntimeError as exc:
        print(f"isabelle-tool: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
