# Issue 976: reproduced participant-crossing publication preflight

Date: 2026-10-31.

Requirements: SEM-232 and ASR-535.

This note fixes the architecture boundaries for publishing the already retained
participant-crossing result. It does not produce or rerun a model check, accept
a reproduction, change a requirement status, or implement a runtime or backend
feature. No new ADR is needed. ADR-100 already owns the theorem, profile,
relation, evidence, and nonclaim boundaries.

## Decisive current-state finding

Historical acceptance is retained, but current-checkout reproduction admission
fails. The completion gate must not yet be reported as verified. The selected
machine-check pin is
`sha256:76422aebb1413e345677eeaa4bea67005e74aa3d9289d185f63f4c69dc838339`.
The selected reproduction pin is
`sha256:3d989819b2b45ea717d1c24e337f53f7bcf7c22c24c030a985e300909b509e46`.
The retained review decision is `accepted-bounded-reproduction` and binds the
second capture to the first. It records a separate implementation-agent review,
not a human review or a cryptographic authenticity guarantee.

Preflight verification on 2026-10-31 found all 446 machine-check source digests
unchanged, but 20 of the 1,269 retained reproducer source digests differ from
this checkout. The existing
`test_issue_975_reproduction_record.py::test_retained_qualified_reproduction_has_exact_artifacts_and_agent_acceptance`
fails at `reproduction.admit_measurement` with `EvidenceIntegrityError`:
`invalid reproduction measurement`. This failure predates this note's changes.
Presence of the review JSON therefore does not establish a passing publication
gate under the current admission path.

The historical statement, subject to a passing retained-record admission gate,
is narrow:

> The declared initial states of
> `sem-230-participant-crossing-abstract@rev2` and
> `api-423-run-319-crossing-kernel@rev2` received a positive finite
> `divergence-preserving-branching-bisimulation` model-check decision over the
> complete reachable carrier of
> `participant-crossing-dpbb-finite-v1@rev2`, under
> `participant-crossing-projection@rev1`; the selected result was independently
> reproduced and separately accepted by the retained issue #975 record.

This statement's evidence boundary is only that named complete finite carrier.
The abstract model has 88 states and 107 semantic/AUT edges. The concrete model
has 178 states and 197 semantic/AUT edges. Both declared initial ordinals are
zero. The equality of semantic and AUT edge counts in these artifacts does not
merge those two count meanings.

Preservation wording comes from the existing formal authority's "Preserved
Properties And Nonclaims" section: visible branching and choices, finite
internal stuttering, the declared crossing order, success/refusal termination,
structural deadlock, and explicit internal divergence, all within this profile.
Do not infer preservation of secret predicates or low-equivalence from it.

The model-check result remains a `model-check` axis claim with `model-checked`
status. It is not a proof or proof certificate. Its original claim correctly
retains `independent-reproduction` as a nonclaim because that claim record was
produced before review acceptance. The separate reproduction capture supplies
the recorded acceptance; publication must validate and compose the two
immutable records, not rewrite the original claim or suppress the current
admission failure.

## Architecture decisions and guardrails

### Publish a view of immutable evidence

The machine-check and reproduction captures are the authorities for result
facts. Reader documentation is a checked projection of them. Do not copy the
evidence into a new result DTO, schema, manifest, evidence bundle, database, or
service. Do not edit either capture, either pin, the original claim, the
mutation corpus, or the historical runtime-mapping record.

Use `machine_check.load_retained` and `machine_check.admit_bundle` for the
selected model-check subject. Reuse `reproduction.admit_measurement`, the
bounded ingress functions, and the exact retained-record joins already asserted
by `test_issue_975_reproduction_record.py` for the reproduction. That test is
the incumbent acceptance contract, but its call to `admit_measurement` also
requires current sources to match the historical measurement. Historical
record admission and current-source replay compatibility need distinct entry
points. Any shared retained-record admission belongs in the formal package,
outside the source files pinned by the existing captures. Reuse the existing
bounded readers, canonical digests, claim validation, and exact artifact joins;
do not copy a second measurement generator or weaken `admit_measurement`.

Historical admission must bind the reviewed capture to its recorded source
revision and complete source inventory, and validate measurement, execution,
claim, mutation subject, review scope/nonclaims, reviewer separation, and
qualified-run joins. A digest and an `accepted` string alone are insufficient.
It must report current-source incompatibility separately and must not claim a
fresh replay. Missing source provenance or acceptance remains a publication
blocker. This preflight does not implement that admission boundary or authorize
replacement evidence.
Historical source lookup is bounded local data inspection; it must not execute
candidate source or fetch missing history automatically. Missing history must
produce a clear refusal, not a weaker digest-only acceptance.

