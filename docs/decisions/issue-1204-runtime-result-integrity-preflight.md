# Issue 1204: realization authority and runtime-result integrity preflight

Recorded 2026-09-11 against `4914612d`. Requirements: ASR-532, SEM-218,
SEM-219. Status: non-normative implementation guidance, not an implementation
plan or an ADR ratification.

ADR-004/036 already assign this boundary to the runtime. ADR-105 and the
[recursive constraint contract](../../specs/sdl/recursive-realization-constraints.md)
supply its relation; the [governing design intent](../research/language-extensibility/design-intent.md)
supplies its scope. No new ADR, semantic engine, or backend certification layer
is needed. ADR-105 remains proposed; #1204 owns its production amendments and
ratification, with version/migration mechanics coordinated with #1210. The
provided issue names #1200, #1212 and #1112 as native blockers and #1202/#1203
as dependencies. This inspection does not certify their current GitHub status;
dependent implementation must observe the native blocker gate. PR #1158 is
superseded, not a design starting point.

## Findings at this revision

- `raes_runtime.backend_calls._call_backend_apply()` already isolates the input
  snapshot and routes returned state through shape, address, result/history,
  time-transition, realization, and credential checks before acceptance.
  `_changed_address_transition_diagnostics()` only checks membership in the
  union of predecessor/successor carrier addresses; it does not establish that
  an address changed, that all changes were reported, or that a change was
  authorized.
- `test_issue_158_runtime_result_integrity.py` still has four strict expected
  failures: unauthorized portable addition, resource-type rewrite, missing
  change accounting, and runtime-domain rewrite. The reference control and
  predecessor-return rejection pass: **2 passed, 4 xfailed** in this inspection.
- #1203's `RealizationConstraintDocument` and bounded recursive evaluator exist,
  but compiler lowering, resolved authority, and runtime matching still use
  the legacy `RealizationStructure` subset and registered concern projections.
  `realization_runtime_evaluation` still uses full projection equality for some
  decisions. A standalone normal-form schema is not end-to-end enforcement.
- `plan_projection` excludes the internal `resources` map from published plans.
  Existing resolved authority is attached to operation concerns; neither that
  map nor `plan.operations` alone transports a general enclosing collection's
  authority. Do not infer global closure from either absence.
- #1212 separates observation demand and transient operational observations,
  including demand-selected compute-substrate readback. Other registered
  concerns still acquire fixed scope/strength through
  `compiler.realization_requirements` calling
  `semantics.realization_operational_verification.operational_verification_requirement`.
  Support admission and runtime corroboration consume those fields. This is
  not yet proof that all verification requirements follow selected demand or
  an independently applicable operational contract.

## Authority and relation

Carry one admitted recursive authority through lowering, plan projection,
authenticated submission, realization comparison and disclosure. Reuse
`raes_contracts.realization_structure.evaluate_realization_constraint`,
`bounded_domains`, and `domain_profiles`; extend their existing compiler and
plan carriers rather than adding a second tree or normalizer. Preserve leaf
domains, presence, local closure universe/profile revision, stable member
identity, defaults and author provenance. The legacy projection is derived and
losslessly checked, never independently editable. Only `conformant` admits a
result; invalid, unresolved, unsupported and limit-exceeded remain distinct
diagnosed failures.

Open scopes delegate unspecified descendants. They neither weaken exact
siblings nor turn unknown/redacted values into permission. Required, optional
and forbidden members remain different. Closed membership is exhaustive only
inside its named universe; syntax closure (`extra="forbid"`) is a different
concern. Core and selected extension fields use the same relation and pinned
profile metadata, not one registry entry per new leaf. Preserve SEM-219's
participant/tool/affordance owners and separate software presence, acquisition,
and final configuration; backend recipes are not compulsory author data.

An additional portable entry needs positive authority from the admitted
enclosing structure/collection, an unambiguous semantic identity, permitted
cardinality, an owning runtime domain and valid dependencies. A merely open
field inside an existing node does not authorize another node. An exact five-node
inventory cannot become six. An explicitly open node inventory can admit a
supported additional node. An incidental backend installation choice outside
the portable universe is not another authored resource. The four existing
perturbations must still reject under their actual fixture's authority, with a
separate positive open-collection case proving the distinction.

