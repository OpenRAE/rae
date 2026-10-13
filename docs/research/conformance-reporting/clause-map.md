# Conformance and support reporting clause map

[ASR-526](../../requirements/ASR-526/requirement.md) asks for conformance and
support reports for processors and backends. The reports must be both
machine-readable and human-readable. The first done-when item of issue #222
asks for a map from every ASR-526 clause to the existing backend reporting. It
also asks which processor reporting is missing. This page is that map. It
changes no code and no requirement text.

ASR-526 is DRAFT, and its record does not number its clauses. The labels C1 to
C7 belong to this page. Code paths are relative to
`implementations/python/packages/`, and `contracts/` paths to the repository
root. Test paths are relative to `implementations/python/tests/`. Code is
cited as `path::symbol`, where the symbol names a definition. A field, local
name or call keyword is qualified by its class or function, as in
`BackendConformanceReport.profile`. A quoted symbol, such as a diagnostic
code, is a string in that file. Citations carry no line numbers, so code that
moves inside its file leaves them valid.

## How the statement is split

The statement reads:

> The ecosystem shall provide machine-readable and human-readable conformance
> and support reports for processors and backends that expose achieved
> conformance profile or level, passed and failed checks, declared and
> observed unsupported or partially supported capabilities, applicable
> validation basis, and diagnostics sufficient to explain gaps or limitations.

The split follows the sentence's own structure and adds no clause of its own:

1. Each of the five things the reports "expose" is one clause, C3 to C7. A
   clause keeps its own "and" and "or" pairs, such as "passed and failed
   checks". Where only part of a clause is met, its section says which part.
2. "machine-readable and human-readable" becomes two clauses, C1 and C2. They
   are two outputs, and either can exist without the other.
3. "for processors and backends" applies to every clause. It is a column, not
   a clause.
4. "conformance and support reports" is one report family. Issue #222 asks to
   extend the existing surfaces rather than add another report family. C5
   carries the support content.
5. "The ecosystem shall provide" and "that expose" frame the clauses and add
   none.

A finer split, such as one clause for each side of an "and", reuses the same
evidence. To try one, divide a row. Its citations stay the same.

## Clause map

**Covered** means the cited code exposes what the clause names, and a cited
test exercises it. **Partial** means only part of it is exposed, and the
section names the missing part. **Gap** means nothing exposes it.

| Clause | Statement words | Backends | Processors |
| --- | --- | --- | --- |
| C1 | "machine-readable" | Covered | Gap |
| C2 | "human-readable" | Gap | Gap |
| C3 | "achieved conformance profile or level" | Partial | Gap |
| C4 | "passed and failed checks" | Covered | Gap |
| C5 | "declared and observed unsupported or partially supported capabilities" | Partial | Gap |
| C6 | "applicable validation basis" | Partial | Gap |
| C7 | "diagnostics sufficient to explain gaps or limitations" | Partial | Gap |

## Evidence by clause

### C1 machine-readable reports

- **Backends: covered.**
  `raes_conformance/conformance/report.py::backend_conformance_report_payload`
  renders a report as one JSON-ready mapping. It first calls
  `raes_conformance/conformance/report.py::validate_backend_conformance_report`,
  which refuses a report that claims more than its cases show. The
  `raes conformance backend` command is
  `raes_cli/conformance.py::backend`. It prints the mapping and exits
  with code 1 when the report fails.
  `raes_operations/realization_conformance.py::write_backend_conformance_report`
  stores the mapping as a run artifact after a redaction check.
  - Tests:
    `test_backend_conformance_cli.py::test_backend_conformance_cli_passes_for_provisioning_only_profile`,
    `test_asr_535_participant_flow_assurance.py::test_serialization_runs_the_validation_seam_before_the_payload_is_produced`
    and
    `test_realization_honesty_conformance.py::test_machine_readable_report_write_is_redaction_gated`.
  - Limits: the command runs only the fixture suite,
    `raes_conformance/conformance/fixture_suite.py::run_fixture_suite`.
    No `raes` command runs
    `raes_conformance/conformance/target.py::run_target_conformance`,
    so target reports come only from the Python API. No schema under
    `contracts/schemas/` describes the mapping. ASR-526 does not ask for one.
