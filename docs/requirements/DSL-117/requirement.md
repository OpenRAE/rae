---
id: DSL-117
title: "Participant Tool And Affordance Modeling"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:24:06.514527Z
updated_at: 2026-07-15T08:42:44.856602Z
---

# DSL-117 — Participant Tool And Affordance Modeling

## Statement

The language shall support declaration of participant-visible tools, affordances, interfaces, and interaction channels together with any relevant scope or availability constraints.

## Rationale

Primary-source refresh shows that tool-using participants require an explicit authoring surface for what interaction affordances are available, rather than leaving that surface implicit in one benchmark or agent harness.

## Clause verification

- Participant-visible tools: a tool is a scenario `content` identity that a
  tool affordance names through its optional `tool_ref`. Declared content alone
  makes no tool available to any participant. Parser: `raes/parser.py` builds
  `ParticipantToolAffordance` (`raes/participant_behavior_specification.py`).
  Schema: `$defs.ParticipantToolAffordance` in
  `contracts/schemas/sdl/sdl-authoring-input-v1.json` is closed. Validator:
  `raes/validator/_participant_tool_affordances.py` resolves `tool_ref` through
  the declaration index and requires a content declaration. Composition:
  `raes/composition/_behavior.py` namespaces bare and section-qualified
  `tool_ref` values with the import's symbols. Compiler:
  `raes_processor/compiler/participant_behaviors.py` emits the resolved
  `provision.content.<name>` address.
- Affordances: `behavior_specifications.<spec>.tool_affordances.<id>` binds
  non-empty action-contract and observation-boundary sets of its owning
  behavior specification, and each referenced observation boundary must
  classify the affordance ref explicitly. Parser: the same model. Schema: both
  relations are required. Validator:
  `raes/semantics/participant_behavior/_tool_affordance.py` rejects relations
  that widen the specification, fall outside a selected participant's actions
  or boundaries, duplicate another relation, or lack a view classification.
  Composition: `raes/composition/_behavior.py` rewrites the relations into the
  import's namespace and maps each affordance ref to its namespaced form.
  `raes/composition/_sections.py` applies that map to the boundary's refs,
  view rules and view transitions, so the classification follows the
  affordance. Compiler: one
  `participant.behavior-specification.<spec>.tool-affordance.<id>` record per
  affordance.
- Interfaces and interaction channels:
  `agents.<name>.interactive_access.<id>` names a compute-node `target_ref`, a
  closed `ssh` or `rdp` channel and an optional `account_ref`. Parser:
  `raes/parser.py` builds `ParticipantInteractiveAccess` (`raes/agents.py`).
  Schema: `$defs.ParticipantInteractiveAccess` is closed. Validator: the
  interactive-access analyzer `raes/semantics/participant_interactive_access.py`,
  run from `raes/validator/_content_objectives.py`, rejects non-compute
  targets, accounts on another node or outside `starting_accounts`, and
  duplicate endpoints per participant. Composition:
  `raes/composition/_behavior.py` namespaces targets and accounts. Compiler:
  `raes_processor/compiler/participant_behaviors.py` carries each entry on the
  compiled participant behavior.
- Scope and availability constraints: an affordance is available only to the
  participants that its behavior specification selects by `participant_refs` or
  `participant_role_refs`, and each of them must already hold the bound actions
  and boundaries. Absence means no availability. Parser and schema: the same
  closed models. Validator: `select_participants` in
  `raes/semantics/participant_behavior/_references.py` selects the
  participants. Composition: role refs stay global, so a local role-scoped
  affordance must hold for every participant with that role in every import.
  Compiler: the specification's `participant_addresses` record the selection.
- Declaring or displaying a tool authorizes no invocation and proves no
  execution. Runtime admission in `raes_runtime/participant_control.py` checks
  the compiled participant's own action set and requires an
  implementation-bound request. A participant whose observation boundary shows
  the tool, but who does not declare the bound action, is refused. A tool
  affordance address is not an action. Refused attempts record no operation and
  no behavior history.

## Fulfillment boundary

