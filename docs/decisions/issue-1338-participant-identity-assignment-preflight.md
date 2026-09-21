# Issue #1338 participant identity, affiliation, and objective assignment preflight

Date: 2026-09-21. Requirement: none; issue #1338 is the delivery contract.
ACT-613 remains a remediation-program label and is not activated by this slice.

This note fixes the architecture boundary before implementation. It is not an
implementation plan and does not claim that the language, migration, schemas,
or conformance evidence have shipped. The semantic change needs a reviewed
companion to ADR-020/022/067 (or their governed amendment); accepted ADR text
must not be edited silently.

## Selected semantic contract

The authored key under `agents` is the participant identity boundary. RAE does
not derive participant identity from an entity, role, implementation, service,
component graph, executable process, account, or runtime episode. Authors decide
which autonomous subject one declaration denotes. The historical `agents` root
remains the authoring home; renaming it is neither required nor sufficient.

The canonical participant fields are:

- `affiliations: list[str] = []`, containing zero or more references to
  `entities`. An affiliation records organizational alignment or
  representation only. It does not merge identities, assign objectives, grant
  authority, share observations, select an implementation, or imply membership
  of participant components.
- `role: ExerciseRole | str | None`, recording the participant's scenario role
  directly. Role is not affiliation, login role, control-plane role, behavior
  mode, or authorization.

The plural affiliation shape is the bounded extensibility seam for a participant
that meaningfully represents more than one organization. It remains a list of
references, not a new organization model or a qualified delegation ontology.
If later work needs relationship type, interval, or evidence, it must use a
separately governed relation rather than adding meanings to the strings.

For compatibility, the effective participant role is the explicitly authored
`agents.*.role` when present. Otherwise, and only when there is exactly one
affiliation, its `entities.*.role` may supply the effective role. Zero or
multiple affiliations supply no inherited role. Consumers that require a role
must reject an absent or unresolved effective role; they must not select the
first affiliation, combine roles, or infer a role from actions, behavior mode,
implementation kind, or objective ownership. This fallback preserves the
current single-entity role source while permitting two participants with one
affiliation to retain distinct identities and explicitly different roles.

The canonical objective fields are:

- `owner: str | None`, an optional reference to `entities`, meaning the
  organization responsible for the objective. Ownership is not participation,
  assignment, authority, beneficiary identity, or proof of action.
- `assigned_participant: str | None`, an optional reference to `agents`, meaning
  the participant designated to pursue the objective. Assignment is authored
  intent, not proof that the participant accepted, attempted, or realized an
  action.
- existing `actions`, interpreted as action-contract constraints on acceptable
  pursuit of the objective, not as action events or undeclared labels.

An objective must declare at least one of `owner` and `assigned_participant` and
may declare both. `actions` always resolve to declared `action_contracts`. When
an assignment exists, every constrained action must also be available in that
participant's `actions`. Without an assignment, valid action constraints remain
organizational intent: they constrain a future explicit assignment but create
no participant, runtime work, evaluation authority, or actor attribution.

The design intentionally does not add a `beneficiary` field. Owner, beneficiary,
target, and success subject are not interchangeable; the issue supplies a
concrete ownership requirement but no beneficiary rules or acceptance case.
No beneficiary may be inferred from `owner`, `targets`, affiliation, or success
assertions. A later beneficiary relation belongs at the normalized objective
relation seam with its own endpoint and validation rules.

Realized actor attribution remains owned by participant action/history/result
contracts using canonical participant address, episode, sequence, and action
coordinates. Neither objective assignment nor affiliation may be copied into a
runtime record as proof of who acted. Conversely, runtime attribution does not
rewrite authored ownership or assignment.

## Alternatives and rejected conflations

| Alternative | Disposition |
| --- | --- |
| Keep mandatory `Agent.entity` and clarify prose | Rejected: composite or unaffiliated participants still need a synthetic organization, while shared entities still do not identify one participant. |
| Make `Agent.entity` optional but retain its identity/role meaning | Rejected: absence fixes authoring pressure but leaves one field with incompatible identity, affiliation, and role meanings. |
| Use optional `affiliations` plus a participant-local `role` | Selected: identity stays at the declaration, affiliation is optional, multiple affiliations are representable, and the current role source has one explicit fallback. |
| Add a generic relation object for affiliation, representation, membership, ownership, and assignment | Rejected: those relations have different endpoints and consequences, and no current requirement supplies qualifiers that justify a new ontology. |
| Keep `Objective.agent` / `Objective.entity` as polymorphic actors | Rejected: an entity objective can exist without participants and currently bypasses action checks; the fields do not have one actor meaning. |
| Infer assignment from all participants sharing the owner/affiliation | Rejected: it silently widens assignment, authority, observations, and potentially execution. |
| Treat every objective action label as a participant action | Rejected: unassigned organizational intent has no participant action set. All labels must first be declared action contracts; participant availability is an additional check only when assigned. |
| Add a second `participants` root or rename `agents` now | Rejected: it creates migration and identity aliases without fixing the semantic relations. |

## Canonical owners and cross-stage invariants

