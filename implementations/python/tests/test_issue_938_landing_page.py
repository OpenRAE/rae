"""The landing pages route readers and say the same thing (issues 938, 1932).

``docs/public/quickstart.md`` owns the first exercise. This test runs its
validation command the way a reader does, against the checked-in quickstart
scenario, and compares the result with what the page promises.

``README.md`` and the hosted front page are routing pages. The README is also
the PyPI description, so it links hosted URLs where the front page links
relative paths. Apart from that link form, each page's title, the README
badges, and the front page's toctree, the two pages share their text and links.
Both embed the ecosystem diagram with alt text, and the diagram itself carries
an accessible name and description. ``docs/index.md`` and ``docs/README.md``
route repository readers to the same first exercise and research explanation.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

import pytest
from defusedxml import ElementTree

REPO_ROOT = Path(__file__).resolve().parents[3]
QUICKSTART_SCENARIO = REPO_ROOT / "docs" / "public" / "_static" / "examples" / "first-scenario.sdl.yaml"
ECOSYSTEM_DIAGRAM = REPO_ROOT / "docs" / "public" / "_static" / "raes-ecosystem.svg"
LANDING_PAGES = ("README.md", "docs/public/index.md")
HOSTED_DOCS = "https://openrae.github.io/rae/"
SVG = "{http://www.w3.org/2000/svg}"
READER_PURPOSES = (
    "Tutorials (learn)",
    "How-to guides (do a task)",
    "Reference (look up facts)",
    "Explanation (understand)",
)
FIRST_ROUTE_PAGES = ("quickstart", "research", "citation")
STABLE_HEADINGS = (
    "What RAES provides",
    "Validate your first scenario",
    "Run a scenario on a backend",
    "Package and share scenarios",
    "Choose your route",
    "Know the limits",
    "Cite RAES",
)

# A console block that feeds a script to `python -` through a heredoc, then the
# first text block after it, which shows what the command prints.
_COMMAND_AND_OUTPUT = re.compile(
    r"```console\npython - <<'PY'\n(?P<script>.*?)\nPY\n```.*?```text\n(?P<output>.*?)\n```",
    re.DOTALL,
)
# The parts of a landing page that are not shared: the title (the single H1
# line, which can follow a lead line), the README badges, and the front page's
# toctree.
_PAGE_SPECIFIC = re.compile(
    r"^# [^\n]*$"
    r"|^\[!\[[^\n]*$"
    r"|^```\{toctree\}.*?^```$",
    re.DOTALL | re.MULTILINE,
)
_LINK_TARGET = re.compile(r"\]\(([^)\s]+)\)")
_DIAGRAM_ALT_TEXT = re.compile(r"!\[([^\]]*)\]\([^)\s]*raes-ecosystem\.svg\)")


def _shared_text(page: str) -> tuple[str, list[str]]:
    """Return a landing page's shared prose with link targets masked, and the targets."""
    text = _PAGE_SPECIFIC.sub("", (REPO_ROOT / page).read_text(encoding="utf-8"))
    prose = " ".join(_LINK_TARGET.sub("](<target>)", text).split())
    return prose, _LINK_TARGET.findall(text)


def _hosted_url(target: str) -> str:
    """Return the URL that the README uses for a front-page link target."""
    if target.startswith("https://"):
        return target
    path = PurePosixPath(target)
    if path.suffix not in {".md", ".rst"}:
        return HOSTED_DOCS + target
    if path.stem == "index":
        return f"{HOSTED_DOCS}{path.parent}/"
    return f"{HOSTED_DOCS}{path.with_suffix('.html')}"


def test_quickstart_prints_the_output_the_page_shows(tmp_path: Path) -> None:
    page = "docs/public/quickstart.md"
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


def test_readme_and_front_page_share_their_text_and_links() -> None:
    for page in LANDING_PAGES:
        titles = re.findall(r"^# ", (REPO_ROOT / page).read_text(encoding="utf-8"), re.MULTILINE)
        assert len(titles) == 1, f"{page} must have exactly one H1 title line"
    readme_prose, readme_targets = _shared_text("README.md")
    front_prose, front_targets = _shared_text("docs/public/index.md")

    assert readme_prose == front_prose
    assert readme_targets == [_hosted_url(target) for target in front_targets]


def test_hosted_front_page_starts_with_its_title() -> None:
    first_line = (REPO_ROOT / "docs/public/index.md").read_text(encoding="utf-8").splitlines()[0]

    assert first_line.startswith("# ")


@pytest.mark.parametrize("page", LANDING_PAGES)
def test_landing_page_routes_to_the_first_exercise_and_research(page: str) -> None:
    text = (REPO_ROOT / page).read_text(encoding="utf-8")
    first_route = text.partition("## Validate your first scenario\n")[2].partition("\n## ")[0]

    for label in READER_PURPOSES:
        assert label in text, f"{page} has no {label} route"
    for destination in FIRST_ROUTE_PAGES:
        assert any(destination in target for target in _LINK_TARGET.findall(first_route)), destination


@pytest.mark.parametrize("page", LANDING_PAGES)
def test_landing_page_keeps_task_steps_at_their_destinations(page: str) -> None:
    text = (REPO_ROOT / page).read_text(encoding="utf-8")

    assert "```console" not in text
    assert "```yaml" not in text
    assert not re.search(r"git clone|uv sync|pip install", text)


@pytest.mark.parametrize("page", LANDING_PAGES)
def test_landing_page_keeps_its_heading_links(page: str) -> None:
    headings = re.findall(r"^## (.+)$", (REPO_ROOT / page).read_text(encoding="utf-8"), re.MULTILINE)

    assert set(STABLE_HEADINGS) <= set(headings)


@pytest.mark.parametrize("page", ["docs/index.md", "docs/README.md"])
def test_repository_entry_page_routes_to_the_first_exercise_and_research(page: str) -> None:
    targets = _LINK_TARGET.findall((REPO_ROOT / page).read_text(encoding="utf-8"))

    for destination in ("public/quickstart.md", "public/research.md", "public/citation.md"):
        assert destination in targets, f"{page} has no route to {destination}"


@pytest.mark.parametrize("page", LANDING_PAGES)
def test_landing_page_embeds_the_diagram_with_alt_text(page: str) -> None:
    alt_texts = _DIAGRAM_ALT_TEXT.findall((REPO_ROOT / page).read_text(encoding="utf-8"))

    assert len(alt_texts) == 1, f"{page} must embed the ecosystem diagram once"
    assert alt_texts[0].strip(), f"{page} embeds the ecosystem diagram without alt text"


def test_ecosystem_diagram_has_an_accessible_name_and_description() -> None:
    root = ElementTree.parse(ECOSYSTEM_DIAGRAM).getroot()
    labels = {child.get("id"): child for child in root if child.tag in {f"{SVG}title", f"{SVG}desc"}}
    referenced = [labels.get(label_id) for label_id in root.get("aria-labelledby", "").split()]

    assert root.get("role") == "img"
    assert None not in referenced
    assert sorted(element.tag for element in referenced) == [f"{SVG}desc", f"{SVG}title"]
    assert all(element.text and element.text.strip() for element in referenced)
