# Issue 1612 Required Cleanup Failure Receipts Preflight

Date: 2026-10-17

Issue #1612 corrects the released SCE-007 contract delivered by #658. This
note constrains the correction without implementing it or prescribing a work
sequence. ADR-009, ADR-036, ADR-061 and ADR-084 remain authoritative.

## Decision: validate reporting separately from successful cleanup

`validate_trial_cleanup_receipt()` in
`implementations/python/packages/raes_contracts/contracts/trial_cleanup.py`
remains the public plan/receipt join. Acceptance means the receipt consistently
reports an attempt, including failure; it does not certify resource reuse,
successful trial execution, successful cleanup, or satisfaction of retry policy.
Do not add an allow-failure flag, alternate receipt DTO, backend exception, or
downstream validation bypass.

The current unconditional success rule also appears in the normative
`specs/formal/scenario-variation-trial-realization/cleanup-contracts.md`, under
Receipt Semantics. That sentence needs reconciliation with the original
[SCE-007 preflight](issue-658-sce-007-clean-state-cleanup-contracts-preflight.md),
which explicitly separates trial and cleanup outcomes. A Python-only relaxation
would leave contradictory contract authority.

The corrected semantics must preserve these distinctions:

| Condition | Required interpretation |
| --- | --- |
| A required obligation matches the terminal trigger | Its keyed result must exist, whatever the aggregate cleanup status. |
| Aggregate cleanup is `succeeded` | Every triggered required result succeeds; retain the existing receipt rule rejecting any unsuccessful reported result, including best-effort results. |
| Aggregate cleanup is `failed`, `partial`, `unsupported`, or `unverified` | A triggered required result may be `succeeded`, `failed`, `unsupported`, or `unverified`. Failure reporting does not downgrade the admitted obligation. |
| A triggered required result is `skipped` or `not-triggered` | Reject: neither satisfies owed-result coverage. Preserve this protection when removing the unconditional success check. |
| An obligation does not match the terminal trigger | Omission or an explicit `not-triggered` result is appropriate; an execution result must not silently assert a different trigger. |
| Aggregate cleanup is `not-required` | Retain the model's empty-result rule; reject if any required obligation is triggered. |
| A result is `succeeded` | Require evidence and forbid residual state, independently of aggregate status. |
| A result is `failed` or `unverified` | Retain evidence-or-residual disclosure; neither evidence nor residuals alone proves cleanup success. |
| Any clean-state claim is present | Require aggregate success and preserve bounded claim references/evidence; failure statuses cannot carry such a claim. |

Use the existing `_OUTCOME_TRIGGER` mapping for all five primary outcomes:
success, failure, cancellation, timeout, and abort. Cancellation/interruption
is not proof of failed cleanup: cleanup may succeed or remain unverified.
Equally, successful primary execution may have failed cleanup.

`partial` is an aggregate status, not an obligation-result status. The existing
valid `partial-cleanup.json` has one failed result; do not redefine partial to
require a mixture of successes and failures. Preserve the existing allowance
for an `unsupported` result without evidence, rather than quietly adding a new
wire requirement. Non-success aggregate labels are producer disclosures, not a
new exact reduction or precedence algorithm over result statuses. They never
override per-result integrity or authorize a clean-state claim.

Trigger consistency is a guardrail to make explicit, not an existing complete
check: `_validate_triggered_cleanup_results()` currently checks only triggered
required obligations. Reconcile inactive-obligation reporting in the same
plan-aware join; do not move it into the result DTO, which lacks the plan.
Best-effort obligations may remain absent or report `skipped` when applicable;
they must not inherit required-result coverage. Accepting an explicit failure
records an unmet obligation, not permission to omit it or reuse its boundary.

`retry` exists in `CleanupTrigger` but not `TrialOutcome`. A terminal receipt
must not manufacture a retry outcome or treat retry-only obligations as owed by
every terminal outcome. Existing `ExecutionRetryPolicyModel` and
`_trial_cleanup_validation.validate_reset_retry_obligations()` own reset policy
references and boundary coverage. This correction does not prove that a later
retry is safe. Any future explicit retry-event reporting needs an event-context
seam at the existing validator boundary, with governed contract semantics;
do not infer it from attempt-id spelling or add caller-configurable validation
leniency. Parameterize terminal-case coverage from the existing outcome/trigger
vocabulary rather than copying five separate validators.

## Layers and incumbents

- **Shape and local integrity:** reuse `raes_contracts._base.ContractModel`
  (`extra="forbid"`), existing literal vocabularies, uniqueness checks, result
  validators, and `TrialCleanupReceiptModel._validate_receipt()`. These own
  single-object facts. Plan-dependent coverage, trigger applicability, and
  references belong in the public join, without a second validation framework.
  Preserve plan id, entry id, run id, distinct attempt id, map-key/embedded-id
  equality, unknown-obligation rejection, and clean-state boundary checks.
  Do not describe arbitrary evidence strings as verified probe execution.
