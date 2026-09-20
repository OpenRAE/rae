# SEM-235 / #1070 architecture preflight

Date: 2026-09-20.

This is implementation guidance, not semantic publication, an implementation
plan, or evidence of requirement fulfillment. It consumes accepted
[ADR-108](adrs/adr-108-modular-participant-control-and-governed-effects.md) and
[participant-control-composition/rev1, PC-01–PC-15](../research/modular-participant-control/composition.md)
at design acceptance revision `ebb70a34b8e7d1cc8964c443841ae57e12ed1014`.
The adopted decision is sufficient; no new ADR or rewrite of that revision is
needed. #1070 owns formal semantic publication and bounded semantic witnesses.
API-424/#1072 owns closed contracts and the provider protocol; RUN-320/#1069
owns orchestration; ASR-538/#1071 owns independent conformance probes.

## Decisive current-state finding

The supplied `SEM-233` requirement is an ACTIVE security-profile dependency,
not #1070's ownership record. #1070 fulfills the DRAFT `SEM-235` semantic
publication boundary while reusing `SEM-230` and preserving `SEM-233` unchanged;
repository workflow and traceability therefore use `SEM-235`.

The repository already has a complete, deliberately security-specific SEM-233
surface: `ParticipantBoundaryFlowPolicyProfileModel` pins the literal
`participant-boundary-flow-policy-v1@rev1` identity and canonical digest,
`ParticipantFlowControlRelationModel` closes its label/release/sink/carrier
graph, `validate_participant_flow_control_resolved_context()` joins it to
trusted incumbent state, and `participant_flow_sink.py` enforces its negotiated
legacy runtime path. Those artifacts are not a partially generic framework.
Changing their literals, widening their unions, weakening their digest check,
or teaching their validator to accept arbitrary domains would silently migrate
SEM-233 and pre-empt API-424. #1070 instead publishes profile-neutral semantics
and a separately identified non-security domain; #1072 later decides their
closed portable representation and compatibility binding.

## Authority and concept boundaries

- Publish SEM-235 alongside the participant semantics under
  `specs/formal/participant-semantics/`, with a distinct authority revision,
  stable clause identifiers, and explicit correspondence to PC-01–PC-15.
  Reference the accepted architecture rather than maintaining a second editable
  composition contract in research prose. Examples, counterexamples and
  nonclaims must identify the semantic revision they exercise.
- SEM-230's `information-flow-control.md` owns participant/audience projection,
  policy resolution, exact cuts, memory and observable order. SEM-233's
  `adversarial-flow-control.md`, `sem-233/rev1` and
  `participant-boundary-flow-policy-v1@rev1` retain their two independent
  confidentiality/integrity coordinates, release authorities and history.
  New non-security domains get new identities. Extracting shared algebra must
  not broaden the existing literal revisions, rewrite the published profile
  digest, or relabel historical values.
- A participant-control profile selects mechanisms and their obligations. An
  IFC domain supplies one closed algebra. A mechanism instance supplies typed
  results. A policy interprets those results; an effect is independently
  admitted. These are not interchangeable identifiers or states.
- `specs/concept-authority/semantic-profiles.md` / `semantic-profile-v1` describe
  cross-phase interoperability assumptions, not mechanism selection.
  `specs/sdl/profile-selections.md` / `DomainProfileBindingModel` describe
  governed extensions at existing selection owners, not authority to install
  IFC semantics. Their revision/digest discipline is reusable; accepting any
  installed private profile as an IFC domain is not. SEM-234's
  `mixed-participant-composition-profile-v1` governs backend allocation and
  coupling, not the mechanism-result conjunction. SDL module composition and
  runtime-control-plane workflow composition likewise keep their owners.
- Reuse the GOV-917–922 concept catalog, vocabulary, reference-model and profile
  governance. Existing `behavioral-relations` / `policy-noninterference`
  placement is the incumbent for flow claims, not proof that every control
  mechanism is a noninterference relation. Map each actual claim to its owning
  family; do not invent an umbrella ontology, reference model, or wire schema
  solely to make the new vocabulary look uniform. Profile, mechanism, slot,
  resolution-status and effect definitions remain formal-semantic terms until
  API-424 publishes fields that need portable values. Do not predeclare them as
  controlled wire vocabularies without a real `governed_scopes` owner.

## Semantic guardrails that downstream designs must retain

PC-01–PC-15 remain authoritative. In particular:

- Profile selection is exact, finite and revision/digest-bound, including
  applicability, mechanism identity, mandatory/advisory slots, dependencies,
  authority, limitations and bounds. Unresolved applicability is not absence.
  Empty optional selection makes no support claim and removes no incumbent gate.
  Shared instances deduplicate only under the complete binding and state scope.
