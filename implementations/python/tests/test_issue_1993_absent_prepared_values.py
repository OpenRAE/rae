"""An absent prepared value carries no delivery obligation (issue #1993)."""

from copy import deepcopy
from dataclasses import replace

import pytest
from raes_backend_stubs.stubs import StubProvisioner
from raes_contracts.contracts.realization_preparation import RealizationPreparation
from raes_contracts.planning import (
    ChangeAction,
    ProvisioningPlan,
    ProvisionOp,
    RealizationAuthorityMode,
    RealizationResolutionSource,
    ResolvedRealizationAuthority,
    RuntimeDomain,
)
from raes_contracts.realization_observation import RealizationObservationDisclosure
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
from raes_contracts.vocabulary import ObservationStrength, RealizationSupportMode
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan, prepared_delivery_violation
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
from test_sem_218_realization_designation import _manifest, _scenario

_ADDRESS = "provision.node.web"
_DELIVERY_FAILURE = "Backend did not deliver its admitted realization completion."
_ABSENT = object()
_ENTRYPOINT = ("runtime-container-entrypoint", ("spec", "node", "runtime", "container", "entrypoint"))
_PUBLISH_ALL = ("runtime-container-publish-all-ports", ("spec", "node", "runtime", "container", "publish_all_ports"))
_ARCHITECTURE = ("node-architecture", ("architecture",))


def _payload(path: tuple[str, ...], value: object) -> dict:
    payload: dict = {}
    current = payload
    for token in path[:-1]:
        current = current.setdefault(token, {})
    if value is not _ABSENT:
        current[path[-1]] = value
    return payload


def _completion(concern: tuple[str, tuple[str, ...]], value: object) -> ProvisioningPlan:
    kind, path = concern
    return ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE, address=_ADDRESS, resource_type="node", payload=_payload(path, value)
            )
        ],
        realization_authority=(
            ResolvedRealizationAuthority(
                address=_ADDRESS,
                field_path=f"nodes.web.{kind}",
                domain="runtime-realization",
                requirement_kind=kind,
                payload_pointer="/" + "/".join(path),
                mode=RealizationAuthorityMode.OPEN,
                source=RealizationResolutionSource.AUTHORED_SCOPE,
            ),
        ),
    )


def _delivered(concern: tuple[str, tuple[str, ...]], value: object) -> RuntimeSnapshot:
    entry = SnapshotEntry(
        address=_ADDRESS,
        domain=RuntimeDomain.PROVISIONING,
        resource_type="node",
        payload=_payload(concern[1], value),
    )
    return RuntimeSnapshot(entries={_ADDRESS: entry})


def _violation(concern, selected, delivered):
    return prepared_delivery_violation(_completion(concern, selected), _delivered(concern, delivered))


@pytest.mark.parametrize(
    ("concern", "delivered"),
    [
        (_ENTRYPOINT, _ABSENT),
        (_ENTRYPOINT, ["/srv/app"]),
        (_ENTRYPOINT, []),
        (_PUBLISH_ALL, True),
        (_ARCHITECTURE, "x86_64"),
    ],
)
def test_absent_completion_value_carries_no_delivery_obligation(concern, delivered):
    assert _violation(concern, _ABSENT, delivered) is None


@pytest.mark.parametrize(
    ("concern", "selected", "delivered"),
    [
        (_ENTRYPOINT, ["/srv/app"], ["/srv/other"]),
        (_ENTRYPOINT, ["/srv/app"], _ABSENT),
        (_ENTRYPOINT, ["/srv/app", "--serve"], ["--serve", "/srv/app"]),
        (_ENTRYPOINT, [], ["/srv/app"]),
        (_ENTRYPOINT, [], _ABSENT),
        (_PUBLISH_ALL, False, True),
        (_ARCHITECTURE, None, "x86_64"),
    ],
)
def test_present_completion_value_stays_an_exact_obligation(concern, selected, delivered):
    assert _violation(concern, selected, delivered) == _DELIVERY_FAILURE


@pytest.mark.parametrize(
    ("concern", "value"),
    [(_ENTRYPOINT, ["/srv/app"]), (_ENTRYPOINT, []), (_PUBLISH_ALL, False), (_ARCHITECTURE, None)],
)
def test_delivered_present_completion_value_passes(concern, value):
    assert _violation(concern, value, deepcopy(value)) is None


def _open_request():
    manifest = _manifest(RealizationSupportMode.OPEN_REALIZATION)
    manifest = replace(
        manifest,
        supported_contract_versions=manifest.supported_contract_versions | {"backend-realization-preparation-v1"},
    )
    scenario = _scenario("realization:\n  default: open")
    scenario = scenario.model_copy(update={"nodes": {"web": scenario.nodes["web"]}})
    execution = plan(compile_runtime_model(scenario), manifest)
    assert execution.is_valid, execution.diagnostics
    return execution.provisioning, manifest


class _BackendSelectingAtApply:
    """Prepare keeps every open field absent; apply selects the entrypoint."""

    def __init__(self, entrypoint):
        self.entrypoint = entrypoint

    def prepare(self, request, snapshot):
        return RealizationPreparation.for_request(request, snapshot, operations=tuple(deepcopy(request.operations)))

    def validate(self, selected):
        return []

    def apply(self, selected, snapshot):
        result = StubProvisioner().apply(selected, snapshot)
        entries = dict(result.snapshot.entries)
        payload = deepcopy(entries[_ADDRESS].payload)
        node = payload["spec"]["node"]
        runtime = node["runtime"] = node.get("runtime") or {}
        container = runtime["container"] = runtime.get("container") or {}
        container["entrypoint"] = self.entrypoint
        entries[_ADDRESS] = replace(entries[_ADDRESS], payload=payload)
        observations = tuple(
            RealizationObservationDisclosure(
                address=authority.address,
                field_path=authority.field_path,
                domain=authority.domain,
                requirement_kind=authority.requirement_kind,
                verification_scope=authority.verification_scope,
                observation_strength=authority.required_observation_strength or ObservationStrength.GUEST_OBSERVED,
            )
            for authority in selected.realization_authority
            if authority.requirement_kind == _ENTRYPOINT[0]
        )
        return replace(
            result,
            snapshot=result.snapshot.with_entries(
                entries,
                realization_envelope=selected.realization_envelope,
                realization_observations=observations,
            ),
        )


def _apply(entrypoint):
    request, manifest = _open_request()
    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        _BackendSelectingAtApply(entrypoint).apply,
        request,
        previous,
        snapshot=previous,
        address="runtime.test.absent-prepared-values",
        realization=_RealizationApplyContext(plan=request, manifest=manifest),
    )
    return previous, result


def test_runtime_accepts_a_value_selected_at_apply_for_an_absent_completion_field():
    _previous, result = _apply(["/srv/app"])
    assert result.success, result.diagnostics
    assert result.snapshot.entries[_ADDRESS].payload["spec"]["node"]["runtime"]["container"]["entrypoint"] == [
        "/srv/app"
    ]


def test_realization_gate_still_checks_a_value_at_an_absent_completion_field():
    previous, result = _apply("not-an-ordered-array")
    assert not result.success
    assert result.snapshot == previous
    diagnostic = result.diagnostics[0]
    assert (diagnostic.code, diagnostic.domain) == ("runtime.backend-contract-invalid", "runtime-realization")
    assert _ENTRYPOINT[0] in diagnostic.message
