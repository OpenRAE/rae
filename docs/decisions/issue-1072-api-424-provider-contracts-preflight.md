# Issue #1072 — API-424 provider-contract architecture preflight

Date: 2026-09-20. Scope: contract publication, not implementation sequencing.

## Authority and scope

[ADR-108](adrs/adr-108-modular-participant-control-and-governed-effects.md) and
[PC-01–PC-15](../research/modular-participant-control/composition.md), accepted
at `ebb70a34b8e7d1cc8964c443841ae57e12ed1014`, settle the architecture.
[SEM-235 revision 1](../../specs/formal/participant-semantics/modular-participant-control.md)
is present in this checkout (semantic publication commit `65ca8e41`), including
`teaching-influence/rev1` and its two-token domain. Consume that publication,
its [concept placement](../../specs/concept-authority/participant-control.md),
and its bounded semantic witnesses; do not derive a competing algebra from
the older design model. Downstream consumers still need exact released
artifacts: local presence, a requirement UID, or DRAFT status is not release
or runtime evidence. No new ADR or amendment is needed for these guardrails.

The public protocol belongs in `raes_backend_protocols`; portable data and
shared contract validation belong in `raes_contracts`. Follow the existing
`protocols.py` structural-protocol/export conventions, without importing the
runtime or a concrete backend into the contract boundary. RUN-320/#1069 owns
orchestration and replacement of the implicit `resolve_flow_sink_decision`
hook in `raes_runtime/participant_flow_sink.py`. API-424 must not change that
hook, disable default final-sink enforcement, or claim an installed provider.

## Contract decisions

- Publish closed, versioned selection, capability, context, result,
  composition and effect bindings. Keep profile identity, mechanism instance,
  IFC domain, policy revision, protocol version and implementation artifact
  distinct. Participant-control profiles are not semantic interoperability
  profiles, SDL extension profiles, SEM-234 backend-allocation profiles, SDL
  module composition, or control-plane workflow composition.
- Bind the complete MPC-03 context: run/apparatus, participant/episode,
  subject/crossing/direction, sink/audience/destination, controller/authority,
  policy revisions, state cut, expected history heads, provider-state and
  input references, memory scope, governed time/order, trigger root and
  predecessors. Missing applicable coordinates must not become wildcards.
  Profile/mechanism/implementation/configuration identities, digests,
  evidence and limitations travel with each contributor. New bindings never
  rewrite historical ones; shared-instance deduplication requires the entire
  binding, state scope and input set, retaining every selecting profile.
- Separate resolution status from the discriminated payload (IFC fact,
  deterministic decision, advisory assessment, effect request), composition
  disposition, and realization. Preserve missing, unknown, unsupported,
  abstain, deny, withhold, conflict, stale, failed, weakened and applied in
  their owning coordinates. A provider cannot report applied as execution
  authority. Mandatory fact slots need valid facts; decision slots need
  permits. Advice cannot satisfy either by implication.
- Retain all contributors and blocking reasons in canonical instance/slot
  order, including optional failures. Validate finite bounds before accepting
  a composition; never silently truncate its evidence. Typed acyclic
  dependencies and pinned stochastic inputs support deterministic composition;
  arrival order, lexical identity and specificity supply no precedence.
- Resolution receives immutable, detached admitted inputs and proposes a next
  provider-state reference. It cannot mutate authoritative state, another
  provider's inputs, or perform participant/world effects. **`ContractModel`
  only sets `extra="forbid"`; it is neither strict nor frozen.** Use suitable
  strict primitives and immutable nested containers for new protocol values;
  a frozen wrapper around mutable models/lists/maps is insufficient. Do not
  globally freeze or tighten incumbent carriers. References expose no private
  provider memory or executable continuation. External monitor computation
  needs separately admitted apparatus/resource/disclosure authority.