The implementation must extend the incumbents below; none may gain a parallel
schema, resolver, exception family, persistence store, or workflow.

| Concern | Canonical incumbent and invariant |
| --- | --- |
| Authoring shape | `raes.agents.Agent`, `raes.entities.Entity`, and `raes.objectives.Objective` remain the only SDL owners. They inherit `SDLModel(extra="forbid")`; portable identifiers and whole-field variables retain `_identifiers.py` / `_base.py` rules. |
| Safe parsing and instantiation | `_yaml_loader.py`, `parser.py`, `_source_profile.py`, and instantiated-scenario revalidation retain byte/depth/node/alias limits, YAML 1.2 safe construction, exact structural keys, source diagnostics, and post-substitution semantic validation. Affiliation or assignment cannot be introduced through variable mapping keys. |
| Name resolution | `DeclarationIndex`, `QualifiedName`, flattened entity references, and `SemanticValidator` remain authoritative. Extend the existing participant/objective analyzers with distinct normalized relation kinds (`AFFILIATION`, `OWNER`, `ASSIGNMENT`, and `ACTION_CONSTRAINT`); do not split rendered addresses or build a second index. |
| Effective role | One shared pure role resolver must serve behavior-specification role selection, autonomous-execution role checks, participant relationships, validation, and compilation. It implements direct-role-first plus the single-affiliation fallback; local reimplementations are forbidden. |
| Objective semantics | `raes.semantics.objective_semantics.analyze_objective_semantics` remains the name-level source of truth. Owner and assignment are separate references with no ordering/refresh role unless the existing dependency constants and planner propagation change together. Action resolution is global-to-contract plus assigned-participant subset validation. |
| Participant relationships | `_participant_relationships.py` continues to require participant endpoints. An objective belongs to an endpoint only through explicit `assigned_participant`; common ownership or affiliation is insufficient. |
| Composition and variation | `raes/composition/_behavior.py`, `_references.py`, the existing symbol maps, and `variation.py` own rewriting. Imports must namespace each affiliation, owner, and assignment through its owning section. Replace old variation slots with the new canonical slots; do not retain two writable meanings. |
| Compilation | `compiler/addresses.py`, `participant_behaviors.py`, `objectives.py`, and the typed runtime models retain canonical addresses. Participant projections keep the authored participant name and carry affiliations/role separately. Objective projections carry owner and assigned-participant coordinates separately; remove the overloaded `actor_type` / `actor_name` projection rather than populating it with a new ambiguity. |
| Runtime authority | `participant_execution.py`, participant behavior semantics, backend capability admission, and runtime action/history contracts remain the execution and attribution owners. Only explicit assignment may select an objective for participant autonomous evaluation, and assignment alone grants no action, target, evaluation, control-plane, or backend authority. |
| Editor and inspection | `_language_metadata.py`, `_language_references.py`, language-service completion/navigation, and MCP inspection summaries consume the same field-specific reference rules and effective-role resolver. User-facing summaries must label owner and assignment separately rather than render either as “actor.” |
| Published contracts | `raes_contracts.contracts.schema_bundle()` remains the generator input. Regenerate `sdl-authoring-input-v1`, `instantiated-scenario-v1`, and `instantiated-scenario-snapshot-v1`; update their schema-publication entries, SDL catalog parity expectations, reference catalog, and valid/invalid fixtures. Generated JSON schemas are never edited directly. |
| Diagnostics and errors | Reuse `SDLParseError`, `SDLValidationError`, `SDLInstantiationError`, analyzer issue records, compiler `Diagnostic`, and the CLI/MCP portable envelopes. New issue codes must be bounded and field-specific. Do not interpolate source documents, Pydantic inputs, credentials, hidden evidence, or tracebacks. |
| Persistence and evidence | Existing `RuntimeSnapshot`, participant episode/history/evidence contracts, configuration digests, CAS/idempotency, and append-only control-plane stores retain ownership. Preserve historical participant addresses and episode joins; do not rewrite stored evidence or create an identity/assignment repository. |
| Governance and verification | ADR-009/061/075, `specs/evolution/deprecation-records.yaml`, schema publication checks, SDL catalog parity, nox policy lanes, and existing parser/semantic/composition/compiler/language-service test families remain authoritative. Schema acceptance alone is not semantic evidence. |

## Compatibility and migration boundary

The canonical model must not accept both old and new writable fields and then
choose one. A source-bound, explicit migration path must reuse the repository's
existing transformation result, canonical digest, structured diagnostic, and
atomic-refusal conventions.

A repository-local structured-document inventory (YAML/JSON, excluding generated
schemas, build/cache trees, and virtual environments) found 21 documents using
the affected shapes: 28 `agents.*.entity` bindings, 20
`objectives.*.agent` bindings, and seven `objectives.*.entity` bindings. The
seven entity objectives are in the formal-semantic-validation corpus and the
hospital, port-authority, reconciliation v1/v2, and satcom examples; none
currently carries `actions`. The hospital example also has two distinct
participants sharing `ransom-crew`, which must remain a positive identity
regression. Inline Python fixtures and generated schemas are consumers to
update, not additional authored inventory authority.

The deterministic mappings are:

