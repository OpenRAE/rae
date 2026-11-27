# Issue #1630 — Trial the record builder preflight

Date: 2026-10-28. The supplied issue is the delivery contract; no requirement UID
is attached. Native GitHub blocked-by relationships govern dependencies. This
inspection does not certify dependency closure or delivery of a release.
This note sets boundaries, not an implementation plan.

## Decision and existing owners

Produce the existing `experiment-run-v1` and `experiment-study-v1` artifacts from
the common runtime's stored work facts. The record builder must work
without replacement being enabled. Keep scientific checks separate from
durable storage: failed checks must not erase an work or its evidence.

[ADR-064](adrs/adr-064-experiment-evidence-and-measure-contract-boundary.md),
[ADR-065](adrs/adr-065-experiment-run-provenance-contract-boundary.md),
[ADR-068](adrs/adr-068-experiment-trials-replication-and-replay-claims.md),
[ADR-094](adrs/adr-094-authoritative-cross-plane-experiment-bindings.md) and the
[shared runtime design](issue-1629-shared-runtime-design.md) already establish
the relevant ownership. No new ADR or root schema is needed for these decisions.
The [runtime preflight](issue-1629-experiment-runtime-preflight.md) remains
applicable to work, supervision, recovery and authored retry policy.

Paths below start at `implementations/python/packages/` unless stated otherwise.

| Concern | Canonical incumbent and boundary |
| --- | --- |
| Live orchestration | `raes_runtime/control_plane.py`, `runtime_engine.py`, `runtime_run_context.py`, `runtime_experiment.py` and `runtime_trial_unit.py`. The shared controller owns effects, attempts, cancellation and cleanup. A producer consumes facts; it never dispatches work. |
| Admitted intent and realization | `raes_contracts/admitted_trial_plan_ingress.py`, `raes_processor/trial_realization.py`, `trial_scheduler.py` and `trial_compiler/replacement.py`. Keep allocated IDs, exact typed selections, original source pins, allocation order and processor-plan references. Do not recompile or redraw intent during export. |
| Portable records | `raes_contracts.contracts` exports `ExperimentRunModel`, `ExperimentStudyModel`, apparatus, evidence, traceability, binding and trial-provenance models. Published schemas under `contracts/schemas/experiment-core/` are authoritative. Private runtime decision carriers are not alternate portable records. |
| Observed facts | `runtime_trial_services.py` and `runtime_trial_decisions.py` keep settings, work, capture, retry and cleanup observed facts. Installed service verification and authorized evidence owners establish their content. Requested settings is not an observed fact. |
| Archive writes | `runtime_experiment_replacement.py::TrialArchiveOwner` already defines run build/write/exact-readback. General the record builder must share that owner with replacement. `raes_operations/run_artifacts.py::RunMaterializationArchive` supplies protected fixed materialization storage, not a general run/study repository. |

## Identity, provenance and facts

One started admitted entry yields one logical run with its allocated
`entry.run_id`. Authored work attempts remain distinct IDs under
`TrialRunProvenanceModel.execution_attempts`; they are not added replicates.
A replacement has a compiler-allocated child plan and run. Transport redelivery,
effect retry, authored attempt retry and replacement are different decisions.
Unstarted allocations remain unstarted, including after cancellation.

`scenario_snapshot_ref` identifies the exact instantiated SDL, using
`TrialRealization.snapshot_digest` and the canonical instantiated SDL contract.
It is not a digest of `RuntimeSnapshot` or a backend materialization. Keep the
actual instantiated artifact and all three `processor_plan_refs`, not only their
names. Keep the work snapshot captured before teardown; the final destroyed
snapshot cannot describe what ran. Use stored event times and clock provenance,
including realized time/stochastic records when present. Export time must not
replace work time or restart an admitted deadline.

Keep complete `ParticipantConfigurationResultModel` artifacts, including fixed
and default values, secret-reference IDs, control-context/prompt pins and
manifest commitments. Reuse `participant_configuration.py`, including
`validate_participant_configuration_selection()`. Selection provenance uses a
paired settings reference/digest. A digest without a retrievable fixed
settings is insufficient. Keep exact `realized_bindings` descriptors,
origins and typed `realized_selections`; never flatten structural treatments into
scalar parameters or reapply defaults during export.

Keep requested apparatus through admitted pins and authored intent. Construct
observed `ExperimentApparatusContextModel` facts from actual setup evidence and
selected manifests; call `validate_experiment_apparatus_context_against_manifests()`
with the concrete manifest payloads. A capability declaration or requested model
alias cannot supply observed apparatus or model ID. Participant implementation
ID also does not identify the underlying model used for an invocation.

