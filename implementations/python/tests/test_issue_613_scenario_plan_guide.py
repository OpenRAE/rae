"""Issue #613: keep the scenario plan guide executable.

``docs/public/sdl/validate-compile-plan.md`` builds the corpus example
``examples/scenarios/guided-web-probe.sdl.yaml`` one section at a time. The
corpus tests already admit the finished file. These checks pin the guide to it:
the guide's steps rebuild the file, every intermediate step validates, and each
output and diagnostic that the guide shows is what the shipped tools return.
"""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest
import yaml
from paths import EXAMPLES_DIR, REPO_ROOT
from raes.language_service import language_diagnostics
from raes_cli.main import app
from typer.testing import CliRunner

GUIDE = REPO_ROOT / "docs" / "public" / "sdl" / "validate-compile-plan.md"
SCENARIO = EXAMPLES_DIR / "guided-web-probe.sdl.yaml"
STEPS = (
    "topology",
    "condition",
    "condition-binding",
    "evidence",
    "attacker-behavior",
    "participants",
    "objectives",
)
SCRIPT_START = "python - <<'PY'\n"
SCRIPT_END = "PY\n"
MISSING_ASSERTION = ("        - web-down-at-end\n", "        - web-offline-at-end\n")


def _block(name: str) -> str:
    """Return the body of the fenced block between the guide's named markers."""
    text = GUIDE.read_text(encoding="utf-8")
    start = f"<!-- scenario-plan:{name}:start -->\n"
    end = f"<!-- scenario-plan:{name}:end -->"
    assert text.count(start) == 1, f"guide block {name!r} must appear exactly once"
    fenced = text.split(start, 1)[1].split(end, 1)[0]
    opening, body = fenced.split("\n", 1)
    assert opening.startswith("```") and body.endswith("```\n"), name
    return body.removesuffix("```\n")


def _merge(document: dict, step: dict) -> None:
    """Add one guide step to the document; a step may extend mappings but never replace a value."""
    for key, value in step.items():
        if isinstance(value, dict) and isinstance(document.get(key), dict):
            _merge(document[key], value)
        else:
            assert key not in document, f"guide step replaces {key!r}"
            document[key] = value


def _document_after(step_count: int) -> dict:
    document: dict = {}
    for name in STEPS[:step_count]:
        _merge(document, yaml.safe_load(_block(name)))
    return document


def _edited_scenario(old: str, new: str) -> str:
    text = SCENARIO.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    return text.replace(old, new)


def _write(directory: Path, text: str) -> Path:
    path = directory / "guided-web-probe.sdl.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _invoke(*args: str):
    return CliRunner().invoke(app, list(args))


def _run_guide_script(name: str, directory: Path, monkeypatch, capsys) -> str:
    """Run one of the guide's ``python - <<'PY'`` snippets in ``directory`` and return its output."""
    block = _block(name)
    assert block.startswith(SCRIPT_START) and block.endswith(SCRIPT_END), name
    script = directory / f"{name}.py"
    script.write_text(block.removeprefix(SCRIPT_START).removesuffix(SCRIPT_END), encoding="utf-8")
    monkeypatch.chdir(directory)
    capsys.readouterr()
    runpy.run_path(str(script), run_name="__main__")
    return capsys.readouterr().out


def _assert_failure_row(code: str, message: str) -> None:
    assert f"| `{code}` | `{message}` |" in GUIDE.read_text(encoding="utf-8")


def test_guide_steps_rebuild_the_corpus_example() -> None:
    assert _document_after(len(STEPS)) == yaml.safe_load(SCENARIO.read_text(encoding="utf-8"))


@pytest.mark.parametrize("step_count", range(1, len(STEPS) + 1), ids=STEPS)
def test_every_guide_step_validates(step_count: int, tmp_path: Path) -> None:
    scenario = _write(tmp_path, yaml.safe_dump(_document_after(step_count), sort_keys=False))

    result = _invoke("semantic", "validate", str(scenario))

    assert result.exit_code == 0, result.output
    assert result.stdout == _block("validate-output")