Bind plan-owned address, resource type, ordering/refresh dependencies and
identity-bearing payload fields to trusted submitted authority. An open payload
does not authorize rewriting these fields. Reuse `require_compiled_address`,
`require_plan_operation_identity`, the domain/type tables in `planning`, and
the owning resource/profile identity rules; do not add backend-name checks or
derive authority from an address prefix alone. Preserve unrelated predecessor
entries and carriers. Legitimate participant, workflow, evaluation and time
operations can affect several carriers: their existing transition contracts
define the permitted effects, not a blanket single-dictionary rule.

The admission claim must also name its quantifier. ADR-070 universal
`subsumes(B, R)` remains containment. Delegated execution selects and delivers a
supported witness satisfying the entire conjunction under execution policy;
one witness does not establish coverage of every possible distribution/version.
Reuse `realization_support_diagnostics`, manifest validation and capability-domain
admission. Revise the negotiated gate explicitly with #1210 where needed; do
not silently reinterpret subsumption as overlap. Unknown support fails before
mutation when knowable. A supported backend choice is not missing author input,
and a complete abstract model needs no invented concrete machine or capture.

## SEM-218 adoption boundaries

These are migration obligations at the inspected revision, not new meanings
for existing contracts. Amend and ratify ADR-105 with the production decision
and coordinate its negotiated revision with #1210. In particular, the formal
SEM-218 spec still describes registered realization points and the #1200
compatibility fragment; broad recursive adoption cannot be authorized by
silently widening that fragment or citing the research oracle as enforcement.

- **Separate similarly named concepts.** `RealizationAuthorityMode.CLOSED`
  denies materialization of an omitted concern; it is neither `EXACT` nor
  `RealizationClosurePosture.CLOSED`, which restricts additional members in a
  named universe. `source=apparatus-default` records who resolved a legacy
  posture; it is not the recursive value's `origin=default`. Source, binding
  origin, selected value and author constraint remain separately meaningful.
  Compatibility must preserve the accepted relation, not match enum spellings.
- **Make carriage complete and authenticated.** Both `planning` and
  `contracts.realization_plans` currently restrict authority to non-delete
  operations; `planner.realization_authority` derives its inventory from
  registered concern descriptors. A recursive collection scope cannot simply
  be appended to that inventory. Evolve the existing portable plan contract
  with explicit scope ownership, retaining duplicate/pointer/domain checks.
  Include the recursive document, profiles, claim revision and applicable
  demand in forward/reverse codecs and trusted plan/request commitments.
  Reassess `_plan_authorization_diagnostics`' empty-operation exemption wherever
  delegated authority could permit effects: zero operations must not become
  an unauthenticated resource-creation capability. Preserve legitimate
  observation-only plans under their own admission. The same effect
  classification must reach `observation_admission`, whose mandatory-observation
  atomicity gate currently relies on `actionable_operations`. Manager-only supplemental
  requirements in `_supplemental_realization_requirements` also need an
  explicit carriage or readmission owner; HTTP submission has no compiler
  requirement tuple to recover a dropped obligation from.
- **Preserve meaning through projection and hashing.** The plan digest helpers
  use `model_dump(..., exclude_none=True)`; on `RealizationLiteral(value=None)`
  that drops its required `value` and prevents round-trip. Preserve explicit
  null while distinguishing absent/default metadata. The current typed runtime
  projector sorts every sequence of records; ordered recursive sequences must
  retain their occurrence order. Selected collection metadata must govern
  normalization before safe projection, comparison, digesting and scope
  rewriting. Test relation-preserving round-trip, not just DTO equality.
- **Keep authority safe to publish.** Legacy exact nodes are value-free;
  recursive literals and domains carry values. A wholesale dump of authored
  configuration into plan authority would create a new disclosure route.
  Reuse `realization_concern_projections`, `realization_typed_runtime_projection`,
  `validate_typed_runtime_observation`, typed secret references and the existing
  presence/commitment contracts. Each sensitive leaf needs a safe representation
  that preserves its admitted relation; unsupported projection fails before
  mutation. Do not weaken the constraint to presence-only, expose arbitrary
  variable domains, or claim that a digest proves range membership or independent
  observation. Scan authority, profiles, provenance and error envelopes as well
  as ordinary operation payloads for prohibited raw material.
