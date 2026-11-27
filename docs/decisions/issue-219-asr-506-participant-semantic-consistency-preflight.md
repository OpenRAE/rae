# ASR-506 participant semantic consistency preflight

Issue: #219. Re-inspected: 2026-10-29, HEAD `8ae926b2`, branch
`219-behavior-model-retired-classification-refs`, including the existing staged
changes. This is a working-tree assessment, not evidence for the supplied
`origin/dev` review baseline or a clean committed tree.

This is advisory architecture guidance, not a new semantic authority, completed
coverage assessment, or implementation plan. ASR-506 needs reconciliation of
existing artifacts. No replacement participant model, schema, service, or ADR
is justified by the supplied scope.

## Authority and scope

Use the normative authority allocation in
[ADR-009](adrs/adr-009-normative-artifact-authority-and-repository-structure.md)
and `specs/authority/authority-boundary.yaml`. Published schemas are governed
authority; Python models and generated output are consistency witnesses, not
permission to change meaning. A disagreement must be resolved against governed
decisions and contracts, rather than copying whichever file was edited latest.

The following are inspection boundaries, not a substitute for the required
clause-to-contract-to-implementation-to-test coverage:

| Concern | Existing semantic home and implementation boundary |
| --- | --- |
| Behavior and interaction | `specs/formal/participant-behavior-model/README.md`, participant-semantics SEM-208/209/211, SDL `agents.*` and `behavior_specifications`, `raes.semantics.participant_behavior`, and `raes_processor.compiler.participant_behaviors`. Action contracts own action meaning; authored bindings, apparatus support, and realized history remain separate. |
| Visibility and decision surfaces | Participant-semantics SEM-210/214/216/219/220/226, information-flow-control, ADR-095, published decision-surface v1/v2 contracts, `raes_processor.models.decision_surface_v2`, and runtime `participant_decision_surface_control_v2`. Participant views exclude assurance-only evidence unless separately authorized. |
| Timing and causality | Participant-semantics SEM-212/213, `raes_contracts.participant_temporal`, `participant_concurrency_time`, attribution contracts, and existing history validators. Clock domains, episode generations, causal frontiers, decision epochs, and policy-effective orders are distinct. Temporal order alone supplies no causal attribution. |
| Outcomes | Participant-semantics SEM-215 and `local-outcomes.md`, `raes.semantics.participant_outcome`, published outcome-report v1/v2, runtime `participant_result_contracts`, and outcome history. Action status, local attainment, objective truth, workflow completion, evaluation, and reward require their own relations and evidence. |
| Information flow and control | Focused SEM-230–235 specifications, exact published profiles, API-409/API-423/API-424 contracts, and RUN-310/319/320 consumers. Profile declarations, installed enforcement, observations, and proof claims have independent support. |

The detailed clause/evidence index already exists at
[`specs/formal/participant-semantics/semantic-coverage.md`](../../specs/formal/participant-semantics/semantic-coverage.md)
and its five part files. Its parity guard is
`implementations/python/tests/test_issue_219_participant_semantic_coverage.py`.
The separate family-status summary at
`docs/explain/reference/shared-semantic-integrity.md#coverage-model` is governed
by ADR-016 and checked by `tools/check_semantic_coverage.py`. Extend these
existing records and owning clause tables; do not move the detailed matrix
into the summary or create another registry. Neither structural check proves
semantic completeness or the truth of an `active` claim. Matrix `covered`
and family `active` have different definitions; do not translate them by name.

ADR-067 and ADR-083 remain **proposed**. Delivered contracts do not promote those
decisions. ADR-095 is the **accepted** executable decision-surface amendment.
Any edit to an accepted ADR, including an editorial correction, follows
[ADR-059](adrs/adr-059-adr-amendment-policy-and-pin-gate.md):
amendment record and matching manifest/pin update, or explicit supersession.
Prefer correcting current entry-point guidance without changing accepted text
when no decision changes. Historical prose and evidence keep their original cut.

The consistency assessment must include these accepted decisions and their
linked normative clauses:

