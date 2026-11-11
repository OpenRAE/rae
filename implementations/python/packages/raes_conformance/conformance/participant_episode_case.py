"""Expose recorded ACT-623 history findings through the target report."""

from raes_contracts.participant_episode_snapshot import iter_participant_episode_snapshot_violations
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.models import RuntimeModel
from raes_runtime.participant_episode_binding import EPISODE_CONTRACTS
from raes_runtime.registry import RuntimeTarget

from .diagnostics import _diagnostic
from .participant_episode_structure import participant_episode_structure_conformance_diagnostics
from .report import ConformanceCaseResult


def participant_episode_structure_case(
    target: RuntimeTarget,
    model: RuntimeModel | None,
    snapshot: RuntimeSnapshot | None,
) -> ConformanceCaseResult:
    """Inspect supplied recorded history; never certify native condition evaluation."""

    name = "participant-episode-structure"
    limitations = ("Recorded history inspection does not establish native policy enforcement or condition evaluation.",)
    applicable = (
        target.manifest.participant_runtime is not None
        and set(target.manifest.supported_contract_versions) >= EPISODE_CONTRACTS
        and model is not None
        and bool(model.participant_episode_policies)
    )
    if not applicable:
        return ConformanceCaseResult(
            name=name,
            contract_name="participant-episode-history-event-stream-v1",
            valid=True,
            passed=False,
            outcome="not-applicable",
            limitations=limitations,
            finite_scope="No compiled authored episode policy and matching target episode capability were selected.",
        )
    diagnostics = []
    participants = {
        address for policy in model.participant_episode_policies.values() for address in policy.participant_addresses
    }
    if snapshot is None or any(not snapshot.participant_episode_history.get(address) for address in participants):
        diagnostics.append(
            _diagnostic(
                "conformance.participant-episode-evidence-missing",
                name,
                "Recorded episode history is required for every governed participant.",
            )
        )
    else:
        diagnostics.extend(
            _diagnostic("conformance.participant-episode-snapshot-invalid", address, message)
            for address, message in iter_participant_episode_snapshot_violations(
                snapshot.participant_episode_results, snapshot.participant_episode_history
            )
        )
        diagnostics.extend(
            participant_episode_structure_conformance_diagnostics(
                model.participant_episode_policies, snapshot.participant_episode_history
            )
        )
    return ConformanceCaseResult(
        name=name,
        contract_name="participant-episode-history-event-stream-v1",
        valid=not diagnostics,
        passed=not diagnostics,
        diagnostics=tuple(diagnostics),
        outcome="unsupported" if snapshot is None else "failed" if diagnostics else "passed",
        finite_scope=f"Supplied recorded history and compiled model; episode contracts declared by target {target.name!r}.",
        limitations=limitations,
    )