- **Select a joint witness under a named claim.** The current
  `realization_envelope_diagnostics` calls universal `subsumes` for open paths.
  Its replacement admission mode must explicitly distinguish chosen delivery
  from full-envelope coverage, without changing `subsumes` itself. Reuse
  `feasible_operating_system_domains`' coupled compatibility rows and selected
  envelope/configuration identity; independently nonempty leaf domains are
  insufficient for a joint witness. Bind any preselected choice or subsequent
  backend selection to the original constraint and selected target. Defaults
  may guide choice but cannot override explicit descendants, execution policy
  or experiment allocation/randomization.
- **Admit extensions for their actual use.** Build on
  `domain_profiles.admit_domain_profile_bindings` and exact offline profile
  resolution, with namespace, authority, revision, definition digest, supported
  operations and bounded schema vocabulary checks. The report's `admitted`
  property can include non-binding `opaque-preserved` exchange: that outcome
  must never authorize execution or satisfy a binding extension constraint.
  Profile graph-reference membership does not itself check whole-graph cycles;
  retain the owning graph validator. Bound work before projection, copying and
  canonicalization, not only inside the final recursive matcher.
- **Attribute every verification floor.** Trace the remaining operational
  scope/strength fields through compiler, support admission, plan authority,
  observation binding and `_corroboration_diagnostic`. Preserve floors selected
  by an actual contract; do not rename an automatic inventory scan
  "operational" to bypass #1212 policy. A requested choice report can use honest
  backend-selection knowledge without independent readback. Missing required
  knowledge remains unresolved; no-demand is not false conformance. A conflict
  between a prohibition and required operational input needs admission failure.
  Compare choices and coverage with the same constraint relation while keeping
  strength, augmentation, timing and retention independently governed.

## SEM-219 participant boundary

[ADR-083](adrs/adr-083-participant-tool-decision-surface-and-exposure-semantics.md)
and the [participant semantics](../../specs/formal/participant-semantics/README.md)
remain the authority for tool identity, authored availability, visibility,
support, eligibility, admission and realized exposure. #1204 carries realization
constraints through their existing owners without creating another tool catalog,
availability flag or action policy. Paths below are under
`implementations/python/packages/`.

| Existing owner | Required composition with recursive realization |
| --- | --- |
| `raes.participant_behavior_specification.ParticipantToolAffordance`, `raes.semantics.participant_behavior._tool_affordance`, `raes.validator._participant_tool_affordances` | Keep the closed reference binding under its behavior specification. Action and observation refs cannot widen parent or participant scope; optional `tool_ref` must resolve to governed tool/artifact identity. Software presence, a package recipe or a manifest expectation grants no participant affordance. |
| `raes_processor.compiler.participant_behaviors._compile_tool_affordances`, `ParticipantToolAffordanceRuntime`, `compiler.addresses` | Preserve canonical binding identity and joins to action contracts, observation boundaries and the owning behavior specification. This IR is not a provisioning operation. Delegation cannot replace an exact tool identity or weaken the referenced action's parameter, authority, target, knowledge, resource or temporal constraints. |
| `raes_processor.models.decision_surface_v2`, `participant_exposure_v2`, `raes_contracts.participant_binding_v2`, `raes_runtime.participant_decision_surface_control_v2` | Reuse trusted state-cut, participant/episode/audience, policy revision, selected apparatus and delivery resolution. A conforming resource snapshot does not prove visibility, delivery or invocation. Requested backend-choice reports still pass exposure and information-flow gates; a report request is not disclosure authority. |
| `raes_runtime.participant_control`, `participant_crossing_policy`, `raes_backend_protocols.capability_admission` | Preserve ordinary action admission, authenticated crossing identity, deny-first semantic gates and selected feature-support levels. Recursive conformance is an additional obligation. Unknown support is not execution permission; declared availability is not current eligibility. |
| `raes_contracts.participant_configuration` and `contracts.experiment_bindings` | Reuse registry alias resolution, declared target/value validation, atomic owner normalization and selection/configuration digests. Preserve the complete target set, owner/manifest identity, default/override origin and literal/secret-reference disposition. Delegated infrastructure choices do not excuse genuinely required participant control inputs. |

