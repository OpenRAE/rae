"""Closed decisions and sandboxed input/output for the admitted checker."""

import importlib
import sys
from pathlib import Path

import pytest
from raes_contracts.errors import EvidenceIntegrityError, InvalidInputError, OperationalError


@pytest.mark.parametrize(
    "module_name,operation,action",
    [
        ("tools.mcrl2_tool", "require_mcrl2", "check-installation"),
        ("implementations.formal.participant_crossing.counterexample_corpus", "load_retained", "check"),
    ],
)
def test_cli_handles_domain_failure_but_preserves_programming_defects(
    monkeypatch: pytest.MonkeyPatch, module_name: str, operation: str, action: str
) -> None:
    module = importlib.import_module(module_name)
    monkeypatch.setattr(sys, "argv", [module_name, action])

    def unavailable(*_args):
        raise OperationalError("dependency unavailable")

    monkeypatch.setattr(module, operation, unavailable)
    assert module.main() == 1

    def defective(*_args):
        raise ValueError("internal defect")

    monkeypatch.setattr(module, operation, defective)
    with pytest.raises(ValueError, match="internal defect"):
        module.main()


@pytest.mark.parametrize("payload,expected", [(b"true\n", True), (b"false\n", False)])
def test_boolean_protocol(payload: bytes, expected: bool) -> None:
    from tools.mcrl2_tool import parse_decision

    assert parse_decision(payload) is expected


@pytest.mark.parametrize("payload", [b"", b"error: false", b"true\nfalse\n", b"FALSE\n", b"false\n/private/path"])
def test_invalid_output_is_no_decision(payload: bytes) -> None:
    from tools.mcrl2_tool import parse_decision

    with pytest.raises(EvidenceIntegrityError, match="invalid checker decision"):
        parse_decision(payload)


def test_command_hides_only_internal_and_has_no_host_root(tmp_path: Path) -> None:
    from tools.mcrl2_tool import sandbox_command

    command = sandbox_command(tmp_path / "tool", tmp_path / "input", tmp_path / "output", "dpbranching-bisim", False)
    assert "--unshare-net" in command
    assert "--clearenv" in command
    assert "--tau=internal" in command
    assert "--equivalence=dpbranching-bisim" in command
    assert "--counter-example" not in command
    for index, option in enumerate(command):
        if option in {"--ro-bind", "--bind"}:
            assert command[index + 1] not in {"/", "/home", str(Path.home())}
    with pytest.raises(ValueError):
        sandbox_command(tmp_path, tmp_path, tmp_path, "trace", False)
    with pytest.raises(ValueError):
        sandbox_command(tmp_path, tmp_path, tmp_path, "dpbranching-bisim", True)


def test_host_qualification_probes_decoder_and_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import bootstrap_profile

    monkeypatch.setattr(
        bootstrap_profile,
        "observe_executable",
        lambda capability_id, *args, **kwargs: {"capability_id": capability_id, "outcome": "passed"},
    )
    results = bootstrap_profile._native_client_results(
        {"platform_id": "linux-x86_64", "required_capability_ids": ["dpkg-deb", "prlimit"]}
    )
    assert {result["capability_id"] for result in results} == {"dpkg-deb", "prlimit"}


@pytest.mark.parametrize("behavior", ["failure", "garbage", "unsafe-witness", "false"])
def test_compare_admits_only_successful_closed_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, behavior: str
) -> None:
    from tools import mcrl2_tool

    monkeypatch.setattr(mcrl2_tool, "require_mcrl2", lambda *args: tmp_path)

    def execute(command, *, stdout, stderr):
        if behavior == "failure":
            raise OperationalError("bounded-tool-failed")
        stdout.write(b"false\n" if behavior != "garbage" else b"fatal: /private/path")
        stdout.flush()
        if behavior == "unsafe-witness":
            output = Path(command[command.index("--bind") + 1])
            (output / "witness.mcf").symlink_to(tmp_path / "outside")

    monkeypatch.setattr(mcrl2_tool, "run_bounded", execute)
    model = b"des (0, 0, 1)\n"
    if behavior == "false":
        assert mcrl2_tool.compare(tmp_path, model, model, "dpbranching-bisim").equivalent is False
    else:
        with pytest.raises((OperationalError, EvidenceIntegrityError, InvalidInputError)):
            mcrl2_tool.compare(tmp_path, model, model, "branching-bisim", formula=behavior == "unsafe-witness")