The source boundary extends beyond the formal package:
`machine_check_evidence.SOURCE_PATHS` includes every `raes_contracts/*.py`,
`noxfile.py`, and `participant-crossing-machine-check.md`.
`reproduction.source_pins` additionally binds every committed Python package
source, `.ground-control.yaml`, and the reproducer itself. Even a harmless
loader edit or module addition can change the admitted identity. Check these
inventories before choosing a delivery file. Do not refresh pins, remove source
entries, introduce drift exceptions, or regenerate evidence to make a
documentation change pass. Keep new publication-only consumers outside those
inventories; a necessary change to a pinned source reopens its evidence and
independent-acceptance obligations.

A documentation drift check must compare structured facts with the admitted
records. It must not compare prose fragments with other prose fragments. At
minimum it binds:

- the two pin digests and the reproduction target-manifest join;
- taxonomy `rev8`, the exact relation, profile `rev2`, projection `rev1`, both
  model ids/revisions, and both initial states;
- complete-carrier Boolean, domain counts, state counts, semantic edge counts,
  AUT edge counts, input and sidecar digests, and the positive decision;
- mCRL2 `202607.0`, `dpbranching-bisim`, `--tau=internal`, ordered inputs, tool
  archive/executable/tree identities, and the fixed mutation subject;
- result, claim, manifest, measurement, execution, review, and qualified-run
  artifact digests; and
- every limitation, authenticity statement, and nonclaim.

The public page may show a smaller digest table, but the checker must bind its
displayed values to the complete admitted record. A digest proves identity
against the selected pin. It does not establish semantic correctness,
authenticity, or review by itself. Both captures are explicitly unsigned.

### Reuse the existing claim model

The structured reader-facing claim is the exact existing
`BehavioralClaimBindingModel` from `result.json`. Validate it with
`validate_behavioral_claim_binding` against the exact catalog and profile. Do
not add a documentation-only claim class or weaken its revision, carrier,
projection, quantifier, evidence-scope, limitation, or nonclaim fields.

The public guide already uses marked JSON and
`test_public_docs_policy.py` to validate a claim against the catalog. A second
marked block for the participant-crossing result should follow that pattern and
must equal the admitted machine-check claim. Separate prose and checked fields
state the independent reproduction decision. Do not alter the original claim
to pretend reproduction existed when it was produced.

`tools/check_behavioral_relation_claims.py` remains the repository-wide guard
against unbound positive prose. Every positive equivalence sentence must keep
the exact relation id and finite evidence boundary nearby. A page that says only
"proved equivalent", "bisimilar", or "formally verified" is invalid.

### Keep the publication surfaces distinct

Use the owners already present in the repository:

| Surface | Existing owner and publication boundary |
| --- | --- |
| Semantic decision | ADR-100 and `participant-crossing-bisimulation.md`. Preserve the historical rev1 sketch while adding a clear pointer to the current rev2 result. Do not rewrite accepted ADR bytes. |
| Exact check and reproduction | `participant-crossing-machine-check.md`, `participant-crossing-reproduction.md`, and their selected captures. These remain the detailed technical records; the machine-check spec itself is source-pinned and must remain unchanged. |
| Research landing and program status | `docs/research/participant-bisimulation/`. Change design-era "no result" wording to the exact reproduced outcome while retaining the historical assessment and worked sketches as historical. |
| Hosted reader guidance | `docs/public/participant-control.md` is the existing participant relation guide. Add the bounded result there, and use `docs/public/research.md` only as navigation if needed. Do not create a second public relation taxonomy. |
| Scientific completeness | The existing REV1 taxonomy, `ScientificCompletenessAssessmentModel`, and `check_scientific_scenario_completeness.py`. Add exact evidence without changing concern meanings. |
| Formal assurance | The existing FM3 `participant-semantics` entry in `assurance-fulfillment.yaml` and `check_assurance_policy.py`. Use existing artifact kinds. |
| Semantic coverage | The `SEM-232.F` row and `check_semantic_coverage.py`. Replace the design-era owner/test placeholder with the actual formal implementation, model-check, counterexample, reproduction, and publication evidence. |
| Lineage | `docs/explain/sdl/lineage.md` and `check_sdl_lineage.py`. Update delivery wording; the external source mapping and governed relation meaning do not change. |
| Requirement traceability | The generated requirement records and Ground Control links for SEM-232 and ASR-535. Link issue #976 documentation and policy evidence without relabelling formal code as runtime implementation. |

