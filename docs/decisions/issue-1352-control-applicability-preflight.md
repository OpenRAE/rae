# Issue #1352 — Control applicability, dependencies and effect decisions

Date: 2026-09-22. Inspection baseline: `c3a9154b9be8`.
Scope: architecture preflight for SEM-235/API-424; guidance, not a normative
amendment, implementation plan or fulfillment claim.

## Authority and observed gaps

[ADR-108](adrs/adr-108-modular-participant-control-and-governed-effects.md),
[SEM-235](../../specs/formal/participant-semantics/modular-participant-control.md)
and the [API-424 preflight](issue-1072-api-424-provider-contracts-preflight.md)
remain the foundations. This note qualifies the earlier guidance where the
issue requires a new decision; it does not supersede published revision 1.
Package paths below are relative to
`implementations/python/packages/`. The issue's `runtime-refactor` diagnosis
files are absent from this checkout; the findings below come from current
repository sources, not those files' pinned revision.

| Current incumbent | Design gap to close explicitly |
| --- | --- |
| `raes_contracts/contracts/participant_control_composition.py::ParticipantControlRequestModel._admitted_scope` | Requires every apparatus binding to match one crossing, and provider-state coverage of every binding. Filtering the selection would instead break the runtime's exact admitted-selection digest check. Neither represents an applicable subset of an unchanged apparatus. |
| `contracts/participant_control_selection.py::_selection_graph` (under `raes_contracts`) | Required profiles need only appear in bindings; zero result slots are accepted. Profile presence is not proof that its obligations are covered. |
| `raes_backend_protocols/protocols.py::ParticipantControlProvider.resolve` and `raes_runtime/participant_control_orchestration.py::_mechanism_results` | Each provider receives the same request in binding order, with no typed predecessor-result input. Topological validation of recorded results does not establish dependency-aware evaluation. |
| `raes_contracts/contracts/participant_control_composition.py::_support_blockers` | Every non-exact or unresolved support record blocks, regardless of mandatory dependency closure. This gives optional support failure a veto and cannot express an admitted bounded requirement. |
| `participant_control_effect_composition.py::control_effect_blockers` and `participant_control_composition.py::admitted_effect_phase` in the same package | Effect phase can change a parent-targeted denial into eligibility or withholding; one global admitted phase cannot express independent consequences of a denied parent. |

A read-only probe using `participant_control_contract_fixtures.evaluation_payload`,
the public derivation and evaluation validator confirmed: parent-targeted
`deny`/`subsequent` and `withhold`/`subsequent` produce `eligible`;
`deny`/`required-predecessor` produces `withhold`; a required profile with no
slots produces `eligible`; failed optional advice with unsupported provider
support produces `unsupported`. These are bounded structural/composition counterexamples, not
proof of bypassing trusted-context validation or live authorization.

## Guardrails for the decision

**Apparatus, obligations and applicability are separate coordinates.** Preserve
the complete admitted selection and its identity. At an exact cut K, resolve
the obligations of every required profile independently of the providers that
happen to respond. Record which slots/providers cover them, which are proven
inapplicable, and which have unresolved coverage. Bind inapplicability evidence
to the exact selection, profile revision, subject, sink, phase and K; a missing
provider, omitted result, mismatch or exception is not such evidence. Reject
ambiguous coverage and unexplained omission. Overlapping profiles retain every
obligation and selecting owner, even when one exactly shared instance serves
them. An empty applicable subset is legitimate only with complete coverage
accounting and satisfied incumbent gates. `None` must not conflate an unbound
optional apparatus with failed resolution of required coverage. A new cut
invalidates the old applicability proof; changing the apparatus requires its
own admitted transition. These distinctions belong in the existing contract
family, not a second apparatus registry.