- Preserve SEM-233's two-coordinate algebra and exact profile/digest loader.
  Teaching influence is a separate closed domain, not a third coordinate or
  arbitrary token registry. Missing source coverage is not bottom; editing,
  reset and handoff do not erase influence. A future domain needs published
  algebra, encoding, source/sink and release relations, fixtures and a closed
  contract variant. Unknown revisions and cross-domain coercions fail closed.
  MPC-04 requires a conservative upper-bound join, not a least-upper-bound
  theorem. `teaching-influence/rev1` has exactly `coached-hint` and
  `worked-example`, canonical duplicate-free lexical encoding, and **no release
  relation**. A trusted teacher cannot remove influence under revision 1.
  Its permissive practice/observation sinks still require propagation facts;
  an unclassified source or ungoverned sink cannot inherit that permission.
- Unresolved applicability is an admission failure, not an inapplicable slot.
  A required profile's absence blocks apparatus admission. Selecting even a
  pre-admitted alternative needs a recorded transition at a new cut, effective
  support validation and disclosed weakening; it cannot silently delete an
  overlapping profile's mandatory obligations (MPC-01).

## Reuse incumbent carriers; close the actual gaps

Package paths below are relative to `implementations/python/packages/`;
`contracts/` in the reuse table abbreviates `raes_contracts/contracts/`.

| Concern | Canonical incumbent and required boundary |
| --- | --- |
| Closed data and scalar constraints | `raes_contracts/_base.py`, `contracts/base.py`, `contracts/schema_constraints.py`, `contracts/schema_factoring.py`. Reuse primitives/discriminators; no new DTO base or parallel schema framework. |
| Canonical content and digest | `raes_contracts/_canonical.py::canonical_json_bytes` / `canonical_json_digest` and `satisfiability.py::canonical_contract_digest`. Reuse JCS/SHA-256 for new canonical contract content; preserve incumbent artifact-specific digest rules. Define the exact hashed projection and canonical ordering of set-valued arrays; JCS does not reorder arrays. A digest is not execution identity or permission. |
| Occurrence envelope | `contracts/participant_envelopes.py` and `ParticipantRuntimeBaseEnvelopeModel`. Reuse for participant occurrences, without adding mechanism fields to every incumbent event. Selection/relation documents do not need a fabricated event. |
| Action and control authority | `raes_contracts/participant_binding.py`, `participant_action_arguments.py`, `contracts/participant_control.py` and `participant_control_validation.py`. Reference proposal, approval/denial, intervention, handoff, override and cancellation identities; do not copy their payloads or lifecycles. |
| Crossings and IFC | `contracts/participant_crossing.py`, `participant_crossing_validation.py`, `participant_flow_control.py`, `participant_flow_control_context.py`, `participant_flow_control_validation.py`. Reuse typed subjects, policies, cuts, sinks and legacy joins; do not force non-IFC mechanisms into the SEM-233 relation shape. |
| Inject, exposure and time | DSL-111/142 `ParticipantInjectDelivery`, SEM-226 exposure records, `contracts/time_model.py`, API-421 and RUN-308. Preserve original inject identity, exact addressee/delivery/visibility and clock/expiry; scheduling is not delivery or observation. |
| Lifecycle | `raes_contracts/participant_episode.py`, `contracts/participant_execution.py`, and RUN-310 owners. Participant, episode, workflow and run scopes are not interchangeable; interrupt, cancel, pause and shutdown remain distinct. |
| Apparatus, configuration, evidence and claims | `contracts/experiment_apparatus.py`, `experiment_bindings.py`, `experiment_evidence.py`, `BehavioralClaimBindingModel`, and `raes_contracts/participant_configuration.py`. Use typed owner/configuration bindings, realization provenance and safe evidence refs; a configuration digest or implementation hash proves neither trust nor permission. |
| Declaration and support | `contracts/feature_support.py`, `participant_manifests.py`, `raes_backend_protocols/participant_feature_admission.py::resolve_participant_feature_support`. Reuse exact/bounded/disclosed-weak/unsupported and authorized downgrade evidence. Manifest declaration, installed binding, effective support at a cut, conformance and observed realization are independent facts. |