| Decision | Boundary the assessment must preserve |
| --- | --- |
| ADR-108 | Modular control and independently governed effects; declared-world boundary; amendments from ADR-111/114. Profile/provider facts execute nothing themselves. |
| ADR-109 | `agents` keys identify participants; affiliation, effective role, objective owner, assignment, controller, and realized actor attribution are independent. Use the shared identity/selector resolvers in `specs/sdl/participant-identity.md`. |
| ADR-110 | MC-01–MC-09: reusable permission policies and immutable occurrences; revision fencing, source-controller authority, exact-cut validity, and original-policy replay. |
| ADR-111 | CA-01–CA-09: complete apparatus versus applicable slots, obligation coverage, required dependency closure, optional advice, independent effect authority, and atomic commit before dispatch. |
| ADR-112 | EI-01–EI-06 in `specs/sdl/external-injects.md`: independent world effects need no synthetic participant. Request, occurrence, attempt, result, delivery, and observation remain different facts. |
| ADR-113 | Execution machinery may be reused without transferring RAE semantic authority. Local and distributed compositions share contracts; selection of an architecture is not evidence of an installed guarantee. |
| ADR-114 | IFC-01–IFC-07: authored guarantees, finite published profile expressibility, and evidenced realization remain separate. Owner obligations cannot collapse merely because audiences coincide. |

Use [revised-control-semantics.md](../explain/reference/revised-control-semantics.md)
for current installed support and explicit refused combinations. Acceptance-time
statements that a design adds no runtime are historical boundaries, not proof
that later implementation remains absent. Conversely, passing individual
runtime arrangements does not establish their combined support.

Also apply accepted ADR-115: concrete backends and their live evidence producers
are outside this repository. Retained captures describe their original producers;
they are not installation instructions or current RAES backend certification.
Do not inspect another checkout to fill this repository's evidence gaps.

## Current findings and reconciliation traps

- The supplied ACT-606 classification mismatch is already corrected in this
  working tree: the aggregate omits native classification fields and ACT-609/610
  describe generic bindings. Current
  `raes.participant_behavior_specification.ParticipantBehaviorSpecification`
  inherits `LegacyClassificationGuard`, which rejects
  `ai_offensive_behavior_refs`, `defensive_behavior_refs`, and
  `offensive_behavior_refs`, including empty lists. Preserve that correction;
  never restore fields, aliases, or extension-bag substitutes. The ACT-606
  inventory now has a different mismatch: it omits the existing `control_context`
  model field. Use its current SDL/ACT-620 contracts, not a new context model.
- The replacement is the existing scheme-neutral
  [external-concept binding contract](../../specs/concept-authority/external-concept-bindings.md),
  `raes.external_concept_subjects`, and
  `raes_contracts.external_concept_bindings.admit_external_concept_bindings`.
  Bind the entire subject coordinate, including owning contract, lifecycle
  phase and digest, to an exact scheme revision. Bindings assert relationships;
  they supply no native action meaning, truth, capability, permission,
  disclosure, or attainment. Native manifest `ConceptBinding` has a different
  owner and purpose. Older preflight notes cannot override this contract.
- Historical decision-surface v1 `observation_order` selects a behavior-history
  occurrence. Actionable v2 uses a derived `decision_epoch`, trusted readiness
  or terminal-observation anchor, exact state cut, participant-view digest,
  cut-specific policies, and validated delivery. Epoch zero needs no fabricated
  behavior. V1-to-v2 conversion requires trusted reprojection, not a rename.
  Projected, disclosed, delivered, observed, selected, admitted, attempted, and
  successful remain distinct facts; derivation and delivery cuts may differ.
  The retained `ParticipantControlMixin.admit_participant_decision_surface_selection`
  still admits v1 under its historical meaning. Keep that path visible in the
  matrix; do not claim v2 removed it or that it supplies v2 delivery guarantees.
- API-409 occurrence v2, API-424 evaluation v2, and decision-surface v2 are
  independent lineages. Wire version, semantic revision, profile revision,
  schema digest, policy identity, and persistence version must not substitute
  for one another. Historical occurrences, policy readers, retry identities,
  consumed budgets, provenance, and outcomes must not be rewritten.