Use `ExperimentRealizedFormDisclosureModel` and its existing
`TypedRealizationDescriptionModel` for supplied model/realization facts, explicit
knowledge states, source, scope and limitations. Prompt delivery evidence must
join the pinned content/settings to the actual participant, run, attempt and
delivery event. Keep requested and observed IDs separately, including
provider-reported ID and uncertainty when stronger ID is unavailable.
Descriptions and checksums do not establish delivery or work. Trusted
participant/backend owners must verify those observed facts; the generic evidence
check does not interpret model behavior. Do not create a model/prompt-specific
run DTO, put these facts in free-form metadata, or copy raw private prompts into
portable disclosures.

## Checks and failure representation

The producer needs all of the following separate gates:

- Closed model/schema checks and archival datetime checks, followed by
  `validate_admitted_trial_run()` for exact entry, snapshot, treatment,
  settings, stochastic and attempt/cleanup joins. This is not content proof.
- `validate_experiment_run_against_task()` with `ExperimentRunEvidenceInputs`:
  exact capture specs, evidence records, fixed byte readers and any scenarios
  required by evidence relations. This uses `evidence_satisfaction.py`,
  `_evidence_content_validation.py` and `evidence_output_validation.py` for actual
  bytes, size/checksum, registered output schema plus owning semantics, source,
  window, sensitivity, loss/redaction and requirement joins.
- `validate_admitted_trial_study()` or, for replacement histories,
  `validate_replacement_trial_study()` with `TrialReplacementStudyInputs`.
  These use `validate_experiment_study_against_tasks_and_runs()` and
  `experiment_conditions.py` for content-backed condition matching, eligibility,
  unique assignments, metric coverage and allocation targets. Separately use
  `reconcile_admitted_trial_plan()`/`reconcile_replacement_trials()` for stored
  attempt/history accounting; study checks alone does not prove completeness.

Do not substitute the `*_structure_*` checks, a settings digest, an
operation receipt or `capture.complete` for these gates. `ValidatedRunEvidence`
is minted only by content checks and bound to the exact task/run cut. It
cannot be deserialized, reused for a new run version or inferred from an archive
receipt. Reopen fixed readers for separate checks calls; consumed streams
are not fresh inputs. The content check admits 1,024 evidence items, 64 MiB
per artifact and 256 MiB aggregate; runtime observation tuples can admit 4,096
records. Keep the proof input within those limits.
Retain larger histories through exact versioned evidence references and protected source records.
Runtime shape acceptance is not scientific evidence acceptance.
Reject unsupported content formats and
integrity modes. A published schema alone does not register an evidence output
owner.

Evidence ID must distinguish attempts and sources without collisions.
The current content gate requires exactly one record per capture requirement
and unambiguous requirement IDs across supplied specs. Define the authoritative
observed fact cut explicitly while keeping prior attempts' evidence through
fixed lineage; do not combine duplicate captures into that proof input or
silently use last-write-wins dictionaries. The stored-history boundary and the
task's evidence claim set must remain distinguishable.

Emit explicit versions in capture and evidence traceability. The #1547 title
describes a defect, not a mandate to make `capture_spec_ref.ref_version` required.
The current published reference contract and
`tests/test_issue_1547_capture_reference_version.py` intentionally accept omitted
or null versions while rejecting mismatches and binding proof to the resolved
spec version. Keep that consumer compatibility; do not add a competing
version rule in the producer.

Work failure, scientific outcome, capture failure, checks failure,
invalidation and cleanup failure remain separate facts. Keep available raw
evidence and explicit missing/withheld metric statuses. A scientifically negative
result can be a valid evaluated run; infrastructure success is not scientific
success. An incomplete capture cannot satisfy a complete capture requirement.
Use existing deviations, validity notes, invalidation and, where a governed
profile applies, `ValidationBasisDisclosureModel` gate results/limitations. Do not
invent new strength labels for checks or claim a passed gate after refusal.

Material gaps in the inspected checkout must be resolved for delivery:

- `RuntimeExperiment.results()` lists terminal decisions only.
  `RuntimeTrialUnit.result()` requires work and cleanup observed facts, and
  destroy failure can prevent a cleanup result. Neither is a complete inventory
  of started work. Account from durable `TrialAttemptDecision` records and all
  run-local observed facts/operations, including settings failure, partial
  capture, cleanup failure and lost results. `reconcile_admitted_trial_plan()`
  defines attempted entries through cleanup receipts, so its result alone misses
  started attempts without receipts.
- Run provenance currently requires a terminal attempt and cleanup reference;
  the run requires end time, evidence artifacts, traceability, parameters and
  metric summaries. An interrupted live/unknown attempt cannot be made terminal
  by inventing those values. Keep its durable start and partial evidence until
  state checks establishes the facts. Known failed/partial cleanup can use the
  existing cleanup statuses; absence is not a successful receipt. If required
  failure cases cannot fit the existing contracts, evolve their owning contracts
  and checks explicitly rather than fabricate data or publish a second run
  schema. This is a delivery gap, not permission to omit started runs.