MPC-09 is the effect-owner map. Requests need closed alternatives for all its
effects, with exact target, rule/revision, authority, predecessor/subsequent
phase, causal references and bounded parameters. In particular, existing
approval and cancellation records do **not** already supply every review,
delay or shutdown request:

- Review binds the withheld parent, supervisory authority/obligation,
  approval/denial references and governed expiry/resumption. Approval does
  not itself dispatch the parent; resumption requires a fresh cut.
- Delay binds a declared clock and compatible time window/expiry. Window
  intersection cannot mix incomparable clocks or become unbounded sleep.
- Interrupt/shutdown uses an explicit supported target alternative and its
  owning lifecycle authority, never a PID, native handle or process signal.
- Transform/mask/route creates or references the fresh candidate and lineage
  required by its owner. Handoff preserves obligations. Audit uses the
  existing evidence/audit carrier and audience, not a new output channel.

Do not overload `ParticipantControlTargetKind` into a universal target enum,
or fill absent request shapes with `effects`, `context`, `metadata`, callbacks
or a nullable universal gateway DTO. Incompatible replacements, routes,
handoffs or lifecycle outcomes conflict. Ordered dependencies and revalidation
are necessary for interacting effects; lexical sorting only serializes them.

## Cross-cutting validation and security boundaries

| Layer | How the intended contract design must satisfy it |
| --- | --- |
| Byte/parser ingress | Reuse `raes_contracts/json_ingress.py::parse_bounded_json_object` with explicit byte and depth limits. It rejects duplicate members, invalid roots and literal NaN/Infinity, but its current decoder accepts `1e999` as infinity. Require finite numeric validation before composition or hashing, including direct Python inputs. Bound artifact reads as well as decoded input; a parser limit after an unrestricted file read is not a memory bound. Harden shared ingress where necessary rather than introduce a second parser. |
| Portable shape | Closed normative JSON Schemas and matching `ContractModel` models reject unknown fields, branch mismatch, invalid revisions/digests, duplicate identities and invalid scalar types. Do not rely on Pydantic coercion where the schema rejects a value; test booleans as integers, numeric strings and non-finite advisory scores. Bound strings, collections and dependency graphs appropriately. |
| Exact artifact/configuration resolution | Follow `participant_flow_policy_profiles.py`: portable identifier validation before path construction, exact revision/digest lookup and `corpus.py` packaged resources, no latest fallback or caller-selected search root. Reuse `participant_configuration.py` and `contracts/experiment_bindings.py` owner/type/normalization/digest checks where configuration bindings are consumed. Provider installation config stays backend/operator-owned; portable selection cannot name import paths, commands, URLs or environment expressions. |
| Cross-record semantic authority | Follow `validate_participant_flow_control_resolved_context`: trusted non-wire indexes resolve exact subjects, evidence, authority, profile/policy, sink, cut and history. Compose API-409/API-423 and SEM-233 owning validators, adding only modular joins. Provider/caller supplied indexes cannot certify their own authority, freshness, installation or capability. A missing resolver fails closed. Do not duplicate these joins in routes, stores, backends or conformance. |
| Authentication and effect authorization | Publication adds no route or live invocation. Later consumers must retain `ControlPlaneSecurityConfig.strict_defaults()`, `_ControlPlaneApiAuth`, verified bearer/proxy identity, role/target and participant/controller/audience bindings, plus `RequestSizeLimitMiddleware`. Independently conjoin current rule scope, principal authority, target support, action admission, projection/crossing and final-sink gates. Portable authority refs are not credentials; authentication does not grant declassification or endorsement. |
| Secrets and environment shapes | Portable records and fixtures contain safe bounded refs, not prompts, credentials, private model state, raw rejected content or external-apparatus details. A string/ref/digest field is not automatically safe. Retain trusted evidence resolution and projection; hashing a secret does not authorize disclosure. No new environment/config bag is needed. If downstream integration uses node environment bindings, `raes/runtime_environment.py::RuntimeEnvironmentVariable` enforces name, `value`/`value_from` exclusivity, generated-source classification and `runtime_values.py::enforce_observed_value_redaction`; do not bypass these with provider metadata. Existing secret-reference bindings are not executable provider selectors. |
| OS/process boundary | API-424 adds no subprocess, host filesystem selector, socket, secret loader or backend launcher. Do not put provider payloads/credentials in argv, environment, temporary filenames, stdout/stderr or shell interpolation. Host/provider protection is backend responsibility and cannot be claimed from schema validity or recast as a participant attack. |
| Errors, logging and observability | Use `raes_contracts.diagnostics.Diagnostic`, existing dispositions/receipts and `raes_conformance/conformance/diagnostics.py` sanitization. Never expose raw `ValidationError`, provider exception text, input values, unknown keys, tracebacks or model reprs. Retain coarse HTTP conflict/error envelopes in `control_plane_api/_responses.py` and `_operation_routes.py`, and existing rejection auditing. No new exception tree, logger or audit channel. Apply SEM-224 plane classification (`raes/observability_plane_semantics.py`, `x-raes-plane`) and SEM-220/226/230 projection to reasons, evidence, review/withhold existence and timing as well as values. |
| Persistence and final dispatch | Contracts carry expected heads, provider-state references, logical effect identity, budgets and realization refs for existing `RuntimeSnapshot`, `ControlPlaneStore`/`AtomicControlPlaneStore`, operation receipts and `AuditEvent`. RUN-320 must extend these authorities, including both memory/local store paths, rather than snapshot metadata or a second trigger store. Contract validity does not prove atomic commit, freshness at invocation, crash durability or external execution. |