- Keep resolution status, fact/decision/advice/request payload, composition
  conflict and eventual realization status distinct. Missing, unknown,
  unsupported, stale, failed and weakened are not label values or synonyms for
  deny. Mandatory abstention is unsatisfied; optional advice cannot secretly
  supply a required dependency. All blocking reasons survive deterministic
  ordering. No provider-arrival or lexicographic winner resolves a conflict.
- Domain joins must be total and conservative within their closed carrier,
  associative, commutative, idempotent, monotone and upper bounds. Do not require
  an unadopted least-upper-bound theorem. Unknown coverage is not the empty
  known input/bottom. Track possible data, memory, argument-selection and
  declared control influence; disclose instrumentation limits. Cross-domain or
  cross-revision comparison requires a published mapping and explicit loss.
- Work the first non-security domain as the PC-04 finite powerset of declared
  experimental-influence refs, with subset order, union join, closed source and
  sink rules, retained-memory propagation and an admitted inject-request rule.
  Work SEM-233 separately as its confidentiality/integrity product. Sharing
  algebraic laws must not make the influence set a third SEM-233 coordinate or
  make the security product the universal carrier.
- Known adversarial input may pass an observation sink under its exact policy,
  retain influence and trigger a governed inject. That neither endorses the
  source nor permits downstream actions. Unknown source authority still fails
  closed. Observe-influence is not a weaker spelling of SEM-233 enforcement.
- Independent results bind one exact cut; dependent rules consume declared
  typed slots in an acyclic graph. Pin stochastic assessments as inputs;
  deterministic composition does not promise deterministic provider reruns.
  Mandatory constraints conjoin with existing gates. Advice alone grants
  neither permission nor veto; an admitted rule may request a gated effect.
- Use PC-09's existing effect owners: API-423 crossings/derivations, API-409
  control and review, DSL-111/142 inject occurrence and participant binding,
  API-421/RUN-308 time, and RUN-310 lifecycle. A closed request is not a claim
  that each incumbent DTO already supports it. Gaps belong to API-424; no
  callback, executable expression, open effects map or universal gateway fills
  them. Route is not handoff; review approval is not release or execution.
- Transform/mask/edit produces a fresh proposal or representation; inject
  produces a fresh occurrence. Preserve provenance, influence and ordinary
  downstream admission. Release changes only its authorized coordinate and
  exact result/sink. Handoff, reset and redaction cannot erase obligations.
  Reasons, receipt existence, timing and audit visibility are projections too.
- Preserve PC-10's commit-before-dispatch and final invocation fence. Checking
  history heads and later calling an unfenced target leaves a race. Provider
  next-state refs, decisions, effect claims and budget consumption share the
  atomic transition; speculative state cannot escape a failed commit.
- Fresh identity is allocated once per logical effect key, not once per retry.
  Changed canonical content under a key conflicts. Required predecessors
  withhold the parent until fresh revalidation; subsequent failures do not
  undo an observed parent. Uncertain external dispatch stays indeterminate;
  local persistence proves neither delivery nor distributed exactly-once work.
- Finite root depth, fan-out, firing, effect, resolution/retry and expiry bounds
  survive retry, restart, handoff, reset and derived identities. Exhaustion
  cannot silently drop a required effect or widen permission. Diagnostics must
  not recursively generate new triggers. Trigger budgets are distinct from
  participant resource quotas even where accounting machinery is shared.

## Cross-cutting layers and canonical incumbents

Paths beginning with a package name below are relative to
`implementations/python/packages/`. #1070 states these boundary obligations;
it does not implement new endpoints, validators or stores.

