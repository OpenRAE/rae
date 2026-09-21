"""Author-facing diagnostics for autonomous participant execution."""

AUTONOMOUS_PARTICIPANT_ISSUE_RENDERERS = {
    "participant.autonomous-action-widens-parent": (
        lambda i: f"Behavior specification '{i.spec_name}' autonomous action '{i.ref}' widens its action contracts"
    ),
    "participant.autonomous-explicit-participants-required": (
        lambda i: f"Behavior specification '{i.spec_name}' autonomous execution requires explicit participant_refs"
    ),
    "participant.autonomous-feature-requirement-missing": (
        lambda i: f"Behavior specification '{i.spec_name}' autonomous execution requires backend feature '{i.ref}'"
    ),
    "participant.autonomous-action-outside-participant": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' autonomous action '{i.ref}' is outside "
            f"participant '{i.participant_name}' actions"
        )
    ),
    "participant.autonomous-boundary-widens-parent": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' autonomous observation boundary '{i.ref}' "
            "widens its observation boundaries"
        )
    ),
    "participant.autonomous-boundary-outside-participant": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' autonomous observation boundary '{i.ref}' is outside "
            f"participant '{i.participant_name}' observation boundaries"
        )
    ),
    "participant.autonomous-clock-unbound": (
        lambda i: f"Behavior specification '{i.spec_name}' autonomous clock_ref '{i.ref}' is not declared"
    ),
    "participant.autonomous-progression-unbound": (
        lambda i: f"Behavior specification '{i.spec_name}' autonomous progression_policy_ref '{i.ref}' is not declared"
    ),
    "participant.autonomous-progression-clock-mismatch": (
        lambda i: f"Behavior specification '{i.spec_name}' autonomous progression policy '{i.ref}' uses another clock"
    ),
    "participant.autonomous-constraint-unbound": (
        lambda i: f"Behavior specification '{i.spec_name}' autonomous temporal constraint '{i.ref}' is not declared"
    ),
    "participant.autonomous-constraint-clock-mismatch": (
        lambda i: f"Behavior specification '{i.spec_name}' autonomous temporal constraint '{i.ref}' uses another clock"
    ),
    "participant.autonomous-activity-window-kind-invalid": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' activity work and pause refs must resolve to window constraints; "
            f"'{i.ref}' does not"
        )
    ),
    "participant.autonomous-activity-timing-unreachable": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' activity timing bounds are unreachable by stepped "
            f"progression '{i.ref}'"
        )
    ),
    "participant.autonomous-activity-window-subject-mismatch": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' activity window '{i.ref}' must name the behavior "
            "specification or every governed participant as a subject"
        )
    ),
    "participant.autonomous-cadence-missing": (
        lambda i: f"Behavior specification '{i.spec_name}' autonomous execution requires exactly one cadence constraint"
    ),
    "participant.autonomous-cadence-unreachable": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' cadence points are unreachable by stepped progression '{i.ref}'"
        )
    ),
    "participant.autonomous-progression-driver-unsupported": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' externally paced progression '{i.ref}' has no portable "
            "runtime transition driver"
        )
    ),
    "participant.autonomous-clock-authority-unsupported": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' wall-paced autonomous clock '{i.ref}' must use runtime authority"
        )
    ),
    "participant.autonomous-non-evaluated-role-not-green": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' non-evaluated autonomous participant "
            f"'{i.participant_name}' must have the green role"
        )
    ),
    "participant.autonomous-non-evaluated-objective-authority": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' non-evaluated participant "
            f"'{i.participant_name}' cannot be assigned an objective"
        )
    ),
    "participant.autonomous-objective-not-assigned": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' objective '{i.ref}' must be assigned to a selected participant"
        )
    ),
    "participant.autonomous-non-evaluated-authority-widening": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' non-evaluated autonomous execution cannot carry "
            "outcome-interpretation or authority-scope refs"
        )
    ),
    "participant.autonomous-evaluation-objective-unbound": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' evaluation-authority objective_ref "
            f"'{i.ref}' is not declared in objectives"
        )
    ),
    "participant.autonomous-evaluation-authority-namespace-unsupported": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' evaluation-authority {i.message} ref "
            f"'{i.ref}' cannot resolve because RAES SDL declares no such authority namespace"
        )
    ),
    "participant.autonomous-participant-owner-conflict": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' autonomous participant '{i.participant_name}' "
            f"is already controlled by behavior specification '{i.ref}'"
        )
    ),
}

__all__ = ["AUTONOMOUS_PARTICIPANT_ISSUE_RENDERERS"]