- **Processors: gap.** No processor conformance report exists. The only
  machine-readable processor output about support is the manifest,
  `raes_processor/manifest.py::reference_processor_manifest_payload`.
  The `raes processor manifest` command,
  `raes_cli/processor.py::manifest`, prints it. A manifest declares
  support and records no checks.
  - Test:
    `test_processor_manifest.py::test_processor_manifest_cli_emits_reference_v2_manifest`.

### C2 human-readable reports

- **Backends: gap.** `raes conformance backend` prints JSON only.
  `raes_cli/conformance.py::backend` passes the indented mapping to
  `typer.echo`. No other code renders a conformance report for people.
  - The `raes semantic` commands already render one result in either form.
    `raes_cli/_semantic_result.py::OutputFormat` offers `human` and
    `json`, and `raes_cli/_semantic_result.py::render_result` prints
    either. The `raes semantic conformance` command,
    `raes_cli/semantic.py::conformance_command`, uses them to check one
    artifact against one registered contract, such as a backend manifest.
    That check is not a conformance and support report. It names no profile,
    cases or support levels.
- **Processors: gap.** There is no processor report to render. Also,
  `raes semantic conformance` cannot check a processor manifest, because
  `processor-manifest-v2` is not a registered contract. The command answers
  with `raes_cli/_semantic_portable.py::"cli.selector"` and exit code 2.
  By contrast,
  `raes_conformance/conformance/validators.py::"backend-manifest-v2"`
  is registered.

### C3 achieved conformance profile or level

- **Backends: partial.** A report names one profile,
  `raes_conformance/conformance/report.py::BackendConformanceReport.profile`,
  which the class docstring calls the requested profile.
  `raes_conformance/conformance/report.py::BackendConformanceReport.passed`
  says whether every check for that profile passed. When the caller names no
  profile,
  `raes_conformance/conformance/target.py::profile_for_manifest` infers
  one from the roles the manifest declares. The run then uses it as
  `raes_conformance/conformance/target.py::run_target_conformance.effective_profile`.
  `raes_conformance/conformance/report.py::BackendConformanceReport.native_conformance`
  adds one level above a plain pass. The runner sets it only when the report
  passed and its realization probes passed on a native-live basis, at
  `raes_conformance/conformance/target.py::_known_profile_report.native_conformance`.
  The report claim states its own assurance level, `tested`, at
  `raes_conformance/conformance/report.py::_bounded_conformance_claim.assurance_status`.
  - Tests:
    `test_runtime_conformance.py::test_profile_is_inferred_as_full_when_manifest_declares_participant_runtime`,
    `test_realization_honesty_conformance.py::test_only_native_live_can_support_native_conformance`
    and
    `test_realization_honesty_conformance.py::test_failed_report_cannot_claim_native_conformance`.
  - Missing: when the profile fails, the report names no profile or level
    that the target did achieve. It also does not say whether its profile was
    requested or inferred. The second done-when item of #222 asks for
    "requested versus achieved profile/level".
- **Processors: gap.** Nothing reports a processor's achieved profile or
  level. The nearest check is a repository test,
  `test_semantic_profiles.py::test_reference_processor_satisfies_processing_profile`.
  It asserts that the reference processor manifest declares what the
  `processing` section of the `reference-stack-v1` semantic profile requires.
  That is a test assertion, not a report.

### C4 passed and failed checks

- **Backends: covered.** Each check is one case.
  `raes_conformance/conformance/report.py::ConformanceCaseResult`
  records `valid`, `passed` and `outcome` for it.
  `raes_conformance/conformance/report.py::ConformanceCaseResult.__post_init__`
  turns a `passed` outcome into `failed` when the case did not pass. The
  fixture suite adds one case for each valid and each invalid fixture. It passes only when
  every case passes, as
  `raes_conformance/conformance/fixture_suite.py::run_fixture_suite`
  shows. Target runs add participant, adapter and realization probe cases.
  The closed probe outcome vocabulary also has `skipped` and `unsupported`,
  in `raes_conformance/_realization_models.py::ProbeOutcome`.
  `raes_conformance/conformance/report.py::_validate_case_evidence`
  refuses a passed report that carries a failed case. It also refuses a claim
  that cites a case the report does not carry.
  - Tests:
    `test_runtime_conformance.py::test_fixture_suite_passes_for_orchestration_evaluation_profile`,
    `test_backend_conformance_cli.py::test_backend_conformance_cli_catches_seeded_manifest_violation`,
    `test_asr_535_participant_flow_assurance.py::test_report_validation_requires_every_claimed_case_to_be_present`
    and
    `test_realization_honesty_conformance.py::test_dishonest_positive_behaviors_fail_for_stable_reason`.
