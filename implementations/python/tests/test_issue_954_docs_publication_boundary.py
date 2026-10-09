"""Publication-boundary rules adopted from env-packs (issue 954).

The public docs checker rejects internal records under ``docs/public``, Markdown
links that resolve outside it, and published downloads or images that are not
copies of a public file. The static tests run without a docs build.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from tools.check_public_docs import (
    INTERNAL_RECORD_DIRECTORIES,
    MARKDOWN_LINK_PATTERNS,
    MAX_SOURCE_BYTES,
    evaluate_public_boundary,
    evaluate_published_assets,
)
from tools.policy.common import PolicyFailure

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_LANE_RUN = "nox -f noxfile.py -s docs-local"


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _findings(failures: list[PolicyFailure]) -> list[tuple[str, str | None]]:
    return [(failure.rule_id, failure.path) for failure in failures]


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
        "[Tool](../../tools/internal_tool.py)",
        "![Diagram](../decisions/diagram.png)",
        "[Tool](<../../tools/internal_tool.py>)",
        '[Tool](../../tools/internal_tool.py "Tool")',
        "[Tool][tool]\n\n[tool]: ../../tools/internal_tool.py",
        "[Hosts](/etc/hosts)",
    ],
)
def test_markdown_link_that_escapes_the_public_root_fails(tmp_path: Path, markdown: str) -> None:
    _write(tmp_path / "docs" / "public" / "index.md", f"# Index\n\n{markdown}\n")

    assert _findings(evaluate_public_boundary(tmp_path)) == [("public-docs-link-escape", "docs/public/index.md")]


@pytest.mark.parametrize(
    "relative_path",
    ["decisions/adrs/adr-001-example.md", "adrs/README.md", "development/ci.md", "guides/ADR-042-moved.md"],
)
def test_internal_record_under_the_public_root_fails(tmp_path: Path, relative_path: str) -> None:
    _write(tmp_path / "docs" / "public" / relative_path, "# Internal record\n")

    assert _findings(evaluate_public_boundary(tmp_path)) == [
        ("public-docs-internal-record", f"docs/public/{relative_path}")
    ]


@pytest.mark.parametrize("output_parts", [("docs", "_build", "html"), ("docs", "public", "_build", "html")])
def test_published_asset_must_copy_a_public_file(tmp_path: Path, output_parts: tuple[str, ...]) -> None:
    example = _write(tmp_path / "docs" / "public" / "_static" / "first-scenario.sdl.yaml", "name: first-scenario\n")
    output_root = tmp_path.joinpath(*output_parts)
    _write(output_root / "_downloads" / "a1" / example.name, example.read_text(encoding="utf-8"))
    _write(output_root / "_downloads" / "b2" / "internal_tool.py", "print('internal')\n")
    _write(output_root / "_images" / "diagram.png", "internal diagram\n")

    assert _findings(evaluate_published_assets(tmp_path, output_root)) == [
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
    targets = [
        docs_root / match.group(1).split("#", 1)[0]
        for pattern in MARKDOWN_LINK_PATTERNS
        for match in pattern.finditer(index)
        if "://" not in match.group(1)
    ]

    assert [target for target in targets if not target.exists()] == []
    reached = {part for target in targets for part in target.relative_to(docs_root).parts}
    assert sorted(INTERNAL_RECORD_DIRECTORIES - reached) == []


def test_required_gate_runs_the_docs_lane() -> None:
    # test_release_workflows pins that the fail-closed gate needs the checks job.
    workflow_path = REPO_ROOT / ".github" / "workflows" / "canonical-verification.yml"
    checks = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))["jobs"]["checks"]

    assert any(DOCS_LANE_RUN in step.get("run", "") for step in checks["steps"])
