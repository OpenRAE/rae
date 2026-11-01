"""Open concern omission cannot establish successful runtime realization."""

from copy import deepcopy
from dataclasses import replace

import pytest
from raes.explicitness import ExplicitnessProvenance
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ChangeAction, RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry
from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope
from raes_processor.planner import (
    realization_authority_disclosure,
    realization_cleanup_diagnostics,
    realization_disclosure,
)
from raes_runtime.backend_calls import _call_backend_apply
from raes_runtime.backend_realization_authority import _RealizationApplyContext
from test_issue_1200_mixed_runtime_constraints import _fixture
from test_issue_1758_open_empty_concern import _snapshot


def _case(field="mail_services"):
    model, plan, manifest = _fixture({}, scope=f"/nodes/host/runtime/{field}")
    requirement = next(item for item in model.realization_requirements if item.field_path.endswith(f".{field}"))
    assert requirement.structure is None
    assert requirement.constraint_document is None
    operation = next(item for item in plan.operations if item.address == requirement.address)
    return requirement, plan, manifest, operation


def _returned(requirement, plan, operation, runtime=None, *, observed=True):
    snapshot = _snapshot(operation, requirement, runtime=runtime, observed=observed)
    return replace(
        snapshot,
        realization_envelope=plan.realization_envelope,
        realization_observations=tuple(
            replace(item, observation_strength=ObservationStrength.GUEST_OBSERVED)
            for item in snapshot.realization_observations
        ),
    )


def _evaluate(route, requirement, plan, snapshot, manifest):
    if route == "compiled":
        return realization_disclosure((requirement,), plan, snapshot, manifest=manifest)
    diagnostics, provenance = realization_authority_disclosure(plan, snapshot, manifest=manifest)
    return diagnostics, tuple(item for item in provenance if item.requirement_kind == requirement.requirement_kind)


@pytest.mark.parametrize("route", ["compiled", "portable"])
@pytest.mark.parametrize("field", ["mail_services", "ssh_servers", "scheduled_jobs", "environment"])
@pytest.mark.parametrize("missing", ["entry", "parent", "field"])
def test_missing_open_report_is_rejected_even_with_corroboration(route, field, missing):
    requirement, plan, manifest, operation = _case(field)
    snapshot = _returned(requirement, plan, operation, {} if missing == "field" else None)
    if missing == "entry":
        snapshot = replace(snapshot, entries={})

    diagnostics, provenance = _evaluate(route, requirement, plan, snapshot, manifest)

    assert diagnostics
    assert all(
        item.code == "runtime.backend-contract-invalid" and item.address == requirement.address for item in diagnostics
    )
    assert any(requirement.requirement_kind in item.message for item in diagnostics)
    assert provenance == ()


@pytest.mark.parametrize("route", ["compiled", "portable"])
@pytest.mark.parametrize("value", [None, {}, False, "private-invalid-report"])
def test_malformed_open_report_is_rejected_without_value_exposure(route, value):
    requirement, plan, manifest, operation = _case()
    snapshot = _returned(requirement, plan, operation, {"mail_services": value})

    diagnostics, provenance = _evaluate(route, requirement, plan, snapshot, manifest)

    assert [item.code for item in diagnostics] == ["runtime.backend-contract-invalid"]
    assert "private-invalid-report" not in repr(diagnostics)
    assert provenance == ()


@pytest.mark.parametrize("route", ["compiled", "portable"])
@pytest.mark.parametrize(
    "evidence", ["valid", "missing", "address", "field_path", "domain", "kind", "scope", "source", "manifest"]
)
def test_explicit_empty_open_report_requires_matching_sufficient_evidence(route, evidence):
    requirement, plan, manifest, operation = _case()
    snapshot = _returned(requirement, plan, operation, {"mail_services": []}, observed=evidence != "missing")
    changes = {
        "address": {"address": "provision.node.other"},
        "field_path": {"field_path": "nodes.host.runtime.ssh_servers"},
        "domain": {"domain": "other"},
        "kind": {"requirement_kind": "runtime-ssh-servers"},
        "scope": {"verification_scope": RealizationVerificationScope.PRESENCE},
        "source": {"observation_strength": ObservationStrength.DRIVER_REPORTED},
    }
    if evidence in changes:
        snapshot = replace(
            snapshot, realization_observations=(replace(snapshot.realization_observations[0], **changes[evidence]),)
        )
    if evidence == "manifest":
        manifest = replace(
            manifest,
            realization_support=tuple(
                replace(item, observation_capabilities={}) for item in manifest.realization_support
            ),
        )

    diagnostics, provenance = _evaluate(route, requirement, plan, snapshot, manifest)

    if evidence == "valid":
        assert diagnostics == []
        assert [(item.requirement_kind, item.provenance) for item in provenance] == [
            (requirement.requirement_kind, ExplicitnessProvenance.BACKEND_REALIZED)
        ]
    else:
        assert [item.code for item in diagnostics] == ["runtime.backend-contract-invalid"]
        assert provenance == ()


