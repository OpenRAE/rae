"""Installed-distribution acceptance tests for the bundled contract corpus (#537).

These build the real ``raes`` wheel, install it into a throwaway virtualenv,
and exercise conformance + SDL semantic validation **with no repository
``contracts/`` tree on the path** — so a source-checkout fallback cannot mask a
missing wheel payload (the failure mode the issue exists to prevent). A passing
unit suite or a Git tag is not evidence that the wheel actually contains the
corpus; building and installing it is.

Marked ``integration`` because they build/install artifacts and read the real
repo on disk; they run in ``nox -s integration`` and the ``verify`` graph, not
the default fast unit sweep.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # implementations/python
REPO_ROOT = PROJECT_ROOT.parents[1]
REPO_CONTRACTS = REPO_ROOT / "contracts"

_CORPUS_PREFIX = "raes_contracts/_corpus/"
_FAMILY_PROBES = {
    "profiles": "raes_contracts/_corpus/profiles/backend/provisioning-only.json",
    "scientific-completeness": "raes_contracts/_corpus/profiles/scientific-completeness/scientific-scenario-completeness-rev1.json",
    "fixtures": "raes_contracts/_corpus/fixtures/",
    "concept-authority": "raes_contracts/_corpus/concept-authority/behavioral-relations-v1.json",
    "schemas": "raes_contracts/_corpus/schemas/",
    "provenance": "raes_contracts/_corpus/provenance/sdl-lineage-ledger-v1.json",
}

_NOTICE_PATH = "raes_contracts/_corpus/provenance/THIRD_PARTY_NOTICES.md"

_UV = shutil.which("uv")
requires_uv = pytest.mark.skipif(_UV is None, reason="uv toolchain not available")


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, timeout=600, **kwargs)


def _sanitized_runtime_env(home: Path) -> dict[str, str]:
    """A minimal env for invoking the *installed* distribution.

    Deliberately omits ``PYTHONPATH`` so the repo's ``packages/`` source tree
    cannot leak onto ``sys.path`` and mask a broken wheel payload.
    """

    return {"PATH": os.environ.get("PATH", ""), "HOME": str(home)}


def _current_python_closure_profile() -> str:
    abi = f"cp{sys.version_info.major}{sys.version_info.minor}"
    machine = platform.machine().lower()
    if sys.platform.startswith("linux") and machine in {"amd64", "x86_64"}:
        return f"public-linux-x86_64-{abi}-all-extras"
    if sys.platform.startswith("linux") and machine in {"aarch64", "arm64"} and abi == "cp314":
        return "public-linux-arm64-cp314-all-extras"
    if sys.platform == "darwin" and machine in {"aarch64", "arm64"} and abi == "cp314":
        return "public-macos-arm64-cp314-all-extras"
    pytest.skip("installed corpus smoke has no reviewed closure for this interpreter/platform tuple")


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out_dir = tmp_path_factory.mktemp("wheel")
    result = _run(
        [
            _UV,
            "build",
            "--wheel",
            "--build-constraints",
            str(REPO_ROOT / "implementations" / "tooling" / "python" / "build-constraints.txt"),
            "--require-hashes",
            "--out-dir",
            str(out_dir),
        ],
        cwd=PROJECT_ROOT,
    )
    assert result.returncode == 0, f"wheel build failed:\n{result.stdout}\n{result.stderr}"
    wheels = list(out_dir.glob("raes-*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, found {wheels}"
    return wheels[0]


@pytest.fixture(scope="module")
def installed_python(built_wheel: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    venv_dir = tmp_path_factory.mktemp("venv")
    py = (
        venv_dir
        / ("Scripts" if sys.platform == "win32" else "bin")
        / ("python.exe" if sys.platform == "win32" else "python")
    )
    install = _run(
        [
            sys.executable,
            "-m",
            "tools.python_closure",
            "smoke",
            "--profile",
            _current_python_closure_profile(),
            "--candidate",
            str(built_wheel),
            "--environment",
            str(venv_dir),
        ],
        cwd=REPO_ROOT,
    )
    assert install.returncode == 0, f"wheel install failed:\n{install.stdout}\n{install.stderr}"
    # The throwaway venv must not contain the source-tree corpus.
    assert not (venv_dir / "contracts").exists()
    return py


@requires_uv
@pytest.mark.parametrize("family", sorted(_FAMILY_PROBES))
def test_built_wheel_bundles_each_corpus_family(built_wheel: Path, family: str):
    """The built wheel must physically contain every normative corpus family."""

    with zipfile.ZipFile(built_wheel) as zf:
        names = zf.namelist()
    corpus_names = [n for n in names if n.startswith(_CORPUS_PREFIX)]
    assert corpus_names, "wheel ships no raes_contracts/_corpus payload at all"
    probe = _FAMILY_PROBES[family]
    assert any(n == probe or n.startswith(probe) for n in names), (
        f"corpus family {family!r} ({probe}) missing from wheel"
    )


@requires_uv
def test_built_wheel_includes_third_party_notice(built_wheel: Path):
    with zipfile.ZipFile(built_wheel) as zf:
        notice = zf.read(_NOTICE_PATH).decode("utf-8")
    assert "Copyright (c) 2022 CR14" in notice
    assert "fe83e8281fc4b954967fbaa5a0d099007ddcb06c" in notice


@requires_uv
def test_installed_wheel_hard_cuts_sdl_import_namespace(installed_python: Path, tmp_path: Path):
    """The wheel exposes the canonical RAES owners."""

    script = "import raes\nimport raes_contracts\nassert raes.parse_sdl\nassert raes_contracts.__doc__\n"
    result = _run(
        [str(installed_python), "-c", script],
        cwd=tmp_path,
        env=_sanitized_runtime_env(tmp_path),
    )
    assert result.returncode == 0, f"canonical namespace check failed:\n{result.stdout}\n{result.stderr}"


@requires_uv
def test_installed_wheel_version_entrypoint_stays_lazy(installed_python: Path, tmp_path: Path):
    """The generated console script must retain the exact-version import boundary."""

    environment = _sanitized_runtime_env(tmp_path)
    raes = installed_python.parent / ("raes.exe" if sys.platform == "win32" else "raes")
    expected = _run(
        [
            str(installed_python),
            "-c",
            "from importlib.metadata import version; print(f\"raes {version('raes')}\")",
        ],
        cwd=tmp_path,
        env=environment,
    )
    result = _run([str(raes), "--version"], cwd=tmp_path, env=environment)

    assert expected.returncode == 0, expected.stderr
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected.stdout

    inspection = """
