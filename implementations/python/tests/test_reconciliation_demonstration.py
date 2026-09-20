"""Tests for the reconciliation demonstration harness (issue #610)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from paths import EXAMPLES_DIR
from raes_backend_protocols.capabilities import BackendManifest
from raes_backend_protocols.manifest import backend_manifest_payload
from raes_backend_stubs.manifest import create_stub_manifest
from raes_cli.main import app
from raes_contracts.domain_profiles import (
    DomainProfileBindingBasis,
    DomainProfileBindingModel,
    DomainProfileBindingOwnerModel,
    DomainProfileBindingProvenanceModel,
    DomainProfileBindingUse,
    DomainProfileCoordinateModel,
)
from raes_contracts.planning import ChangeAction, RuntimeDomain
from raes_processor.reconciliation_demonstration import (
    PLANNED_STATE_PROJECTION,
    ReconciliationInputError,
    ReconciliationStatus,
    ScenarioVersion,
    ScenarioVersionRejected,
    planned_state_snapshot,
    reconcile_scenario_versions,
)
from raes_processor.reference import run_reference_processor
from typer.testing import CliRunner

_BASELINE = EXAMPLES_DIR / "reconciliation-demo-v1.sdl.yaml"
_CANDIDATE = EXAMPLES_DIR / "reconciliation-demo-v2.sdl.yaml"


def _manifest_without_switch_support() -> BackendManifest:
    """A manifest that turns the demo's `lab` network into a capability gap."""

    manifest = create_stub_manifest()
    capabilities = manifest.capabilities
    return replace(
        manifest,
        capabilities=replace(
            capabilities,
            provisioner=replace(capabilities.provisioner, supported_node_types=frozenset({"compute"})),
        ),
    )


def _candidate_with_unsupported_operating_system(tmp_path: Path) -> Path:
    """A candidate that plans but carries an error diagnostic.

    The dry-run stub declares no operating-system compatibility rows, so a node
    that pins a distribution and version is a realization gap rather than a
    parse failure.
    """

    source = _CANDIDATE.read_text(encoding="utf-8")
    pinned = source.replace(
        """  cache:
    type: compute
    resources:
""",
        """  cache:
    type: compute
    os: linux
    os_distribution: ubuntu
    os_version: "22.04"
    resources:
""",
    )
    assert pinned != source
    path = tmp_path / "reconciliation-demo-v2-unsupported.sdl.yaml"
    path.write_text(pinned, encoding="utf-8")
    return path


def _profile_binding() -> DomainProfileBindingModel:
    """A minimal typed profile binding for projection-fidelity assertions."""

    return DomainProfileBindingModel(
        binding_id="reconciliation-demo-binding",
        coordinate=DomainProfileCoordinateModel(
            namespace="org.openrae.test",
            authority="https://openrae.org/profiles",
            profile_id="reconciliation-demo",
            revision="1.0.0",
            definition_digest="sha256:" + "0" * 64,
        ),
        owner=DomainProfileBindingOwnerModel(
            owning_contract_id="provisioning-plan/v1",
            canonical_address="#/provisioning/resources",
            concept_family="assets",
            lifecycle_phase="planning",
            context="reconciliation-demonstration",
            use=DomainProfileBindingUse.CONSTRAINT,
        ),
        value={"substrate": "demonstration"},
        provenance=DomainProfileBindingProvenanceModel(
            basis=DomainProfileBindingBasis.AUTHOR_SUPPLIED,
            source_ref="urn:example:reconciliation-demo",
        ),
    )


def _baseline_plan():
    result = run_reference_processor(_BASELINE, create_stub_manifest())
    assert result.is_valid, [diagnostic.code for diagnostic in result.diagnostics]
    return result.execution_plan


def test_projection_covers_every_planned_domain() -> None:
    snapshot = planned_state_snapshot(_baseline_plan())

    domains = {entry.domain for entry in snapshot.entries.values()}
    assert domains == {
        RuntimeDomain.PROVISIONING,
        RuntimeDomain.ORCHESTRATION,
        RuntimeDomain.EVALUATION,
    }
    # Assumed state, not execution evidence: no entry claims it was applied.
    assert {entry.status for entry in snapshot.entries.values()} == {PLANNED_STATE_PROJECTION}


def test_projection_preserves_reconciliation_identity() -> None:
    """Replanning the baseline against its own projection must be a no-op.

    ``_entry_matches_resource`` compares domain, profile bindings, resource
    type, payload, and both dependency sets, so any field the projection drops
    shows up here as a spurious ``update``.
    """

    snapshot = planned_state_snapshot(_baseline_plan())

    replanned = run_reference_processor(_BASELINE, create_stub_manifest(), base_snapshot=snapshot)

    assert replanned.is_valid
    actions = {
        operation.action
        for domain_plan in (
            replanned.execution_plan.provisioning,
            replanned.execution_plan.orchestration,
            replanned.execution_plan.evaluation,
        )
        for operation in domain_plan.operations
    }
    assert actions == {ChangeAction.UNCHANGED}