An open software inventory may admit another implementation component without
adding an authored affordance. An open field within one tool realization cannot
grant another action or observation boundary. Exact tool identity or descendant
values create no automatic report/capture/retention/export demand; selected
evidence obligations remain binding at their actual scope and strength.

Participant-native results retain their specialized checks in
`participant_action_validation.autonomous_action_result_violation`,
`participant_scheduler_operations` and `participant_scheduler_concurrent_commit`:
bound terminal outcomes, append-only history, scheduler ownership and current
execution generation. Compose shared integrity with these owners; do not coerce
`ParticipantActionApplyResult` into a generic result that loses its action
outcome. Concurrent settlement preserves other accepted participants' changes
through the existing serialized merge and history-head checks. Owner validation
errors can contain input values; expose bounded diagnostics, not raw exceptions.

The participant extension seam is its existing binding address plus trusted
selection/state-cut context and governed configuration target/profile revision.
Future tools vary these inputs without changing availability or visibility
meaning. Reuse the SEM-208 tool-affordance and SEM-220 v2 projection/admission
tests, RUN-319 policy tests and participant concurrent-commit tests. Cross-stage
regressions must show that a permitted realization cannot widen participant
grants, retarget an exact binding or revive stale delivery/selection authority.

## Acceptance, transitions and trusted state

Keep `_call_backend_apply` / `_finalize_backend_apply` as the single acceptance
coordinator for manager, direct control-plane and cleanup calls. Extend the
existing call context with the trusted operation/domain and admitted authority
needed by each call family. Provisioning-only `_RealizationApplyContext` cannot
by itself describe orchestration, evaluation, participant actions or `stop()`
calls without a plan. Missing authority on an effect-capable path must have an
explicit owner-specific admission rule, never mean unrestricted writes.

Capture predecessor and authority independently of backend-owned mutable
objects. The current snapshot copy is useful; `_bind_submitted_plan()` uses a
shallow dataclass replacement, so nested operation payloads can still alias the
comparison authority. Protect the submitted authority too, and detach accepted
mutable state from backend aliases. Frozen dataclasses do not freeze their
nested dictionaries. This prevents ordinary mutation/aliasing errors; it is not
containment of hostile Python running in the same process.

Validate result shape before traversal, including an actual boolean `success`,
entry/carrier types, diagnostic fields, canonical unique changed addresses and
serializable bounded details. Constructors and `isinstance` alone do not
revalidate mutated objects. Materialize permitted diagnostic iterables once
within bounds and handle invalid iteration/validation as boundary rejection.
Backend invocation exceptions and post-return validation failures both need
the incumbent failure envelope; neither may escape as an accepted candidate.

Changed addresses describe authorized semantic transitions, not every unequal
byte and not just the set of actionable plan addresses:

| Operation | Successful-claim obligation |
| --- | --- |
| CREATE | Admitted predecessor absence, successor presence with authorized identity/value, and reported change. |
| UPDATE | Predecessor and successor retain identity; delivered state satisfies the admitted update, and the action is accounted for. Dependency-driven refresh is an existing UPDATE even when portable payload bytes are equal. |
| DELETE | The authorized predecessor entry is removed and reported using its predecessor address. Dependent references/carriers follow their owning lifecycle rules; returning it unchanged is not successful deletion. |
| UNCHANGED | No resource semantic change or false change claim. The incumbent `applied` to `unchanged` status annotation alone is not a resource change. Any newly selected delegated value that does change accepted semantics must follow an authorized, accounted transition. |

Reuse `semantics.planner.reconcile_resource_actions`, refresh propagation,
`planner.ordering._entry_matches_resource`, and the existing owner projections.
Make their comparison agree with the shared admitted relation without equating
constraint satisfaction with transition equality: two different allowed values
can both conform while still constituting a change. Equal bytes on a declared
refresh also do not prove an infrastructure effect. Do not invent observation
to make that claim stronger. Reject omitted changes, duplicates, phantom
addresses, false UNCHANGED reports and unauthorized removals as well as additions.