- Full evidence checks explicitly rejects missing required captures; study
  checks rejects allocation shortfalls and ineligible analysis members.
  Keep structurally valid failure records and an honest failed checks
  disposition, without labeling them content-validated. Keep invalidated and
  superseded history outside the eligible analysis subset. A failed evaluated
  run is not automatically excluded. Keep the original target counts and
  disclose shortfalls instead of shrinking the design to make checks pass.
- `ExperimentSpecModel` does not supply every required study field. Accept an
  explicitly authored study definition through the existing study model (or
  existing typed inputs where enough), including ID/version, owner,
  purpose and inclusion criteria. Claim-bearing studies also need research
  questions, behavioral claims, allocation and analysis policy. Do not synthesize
  claims/statistical methods, silently change `study_kind`, or copy fixture
  metadata. Pin this definition for resume. A reference to a study is not its
  content, and authoring input is not an archival study.

## Durability and extensibility

Archive every started run separately of `ExperimentReplacementBinding`.
Currently `archive_and_replace()` returns without a binding, and the normal
finish path refuses non-reusable cleanup before archival. Reuse the existing
archive boundary while removing that coupling; the record builder must not
release resources or authorize replacement. The fixture archive in
`tests/issue_1629_archive_fixture.py` copies a reference record and supplies no
production evidence proof. It is not a producer implementation to promote.

Use `ControlPlaneStore`, `runtime_decision_store.py`, the closed
`RuntimeDecision` union, existing codecs, owner leases, revisions and uncertainty
readback. Keep actor, target/run, plan/entry, attempt and archive-version
bindings. New private decisions must pass that union and all supported store
round trips. Check parity between durable starts and archival coverage before
claiming completion. Memory-only state cannot promise process-loss recovery.

An archive write and a runtime decision are separate commits. Freeze the exact
candidate ID/version/content before archive write, using existing decision
machinery. Resume must read and compare uncertain writes and finish the same
archive write; rebuilding with a new timestamp/version can create conflicting
bytes. Identical retries are safe; conflicting ID reuse must fail.
Study archive write must reference durable exact run versions. Keep originals
and use `build_superseded_trial_run()` and compiler-owned replacement history
for successors; never overwrite a failure or choose a second analysis leaf.
Do not transplant checks disclosures to a new artifact version.

The extension seam is the installed archive owner plus authorized, typed
observed fact/evidence inputs and a pinned study definition. Extend that existing
boundary only where missing; keep pure assembly/checks separate from storage
I/O. Parameterize destination, readers and existing participant settings
targets through trusted composition. Another model, capture channel or archive
provider must not require name-specific branches or a new record schema. Reuse
the canonical output registry if another content format needs proof. Local and
Temporal work consume the same stored facts; Temporal history must carry
references, not record payloads, secrets or a second archive write workflow.

## Cross-cutting layers the design must pass

