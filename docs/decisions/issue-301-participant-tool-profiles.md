# Issue #301 — Reusable participant tool profiles

Date: 2026-10-13. Requirement: ACT-619 (traceability only).

## Decision

A participant tool profile is the `tool_affordances` of one
`ParticipantBehaviorSpecification` together with that specification's
participant and role selection. There is no new section, model family, or
contract name. The profile is identified by the ADR-076 address
`participant.behavior-specification.<name>`, and each binding keeps
`participant.behavior-specification.<name>.tool-affordance.<id>`. The version
is the existing `semantic_version` with `lifecycle_state`. Reuse is through the
specification's own selectors and ADR-053 module import.

A binding gains two optional selector lists, `participant_refs` and
`participant_role_refs`, with the item shape of the specification selector.
Both empty means today's meaning: the binding applies to every participant the
specification selects. The binding gains no nested map, restriction id,
constraint, condition, policy, metadata, or extension field. Two roles that
need different relations from one tool get separately keyed bindings that
share one `tool_ref`. This is the SEM-219 row A positive case ("one content
identity exposes separately keyed action affordances"). It is also the #294
rule that one tool identity "may participate in several distinct bindings".

## Compared designs

1. One specification per role (existing reuse). It works today but fails "two
   roles using one profile" and duplicates the profile's identity, version, and
   shared bindings per role.
2. ADR-053 parameterized import once per role. Import parameters bind scalar
   variables, so they cannot give roles different action or boundary sets. Each
   import also yields its own specification and namespaced contracts, so this is
   two profiles, as in 1.
3. A top-level `tool_profiles` section referenced by specifications. It is a
   second availability authority and a parallel stack, which the #206 preflight
   reserves for "a later ADR" and the #294 preflight rejects.
4. A trait-style binding set included by specifications. It would remove the
   behavior coupling below, but it needs a new authored section with its own
   identity, version, import, namespace, and rename rules, which #294 and #206
   rule out without a later ADR. It also does not deliver role-specific
   bindings on its own: it still needs the selectors chosen here, or an
   include-time exclusion, which is an override operator.
5. A nested per-binding restriction map. One address would carry
   participant-dependent relations that every `affordance_refs`,
   exposure-policy, workflow-step, and manifest consumer would have to read per
   participant. It expresses nothing that separately keyed bindings do not.
6. Relative (parent-scoped) binding selectors. Rejected because #297 fixes the
   meaning of `participant_role_refs` ("selects all matching participants";
   roles "are not module-local identities"; "No new participant root, model,
   scope switch, or runtime selector is introduced"). Absolute semantics also
   keeps a later relaxation backward compatible.
7. A specification-level selection map from selectors to binding ids. It adds a
   second keyed structure with its own coverage rules away from the binding
   seam that #294 names.
8. Silently narrowing role-wide bindings. Rejected by #297 and SEM-219 row B.
9. Overrides with precedence (deny-overrides, last-wins, `extends`,
   include-time exclusion). They are order-dependent, deny is a constraint and
   not a negative grant, and overlays conflict with ADR-053.
10. Constraint bodies on a binding. They duplicate SEM-211 contracts and would
    collide with the ADR-108 control profiles.
11. New v2 surface fields such as a profile version, or an omission rule for
    hidden affordances. Both change ADR-095 v2 meaning.

The selected design is the smallest change that meets the issue: it adds no
map, id, module, runtime dataclass, or model error, and every binding address
keeps one fixed meaning.

Its main cost is behavior coupling. `behavior_mode`, `autonomous_execution`,
`mixed_control`, and `realization_profile_ref` apply to every participant the
specification selects, and PI-06 ownership is decided on that selection. One
profile therefore cannot be shared by participants that need different values
for them; they need separate specifications.

## Reconciliation with the #294 preflight

The [#294 preflight](issue-294-sem-219-participant-tool-affordance-preflight.md)
says that "The containing behavior specification supplies participant/role
scope". It also says that participant or role scope "remain[s] on the owning
`ParticipantBehaviorSpecificationRuntime`" and is reached through that address
"rather than copied into every affordance". This design is consistent with both
clauses:

- The SEM-219 formal text already names the participant branch: "An affordance
  binding relates: ... participant or behavior-specification scope"
  ([participant semantics](../../specs/formal/participant-semantics/README.md)).
  #294 realized the behavior-specification branch, and these selectors add the
  participant branch as a narrowing only.
- Dev already has a nested binding with its own participant scope under the
  specification: `participant_inject_deliveries.*.participant_ref` is "fatal
  dangling or outside the owning behavior specification"
  ([references](../../specs/sdl/references.md)), is rewritten through the agent
  symbol map, and compiles to `participant_address`. The binding selectors
  follow that shape.
- The #294 extensibility seam projects for `(participant, episode, order point,
  policy revision)` and says that "A per-phase or conditional availability
  variant adds a typed selection-context or condition reference at the binding
  seam". A participant selector is that selection context.
- A narrowing selector is not copied scope. An unscoped binding compiles with
  empty selector fields and reaches the specification's scope through
  `behavior_specification_address`. A scoped binding records only its own
  authored narrowing, as it already records its own action and boundary
  subsets.
- SEM-219 row B is preserved, not redefined (ADR-083 section 7). Its positive
  case "affordance remains within one behavior spec and every resolved
  participant" still holds with "resolved participant" read as the participants
  of `Sel(f) ⊆ Sel(S)`.

## Semantics

Rules TP-1 to TP-9 and conflict classes K1 to K5 are normative in the
[ACT-619 section](../../specs/formal/participant-behavior-model/README.md).
The points a reviewer most needs:

- Scoped is syntactic. A binding is scoped iff either authored selector list
  is non-empty. The validator, compiler, v1 refusal, v2 filter, and docs decide
  this from the raw lists, never from resolved addresses. A scoped binding that
  resolves to nobody is offered to nobody.
- Absolute selector semantics. `Sel(f)` uses the same resolver as `Sel(S)` over
  the whole composed scenario and must be a subset of `Sel(S)`. Example: `S`
  selects `participant_refs: [analyst, observer]`, a binding selects
  `participant_role_refs: [blue]`, and the root adds an unrelated blue
  participant driven by another specification. The binding is then rejected
  with `participant.tool-affordance-participant-widens-parent`, although the
  profile did not change. In a module imported twice, a role-scoped binding
  over module-local actions is rejected for the same reason.
- Conflicts. K2 duplicate relations ignore selectors; the canonical form is one
  binding with the combined selector. K5: two specifications may select one
  participant. A surface projected for `(p, S)` carries exactly the bindings of
  `S` that select `p`, and nothing copies or merges bindings across
  specifications. #301 adds no rule for choosing which specification's surface
  is projected for `p`.
- The participant filter runs before the one-disposition check, so only the
  participant whose own binding disagrees with the action fails to project.
- TP-9. A selector that covers exactly `Sel(S)` gives the same validation
  result, v2 entries, affordance refs, and participant-view digest as no
  selector. The compiled binding record also differs in its dependencies and
  dumped spec, and v1 refuses the scoped form.

Diagnostic codes. The validator emits `participant.tool-affordance-participant-unbound`,
`participant.tool-affordance-role-unbound`, and
`participant.tool-affordance-participant-widens-parent`. The compiler, a defense
for direct callers, emits `participant.tool-affordance-participant-ref-unbound`,
`participant.tool-affordance-participant-role-ref-unbound`, and the same
`participant.tool-affordance-participant-widens-parent`. The split follows the
existing pairs `participant.behavior-spec-participant-unbound` (validator) and
`participant.behavior-specification-participant-ref-unbound` (compiler). The
compiler's selector resolution also makes that existing compiler diagnostic
reachable for a specification with a dangling explicit participant ref.

## Projection, admission, and evidence

- `participant-decision-surface-v1` refuses a specification that contains a
  scoped binding ("participant-scoped tool affordances require
  participant-decision-surface-v2"). ADR-095 section 3 keeps v1 for historical
  validation and migration, and no historical v1 record can contain a scoped
  binding.
- A profile does not gate admission. A participant may invoke any action it
  declares and its specification admits, with or without a binding. A binding
  names the tool affordance offered on the surface for an action, together with
  the bound contract's constraints; it does not restrict what the participant
  can otherwise do (SEM-219 row D; ADR-083 section 1). A role-specific tool
  profile is therefore not a role-specific permission profile.
- Evidence identifies the profile by its address. The v2 assurance carries
  `behavior_specification_address`, and per-role `affordance_refs` are inside
  the participant-view digest that admission binds. The profile's version label
  and content are identified only through the pinned instantiated snapshot,
  whose `canonical_instantiated_sdl_digest` is the value that
  `trial_provenance.instantiated_scenario_digest` must equal. No control-plane
  contract changes.
- `semantic_version` is an authored label that nothing checks, imported or
  local. ADR-053 compares an import's requested version with the module
  descriptor's version, and compares bytes only under a digest pin.

## Capability requirements for #304

#301 adds no manifest field or vocabulary. Which rows need a new field stays
with #304.

| Req | Feature | Existing surface #304 evaluates |
| --- | --- | --- |
| R1 | Parse and validate binding selectors, K3/K4, and the `__private` scan in `sdl-authoring-input-v1` | `processor-manifest-v2` `capabilities.supported_sdl_versions`; the id is unchanged, and the schema-publication ledger records the change |
| R2 | Compile selectors into `ParticipantToolAffordanceRuntime` | `capabilities.supported_features` value `compilation` |
| R3 | Participant-filtered v2 projection, fail closed | no `participant-decision-surface-*` id in processor or backend manifests; `participant-implementation-manifest-v1` lists v2 on the consumer side |
| R4 | v1 refuses any specification with a scoped binding | as R3; a candidate disclosed limitation |
| R5 | New derived documents carry the two keys; older closed readers reject them | schema-publication ledger and compatibility rules |
| R6 | Backend realization of bindings | none: the binding stays compiler IR only (#294), and `backend-manifest-v2` `realization_support` is unchanged |

## Unsupported cases

- a per-surface profile-version field;
- conditional or phase-dependent availability;
- `extends`, inheritance, cross-module overlays, or patches;
- per-binding authority scope or constraint bodies;
- omission of hidden affordances from a surface;
- v1 projection of scoped bindings;
- any tie between `semantic_version` and the module version or content, and
  any immutability check;
- one profile across participants that need different behavior modes,
  autonomy, mixed control, or realization profiles;
- carrying one specification's bindings onto another specification's surface;
- profile-gated admission;
- relative binding selectors;
- role-scoped bindings in a module imported more than once with module-local
  actions;
- backend support claims, which #304 owns.

## Tracked gaps

These pre-existing gaps are neither widened nor fixed here:

- #1498: the existing nested `tool_affordances.*` refs and
  `participant_inject_deliveries.*` refs skip the authored `__private` check.
  This change scans only the new binding `participant_refs`.
- #1570: projection checks the projected action and boundary against the
  specification, not against the projected participant's declarations.
- #1571: projection has no boundary filter, so a binding must be classified at
  every projection boundary, not only at its own.

#1572 is fixed by #1592. Projection reads the view relation by runtime
address, and compilation keys each authored action-contract and binding
classification by its compiled address. Each boundary that a binding in the
#301 fixtures names classifies that binding once, by authored reference.

## Precedents

- N. Schärli, S. Ducasse, O. Nierstrasz, A. P. Black, "Traits: Composable Units
  of Behaviour", ECOOP 2003, LNCS 2743, pp. 248-274, Springer,
  doi:10.1007/978-3-540-45070-2_12. Composition order is irrelevant and
  conflicts are disambiguated explicitly.
- S. Ducasse, O. Nierstrasz, N. Schärli, R. Wuyts, A. P. Black, "Traits: A
  mechanism for fine-grained reuse", ACM TOPLAS 28(2):331-388, 2006,
  doi:10.1145/1119479.1119483, cited for the formal model only.
- R. S. Sandhu, E. J. Coyne, H. L. Feinstein, C. E. Youman, "Role-Based Access
  Control Models", IEEE Computer 29(2):38-47, 1996,
  <https://csrc.nist.gov/CSRC/media/Projects/Role-Based-Access-Control/documents/sandhu96.pdf>:
  permissions from several
  roles combine as a union, and denial is a constraint, not a negative
  permission.
- AWS IAM User Guide, "Policy evaluation logic",
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html>:
  a permissions boundary can
  only reduce. Deny-overrides is the rejected alternative.
- Kubernetes documentation, "Using RBAC Authorization",
  <https://kubernetes.io/docs/reference/access-authn-authz/rbac/>: "Permissions are purely
  additive (there are no 'deny' rules)."
- Model Context Protocol specification 2025-06-18, "Tools",
  <https://modelcontextprotocol.io/specification/2025-06-18/server/tools>: discovery and
  invocation are separate, and listing is not permission.
- E. Debenedetti et al., "Defeating Prompt Injections by Design" (CaMeL),
  arXiv:2503.18813, 2025, <https://arxiv.org/abs/2503.18813>: policy is enforced
  at each tool call, independently
  of what the model sees.
- T. Preston-Werner, "Semantic Versioning 2.0.0",
  <https://semver.org/spec/v2.0.0.html>, rule 3: released contents
  must not change. Here that is an authoring convention that nothing checks.