**Dependencies govern invocation as well as composition.** Retain a finite
typed DAG and pin predecessor result identities, content, resolution status,
binding and cut in each dependent invocation. Supply detached, immutable,
disclosure-authorized inputs; never let providers discover predecessors through
ambient state or caller-supplied authority indexes. Define the invocation unit
explicitly: a slot DAG can require A.fact → B.assessment → A.rule, which an
unqualified once-per-provider call cannot realize. A slot/stage-aware protocol
or an explicitly restricted supported graph must make that case unambiguous;
do not add a general workflow engine. Independent ordering is immaterial only
with evidenced independence. A deterministic composition consumes recorded
stochastic assessments; it does not silently resample them on retries.
The invocation must identify the requested slots/stage and permitted input
projection. A dependency authorizes neither disclosure of another provider's
private state nor transmission of the complete apparatus context. Bind outputs
to that invocation and its exact predecessor inputs, not only to a shared K.
Define finite input/result and invocation bounds before expanding dependencies;
a byte limit on a serialized evaluation cannot bound a live provider iterator.

**Mandatory closure is an admitted obligation.** A mandatory consumer's entire
required input closure must have the required typed results and support.
Required availability of an advisory assessment does not grant its score or
negative opinion veto authority; only the admitted decision rule interprets
it. Declare that dependency at admission, without silently promoting optional
advice during execution. Truly optional missing, failed, malformed or
unsupported contributions produce safe lost-advice evidence and cannot block
the parent through support checks, result validation, conflict accounting or
effect admission. This does not excuse malformed apparatus, unknown coverage
or forged shared authority; those remain admission failures. Failure of a
required input does block its mandatory consumer. Distinguish an evaluated
rule whose trigger is false from an absent mandatory result; an effect slot
must not force fabrication of an effect to
prove the rule ran. Preserve all reasons, not just the displayed disposition.

Normalize a rejected optional contribution into an explicit, value-safe failure
at its declared invocation boundary before shared composition validation.
Keep the complete outer record closed and valid; catching an arbitrary
whole-evaluation error as "lost advice" would hide mandatory failures and
forged bindings. Failure isolation must respect shared mandatory state and
dependency closure rather than trust a response's claim to be optional.

Required support strength and admissible constraints belong to the admitted
obligation. Reuse API-407's `resolve_participant_feature_support`, API-424's
`resolve_participant_control_support` and `ControlEffectiveSupportModel`;
do not add a second strength ranking. Bounded support is usable only when its
actual coverage/constraints satisfy the requirement at K. A rank comparison
alone is insufficient. Falling below the requested strength requires an
authorized, separately identified effective binding and disclosed claim limits;
a downgrade token never makes unmet requirements disappear.

**Parent decision, effect target and execution dependency are independent.**
Reuse `ControlDecisionModel`, the closed `ControlEffectTarget` alternatives and
their owner identities. Settle how existing permit/deny/withhold effect targets
map to decisions, rejecting contradictory or ambiguous encodings. A phase is
ordering information, never permission to reinterpret a decision.

| Meaning | Required invariant |
| --- | --- |
| Deny or withhold the parent | The parent is respectively refused or pending in every phase. Permit cannot override either; deferring a denial until after dispatch is invalid. |
| Required predecessor | Commit a pending parent and separately authorized prerequisite. Only its exact successful owner outcome can satisfy that dependency; re-evaluate the parent at a fresh K before release. Completion cannot erase another deny/withhold reason. |
| Consequence dependent on parent success | Bind the prerequisite to the relevant owner outcome (commit, dispatch and application are distinct). Failure of the consequence does not rewrite an applied parent. |
| Independent consequence of a disposition | An admitted rule may request audit/review for a denied or withheld parent. That request has its own target, authority, support, conflicts and outcome; it neither inherits parent permission nor releases it. |

Resolve effect-dependency order together with parent prerequisites: a slot DAG
alone misses a cycle in which a predecessor effect waits for parent success.
Reject cycles, incompatible phases and stale/mismatched realization receipts.
Retain the MPC-07 conflict rules; lexical/provider order cannot repair competing
replacements, routes or lifecycle outcomes. A transformation replaces the old
proposal with a fresh, traceable candidate that re-enters ordinary admission;
it must not both release the original and dispatch its replacement. Do not
conflate completing a prerequisite with superseding the parent.

