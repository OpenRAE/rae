---
id: DSL-117
title: "Participant Tool And Affordance Modeling"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:24:06.514527Z
updated_at: 2026-10-15T04:57:10.841468+00:00
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
  the declaration index and requires exactly one content declaration.
  Composition: `raes/composition/_behavior.py` rewrites a bare unit content
  name through the import's content symbols and any other spelling, such as
  `content.<name>`, through its named symbols. Before that rewrite,
  `raes/composition/_expand.py` rejects a unit `tool_ref` that the unit's own
  declaration index finds ambiguous, with the standalone diagnostic. Authored
  private tool references and relations fail before expansion or parameter
  binding; generated private references remain valid. Compiler:
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
- Interfaces: the access interface is
  `agents.<name>.interactive_access.<id>`, which names a compute-node
  `target_ref` and an optional `account_ref` in the participant's
  `starting_accounts`. The invocation interface is the bound action contract's
  `arguments`. The compiled affordance holds only action addresses; each one
  resolves to a compiled action contract whose `argument_shape_ref` starts with
  that address, and the affordance copies no argument data (issue-294
  compilation boundary; ACT-622). Parser: `raes/parser.py` builds
  `ParticipantInteractiveAccess` (`raes/agents.py`). Schema:
  `$defs.ParticipantInteractiveAccess` is closed. Validator: the
  interactive-access analyzer `raes/semantics/participant_interactive_access.py`,
  run from `raes/validator/_content_objectives.py`, rejects non-compute
  targets, accounts on another node or outside `starting_accounts`, and
  duplicate endpoints per participant. Composition:
  `raes/composition/_behavior.py` namespaces targets and accounts. Compiler:
  `raes_processor/compiler/participant_behaviors.py` carries each entry on the
  compiled participant behavior.
- Interaction channels: `channel` is the closed vocabulary `ssh` or `rdp`. Any
  other value, in a root document or an imported unit, raises `SDLParseError`
  with the file and the `/agents/<name>/interactive_access/<id>/channel`
  pointer.
- Scope and availability constraints: an affordance is available only to the
  participants that its behavior specification selects by `participant_refs` or
  `participant_role_refs`, within its `authority_scope_refs`, and each of them
  must already hold the bound actions and boundaries. Action-contract
  preconditions and argument domains bound each invocation. Absence means no
  availability. Validator: `select_participants` in
  `raes/semantics/participant_behavior/_references.py` selects the
  participants. Composition: role refs select across the composed scenario, so
  a role-scoped affordance must hold for every participant with that role in
  every import. Compiler: the specification's `participant_addresses` record
  the selection.
  Before rewriting, composition rejects ambiguous unit authority scopes using
  the same reference purpose and diagnostic as standalone validation.
- Declaring or displaying a tool authorizes no invocation and proves no
  execution. Runtime admission in `raes_runtime/participant_control.py` checks
  the compiled participant's own action set and requires an
  implementation-bound request. A participant whose observation boundary shows
  the tool, but who does not declare the bound action, is refused. A tool
  affordance address is not an action. Refused attempts record no operation and
  no behavior history. Declared, visible, supported, eligible, admitted and
  realized remain separate SEM-219 predicates.

`examples/scenarios/participant-tools/` holds a reusable tool unit and a
scenario that imports it twice. Its README maps each concern to its authored
field.

## Fulfillment boundary

ACTIVE. #298 verified the #294 and #805 surfaces through parsing, semantic
validation, composition, declaration rename, compilation and runtime admission.
It fixes imported tool identities and authority-scope ambiguity, and rejects
authored private tool references before composition and parameter binding. The
[tool authoring decision](../../decisions/issue-298-tool-authoring.md) records
the semantics and the migration.

- A section-qualified `tool_ref` such as `content.scanner-package` was not
  rewritten. In composition, the imported affordance bound the importing
  scenario's content of the same name, or failed when there was none. In
  `rename_sdl_declaration` (`raes/_transformation_rename.py`), which shares the
  rewrite, renaming that content was refused with
  `artifact-transformation.target-invalid`. The ref now binds the unit's own
  content and is renamed with it. A `tool_ref` that names a non-content
  declaration of the unit gets the standalone diagnostic.
- A bare `tool_ref` that names two of the unit's declarations, such as content
  and a relationship, or content and a content item, failed in the unit alone
  but composed silently to the content. Composition now fails with the
  standalone ambiguity diagnostic, anchored at the unit file.

Settled boundaries, not gaps:

- An importing scenario cannot add a tool affordance for an imported
  participant: ADR-053 rejects overlay patches, and the issue-294 preflight
  requires the participant's own observation boundary to classify the
  affordance. The unit exports the affordance, or the importer declares its own
  participant over imported actions and tools.
- `participant_role_refs` in an imported declaration select every participant
  with that role in the composed scenario. The
  [issue-297 decision](../../decisions/issue-297-behavior-authoring.md) settles
  this; reusable tool bindings use explicit `participant_refs`.
- An invalid imported `channel` raises `SDLParseError`, as #1426 delivered.
- Decision-time exposure belongs to #300, reusable tool profiles to #301, and
  capability declarations to #304.

Adjacent defects outside DSL-117 are tracked separately:

- #1573: rename of nested node-service and content-item refs.
- #1574: reference-typed action argument values across imports.
- #1575 retains other reference families; this delivery rejects ambiguous
  behavior `authority_scope_refs` before import rewriting, as it does tool refs.
- #1498 retains agent-field authoring checks; this delivery rejects authored
  `__private` tool identities and tool action/observation relations before
  composition or parameter binding, while preserving generated private refs.

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
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_expand.py` (Import-time rejection of ambiguous unit tool identities and behavior authority scopes)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_behavior_authoring.py` (Authored tool references reject reserved private namespace segments before composition and binding)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_sections.py` (Observation-boundary classification rewritten to the namespaced affordance refs)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_behaviors.py` (Compiled tool affordance and interactive-access records)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control.py` (Runtime admission that a tool declaration does not bypass)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/sections.md` (Tool affordance and interactive-access authoring reference)
- DOCUMENTS → SPEC `specs/formal/participant-semantics/README.md` (SEM-219 predicates and the DSL-117 interactive-access specialization)
- DOCUMENTS → GITHUB_ISSUE `298` (Verify participant tool authoring across composition and compilation)
- TESTS → TEST `implementations/python/tests/test_issue_298_tool_authoring.py` (Standalone, twice-imported and local tool bindings through composition, declaration rename, compilation and runtime admission)
- VERIFIES → SPEC `examples/scenarios/participant-tools/tool-kit.sdl.yaml` (Reusable tool unit that is also a valid standalone scenario)
- VERIFIES → SPEC `examples/scenarios/participant-tools/twice-imported.sdl.yaml` (Two namespaced imports of one tool unit and a local tool affordance)
- DOCUMENTS → DOCUMENTATION `examples/scenarios/participant-tools/README.md` (Concern-to-field mapping, import rules and limits)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-298-tool-authoring.md` (Tool composition decision, settled boundaries and migration)
- TESTS → TEST `implementations/python/tests/test_issue_297_behavior_authoring.py` (Role-wide selection of a reusable tool binding and explicit participant refs)
- TESTS → TEST `implementations/python/tests/test_sem_208_participant_behavior.py` (Single-file tool affordance parsing, validation, visibility and compilation)
- TESTS → TEST `implementations/python/tests/test_runtime_control_plane.py` (Runtime admission rejects an action outside the compiled participant behavior)