The formal result does not resolve the broader
`participant-action-observation` scientific-completeness concern. That concern
still includes live runtime, portable observation, backend, and universal
information-flow gaps. The result belongs as additional exact evidence for the
implemented `behavioral-relation-taxonomy` concern, while the former concern
stays `partial`. No scientific-completeness profile becomes complete from this
result.

The scientific-completeness taxonomy and delivery assessment are different
revision axes. Issue #727 states that a delivery change publishes a new
assessment rather than silently changing the meaning or history of REV1. Do not
edit `delivery-assessment-2026-07-12.json` in place again. Publish a new
assessment revision using the existing schema/model, retain the old assessment,
and select it explicitly at the repository publication/checker boundary.
Reuse `ScientificCompletenessAssessmentModel`, `scientific_completeness_root`,
and `evaluate_profile_completeness`; do not change the source-pinned package
loader merely to change its default filename. The existing default continues
to identify its historical assessment. The checker, publication tests, and
reader-facing current-assessment link share one reviewed selection, while
historical consumers keep their explicit revision. Include the existing
`specs/agent-guidance/agent-guidance.yaml` assessment reference in that review.
Changing the packaged default is a separate source/evidence migration. Do not
scan for "latest" or select an assessment from an environment variable.

The FM3 assurance map records required artifact kinds, not a theorem status.
Add the participant-crossing invariant/model, closed profile, counterexample
and reproduction tests under the existing kinds. Do not invent a `proof`,
`model_check`, or `reproduced` artifact kind in that map. Preserve the unrelated
observation-capture-apparatus waiver for #1595. Replace the stale comment that
ASR-535 makes no model-check claim with wording limited to this exact model
check; ASR-535 still has no general participant-flow proof claim.

## Canonical incumbents to reuse

| Concern | Canonical incumbent and required use |
| --- | --- |
| Relation and profile authority | ADR-081, ADR-100, the exact `raes-behavioral-relations@rev8` catalog, `participant-crossing-dpbb-finite-v1@rev2`, `BehavioralRelationProfileModel`, and exact-revision loaders. Do not resolve "current" at runtime. |
| Models and projection | `export.build_bundle`, independent `abstract` and `concrete` modules, the profile contract, and the AUT codec. Documentation never reconstructs or simplifies either LTS. |
| Positive and negative evidence | `machine_check`, `machine_check_evidence`, `counterexample_corpus`, `counterexample_witnesses`, and `machine_check_publication`. Preserve the complete mandatory mutation/calibration inventory. |
| Reproduction | `reproduction`, `reproduction_checks`, `reproduction_sandbox`, the selected reproduction pin, and the separately accepted review record. A fresh measurement without accepted review is not enough. |
| Safe input | `participant_crossing.ingress.safe_path`/`read_bytes`, `json_ingress.parse_bounded_json_object`, `tools.policy.common.safe_repo_path`, and closed inventories. Use the existing canonical JSON helpers for structured digests and `export.digest` for exact artifact bytes; these digest meanings are not interchangeable. No generic `Path.read_text()` over a caller-selected evidence path. |
| Claims | `BehavioralClaimBindingModel`, `validate_behavioral_claim_binding`, and `check_behavioral_relation_claims.py`. Preserve nested scanning and exact catalog/profile joins. |
| Scientific completeness | Existing taxonomy/assessment Pydantic models, schemas, corpus routing, `evaluate_profile_completeness`, and `check_scientific_scenario_completeness.py`. No new profile family or status vocabulary. |
| Assurance and coverage | ADR-007/018, `assurance-policy.yaml`, `assurance-fulfillment.yaml`, `check_assurance_policy.py`, the semantic-coverage matrix, and `check_semantic_coverage.py`. |
| Public docs | `docs/public/`, its toctree, `tools/check_public_docs.py`, `test_public_docs_policy.py`, and the bounded docs build. Public pages use contained assets or ordinary HTTPS links; they do not include files from internal directories. |
| Errors and logs | ADR-116, `RaesError` categories, `PolicyFailure`, `operational_logging.run_application`, and `SessionReporter`. Evidence drift is `EvidenceIntegrityError`; repository publication drift is a bounded `PolicyFailure`. No new exception hierarchy or logger. |
| Workflow | `.ground-control.yaml`, `.gc/plan-rules.md`, the exact-file assignments in `requirement-scopes/976.json`, the canonical nox policy/contracts/docs lanes, requirement governance, and change-selected tests. Extend the scope manifest for every delivery file. Set `RAES_REQUIREMENT_UID=SEM-232`; full, integration, fuzz, and completion suites remain CI-only. |

