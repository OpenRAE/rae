"""Read-only instrumentation around public runtime calls for issue 972.

Only this test driver patches call sites. All original admission, policy,
provider, backend, and transaction functions still execute.
"""

from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch

from implementations.formal.participant_crossing.runtime_mapping import Binding, Commit, Event, Observation
from participant_crossing_fixtures import AUDIENCE, CONTROLLER, PARTICIPANT, crossing_request
from raes_contracts.errors import (
    AuthorizationError,
    ConflictError,
    EvidenceIntegrityError,
    InvalidInputError,
    NotFoundError,
    OperationalError,
)
from raes_runtime import participant_crossing_mediation as mediation
from raes_runtime import participant_crossing_policy as policy
from raes_runtime import participant_crossing_records as records
from raes_runtime.control_plane_profiles import store_capabilities
from raes_runtime.control_plane_store import InMemoryControlPlaneStore, LocalControlPlaneStore


def crossing_binding(**overrides):
    cut = crossing_request()["occurrence"]["policy"]["decision_cut_ref"]
    return Binding(
        **dict(
            participant=PARTICIPANT,
            episode="episode-1",
            audience=AUDIENCE,
            controller=CONTROLLER,
            principal="operator.red",
            target="stub",
            policy_cuts=(cut, cut + ".p1"),
        )
        | overrides
    )


