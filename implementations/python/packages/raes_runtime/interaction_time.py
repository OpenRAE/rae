"""Compose one shared-clock transition before its atomic snapshot commit."""

from dataclasses import replace

from raes_contracts.contracts.time_model import validate_time_runtime_state
from raes_contracts.participant_autonomous_state import require_participant_autonomous_runtime_snapshot
from raes_contracts.runtime_state import ApplyResult

from .diagnostics import _failure_diagnostic
from .interaction_results import validated_composition_result


def finalize_time_result(owner, result, predecessor, *, declaration, method, clock_address=None):
    if not result.success:
        return result
    try:
        if result.snapshot.time_model_state is None:
            raise ValueError("shared-time state is missing")
        validate_time_runtime_state(declaration, result.snapshot.time_model_state)
    except ValueError:
        return ApplyResult(
            False,
            predecessor,
            diagnostics=[
                _failure_diagnostic(
                    "runtime.time-readback-invalid",
                    f"runtime.time.{method}",
                    "Time runtime returned state that disagrees with the admitted shared-time model.",
                )
            ],
        )
    scheduler = owner._participant_scheduler
    synced = None
    if scheduler is not None and method == "reset":
        synced = scheduler.reset_clock(
            owner._participant_execution_policies,
            owner._participant_execution_time_model,
            owner._target.participant_runtime,
            result.snapshot,
            clock_address,
            reset_participants=False,
            activity_controls=owner._participant_activity_controls,
        )
    elif scheduler is not None and method in {"pause", "resume"}:
        synced = scheduler.set_clock_lifecycle(
            result.snapshot,
            clock_address,
            "paused" if method == "pause" else "running",
        )
    if synced is not None:
        result = replace(
            result,
            success=synced.success,
            snapshot=synced.snapshot,
            diagnostics=[*result.diagnostics, *synced.diagnostics],
            changed_addresses=list(dict.fromkeys([*result.changed_addresses, *synced.changed_addresses])),
        )
    try:
        require_participant_autonomous_runtime_snapshot(result.snapshot)
    except ValueError:
        return ApplyResult(
            False,
            predecessor,
            diagnostics=[
                _failure_diagnostic(
                    "runtime.participant-autonomous-readback-invalid",
                    f"runtime.time.{method}",
                    "Participant runtime state disagrees with the shared-clock transition.",
                )
            ],
        )
    return validated_composition_result(owner, result, predecessor, f"runtime.time.{method}")
