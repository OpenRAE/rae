# Issue #1008: evaluation-backed adversarial control claims preflight

Date: 2026-10-29. Inspection baseline: `dea4d1be`.

This note records architecture constraints for ASR-536 and issue #1008. It is
not an implementation plan, requirement amendment, evaluation result, or
completion record. The supplied maintainer scope correction governs this work:
RAE evaluates and publishes its own contract and runtime behavior through a
conformant RAE harness. A concrete backend is not a prerequisite.

## Decision and authority boundary

Reuse the [#1007 harness design](issue-1007-intentional-subversion-evaluation-design.md)
and installed modular-control runner. Extend their evidence collection where
needed; do not create another runner, policy engine, backend selector, store,
trajectory schema, or publication service. [ADR-115](adrs/adr-115-concrete-backends-owned-outside-raes.md)
keeps concrete realization, credentials, native lifecycle, and qualification
outside RAE. The runner's `BackendConformanceReport` type name does not make a
hermetic RAE test a backend realization claim.

Keep these evidence stages distinct: capability declaration, enforced runtime
behavior, experimental evaluation, concrete backend realization, and
mathematical assurance. API-424 control evaluations are individual runtime
decisions, not ASR-536 experimental results. API-409 occurrence v2, API-424
evaluation v2, SEM-233 revisions, mechanism profiles, and experimental protocol
revisions have independent identities.

Known adversarial input may be intentionally admitted and tracked. The selected
policy determines the expected disposition; successful influence is not by
itself a policy violation. Out-of-world provider, host, or backend interference
invalidates the affected evidence. It is not a participant attack or evidence
that a control resisted one. The host and installed harness remain trusted.

The current repository still contains conflicting dependency guidance:

- [ASR-536](../requirements/ASR-536/requirement.md) requires exact realized
  compositions and a real backend for realization-based results. RAE harness
  evaluation must bind its exact installed fixture composition instead, while
  retaining the separate evidence obligation for any concrete realization claim.
- [ADR-108](adrs/adr-108-modular-participant-control-and-governed-effects.md)
  section 7 and `docs/research/modular-participant-control/{requirements.md,
  delivery.md,delivery.json}` retain backend proof prerequisites. The graph's
  `check_design.py` explicitly indexes `#1007.requires_any[0]` and asserts the
  two backend alternatives. Updating prose alone leaves a contradictory gate.
- ADR-101 section 10 and the adversarial-control `implementation-program.json`
  completion gate still join publication to apparatus/backend realization.
  Their historical design cut is not the current evidence status.

The authorized implementation must reconcile these authorities without making
backend evidence optional for a backend claim. Preserve conditional backend
claim gates and historical observations. Accepted ADR changes follow
[ADR-059](adrs/adr-059-adr-amendment-policy-and-pin-gate.md): an amendment record
and matching `adr-index.yaml` pin/record belong in the same change. This note
does not silently override an accepted ADR or mark ASR-536 fulfilled.

## Canonical components and ownership

Paths below are repository-relative; package names refer to
`implementations/python/packages/`, and test files to
`implementations/python/tests/`.

| Concern | Incumbent and required reuse |
| --- | --- |
| Experimental coordinates and cases | `issue_1007_intentional_subversion_harness.py`: `PROTOCOL`, fresh `case_matrix()`, `evaluate_case()`, and its safe `published_payload()`. The dataclasses are test data, not portable DTOs or a new profile registry. |
| Runtime driver and observations | `raes_conformance.conformance.run_modular_control_conformance`, `ModularControlCase`, `ModularControlStep`, `ModularOwnerObservation`, and `modular_control_{execution,checks,replay,refusals}.py`. Keep independent call counts, committed readback, causal joins, exact replay, and cleanup checks. |
| Report honesty | `BackendConformanceReport`, `validate_backend_conformance_report()`, `validate_modular_report()`, and `backend_conformance_report_payload()`. Preserve selected-subset coverage, diagnostics, failed/unsupported rows, exclusions, and native-claim refusal. Do not reconstruct a friendlier success envelope. |
| Runtime enforcement | `RuntimeControlPlane`, injected `RuntimeTarget`, `ParticipantControlRuntimeBinding`, API-424 request/evaluation/context validators, API-409 occurrence/history validators, SEM-233 flow validation, crossing mediation, and final-sink enforcement. The publisher consumes these facts; it does not reimplement their reducers. |
| Experiment and claim carriers | Existing task/protocol/apparatus/run, `ExperimentEvidenceRecordModel`, `ExperimentDerivedMeasureModel`, `ExperimentInvalidationModel`, `BehavioralClaimBindingModel`, and governed relation assurance. Use contextual validators, including `validate_experiment_apparatus_context_against_manifests()` and content-backed `validate_experiment_run_against_task()`, when claiming those contracts. |
| Local collection precedent | `mixed_control_demonstration.py` already has `source_identity()`, fresh local collection, source-stability checks, exclusive output creation, verification, and fresh-run comparison. Reuse suitable collection logic; keep adversarial assertions in their owning harness. Do not run unrelated mixed-backend probes just to obtain publication metadata. |
| Digests and historical evidence | `raes_contracts.canonical.canonical_json_digest()` owns canonical encoding. `tools.research_capture` and `docs/develop/research-captures.md` own immutable source-bound formal/specification captures, retention, and integration publication. A new test result does not upgrade an old formal witness. |

`ExperimentApparatusContextModel` requires `processor` and `backend` components,
selected manifests, compatibility, and observed setup evidence. A named RAE
stub can fill its actual declared test role where those bindings are valid;
that is not a native realization. Do not invent component evidence, omit
required fields, use unchecked construction, or weaken this cross-cutting
validator to serialize a publication. A bounded harness projection can remain
test evidence without pretending to be a complete portable experiment record.
Schema gaps require their own explicit authority decision, not a parallel DTO.

## Evidence sufficiency and current harness limits

The current harness has seven finite cases: honest baseline, permitted
injection, an unrelated-admission negative control, exfiltration denial,
adaptive evasion denial with reopen/replay, handoff denial, and apparatus
invalidation. `passed` means the expected case behavior occurred. The permitted
injection can report both a pass and attack success. Invalidated cases cannot
contribute a successful safety observation or a robustness denominator.

A targeted preflight run of `test_issue_1007_intentional_subversion_evaluation.py`
passed its first two protocol/case-shape tests, then timed out in the runtime
execution test under the configured 120-second test limit. The remaining run
was interrupted; the cause is not established. This inspection therefore does
not verify the runtime prerequisite. Publication still requires a completed,
validated run, not the presence of the harness or its design record.

The current projection contains digests, not the retained conformance report
or an explicit source revision. The runner removes its temporary ledger after
each case. A digest without resolvable content and a reproduction entry point
does not make publication replayable. Retain the safe validated report and
required reference content before disposal; disclose any unavailable replay
material. Do not retain private payloads merely to claim fuller replay.

Every claim must bind the same contract IDs and schema hashes, protocol/profile
revisions, mechanism/provider fixture and implementation identity, policy,
configuration, applicability, trigger/effect rules, attacker/monitor assignment,
memory scope, selected cases, source content/revision, harness configuration,
and execution basis. Names of Python classes or callables alone do not pin
their implementation. Record dirty source content honestly; a HEAD revision
alone does not identify uncommitted code. Collection must detect source drift.
An allowlist of nonsecret runtime/tool versions supplies environment identity;
never serialize or hash the process environment.

Keep authored coordinates, expected assertions, observed outcomes, and derived
measures separate. Fixed independent expectations remain test oracles; neither
runtime reducers nor case-supplied success/invalidation flags may manufacture
observations. A retained report must join the marked evaluation, originating
operation, and exact admitted action. An unrelated admission or refusal proves
nothing about that attack. A malformed provider must have observed integrity
failure evidence, not just an authored invalidation label.

Profile field presence does not establish exercised coverage. The current
fixtures declare correlation, collusion, memory, and intervention coordinates;
they do not demonstrate every coalition, correlated failure, cross-participant
or cross-episode retention policy, editing, deferral, interruption, or shutdown.
Current audit cost counts selected cases, intervention cost counts committed
denials/final-sink denials, usefulness records whether an admission occurred,
and uncertainty is `deterministic-fixture-only`. These are bounded proxies,
not labor cost, task-quality measurement, statistical confidence, or evidence
of runtime audit-budget enforcement. False-positive rates require an explicit
honest population and denominator. Mark unexercised coordinates and missing
measures unsupported or limited; do not substitute zero or infer coverage.

Report safety, usefulness, attack success, intervention cost, audit cost,
uncertainty, limitations, invalidation, and nonclaims separately. Exact retries
do not consume another intervention. A fresh run has new operation identities
and may have different runtime/trajectory digests; compare stable coordinates
and observed facts. Exact ledger replay and fresh-process reproduction are
different evidence. Neither proves independent replication or a universal claim.

## Cross-cutting security and runtime gates

| Layer touched by collection/publication | Required boundary and how the design satisfies it |
| --- | --- |
| Parsing and shape | Use closed `ContractModel` DTOs and existing model/context validators; schema acceptance alone does not enforce `x-raes-invariants` or external joins. Any SDL example uses bounded `load_sdl_yaml`, `parse_sdl`/`parse_sdl_file`, `SemanticValidator`, and the existing compiler. No permissive loader or duplicate validation language. |
| Harness/config admission | The runner validates bounded unique typed cases and selected obligation/effect subsets. `ControlPlaneConfiguration` validates typed installed owners and compiled context; `ParticipantControlRuntimeBinding` checks exact providers/protocols and fences trusted context. Keep final-sink enforcement enabled and the runner-owned isolated store. No scenario-selected imports, executable paths, arbitrary option bags, or claimed capability from method presence. |
| Authority and information flow | Supply `ControlPlaneIdentity` and retain role, target, participant/controller/audience and operation scope checks, trusted exact-cut resolution, API-407 effective support, crossing mediation, and the final sink. Administrative access is not participant visibility. Monitor scores and trusted-role labels confer no authority. Recheck access on readback/retry; the drain caller cannot lend authority to an effect. |
| Optional HTTP transport | Collection stays in-process. If guidance shows HTTP, reuse `control_plane_api`, `ControlPlaneSecurityConfig.strict_defaults()`, sealed route authority, bounded strict JSON ingress, `control_plane_api_guards`, and no-store responses. Keep duplicate-key, depth, number/body bounds and fixed auth/error responses. No new endpoint or development-auth bypass is needed. |
| Secrets and environment shapes | Use credential-free synthetic fixtures. Any SDL environment example must satisfy `RuntimeEnvironmentVariable` redaction and literal/`GeneratedArtifactValueSource` exclusivity; a generated value cannot be `operator_secret`. Logical operator references use `raes_contracts.secret_references.SecretReferenceId`. Never read secret files, resolve backend credentials, or hash real secrets as evidence. |
| Host/process/filesystem | Use the repository's frozen Python 3.14 environment and local collector precedent. Use a fresh caller-selected local output root outside hashed source roots, owner-restricted output, exclusive creation, bounded file reads and repo-contained references. Reject traversal/symlink escapes when resolving evidence. No tokens in argv, filenames, shell history, diagnostics, or examples; no daemon discovery, native host commands, external processing, or upload. |
| Exceptions and logs | Follow ADR-116 and `docs/develop/exceptions-and-logging.md`: reuse `RaesError` categories, `Diagnostic`/`Severity`, stable codes, `sanitized_failure_message()`, `get_logger()`, `foreign_failure_record()`, and `run_application()` where applicable. Log unexpected failures once at the owning boundary, preserve cancellation, and keep protocol output separate. Never echo rejected values or raw provider exceptions; HTTP retains its fixed redacted 500 envelope. No second exception hierarchy or logger pipeline. |
| Audit and evidence disclosure | `require_audit_event_fields()` permits only bounded, action-owned detail keys; an experimental coordinate is not a new audit field. Logs are not evidence, audit, or participant observations (ADR-066). Publish allowlisted synthetic identifiers, counts, digests and limits, excluding hidden objectives, prompts, private reasoning, raw payloads, credentials and private state. Evidence records preserve sensitivity, redaction policy, and loss disclosure. A hash authenticates neither origin nor authority. |
| Persistence/concurrency | Reuse `RuntimeSnapshot`, `ControlPlaneStore`/`LocalControlPlaneStore`, atomic `commit_participant_transition`, immutable history validation, expected revisions/heads, leases, idempotency and dispatch claims. Read committed owner outcomes; an accepted receipt is not effect completion or observation. Reopen before exact replay. No history mutation, budget reset through fresh IDs, resending consumed claims, or exactly-once external-effect claim. |

## Whole-repository reconciliation and extension seam

The in-scope authority surfaces are the ASR-536 repository record, affected
ADR-101/108 interpretation, both research programs and their dependency
checkers, formal participant semantics, `specs/formal/assurance-{policy,
fulfillment}.yaml`, scientific-completeness records, and
`docs/explain/sdl/lineage.md`. Add only actual artifact/evidence links; requirement
status, assurance level and scientific completeness are not interchangeable.
Historical DRAFT statements and captures keep their dates and evidence scope.

`docs/public/participant-control.md` still describes attack evaluation as
unclaimed. Current public guidance must distinguish the new bounded RAE result
from unsupported dimensions and downstream backend claims. The public build is
owned by `docs/public/conf.py`, `tools/check_public_docs.py`,
`tools/public_docs_guard.py`, `.vale.ini`, and the existing `docs-local` lane.
Link to repository authorities; do not include internal source trees into the
curated public build. Hub #36/#37 consume the same exact result pointers and
limits; coordination is not another semantic authority or an excuse to inspect
other checkouts. This preflight changes no external issue or hosted content.

The extension seam is the existing injected target, typed case factory,
explicit protocol revision, selected obligation/effect subset, and safe local
collector output. New attack/monitor/memory arrangements supply fresh typed
cases and coordinates through that seam, not backend-name branches. Changed
meaning requires an explicit protocol revision; never reinterpret rev1 bytes.
Any protocol/case-selection parameter belongs at the harness/collector boundary
and must be included in its evidence identity, not added to a portable schema.
Keep verifier expectations fixed independently of configurable attack inputs.
A future concrete backend supplies its own admitted adapter and exact evidence
outside this RAE result. No mechanism parity or equivalence is presumed.

Use `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/check_repo_policy.py`
with file-local scope, requirement traceability, and relevant targeted harness
and dependency-checker tests. Source changes affecting formal evidence use
immutable captures, not rewritten numbered releases. Any separately justified
published schema change still follows ADR-009/061: publication ledger/hash,
fixtures, exports, packaged corpus, and `schema_bundle()` parity. Versions and
changelogs remain release-tool owned; full verification remains CI/CD work.

## Non-goals and implementation boundaries

No production runtime API, backend implementation/selection, credential
transport, native execution, new store/scheduler, provider discovery, general
policy interpreter, generic publication platform, or automatic migration is
needed. Reuse or extend the RAE harness only where publication requires missing
observations or retained evidence; do not import repository tests into installed
packages. #1019 owns broader control reference/migration documentation; #976
owns the separate finite-bisimulation publication. This work establishes no
universal robustness, monitor honesty, opacity, bisimulation, backend
equivalence, undeclared-channel control, or host containment. Guidance cannot
turn a known gap into a completed claim.