**State and commit have one authority.** Define provider-state read/write scope
separately from participant memory and profile identity, including explicit
sharing across slots, profiles, participants or episodes. Existing
`ControlProviderStateModel`, `next_provider_state`, memory references and
expected history heads are the starting point. One invocation's speculative
next state must not become another's ambient committed state. Multiple writers
require a declared ordered transition or a conflict; never last-result-wins.
Shared-instance deduplication requires equal configuration, authority, inputs,
state scope and exact binding, not just an implementation name.

Use the ADR-104 `ControlPlaneStore`/`AtomicControlPlaneStore` authorities for one
expected-head/snapshot-revision commit of the decision, provider-state changes,
authorized effect intents, claims and budget consumption. Cover every shared
state scope in that concurrency boundary; an unsupported cross-store atomicity
claim stays unsupported. A refused parent may still have an explicitly defined
evaluation-state transition, but no discarded candidate may mutate state.
Store failure or a stale cut prevents dispatch. Preserve final-invocation
fencing and ordinary revalidation; a provider re-entry fence is neither a
process sandbox nor a wall-clock timeout.

Logical effect keys and allocated fresh identities survive retries; changed
intent under an existing key conflicts. Reuse the committed-history budget
fold, extending its authoritative scope if a root crosses participant histories
instead of resetting counters. Preserve finite depth, fan-out, firing, attempt
and expiry bounds through handoff/reset/restart. Uncertain dispatch remains
indeterminate pending exact readback/idempotency evidence. Local atomic commit
does not establish distributed exactly-once execution or rollback.

## Cross-cutting owners and gates

The design must pass all applicable layers below. Documentation introduces no
new route, environment binding or launcher; later consumers still pass these
incumbent gates rather than treating portable records as authorization.