Account for results/history/time carriers, not only `entries`.
`_snapshot_carrier_addresses()` is currently a hand-maintained inventory and
omits participant closure and resource budget/pool/event carriers. Require an
exhaustive classification against `RuntimeSnapshot` fields, like the durable
codec's completeness guard: each field has an owning transition/accounting
rule or an explicit non-addressed metadata/projection rule. Do not stringify
arbitrary mapping keys into admitted identities or allow unclassified new fields.
Reuse `workflow_result_contract_diagnostics`,
`evaluation_result_contract_diagnostics`, `proposition_truth_contract_diagnostics`,
participant state/history validators, and `validate_time_runtime_transition`;
the conformance package already consumes runtime result validators.

A rejected successful claim returns failure with the untouched trusted
predecessor, no rejected changed addresses, no arbitrary backend details and no
success provenance. Evaluate authority before lossy sanitization could hide a
violation. Sanitization is limited to the existing explicitly allowed safe
projections; it cannot repair forbidden membership or silently relabel identity
or domain. The final sanitized candidate must still satisfy the contract and
accounting. Keep selected operational observations transient and attach only
runtime-produced admitted provenance.

The predecessor is the state immediately before that backend call. In a
multi-phase apply, earlier accepted phases and separately authorized cleanup
may remain visible. An honest failed backend result can carry contract-valid
partial cleanup inventory; `_post_apply_contract_result` deliberately suppresses
observation-success demands for that case. Do not indiscriminately replace every
failure with the initial run snapshot or erase recoverable resources. Existing
credential plans have stricter failure preservation rules. Result rejection
does not roll back infrastructure or justify automatic backend replay.

`RuntimeDurabilityMixin`, `SnapshotState`, `ControlPlaneStoreCommitAdapter`, and
the in-memory/SQLite stores remain the publication boundary. Commit only
admitted content with the captured `expected_revision`, existing history-head
checks, terminal record/audit and selected observation retention transaction.
Publish caches after commit. Preserve `SnapshotRevisionConflict` handling and
uncertain-store-outcome recovery as separate paths. A failed terminal operation
may durably record the same predecessor content and advance its store revision;
ASR-532 does not require operation/audit/revision records to remain unchanged.
Reconciliation and teardown must consume the same admitted collection authority
so permitted additions are not later deleted merely for lacking authored ops.

## Cross-cutting layers and canonical incumbents

Paths below are under `implementations/python/packages/` unless qualified.