def test_projection_preserves_dependencies() -> None:
    execution_plan = _baseline_plan()

    snapshot = planned_state_snapshot(execution_plan)

    for domain_plan in (
        execution_plan.provisioning,
        execution_plan.orchestration,
        execution_plan.evaluation,
    ):
        for address, resource in domain_plan.resources.items():
            entry = snapshot.entries[address]
            assert entry.resource_type == resource.resource_type
            assert entry.ordering_dependencies == resource.ordering_dependencies
            assert entry.refresh_dependencies == resource.refresh_dependencies
    # The fixture is only a real oracle for dependencies if it declares some.
    assert any(entry.ordering_dependencies for entry in snapshot.entries.values())
    assert any(entry.refresh_dependencies for entry in snapshot.entries.values())


def test_projection_carries_non_empty_profile_bindings() -> None:
    """Profile bindings are part of reconciliation identity, so they must survive.

    The example pair declares none, so comparing the projection against the
    fixture would still pass if the projection dropped bindings entirely.
    Inject one and prove it is carried, and that an unbound resource does not
    inherit it.
    """

    execution_plan = _baseline_plan()
    address = "provision.node.web"
    binding = _profile_binding()
    bound_resources = dict(execution_plan.provisioning.resources)
    bound_resources[address] = replace(bound_resources[address], profile_bindings=(binding,))
    bound_plan = replace(
        execution_plan,
        provisioning=replace(execution_plan.provisioning, resources=bound_resources),
    )

    snapshot = planned_state_snapshot(bound_plan)

    assert snapshot.entries[address].profile_bindings == (binding,)
    assert snapshot.entries["provision.node.database"].profile_bindings == ()


def test_projection_copies_payloads_away_from_the_plan() -> None:
    execution_plan = _baseline_plan()

    snapshot = planned_state_snapshot(execution_plan)

    address = "provision.node.web"
    entry = snapshot.entries[address]
    assert entry.payload == execution_plan.provisioning.resources[address].payload
    entry.payload["injected"] = "mutation"
    assert "injected" not in execution_plan.provisioning.resources[address].payload


def test_projection_refuses_a_plan_reconciled_against_existing_state() -> None:
    """The adapter drops deletes, which is only sound for an empty baseline."""

    snapshot = planned_state_snapshot(_baseline_plan())
    chained = run_reference_processor(_CANDIDATE, create_stub_manifest(), base_snapshot=snapshot)

    with pytest.raises(ReconciliationInputError):
        planned_state_snapshot(chained.execution_plan)


def _actions(demonstration) -> dict[str, ChangeAction]:
    return {operation.address: operation.action for operation in demonstration.operations}


def test_identical_versions_reconcile_as_unchanged() -> None:
    demonstration = reconcile_scenario_versions(_BASELINE, _BASELINE, create_stub_manifest())

    assert demonstration.status is ReconciliationStatus.RECONCILED
    assert set(demonstration.action_counts) == set(ChangeAction)
    assert demonstration.action_counts[ChangeAction.CREATE] == 0
    assert demonstration.action_counts[ChangeAction.UPDATE] == 0
    assert demonstration.action_counts[ChangeAction.DELETE] == 0
    assert demonstration.action_counts[ChangeAction.UNCHANGED] == len(demonstration.operations)


def test_modified_version_reports_every_action_across_every_domain() -> None:
    demonstration = reconcile_scenario_versions(_BASELINE, _CANDIDATE, create_stub_manifest())

    assert demonstration.status is ReconciliationStatus.RECONCILED
    assert demonstration.baseline_scenario_name == "reconciliation-demo"
    assert demonstration.candidate_scenario_name == "reconciliation-demo"

    actions = _actions(demonstration)
    assert actions["provision.node.cache"] is ChangeAction.CREATE
    assert actions["provision.node.database"] is ChangeAction.UPDATE
    assert actions["provision.node.retired"] is ChangeAction.DELETE
    assert actions["provision.node.web"] is ChangeAction.UNCHANGED
    assert actions["provision.network.lab"] is ChangeAction.UNCHANGED

    counts = demonstration.action_counts
    assert counts[ChangeAction.CREATE] == 1
    assert counts[ChangeAction.DELETE] == 1
    assert sum(counts.values()) == len(demonstration.operations)

    # All three planned domains aggregate into one report.
    assert {operation.domain for operation in demonstration.operations} == {
        RuntimeDomain.PROVISIONING,
        RuntimeDomain.ORCHESTRATION,
        RuntimeDomain.EVALUATION,
    }
    assert {
        operation.domain for operation in demonstration.operations if operation.action is ChangeAction.UNCHANGED
    } == {
        RuntimeDomain.PROVISIONING,
        RuntimeDomain.ORCHESTRATION,
        RuntimeDomain.EVALUATION,
    }