- **Processors: gap.** No processor check runs as part of a report. Only
  repository tests check processor behavior.

### C5 declared and observed unsupported or partially supported capabilities

- **Backends: partial.**
  - Gaps against the profile:
    `raes_conformance/conformance/report.py::BackendConformanceReport.unsupported_contract_gaps`
    lists the contracts that the profile requires and the manifest does not
    declare. `raes_conformance/conformance/target.py::_declared_contract_gaps`
    computes them.
    `raes_conformance/conformance/report.py::BackendConformanceReport.unsupported_capability_gaps`
    lists the runtime roles that the target lacks, from
    `raes_conformance/conformance/target.py::_capability_gaps`. It also
    lists capability claims made without their contracts.
  - Declared support levels: each policy feature in the manifest's
    participant feature-support list gets a case. The case records
    `raes_conformance/conformance/report.py::ConformanceCaseResult.declared_support_level`
    and
    `raes_conformance/conformance/report.py::ConformanceCaseResult.effective_support_level`.
    The levels come from the ADR-054 scale,
    `raes_contracts/vocabulary.py::ParticipantFeatureSupportLevel`:
    `unsupported`, `disclosed_weak`, `bounded` and `exact`. For these cases,
    `raes_conformance/conformance/target.py::_participant_feature_cases`
    resolves the effective level from the manifest. So it is declared, not
    observed.
  - Observed support: participant-policy probes drive the runtime boundary.
    They record the observed level beside the declared one, as
    `raes_conformance/conformance/participant_policy_probes.py::_case_result.effective_support_level`.
    A probe that observes a breach of the declared obligation fails with
    `raes_conformance/conformance/participant_policy_probes.py::"conformance.participant-policy-overclaim"`.
    In a release case, an effective level that differs from the declared one
    is such a breach. A declared feature that no authorized probe established
    becomes an `unsupported` case, from
    `raes_conformance/conformance/participant_policy_probes.py::_unsupported_case`.
    A participant-opacity case keeps an effective level only when its probe
    passed, at
    `raes_conformance/conformance/participant_opacity_probes.py::_run_case.effective_support_level`.
  - Realization probes record observed behavior beside the plan:
    `raes_conformance/realization.py::_positive_case.accounted_operations`
    beside the expected operations, and
    `raes_conformance/realization.py::_positive_case.actual_observation_strengths`
    beside the expected strengths. An envelope that yields no usable probes
    becomes an `unsupported` case, from
    `raes_conformance/realization.py::_constructive_failure`.
  - Tests:
    `test_runtime_conformance.py::test_target_conformance_fails_when_declared_contracts_do_not_cover_profile_requirements`,
    `test_runtime_conformance.py::test_target_conformance_rejects_participant_capability_claims_without_contract_evidence`,
    `test_runtime_conformance.py::test_target_conformance_records_evidence_backed_exact_policy_support`,
    `test_asr_535_participant_flow_assurance.py::test_an_overclaiming_target_fails_instead_of_retaining_its_exact_claim`,
    `test_asr_535_participant_flow_assurance.py::test_declared_policy_support_without_a_probe_harness_is_unsupported_not_passed`,
    `test_issue_965_participant_opacity_backend.py::test_declared_profile_without_executed_cases_is_unsupported`
    and
    `test_realization_honesty_conformance.py::test_current_open_libvirt_envelope_fails_as_non_constructive_without_fallback`.
  - Missing: observed support levels exist only for participant-policy and
    participant-opacity features. Contract and role gaps compare the manifest
    and the target's components with the profile, and no probe observes them.
    The report has
    no single list of unsupported or partially supported capabilities. A
    reader joins the two gap lists and the case levels. No test asserts the
    `conformance.unsupported-surface` diagnostic that a missing runtime role
    produces in
    `raes_conformance/conformance/target.py::_gap_diagnostics`.