| Layer and canonical owner | Required behavior |
| --- | --- |
| Ingress and bounded shapes: `admitted_trial_plan_ingress.py`, `json_ingress.py`, `ContractModel`, `runtime_decisions.py` | Reconstruct stored/untrusted nested models; bound counts, depth and aggregate bytes before copying/hashing/persisting. Reject duplicate JSON members and non-finite values. Keep contract-specific reference restrictions: some refs forbid even explicit null digest/path fields. Do not serialize every reference with the same generic dictionary helper. |
| Authentication/authorization: `control_plane_admission.py`, `control_plane_plan_authorization.py`, `control_plane_operation_context.py` | Keep admitted actor and run scope; authorize evidence reads, writes and retrieval separately from work. P0 trusts its embedder. IDs, digests and archive receipts are not credentials. Evidence access must not cross tenants/runs. |
| HTTP, if exposed: `ControlPlaneSecurityConfig.strict_defaults()`, `control_plane_api/_auth.py`, `control_plane_api_guards.py` | Keep route seals, role/subject checks, bounded request/offload queues, denial audit and no-store responses. An installed Python API does not require a new HTTP route. Never enlarge ingress limits to transport whole archives. |
| Secrets and participant disclosure: `secret_references.py`, `participant_configuration.py`, `runtime_fact_binding_policy.py`, participant crossing and `participant_flow_sink.py` | Keep opaque secret references until authorized sinks. Keep audience, freshness and information-flow decisions. Archive/export is a disclosure boundary, not permission to dump runtime state, protected prompts, hidden answers or resolved credentials. Digests do not authorize disclosure of sensitive inputs. |
| Environment/settings and host work: `raes/runtime_environment.py`, `runtime_configuration.py`, `runtime_generated_value.py`, semantic checks | Reuse typed environment shapes, unique names, sensitivity/provenance, literal versus `value_from` exclusivity and generated-output visibility. Generated values cannot claim `operator_secret`. No raw env dictionary, ambient credential lookup, shell interpolation, tokens in argv or broad inherited environment. Keep native effects and process isolation with existing backend owners. |
| Artifact acquisition and persistence: `uri_safety.py`, `_evidence_content_validation.py`, `control_plane_store_paths.py`, `RunMaterializationArchive` | Readers come from authorized configured owners; checks never fetch URIs. URI checks are not fetch authorization or SSRF protection. Keep containment, bounded regular-file reads, private permissions and symlink/link protections. Validate filesystem labels separately from logical IDs; never sanitize distinct IDs into colliding paths. Add no service, listener or data destination. |
| Errors and observability: shared `Diagnostic`/`DiagnosticModel`, `portable_diagnostic_payload()`, `backend_result_diagnostics.py`, `_responses.py::_conflict_detail()`, redacted API handlers | Use existing failures and safe envelopes; no parallel exception hierarchy. Do not expose Pydantic input dumps, raw exception/cause text, paths, provider responses, commands or stdout/stderr. Use module loggers and `AuditEvent`; `control_plane_audit.py::require_audit_event_fields()` has action-specific closed detail keys, so new correlation fields require canonical admission there. General logs are not task evidence. |
| Packages, contracts and workflow: `tools/policy/adr_policy.yaml`, `specs/authority/authority-boundary.yaml`, `.ground-control.yaml`, `.gc/plan-rules.md` | Respect import facades and the 500-line source cap. Runtime consumes processor public APIs; `raes_operations` must not import runtime/processor to build records. Published schema changes need archive write-ledger updates and matching `schema_bundle()` output; use `tools/check_schema_publication.py` and `tools/check_generated_schemas.py`. Do not invent a requirement UID for this issue. |

## Delivery boundary and non-goals

Publish supported runtime/record APIs through existing package facades and
document them in `docs/public/api/runtime.rst` and the applicable public guide.
Keep lazy exports and optional Temporal dependencies intact. Use
`implementations/python/pyproject.toml`, its build hook/corpus packaging,
`release-please-config.json` and `.github/workflows/release-please.yml` under the
[release process](../explain/releasing.md). A consumer-visible `feat:`/`fix:` title
must trigger the existing release machinery; never hand-edit versions/changelog.
Consumability requires CI evidence from the installed wheel and sdist outside
the checkout, exercising the public record APIs and packaged evidence schemas.
A source-tree import or tag is insufficient. Preflight does not publish anything.

Reuse focused patterns in `test_issue_1629_*`, `test_issue_1627_trial_unit.py`,
`test_sce_002_admitted_trial_plan.py`, `test_issue_1396_trial_replacement.py`,
`test_exp_731_archival_validation.py`, `test_issue_1237_evidence_proof.py`,
`test_issue_1547_capture_reference_version.py`, API/audit security tests and
`test_corpus_packaging.py`. Meaningful coverage must distinguish matching
commitments from actual treatment work, keep all failure cuts and prove
idempotent recovery across archive/store interruption. Use targeted local checks;
integration, full-suite and installed-distribution acceptance belong in CI/CD.
Assess changed archive write/recovery state under the existing assurance policy;
do not classify stateful transitions as mere serialization.

This issue does not introduce a scheduler, work/retry/cleanup policy,
backend, model service, statistical engine, replay engine, database, universal
artifact fetcher, new hosting or new public transport. The record builder must
not rerun effects, reinterpret authored treatments, grant clean-state reuse,
weaken checks to admit partial evidence, or turn operational logs into a
second provenance store. Keep the shared runtime and existing scientific
contract owners throughout.

## Concrete failure cases

A run starts, then its node fails to start. No model is called.
The run still exists. Keep its start and failure facts.
There is no score to report. A missing score is not zero.
A failed run must not vanish from a study's count.

A second run ends, but its cleanup fails. Keep its captured output.
Keep the cleanup failure as a separate fact.
A stored record does not prove that the target is safe.
Do not release the target until its checks pass.

A third run fails and an allowed retry works. Keep both attempts.
They share one run ID. They are not two samples in the study.
If the retry's reply is lost, read back the stored facts.
Do not start new work to obtain a reply.
A fresh replacement is a new run. Keep its link to the old run.

When end time is unknown, leave it unset.
When a reply is lost, keep the same key.
A new key means new work. Do not change the key to hide a failure.

An empty score field is not proof that a task failed.
State the cause of the missing score when it is known.
