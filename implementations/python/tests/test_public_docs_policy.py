"""Behavioral tests for the curated public documentation boundary."""

from __future__ import annotations

import json
import os
import re
import runpy
import shlex
import sys
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raes import parse_sdl_file  # noqa: E402
from raes_cli.main import app  # noqa: E402
from raes_contracts.behavioral_relations import validate_behavioral_claim_binding  # noqa: E402
from raes_contracts.contracts import BehavioralClaimBindingModel  # noqa: E402
from tools.check_public_docs import (  # noqa: E402
    REQUIRED_PUBLIC_PAGES,
    REQUIRED_PUBLIC_REDIRECTS,
    evaluate_public_output,
    evaluate_public_sources,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_public_docs(repo_root: Path) -> Path:
    public_root = repo_root / "docs" / "public"
    for relative_path in REQUIRED_PUBLIC_PAGES:
        _write(public_root / relative_path, f"# {Path(relative_path).stem.title()}\n")
    _write(public_root / "redirects.json", json.dumps(REQUIRED_PUBLIC_REDIRECTS))
    _write(public_root / "conf.py", 'project = "RAES"\n')
    return public_root


def test_public_source_root_accepts_only_contained_regular_sources(tmp_path: Path) -> None:
    _seed_public_docs(tmp_path)

    assert evaluate_public_sources(tmp_path) == []


def test_public_source_root_rejects_symlinks(tmp_path: Path) -> None:
    public_root = _seed_public_docs(tmp_path)
    internal = tmp_path / "docs" / "decisions" / "private.md"
    _write(internal, "# Internal decision\n")
    os.symlink(internal, public_root / "linked-decision.md")

    failures = evaluate_public_sources(tmp_path)

    assert any(failure.rule_id == "public-docs-symlink" for failure in failures)
    assert all("Internal decision" not in failure.message for failure in failures)


def test_public_source_root_rejects_directives_that_escape_it(tmp_path: Path) -> None:
    public_root = _seed_public_docs(tmp_path)
    _write(
        public_root / "quickstart.md",
        "# Quickstart\n\n```{literalinclude} ../decisions/private.md\n```\n",
    )

    failures = evaluate_public_sources(tmp_path)

    assert [(failure.rule_id, failure.path) for failure in failures] == [
        ("public-docs-source-escape", "docs/public/quickstart.md")
    ]


def test_public_source_root_requires_the_legacy_redirect_contract(tmp_path: Path) -> None:
    public_root = _seed_public_docs(tmp_path)
    redirects = dict(REQUIRED_PUBLIC_REDIRECTS)
    redirects.pop("explain/getting-started")
    _write(public_root / "redirects.json", json.dumps(redirects))

    failures = evaluate_public_sources(tmp_path)

    assert [(failure.rule_id, failure.path) for failure in failures] == [
        ("public-docs-redirect-map", "docs/public/redirects.json")
    ]


def _seed_public_output(public_root: Path, output_root: Path) -> None:
    for source in public_root.rglob("*.md"):
        route = source.relative_to(public_root).with_suffix(".html")
        _write(output_root / route, "<html></html>\n")
    for source, target in REQUIRED_PUBLIC_REDIRECTS.items():
        _write(
            output_root / f"{source}.html",
            f'<html><meta http-equiv="refresh" content="0; url={target}"></html>\n',
        )
    _write(output_root / "genindex.html", "<html></html>\n")
    _write(output_root / "search.html", "<html></html>\n")
    search_index = {
        "docnames": sorted(
            source.relative_to(public_root).with_suffix("").as_posix() for source in public_root.rglob("*.md")
        )
    }
    _write(output_root / "searchindex.js", f"Search.setIndex({json.dumps(search_index)})")


def test_public_output_rejects_unexpected_pages_and_search_documents(tmp_path: Path) -> None:
    public_root = _seed_public_docs(tmp_path)
    output_root = tmp_path / "docs" / "_build" / "html"
    _seed_public_output(public_root, output_root)
    _write(output_root / "decisions" / "private.html", "<html></html>\n")
    search_index = {
        "docnames": [
            *sorted(source.relative_to(public_root).with_suffix("").as_posix() for source in public_root.rglob("*.md")),
            "decisions/private",
        ]
    }
    _write(output_root / "searchindex.js", f"Search.setIndex({json.dumps(search_index)})")
    _write(
        output_root / "sitemap.xml",
        '<?xml version="1.0"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        "  <url><loc>https://docs.example.test/en/latest/decisions/index.html</loc></url>\n"
        "</urlset>\n",
    )

    failures = evaluate_public_output(tmp_path, output_root)

    assert {failure.rule_id for failure in failures} == {
        "public-docs-output-route",
        "public-docs-search-route",
        "public-docs-sitemap-route",
    }


def test_public_output_rejects_missing_or_tampered_redirects(tmp_path: Path) -> None:
    public_root = _seed_public_docs(tmp_path)
    output_root = tmp_path / "docs" / "_build" / "html"
    _seed_public_output(public_root, output_root)
    source, _target = next(iter(REQUIRED_PUBLIC_REDIRECTS.items()))
    _write(
        output_root / f"{source}.html",
        '<html><meta http-equiv="refresh" content="0; url=../../decisions/private.html"></html>\n',
    )

    failures = evaluate_public_output(tmp_path, output_root)

    assert [(failure.rule_id, failure.path) for failure in failures] == [
        ("public-docs-redirect-output", f"{source}.html")
    ]


def test_checked_in_quickstart_scenario_parses() -> None:
    scenario_path = REPO_ROOT / "docs" / "public" / "_static" / "examples" / "first-scenario.sdl.yaml"

    parsed = parse_sdl_file(scenario_path)

    assert parsed.name == "first-scenario"


def test_public_docs_linkcheck_is_bounded_serialized_and_skips_own_repository() -> None:
    config = runpy.run_path(str(REPO_ROOT / "docs" / "public" / "conf.py"))

    assert config["linkcheck_timeout"] == 15
    assert config["linkcheck_workers"] == 1
    assert config["linkcheck_ignore"] == [r"^https://github\.com/(?:RAESystem|OpenRAE)/rae(?:/|$)"]


def test_readme_quickstart_matches_checked_in_scenario() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(
        r"<!-- quickstart-sdl:start -->\s*```yaml\s*(.*?)\s*```\s*<!-- quickstart-sdl:end -->",
        readme,
        re.DOTALL,
    )
    assert match is not None
    readme_scenario = yaml.safe_load(match.group(1))
    checked_in_scenario = yaml.safe_load(
        (REPO_ROOT / "docs" / "public" / "_static" / "examples" / "first-scenario.sdl.yaml").read_text(encoding="utf-8")
    )

    assert readme_scenario == checked_in_scenario


def _stated_format_check(tutorial: str) -> tuple[list[str], int, str]:
    """Return the tutorial's format command arguments, stated exit code and shown output."""
    section = tutorial.partition("## Check the file format\n")[2].partition("\n## ")[0]
    command = re.search(r"```console\n(.*?)```", section, re.DOTALL)
    assert command is not None
    arguments = shlex.split(command.group(1).replace("\\\n", " "))
    claims = section[command.end() :]
    exit_code = re.search(r"[Ee]xits?(?: with)? code `(\d+)`", claims)
    assert exit_code is not None
    output = re.search(r"```text\n(.*?)```", claims, re.DOTALL)
    return arguments[arguments.index("raes") + 1 :], int(exit_code.group(1)), output.group(1) if output else ""


def test_first_scenario_tutorial_states_the_real_format_check_result(monkeypatch: pytest.MonkeyPatch) -> None:
    tutorial = (REPO_ROOT / "docs" / "public" / "tutorials" / "first-scenario.md").read_text(encoding="utf-8")
    arguments, stated_exit_code, shown_output = _stated_format_check(tutorial)
    monkeypatch.chdir(REPO_ROOT)

    result = CliRunner().invoke(app, arguments)

    assert (result.exit_code, result.stderr) == (stated_exit_code, shown_output)


def test_participant_control_claim_example_is_bounded() -> None:
    guide = (REPO_ROOT / "docs" / "public" / "participant-control.md").read_text(encoding="utf-8")
    match = re.search(
        r"<!-- participant-control-claim:start -->\s*```json\s*(.*?)\s*```"
        r"\s*<!-- participant-control-claim:end -->",
        guide,
        re.DOTALL,
    )
    assert match is not None

    binding = BehavioralClaimBindingModel.model_validate_json(match.group(1))
    validated = validate_behavioral_claim_binding(binding)

    assert validated.relation_id == "bounded-probe-success"
    assert validated.quantifier_scope == "finite-cases"
    assert validated.evidence_scope == "finite"
    assert validated.assurance_status == "tested"
    assert validated.observation_projection_ref == "participant-policy-probe-projection"
    assert validated.observation_projection_revision == "rev1"
    required_cases = {
        "denial",
        "withholding",
        "redaction",
        "governed declassification",
        "transformation",
        "participant-directed inject delivery",
        "unsupported-capability",
    }
    assert all(case in validated.evidence_boundary for case in required_cases)
    assert validated.evidence_refs
    assert validated.limitations
    assert any("noninterference" in nonclaim for nonclaim in validated.explicit_non_claims)
    assert any("bisimulation" in nonclaim for nonclaim in validated.explicit_non_claims)