## Cross-cutting layers and security posture

1. **Evidence ingress and shape.** Read only the fixed repository-relative pin
   and capture inventories through the formal package's bounded, no-follow
   ingress. Admit the machine-check bundle and the full reproduction joins
   before exposing a positive publication fact. Reject missing, extra,
   malformed, linked, oversized, drifted, or candidate-selected artifacts.
2. **Relation/profile validation.** Resolve the exact catalog and profile
   revisions and run `validate_behavioral_claim_binding`. Check the declared
   carriers, projection, initial states, complete domain, hidden-label
   partition, counts, result, and claim digest. Shape-valid JSON alone is not an
   accepted claim.
3. **Scientific-completeness config.** A new assessment passes the existing
   closed Pydantic model, published JSON Schema, corpus routing, exact taxonomy
   join, evidence-path containment, contract evidence checks, computed outcome
   summary, and nonclaim checks. It carries no command, URL fetch, hook, or
   open metadata.
4. **Assurance and semantic coverage.** The existing YAML safe loader,
   repo-relative path checks, FM3 artifact-kind rules, semantic-coverage row
   shape, owner rules, and evidence-path tests all remain in force. Publication
   cannot use a prose link to bypass these checks.
5. **Public documentation boundary.** `docs/public` remains the only hosted
   source root. It may not include, download, or read internal evidence during
   a Sphinx build. Use stable GitHub HTTPS links for reader navigation and use
   repository tests, outside the Sphinx process, to compare marked structured
   facts with admitted evidence. Do not copy raw captures into public assets.
6. **Authentication and authorization.** No route, control-plane operation,
   backend call, or authenticated runtime resource is in scope. Do not add an
   evidence endpoint or weaken `_ControlPlaneApiAuth`. Existing issue/review and
   Actions links are provenance references, not authorization or authenticity.
7. **Secrets and privacy.** Publish only the already allowlisted synthetic ids,
   counts, fixed labels, revisions, safe refs, and digests. Do not publish raw
   diagnostics, process output, environment maps, credentials, tokens, home or
   host paths, backend objects, participant payloads, policy bodies, or hidden
   observations. Hashing secret material does not make it safe to publish.
8. **Environment and OS exposure.** Documentation and drift checks need no
   native model-check execution, network, shell, daemon, socket, privilege,
   mutable cache, or environment-selected subject. Existing source admission
   does invoke local Git through `reproduction_sandbox.git_output` and
   `run_bounded`; preserve its fixed arguments, disabled hooks/redirection,
   bounded output, and timeout. Do not put evidence content or secrets in
   process argv or environment variables. `RAES_REQUIREMENT_UID` is workflow
   classification only and never selects evidence.
9. **Errors and observability.** Repository checks return stable
   `PolicyFailure` ids with safe repository locations. Formal admission retains
   `InvalidInputError` and `EvidenceIntegrityError`. Application boundaries use
   `run_application`; no raw exception text, rejected values, native stdout or
   stderr, or host paths enter public pages or logs. Operational logs remain
   separate from evidence and audit.
10. **Persistence and distribution.** Durable state is the immutable checked-in
    captures, pins, versioned assessment, assurance/coverage records, and docs.
    Add no runtime store, database, cache, audit stream, upload destination, or
    external hosting. Existing CI owns its approved artifact upload; #976 does
    not republish tool trees, caches, or the checkout.

## Whole-repository surfaces in scope

- **Authority:** ADR-081/100, the current/historical behavioral catalogs, the
  exact relation profile, SEM-230/API-423/RUN-319 boundaries, and SEM-232/ASR-535
  requirement records.
- **Evidence:** model, runtime-mapping, counterexample, machine-check, and
  reproduction specs; formal-package admission interfaces; selected pins and
  immutable captures; mCRL2/tooling provenance.
- **Governance:** scientific-completeness taxonomy and newly selected assessment,
  FM3 assurance fulfillment, semantic coverage, lineage prose/ledger checks,
  concept/claim policy, and requirement traceability.
- **Readers:** participant-semantics README, participant-bisimulation research
  index/status, participant-control public guide, research navigation, and
  current limitations/nonclaims.