| Layer | Incumbents and required treatment |
| --- | --- |
| Source and semantic ingress | `raes._base.SDLModel`, safe YAML/source/key validation, `SDLParserLimits`, composition provenance, designation resolution, `SemanticValidator`, `phase_contracts`: keep closed source shapes, duplicate/ambiguous-reference rejection and source/import budgets. Preserve absent/default/authored distinctions and canonical pointer rewriting. No second parser or provenance ledger. |
| Recursive/config admission | `RealizationConstraintDocument`, `RealizationConstraintLimits`, `RealizationCollectionProfile`, `bounded_domains`, `domain_profiles`: pass explicit bounded limits and pinned identity/closure profiles, including direct JSON/model ingress. Preserve strict JSON type equality (`true` is not `1`), null versus absence, keyed collection versus ordered sequence, aliases and reference-hop limits. No network profile resolution or Cartesian-product capability enumeration. |
| Plan/DTO/handoff | `CompiledRealizationRequirement`, `CompiledRealizationAuthority`, `ResolvedRealizationAuthority`, `ProvisioningPlanModel`, `plan_projection`, `control_plane_api_models`, `RuntimePlanAuthorizationMixin`, `manager_plan_admission`, `control_plane_submission`: carry all admitted authority and demand through both codec directions, domain-tagged digests and request commitments. The runtime registration and authenticated caller supply authority; possession of a digest alone does not. Bind target, manifest and predecessor; reject tampered/dropped authority before backend `validate`/`apply`. No internal-only authority sidecar omitted by serialization. |
| Backend target/config | `registry._validate_runtime_target_shape`, `raes_backend_protocols` manifests/protocols and planner manifest/capability validators: retain callable signatures, component/manifest coherence and selected semantic support. Supporting a shape is not proof of manifest truthfulness. No permissive configuration flag to skip integrity enforcement. |
| HTTP and runtime authorization | `ControlPlaneSecurityConfig.strict_defaults`, `_ControlPlaneApiAuth`, `RequestSizeLimitMiddleware`, bounded `_ControlPlaneCallExecutor`, `runtime_owned`, existing participant policy/crossing gates: retain bearer/trusted-proxy authentication, exact target/role/audience binding and mutation ownership. A conforming backend result grants no caller or participant access. CLI/MCP remain adapters to these owners. |
| Secrets and environment shapes | `account_credentials`, `backend_account_credentials.sanitize_account_credential_result`, `RuntimeEnvironmentVariable`, generated-value/file validators, `BindingValue`/`SecretReferenceId`, `participant_configuration`: keep value/reference exclusivity, sensitivity/redaction, duplicate environment identity and reference-disposition checks. Returned configuration must pass the same owning closed validators. Credential sanitization's closed plan-entry rule is deliberately stricter; do not copy it as universal closure or bypass it for open collections. Supporting that combination requires an explicit safe contract, otherwise reject before mutation. No secret resolution, ambient env lookup or secret values in portable authority, diagnostics, details or snapshots. |
| Host/process boundary | The relation and integrity gate perform no subprocess, driver probe, filesystem inspection or URI fetch. Reuse `raes_reference_backend.drivers.oci` for fixed argv, runtime-name validation, bounded timeouts and redacted native errors; `raes_backend_libvirt.drivers.seed` retains exclusive private artifact creation and controlled command execution. Preserve `runtime_generated_value.resolve_consumable_generated_artifact_output` and generated env-file name confinement. Do not add an external validator command or place credentials, raw configuration or result payloads in argv, stdout/stderr, logs, temporary files or crash diagnostics. No new deployment/configuration surface is needed. |
| Errors and observability | Reuse `Diagnostic`, `Severity`, `_failure_diagnostic`, `runtime.backend-contract-invalid`, and `portable_diagnostic_payload`. Use stable, bounded invariant-specific code/address/message combinations; preserve deterministic precedence and test exact diagnostics. `DiagnosticModel` requires bounded strings and RFC 6901 addresses: internal dotted locations need the existing portable converter. Do not expose raw values, `ValidationError` input, backend exception text or payload reprs. Preserve shared redacted HTTP 422/500 and conflict envelopes, `OperationStatus`, `operation_terminal_diagnostics`, `AuditEvent`, bounded rejection audit and module logging; no new exception hierarchy or telemetry plane. |
| Observation and disclosure | `observation_demand`, `observation_execution`, `backend_observation_calls`, `realization_operational_verification`, `realization_snapshot_sanitization`, observation binding and experiment realized-form contracts: compare declared choices at their honest basis. #1212 determines effective demand; #1112 owns actual required capture admission. Exact detail creates no capture/retention/export obligation. Preserve selected corroboration, augmentation, scope/strength and operation/manifest binding. Enforce prohibitions before collection and retention before persistence; no probe-as-validation shortcut. Current mandatory observation-plus-mutation and export admission restrictions remain until their execution owners support them. |
| Durable/API representation | `RuntimeSnapshot`, `RuntimeSnapshotEnvelopeModel`, `_snapshot_payload`/`_snapshot_from_payload`, `_require_complete_runtime_snapshot_fields`, `_snapshot_model`, `RuntimeDurabilityMixin`: reuse one portable schema and codec, private SQLite/WAL ownership and atomic revision checks. Candidate state and transient readback must not leak through API, recovery, histories or retention before acceptance. Store CAS is concurrency protection, not semantic validation or backend rollback. |
| Repository/evolution | `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/policy/adr_policy.yaml`, `noxfile.py`, `tools/check_repo_policy.py`, `tools/check_requirement_governance.py`, `tools/verify_all.py`, `.pre-commit-config.yaml` and `.github/workflows/canonical-verification.yml` (called by `ci.yml`): preserve module dependency/size rules and the canonical verification graph. The runtime may consume only the public compiler/models/planner processor surfaces; backends cannot import `raes_processor` or `raes`. Keep pure relations in contracts and expose processor coordination through its existing public facade. Published schema changes require the matching `schema_bundle()` output, `contracts/schema-publication-manifest.json` ledger/tombstones, generated-schema checks and governed migration; do not hand-bump release versions or edit `CHANGELOG.md`. Set `RAES_REQUIREMENT_UID=SEM-218` on this UID-free branch and maintain eventual IMPLEMENTS/TESTS traceability without claiming this note implements a requirement. |

