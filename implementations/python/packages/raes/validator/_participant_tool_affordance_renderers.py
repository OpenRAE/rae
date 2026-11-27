"""Authoring diagnostics for participant-scoped tool-affordance selectors (ACT-619)."""

PARTICIPANT_TOOL_AFFORDANCE_ISSUE_RENDERERS = {
    "participant.tool-affordance-participant-unbound": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' tool affordance '{i.action_name}' participant_ref "
            f"'{i.ref}' does not reference a declared agent"
        )
    ),
    "participant.tool-affordance-role-unbound": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' tool affordance '{i.action_name}' participant_role_ref "
            f"'{i.ref}' does not match any declared participant role"
        )
    ),
    "participant.tool-affordance-participant-widens-parent": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' tool affordance '{i.action_name}' selects participant "
            f"'{i.ref}' outside its owning behavior specification; binding selectors only narrow"
        )
    ),
}