| Layer and canonical incumbents | Required treatment |
| --- | --- |
| Ingress: `raes_contracts/json_ingress.py::parse_bounded_json_object`, `parse_participant_control_evaluation`, `raes_runtime/control_plane_api_guards.py::RequestSizeLimitMiddleware` | Bound bytes/depth before decoding and bound artifact reads. Reuse rejection of duplicate members, wrong roots, NaN/Infinity and overflow such as `1e999`; the overflow gap mentioned in the older API-424 preflight is already fixed. |
| Shapes: `contracts/base.py`, `participant_control_coordinates.py`, selection/results/effects models, schema constraints and factoring under `raes_contracts` | Closed, bounded, versioned alternatives; strict scalar validation, finite numbers, unique IDs and finite graphs on both JSON and direct Python ingress. Revalidate portable projections to defeat unchecked model construction. `ContractModel` alone is neither strict nor deeply immutable. No new DTO base, open metadata bag or duplicate schema. |
| Package/protocol boundary: `raes_backend_protocols/protocols.py`, `raes_contracts/contracts/_participant_control_exports.py`, `tools/policy/adr_policy.yaml`, `tools/policy/repo_policy.py::_check_backend_protocol_contract_annotations` | Public predecessor inputs and results use neutral `raes_contracts` DTOs. The protocol package may import only that repository package; no runtime/conformance/backend imports, public `Any`, or open `object`/kwargs escape hatch. Reuse diagnostics in each owning layer; importing the conformance sanitizer into contracts/runtime violates the dependency boundary. |
| Semantic joins: `derive_control_composition`, `validate_participant_control_resolved_context`, API-409/API-423/SEM-233 owner validators | One shared derivation for recorded and live decisions; independently trusted, non-wire indexes resolve coverage, support, authority, predecessors, safe references and receipts. Add the missing joins there, not copies in routes, runtime, stores or conformance. Schema validity is not resolved authority. |
| Artifact/configuration resolution: `participant_control_profiles.py`, `participant_flow_policy_profiles.py`, `corpus.py`, `participant_configuration.py`, `contracts/experiment_bindings.py` | Exact revision/digest and typed owner/normalization checks. JCS via `_canonical.py`/`control_digest` with explicitly defined projections and set ordering; preserve incumbent digest conventions. No latest fallback, caller-selected path root, arbitrary URL fetch, import path or executable configuration. A digest is neither trust nor secrecy. |
| Authentication/authorization: `ControlPlaneSecurityConfig.strict_defaults()`, `control_plane_api/_auth.py`, `participant_effect_authority.py`, `participant_control_receipts.py` | Retain verified bearer/proxy identity and actor/role/target/audience checks. Providers cannot confer principal or release authority. Independent effects retain their originating `OperationAdmissionContext`, then re-enter ordinary owner, capability, crossing/projection and final-sink gates. The drain caller is separately authorized before reading committed state and does not become the effect principal. |
| Secret/environment/host boundary: `raes_contracts/secret_references.py`, `raes/runtime_environment.py::RuntimeEnvironmentVariable`, `runtime_values.py::enforce_observed_value_redaction` | Safe references only in portable inputs, state and evidence; no raw secrets, prompts or private provider memory. If a realization uses environment bindings, retain valid names, `value`/`value_from` exclusivity, generated-source classification and redaction. Never transport credentials or provider payloads in process argv, shell interpolation, temporary filenames or diagnostic output. This issue needs no secret-file reader or provider launcher; out-of-world host/tenant/network integrity remains backend-owned. |
| Errors/observability: `raes_contracts/diagnostics.py`, `raes_runtime/backend_result_diagnostics.py`, `participant_control_diagnostics.py`, `control_plane_api/_responses.py` and `_operation_routes.py`, `control_plane_audit.py` | Closed coarse reasons and existing receipts/audit, without raw provider exceptions, validation values, unknown keys or tracebacks. `portable_diagnostic_payload` checks shape, not redaction. Sanitize before construction, including addresses. Audit failure must not replace the original safe response. Apply `raes/observability_plane_semantics.py`, `x-raes-plane` and participant projection to dependencies, applicability, denial/review existence and timing as well as values. No new exception tree, logger or evidence channel. |
| Persistence/recovery: `raes_contracts/participant_control_evaluation_history.py`, `raes_runtime/participant_control_causal_state.py`, `participant_control_records.py`, `participant_control_receipts.py`, store memory/local implementations and record migration | Keep runtime-owned evaluation history append-only, exact replay commitments and owner receipts. Route new meaning through version-aware history validation/folding; do not reinterpret old phase decisions or recalculate old effect claims under new rules. No second provider-state store, trigger ledger or snapshot metadata shortcut. |
| Runtime integration: `participant_control_binding.py`, `participant_control_orchestration.py`, `participant_crossing_commit.py`, `control_plane_mutation.py`, `participant_control_effects.py` under `raes_runtime` | Preserve operator-bound providers, detached inputs, external-call re-entry fencing, expected-head commit and independent effect-owner dispatch. These are downstream consumers of the contract decision, not places to invent missing semantics. API-404 transport/durability profiles, SDL workflow orchestration and SEM-234 backend allocation remain distinct. |

## Publication, migration and extensibility

The issue's decision and SEM-235/API-424 amendments must agree with MPC-01/03/
05–11, ADR-108, concept placement, worked cases and the contract correspondence.
Changing an accepted ADR uses ADR-059's in-band amendment plus `adr-index.yaml`
pin/record (or explicit supersession), checked by `check_adr_immutability.py`;
do not silently edit the accepted decision. This preflight changes neither ADR
nor requirement. Preserve SEM-233's published two-coordinate security algebra,
release authorities and history, and the separate closed teaching domain.

Publication authority remains `contracts/schemas/`, matched by
`raes_contracts/contracts/bundle_runtime.py`, exports, `schema_invariants.py`
annotations and `raes_conformance/conformance/validators.py`. New identities
also reach `manifest_authority.py`, API-407 capability requirements, explicit
directory routing in `tools/generate_contract_schemas.py`, corpus packaging in
`implementations/python/pyproject.toml`, fixtures and public documentation.
Use `contracts/schema-publication-manifest.json` v2 and its per-schema entries
for hashes/`last_change`, plus tombstones for removal; do not recreate a ledger.