- **Processors: gap.** The processor manifest declares support: contract
  versions, SDL versions, features and compatible backends, in
  `raes_processor/manifest.py::create_reference_processor_manifest`.
  Its vocabulary has no unsupported or partial level. A feature is either in
  `raes_processor/capabilities.py::ProcessorCapabilitySet.supported_features`
  or absent. The reference processor declares every feature, at
  `raes_processor/manifest.py::create_reference_processor_manifest.supported_features`.
  Nothing observes processor support.

### C6 applicable validation basis

- **Backends: partial.**
  - Each case records its
    `raes_conformance/conformance/report.py::ConformanceCaseResult.execution_basis`:
    `fixture-only`, `hermetic-live` or `native-live`, from
    `raes_conformance/_realization_models.py::ExecutionBasis`. The
    target runner's basis defaults to `hermetic-live`, at
    `raes_conformance/conformance/target.py::_TargetConformanceOptions.execution_basis`.
  - The report claim fixes the evidence scope.
    `raes_conformance/conformance/report.py::_bounded_conformance_claim.quantifier_scope`
    is `finite-cases`, and
    `raes_conformance/conformance/report.py::_bounded_conformance_claim.evidence_scope`
    is `finite`.
    `raes_conformance/conformance/report.py::_bounded_conformance_claim.evidence_boundary`
    counts the named cases. Cases add
    `raes_conformance/conformance/report.py::ConformanceCaseResult.finite_scope`,
    limitations and nonclaims.
  - `raes_conformance/conformance/report.py::_validate_claim_strength`
    refuses a universal claim backed by finite evidence. It also refuses a
    native claim without a native-live case.
    `raes_conformance/conformance/report.py::_validate_backend_conformance_claim`
    requires six digests for a backend conformance claim: profile, manifest,
    configuration, tool, environment and probe set.
  - Tests:
    `test_asr_535_participant_flow_assurance.py::test_report_validation_rejects_a_universal_quantifier_backed_by_finite_evidence`,
    `test_asr_535_participant_flow_assurance.py::test_report_validation_rejects_native_conformance_without_native_evidence`,
    `test_issue_965_participant_opacity_backend.py::test_forged_manifest_digest_cannot_bind_backend_conformance`
    and
    `test_runtime_conformance.py::test_stub_target_realization_claim_fails_closed_until_its_envelope_is_constructive`.
  - Missing: the report carries no validation-basis disclosure of the kind
    that [proposed ADR-072](../../decisions/adrs/adr-072-validation-and-admission-profiles.md)
    describes. The carrier for one is
    `raes_contracts/contracts/validation_disclosure.py::ValidationBasisDisclosureModel`,
    with its
    `raes_contracts/contracts/validation_disclosure.py::ValidationBasisDisclosureModel.achieved_strength`.
    Its subject kinds include
    `raes_contracts/contracts/validation_disclosure.py::"backend_conformance_claim"`,
    and the validation profile catalog lists that kind at
    `contracts/profiles/validation/validation-profile-catalog-v1.json::"backend_conformance_claim"`.
    No report field holds a disclosure. Fixture cases also omit each
    contract's validation strength.
    `raes_conformance/conformance/validators.py::contract_validation_strength`
    computes it, and `raes semantic` reports it as
    `raes_cli/_semantic_portable.py::_execute_registered_portable.validation_strength`.
- **Processors: gap.** No processor report exists to carry a basis. The
  disclosure's subject kinds include no processor kind, in
  `raes_contracts/contracts/validation_disclosure.py::_SUBJECT_KIND_TO_REF_KIND`.

### C7 diagnostics sufficient to explain gaps or limitations