| Legacy source | Canonical result | Compatibility treatment |
| --- | --- | --- |
| `agents.*.entity: E` | `agents.*.affiliations: [E]` | Lossless relation rewrite; legacy effective role is preserved by the single-affiliation fallback. |
| `objectives.*.agent: P` | `objectives.*.assigned_participant: P` | Preserves the only existing path that validates participant action availability; it does not invent an owner. |
| `objectives.*.entity: E` | No automatic canonical output | Requires a source-digest-bound author decision: owner-only, or owner plus an explicitly named assigned participant. The migrator must never select affiliated participants. |

For a legacy entity objective, owner-only conversion keeps `actions` only when
every value resolves to a declared action contract. An undeclared label is a
bounded migration refusal, not a newly invented participant action. Owner plus
assignment additionally applies the assigned participant's action subset check.
Migration is atomic: missing decisions, stale source digests, unresolved refs,
or conflicting old/new fields produce no canonical scenario. Diagnostics name
JSON pointers and rule ids, not source bodies. A deprecation/removal record and
author guide must state the supported legacy-reader window; hidden aliases in
Pydantic validators are not a migration policy.

Historical compiled records, participant episode histories, evidence, and
configuration digests retain their original addresses and schema identifiers.
Migration creates a new canonical artifact with recorded provenance; it does not
rewrite old evidence by string replacement.

## Security and operational passage

This semantic change does not add a network API, secret field, environment
binding, subprocess, listener, host path, OS identity, or privilege. That
absence is a constraint, not permission to skip the layers the data already
passes:

- **Source and shape gate:** safe bounded YAML loading, closed Pydantic models,
  identifier validation, variable restrictions, and semantic revalidation
  reject malformed, oversized, ambiguous, or post-substitution-invalid input.
- **Authorization gate:** authored participant identity, affiliation, role,
  ownership, and assignment are scenario facts only. `ControlPlaneSecurityConfig`,
  control-plane API authentication/authorization, participant control grants,
  effect authority, and backend admission remain mandatory for live effects.
- **Secret and configuration gate:** none of the new fields may carry literals,
  credentials, prompts, tokens, implementation settings, or environment values.
  If later apparatus selection is involved, reuse participant-configuration,
  experiment-binding, and logical secret-reference contracts; never argv, URLs,
  logs, or raw provenance.
- **OS/runtime exposure gate:** affiliation and assignment create no account,
  process, port, service, environment variable, mount, listener, target access,
  or episode. Existing runtime-environment/generated-value and host admission
  rules remain outside this authoring change.
- **Error-envelope gate:** parser source ranges and bounded semantic/compiler
  diagnostics identify field paths and canonical refs. CLI, MCP, and HTTP
  adapters keep their existing redacted envelopes; no request/source dump or
  arbitrary exception text is added.
- **Persistence gate:** compiled projections and existing snapshots may carry
  non-secret names only. Runtime stores retain revisions, CAS, idempotency,
  audit, retention, and redaction rules; no affiliation-based query or access
  control is inferred.

## Acceptance guardrails

- An `agents.composite` declaration with no affiliations, components, entity,
  node, service, or selected implementation is a complete participant identity.
- Two participant declarations with the same affiliation remain different
  canonical participant addresses, targets, observation boundaries, histories,
  and episode identities.
- An objective may have `owner: org` and
  `assigned_participant: responder`; removing the assignment leaves valid
  organizational intent but no actor or autonomous objective selection.
- Shared affiliation never broadens assignment. A role-selected behavior
  specification may select both participants only because their effective roles
  match its explicit role rule, not because an objective owner matches.
- A constrained action on an unassigned objective must resolve globally; after
  assignment it must also be available to that participant. Neither condition
  records an action occurrence.
- A participant remains eligible as an interaction actor and as another
  interaction's target. Entities remain entity targets only and cannot acquire
  participant episodes, observations, relationships, or action histories.
- Composition, variable instantiation, compiler projection, schema generation,
  language-service navigation, and MCP summaries preserve the same meanings and
  fail closed on dangling or ambiguous refs.
- The author-task walkthrough must exercise unaffiliated composite identity,
  shared affiliation, direct and inherited roles, owned/unassigned and
  owned/assigned objectives, invalid undeclared actions, migration decisions,
  and realized attribution that differs from authored assignment.

## Non-goals and anti-patterns

This issue does not define an autonomy threshold, participant component graph,
service-to-participant realization relation, beneficiary ontology, general
actor ontology, new targetability policy, new address syntax, apparatus
selection, runtime scheduling, evaluation authority, control-plane identity,
authorization, persistence, or ACT-613 completion evidence. Those remain with
their existing owners or follow-up issues #1339-#1342 and #220-#221.

Avoid mandatory organizations for unaffiliated participants; entity-derived
identity; role inference from actions or implementations; owner-as-actor;
affiliation-as-assignment; assignment-as-attribution; target-as-authority;
schema-only acceptance; duplicated role/objective resolvers; parallel DTOs;
free-form metadata; silent legacy aliases; first-affiliation wins; bulk address
renames; historical-evidence rewrites; and generated-schema hand edits.
