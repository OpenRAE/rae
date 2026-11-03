"""Generated transports do not move the concept-authority data boundary."""

from pathlib import Path

from tools.policy.repo_policy import evaluate_repo_policy

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_generated_concept_transport_keeps_authority_data_paths_guarded() -> None:
    generated = "implementations/go/internal/contract/binding/concept-families-v1_generated.go"
    forbidden = {
        "implementations/go/internal/contract/binding/concept-families-v1.json",
        "docs/drafts/concept-authority-notes.md",
        "implementations/go/internal/contract/binding/concept-families-v1_generated.go.copy",
    }
    failures = evaluate_repo_policy(REPO_ROOT, [generated, *sorted(forbidden)], check_set="file-local")
    assert {(failure.rule_id, failure.path) for failure in failures} == {
        ("concept-authority-reserved-path", path) for path in forbidden
    }