- The participant-semantics README's older sufficiency discussion still lists
  participant `entity` framing. Reconcile such current guidance with ADR-109;
  do not infer identity, assignment, authority, or attribution from affiliation.
  Author-facing identity/migration guidance remains owned by #1342.
- The formal README now correctly describes the oracle's canonical positive
  control, heading/catalog checks and targeted mutations over a test-local
  model. Preserve that narrow claim; its green result establishes neither
  property-based production coverage nor completeness of the clause matrix.

The targeted two-module run at this cut returned **43 passed, 3 failed**.
All three failures are existing consistency gaps, left for implementation:

| Gap | Existing acceptance guard | Boundary to preserve |
| --- | --- | --- |
| PBM-13 has no matrix row | `test_clause_rows_match_their_source_in_both_directions[PBM]` | ACT-619 tool-profile bindings narrow selection without granting availability, visibility or admission. Extend the existing matrix; do not freeze it at PBM-12 or weaken source parity. |
| `participant-crossing-runtime-mapping.md` has no family-row reference | `test_every_focused_specification_is_named_by_a_family_row` | Reuse the SEM-232 mapping and its exact model, projection, catalog pins and bounds. Observed runtime compatibility, finite exploration and equivalence proof remain separate. |
| ACT-606 omits `control_context` | `test_act606_aggregate_matches_the_behavior_specification_model` | Preserve the existing ACT-620 reference, scope, digest, privacy and lifecycle boundaries; model-field parity is a drift detector, not authority to change a published contract. |

The matrix's advertised counts and PBM-01–PBM-12 scope therefore describe its
present inventory, not a complete current assessment. These guards cover only
their declared clause universe: passing them would not prove that ADR-108–114,
current revised-control support or every new SDL clause has been mapped.

## Cross-cutting layers to reuse

The intended change is documentation/traceability reconciliation. It introduces
no new request, configuration, process, or persistence path. Claims and examples
must nevertheless satisfy the existing layers below; a documentation correction
must not imply bypasses or introduce an unvalidated example.

