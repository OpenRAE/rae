"""Runner-owned mixed-backend case catalog, selection, probe digests and requested cuts.

Every expectation lives here, next to the case that tests it. The requested
time cuts derive from the admitted time model and the harness's nominal cut,
and the binding variants derive from the installed declaration, never from a
backend answer.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from fractions import Fraction
from math import floor

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import MixedBackendExecutionBindingModel, mixed_backend_time_comparison
from raes_contracts.contracts.time_model import TimeModelDeclarationModel, TimeRuntimeStateModel

from raes_conformance.conformance.mixed_backend_types import MixedBackendCondition, MixedBackendSubject

PROBE_REVISION = "mixed-backend-probes/rev1"
_EDGE = MixedBackendSubject.EDGE
_HANDOFF = MixedBackendSubject.HANDOFF
_CONTROL = MixedBackendSubject.CONTROL
_COMBINATION = MixedBackendSubject.COMBINATION
_Condition = MixedBackendCondition


@dataclass(frozen=True)
class MixedBackendCase:
    """One independently runnable case and the result it must produce to pass."""

    case_id: str
    subject: MixedBackendSubject
    claim: str
    condition: MixedBackendCondition = MixedBackendCondition.NOMINAL
    condition_point: str = "before-submission"
    time_variant: str = "nominal"
    binding_variant: str | None = None
    expected_state: str | None = None


MIXED_BACKEND_CASES: tuple[MixedBackendCase, ...] = (
    MixedBackendCase(
        "edge-executes",
        _EDGE,
        "The admitted edge executes once through its pinned services with separate stage facts.",
        expected_state="succeeded",
    ),
    MixedBackendCase(
        "edge-time-mapped-incomparable",
        _EDGE,
        "A cut whose mapped source passes the destination starts no effect.",
        time_variant="mapped-past-destination",
        expected_state="failed",
    ),
    MixedBackendCase(
        "edge-time-segment-incomparable",
        _EDGE,
        "A cut across clock segments starts no effect.",
        time_variant="destination-new-segment",
        expected_state="failed",
    ),
    MixedBackendCase(
        "edge-unbound-refused",
        _EDGE,
        "An edge without installed portable services refuses before any call.",
        binding_variant="unbound",
    ),
    MixedBackendCase(
        "edge-missing-mapping-refused",
        _EDGE,
        "A binding that names an absent mapping refuses before any call.",
        binding_variant="missing-mapping",
    ),
    MixedBackendCase(
        "edge-reversed-mapping-refused",
        _EDGE,
        "A binding that reverses the bound clocks refuses before any call.",
        binding_variant="reversed-mapping",
    ),
    MixedBackendCase(
        "edge-undeclared-loss-refused",
        _EDGE,
        "A binding that declares another mapping loss refuses before any call.",
        binding_variant="undeclared-loss",
    ),
    MixedBackendCase(
        "edge-refused-before-claim",
        _EDGE,
        "Withdrawn willingness before the claim leaves an audit-only refusal.",
        condition=_Condition.WILLINGNESS_WITHDRAWN,
    ),
    MixedBackendCase(
        "edge-refused-after-time-grant",
        _EDGE,
        "Willingness withdrawn after the grant cancels the operation before the one-use start.",
        condition=_Condition.WILLINGNESS_WITHDRAWN,
        condition_point="after-time-grant",
        expected_state="cancelled",
    ),
    MixedBackendCase(
        "edge-start-refused",
        _EDGE,
        "A refused start keeps the consumed grant unresolved and creates no later stage.",
        condition=_Condition.START_REFUSED,
        expected_state="indeterminate",
    ),
    MixedBackendCase(
        "edge-partial-execution",
        _EDGE,
        "Partial execution stays indeterminate and retains its residual state.",
        condition=_Condition.PARTIAL_EXECUTION,
        expected_state="indeterminate",
    ),
    MixedBackendCase(
        "edge-missing-delivery",
        _EDGE,
        "A missing destination receipt keeps execution and creates no delivery or observation.",
        condition=_Condition.MISSING_DELIVERY,
        expected_state="indeterminate",
    ),
    MixedBackendCase(
        "edge-restart-no-reissue",
        _EDGE,
        "A reopened store returns the original operation and calls no service again.",
        expected_state="succeeded",
    ),
    MixedBackendCase(
        "handoff-commits",
        _HANDOFF,
        "A native transfer commits the next phase only after destination-owner readback.",
        expected_state="succeeded",
    ),
    MixedBackendCase(
        "handoff-stale-transfer",
        _HANDOFF,
        "A stale transfer fails with source-owner readback and keeps the phase.",
        condition=_Condition.STALE_TRANSFER,
        expected_state="failed",
    ),
    MixedBackendCase(
        "handoff-repeated-transition",
        _HANDOFF,
        "Repeated attempts fence on the current cut and never transfer twice.",
        condition=_Condition.STALE_TRANSFER,
        expected_state="succeeded",
    ),
    MixedBackendCase(
        "control-repeated-cycles",
        _CONTROL,
        "Repeated control cycles advance one revision each and the next action dispatches once.",
        expected_state="succeeded",
    ),
    MixedBackendCase(
        "control-dispatch-refused",
        _CONTROL,
        "A backend refusal at the dispatch boundary fails the action without a control change.",
        condition=_Condition.DISPATCH_REFUSED,
        expected_state="failed",
    ),
    MixedBackendCase(
        "combination-reusable-control-with-mixed-runtime",
        _COMBINATION,
        "Reusable control combined with a mixed runtime has no supported path.",
    ),
    MixedBackendCase(
        "combination-distributed-portable-mixed",
        _COMBINATION,
        "A distributed dispatcher combined with portable mixed services has no supported path.",
    ),
)

_CASES = {case.case_id: case for case in MIXED_BACKEND_CASES}


def select_cases(case_ids: Iterable[str] | None) -> tuple[MixedBackendCase, ...]:
    """Return the requested cases in catalog order; refuse an empty or unknown selection."""

    if case_ids is None:
        return MIXED_BACKEND_CASES
    requested = tuple(case_ids)
    unknown = sorted(set(requested) - set(_CASES))
    if unknown:
        raise ValueError("a mixed-backend case selection names an unknown case id")
    if not requested:
        raise ValueError("a mixed-backend conformance run requires at least one case")
    return tuple(case for case in MIXED_BACKEND_CASES if case.case_id in set(requested))


def probe_digest(case: MixedBackendCase) -> str:
    """Digest the case definition under the probe revision."""

    return canonical_json_digest({"revision": PROBE_REVISION, "case": asdict(case)})


def probe_set_digest(cases: Iterable[MixedBackendCase]) -> str:
    """Digest the exact selected case set."""

    return canonical_json_digest({"revision": PROBE_REVISION, "cases": [probe_digest(case) for case in cases]})


def requested_time_state(
    case: MixedBackendCase,
    required: object,
    time_model: TimeModelDeclarationModel,
    nominal: TimeRuntimeStateModel,
) -> tuple[TimeRuntimeStateModel | None, bool]:
    """Return the cut to request and whether it distinguishes the mapping from identity.

    ``mapped-past-destination`` advances the source clock to the first tick
    whose mapped value passes the destination tick. ``destination-new-segment``
    resets the destination clock into the next segment.
    """

    if case.time_variant == "nominal":
        return None, False
    source = nominal.clocks[required.source_clock_address].coordinate
    destination = nominal.clocks[required.destination_clock_address].coordinate
    if case.time_variant == "destination-new-segment":
        reset = {"segment": destination.segment + 1, "tick": 0, "microstep": 0}
        return _appended(nominal, required.destination_clock_address, "reset", reset), False
    mapping = time_model.mappings[required.mapping_ref]
    threshold = (Fraction(destination.tick) - mapping.offset_ticks) * mapping.scale.denominator
    tick = max(source.tick + 1, floor(threshold / mapping.scale.numerator) + 1)
    advanced = {"segment": source.segment, "tick": tick, "microstep": 0}
    return _appended(nominal, required.source_clock_address, "advance", advanced), tick <= destination.tick


def cut_comparison(required: object, time_model: TimeModelDeclarationModel, state: TimeRuntimeStateModel) -> str:
    """Return the comparison that the admitted mapping proves for a committed cut."""

    return mixed_backend_time_comparison(
        required,
        time_model,
        state.clocks[required.source_clock_address].coordinate,
        state.clocks[required.destination_clock_address].coordinate,
    )


def _appended(
    state: TimeRuntimeStateModel,
    address: str,
    kind: str,
    coordinate: dict[str, int],
) -> TimeRuntimeStateModel:
    """Append one admitted clock transition, so the requested cut keeps a valid history."""

    payload = state.model_dump(mode="json")
    clock = payload["clocks"][address]
    last = clock["history"][-1]
    event = {
        "sequence": last["sequence"] + 1,
        "kind": kind,
        "previous": last["resulting"],
        "resulting": coordinate,
        "resulting_state": last["resulting_state"],
    }
    clock["history"].append(event)
    clock.update(coordinate=coordinate, sequence=event["sequence"], state=event["resulting_state"])
    return TimeRuntimeStateModel.model_validate(payload)


def binding_variant(
    case: MixedBackendCase,
    declaration: MixedBackendExecutionBindingModel,
) -> MixedBackendExecutionBindingModel | None:
    """Return the contradictory declaration for a binding-variant case, else ``None``."""

    if case.binding_variant in {None, "unbound"}:
        return None
    payload = declaration.model_dump(mode="json")
    subject = payload["subject"]
    if case.binding_variant == "missing-mapping":
        subject["time"]["mapping_ref"] = "time.mappings.x-conformance-absent"
    elif case.binding_variant == "reversed-mapping":
        time = subject["time"]
        time["source_clock_address"], time["destination_clock_address"] = (
            time["destination_clock_address"],
            time["source_clock_address"],
        )
    else:
        subject["mapping_loss"]["limitation_ref"] = "limitation:x-conformance-undeclared"
    return MixedBackendExecutionBindingModel.model_validate(payload)


__all__ = [
    "MIXED_BACKEND_CASES",
    "PROBE_REVISION",
    "MixedBackendCase",
    "binding_variant",
    "cut_comparison",
    "probe_digest",
    "probe_set_digest",
    "requested_time_state",
    "select_cases",
]