| Layer | Incumbent and required fit |
| --- | --- |
| Semantic publication and governance | Normative prose stays under `specs/formal/participant-semantics/`. Any changed concept-authority JSON must remain under the approved GOV-917–922 surfaces and pass its published JSON Schema, `tools/check_json_artifacts.py` and `tools/check_concept_authority_governance.py`. Lineage updates use `SDLLineageLedgerModel` / `tools/check_sdl_lineage.py`; assurance updates use the existing `specs/formal/assurance-fulfillment.yaml` shape and `tools/check_assurance_policy.py`. Documentation and requirement links still pass the existing docs, repository-policy and requirement-governance gates. Do not add a SEM-235-only parser or validation workflow. |
| Portable ingress and shape | `raes_contracts/json_ingress.py`: `parse_bounded_json_object()` already supports byte and depth limits and rejects duplicate members/non-finite numbers. Downstream API-424 uses it, `StrictJsonIngressError`, `ContractModel(extra="forbid")`, governed revisions, bounded refs and `canonical_json_digest()`. Bound graph work/cardinality separately. No second parser/base model or schema-valid-equals-authorized shortcut. |
| Contextual policy validation | `contracts/participant_flow_control_validation.py` in `raes_contracts` resolves the exact published SEM-233 profile, then calls incumbent action, control, crossing and sink validators. Reuse that trusted-context pattern and `validate_participant_control_occurrence_context()` / `validate_participant_crossing_occurrence_context()`; retain separate structural, graph and contextual gates. Do not generalize the SEM-233 validator into accepting arbitrary new domains or copy its policy into a competing validator. |
| Authentication and authority | `raes_runtime/control_plane_api/_auth.py`, `control_plane_security.py`, `ControlPlaneIdentity`, request-size guards and mutation/idempotency checks retain caller/role/target binding. Participant/controller authority, release authority, rule scope, audience, admission and capability remain independent intersections. #1070 introduces no auth surface or credentials. |
| Final sinks and capability | `raes_runtime/participant_flow_sink.py`, `participant_crossing_state_cut.py`, `participant_crossing_policy.py`, action admission and API-407 `resolve_participant_feature_support()` remain the downstream gates. Serialization, streams, errors, writes and evidence exports are sinks. The optional `resolve_flow_sink_decision` hook and its explicit legacy opt-out are not the new protocol or evidence of modular support; #1069 owns its negotiated replacement. |
| Manifest/configuration shapes | `raes_contracts/contracts/experiment_bindings.py`, participant manifests and `participant_configuration.py` validate target registry, aliases, value types, defaults and complete same-type normalization. Bind admitted configuration identity/digest and exact requested/effective support. A profile or manifest cannot smuggle code via an import, URL, environment value, path or arbitrary options map. Availability does not imply authority or conformance. |
| Secrets and environment | `raes_contracts/secret_references.py` supplies bounded logical secret identities; `raes/runtime_environment.py` and `runtime_values.py` enforce observed-value redaction; runtime-fact policy and `raes_runtime/runtime_fact_dispatch.py` own late-bound dispatch. Carry only safe references where the owning contract permits them. No resolved secret, raw prompt, private state or secret-bearing config in profiles, digest inputs, examples, logs or evidence. A digest is not redaction of a low-entropy secret. |
| Errors, logging and observation | Preserve bounded `ValueError` resolver failures, `CompilationFailure`, `Diagnostic`/`DiagnosticModel`, conformance `sanitized_failure_message()`, and `AuditEvent`. `raes_runtime/control_plane_api/_operation_routes.py` already redacts both unexpected 500 and request-validation 422 responses. Do not serialize raw Pydantic input or provider exception text, introduce another exception hierarchy/logger, or treat audit visibility as participant visibility. Safe refs, coarse reasons and limitations stay audience-governed; logs are not experimental evidence. |
| Persistence and recovery | ADR-104, `ControlPlaneStore.commit_participant_transition()`, `control_plane_store_*`, existing in-memory/local stores, expected heads, scoped idempotency and snapshot migration own state. RUN-320 extends this boundary for provider-state/effect/budget atomicity; no trigger repository, side journal, mutable history or private cache as authority. In-memory evidence cannot establish restart durability. |
| Host/process boundary | Backend calls continue through `RuntimeTarget`, `backend_call_contracts.py` and sanitized `backend_result_diagnostics.py`. #1070 requires no process, socket, daemon, CLI/env binding or secret materialization. Future bindings must keep secrets out of argv, filenames and stdout/stderr and remain operator-bound. Declared-world attacks may be realized; host/provider/credential compromise outside that world invalidates realization and remains backend responsibility. |

## Publication, evidence and workflow fit

Use `contracts/concept-authority/`, its governed vocabularies and reference
models, and the current `contracts/provenance/sdl-lineage-ledger-v2.json`.
The existing SEM-230/233 claims record exact source and RAES boundaries under
`concept-family:behavioral-relations`; extend actual derivation evidence without
rewriting those claims or inventing a compatibility claim. Current ledger
subjects resolve to JSON authorities/pointers; a Markdown section is a semantic
boundary reference, not a replacement JSON authority. Research citations alone
do not establish that join. A semantic term without a published contract field
does not justify an empty governed scope, placeholder schema, or speculative
catalog term; record its definition and lineage in the formal authority and add
machine-readable vocabulary only when an approved existing surface actually
binds it.

