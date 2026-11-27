# Issue 1547 capture reference version preflight

Non-normative architecture guidance. GitHub issue #1547 defines the scope.
No formal requirement is attached. Baseline: `cc117eb2`, branch
`1547-capture-reference-version`. This note contains no code changes.

[ADR-064](adrs/adr-064-experiment-evidence-and-measure-contract-boundary.md),
[ADR-066](adrs/adr-066-observability-evidence-plane-separation.md), and the
[capture-proof preflight](issue-1237-capture-proof-authority-preflight.md)
already define the evidence boundaries. No new ADR is needed.

## Decision and reference semantics

Keep the published `experiment-evidence-record-v1` contract. Its
`ExperimentCaptureSpecReferenceModel` requires only `ref_kind` and `ref_id`.
`ref_version` may be omitted or null. Correct satisfaction to use the existing
`raes_contracts.contracts.experiment_artifacts._reference_satisfies_requirement`
semantics, as `run_ref` already does.

The candidate is the supplied capture spec's actual identity, represented by
`ExperimentReferenceModel`: kind `capture-spec`, its `capture_spec_id`, and its
`spec_version`. The requirement argument is the record's `capture_spec_ref`.
Argument order matters.
The requirement supplies optional constraints.

| Record reference | Required outcome with otherwise valid evidence |
| --- | --- |
| Matching kind/id, omitted version | Accept through the full evidence validator. |
| Matching kind/id, null version | Same as omitted. |
| Matching kind/id, explicit matching version | Accept through the full evidence validator. |
| Explicit different version or wrong identity | Reject. Never ignore an explicit constraint. |

Versions compare exactly. Do not use version ranges, normalize versions,
resolve `latest`, or hardcode `1.0.0`. Do not reverse the matcher
arguments, change the shared matcher, or introduce a second comparison helper.
`schema_version` identifies the wire contract. `spec_version` identifies the
capture spec. Neither is the package version or record version.

Accepting this reference shape does not make every schema-valid record satisfy
an experiment. Source, window, disclosure, artifact and content failures remain
valid reasons to reject it. A missing version alone must no longer cause
rejection. Do not fill in or mutate the record's missing version as a repair.

Downstream owners already converge on this boundary:
`raes_contracts/contracts/experiment_study_run_validation.py`,
`raes_conformance/necessity_evidence.py`, and
`raes_conformance/repeatability_evidence.py` use
`validate_experiment_run_against_task`. Keep the fix in satisfaction rather
than adding producer-specific exceptions in these consumers. The control plane
is an adjacent security boundary, not a new ingress for this issue.

## Existing owners and cross-cutting gates

Paths below are relative to `implementations/python/packages/` unless stated
otherwise. All these boundaries remain in force.

| Layer | Canonical incumbent and guardrail |
| --- | --- |
| Contract shape | `raes_contracts._base.ContractModel` forbids extra fields. `contracts/experiment_references.py`, `experiment_manifest_references.py`, and `experiment_evidence.py` own reference and record checks inside `raes_contracts`. Keep `ref_kind="capture-spec"`. Digest/path qualifiers remain forbidden, including explicit null fields pruned from the published schema. No permissive DTO, alternate schema, or parser built for one adapter. |
| Exact admission and relation checks | `raes_processor/trial_compiler/inputs.py::_validate_capture_inputs`, `raes_processor/trial_realization.py::_validate_capture_specs`, and `AdmittedTrialPlanInputRefsModel` retain exact version/digest pins. `ExperimentEvidenceRequirementRelationModel` also requires a version. These contracts govern admission. They do not perform optional record-reference matching. Do not loosen them or the record's existing task-reference check. |
| Supplied evidence and ambiguity | `raes_contracts/evidence_satisfaction.py::_validate_supplied_evidence_sets` retains exact run-traceability spec and record versions. `_index_capture_evidence` rejects ambiguous requirement ids across supplied specs. It also rejects unresolved spec/requirement pairs. An omitted record version binds only within this admitted set. Never search a registry or choose the first/latest spec. |
| Satisfaction authority | Reuse `_validate_record_binding` and `validate_experiment_run_evidence`. Task/run ingress is `contracts/experiment_run_evidence_validation.py` with `ExperimentRunEvidenceInputs`. Study, trial analysis, necessity and repeatability consumers already reach this authority. Keep the metadata snapshot and model checks before reader callbacks. Keep aggregate limits and every execution, source, window, disclosure and output-contract check. Shape checks alone and `satisfies_refs` cannot establish satisfaction. |
| Bytes, parsers and installed schemas | `_evidence_content_validation.py` retains caller-supplied bounded `BinaryIO` readers and size/checksum checks. Keep its shared-content cache for each call, plus field selectors. Reuse `json_ingress`, `evidence_output_validation`'s atomic schema/semantic owner registry, `corpus_family_root(SCHEMAS)`, and `_domain_profile_schema_registry.profile_schema_registry`. Both JSON Schema and owning model checks remain required. Schema lookup stays packaged and offline. No duplicate registry, remote `$ref` fetch, unbounded parser, or runtime lookup tied to a source checkout. |
| Locators and secrets | `_validate_evidence_locator` and `uri_safety.validate_safe_absolute_uri` keep locators inert. They reject credentials, query secrets, unsafe host paths and file URIs before I/O. Keep raw content, signed URLs, secret bindings and environment values out of matching, fixtures, proof output and diagnostics. |
| Auth and configuration | This fix stays in process. It adds no endpoint, environment binding or config shape. Keep `raes_runtime/control_plane_security.py::ControlPlaneSecurityConfig` and existing role/target checks and request limits wherever callers expose results. No auth bypass, compatibility flag, token lookup or secret/config validator change is needed. |
| Host/OS exposure | Matching remains pure. It spawns no process, runs no shell, makes no network call and opens no host path. The caller still acquires artifact bytes. No token or evidence payload enters process argv, environment, stderr or logs. |
| Errors and observability | Keep the existing capture-reference `ValueError`, Pydantic shape failures and coarse output-contract errors. Conformance wrappers already map task/run failures to coarse `ValueError`s. Do not add an exception hierarchy or logger. Use existing `Diagnostic`, `AuditEvent` and redacted control-plane envelopes for outward errors. Do not expose payloads, locators, parser input, exception chains or raw `str(exc)` through a new route. |
| Proof and persistence | `evidence_proof.ValidatedEvidenceBinding` records the actual supplied spec version after full validation. `ValidatedRunEvidence` binds the validated task/run digests. Keep proofs immutable and process-local. They have no decoder or persisted validated flag. `raes_runtime/control_plane_store.py::ControlPlaneStore` and `AuditEvent` retain their roles. No store, cache service, migration or audit stream is required. |