- **Backends: partial.**
  - Reports and cases both carry diagnostics, in
    `raes_conformance/conformance/report.py::BackendConformanceReport.diagnostics`
    and
    `raes_conformance/conformance/report.py::ConformanceCaseResult.diagnostics`.
    The payload keeps each diagnostic's code, domain, address, severity and
    message.
  - Each gap kind that the runner detects has its own code:
    `raes_conformance/conformance/target.py::"conformance.unsupported-contract-declaration"`,
    `raes_conformance/conformance/target.py::"conformance.unsupported-surface"`,
    `raes_conformance/conformance/target.py::"conformance.unsupported-capability-claim"`,
    `raes_conformance/conformance/profiles.py::"conformance.profile-load-failed"`,
    `raes_conformance/conformance/target.py::"conformance.profile-runtime-surface-unknown"`,
    `raes_conformance/conformance/fixture_suite.py::"conformance.fixture-missing"`,
    `raes_conformance/conformance/target.py::"conformance.participant-feature-support-invalid"`,
    `raes_conformance/conformance/participant_policy_probes.py::"conformance.participant-policy-probe-missing"`,
    `raes_conformance/realization.py::"conformance.realization-harness-missing"`
    and
    `raes_conformance/realization.py::"conformance.native-basis-required"`.
  - Limitations travel as text. Cases carry
    `raes_conformance/conformance/report.py::ConformanceCaseResult.limitations`
    and
    `raes_conformance/conformance/report.py::ConformanceCaseResult.explicit_non_claims`.
    The claim that
    `raes_conformance/conformance/report.py::_bounded_conformance_claim`
    builds carries its own limitations and nonclaims.
    `raes_conformance/conformance/profiles.py::_sanitize_load_error`
    describes a failure without echoing the rejected input, so a report can be
    stored.
  - Tests:
    `test_backend_conformance_cli.py::test_backend_conformance_cli_emits_structured_profile_load_diagnostics`,
    `test_backend_conformance_cli.py::test_backend_conformance_cli_exits_non_zero_when_fixtures_missing`,
    `test_runtime_conformance.py::test_run_target_conformance_refuses_unknown_profile_id`
    and
    `test_asr_535_participant_flow_assurance.py::test_rejected_payload_content_never_reaches_a_conformance_diagnostic`.
  - Missing: a failed invalid-fixture case has no diagnostic. When the
    validators accept a fixture from an `invalid/` directory, the case fails
    with an empty diagnostics list, at
    `raes_conformance/conformance/fixture_suite.py::run_fixture_suite.case_diagnostics`.
    The report adds no diagnostic either. Only `valid: false` with
    `passed: false` marks the failure. No test asserts the
    `conformance.unsupported-surface` path (see C5). Whether diagnostics are
    "sufficient" is a judgment. This map checks only that they exist.
- **Processors: gap.** Processor commands report scenario diagnostics. One
  example is the `diagnostics` list that `raes processor plan` prints, built
  in `raes_cli/processor.py::_execution_plan_payload`. None of them
  explains a gap in a processor's own support.

## Missing processor reporting

Processors have one reporting surface: the manifest. It declares supported
contracts, SDL versions, features and compatible backends (C1, C5). Against
ASR-526, processors lack:

- a conformance report in JSON (C1) and in a form for people (C2);
- an achieved profile or level (C3);
- passed and failed checks (C4);
- unsupported or partial support, declared or observed (C5);
- a validation basis, including a processor subject kind for a disclosure
  (C6);
- diagnostics that explain processor gaps or limitations (C7).

Two records bear on any addition.
[ASR-518](../../requirements/ASR-518/requirement.md), also DRAFT, asks for
processor conformance profiles, fixtures and executable checks. The
[issue 196 preflight](../../decisions/issue-196-run-313-reference-processor-preflight.md)
says that a processor conformance addition should follow the backend
conformance model. This map does not choose a design.

## Limits of this map

- The map changes no runtime code, profile or requirement text. It claims no
  executable or runtime adoption.
- A status rests on the cited code and tests. "Covered" means the cited code
  exposes what the clause names. It does not mean that the exposure suffices
  for every consumer.
- The map does not assess the other done-when items of #222.
- ASR-526 is DRAFT and has no phase in `tools/policy/requirement_order.yaml`,
  so its words can change. The check below then fails until the map follows.

## How the map is checked

`test_issue_222_conformance_clause_map.py` fails when any of these holds:

- A clause's statement words no longer appear in the ASR-526 statement, or
  the statement gains words that no clause or frame phrase covers.
- A clause loses its row or its section, or gains a second one. A table
  status disagrees with its section.
- A cited code file is missing, or it no longer defines the cited symbol or
  holds the cited string.
- A cited test module or `module::test` function is missing.
- A link opens no page.

The check reads no line numbers, so code that moves inside its file still
passes. Renaming or removing a cited symbol or string fails it.