Publish non-schema-expressible obligations using
`contracts/schema_invariants.py::_add_raes_invariant` and the existing
`x-raes-invariants` profile. Integrate with
`raes_conformance/conformance/validators.py` so schema-only validity is not
reported as resolver-backed validation. Local structural checks, shared
contextual joins and runtime freshness/authorization each have one owner;
they are complementary gates, not three copies of composition semantics.

Diagnostic reuse must respect `tools/policy/adr_policy.yaml` package boundaries:
`raes_contracts`, `raes_backend_protocols` and `raes_runtime` cannot import
`raes_conformance` to obtain its sanitizer. Contract validators use stable,
value-independent failures; conformance uses its own existing sanitizer, and
runtime uses `backend_result_diagnostics.py` and its existing coarse envelopes.
Serialize through `raes_contracts/diagnostics.py::portable_diagnostic_payload`
where required by the transport. Its closed `DiagnosticModel` checks code,
domain, JSON-Pointer address and bounded message shape; it does not redact
sensitive text. Sanitize before constructing the diagnostic, including its
address, and do not expose provider-chosen exception class names. Rejection
audit failure must retain the original coarse response, as in
`control_plane_api/_operation_routes.py`.

## Causal and recovery compatibility

The contracts must represent MPC-10–12 without implementing its executor:
provider-state proposal, decision, budgets and authorized effect intent share
the existing expected-head commit. Failed commit means no dispatch; a later
head check alone is not a dispatch fence. Required predecessor effects withhold
the parent until fresh revalidation; subsequent effects have independent
outcomes and cannot erase an already applied parent.

Logical effect identity is `(run, trigger root, rule id/revision, slot, admitted
firing epoch)`. Retry count, current cut and transport identity are not part of
that key. Same key/different canonical content conflicts; retries retain the
allocated effect identity. Preserve indeterminate external realization after
uncertain dispatch, distinct from failed and applied. No exactly-once or
cross-effect transaction claim follows from a local commit. Finite depth,
fan-out, per-root effects, per-rule firings, attempts and expiry survive retry,
handoff, reset and restart; diagnostics cannot recursively trigger effects.

## Publication, extensibility and acceptance boundaries