- **Host/workflow:** public-doc containment, Sphinx/docs checks, canonical nox
  policy and contracts lanes, Ground Control classification, and CI-only full
  verification.

## Extensibility seam

The stable publication identity is:

```text
(catalog revision, relation id,
 profile id + revision + digest,
 left/right model ids + revisions + digests + initial states,
 projection id + revision, complete carrier + domains + counts,
 hidden-label set, tool identity + mode,
 result/claim/manifest pin,
 reproduction measurement + execution + review pin)
```

The publication checker should receive that selected identity, or its two
reviewed pin paths, as fixed parameters. It must not embed a special case that
assumes every future crossing result is the single-operation rev2 carrier. A
future result for the multi-operation profile, another tool, another qualified
host, or another projection gets its own admitted evidence and reproduction
record. It can reuse the projection/checking code and add another publication
entry without changing the meaning or bytes of this result.

Scientific-completeness assessment selection is the other required seam. The
repository checker/publication consumer accepts an explicit retained assessment
revision, validates it with the existing model, and shares the reviewed current
selection with reader links. This avoids editing the pinned package loader.
A new assessment changes the selection, not the historical assessment or the
taxonomy. Historical record admission likewise selects a reviewed source
revision; it must not silently reinterpret a historical record as current-code
compatibility.

## Gotchas and anti-patterns

Avoid:

- calling the finite result an unbounded mathematical proof, theorem prover
  certificate, checked abstraction map, or whole-runtime verification;
- editing `result.json` to remove its original independent-reproduction
  nonclaim instead of composing it with the later accepted review record;
- treating a successful process exit, state counts, matching digests, a
  candidate pin, or a fresh unreviewed measurement as the result;
- treating a retained accepted review as proof that current admission passes,
  or changing a source-pinned loader/spec/workflow file without reopening its
  evidence obligations;
- hiding denial, unsupported status, replay rejection, cut advance, delivery,
  observation, redaction occurrence, deadlock, or termination;
- collapsing the five semantic mediation classes into a claim that all
  runtime bookkeeping is unobservable;
- promoting the historical runtime mapping, which records 8 matches, 15
  incompatible cases, and 2 observation gaps, to live-runtime realization;
- giving the separate multi-operation profile this result;
- inferring backend conformance, policy noninterference, predicate opacity,
  authenticity, timing, probability, fairness, true concurrency, partial
  order, controller handoff, or wider policy-cut behavior;
- changing the `participant-action-observation` completeness status or profile
  outcomes because a formal crossing-kernel relation was reproduced;
- mutating the dated scientific-completeness assessment in place, inventing a
  `latest` scan, or selecting authority through environment configuration;
- inventing another claim model, evidence schema, relation catalog, profile
  loader, exception hierarchy, logger, store, CI workflow, or docs taxonomy;
- putting internal evidence files under `docs/public`, using Sphinx includes to
  escape that root, or copying raw native output into a public asset; and
- changing accepted ADR bytes, release-owned version/changelog files, or
  historical captures to make current documentation easier to state.

## Non-goals and implementation boundaries

- Do not rerun, regenerate, resign, or replace the model-check or reproduction
  evidence as part of documentation publication.
- Do not change model semantics, projection, relation, profile, tool selection,
  mutation corpus, runtime mapping, runtime code, backend code, HTTP behavior,
  or persistence. Extend existing publication/drift checks without weakening
  their admission or policy rules.
- Do not establish live-runtime realization, backend declaration/realization/
  conformance, SEM-230 noninterference, SEM-231 opacity, or an unbounded
  coinductive theorem.
- Do not claim another carrier, model revision, participant/audience/controller
  domain, operation count, request identity, history bound, policy order, time
  model, probability model, concurrency model, fairness assumption, or backend.
- Do not change SEM-232 from DRAFT or close/merge issue work without the
  separate requirement and workflow authority that owns those state changes.
- Do not add external hosting, uploads, services, telemetry, or data transfer.


## Decision after preflight

On 2026-10-31 the user selected a redesign instead of a publication without pinned-source edits.
Each retained record now binds subject sources and records apparatus identity as execution provenance.
The corpus and machine-check captures were recorded again under that design.
A new qualified reproduction and a separate reviewer acceptance replace the issue #975 record as the pinned subject.
The guidance above against new evidence applied to the earlier design only.
The `/implement` requirement transition is the workflow authority for the SEM-232 status change.
ADR-100 records that transition in an in-band amendment.
The [evidence identity design](issue-976-crossing-evidence-identity-design.md) describes the result.
