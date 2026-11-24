"""The Quick Example in the SDL reference page must stay valid SDL."""

from __future__ import annotations

import json
import re
from pathlib import Path

from raes_cli.main import app
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[3]
SDL_REFERENCE = REPO_ROOT / "docs" / "explain" / "sdl" / "index.md"


def _quick_example() -> str:
    """Return the one YAML block of the page's "Quick Example" section."""
    page = SDL_REFERENCE.read_text(encoding="utf-8")
    section = page.partition("\n## Quick Example\n")[2].partition("\n## ")[0]
    blocks = re.findall(r"^```yaml\n(.*?)^```$", section, flags=re.DOTALL | re.MULTILINE)
    assert len(blocks) == 1, f"expected one yaml block in the Quick Example section, found {len(blocks)}"
    return blocks[0]


def test_quick_example_passes_semantic_validation() -> None:
    result = CliRunner().invoke(app, ["semantic", "validate", "-", "--output", "json"], input=_quick_example())

    report = json.loads(result.stdout)
    assert report["diagnostics"] == []
    assert (result.exit_code, report["status"], report["validation_strength"]) == (0, "success", "semantic")
    assert report["payload"]["semantic_validated"] is True