`docs/explain/reference/shared-semantic-integrity.md` is the mutable coverage
surface governed by ADR-016. `specs/formal/assurance-policy.yaml` and
`assurance-fulfillment.yaml` retain their evidence classification. Reuse the
SEM-230/233 test-local finite-model pattern (`sem230_information_flow_model.py`,
`sem233_boundary_flow_model.py` and companion tests). The existing
`docs/research/modular-participant-control/check_design.py` is bounded design
falsification only: typed-slot validation, real effect conflicts, concurrent
commit/dispatch fences and crash recovery are not proved by its reducer.
Semantic witnesses need both security and non-security cases, intentional
adversarial delivery/inject, failed conjunctions, order permutations, conflicting
effects, stale cuts, laundering, retry identity and budget exhaustion. Reuse
cases A–G rather than duplicating an alternative acceptance story. Existing
`test_issue_1003_final_sink_flow_enforcement.py` and
`test_issue_1004_apparatus_backend_capabilities.py` remain downstream precedents,
not new SEM-235 runtime evidence. No coverage/status promotion from prose alone.

The workflow incumbents are `.ground-control.yaml`, `.gc/plan-rules.md`,
`tools/policy/requirement_order.yaml`, `noxfile.py`, `tools/verify_all.py`, the
existing CI workflows, and the repo/requirement, concept-authority, lineage,
semantic-coverage, assurance, JSON-artifact and ADR-immutability checkers.
Set `RAES_REQUIREMENT_UID=SEM-235`. Governance now selects the repository source;
do not copy older research notes' retired-HTTP skip as a successful check.
`modular-control-semantics` has its own dependency phase and, in the #1070
delivery diff, exact semantic-publication ownership paths. The governance
witness rejects runtime implementation under this phase. Local verification
uses targeted tests and checks; CI owns repository-wide verification,
completion and policy suites, as required by `/implement` and `.gc/plan-rules.md`.

No schema is required for this preflight. If semantic publication changes an
existing governed catalog's content, follow its existing revision/fixture
rules. If a schema change is actually needed, respect ADR-009/061, the hand-owned
schema, identical `schema_bundle()` output, explicit generator routing and
`check_generated_schemas.py` / `check_schema_publication.py`. The current
publication manifest is an index: hashes and `last_change` belong to the
per-contract `contracts/schema-publication/entries/` record; removals have
tombstones. Do not apply older monolithic-manifest instructions literally or
advertise unpublished API-424 contracts as available capabilities.

## Extensibility seam and non-goals

The seam is a separately revisioned domain/profile authority with a closed
carrier, algebra, source/default, propagation, memory, release and sink
relations, plus explicit typed mechanism slots and mappings. Another
non-security domain supplies that publication and later closed contract
support; it does not edit SEM-233 or add backend-name branches. Future validators
take trusted context/resolver indexes and finite limits. Provider construction
remains operator/backend-owned; shared reference/digest machinery does not
become a runtime code loader or universal policy interpreter.

This work must not deliver a backend engine, provider protocol implementation,
plugin host, scheduler, controller, DTO family, persistence layer, exception
family, secret resolver or new verification workflow. It does not establish
instrumentation completeness, universal noninterference, backend equivalence,
exactly-once effects, controllability, liveness or experimental robustness.
Semantic publication, contract validity, runtime orchestration, installed
provider, declared capability, observed realization, conformance and evaluation
remain separately evidenced stages in the existing delivery graph.

## Gotchas and anti-patterns to reject

- Do not rename generic taint tracking as dynamic IFC without a closed carrier,
  order, join, source/default, propagation, memory, release and sink relation.
- Do not add `labels`, `effects`, `context`, `metadata`, `options` or callback
  bags; arbitrary keys cannot extend semantic authority or select executable
  code.
- Do not collapse profile, domain, mechanism, provider, policy, result slot,
  decision, effect request, commit or realization into one status or DTO.
- Do not treat authentication, authorization, admission, approval,
  declassification, endorsement, redaction, transformation, handoff, delivery
  or observation as substitutes for one another.
- Do not fork API-409/API-423 effects, crossing histories, diagnostics, audit,
  operation persistence, idempotency, recovery or schema/workflow publication
  simply to give participant-control composition a single facade.
- Do not use schema validity, importability, method presence, a manifest claim,
  a profile digest, a local commit or a bounded witness as proof of authority,
  installed support, external realization, conformance or evaluation.
- Do not resolve mandatory conflicts by provider order, lexical order,
  specificity, last-writer-wins or a nominally advisory result. Do not turn
  missing, unknown, unsupported, stale, failed, weakened or exhausted state
  into permission.
- Do not clear influence, obligations, causal roots or budgets on edit, mask,
  transform, route, handoff, episode reset, retry or restart; do not retry an
  uncertain non-idempotent external effect blindly.
- Do not leak governed values, raw rejected payloads, provider exceptions,
  credentials, private state or policy bodies through examples, digests,
  validation errors, audit records, logs, environment, argv or filenames.