## Extensibility and verification boundary

The extension seams are the existing recursive document revision, explicit
collection/profile identity metadata and `limits`, plus trusted call-domain /
operation authority supplied to the existing result coordinator. Another
collection or backend must not require another matcher, backend-specific
closure rule or global leaf catalog. A new snapshot carrier must declare its
owner and transition/accounting treatment; it cannot inherit permission from
being a dictionary. Keep authorization, semantic comparison, accounting and
safe publication distinct responsibilities within the established boundaries.

Acceptance evidence must retain the real reference control and convert the four
#158 xfails to ordinary regressions asserting exact invariant diagnostics and
the complete predecessor snapshot, including histories/metadata, empty rejected
change claims and absence of leaked details. Keep the already-passing predecessor
case. Exercise nonempty predecessors, mutable input/return aliases, CREATE /
UPDATE / refresh / DELETE / UNCHANGED, unrelated-domain changes and honest partial
failure cleanup. Boundary-level tests must distinguish malformed shape from
semantic rejection rather than passing on construction errors.

Use existing `test_issue_1200_mixed_runtime_constraints`,
`test_issue_1203_recursive_normal_form`, `test_issue_1067_resolved_realization_authority`,
`test_sem_218_runtime_realization`, `test_runtime_result_envelope_properties`,
`test_issue_673_account_credential_bindings`, #1212 boundary tests, and runtime
manager/control-plane/API/durability suites. Trace nested core and extension
constraints through both plan codecs and authenticated direct submission;
include valid delegated witnesses, exact siblings, permitted/forbidden extras,
collection reorder/duplicates, unknown capability, limits, selected observation
strength and no-demand/no-capture cases. A tampered plan must fail before calls;
a rejected result must survive durable reload as predecessor content plus an
honest failure record. Schema-valid error/response and negative leakage checks
must cover all portable egress, not only the immediate return value.

SEM-218 migration coverage also needs explicit null through plan digesting,
ordered record sequences through safe projection, closed omission versus
closed membership, constrained extension versus opaque exchange, an empty-op
plan carrying effect-capable authority, and coupled witness selection. Keep
these separate from the four completed #158 characterizations: they exercise
additional boundaries that a runtime-only result check cannot establish.

## Repository-governance synchronization repair

The repository-backed requirement gate retains phase ordering, lifecycle and
exact traceability checks. During an in-progress integration merge it checks
the delivery diff against the actual `MERGE_HEAD`, provided that commit is in
`refs/remotes/origin/dev` history. This includes already-committed feature work
and conflict resolutions without attributing unchanged imported files to the
feature's requirement. A later remote-tip advance does not replace the pinned
merge parent. Missing or unrelated integration evidence retains the ordinary
local-diff checks; explicit paths, explicit bases and staged-versus-working-tree
selection retain their existing behavior. Real temporary-repository regressions
exercise each selection boundary. Other repository-policy checks are unchanged.

## Non-goals and anti-patterns

This work validates RAE-owned claims at execution admission. It does not certify
external backends, verify manifest truthfulness, observe infrastructure, contain
malicious in-process code, prove exactly-once effects, implement compensation,
or supply comprehensive backend acceptance testing. Public software syntax,
report/export delivery, capture integration and global migration retain their
separately assigned owners.

Avoid operation-list closure, blanket dictionary equality, truthy relation
outcomes, re-derived defaults presented as author facts, sanitized-away authority
violations, backend-authored provenance treated as trusted, unchecked metadata
escape hatches, duplicate DTOs/validators/exception hierarchies, and independent
CLI/MCP/store acceptance workflows. Passing a finite semantic model, a shape
validator, an authenticated digest check or a store transaction does not replace
the other boundaries.