def test_omission_without_a_verification_floor_preserves_existing_behavior():
    requirement, plan, manifest, _operation = _case()
    requirement = replace(requirement, verification_scope=None, required_observation_strength=None)

    assert realization_disclosure((requirement,), plan, RuntimeSnapshot(), manifest=manifest) == ([], ())


@pytest.mark.parametrize("deleted", [True, False])
def test_inapplicable_open_requirement_does_not_demand_a_report(deleted):
    requirement, plan, manifest, operation = _case()
    plan = replace(
        plan,
        operations=[replace(operation, action=ChangeAction.DELETE)] if deleted else [],
        realization_authority=(),
        realization_constraints=(),
    )

    assert realization_disclosure((requirement,), plan, RuntimeSnapshot(), manifest=manifest) == ([], ())


@pytest.mark.parametrize("reported", [True, False])
def test_adapter_retains_only_corroborated_successful_reports(reported):
    requirement, plan, manifest, operation = _case()
    retained = replace(operation, address="provision.node.retained", payload={"node_name": "retained"})
    baseline = RuntimeSnapshot(
        entries={
            retained.address: SnapshotEntry(retained.address, RuntimeDomain.PROVISIONING, "node", retained.payload)
        }
    )

    def backend(submitted, snapshot):
        returned = _returned(requirement, submitted, operation, {"mail_services": []} if reported else {})
        return ApplyResult(
            True,
            returned.with_entries({**deepcopy(dict(snapshot.entries)), **returned.entries}),
            changed_addresses=[operation.address],
            details={"candidate": "private-result-details"},
        )

    result = _call_backend_apply(
        backend,
        plan,
        baseline,
        address="runtime.apply.provisioning",
        snapshot=baseline,
        realization=_RealizationApplyContext(plan=plan, manifest=manifest),
    )

    assert result.success is reported, result.diagnostics
    if reported:
        assert result.snapshot.entries[retained.address] == baseline.entries[retained.address]
        assert result.snapshot.entries[operation.address].payload["spec"]["node"]["runtime"]["mail_services"] == []
        assert result.snapshot.realization_observations == ()
        assert any(
            item.requirement_kind == requirement.requirement_kind for item in result.snapshot.realization_provenance
        )
    else:
        assert result.snapshot == baseline
        assert result.changed_addresses == []
        assert result.details == {}
        assert "private-result-details" not in repr(result)
        assert [item.code for item in result.diagnostics] == ["runtime.backend-contract-invalid"]


def test_failed_apply_retains_partial_inventory_without_claiming_readback_success():
    requirement, plan, manifest, operation = _case()
    baseline = RuntimeSnapshot()

    def backend(submitted, snapshot):
        return ApplyResult(
            False,
            _returned(requirement, submitted, operation, {}, observed=False),
            changed_addresses=[operation.address],
            diagnostics=[
                Diagnostic(
                    code="test.readback-failed", domain="runtime", address=operation.address, message="Readback failed."
                )
            ],
        )

    result = _call_backend_apply(
        backend,
        plan,
        baseline,
        address="runtime.apply.provisioning",
        snapshot=baseline,
        realization=_RealizationApplyContext(plan=plan, manifest=manifest),
    )

    assert not result.success
    assert operation.address in result.snapshot.entries
    assert result.changed_addresses == [operation.address]
    assert [item.code for item in result.diagnostics] == ["test.readback-failed"]
    assert result.snapshot.realization_provenance == ()


@pytest.mark.parametrize("corruption", ["authority", "closed", "report"])
def test_cleanup_projection_preserves_original_authority_and_supplied_value_checks(corruption):
    requirement, plan, manifest, operation = _case()
    snapshot = _returned(requirement, plan, operation, {}, observed=False)
    if corruption == "authority":
        plan = replace(plan, realization_authority=plan.realization_authority[:-1])
    elif corruption == "closed":
        snapshot.entries[operation.address].payload["node_kind"] = "switch"
    else:
        snapshot.entries[operation.address].payload["spec"]["node"]["runtime"]["mail_services"] = []
    original = deepcopy(plan)

    diagnostics = realization_cleanup_diagnostics(plan, snapshot, manifest=manifest)

    assert diagnostics
    assert plan == original


def test_missing_report_with_only_a_source_constraint_is_rejected():
    requirement, plan, manifest, _ = _case()
    requirement = replace(
        requirement, verification_scope=None, required_observation_strength=ObservationStrength.GUEST_OBSERVED
    )

    diagnostics, provenance = realization_disclosure((requirement,), plan, RuntimeSnapshot(), manifest=manifest)

    assert [item.code for item in diagnostics] == ["runtime.backend-contract-invalid"]
    assert provenance == ()