| Layer | Canonical incumbent and required treatment |
| --- | --- |
| SDL parsing, shape, and phase admission | `raes.parser`, closed `SDLModel`, `LegacyClassificationGuard`, `SemanticValidator`, `instantiate_scenario()` and `admit_instantiated_scenario()`. Keep source profiles, concrete symbol keys, collision-preserving references and post-substitution validation. Current examples must reject removed fields and unresolved/ambiguous refs. |
| External classification admission | Closed `external-concept-bindings-v1`, its canonical conformance registry entry, `external_concept_subjects()` and `admit_external_concept_bindings()`. Supply explicit exact local subjects and pinned snapshots. Unavailable assertions remain inactive; stale, duplicate, ambiguous, superseded and unknown coordinates do not become current by fallback. Locators are inert, credential-free identifiers; parsing/admission performs no network, env lookup, filesystem discovery or subprocess execution. |
| Control-context assets and selections | `specs/sdl/participant-control-context.md`, `raes.participant_control_context`, published ACT-620 contracts and `raes_contracts.participant_control_context`. Reuse the declaration index and exact asset id/version/digest; competing direct/reusable/experiment selections have no precedence. The trusted validation context owns lifecycle, roles, authority, audience and cut. Private bytes stay with explicit bounded readers through the existing associated-artifact validator; selection proves no disclosure, delivery, compliance or executable policy. JSON ingress reuses `parse_bounded_json_object`; no locator acquisition or new asset store. |
| Contract, vocabulary, and profile validation | `raes_contracts.contracts.ContractModel`, `schema_bundle()`, `contracts/schemas/`, `contracts/concept-authority/`, governed vocabulary/profile helpers, schema-publication manifest and per-schema records, `contracts/fixtures/`, and `raes_conformance.conformance.validators`. Schema acceptance is structural evidence only where contextual semantic validation is required; preserve `x-raes-invariants` and explicit missing-context diagnostics. No new DTO, schema registry, enum list or validator stack. |
| Runtime admission and configuration shapes | `RuntimeControlPlane`, `ControlPlaneConfiguration`, typed participant/mixed-control bindings, trusted policy/context resolvers, existing episode/history/crossing/result validators, and injected backend protocols. Exact participant/episode/cut/profile joins and installed support remain mandatory. Configuration explicitly refuses unsupported combinations; passing a model or receiving provider `None` supplies no missing authority or inapplicability evidence. |
| Authentication and authorization | `ControlPlaneSecurityConfig.strict_defaults()`, `ControlPlaneRouteAuthority`, sealed route composition, target-bound identities and separate participant/controller/audience bindings. P2 is administrative; a read role can read broader operational state. A participant-shaped view or binding is not a participant-only transport permission. Reuse request-size guards, role checks, idempotency fingerprints, revision checks and audit. No new endpoint is needed. |
| Secrets, env/config shapes, and host exposure | `raes.runtime_environment.RuntimeEnvironmentVariable`, `GeneratedArtifactValueSource`, `raes.runtime_values.enforce_observed_value_redaction`, and existing implementation configuration/provenance contracts. Preserve literal/`value_from` exclusivity and explicit `redacted`/`operator_secret` omission rules; generated in-band values cannot claim `operator_secret`. Scenario fixture values and operator credentials have different meanings. No real credentials, bearer tokens, private prompts or hidden evaluator data in examples, argv, diagnostics, logs or captures; no new env binding or secret loader. ADR-115 keeps native credential handling with backend owners. |
| Errors and observability | `SDLParseError`, collected `SDLValidationError`, `SDLInstantiationError`, `Diagnostic`/`Severity`, bounded external-binding diagnostics, existing API conflict mappings, and redacted 422/500 handlers in `control_plane_api._operation_routes`. Reuse no-store response middleware and value-free audit-failure logging. Do not echo raw rejected payloads, concept identifiers, validation inputs, backend exceptions or tracebacks. ADR-066 separates telemetry, audit, evidence, analysis and participant observation. |
| Persistence and effects | `RuntimeSnapshot`, `ControlPlaneStore`/`AtomicControlPlaneStore`, operation/participant histories, `raes_contracts.satisfiability.canonical_contract_digest()` and existing revision/idempotency/commit paths. Retain phase-specific SDL subject digests for external bindings. No participant-semantic database or alternate workflow engine. Commit failure dispatches nothing; a local commit or accepted receipt proves neither external success nor cessation. |

These are obligations on claims and any examples used in the reconciliation,
not new runtime work for #219. Reuse the public entry points and their negative
tests rather than constructing evidence below the owning security gates.

Preserve package ownership under ADR-036: SDL semantics in `raes`, portable
data in `raes_contracts`, compiled resources in `raes_processor`, provider
protocols in `raes_backend_protocols`, mediation in `raes_runtime`, and bounded
conformance in `raes_conformance`. Avoid copying semantic rules between them.

## Evidence, extension, and workflow boundaries

The eventual coverage records need stable clause identifiers, authority/status,
lifecycle and contract/version, implementation seam, exact executable test or
retained evidence, assurance kind and bounds, and any uncovered obligation's
concrete owning issue/requirement plus acceptance test. A module path or vague
"future work" is insufficient. A missing runtime guarantee does not imply its
normative artifact is missing; an existing artifact does not fulfill that
guarantee. ASR-506 completeness and each consumer's completion remain separate.

Keep the existing evidence distinctions:

- `test_participant_semantics_invariant_oracle.py` checks the test-local
  `ParticipantProgression` model, I1–I18 heading/catalog parity, a canonical
  positive control and targeted counterexamples. Its catalog is not a runtime
  validator.
  Preserve the stable headings; new clause families do not silently become I19.
- Finite abstract witnesses, bounded model checks, runtime tests, backend
  declarations, independently observed realization and mathematical proof are
  different evidence. Record tool/model revision, bounds, assumptions,
  projection and result for a model-check claim; a test named "model" is not
  enough. Deliberately unproved and missing evidence remain visible.
