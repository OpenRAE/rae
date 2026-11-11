"""Reference-edge expectations, part 3 (split from one registry literal)."""

from __future__ import annotations

from tools.sdl_catalog_parity._expectations_cloud import CLOUD_RESOURCE_EXPECTATIONS
from tools.sdl_catalog_parity._paths import (
    _DANGLING,
    _DANGLING_CYCLIC,
    _DANGLING_UNREACHABLE,
    _NON_PRECONDITION_ROLE,
    _ORDER_POINT_SCOPE,
    _SEMANTIC,
    _STRUCTURAL,
    _VARIATION_MEMBERS,
    _VARIATION_SCOPE,
    _WRONG_SLOT_CANDIDATE,
)

_FATAL_DANGLING = "fatal dangling"

EXPECTATIONS_PART_3: dict[str, tuple[(str, str, str)]] = {
    **{
        source: (
            "assertions",
            _SEMANTIC,
            "fatal unless observed positive postconditions cover each exact target",
        )
        for source in (
            "safe_state.default.assertion_refs[]",
            "safe_state.scopes[].state.assertion_refs[]",
        )
    },
    "execution_policy.default.clock_ref": ("clocks", _SEMANTIC, _FATAL_DANGLING),
    "execution_policy.default.evidence_refs[]": (
        "evidence_requirements",
        _SEMANTIC,
        _FATAL_DANGLING,
    ),
    "execution_policy.scopes[].policy.clock_ref": (
        "clocks",
        _SEMANTIC,
        _FATAL_DANGLING,
    ),
    "execution_policy.scopes[].policy.evidence_refs[]": (
        "evidence_requirements",
        _SEMANTIC,
        _FATAL_DANGLING,
    ),
    "evidence_requirements.*.source_refs[]": (
        "eligible:observation_subject",
        _SEMANTIC,
        _DANGLING,
    ),
    "evidence_requirements.*.scope_refs[]": (
        "eligible:observation_subject",
        _SEMANTIC,
        _DANGLING,
    ),
    "evidence_requirements.*.channel_refs[]": ("targetable", _SEMANTIC, _DANGLING),
    "evidence_requirements.*.trigger_ref": ("targetable", _SEMANTIC, _DANGLING),
    "evidence_requirements.*.boundary_ref": ("targetable", _SEMANTIC, _DANGLING),
    "clocks.*.time_domain_ref": ("time_domains", _SEMANTIC, _FATAL_DANGLING),
    "time_domain_mappings.*.source_domain_ref": (
        "time_domains",
        _SEMANTIC,
        "fatal dangling, duplicate, or cyclic mapping",
    ),
    "time_domain_mappings.*.target_domain_ref": (
        "time_domains",
        _SEMANTIC,
        "fatal dangling, duplicate, or cyclic mapping",
    ),
    "time_progression_policies.*.clock_ref": (
        "clocks",
        _SEMANTIC,
        "fatal dangling or incompatible reset/replay lifecycle",
    ),
    "temporal_constraints.*.clock_ref": ("clocks", _SEMANTIC, _FATAL_DANGLING),
    "temporal_constraints.*.subject_refs[]": (
        "declared",
        _SEMANTIC,
        "fatal dangling or ambiguous",
    ),
    "variation_points.*.target.variable": (
        "variables",
        _SEMANTIC,
        "fatal dangling or wrong variable type",
    ),
    "variation_points.*.target.owner": (
        "targetable",
        _SEMANTIC,
        "fatal dangling or wrong slot owner type",
    ),
    "variation_points.*.domain.allowed_refs[]": (
        "targetable",
        _SEMANTIC,
        _WRONG_SLOT_CANDIDATE,
    ),
    "variation_points.*.alternatives.*.reference": (
        "targetable",
        _SEMANTIC,
        _WRONG_SLOT_CANDIDATE,
    ),
    "variation_points.*.members.*.reference": (
        "targetable",
        _SEMANTIC,
        _WRONG_SLOT_CANDIDATE,
    ),
    "variation_points.*.alternatives.*.requires[].point": (
        "variation_points",
        _SEMANTIC,
        _DANGLING,
    ),
    "variation_points.*.alternatives.*.requires[].members[]": (
        _VARIATION_MEMBERS,
        _SEMANTIC,
        _VARIATION_SCOPE,
    ),
    "variation_points.*.alternatives.*.excludes[].point": (
        "variation_points",
        _SEMANTIC,
        _DANGLING,
    ),
    "variation_points.*.alternatives.*.excludes[].members[]": (
        _VARIATION_MEMBERS,
        _SEMANTIC,
        _VARIATION_SCOPE,
    ),
    "variation_points.*.members.*.requires[].point": (
        "variation_points",
        _SEMANTIC,
        _DANGLING,
    ),
    "variation_points.*.members.*.requires[].members[]": (
        _VARIATION_MEMBERS,
        _SEMANTIC,
        _VARIATION_SCOPE,
    ),
    "variation_points.*.members.*.excludes[].point": (
        "variation_points",
        _SEMANTIC,
        _DANGLING,
    ),
    "variation_points.*.members.*.excludes[].members[]": (
        _VARIATION_MEMBERS,
        _SEMANTIC,
        _VARIATION_SCOPE,
    ),
    "variation_points.*.precedence[].before": (
        _VARIATION_MEMBERS,
        _STRUCTURAL,
        _ORDER_POINT_SCOPE,
    ),
    "variation_points.*.precedence[].after": (
        _VARIATION_MEMBERS,
        _STRUCTURAL,
        _ORDER_POINT_SCOPE,
    ),
    "variation_points.*.fixed_positions.*.$key": (
        _VARIATION_MEMBERS,
        _STRUCTURAL,
        _ORDER_POINT_SCOPE,
    ),
    "objectives.*.assigned_participant": ("agents", _SEMANTIC, _DANGLING),
    "objectives.*.owner": ("entities", _SEMANTIC, _DANGLING),
    "objectives.*.actions[]": (
        "action_contracts",
        _SEMANTIC,
        "fatal undeclared contract or outside assigned participant actions",
    ),
    "objectives.*.targets[]": ("eligible:objective_subject", _SEMANTIC, _DANGLING),
    "objectives.*.success.assertions[]": (
        "assertions",
        _SEMANTIC,
        "fatal dangling, ambiguous, or precondition role",
    ),
    "objectives.*.depends_on[]": ("objectives", _SEMANTIC, _DANGLING_CYCLIC),
    "objectives.*.window.stories[]": ("stories", _SEMANTIC, _DANGLING),
    "objectives.*.window.scripts[]": (
        "scripts",
        _SEMANTIC,
        "fatal dangling or outside referenced stories",
    ),
    "objectives.*.window.events[]": (
        "events",
        _SEMANTIC,
        "fatal dangling or outside referenced scripts",
    ),
    "objectives.*.window.workflows[]": ("workflows", _SEMANTIC, _DANGLING),
    "objectives.*.window.steps[]": (
        "workflow_steps",
        _SEMANTIC,
        "fatal malformed, dangling, or outside referenced workflows",
    ),
    "workflows.*.start": ("workflow_steps", _SEMANTIC, "fatal dangling step"),
    "workflows.*.steps.*.when.assertions[]": (
        "assertions",
        _SEMANTIC,
        _NON_PRECONDITION_ROLE,
    ),
    "workflows.*.steps.*.when.objectives[]": ("objectives", _SEMANTIC, _DANGLING),
    "workflows.*.steps.*.when.steps.*.step": (
        "workflow_steps",
        _SEMANTIC,
        "fatal dangling, self-referential, non-executable, or unavailable before evaluation",
    ),
    "workflows.*.steps.*.cases.*.when.assertions[]": (
        "assertions",
        _SEMANTIC,
        _NON_PRECONDITION_ROLE,
    ),
    "workflows.*.steps.*.cases.*.when.objectives[]": (
        "objectives",
        _SEMANTIC,
        _DANGLING,
    ),
    "workflows.*.steps.*.cases.*.when.steps.*.step": (
        "workflow_steps",
        _SEMANTIC,
        "fatal dangling, self-referential, non-executable, or unavailable before evaluation",
    ),
    "workflows.*.steps.*.objective": ("objectives", _SEMANTIC, _DANGLING),
    "workflows.*.steps.*.procedure_ref": (
        "action_contracts",
        _SEMANTIC,
        "fatal dangling or non-procedure granularity",
    ),
    "workflows.*.steps.*.scaffold_refs[]": (
        "observation_boundaries",
        _SEMANTIC,
        "fatal dangling or scaffold-incompatible boundary",
    ),
    "workflows.*.steps.*.allowed_action_families[]": (
        "action_contracts",
        _SEMANTIC,
        "fatal dangling or non-aggregate granularity",
    ),
    "workflows.*.steps.*.next": ("workflow_steps", _SEMANTIC, _DANGLING_UNREACHABLE),
    "workflows.*.steps.*.on_success": (
        "workflow_steps",
        _SEMANTIC,
        _DANGLING_UNREACHABLE,
    ),
    "workflows.*.steps.*.on_failure": (
        "workflow_steps",
        _SEMANTIC,
        _DANGLING_UNREACHABLE,
    ),
    "workflows.*.steps.*.on_exhausted": (
        "workflow_steps",
        _SEMANTIC,
        _DANGLING_UNREACHABLE,
    ),
    "workflows.*.steps.*.then": ("workflow_steps", _SEMANTIC, _DANGLING_UNREACHABLE),
    "workflows.*.steps.*.else": ("workflow_steps", _SEMANTIC, _DANGLING_UNREACHABLE),
    "workflows.*.steps.*.cases.*.next": (
        "workflow_steps",
        _SEMANTIC,
        _DANGLING_UNREACHABLE,
    ),
    "workflows.*.steps.*.default": ("workflow_steps", _SEMANTIC, _DANGLING_UNREACHABLE),
    "workflows.*.steps.*.branches[]": (
        "workflow_steps",
        _SEMANTIC,
        "fatal dangling or outside a closed parallel branch",
    ),
    "workflows.*.steps.*.join": (
        "workflow_steps",
        _SEMANTIC,
        "fatal dangling, non-join, multiply owned, or outside branch closure",
    ),
    "workflows.*.steps.*.workflow": (
        "workflows",
        _SEMANTIC,
        "fatal dangling or cyclic",
    ),
    "workflows.*.steps.*.compensate_with": (
        "workflows",
        _SEMANTIC,
        "fatal dangling, cyclic, or invalid as a compensation target",
    ),
}

EXPECTATIONS_PART_3.update(CLOUD_RESOURCE_EXPECTATIONS)
