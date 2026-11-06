"""Generated transports do not move the concept-authority data boundary."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_generated_concept_transport_keeps_authority_data_paths_guarded() -> None:
    policy = yaml.safe_load((REPO_ROOT / "tools/policy/adr_policy.yaml").read_text())
    allowed = {Path(path) for path in policy["concept_authority"]["allowed_paths"]}
    generated = Path("implementations/go/contract/binding/concept-families-v1_generated.go")
    forbidden = {
        Path("implementations/go/contract/binding/concept-families-v1.json"),
        Path("docs/drafts/concept-authority-notes.md"),
        Path("implementations/go/contract/binding/concept-families-v1_generated.go.copy"),
    }
    assert generated in allowed
    for path in forbidden:
        assert path not in allowed
        assert allowed.isdisjoint(path.parents)