- Reuse the versioned behavioral-relation catalog and `BehavioralClaimBindingModel`
  for stronger claims, including evidence/quantifier scope and limitations.
  Existing classification migration/external-binding, SEM-213/215, v1/v2
  decision-surface, reusable-control and applicability tests are evidence
  candidates, not blanket proof of every clause or backend combination.

The extension seam is the existing clause/evidence record, parameterized by
contract lineage, semantic/profile revision, lifecycle, projection and evidence
scope. Keep the existing part discovery and source-derived parity checks;
future clauses add records referencing their owning authority, rather than
changing the original invariant oracle or inventing an ASR-506 model. Existing
bullet-order clause IDs must not silently acquire different meaning when
normative bullets move; reconcile the affected references and excerpts together.
New external schemes enter through explicit pinned snapshots/adapters to the
same neutral contract. New IFC distinctions require governed finite publication
and coherent reader support; ADR-114 does not authorize an owner-parameter
language, arbitrary labels, callbacks or runtime plugin discovery.

Repository-wide consumers in scope include `.ground-control.yaml`,
`.gc/plan-rules.md`, `tools/policy/requirement_order.yaml`,
`specs/authority/authority-boundary.yaml`, `specs/formal/assurance-policy.yaml`,
the ADR pin manifest, schema publication records, owning requirement records,
the detailed matrix and shared coverage table, nox/pre-commit policy selection
and CI. File references and pins use existing contained-path/bounded readers
(`tools.policy.common.safe_repo_path()` and `load_bounded_json_object()`), never
an escaping path or a new recursive discovery script. Reuse
`check_repo_policy.py`, `check_requirement_governance.py`,
`check_adr_immutability.py`, `check_semantic_coverage.py`,
`check_behavioral_relation_claims.py`, `check_authority_boundary.py` and the
existing concept/schema/publication/fixture checks for the surfaces changed.
No policy bypass or new checker is justified merely to reconcile prose.

At this inspection cut, `tools/policy/requirement_order.yaml` selects repository
requirement authority. `docs/governance/requirement-scopes/219.json` exists, but
neither this preflight nor `issue-219-participant-semantic-consistency-design.md`
has an explicit binding in it. The targeted requirement-governance check reports
`requirement-scope-unassigned` for both guidance files; file-local repo policy
passes. Resolve assignments through that existing scope before publishing the
guidance. No scope, exception or requirement authority is changed by this
preflight. Do not suppress the check or substitute a remote authority.

Use the repository's frozen Python 3.14 tooling environment. The host `python3`
cannot parse the current governance tooling; a host-interpreter failure is not
a governance verdict. No dependency installation or new service is needed.

Set `RAES_REQUIREMENT_UID=ASR-506` on this branch. Use targeted local policy
checks and explicit relevant tests or `verify-fast-feedback`; full verification,
integration, fuzz and completion suites belong in CI. If a contract change is
actually necessary, it needs normative approval, publication `last_change`
summary/hash, generator parity and positive/negative fixtures together; draft
status is not permission for silent reinterpretation.

Reconcile DOCUMENTS, IMPLEMENTS and TESTS links according to actual ownership
and evidence, preserving the #487 oracle's narrow delivered scope. A
DOCUMENTS link does not transfer schema ownership; the published-contract gate
requires an exact `IMPLEMENTS → SPEC` schema link from its live owner. Keep
repository requirement records and Ground Control aligned through the existing
workflow. Do not activate ASR-506 or another DRAFT requirement from prose alone.
New source-bound research evidence uses immutable branch captures through
`tools.research_capture record`; do not relabel old captures as current or
allocate numbered research releases on a feature branch.

## Non-goals

This preflight changes no normative specification, accepted ADR, requirement
status, schema, implementation, test, runtime configuration or stored evidence.
The implementation boundary for #219 is consistency and coverage ownership;
it must not quietly deliver missing runtime behavior as a documentation fix.
No replacement participant model, classification taxonomy, clock, outcome
ontology, policy interpreter, exception hierarchy, persistence store, scheduler,
conformance runner, backend integration, new service or data transfer is needed.
The executable conformance corpus remains #220's deliverable; author-facing
identity/migration guidance remains #1342's. Record dependencies and bounded
gaps without taking over either deliverable or claiming their results.