def capture_call(
    plane, call, binding, *, input_class, cut="p0", entry_point="admit_participant_action", policy_advance=None
):
    store = getattr(plane._store, "raw_store", plane._store)
    before = deepcopy(store.load_snapshot())
    before_revision = store.load_snapshot_state().revision
    before_policy_cut = plane._crossing_policy_resolver.policy.decision_cut_ref
    records_before = deepcopy(store.load_records())
    audit_before = tuple(deepcopy(store.read_audit()))
    events, intents, commits = [], [], []
    backend_calls = 0
    effective_levels = []
    if policy_advance is not None:
        previous_cut = plane._crossing_policy_resolver.policy.decision_cut_ref
        policy_advance()
        current_cut = plane._crossing_policy_resolver.policy.decision_cut_ref
        if (previous_cut, current_cut) != binding.policy_cuts or store.load_snapshot() != before:
            raise ValueError("invalid observed policy environment step")
        events.append(Event("policy.cut.advance", {"cut": "p1"}))

    def identity(original, *args, **kwargs):
        intent = args[1]
        intents.append(intent)
        events.append(Event("crossing.request"))
        result = original(*args, **kwargs)
        events.append(Event("internal.validate"))
        return result

    def resolved_policy(original, *args, **kwargs):
        prior_revision = store.load_snapshot_state().revision
        result = original(*args, **kwargs)
        if store.load_snapshot_state().revision != prior_revision:
            events.append(Event("runtime.state-cut.changed"))
        resolved_cut = result.policy.decision_cut_ref
        events.append(
            Event(
                "internal.resolve-policy-cut",
                {
                    "cut": "p0"
                    if resolved_cut == binding.policy_cuts[0]
                    else "p1"
                    if resolved_cut == binding.policy_cuts[1]
                    else "unmapped"
                },
            )
        )
        return result

    def gates(original, *args, **kwargs):
        result = original(*args, **kwargs)
        values = result.model_dump(mode="json")
        facts = {"gates": dict(values), "effective_levels": list(effective_levels)}
        support = values.pop("backend_support")
        events.append(
            Event(
                "internal.resolve-capability",
                {
                    "capability": "supported" if support == "permit" else "unsupported",
                    "gate": "deny" if "deny" in values.values() else "permit",
                },
                facts,
            )
        )
        return result

    def support(original, *args, **kwargs):
        nonlocal effective_levels
        result = original(*args, **kwargs)
        effective_levels = [list(item) for item in result.effective_levels]
        return result

    def decision(original, *args, **kwargs):
        result = original(*args, **kwargs)
        disposition = result.value
        if disposition == "transform":
            operation = args[1].required_operation.value
            disposition = "declassify" if operation == "declassification" else "transform"
        label = disposition if disposition in {"deny", "unsupported"} else "permit"
        events.append(Event("crossing.decision." + label, {"decision": disposition}))
        return result

    def transformed(original, *args, **kwargs):
        result = original(*args, **kwargs)
        label = "declassify" if result.occurrence.operation.value == "declassification" else "transform"
        events.append(Event("crossing." + label))
        return result

    def transformed_intent(original, *args, **kwargs):
        result = original(*args, **kwargs)
        intents.append(result)
        events.append(Event("crossing.request"))
        return result

    def prepared(original, *args, **kwargs):
        result = original(*args, **kwargs)
        events.append(Event("internal.prepare-record"))
        return result

    def committed(original, *args, **kwargs):
        previous_state = deepcopy(store.load_snapshot_state())
        previous = previous_state.snapshot.participant_crossing_history
        previous_audit = tuple(deepcopy(store.read_audit()))
        previous_record = deepcopy(store.load_records().get(kwargs["record"].receipt.operation_id))
        expected_snapshot = deepcopy(kwargs["snapshot"])
        expected_record = deepcopy(kwargs["record"])
        expected_audit = deepcopy(kwargs["audit_event"])
        try:
            return original(*args, **kwargs)
        finally:
            snapshot = deepcopy(store.load_snapshot())
            record = store.load_records().get(kwargs["record"].receipt.operation_id)
            current_state = store.load_snapshot_state()
            if record is not None and (current_state != previous_state or record != previous_record):
                commits.append(
                    Commit(
                        snapshot,
                        deepcopy(record),
                        tuple(store.read_audit()),
                        expected_snapshot,
                        expected_record,
                        expected_audit,
                        kwargs["expected_revision"],
                        current_state.revision,
                        deepcopy(store.load_records()),
                        previous_audit,
                    )
                )
            if snapshot.participant_crossing_history != previous and record is not None:
                events.append(
                    Event(
                        "internal.atomic-commit",
                        {"head": "h1"},
                        {
                            "operation_state": record.status.state.value,
                            "crossing_rows": len(snapshot.participant_crossing_history.get(binding.participant, []))
                            - len(previous.get(binding.participant, [])),
                        },
                    )
                )
                prior_rows = previous.get(binding.participant, [])
                for row in snapshot.participant_crossing_history.get(binding.participant, [])[len(prior_rows) :]:
                    stage = row["occurrence"]["stage"]
                    if stage in {"delivered", "observed"}:
                        events.append(Event("crossing.delivery" if stage == "delivered" else "crossing.observation"))

    def backend(original, *args, **kwargs):
        nonlocal backend_calls
        backend_calls += 1
        return original(*args, **kwargs)

    def install(stack, module, name, observer):
        original = getattr(module, name)

        def wrapped(*args, **kwargs):
            return observer(original, *args, **kwargs)

        stack.enter_context(patch.object(module, name, wrapped))

    refusals = (
        AuthorizationError,
        ConflictError,
        EvidenceIntegrityError,
        InvalidInputError,
        NotFoundError,
        OperationalError,
        PermissionError,
        ValueError,
        TypeError,
        OSError,
        RuntimeError,
    )
    result, error_type = None, None
    with ExitStack() as stack:
        install(stack, policy, "_require_crossing_identity", identity)
        install(stack, mediation, "_resolve_crossing_policy", resolved_policy)
        for module in (policy, records):
            install(stack, module, "_resolve_backend_support", support)
            install(stack, module, "_decision_gates", gates)
            install(stack, module, "_decision_disposition", decision)
        install(stack, records, "_transformation_record", transformed)
        install(stack, records, "_fresh_transformed_intent", transformed_intent)
        install(stack, records, "_prepare_crossing_decision", prepared)
        install(stack, store, "commit_participant_transition", committed)
        runtime = plane._target.participant_runtime
        if runtime is not None:
            install(stack, runtime, "admit_action", backend)
        try:
            result = call()
        except refusals as exc:
            error_type = next(kind.__name__ for kind in refusals if isinstance(exc, kind))
    after = deepcopy(store.load_snapshot())
    context = plane._crossing_policy_resolver.validation_context(after, binding.participant)
    return Observation(
        binding=binding,
        input_class=input_class,
        events=tuple(replace(event, ordinal=index) for index, event in enumerate(events)),
        intents=tuple(intents),
        before=before,
        after=after,
        records_before=records_before,
        records_after=deepcopy(store.load_records()),
        audit=tuple(store.read_audit()),
        commits=tuple(commits),
        context=context,
        result=result,
        error_type=error_type,
        backend_calls=backend_calls,
        cut=cut,
        entry_point=entry_point,
        final_sink=plane._enforce_final_sink_flow_control,
        configuration={
            "operating_profile": plane.profile_declaration.profile.value
            if plane.profile_declaration is not None
            else None,
            "store_capabilities": sorted(item.value for item in store_capabilities(store)),
            "store": "local"
            if isinstance(store, LocalControlPlaneStore)
            else "memory"
            if isinstance(store, InMemoryControlPlaneStore)
            else "unsupported",
            "control_providers_selected": plane._participant_control is not None,
            "declared_support": [
                [entry.feature, entry.support_level.value]
                for entry in plane._target.manifest.participant_runtime.feature_support
            ],
        },
        before_revision=before_revision,
        after_revision=store.load_snapshot_state().revision,
        before_policy_cut=before_policy_cut,
        witness_count=len(events),
        audit_before=audit_before,
    )