def test_refresh_dependency_updates_a_resource_whose_payload_did_not_change() -> None:
    """The case a payload-diff implementation gets wrong.

    ``evaluation.condition.database.health`` refresh-depends on the database
    node. The node changes, so the condition reconciles as ``update`` even
    though its own payload is byte-identical to the projected baseline entry.
    """

    demonstration = reconcile_scenario_versions(_BASELINE, _CANDIDATE, create_stub_manifest())

    address = "evaluation.condition.database.health"
    assert _actions(demonstration)[address] is ChangeAction.UPDATE

    candidate = run_reference_processor(
        _CANDIDATE, create_stub_manifest(), base_snapshot=demonstration.baseline_snapshot
    )
    replanned = next(
        operation for operation in candidate.execution_plan.evaluation.operations if operation.address == address
    )
    assert replanned.payload == demonstration.baseline_snapshot.entries[address].payload


def test_operations_keep_the_planner_apply_then_delete_ordering() -> None:
    demonstration = reconcile_scenario_versions(_BASELINE, _CANDIDATE, create_stub_manifest())

    provisioning = [
        operation for operation in demonstration.operations if operation.domain is RuntimeDomain.PROVISIONING
    ]
    expected = run_reference_processor(
        _CANDIDATE, create_stub_manifest(), base_snapshot=demonstration.baseline_snapshot
    ).execution_plan.provisioning.operations
    assert [operation.address for operation in provisioning] == [operation.address for operation in expected]


def test_rejected_baseline_stops_before_projecting_or_planning_the_candidate() -> None:
    demonstration = reconcile_scenario_versions(_BASELINE, _CANDIDATE, _manifest_without_switch_support())

    assert demonstration.status is ReconciliationStatus.BASELINE_REJECTED
    # Not "zero changes": nothing was computed at all.
    assert demonstration.operations is None
    assert demonstration.action_counts is None
    assert demonstration.baseline_snapshot is None
    assert demonstration.candidate_scenario_name is None
    assert demonstration.candidate_diagnostics == ()
    assert any(diagnostic.is_error for diagnostic in demonstration.baseline_diagnostics)


def test_rejected_candidate_still_reports_its_operations(tmp_path: Path) -> None:
    demonstration = reconcile_scenario_versions(
        _BASELINE,
        _candidate_with_unsupported_operating_system(tmp_path),
        create_stub_manifest(),
    )

    assert demonstration.status is ReconciliationStatus.CANDIDATE_REJECTED
    assert demonstration.operations
    assert any(diagnostic.is_error for diagnostic in demonstration.candidate_diagnostics)


@pytest.mark.parametrize(
    ("version", "broken_first"),
    [(ScenarioVersion.BASELINE, True), (ScenarioVersion.CANDIDATE, False)],
)
def test_uncompilable_version_is_named_without_leaking_its_content(
    tmp_path: Path, version: ScenarioVersion, broken_first: bool
) -> None:
    broken = tmp_path / "broken.sdl.yaml"
    broken.write_text("name: [unclosed SECRETMARKER\n", encoding="utf-8")
    versions = (broken, _CANDIDATE) if broken_first else (_BASELINE, broken)

    with pytest.raises(ScenarioVersionRejected) as raised:
        reconcile_scenario_versions(*versions, create_stub_manifest())

    assert raised.value.version is version
    assert "SECRETMARKER" not in str(raised.value)


def _invoke(*args: str):
    return CliRunner().invoke(app, ["processor", "reconcile", *args])


