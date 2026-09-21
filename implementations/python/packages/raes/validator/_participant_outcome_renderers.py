"""Authoring diagnostics for participant outcome interpretation rules."""

PARTICIPANT_OUTCOME_ISSUE_RENDERERS = {
    "participant.outcome.local-effect-unbound": (
        lambda i: (
            f"Outcome interpretation rule '{i.rule_name}' criterion '{i.binding_id}' "
            f"references undefined effect '{i.ref}'"
        )
    ),
    "participant.outcome.source-action-unbound": (
        lambda i: f"Outcome interpretation rule '{i.rule_name}' source '{i.ref}' references undefined action contract"
    ),
    "participant.outcome.source-objective-unbound": (
        lambda i: f"Outcome interpretation rule '{i.rule_name}' source '{i.ref}' references undefined objective"
    ),
    "participant.outcome.source-workflow-unbound": (
        lambda i: f"Outcome interpretation rule '{i.rule_name}' source '{i.ref}' references undefined workflow"
    ),
    "participant.outcome.target-objective-unbound": (
        lambda i: f"Outcome interpretation rule '{i.rule_name}' target '{i.ref}' references undefined objective"
    ),
    "participant.outcome.target-workflow-unbound": (
        lambda i: f"Outcome interpretation rule '{i.rule_name}' target '{i.ref}' references undefined workflow"
    ),
}
