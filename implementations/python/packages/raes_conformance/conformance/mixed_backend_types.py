"""Mixed-backend capability probe vocabulary (issue #1017).

The declarative half of the probe family: the probe request, the conditions a
harness realizes, the fresh configurations it returns, the harness protocol and
the report coordinates. A harness contributes trusted inputs and realizes
backend conditions. It contributes no expected outcome, stage fact, digest or
verdict: the runner derives each of those from what the shared runtime retains.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pydantic_core import to_jsonable_python
from raes_contracts.contracts.time_model import TimeRuntimeStateModel
from raes_runtime.registry import RuntimeTarget

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class MixedBackendSubject(StrEnum):
    """The obligation family one case probes."""

    EDGE = "edge"
    HANDOFF = "handoff"
    CONTROL = "control"
    COMBINATION = "combination"


class MixedBackendCondition(StrEnum):
    """A backend condition that the harness realizes in the backend it installed."""

    NOMINAL = "nominal"
    WILLINGNESS_WITHDRAWN = "willingness-withdrawn"
    START_REFUSED = "start-refused"
    PARTIAL_EXECUTION = "partial-execution"
    MISSING_DELIVERY = "missing-delivery"
    STALE_TRANSFER = "stale-transfer"
    DISPATCH_REFUSED = "dispatch-refused"


@dataclass(frozen=True)
class MixedBackendProbeRequest:
    """One runner request for fresh configuration.

    ``collection_id`` is a fresh runner nonce. ``time_state`` is the committed
    time cut the harness must realize, or ``None`` for its nominal cut.
    ``restart_of`` names an earlier collection whose durable store the new
    configuration must reopen with fresh services.
    """

    case_id: str
    subject: MixedBackendSubject
    collection_id: str
    time_state: TimeRuntimeStateModel | None = None
    restart_of: str | None = None


@dataclass(frozen=True)
class MixedCompositionProbeConfiguration:
    """Fresh trusted inputs for one edge or handoff case.

    ``binding`` is the embedder's ``MixedRuntimeBinding`` with installed
    portable services, ``store`` is the selected control-plane store seeded
    with the committed cut, and ``obligation_id`` names the probed edge or
    transition. ``apply_condition`` realizes a condition in the backend and
    returns ``False`` when the backend cannot realize it.
    """

    binding: object
    target: RuntimeTarget
    crossing_policy_resolver: object
    store: object
    identity: object
    obligation_id: str
    apply_condition: Callable[[MixedBackendCondition], bool]
    participant_address: str | None = None
    episode_id: str | None = None
    behavior: object | None = None
    admission_request: object | None = None
    crossing_evidence: object | None = None
    supervision: object | None = None
    distributed_execution: object | None = None


@dataclass(frozen=True)
class MixedControlProbeConfiguration:
    """Fresh trusted inputs for one reusable-control case on one target.

    ``control_intent(transition_id, revision=, head=, order=, key=)`` builds an
    intent for an admitted policy transition at the coordinates the runner
    chooses. ``actor_identity`` holds the single controller binding that a
    governed participant action requires.
    """

    target: RuntimeTarget
    behavior_specifications: Mapping[str, object]
    mixed_control: object
    store: object
    identity: object
    actor_identity: object
    participant_address: str
    episode_id: str
    take_transition: str
    return_transition: str
    control_intent: Callable[..., object]
    behavior: object
    admission_request: object
    apply_condition: Callable[[MixedBackendCondition], bool]
    crossing_policy_resolver: object | None = None
    crossing_evidence: object | None = None


class MixedBackendProbeHarness(Protocol):
    """Trusted in-process embedder adapter used by the generic runner."""

    environment_digest: str

    def composition(self, request: MixedBackendProbeRequest) -> MixedCompositionProbeConfiguration | None: ...

    def control(self, request: MixedBackendProbeRequest) -> MixedControlProbeConfiguration | None: ...


@dataclass(frozen=True)
class MixedComponentCoordinate:
    """Exact backend, manifest, envelope and configuration identity of one component."""

    component_id: str
    target_name: str
    backend_name: str
    backend_version: str
    manifest_digest: str
    envelope_id: str | None = None
    envelope_digest: str | None = None
    configuration_digest: str | None = None


@dataclass(frozen=True)
class MixedServiceCoordinate:
    """One pinned service role of the probed obligation."""

    role: str
    service_ref: str
    version: str
    digest: str


@dataclass(frozen=True)
class MixedEvidenceRecord:
    """One retained fact and the producer that the runtime attributed it to."""

    position: int
    kind: str
    producer_ref: str
    digest: str
    status: str | None = None
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class MixedBackendCaseBinding:
    """Resolvable coordinates of one mixed-backend case, beside the case result."""

    subject: str
    condition: str
    obligation_ref: str | None = None
    profile_id: str | None = None
    profile_revision: str | None = None
    profile_digest: str | None = None
    plan_id: str | None = None
    plan_entry_id: str | None = None
    run_id: str | None = None
    binding_id: str | None = None
    binding_digest: str | None = None
    time_model_ref: str | None = None
    time_model_digest: str | None = None
    source_clock: str | None = None
    destination_clock: str | None = None
    mapping_ref: str | None = None
    ordering_basis: str | None = None
    temporal_coupling: str | None = None
    mapping_loss_ref: str | None = None
    expected_state: str | None = None
    observed_state: str | None = None
    control_policies: tuple[str, ...] = ()
    components: tuple[MixedComponentCoordinate, ...] = ()
    services: tuple[MixedServiceCoordinate, ...] = ()
    evidence: tuple[MixedEvidenceRecord, ...] = ()


def mixed_case_binding_payload(binding: MixedBackendCaseBinding | None) -> dict[str, object] | None:
    """Project mixed coordinates into the one report family."""

    if binding is None:
        return None
    return to_jsonable_python(binding)


def require_environment_digest(value: object) -> str:
    """Return a harness environment digest, or refuse a malformed one."""

    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError("mixed probe harness environment digest must be a sha256 digest")
    return value


__all__ = [
    "MixedBackendCaseBinding",
    "MixedBackendCondition",
    "MixedBackendProbeHarness",
    "MixedBackendProbeRequest",
    "MixedBackendSubject",
    "MixedComponentCoordinate",
    "MixedCompositionProbeConfiguration",
    "MixedControlProbeConfiguration",
    "MixedEvidenceRecord",
    "MixedServiceCoordinate",
    "mixed_case_binding_payload",
    "require_environment_digest",
]
