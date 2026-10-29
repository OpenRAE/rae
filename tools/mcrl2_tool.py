"""Explicit acquisition and offline comparison with the admitted mCRL2 release."""

from __future__ import annotations

import argparse
import platform
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tools.bounded_tool_process import run_bounded
from tools.tool_versions import MCRL2_VERSION
from tools.tooling_policy_gate import load_tooling_artifact_selection

MODES = ("bisim", "weak-bisim", "branching-bisim", "dpbranching-bisim")
FORMULA_MODES = frozenset({"bisim", "branching-bisim"})
MAX_OUTPUT_BYTES = 65536
REPO_ROOT = Path(__file__).resolve().parents[1]


def selection():
    """Resolve the exact release and complete tree before any tool use."""

    if platform.system() != "Linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        raise RuntimeError("unsupported model-check host")
    selected = load_tooling_artifact_selection(
        artifact_id="mcrl2",
        version=MCRL2_VERSION,
        platform_id="linux-x86_64",
        profile_id="model-check-linux-x86_64",
    )
    if (
        len(selected.raw_manifest) != 1
        or len(selected.installed_manifest) != 1
        or selected.installed_manifest[0].path != "usr/bin/ltscompare"
        or not selected.installed_manifest[0].executable
        or selected.installed_tree is None
        or selected.installed_tree.format != "deb"
    ):
        raise RuntimeError("invalid model-check selection")
    return selected


def acquire_mcrl2(repo_root: Path = REPO_ROOT, *, local_input: Path | None = None) -> Path:
    from tools.maintained_client_acquisition import LARGE_OBJECT_TRANSFER_BUDGET, acquire_locked_file
    from tools.verified_tree_installation import ensure_verified_tree_installation

    selected = selection()

    def acquire_raw(destination: Path) -> None:
        acquire_locked_file(
            artifact_id="mcrl2",
            source_url=selected.source_urls[0],
            expected=selected.raw_manifest[0],
            destination=destination,
            local_input=local_input,
            budget=LARGE_OBJECT_TRANSFER_BUDGET,
        )

    return ensure_verified_tree_installation(repo_root, selected, acquire_raw=acquire_raw)


def require_mcrl2(repo_root: Path = REPO_ROOT) -> Path:
    from tools.verified_tree_installation import require_verified_tree_installation

    return require_verified_tree_installation(repo_root, selection())


def parse_decision(payload: bytes) -> bool:
    if payload not in (b"true\n", b"false\n"):
        raise ValueError("invalid checker decision")
    return payload == b"true\n"


def sandbox_command(tool: Path, inputs: Path, output: Path, mode: str, formula: bool) -> list[str]:
    if mode not in MODES or formula and mode not in FORMULA_MODES:
        raise ValueError("unsupported comparison mode")
    command = [
        "/usr/bin/bwrap",
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
        "/usr",
        "--dir",
        "/etc",
    ]
    for name in ("/usr/lib", "/usr/lib64", "/lib", "/lib64", "/etc/ld.so.cache"):
        if Path(name).exists():
            command.extend(("--ro-bind", name, name))
    command.extend(
        (
            "--ro-bind",
            str(tool),
            "/opt/mcrl2",
            "--ro-bind",
            str(inputs),
            "/input",
            "--bind",
            str(output),
            "/output",
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--tmpfs",
            str(Path("/") / "tmp"),
            "--chdir",
            "/output",
            "--setenv",
            "LC_ALL",
            "C",
            "/opt/mcrl2/usr/bin/ltscompare",
            f"--equivalence={mode}",
            "--tau=internal",
            "--in1=aut",
            "--in2=aut",
        )
    )
    if formula:
        command.extend(("--counter-example", "--counter-example-file=/output/witness.mcf"))
    return [*command, "/input/left.aut", "/input/right.aut"]


@dataclass(frozen=True)
class Comparison:
    equivalent: bool
    formula: bytes | None


def compare(repo_root: Path, left: bytes, right: bytes, mode: str, *, formula: bool = False) -> Comparison:
    """Return a decision only after complete successful execution and safe reads.

    Formula bytes remain private candidate data; the corpus witness checker must
    admit them before publication. This function never acquires a missing tool.
    """

    from implementations.formal.participant_crossing.aut import parse_aut
    from implementations.formal.participant_crossing.ingress import read_bytes

    for payload in (left, right):
        parse_aut(payload, max_states=512, max_bytes=65536)
    tool = require_mcrl2(repo_root)
    with tempfile.TemporaryDirectory(prefix="mcrl2-check-") as temporary:
        root = Path(temporary)
        inputs, output = root / "input", root / "output"
        inputs.mkdir(mode=0o700)
        output.mkdir(mode=0o700)
        (inputs / "left.aut").write_bytes(left)
        (inputs / "right.aut").write_bytes(right)
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            run_bounded(sandbox_command(tool, inputs, output, mode, formula), stdout=stdout, stderr=stderr)
            stdout.seek(0)
            equivalent = parse_decision(stdout.read(MAX_OUTPUT_BYTES + 1))
        candidate = None
        if formula and not equivalent:
            candidate = read_bytes(output, "witness.mcf", max_bytes=MAX_OUTPUT_BYTES)
        elif list(output.iterdir()):
            raise ValueError("unexpected checker output")
        if any(path.name != "witness.mcf" for path in output.iterdir()):
            raise ValueError("unexpected checker output")
        return Comparison(equivalent, candidate)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("acquire", "check-installation"))
    parser.add_argument("--local-input", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "acquire":
            acquire_mcrl2(local_input=args.local_input)
        else:
            require_mcrl2()
    except OSError, ValueError, RuntimeError:
        print("mcrl2: tool admission failed")
        return 1
    print("mcrl2: admitted installation verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
