"""ASR-516 owns conformance delivery, not concrete adapter implementations."""

from pathlib import Path

from tools.policy.repository_requirements import RepositoryRequirementClient
from tools.policy.requirement_governance import evaluate_requirement_governance, load_policy, match_phase

ROOT = Path(__file__).resolve().parents[3]
IMPLEMENTATION = "implementations/python/packages/raes_conformance/authoring_adapters.py"


def test_authoring_adapter_delivery_owns_its_contract_and_tests():
    assert match_phase(load_policy(ROOT), "ASR-516").phase_id == "authoring-adapter-conformance"
    paths = [
        IMPLEMENTATION,
        "implementations/python/packages/raes_contracts/contracts/bundle.py",
        "implementations/python/tests/test_authoring_adapters.py",
        "contracts/schemas/authoring-adapters/authoring-adapter-vector-v1.json",
        "contracts/fixtures/authoring-adapters-v1/cases/strict-source.json",
    ]
    assert not evaluate_requirement_governance(
        ROOT, paths, client=RepositoryRequirementClient(ROOT), requirement_uid="ASR-516"
    )


def test_authoring_adapter_delivery_rejects_unrelated_implementations():
    paths = [
        "implementations/python/packages/raes_mcp/server.py",
        "implementations/python/packages/raes_backend_libvirt/target.py",
        "contracts/profiles/backend/unrelated.json",
        "contracts/schemas/sdl/unrelated.json",
        "docs/research/unrelated-study/results.md",
        "docs/requirements/GOV-941/requirement.md",
    ]
    failures = evaluate_requirement_governance(
        ROOT, paths, client=RepositoryRequirementClient(ROOT), requirement_uid="ASR-516"
    )
    assert {failure.path for failure in failures if failure.rule_id == "requirement-ownership-mismatch"} == set(paths)


def test_authoring_adapter_delivery_preserves_prerequisites_and_traceability():
    class IncompleteClient(RepositoryRequirementClient):
        def get_requirement(self, project, requirement_uid):
            result = super().get_requirement(project, requirement_uid)
            return {**result, "status": "DRAFT"} if requirement_uid == "GOV-917" else result

        def get_traceability(self, requirement_id):
            return []

    failures = evaluate_requirement_governance(
        ROOT, [IMPLEMENTATION], client=IncompleteClient(ROOT), requirement_uid="ASR-516"
    )
    assert {failure.rule_id for failure in failures} == {"requirement-order-blocked", "traceability-missing-implements"}