API-424's selection/evaluation schemas are currently **draft**: ADR-061 permits
recorded in-place schema changes, while stable breaking changes need a new
contract ID. That flexibility does not permit changing `sem-235/rev1` history
or silently extending `participant-control-provider/v1`. The decision must
identify new semantic/protocol meaning, negotiation and exact supported schema
content, with explicit old/new reader behavior. Preserve historical decoding
and receipt/claim meaning; legacy records missing coverage/dependency evidence
cannot be upgraded into new guarantees. Unsupported consumers fail closed;
never infer protocol support from a `resolve` attribute or method signature.

This is also a storage-read constraint: `RuntimeSnapshot.__post_init__`,
`participant_control_evaluation_history.py`, `causal_state_from_history` and
`dispatch_participant_control_effects` validate retained evaluations; the last
two derive admitted effects using the shared composition functions. Changing
those functions globally can reject an old snapshot or change which old
requests consume budgets or become executable. Historical interpretation and
new live admission must select their declared semantics explicitly. A record
without enough version/content identity requires an explicit legacy migration
disposition, never guessed new applicability or a replayed provider call.

The extensibility seam is the existing revisioned selection and provider
protocol: parameterize obligation coverage/applicability, typed predecessor
inputs, invocation and state scope, required support/constraints, effect target
and dependency on parent disposition/outcome. Another sink or independently
installed provider for the same semantics should use those bindings without
editing the profile algebra or adding backend-name branches. A new domain,
effect meaning or release rule still requires a governed closed revision;
neither an open predicate language nor a universal target enum is warranted.

Repository gates remain `.ground-control.yaml`, `.gc/plan-rules.md`,
`tools/policy/requirement_order.yaml`, `tools/policy/adr_policy.yaml`,
`noxfile.py`, `tools/nox_support/`, `.pre-commit-config.yaml` and CI. SEM-235,
API-424 and RUN-320 have separate path ownership; #1352 needs an explicit
requirement-scope disposition for its cross-owner publication, not expanded
semantic ownership of runtime code. Set `RAES_REQUIREMENT_UID` on this
UID-free branch. Reuse generated-schema/publication, authority-boundary,
concept-authority and SDL-lineage checks when their governed artifacts change.
Keep traceability honest; no new runner, release/version edits or hand-written
changelog. Local verification uses targeted cases or `verify-fast-feedback`;
full policy/test/integration/fuzz/completion suites remain CI-owned.

## Evidence boundaries and non-goals

Reuse `sem235_modular_control_model.py`, `test_sem_235_modular_control.py`,
`test_api_424_composition_derivation.py`, `test_api_424_composition_boundaries.py`,
`test_api_424_control_resolution.py`, and the API-424 publication/governance
tests under `implementations/python/tests/`. The decisive cases are mixed
ingress/egress applicability under one unchanged apparatus; proven
inapplicability versus unknown coverage; omitted mandatory obligations;
A → B → A provider dependencies; optional failure versus mandatory input
closure; satisfied/insufficient bounded support; false triggers; parent denial
and withholding in every phase; independent audit of a denial; phase cycles;
shared-state conflicts; stale cuts; and old-history replay without new claims.
Use existing RUN-320 fixtures for downstream memory/local-store, re-entry,
atomicity and zero-dispatch evidence when runtime delivery is in scope.
Bounded witnesses establish neither production realization nor noninterference.

Non-goals: implementing the requirement during preflight; inventing a provider
engine, plugin host, policy interpreter, workflow scheduler, HTTP endpoint,
credential/configuration system, universal control hierarchy or persistence
authority; changing SEM-233; backend instrumentation, parity or availability
claims; executing effects merely because a schema accepts them. Admission,
authority and realization remain separate decisions throughout.
