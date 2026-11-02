"""Execute public Python and offline CLI guide samples, including refusal mutations."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from raes_cli.main import app
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[3]
GUIDES = ROOT / "docs/public/guides"
SCENARIO = ROOT / "docs/public/_static/examples/first-scenario.sdl.yaml"
BLOCK = re.compile(r"^```(python|console|yaml|yml)\n(.*?)^```$", re.MULTILINE | re.DOTALL)
EXPECTED_PYTHON_OUTPUT = "first-scenario\nfrontend\nFalse\n"


def _python_result(page: str, directory: Path) -> subprocess.CompletedProcess[str]:
    (directory / SCENARIO.name).write_bytes(SCENARIO.read_bytes())
    blocks = [body for language, body in BLOCK.findall(page) if language == "python"]
    assert len(blocks) == 5, "the guide must exercise file/text parsing, admission, rename, and removal"
    script = "\n".join(
        [
            'from pathlib import Path\nsdl_text = Path("first-scenario.sdl.yaml").read_text()',
            *blocks,
            'assert family.semantic_validated\nassert result.succeeded\nassert "index-page" not in result.output.content',
        ]
    )
    return subprocess.run(
        [sys.executable, "-"], input=script, cwd=directory, capture_output=True, text=True, check=False, timeout=120
    )


def _assert_python_result(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stderr
    assert result.stdout == EXPECTED_PYTHON_OUTPUT


def test_python_guide_samples(tmp_path: Path) -> None:
    _assert_python_result(_python_result((GUIDES / "python.md").read_text(encoding="utf-8"), tmp_path))


@pytest.mark.parametrize("mutation", ["old-rename", "missing-removal", "unauthorized-loss"])
def test_python_guide_checks_detect_broken_examples(mutation: str, tmp_path: Path) -> None:
    page = (GUIDES / "python.md").read_text(encoding="utf-8")
    original, replacement = {
        "old-rename": (
            "scenario = parse_sdl(sdl_text)\nresult = rename_sdl_declaration(",
            'scenario = parse_sdl_file(Path("first-scenario.sdl.yaml"))\nresult = rename_sdl_declaration(',
        ),
        "missing-removal": ('target_address="content.index-page"', 'target_address="nodes.obsolete"'),
        "unauthorized-loss": ("ArtifactTransformationLossKind.DECLARATION_REMOVED,", ""),
    }[mutation]
    assert original in page
    with pytest.raises(AssertionError):
        _assert_python_result(_python_result(page.replace(original, replacement, 1), tmp_path))


def test_cli_guide_samples(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "scenario.sdl.yaml").write_bytes(SCENARIO.read_bytes())
    fixture = ROOT / "contracts/fixtures/control-plane/operation-status-v1/valid/succeeded.json"
    (tmp_path / "operation-status.json").write_bytes(fixture.read_bytes())
    monkeypatch.chdir(tmp_path)
    page = (GUIDES / "cli.md").read_text(encoding="utf-8")
    operations = []
    for language, body in BLOCK.findall(page):
        assert language == "console"
        for line in body.replace("\\\n", " ").splitlines():
            words = shlex.split(line)
            if not words:
                continue
            assert words[:5] == ["uv", "run", "--project", "implementations/python", "raes"]
            arguments = words[5:]
            input_text = None
            if "<" in arguments:
                index = arguments.index("<")
                assert len(arguments[index:]) == 2
                input_text = (tmp_path / arguments[index + 1]).read_text(encoding="utf-8")
                arguments = arguments[:index]
            result = CliRunner().invoke(app, arguments, input=input_text)
            assert result.exit_code == 0, result.output
            if "--output" in arguments and arguments[arguments.index("--output") + 1] == "json":
                report = json.loads(result.stdout)
                assert report["status"] == "success"
            operations.append(arguments[1])
    assert operations == ["--help", "parse", "validate", "normalize", "compile", "transform"]


@pytest.mark.parametrize("guide", sorted(GUIDES.glob("*.md")), ids=lambda path: path.stem)
def test_guide_sample_coverage(guide: Path) -> None:
    page = guide.read_text(encoding="utf-8")
    blocks = list(BLOCK.finditer(page))
    for block in blocks:
        if guide.name in {"python.md", "cli.md"}:
            expected_language = "python" if guide.name == "python.md" else "console"
            assert block.group(1) == expected_language, "add execution coverage for the new sample language"
            continue
        marker = re.search(r"<!-- example-skip: ([^\n]+) -->\s*$", page[: block.start()])
        assert marker is not None, f"{guide.name}: add execution coverage or explain the fragment's prerequisites"
        assert marker.group(1).strip()
    if blocks and guide.name not in {"python.md", "cli.md"}:
        pytest.skip("; ".join(re.findall(r"<!-- example-skip: ([^\n]+) -->", page)))
