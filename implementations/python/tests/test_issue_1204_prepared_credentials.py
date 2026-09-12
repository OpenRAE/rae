"""Preparation and credential egress compose without broadening either grant."""

from copy import deepcopy
from dataclasses import replace

import pytest
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
from test_issue_673_account_credential_bindings import FIXTURE_SENTINEL, OPERATOR_REFERENCE, _credential_plan
from test_issue_1204_backend_preparation import _PreparingBackend, _request


@pytest.mark.parametrize("leak", [False, True])
def test_prepared_completion_is_sanitized_under_its_selected_values(leak):
    from raes_contracts.runtime_state import RealizationObservationDisclosure

    request, manifest = _request()
    account = _credential_plan().operations[0]
    account = replace(
        account, payload={**account.payload, "node_name": "host", "target_address": "provision.node.host"}
    )
    request = replace(request, operations=[*request.operations, account])

    class Backend(_PreparingBackend):
        def apply(self, plan, snapshot):
            self.applies += 1
            entries = {
                op.address: SnapshotEntry(
                    op.address,
                    RuntimeDomain.PROVISIONING,
                    op.resource_type,
                    deepcopy(op.payload),
                    status="applied",
                    ordering_dependencies=op.ordering_dependencies,
                    refresh_dependencies=op.refresh_dependencies,
                )
                for op in plan.operations
            }
            return ApplyResult(
                True,
                snapshot.with_entries(
                    entries,
                    realization_envelope=plan.realization_envelope,
                    realization_observations=tuple(
                        RealizationObservationDisclosure(
                            address=a.address,
                            field_path=a.field_path,
                            domain=a.domain,
                            requirement_kind=a.requirement_kind,
                            verification_scope=a.verification_scope,
                            observation_strength=a.required_observation_strength,
                        )
                        for a in plan.realization_authority
                        if a.required_observation_strength is not None
                        and a.requirement_kind == "runtime-database-services"
                    ),
                ),
                changed_addresses=list(entries),
                details={"leak": FIXTURE_SENTINEL} if leak else {},
            )

    backend = Backend()
    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        backend.apply,
        request,
        previous,
        address="runtime.prepared-credentials",
        snapshot=previous,
        realization=_RealizationApplyContext(plan=request, manifest=manifest),
    )
    assert backend.applies == 1, result.diagnostics
    assert result.success is not leak, result.diagnostics
    assert FIXTURE_SENTINEL not in repr(result)
    assert OPERATOR_REFERENCE not in repr(result)
    if leak:
        assert result.snapshot == previous
        assert (
            result.diagnostics[0].message == "Backend returned credential material outside its canonical material node."
        )
    else:
        assert (
            result.snapshot.entries["provision.node.host"].payload["spec"]["node"]["runtime"]["database_services"][0][
                "engine"
            ]
            == "sqlite"
        )