ACTIVE. #298 verified the #294 and #805 surfaces through composition,
compilation and runtime admission. It fixed one gap in the reference rewrite
that module composition and `rename_sdl_declaration`
(`raes/_transformation_rename.py`) share. A section-qualified `tool_ref` such
as `content.scanner-package` was not rewritten. In composition, the imported
affordance bound the importing scenario's content of the same name, or failed
when there was none. In rename, renaming that content was refused with
`artifact-transformation.target-invalid`, because the ref kept the old name.
`raes/composition/_behavior.py` now rewrites `tool_ref` through the named
symbols, as the validator resolves it through the declaration index. The
composed affordance binds the unit's own content, and the rename rewrites the
ref to `content.<new-name>`. Bare refs are rewritten as before. A `tool_ref`
that names a non-content declaration of the unit now gets the same diagnostic
as in the standalone unit.

Residual boundaries:

- An importing scenario cannot add a tool affordance for an imported
  participant. The affordance must be classified by one of that participant's
  own observation boundaries, and those belong to the imported unit.
- `participant_role_refs` in an imported declaration select every participant
  with that role in the composed scenario, as the #297 verification in PR #1426
  also found. A unit with a role-scoped tool affordance validates when imported
  once and fails when imported twice.
- A structurally invalid declaration in an imported unit, such as an
  interactive-access `channel: telnet`, raises a raw pydantic `ValidationError`
  instead of an `SDLParseError` diagnostic, as PR #1426 also found.
- Decision-time exposure belongs to #300, reusable tool profiles to #301, and
  capability declarations to #304.

## Traceability

- TESTS → TEST `implementations/python/tests/test_participant_interactive_access.py` (Participant interactive-access SDL and compiler tests)
- IMPLEMENTS → PULL_REQUEST `807` (feat(sdl): add participant interactive access)
- IMPLEMENTS → GITHUB_ISSUE `294` (Participant Tool And Affordance Semantics (SEM-219))
- IMPLEMENTS → GITHUB_ISSUE `805` (SDL: authored participant interactive-access (SSH/RDP) declarations)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/parser.py` (SDL parse entry point and model-diagnostic wrapping)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_behavior_specification.py` (Participant tool affordance model)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/agents.py` (Participant interactive-access model and closed channel vocabulary)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (Published authoring schema for tool affordances and interactive access)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_participant_tool_affordances.py` (Tool identity resolution through scenario content)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/semantics/participant_behavior/_tool_affordance.py` (Affordance relation, widening, participant subset and view classification checks)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/semantics/participant_behavior/_references.py` (Participant and role selection for affordance availability)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/semantics/participant_interactive_access.py` (Interactive-access target, account and endpoint analyzer)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_content_objectives.py` (Semantic validation entry for participant tool and access checks)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_behavior.py` (Namespaced tool, affordance and access references for imports)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_sections.py` (Observation-boundary classification rewritten to the namespaced affordance refs)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_behaviors.py` (Compiled tool affordance and interactive-access records)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control.py` (Runtime admission that a tool declaration does not bypass)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/sections.md` (Tool affordance and interactive-access authoring reference)
- DOCUMENTS → SPEC `specs/formal/participant-semantics/README.md` (SEM-219 predicates and the DSL-117 interactive-access specialization)
- DOCUMENTS → GITHUB_ISSUE `298` (Verify participant tool authoring across composition and compilation)
- TESTS → TEST `implementations/python/tests/test_issue_298_tool_authoring.py` (Standalone, twice-imported and local tool bindings through composition, compilation and runtime admission)
- TESTS → TEST `implementations/python/tests/fixtures/tool-authoring/scanner-toolkit.sdl.yaml` (Reusable tool unit that is also a valid standalone scenario)
- TESTS → TEST `implementations/python/tests/fixtures/tool-authoring/operator-console.sdl.yaml` (Two namespaced imports of one tool unit and a local tool affordance)
- TESTS → TEST `implementations/python/tests/test_sem_208_participant_behavior.py` (Single-file tool affordance parsing, validation, visibility and compilation)
- TESTS → TEST `implementations/python/tests/test_runtime_control_plane.py` (Runtime admission rejects an action outside the compiled participant behavior)