import sys
from importlib.metadata import entry_points

entrypoint = next(item for item in entry_points(group="console_scripts") if item.name == "raes")
assert entrypoint.value == "raes_cli.entrypoint:main", entrypoint.value
sys.argv = ["raes", "-V"]
entrypoint.load()()
assert "raes_cli.main" not in sys.modules
assert not any(name == "raes_contracts" or name.startswith("raes_contracts.") for name in sys.modules)
"""
    inspected = _run([str(installed_python), "-c", inspection], cwd=tmp_path, env=environment)
    assert inspected.returncode == 0, f"installed entry-point check failed:\n{inspected.stdout}\n{inspected.stderr}"


@requires_uv
def test_corpus_discoverable_via_importlib_resources_from_installed_wheel(installed_python: Path, tmp_path: Path):
    """Acceptance: the corpus is discoverable via ``importlib.resources`` from
    the installed distribution, resolved out of site-packages — NOT the repo
    ``contracts/`` tree."""

    script = (
        "import json\n"
        "from raes_contracts.corpus import corpus_root, corpus_family_root\n"
        "root = corpus_root()\n"
        "print(json.dumps({\n"
        "  'root': str(root),\n"
        "  'backend_profile': (corpus_family_root('profiles')/'backend'/'provisioning-only.json').exists(),\n"
        "  'scientific_completeness': (corpus_family_root('profiles')/'scientific-completeness'/'scientific-scenario-completeness-rev1.json').exists(),\n"
        "  'controlled_vocab': (corpus_family_root('concept-authority')/'controlled-vocabularies-v1.json').exists(),\n"
        "  'activitystreams_source': (corpus_family_root('concept-authority')/'w3c-activitystreams-activity-types-source-v1.json').exists(),\n"
        "  'fipa_source': (corpus_family_root('concept-authority')/'fipa-communicative-acts-source-v1.json').exists(),\n"
        "  'fixtures_dir': corpus_family_root('fixtures').is_dir(),\n"
        "  'schemas_dir': corpus_family_root('schemas').is_dir(),\n"
        "}))\n"
    )
    result = _run(
        [str(installed_python), "-c", script],
        cwd=tmp_path,
        env=_sanitized_runtime_env(tmp_path),
    )
    assert result.returncode == 0, f"discovery failed:\n{result.stdout}\n{result.stderr}"
    payload = json.loads(result.stdout)
    resolved = Path(payload["root"]).resolve()
    assert "site-packages" in resolved.parts, f"corpus resolved outside site-packages: {resolved}"
    assert resolved != REPO_CONTRACTS.resolve(), "installed dist fell back to the repo contracts/ tree"
    assert payload["backend_profile"] is True
    assert payload["scientific_completeness"] is True
    assert payload["controlled_vocab"] is True
    assert payload["activitystreams_source"] is True
    assert payload["fipa_source"] is True
    assert payload["fixtures_dir"] is True
    assert payload["schemas_dir"] is True


@requires_uv
def test_conformance_backend_passes_from_installed_wheel(installed_python: Path, tmp_path: Path):
    """Acceptance: ``raes conformance backend --profile provisioning-only`` exits
    0 from a fresh wheel install with no source tree present."""

    raes = installed_python.parent / ("raes.exe" if sys.platform == "win32" else "raes")
    result = _run(
        [str(raes), "conformance", "backend", "--profile", "provisioning-only"],
        cwd=tmp_path,
        env=_sanitized_runtime_env(tmp_path),
    )
    assert result.returncode == 0, f"conformance CLI failed:\n{result.stdout}\n{result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["profile"] == "provisioning-only"
    assert payload["passed"] is True, payload
    assert payload["cases"], "conformance ran zero cases — corpus fixtures not bundled"


@requires_uv
def test_sdl_semantic_validation_loads_corpus_from_installed_wheel(installed_python: Path, tmp_path: Path):
    """Acceptance: SDL semantic validation reads the concept-authority corpus
    from the installed wheel with no source checkout."""

    script = (
        "from raes_contracts.controlled_vocabularies import load_controlled_vocabulary_catalog\n"
        "catalog = load_controlled_vocabulary_catalog()\n"
        "assert catalog.vocabularies, 'no controlled vocabularies loaded'\n"
        "print(len(catalog.vocabularies))\n"
    )
    result = _run(
        [str(installed_python), "-c", script],
        cwd=tmp_path,
        env=_sanitized_runtime_env(tmp_path),
    )
    assert result.returncode == 0, f"semantic-validation load failed:\n{result.stdout}\n{result.stderr}"
    assert int(result.stdout.strip()) > 0
