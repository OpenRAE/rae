"""Reference-runtime refusal of rev1 mixed-control semantics.

Execution admission and control-plane construction both refuse the
``mixed-control-policy-occurrence/rev1`` form: the reference runtime has no
reusable mixed-control executor, so no rev1 episode is initialized and no
embedder can install a rev1 specification into a control plane.
"""

from collections.abc import Mapping

from raes_contracts.diagnostics import Diagnostic
from raes_processor.models import ParticipantBehaviorSpecificationRuntime, RuntimeModel
from raes_processor.planner.mixed_control_admission import mixed_control_policy_addresses


def reference_mixed_control_diagnostics(model: RuntimeModel) -> list[Diagnostic]:
    """Execution admission: one refusal per rev1 specification or rev1 delivery binding."""

    addresses = mixed_control_policy_addresses(
        model.behavior_specifications.values(),
        model.participant_inject_deliveries.values(),
    )
    return [
        Diagnostic(
            code="runtime.mixed-control-semantics-unsupported",
            domain="participant",
            address=address,
            message="The reference runtime cannot execute reusable mixed-control policies or their occurrences.",
        )
        for address in addresses
    ]


def refuse_unsupported_mixed_control(
    behavior_specifications: Mapping[str, ParticipantBehaviorSpecificationRuntime] | None,
) -> None:
    """Construction gate: raise ``ValueError`` for any rev1 behavior specification."""

    if behavior_specifications and mixed_control_policy_addresses(behavior_specifications.values()):
        raise ValueError("control plane cannot install mixed-control-policy-occurrence/rev1 behavior specifications")


__all__ = ["reference_mixed_control_diagnostics", "refuse_unsupported_mixed_control"]