- **Admission and config shapes:** preserve closed cleanup capability models in
  `contracts/manifests.py`, backend manifest rendering, and
  `raes_backend_protocols.capabilities.require_cleanup_plan_capability()`.
  Its implementation lives in `capability_admission.py`; reuse
  `CleanupCapabilities`, `CleanupCapabilitiesModel`, `BackendManifest`, and
  `manifest.py` rendering/parsing rather than adding a capability adapter.
  Reporting an unsupported runtime result must not admit a backend known to
  lack required capability. Preserve `revalidate_admitted_trial_plan()` at
  processor ingress and sealed-plan digests. `ContractModel` is not frozen;
  object construction, `model_copy(update=...)`, and mutation are not substitutes
  for validation at existing trust boundaries. No config/environment-binding
  fields or schema exceptions are needed for this correction.
  `admitted_trial_plan_ingress.parse_admitted_trial_plan_json()` already uses
  `json_ingress.parse_bounded_json_object()` to enforce the input byte bound,
  object root, duplicate-member rejection, and finite numbers before model
  reconstruction. Preserve that ingress rather than introducing a permissive
  JSON loader; the semantic join takes validated models, not raw JSON.
- **Batch and archival joins:** `contracts/batch_execution.py` and
  `contracts/trial_analysis.py` already delegate to the cleanup validator. Keep
  that delegation and all attempt/outcome/plan/provenance checks. In
  `test_sce_006_batch_scheduler.py`,
  `test_failed_cleanup_cannot_be_reported_as_a_clean_successful_trial` currently
  expects rejection of a successful primary trial with truthful failed cleanup
  and no clean claim. That expectation conflates outcomes and needs correction;
  preserve rejection of actual false success and unsupported clean claims.
  Retain failed-attempt evidence in reconciliation without rewriting archival
  primary status. No new repository, persistence service, or receipt store.
- **Auth, errors, and observability:** this remains pure in-memory validation,
  with existing `ValueError`/Pydantic `ValidationError` conventions. Valid failure
  evidence is data, not a new exception class. No route/auth change is required;
  existing control-plane `_auth.py` admission/target binding and
  `_operation_routes.py` redacted exception/request-validation handlers remain
  the transport boundary if reached. Do not expose raw validation input,
  exception text, traceback, backend output, or receipt bodies in HTTP errors
  or logs. Existing evidence references provide traceability; no new logging
  sink or telemetry path is needed.
- **Secrets and OS/runtime:** ids and evidence/residual references stay opaque
  data. Closed fields reject extra credential properties but `NonEmptyString`
  does not detect embedded secrets. Producers must supply safe references;
  do not dereference them, inspect resources, resolve credentials, dump env,
  execute cleanup, or pass data to shell/process argv in this validator. The
  correction requires no secret resolver, env-binding relaxation, filesystem
  lookup, network request, host privileges, or external service.

The wider runtime retains `ControlPlaneStore`, operation receipts and audit
events for mutable operational state, and `trial_provenance.py` plus
`ExperimentRunModel` for archival identity and evidence. Cleanup reporting must
not introduce a second scenario lifecycle or redefine workflow compensation.
`SchedulerIsolationProofModel`, `validate_scheduler_isolation_proof()`, and
`trial_scheduler.py` retain serial default and the admitted parallelism ceiling;
failure-report acceptance changes neither isolation nor dispatch authority.
Operational/conformance `cleanup_verified` and native-driver cleanup summaries
are separate evidence surfaces, not alternate validators or wire-status enums
to merge into this contract.

## Contract publication and verification boundaries

The hand-governed `contracts/schemas/` corpus is authority; `schema_bundle()` in
`contracts/bundle.py` must continue generating identical schemas. Preserve the
receipt's `x-raes-invariants` public validator linkage and distinguish JSON
Schema shape checks from semantic joins that require both plan and receipt.
If schema annotations or constraints change, update the corresponding entry's
hash and `last_change` under `contracts/schema-publication/entries/`, the v2
manifest's canonical ledger location. Use `tools/check_generated_schemas.py`
and `tools/check_schema_publication.py`; do not overwrite the corpus merely to
silence drift. The cleanup entries are currently draft; apply ADR-061 to any
additional tightening rather than assuming every change is a compatible fix.

Reuse `test_sce_006_cleanup_contracts.py`, its fixture helpers/corpora, batch
receipt tests, and `test_sce_002_trial_realization.py` for affected joins.
Fixture JSON Schema acceptance alone does not test plan/receipt compatibility:
pair receipts with matching plans and exercise the public validator. Cover
truthful failure, partial/unsupported/unverified reporting, all five terminal
triggers, successful cleanup independent of primary outcome, mixed required
and best-effort obligations, inactive triggers and retry-only obligations.
Negative coverage must retain missing required results under non-success as
well as success, skipped/not-triggered owed results, false success, residuals
on successful results, unsupported clean claims, and identity/reference errors.
Use targeted local tests/checks; repository-wide, integration, fuzz, and
completion suites belong to CI per `AGENTS.md` and `.gc/plan-rules.md`.

A source merge alone does not unblock a released consumer. Reuse
`release-please-config.json`, `.github/workflows/release-please.yml`, existing
release-evidence/admission gates, and the `raes` wheel/sdist corpus packaging in
`implementations/python/pyproject.toml`. `raes_contracts.corpus` is the canonical
installed/source corpus resolver. A consumer-visible `fix:` title enables the
normal release path; do not hand-edit `_version.py`/`CHANGELOG.md`, create a
parallel package, or claim downstream availability before a consumable release
exists. Publication and protected-branch merges retain their existing approvals.

## Non-goals

No cleanup executor, scheduler redesign, workflow compensation changes, retry
admission relaxation, backend mechanics, downstream LilRAE implementation,
automatic resource reuse, stronger proof of evidence authenticity, new contract
version by default, or generic aggregation/policy engine. Keep the correction
inside the existing portable contract and its affected semantic consumers,
normative invariants, fixtures, and established release path.
