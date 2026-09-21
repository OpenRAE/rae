from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.check_example_library import (  # noqa: E402
    CATALOG_RELATIVE_PATH,
    REQUIRED_SURFACES,
    REQUIREMENT_REF,
    evaluate_example_library,
)

_VALID_BODY = {
    "name": "library-policy-test",
    "nodes": {
        "app": {
            "type": "compute",
            "resources": {"ram": "1 GiB", "cpu": 1},
            "services": [{"port": 443, "name": "https"}],
        }
    },
    "conditions": {
        "app-healthy": {
            "proposition": "app-healthy",
            "command": "curl -fsS https://app/health",
            "interval": 30,
        }
    },
    "evidence_requirements": {
        "app-health-evidence": {
            "description": "Capture the governed application health observation.",
            "source_refs": ["nodes.app.services.https"],
            "scope_refs": ["nodes.app"],
            "trigger_ref": "conditions.app-healthy",
            "channel": "api_response",
            "artifact_role": "proposition_truth_evidence",
            "media_types": ["application/json"],
            "sensitivity": "plain",
            "redaction": "redact_secrets",
            "integrity": "checksum",
            "retention": "study_lifetime",
            "loss_disclosure": "required",
        }
    },
    "propositions": {
        "app-healthy": {
            "description": "The governed application service responds successfully.",
            "subjects": ["nodes.app.services.https"],
            "basis": "observed_state",
            "predicate": {
                "kind": "boolean",
                "property": "service-healthy",
                "semantic_ref": "urn:raes:observable:service-healthy",
                "operator": "equals",
                "expected": True,
            },
            "evidence_requirements": ["app-health-evidence"],
        }
    },
    "assertions": {
        "app-healthy": {
            "description": "Application health must hold at the objective boundary.",
            "proposition": "app-healthy",
            "role": "postcondition",
            "polarity": "positive",
        }
    },
    "entities": {"blue-team": {"role": "blue"}},
    "agents": {"operator": {"affiliations": ["blue-team"]}},
    "objectives": {
        "verify-app-health": {
            "assigned_participant": "operator",
            "targets": ["nodes.app.services.https"],
            "success": {"assertions": ["app-healthy"]},
        }
    },
    "workflows": {
        "baseline-check": {
            "start": "verify",
            "steps": {
                "verify": {
                    "type": "objective",
                    "objective": "verify-app-health",
                    "on_success": "done",
                },
                "done": {"type": "end"},
            },
        }
    },
}


def _write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def _seed_repo(tmp_path: Path) -> Path:
    catalog: dict[str, Any] = {
        "library": "raes-example-pattern-library",
        "version": 1,
        "requirement_refs": [REQUIREMENT_REF],
        "source_refs": ["examples/README.md"],
        "surfaces": {},
    }
    for surface in REQUIRED_SURFACES:
        worked_path = f"examples/library/worked/{surface}.txt"
        template_path = f"examples/library/templates/{surface}/template.yaml"
        pattern_path = f"examples/library/patterns/{surface}.yaml"
        catalog["surfaces"][surface] = {
            "summary": f"{surface} surface with enough detail for the policy checker.",
            "worked_examples": [
                {
                    "id": f"{surface}-worked",
                    "path": worked_path,
                    "source_refs": ["examples/README.md"],
                }
            ],
            "templates": [{"id": f"{surface}-template", "path": template_path}],
            "patterns": [{"id": f"{surface}-pattern", "path": pattern_path}],
        }
        worked_file = tmp_path / worked_path
        worked_file.parent.mkdir(parents=True, exist_ok=True)
        worked_file.write_text("worked example\n", encoding="utf-8")
        _write_yaml(
            tmp_path / template_path,
            {
                "template": "raes-library-template",
                "version": 1,
                "id": f"{surface}-template",
                "surface": surface,
                "requirement_refs": [REQUIREMENT_REF],
                "source_refs": ["docs/explain/sdl/sections.md"],
                "summary": f"Reusable {surface} template for policy tests.",
                "body": dict(_VALID_BODY, name=f"{surface}-template"),
            },
        )
        _write_yaml(
            tmp_path / pattern_path,
            {
                "pattern": "raes-library-pattern",
                "version": 1,
                "id": f"{surface}-pattern",
                "surface": surface,
                "requirement_refs": [REQUIREMENT_REF],
                "source_refs": ["docs/explain/sdl/validation.md"],
                "summary": f"Reusable {surface} pattern for policy tests.",
                "intent": "Exercise the policy checker with a substantive reusable pattern.",
                "authoring_steps": ["Start from a valid SDL body."],
                "validation": [{"command": "parse_sdl_file", "expected": "valid SDL"}],
            },
        )
    _write_yaml(tmp_path / CATALOG_RELATIVE_PATH, catalog)
    return tmp_path


def _catalog_path(repo_root: Path) -> Path:
    return repo_root / CATALOG_RELATIVE_PATH


def _read_catalog(repo_root: Path) -> dict[str, Any]:
    return yaml.safe_load(_catalog_path(repo_root).read_text(encoding="utf-8"))


def _write_catalog(repo_root: Path, catalog: dict[str, Any]) -> None:
    _write_yaml(_catalog_path(repo_root), catalog)


def _flagged(failures, marker: str) -> bool:
    needle = marker.lower()
    return any(failure.rule_id == marker or needle in failure.render().lower() for failure in failures)


def test_good_example_library_has_no_failures(tmp_path: Path) -> None:
    assert evaluate_example_library(_seed_repo(tmp_path)) == []


def test_requirement_ref_is_aut_806() -> None:
    assert REQUIREMENT_REF == "AUT-806"


def test_required_surfaces_cover_aut_806_clauses() -> None:
    assert REQUIRED_SURFACES == (
        "scenario",
        "workflow",
        "participant_behavior",
        "task",
        "run",
        "study",
    )


def test_missing_surface_is_flagged(tmp_path: Path) -> None:
    repo_root = _seed_repo(tmp_path)
    catalog = _read_catalog(repo_root)
    del catalog["surfaces"]["study"]
    _write_catalog(repo_root, catalog)

    failures = evaluate_example_library(repo_root)

    assert _flagged(failures, "example-library-surface")


def test_top_level_requirement_ref_is_flagged(tmp_path: Path) -> None:
    repo_root = _seed_repo(tmp_path)
    catalog = _read_catalog(repo_root)
    catalog["requirement_refs"] = ["OTHER-001"]
    _write_catalog(repo_root, catalog)

    failures = evaluate_example_library(repo_root)

    assert _flagged(failures, "example-library-requirement-ref")


def test_template_body_must_parse_as_sdl(tmp_path: Path) -> None:
    repo_root = _seed_repo(tmp_path)
    template_path = repo_root / "examples/library/templates/scenario/template.yaml"
    template = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    del template["body"]["name"]
    _write_yaml(template_path, template)

    failures = evaluate_example_library(repo_root)

    assert _flagged(failures, "example-library-template-body")


def test_pattern_surface_must_match_catalog(tmp_path: Path) -> None:
    repo_root = _seed_repo(tmp_path)
    pattern_path = repo_root / "examples/library/patterns/scenario.yaml"
    pattern = yaml.safe_load(pattern_path.read_text(encoding="utf-8"))
    pattern["surface"] = "workflow"
    _write_yaml(pattern_path, pattern)

    failures = evaluate_example_library(repo_root)

    assert _flagged(failures, "example-library-pattern-surface")
