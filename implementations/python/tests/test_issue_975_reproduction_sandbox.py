"""Exercise the entire Python worker boundary, including inherited host state."""

import shutil
import subprocess
from pathlib import Path

import pytest
from raes_contracts.errors import EvidenceIntegrityError

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="native isolation runs in the required model-check job")
def test_worker_cannot_use_network_environment_or_host_result_cache(tmp_path, monkeypatch):
    from implementations.formal.participant_crossing import reproduction_sandbox as sandbox

    output = tmp_path / "output"
    output.mkdir()
    tool = tmp_path / "tool"
    tool.mkdir()
    host_file = tmp_path / "host-sentinel"
    host_file.write_text("private-sentinel")
    monkeypatch.setenv("REPRODUCTION_PRIVATE_SENTINEL", "private-sentinel")
    sandbox.stage_sources(ROOT, tmp_path / "sources")
    assert not list((tmp_path / "sources").rglob("*.pyc"))
    command = sandbox.command(ROOT, output, tool)
    assert command[-2:] == ["-m", "implementations.formal.participant_crossing.reproduction_sandbox"]
    probe = f"""
import os, pathlib, socket
assert os.environ.get('REPRODUCTION_PRIVATE_SENTINEL') is None
assert not pathlib.Path({str(host_file)!r}).exists()
assert not pathlib.Path('/reproduction/.git').exists()
assert not list(pathlib.Path('/reproduction/specs/formal/participant-semantics/machine-check').iterdir())
assert not pathlib.Path('/reproduction/.cache/unreviewed-result').exists()
sock = socket.socket()
sock.settimeout(1)
try:
    sock.connect(('192.0.2.1', 443))
except OSError:
    pass
else:
    raise AssertionError('network escaped')
try:
    pathlib.Path('/reproduction/noxfile.py').write_text('changed')
except OSError:
    pass
else:
    raise AssertionError('source was writable')
print('isolated')
"""
    completed = subprocess.run([*command[:-2], "-c", probe], capture_output=True, timeout=20, check=False)
    assert completed.returncode == 0, completed.stderr.decode()
    assert completed.stdout == b"isolated\n"
    assert not list(output.iterdir())


@pytest.mark.parametrize(
    "payload", [b"{}", b'{"../escape":"eA=="}', b'{"manifest.json":1}', b'{"manifest.json":"%%%"}']
)
def test_worker_output_has_a_closed_bounded_byte_inventory(payload):
    from implementations.formal.participant_crossing import reproduction_sandbox as sandbox

    with pytest.raises(EvidenceIntegrityError):
        sandbox.decode_bundle(payload)


def test_timeout_reaps_the_complete_worker_group(monkeypatch, tmp_path):
    from implementations.formal.participant_crossing import reproduction_sandbox as sandbox

    class Child:
        pid = 98765
        calls = 0

        def wait(self, timeout=None):
            self.calls += 1
            if timeout is not None:
                raise subprocess.TimeoutExpired("fixed-worker", timeout)
            return -9

    child = Child()
    groups = []
    monkeypatch.setattr(sandbox.subprocess, "Popen", lambda *args, **kwargs: child)
    monkeypatch.setattr(sandbox.os, "killpg", lambda pid, sig: groups.append(pid))
    with (
        (tmp_path / "stdout").open("wb") as stdout,
        (tmp_path / "stderr").open("wb") as stderr,
        pytest.raises(sandbox.OperationalError, match="worker failed"),
    ):
        sandbox.run_worker(["fixed-worker"], stdout, stderr)
    assert groups == [child.pid]
    assert child.calls == 2


def test_package_selection_ignores_ambient_git_redirection(monkeypatch):
    from implementations.formal.participant_crossing import reproduction_sandbox as sandbox

    expected = sandbox.package_source_paths(ROOT)
    monkeypatch.setenv("GIT_DIR", "/unavailable-synthetic-git-directory")
    monkeypatch.setenv("GIT_WORK_TREE", "/unavailable-synthetic-worktree")
    assert sandbox.package_source_paths(ROOT) == expected
