"""Publication-boundary rules adopted from env-packs (issue 954).

The public docs checker rejects internal records under ``docs/public``, Markdown
links and file-reading directives that resolve outside it, and published
downloads or images that are not copies of a public file. The static tests run
without a docs build.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from tools.check_public_docs import (
    INTERNAL_RECORD_DIRECTORIES,
    MAX_SOURCE_BYTES,
    REQUIRED_PUBLIC_PAGES,
    REQUIRED_PUBLIC_REDIRECTS,
    evaluate_public_boundary,
    evaluate_public_sources,
    evaluate_published_assets,
)
from tools.policy.common import PolicyFailure
from tools.public_docs_markup import markdown_link_targets

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_LANE_RUN = "nox -f noxfile.py -s docs-local"
TOOL_LINK = "[Tool](../../tools/internal_tool.py)"


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _findings(failures: list[PolicyFailure]) -> list[tuple[str, str | None]]:
    return [(failure.rule_id, failure.path) for failure in failures]


@pytest.fixture
def seeded_repo(tmp_path: Path) -> Path:
    public_root = tmp_path / "docs" / "public"
    for relative_path in REQUIRED_PUBLIC_PAGES:
        _write(public_root / relative_path, "# Page\n")
    _write(public_root / "redirects.json", json.dumps(REQUIRED_PUBLIC_REDIRECTS))
    return tmp_path


def test_pages_and_links_inside_the_public_root_pass(tmp_path: Path) -> None:
    public_root = tmp_path / "docs" / "public"
    _write(public_root / "quickstart.md", "# Quickstart\n")
    _write(public_root / "guides" / "development-setup.md", "# Set up\n")
    _write(
        public_root / "sdl" / "index.md",
        "[Start](../quickstart.md) [Set up](../guides/development-setup.md#install) "
        "[Site](https://example.test/docs) [Top](#top) [Mail](mailto:docs@example.test)\n\n"
        "[start]: ../quickstart.md\n[^note]: ../../a footnote, not a link\n",
    )

    assert evaluate_public_boundary(tmp_path) == []


@pytest.mark.parametrize(
    "markdown",
    [
        TOOL_LINK,
        "![Diagram](../decisions/diagram.png)",
        "[Tool](<../../tools/internal_tool.py>)",
        '[Tool](../../tools/internal_tool.py "Tool")',
        "[Tool][tool]\n\n[tool]: ../../tools/internal_tool.py",
        "[Hosts](/etc/hosts)",
        # MyST parses directive and colon fence bodies as Markdown.
        f"```{{note}}\n{TOOL_LINK}\n```",
        f":::\n{TOOL_LINK}\n:::",
        f"```text\nexample\n```\n\n`code` {TOOL_LINK}",
    ],
)
def test_markdown_link_that_escapes_the_public_root_fails(tmp_path: Path, markdown: str) -> None:
    _write(tmp_path / "docs" / "public" / "index.md", f"# Index\n\n{markdown}\n")

    assert _findings(evaluate_public_boundary(tmp_path)) == [("public-docs-link-escape", "docs/public/index.md")]


@pytest.mark.parametrize(
    "markdown",
    [
        f"```text\n{TOOL_LINK}\n```",
        f"~~~~\n{TOOL_LINK}\n~~~~",
        f"Write `{TOOL_LINK}` or ``{TOOL_LINK}``.",
        f"````{{note}}\n```markdown\n{TOOL_LINK}\n```\n````",
    ],
    ids=["backtick-fence", "tilde-fence", "code-span", "fence-inside-a-directive"],
)
def test_link_shown_as_code_passes(tmp_path: Path, markdown: str) -> None:
    _write(tmp_path / "docs" / "public" / "index.md", f"# Index\n\n{markdown}\n")

    assert evaluate_public_boundary(tmp_path) == []


@pytest.mark.parametrize(
    ("page", "directive"),
    [
        pytest.param("support.md", "```{raw} html\n:file: ../decisions/record.md\n```", id="myst-raw"),
        pytest.param("support.md", "```{csv-table} Data\n:file: ../development/data.csv\n```", id="myst-csv-table"),
        pytest.param("api/index.rst", ".. raw:: html\n   :file: ../../development/record.md", id="rst-raw"),
        pytest.param(
            "support.md", "```{raw} html\n---\nfile: ../decisions/record.md\n---\n```", id="myst-yaml-options"
        ),
        pytest.param(
            "support.md", '- Item\n\n  ```{raw} html\n  :"file" : ../decisions/record.md\n  ```', id="myst-quoted-key"
        ),
        pytest.param(
            "support.md", "```{literalinclude} quickstart.md\n:diff: ../development/record.md\n```", id="diff"
        ),
        pytest.param("support.md", "```{raw} html\n:url: file:///srv/docs/development/record.md\n```", id="file-url"),
        pytest.param("support.md", ":::{include} ../development/record.md\n:::", id="colon-fence-include"),
        pytest.param("support.md", "~~~{include} ../development/record.md\n~~~", id="tilde-fence-include"),
        pytest.param("support.md", "```` {include} ../development/record.md\n````", id="long-fence-include"),
    ],
)
def test_directive_that_reads_a_file_outside_the_public_root_fails(
    seeded_repo: Path, page: str, directive: str
) -> None:
    _write(seeded_repo / "docs" / "public" / page, f"{directive}\n")

    assert _findings(evaluate_public_sources(seeded_repo)) == [("public-docs-source-escape", f"docs/public/{page}")]


def test_directive_that_reads_a_public_file_passes(seeded_repo: Path) -> None:
    _write(
        seeded_repo / "docs" / "public" / "support.md",
        "```{csv-table} Data\n:file: _static/data.csv\n```\n\n:::{include} guides/python.md\n:::\n\n"
        "```{raw} html\n---\nurl: https://example.test/banner.html\n---\n```\n",
    )

    assert evaluate_public_sources(seeded_repo) == []


@pytest.mark.parametrize(
    "relative_path",
    ["decisions/adrs/adr-001-example.md", "adrs/README.md", "development/ci.md", "guides/ADR-042-moved.md"],
)
def test_internal_record_under_the_public_root_fails(tmp_path: Path, relative_path: str) -> None:
    _write(tmp_path / "docs" / "public" / relative_path, "# Internal record\n")

    assert _findings(evaluate_public_boundary(tmp_path)) == [
        ("public-docs-internal-record", f"docs/public/{relative_path}")
    ]


@pytest.mark.parametrize(
    "output_trees",
    [
        [("docs", "_build", "html")],
        [("docs", "public", "_build", "html")],
        # A stale build under docs/public is not a source, so its copies hide nothing.
        [("docs", "_build", "html"), ("docs", "public", "_build", "html")],
    ],
    ids=["outside-the-public-root", "inside-the-public-root", "beside-a-stale-public-build"],
)
def test_published_asset_must_copy_a_public_file(tmp_path: Path, output_trees: list[tuple[str, ...]]) -> None:
    example = _write(tmp_path / "docs" / "public" / "_static" / "first-scenario.sdl.yaml", "name: first-scenario\n")
    output_roots = [tmp_path.joinpath(*parts) for parts in output_trees]
    for output_root in output_roots:
        _write(output_root / "_downloads" / "a1" / example.name, example.read_text(encoding="utf-8"))
        _write(output_root / "_downloads" / "b2" / "internal_tool.py", "print('internal')\n")
        _write(output_root / "_images" / "diagram.png", "internal diagram\n")

    assert _findings(evaluate_published_assets(tmp_path, output_roots[0])) == [
        ("public-docs-output-asset", "_downloads/b2/internal_tool.py"),
        ("public-docs-output-asset", "_images/diagram.png"),
    ]


@pytest.mark.parametrize(
    "payload", [b"\xff[Tool](../../tools/internal_tool.py)\n", b"[Tool](../tool.py)" + b" " * MAX_SOURCE_BYTES]
)
def test_unreadable_or_oversized_page_is_left_to_the_source_check(tmp_path: Path, payload: bytes) -> None:
    page = tmp_path / "docs" / "public" / "index.md"
    page.parent.mkdir(parents=True)
    page.write_bytes(payload)

    assert evaluate_public_boundary(tmp_path) == []


def test_missing_public_root_is_left_to_the_source_check(tmp_path: Path) -> None:
    assert evaluate_public_boundary(tmp_path) == []
    assert evaluate_published_assets(tmp_path, tmp_path / "docs" / "_build" / "html") == []


def test_checked_in_public_docs_hold_the_boundary() -> None:
    assert evaluate_public_boundary(REPO_ROOT) == []


def test_developer_index_links_resolve_and_reach_every_internal_record_kind() -> None:
    docs_root = REPO_ROOT / "docs"
    index = (docs_root / "README.md").read_text(encoding="utf-8")
    targets = [docs_root / target.split("#", 1)[0] for target in markdown_link_targets(index) if "://" not in target]

    assert [target for target in targets if not target.exists()] == []
    reached = {part for target in targets for part in target.relative_to(docs_root).parts}
    assert sorted(INTERNAL_RECORD_DIRECTORIES - reached) == []


def test_required_gate_runs_the_docs_lane() -> None:
    # test_release_workflows pins that the fail-closed gate needs the checks job.
    workflow_path = REPO_ROOT / ".github" / "workflows" / "canonical-verification.yml"
    checks = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))["jobs"]["checks"]

    assert any(DOCS_LANE_RUN in step.get("run", "") for step in checks["steps"])