## Extensibility and verification boundary

The existing seam is the matcher's `(candidate, requirement)` parameters and
the record's optional `ref_version`. Another spec revision needs only different
input values. It needs no central artifact edit, producer-specific branch or
config switch. A future digest/path constraint would require its owning
contract and admission design to change. Do not extend this pruned reference
type in advance.

Reuse the content-backed `_evidence_bundle` in
`implementations/python/tests/test_issue_1112_capture_admission.py` and the
optional-reference patterns in `test_exp_732_evidence_provenance.py`.
Tests must cover actual key omission and explicit null.
Assert omission on the wire payload before model validation: a default
`model_dump()` can materialize an omitted optional version as null, so testing
only that dump would miss the producer's shape.
They must cover matching and mismatching versions.
Wrong ids and kinds must fail at their owning layers. Include a
spec revision other than `1.0.0`, and assert that the successful proof records
that actual revision while the input reference stays unversioned. Keep the
run's exact traceability pin aligned with that supplied spec in this case;
an unrelated admission failure must not mask the matching behavior. Schema/model
acceptance alone or a direct private-helper test does not prove the fix.

Reuse `test_runtime_contracts.py`'s schema/model fixture checks and
`test_issue_1237_evidence_proof.py`'s full-proof and mutation protections.
A portable valid fixture can show omission. It cannot replace a content-backed
satisfaction test. Reject an explicit mismatch before artifact reader I/O.
Keep exact traceability and ambiguity checks. Run targeted checks locally.
Full, integration,
fuzz, research replay and completion suites belong to CI.

## Repository and publication boundaries

The normative schema remains under `contracts/schemas/`. `schema_bundle()` must
match it. This design needs
no schema or publication-ledger edit. If schema tightening is chosen instead,
it changes the selected design and invokes
[ADR-061](adrs/adr-061-published-schema-evolution-policy.md), generated-schema
parity, publication change records, compatibility review and downstream LilRAE
coordination. Do not quietly make `ref_version` required in the shared model.

Canonical gates are `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`,
the targeted `tools/check_repo_policy.py` checks, authority/concept-authority
checks, `tools/check_generated_schemas.py`, `tools/check_schema_publication.py`
and `tools/check_json_artifacts.py`. Reuse these rather than adding issue-local
workflow scripts. `tools/nox_support/runner.py::_requirement_aware_policy_args`
already selects `--skip-requirement` when no UID or issue-bound scope exists.
Use that existing requirement-free route. The standalone
`check_requirement_governance.py` rejects a missing UID. Do not fabricate one,
create a requirement assignment or weaken policy to make it pass.

`tools/research_evidence.py::implementation_digest` covers package Python
source. The eventual code change therefore needs fresh formal-semantic-validation
and specification-coverage captures in the same PR. Follow
[research-captures.md](../develop/research-captures.md) and
`python -m tools.research_capture record`, retaining the capture receipts,
baseline pins and honest observations. Do not relabel old observations by
replacing a digest, edit historical captures or shared research narrative
indexes, or allocate numbered releases on the feature branch. Numbered
`publish` receipts belong only to clean `dev` integration. This documentation
preflight does not change the implementation digest.

`docs/research/fixture-provenance/` is absent at this baseline. If #1461's
documents are present when the fix is integrated, update the existing EV-1
entry and inventory row with fix/test evidence. Do not invent their format or
mark the finding fixed in advance. Preserve unrelated audit findings.

## Non-goals and anti-patterns

No issue implementation, schema/fixture/test edits or research captures in
this preflight. No new ADR, generic reference resolver, evidence architecture,
policy, exception family, persistence layer, API or service. No changes to
capture admission, refinement semantics, output-contract eligibility,
redaction rules, integrity requirements, study claims or proof authority.
No external repository work, uploads or downstream builder changes for the
selected design. Release Please continues to own versions and `CHANGELOG.md`.
The eventual consumer-visible fix uses the existing release workflow.