def test_guide_compile_output_is_an_excerpt_of_the_cli_output() -> None:
    result = _invoke("semantic", "compile", str(SCENARIO), "--output", "json")

    assert result.exit_code == 0, result.output
    assert _block("compile-output") in result.stdout


def test_guide_plan_script_prints_the_documented_plan(tmp_path: Path, monkeypatch, capsys) -> None:
    result = _invoke("processor", "plan", str(SCENARIO), "--format", "json")

    # The reference dry-run manifest declares no capture offers, so the complete
    # plan carries a capture.offer-missing error and the command exits 1.
    assert result.exit_code == 1, result.output
    (tmp_path / "plan.json").write_text(result.stdout, encoding="utf-8")

    assert _run_guide_script("plan-script", tmp_path, monkeypatch, capsys) == _block("plan-output")


def test_guide_duplicate_key_failure_matches_the_tools(tmp_path: Path, monkeypatch, capsys) -> None:
    # The guide's example mistake: appending the condition binding as a second `nodes` key.
    text = SCENARIO.read_text(encoding="utf-8") + "\n" + _block("condition-binding")
    scenario = _write(tmp_path, text)

    result = _invoke("semantic", "validate", str(scenario))

    assert result.exit_code == 1
    assert result.stdout + result.stderr == _block("invalid-output")
    assert _run_guide_script("diagnostics-script", tmp_path, monkeypatch, capsys) == _block("diagnostics-output")
    _assert_failure_row("sdl.mapping_key_conflict", "Duplicate mapping key 'nodes'.")


@pytest.mark.parametrize(
    ("old", "new", "code", "messages"),
    [
        pytest.param(
            "    scope_refs:\n      - nodes.web.services.http\n",
            "",
            "sdl.model.invalid",
            ["evidence requirement must declare scope_refs or scope"],
            id="missing-scope",
        ),
        pytest.param(
            "retention: run_lifetime",
            "retention: forever",
            "sdl.model.invalid",
            ["retention must be one of: not_retained, run_lifetime, study_lifetime, archival, policy_defined, other"],
            id="closed-value",
        ),
        pytest.param(
            "      web-alive: operator\n",
            "      web-alive-check: operator\n",
            "sdl.validation",
            ["Node 'web' references undefined condition 'web-alive-check'"],
            id="undefined-condition",
        ),
        pytest.param(
            "    actions:\n      - stop-web\n    initial_knowledge:",
            "    initial_knowledge:",
            "sdl.validation",
            ["Objective 'take-web-offline' action 'stop-web' is not declared by agent 'red-agent'"],
            id="undeclared-action",
        ),
        pytest.param(
            *MISSING_ASSERTION,
            "sdl.validation",
            [
                "Objective 'take-web-offline' references undefined assertion 'web-offline-at-end' in success criteria",
                "Objective 'take-web-offline' success assertion 'web-offline-at-end' not in assertions section",
            ],
            id="undefined-assertion",
        ),
    ],
)
def test_guide_common_failures_match_the_tools(
    old: str, new: str, code: str, messages: list[str], tmp_path: Path
) -> None:
    text = _edited_scenario(old, new)

    result = _invoke("semantic", "validate", str(_write(tmp_path, text)))

    assert result.exit_code == 1
    assert result.stdout == "validate: invalid\n"
    assert result.stderr.startswith(f"error [{code}] ")
    assert [diagnostic["message"] for diagnostic in language_diagnostics(text)["diagnostics"]] == messages
    _assert_failure_row(code, messages[0])


def test_guide_parse_accepts_what_validate_rejects(tmp_path: Path) -> None:
    broken = _write(tmp_path, _edited_scenario(*MISSING_ASSERTION))

    finished = _invoke("semantic", "parse", str(SCENARIO))
    parsed = _invoke("semantic", "parse", str(broken))
    validated = _invoke("semantic", "validate", str(broken))

    assert (finished.exit_code, finished.stdout) == (0, _block("parse-output"))
    assert (parsed.exit_code, parsed.stdout) == (0, _block("parse-output"))
    assert (validated.exit_code, validated.stdout) == (1, "validate: invalid\n")
