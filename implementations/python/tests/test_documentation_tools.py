"""Exercise dependency admission and local Vale package installation."""

from __future__ import annotations

import subprocess
from contextlib import nullcontext
from pathlib import Path

import pytest
from tools import documentation_tools
from tools import verified_tool_installation as installation
from tools.maintained_client_acquisition import ArtifactAcquisitionError
from tools.verified_tool_installation import ToolInstallationError

pytestmark = pytest.mark.integration


def test_documentation_dependencies_import_from_tooling_environment() -> None:
    root = Path(__file__).resolve().parents[3]
    python = root / "implementations/tooling/python/.venv/bin/python"
    result = subprocess.run(
        [str(python), "-I", "-c", f"import sys; sys.path.insert(0, {str(root)!r}); import tools.documentation_tools"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture(autouse=True)
def installer_without_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    # Real-lock concurrency is covered by the existing installation qualification harness.
    monkeypatch.setattr(installation, "_portable_lock", lambda _path: nullcontext())


@pytest.mark.parametrize("ensure", ["ensure_doc_tools", "ensure_ste"])
def test_bad_archive_is_rejected_before_installation(tmp_path: Path, ensure: str) -> None:
    archive = tmp_path / "bad.tar.gz"
    archive.write_bytes(b"changed archive")
    with pytest.raises(ArtifactAcquisitionError):
        getattr(documentation_tools, ensure)(tmp_path, local_input=archive)
    assert not list(tmp_path.rglob("ste"))
    assert not list(tmp_path.rglob("ste-lint.sh"))


@pytest.mark.parametrize("ensure, relative", [("ensure_doc_tools", ".ste.yml"), ("ensure_ste", None)])
def test_changed_installed_content_is_rejected(tmp_path: Path, ensure: str, relative: str | None) -> None:
    install = getattr(documentation_tools, ensure)
    installed = install(tmp_path)
    target = installed / relative if relative else installed
    target.chmod(0o600)
    target.write_text("changed installed bytes\n")
    with pytest.raises(ToolInstallationError):
        install(tmp_path)


def test_vale_sync_uses_verified_local_package(tmp_path: Path) -> None:
    from tools.vale_tool import ensure_vale

    package = documentation_tools.ensure_doc_tools(tmp_path)
    binary = ensure_vale(tmp_path)
    documentation_tools.sync_doc_tools_styles(tmp_path, binary, package)
    installed = tmp_path / "styles" / "DocTools"
    assert (installed / "PlainWords.yml").read_bytes() == (package / "vale/DocTools/PlainWords.yml").read_bytes()
    (installed / "PlainWords.yml").write_text("changed installed style\n")
    documentation_tools.sync_doc_tools_styles(tmp_path, binary, package)
    assert (installed / "PlainWords.yml").read_bytes() == (package / "vale/DocTools/PlainWords.yml").read_bytes()
    assert (package / "skills/documentation/SKILL.md").is_file()
    assert (package / "skills/documentation/LICENSE").is_file()
    assert (package / "LICENSE").is_file()
    assert (package / "THIRD_PARTY_NOTICES.md").is_file()


def test_shared_wrapper_refuses_no_path_before_installing_binary(tmp_path: Path) -> None:
    package = documentation_tools.ensure_doc_tools(tmp_path)
    result = subprocess.run(["bash", str(package / "tools/ste-lint.sh")], capture_output=True, text=True)
    assert result.returncode == 2
    assert "Usage:" in result.stderr
    assert not (package / ".tools").exists()
