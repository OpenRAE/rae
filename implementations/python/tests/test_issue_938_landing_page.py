"""The landing-page quickstart runs as written (issue 938).

``README.md``, the hosted front page, and the hosted quickstart each show the
same validation command followed by the output it prints. These tests run that
command the way a reader does, against the checked-in quickstart scenario, and
compare the result with what each page promises. The diagram that both landing
pages embed must carry an accessible name and description.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
from defusedxml import ElementTree

REPO_ROOT = Path(__file__).resolve().parents[3]
QUICKSTART_SCENARIO = REPO_ROOT / "docs" / "public" / "_static" / "examples" / "first-scenario.sdl.yaml"
ECOSYSTEM_DIAGRAM = REPO_ROOT / "docs" / "public" / "_static" / "raes-ecosystem.svg"
SVG = "{http://www.w3.org/2000/svg}"

# A console block that feeds a script to `python -` through a heredoc, then the
# first text block after it, which shows what the command prints.
_COMMAND_AND_OUTPUT = re.compile(
    r"```console\npython - <<'PY'\n(?P<script>.*?)\nPY\n```.*?```text\n(?P<output>.*?)\n```",
    re.DOTALL,
)


@pytest.mark.parametrize("page", ["README.md", "docs/public/index.md", "docs/public/quickstart.md"])
def test_quickstart_prints_the_output_each_page_shows(page: str, tmp_path: Path) -> None:
    match = _COMMAND_AND_OUTPUT.search((REPO_ROOT / page).read_text(encoding="utf-8"))
    assert match is not None, f"{page} has no quickstart command followed by its output"
    (tmp_path / QUICKSTART_SCENARIO.name).write_bytes(QUICKSTART_SCENARIO.read_bytes())

    completed = subprocess.run(
        [sys.executable, "-"],
        input=match.group("script"),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.rstrip("\n") == match.group("output")


def test_ecosystem_diagram_has_an_accessible_name_and_description() -> None:
    root = ElementTree.parse(ECOSYSTEM_DIAGRAM).getroot()
    labels = {child.get("id"): child for child in root if child.tag in {f"{SVG}title", f"{SVG}desc"}}
    referenced = [labels.get(label_id) for label_id in root.get("aria-labelledby", "").split()]

    assert root.get("role") == "img"
    assert None not in referenced
    assert sorted(element.tag for element in referenced) == [f"{SVG}desc", f"{SVG}title"]
    assert all(element.text and element.text.strip() for element in referenced)