Use `contracts/schemas/` as normative authority (ADR-009/061), with matching
`contracts/bundle.py`/`bundle_runtime.py`, exports and explicit routing in
`tools/generate_contract_schemas.py`. Its default directory is `control-plane`:
a new name alone will misplace a participant-runtime contract. Use the current
v2 publication manifest's `contracts/schema-publication/entries/` and
`tombstones/`, with `last_change`/content hashes and base-revision compatibility
checks. Do not copy older preflight instructions to embed v1 ledger entries
in the manifest or use pre-rename invariant names.

New published IDs/scopes must agree across manifest allowlists/capability
requirements, controlled vocabulary governance, concept placement, semantic
invariant and observability annotations, schema bundle, conformance registry
and installed corpus. The declaration owner is
`raes_contracts/manifest_authority.py`, consumed by the manifest models and
feature admission; a new schema ID alone is not an admissible support claim.
Follow `tools/check_generated_schemas.py`,
`check_schema_publication.py`, `check_authority_boundary.py`,
`check_concept_authority_governance.py`, `check_sdl_lineage.py`, existing public
API docs and `implementations/python/pyproject.toml` corpus packaging. Update
lineage only for an actual derivation/compatibility change, not to claim runtime
delivery. `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py` and
`tools/nox_support/` remain workflow owners; use `RAES_REQUIREMENT_UID=API-424`
when the branch lacks a UID. Add no issue-local runner or release machinery.
`tools/policy/requirement_order.yaml` assigns SEM-235 to the bounded
`modular-control-semantics` phase and API-424 to `modular-control-contracts`.
The supplied SEM-235 payload is semantic input to #1072, not authority to
classify provider/contract implementation as semantic publication or widen
that phase's path ownership.

The extensibility seam is an operator-bound provider protocol over exact,
immutable typed context/results, with trusted resolver context supplied out of
band. Parameterize exact revisions, applicability, role/slot dependencies,
state scope, authority, resource bounds and supported effect targets. This
permits another independently installed provider for an existing semantic
profile without editing its canonical artifact or adding backend-name branches.
A new domain/effect meaning needs a governed closed revision/variant and
negotiation; an open map, structural method check or import is not that seam.
Preserve old schemas and explicitly negotiated SEM-233 behavior; do not upgrade
legacy evidence merely because a new protocol can be imported.

Use the existing dual JSON-Schema/Python and resolver-backed patterns in
`test_sem_233_flow_control_contracts.py`, API-409/API-423 tests, SEM-235 finite
witnesses and corpus packaging tests. Acceptance evidence must cover multiple
mechanisms and order permutations; teaching/SEM-233 separation; IFC-triggered
inject and review/delay/lifecycle targets; conflicting requests; stale/mismatched
cuts and provider state; missing/abstaining/failed mandatory slots; advisory
failure; explicit weakening; dishonest support/installation claims; unknown
revisions; parser limits; mutable aliasing; secret-bearing errors; and unchanged
legacy acceptance. Distinguish schema-invalid fixtures from structurally valid
but semantically rejected records. Passing fixtures proves bounded contract
behavior, not provider realization or backend conformance.
The SEM-235 oracle's one symbolic rule node per request is an explicit model
limit, not a portable restriction: MPC-07 permits multiple effect slots for
one rule. Preserve slot-indexed bindings and test them independently. Its
assumptions about trusted resolution, immutable state and a correct dispatch
fence must not be promoted into tested contract or runtime guarantees; see
[semantic verification limits](../research/modular-participant-control/semantic-verification.md#executable-evidence-and-assumptions).

Non-goals: no provider discovery/installation, plugin host, concrete engine,
policy interpreter, runtime invocation/composition scheduler, effect execution,
HTTP endpoint, persistence migration, backend parity claim or ASR-538 proof.
No duplicate action/crossing/inject/intervention/lifecycle/evidence hierarchy,
exception hierarchy, schema registry, validation framework or workflow logic.