def _manifest_file(tmp_path: Path, *, supported_node_types: list[str] | None = None) -> Path:
    payload = backend_manifest_payload(create_stub_manifest())
    if supported_node_types is not None:
        payload["capabilities"]["provisioner"]["supported_node_types"] = supported_node_types
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_reconcile_emits_the_documented_report_for_the_example_pair() -> None:
    result = _invoke(str(_BASELINE), str(_CANDIDATE), "--format", "json")

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert set(payload) == {
        "status",
        "snapshot_kind",
        "baseline",
        "candidate",
        "actions",
        "operations",
    }
    assert payload["status"] == "reconciled"
    assert payload["snapshot_kind"] == PLANNED_STATE_PROJECTION
    assert payload["baseline"]["scenario_name"] == "reconciliation-demo"
    assert payload["candidate"]["scenario_name"] == "reconciliation-demo"

    # All four counts are reported, including the ones that did not occur.
    assert set(payload["actions"]) == {"create", "update", "delete", "unchanged"}
    assert payload["actions"]["create"] == 1
    assert payload["actions"]["delete"] == 1
    assert sum(payload["actions"].values()) == len(payload["operations"])

    actions = {operation["address"]: operation["action"] for operation in payload["operations"]}
    assert actions["provision.node.cache"] == "create"
    assert actions["provision.node.database"] == "update"
    assert actions["evaluation.condition.database.health"] == "update"
    assert actions["provision.node.retired"] == "delete"
    assert actions["provision.node.web"] == "unchanged"

    snapshot = payload["baseline"]["snapshot"]
    assert snapshot["entry_count"] == len(snapshot["entries"])
    web = next(entry for entry in snapshot["entries"] if entry["address"] == "provision.node.web")
    assert web["domain"] == "provisioning"
    assert web["resource_type"] == "node"
    assert "provision.network.lab" in web["ordering_dependencies"]
    assert web["profile_binding_ids"] == []


def test_reconcile_report_carries_no_resource_payloads() -> None:
    result = _invoke(str(_BASELINE), str(_CANDIDATE), "--format", "json")

    assert result.exit_code == 0
    # Authored payload values -- a network CIDR and a condition command -- are
    # reachable from the plan but must not reach the report.
    assert "10.10.0.0/24" not in result.stdout
    assert "/bin/true" not in result.stdout


def test_reconcile_output_is_deterministic() -> None:
    first = _invoke(str(_BASELINE), str(_CANDIDATE), "--format", "json")
    second = _invoke(str(_BASELINE), str(_CANDIDATE), "--format", "json")

    assert first.exit_code == 0
    assert first.stdout == second.stdout


def test_reconcile_identical_versions_report_only_unchanged() -> None:
    result = _invoke(str(_BASELINE), str(_BASELINE), "--format", "json")

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert {operation["action"] for operation in payload["operations"]} == {"unchanged"}
    assert payload["actions"]["create"] == 0
    assert payload["actions"]["update"] == 0
    assert payload["actions"]["delete"] == 0


def test_reconcile_rejected_baseline_reports_no_action_report(tmp_path: Path) -> None:
    manifest = _manifest_file(tmp_path, supported_node_types=["compute"])

    result = _invoke(str(_BASELINE), str(_CANDIDATE), "--manifest", str(manifest), "--format", "json")

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "baseline_rejected"
    # Null, not zeroes: nothing was reconciled, so there is no delta to report.
    assert payload["actions"] is None
    assert payload["operations"] is None
    assert payload["candidate"] is None
    assert payload["baseline"]["snapshot"] is None
    error_codes = {
        diagnostic["code"] for diagnostic in payload["baseline"]["diagnostics"] if diagnostic["severity"] == "error"
    }
    assert "provisioner.unsupported-node-type" in error_codes


def test_reconcile_rejected_candidate_still_reports_operations(tmp_path: Path) -> None:
    candidate = _candidate_with_unsupported_operating_system(tmp_path)

    result = _invoke(str(_BASELINE), str(candidate), "--format", "json")

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "candidate_rejected"
    assert payload["operations"]
    assert any(diagnostic["severity"] == "error" for diagnostic in payload["candidate"]["diagnostics"])


def test_reconcile_invalid_sdl_fails_without_partial_json(tmp_path: Path) -> None:
    bad = tmp_path / "broken.sdl.yaml"
    bad.write_text("name: [unclosed\n", encoding="utf-8")

    result = _invoke(str(bad), str(_CANDIDATE), "--format", "json")

    assert result.exit_code == 1
    assert result.stdout.strip() == ""
    assert "could not compile" in result.stderr
    assert result.stderr.count("\n") <= 1
    assert "Traceback" not in result.stderr


def test_reconcile_invalid_candidate_sdl_is_reported_against_its_own_path(tmp_path: Path) -> None:
    bad = tmp_path / "broken-candidate.sdl.yaml"
    bad.write_text("name: [unclosed\n", encoding="utf-8")

    result = _invoke(str(_BASELINE), str(bad), "--format", "json")

    assert result.exit_code == 1
    assert result.stdout.strip() == ""
    assert "broken-candidate.sdl.yaml" in result.stderr


def test_reconcile_requires_explicit_format() -> None:
    result = _invoke(str(_BASELINE), str(_CANDIDATE))

    assert result.exit_code != 0
