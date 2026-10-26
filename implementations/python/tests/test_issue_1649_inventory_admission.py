"""Invalid descendant reports never replace the trusted predecessor."""

from copy import deepcopy

import pytest
from runtime_descendant_fixtures import descendant_runtime


@pytest.mark.parametrize(
    "mutation",
    [
        "attempt",
        "target",
        "predecessor",
        "run",
        "sequence",
        "duplicate",
        "native-duplicate",
        "replacement",
        "parent",
        "source",
        "cycle",
        "missing-evidence",
        "foreign-evidence",
        "incomplete",
        "unavailable",
        "omission",
        "over-limit",
        "missing-report",
    ],
)
def test_invalid_refresh_preserves_snapshot_lineage_and_provenance(tmp_path, mutation):
    manager, backend, plan, _target, _archive = descendant_runtime(tmp_path)
    assert manager.apply(plan).success
    predecessor = deepcopy(manager.snapshot)

    def mutate(document):
        provenance = document["materialization_provenance"]
        inventory = provenance["inventory"]
        first = inventory["descendants"][0]
        if mutation == "attempt":
            inventory["attempt_id"] = "foreign-attempt"
        elif mutation == "target":
            inventory["target_scope"] = "target:foreign"
        elif mutation == "predecessor":
            provenance["predecessor_digest"] = "sha256:" + "0" * 64
        elif mutation == "run":
            inventory["run_id"] = "foreign-run"
        elif mutation == "sequence":
            inventory["sequence"] = 1
        elif mutation == "duplicate":
            inventory["descendants"].append(deepcopy(first))
        elif mutation == "native-duplicate":
            inventory["descendants"][1]["native_identity_digest"] = first["native_identity_digest"]
        elif mutation == "replacement":
            first["native_identity_digest"] = "sha256:" + "a" * 64
        elif mutation == "parent":
            first["parent_address"] = "provision.node.missing"
        elif mutation == "source":
            first["source_address"] = "provision.node.foreign"
        elif mutation == "cycle":
            first["parent_address"] = "provision.node.leaf"
        elif mutation == "missing-evidence":
            first.pop("creation")
        elif mutation == "foreign-evidence":
            first["creation"]["run_id"] = "foreign-run"
        elif mutation == "incomplete":
            inventory["complete"] = False
        elif mutation == "unavailable":
            inventory["unavailable_evidence"] = ["sha256:" + "f" * 64]
        elif mutation == "omission":
            inventory["descendants"].clear()
        elif mutation == "over-limit":
            inventory["descendants"] *= 2049
        elif mutation == "missing-report":
            provenance.pop("inventory")

    backend.mutate = mutate
    result = manager.refresh_inventory(plan)
    assert not result.success
    assert result.snapshot == predecessor
    assert manager.snapshot == predecessor
    assert result.changed_addresses == []
    assert result.details == {}
    assert result.materialization_attestation is None
    if mutation in {"attempt", "predecessor"}:
        assert any(diagnostic.code == "runtime.inventory-binding-invalid" for diagnostic in result.diagnostics)
    if mutation in {"incomplete", "unavailable", "omission"}:
        assert any(diagnostic.code == "runtime.inventory-coverage-invalid" for diagnostic in result.diagnostics)
    manager.close()


def test_termination_retains_inventory_and_autoremove_retains_tombstones(tmp_path):
    manager, backend, plan, _target, _archive = descendant_runtime(tmp_path)
    assert manager.apply(plan).success
    backend.states["leaf"] = "terminated"
    terminated = manager.refresh_inventory(plan)
    assert terminated.success, terminated.diagnostics
    assert terminated.snapshot.entries["provision.node.leaf"].status == "terminated"
    backend.states["leaf"] = "autoremoved"
    removed = manager.refresh_inventory(plan)
    assert removed.success, removed.diagnostics
    assert "provision.node.leaf" not in removed.snapshot.entries
    inventory = removed.snapshot.materialization_attestations[-1].inventory
    assert any(
        entry.address == "provision.node.leaf" and entry.state == "autoremoved" for entry in inventory.descendants
    )
    assert manager.refresh_inventory(plan).success
    manager.close()


def test_refresh_cannot_publish_credential_details_or_diagnostic_values():
    from raes_contracts.diagnostics import Diagnostic
    from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
    from raes_runtime.backend_inventory import admit_refresh_proposal
    from test_issue_673_account_credential_bindings import _credential_plan

    predecessor = RuntimeSnapshot()
    raw = ApplyResult(True, predecessor, details={"credential": "private-fixture"})
    rejected = admit_refresh_proposal(raw, predecessor, _credential_plan())
    assert not rejected.success
    assert rejected.details == {}
    safe = admit_refresh_proposal(
        ApplyResult(
            True,
            predecessor,
            diagnostics=[
                Diagnostic(
                    code="backend.warning",
                    domain="runtime",
                    address="runtime.inventory",
                    message="private-fixture",
                )
            ],
        ),
        predecessor,
        _credential_plan(),
    )
    assert all("private-fixture" not in diagnostic.message for diagnostic in safe.diagnostics)


@pytest.mark.parametrize("permission", ["open", "closed"])
def test_initial_inventory_preserves_prospective_augmentation_permission(tmp_path, permission):
    manager, backend, plan, _target, _archive = descendant_runtime(tmp_path, augmentation={"default": permission})
    result = manager.apply(plan)
    assert result.success is (permission == "open"), result.diagnostics
    assert backend.applies == int(permission == "open")
    if permission == "closed":
        assert not manager.snapshot.entries
    else:
        backend.members["later"] = "provision.node.leaf"
        assert manager.refresh_inventory(plan).success
    manager.close()


def test_autoremoved_causal_parent_does_not_remove_a_surviving_child(tmp_path):
    manager, backend, plan, _target, _archive = descendant_runtime(tmp_path)
    assert manager.apply(plan).success
    backend.states["worker"] = "autoremoved"
    result = manager.refresh_inventory(plan)
    assert result.success, result.diagnostics
    assert "provision.node.worker" not in result.snapshot.entries
    assert "provision.node.leaf" in result.snapshot.entries
    assert any(
        entry.address == "provision.node.worker" and entry.state == "autoremoved"
        for entry in result.snapshot.materialization_attestations[-1].inventory.descendants
    )
    manager.close()
