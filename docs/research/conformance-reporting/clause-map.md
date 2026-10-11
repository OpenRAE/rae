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
root. Test paths are relative to `implementations/python/tests/`. Each code
citation names a symbol and the line that holds it.

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
  `backend_conformance_report_payload` (`raes_conformance/conformance/report.py:299`)
  renders a report as one JSON-ready mapping. It first calls
  `validate_backend_conformance_report` (`raes_conformance/conformance/report.py:140`),
  which refuses a report that claims more than its cases show. The
  `raes conformance backend` command is
  `backend` (`raes_cli/conformance.py:27`). It prints the mapping and exits
  with code 1 when the report fails.
  `write_backend_conformance_report` (`raes_operations/realization_conformance.py:12`)
  stores the mapping as a run artifact after a redaction check.
  - Tests:
    `test_backend_conformance_cli.py::test_backend_conformance_cli_passes_for_provisioning_only_profile`,
    `test_asr_535_participant_flow_assurance.py::test_serialization_runs_the_validation_seam_before_the_payload_is_produced`
    and
    `test_realization_honesty_conformance.py::test_machine_readable_report_write_is_redaction_gated`.
  - Limits: the command runs only the fixture suite,
    `run_fixture_suite` (`raes_conformance/conformance/fixture_suite.py:26`).
    No `raes` command runs
    `run_target_conformance` (`raes_conformance/conformance/target.py:365`),
    so target reports come only from the Python API. No schema under
    `contracts/schemas/` describes the mapping. ASR-526 does not ask for one.
- **Processors: gap.** No processor conformance report exists. The only
  machine-readable processor output about support is the manifest,
  `reference_processor_manifest_payload` (`raes_processor/manifest.py:99`).
  The `raes processor manifest` command,
  `manifest` (`raes_cli/processor.py:69`), prints it. A manifest declares
  support and records no checks.
  - Test:
    `test_processor_manifest.py::test_processor_manifest_cli_emits_reference_v2_manifest`.

### C2 human-readable reports

- **Backends: gap.** `raes conformance backend` prints JSON only.
  `typer.echo` (`raes_cli/conformance.py:61`) writes the indented mapping. No
  other code renders a conformance report for people.
  - The `raes semantic` commands already render one result in either form.
    `OutputFormat` (`raes_cli/_semantic_result.py:19`) offers `human` and
    `json`, and `render_result` (`raes_cli/_semantic_result.py:139`) prints
    either. The `raes semantic conformance` command,
    `conformance_command` (`raes_cli/semantic.py:225`), uses them to check one
    artifact against one registered contract, such as a backend manifest.
    That check is not a conformance and support report. It names no profile,
    cases or support levels.
- **Processors: gap.** There is no processor report to render. Also,
  `raes semantic conformance` cannot check a processor manifest, because
  `processor-manifest-v2` is not a registered contract. The command answers
  with `cli.selector` (`raes_cli/_semantic_portable.py:42`) and exit code 2.
  By contrast,
  `backend-manifest-v2` (`raes_conformance/conformance/validators.py:120`)
  is registered.

### C3 achieved conformance profile or level

- **Backends: partial.** A report names one profile,
  `profile` (`raes_conformance/conformance/report.py:123`), which the class
  docstring calls the requested profile.
  `passed` (`raes_conformance/conformance/report.py:124`) says whether every
  check for that profile passed. When the caller names no profile,
  `profile_for_manifest` (`raes_conformance/conformance/target.py:54`) infers
  one from the roles the manifest declares. The run then uses it as
  `effective_profile` (`raes_conformance/conformance/target.py:383`).
  `native_conformance` (`raes_conformance/conformance/report.py:132`) adds one
  level above a plain pass. The runner sets it only when the report passed
  and its realization probes passed on a native-live basis, at
  `native_conformance` (`raes_conformance/conformance/target.py:361`). The
  report claim states its own assurance level, `tested`, at
  `assurance_status` (`raes_conformance/conformance/report.py:380`).
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
  `ConformanceCaseResult` (`raes_conformance/conformance/report.py:66`)
  records `valid`, `passed` and `outcome` for it.
  `__post_init__` (`raes_conformance/conformance/report.py:105`) turns a
  `passed` outcome into `failed` when the case did not pass. The fixture suite
  adds one case for each valid and each invalid fixture. It passes only when
  every case passes, as
  `run_fixture_suite` (`raes_conformance/conformance/fixture_suite.py:26`)
  shows. Target runs add participant, adapter and realization probe cases.
  The closed probe outcome vocabulary also has `skipped` and `unsupported`,
  in `ProbeOutcome` (`raes_conformance/_realization_models.py:23`).
  `_validate_case_evidence` (`raes_conformance/conformance/report.py:254`)
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
    `unsupported_contract_gaps` (`raes_conformance/conformance/report.py:128`)
    lists the contracts that the profile requires and the manifest does not
    declare. `_declared_contract_gaps` (`raes_conformance/conformance/target.py:121`)
    computes them.
    `unsupported_capability_gaps` (`raes_conformance/conformance/report.py:129`)
    lists the runtime roles that the target lacks, from
    `_capability_gaps` (`raes_conformance/conformance/target.py:78`). It also
    lists capability claims made without their contracts.
  - Declared support levels: each policy feature in the manifest's
    participant feature-support list gets a case. The case records
    `declared_support_level` (`raes_conformance/conformance/report.py:92`)
    and
    `effective_support_level` (`raes_conformance/conformance/report.py:93`).
    The levels come from the ADR-054 scale,
    `ParticipantFeatureSupportLevel` (`raes_contracts/vocabulary.py:174`):
    `unsupported`, `disclosed_weak`, `bounded` and `exact`. For these cases,
    `_participant_feature_cases` (`raes_conformance/conformance/target.py:226`)
    resolves the effective level from the manifest. So it is declared, not
    observed.
  - Observed support: participant-policy probes drive the runtime boundary.
    They record the observed level beside the declared one, as
    `effective_support_level` (`raes_conformance/conformance/participant_policy_probes.py:239`).
    A probe that observes a breach of the declared obligation fails with
    `conformance.participant-policy-overclaim` (`raes_conformance/conformance/participant_policy_probes.py:54`).
    In a release case, an effective level that differs from the declared one
    is such a breach. A declared feature that no authorized probe established
    becomes an `unsupported` case, from
    `_unsupported_case` (`raes_conformance/conformance/participant_policy_probes.py:84`).
    A participant-opacity case keeps an effective level only when its probe
    passed, at
    `effective_support_level` (`raes_conformance/conformance/participant_opacity_probes.py:343`).
  - Realization probes record observed behavior beside the plan:
    `accounted_operations` (`raes_conformance/realization.py:255`) beside the
    expected operations, and
    `actual_observation_strengths` (`raes_conformance/realization.py:257`)
    beside the expected strengths. An envelope that yields no usable probes
    becomes an `unsupported` case, from
    `_constructive_failure` (`raes_conformance/realization.py:141`).
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
    `_gap_diagnostics` (`raes_conformance/conformance/target.py:191`).
- **Processors: gap.** The processor manifest declares support: contract
  versions, SDL versions, features and compatible backends, in
  `create_reference_processor_manifest` (`raes_processor/manifest.py:45`).
  Its vocabulary has no unsupported or partial level. A feature is either in
  `supported_features` (`raes_processor/capabilities.py:20`) or absent. The
  reference processor declares every feature, at
  `supported_features` (`raes_processor/manifest.py:57`). Nothing observes
  processor support.

### C6 applicable validation basis

- **Backends: partial.**
  - Each case records its
    `execution_basis` (`raes_conformance/conformance/report.py:74`):
    `fixture-only`, `hermetic-live` or `native-live`, from
    `ExecutionBasis` (`raes_conformance/_realization_models.py:15`). The
    target runner's basis defaults to `hermetic-live`, at
    `execution_basis` (`raes_conformance/conformance/target.py:148`).
  - The report claim fixes the evidence scope.
    `quantifier_scope` (`raes_conformance/conformance/report.py:374`) is
    `finite-cases`, and
    `evidence_scope` (`raes_conformance/conformance/report.py:375`) is
    `finite`. `evidence_boundary` (`raes_conformance/conformance/report.py:376`)
    counts the named cases. Cases add
    `finite_scope` (`raes_conformance/conformance/report.py:94`), limitations
    and nonclaims.
  - `_validate_claim_strength` (`raes_conformance/conformance/report.py:235`)
    refuses a universal claim backed by finite evidence. It also refuses a
    native claim without a native-live case.
    `_validate_backend_conformance_claim` (`raes_conformance/conformance/report.py:215`)
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
    `ValidationBasisDisclosureModel` (`raes_contracts/contracts/validation_disclosure.py:211`),
    with its
    `achieved_strength` (`raes_contracts/contracts/validation_disclosure.py:222`).
    Its subject kinds include
    `backend_conformance_claim` (`raes_contracts/contracts/validation_disclosure.py:85`),
    and the validation profile catalog lists that kind at
    `backend_conformance_claim` (`contracts/profiles/validation/validation-profile-catalog-v1.json:54`).
    No report field holds a disclosure. Fixture cases also omit each
    contract's validation strength.
    `contract_validation_strength` (`raes_conformance/conformance/validators.py:460`)
    computes it, and `raes semantic` reports it as
    `validation_strength` (`raes_cli/_semantic_portable.py:107`).
- **Processors: gap.** No processor report exists to carry a basis. The
  disclosure's subject kinds include no processor kind, in
  `_SUBJECT_KIND_TO_REF_KIND` (`raes_contracts/contracts/validation_disclosure.py:79`).

### C7 diagnostics sufficient to explain gaps or limitations

- **Backends: partial.**
  - Reports and cases both carry
    `diagnostics` (`raes_conformance/conformance/report.py:130`). The payload
    keeps each diagnostic's code, domain, address, severity and message.
  - Each gap kind that the runner detects has its own code:
    `conformance.unsupported-contract-declaration` (`raes_conformance/conformance/target.py:202`),
    `conformance.unsupported-surface` (`raes_conformance/conformance/target.py:210`),
    `conformance.unsupported-capability-claim` (`raes_conformance/conformance/target.py:218`),
    `conformance.profile-load-failed` (`raes_conformance/conformance/profiles.py:171`),
    `conformance.profile-runtime-surface-unknown` (`raes_conformance/conformance/target.py:165`),
    `conformance.fixture-missing` (`raes_conformance/conformance/fixture_suite.py:53`),
    `conformance.participant-feature-support-invalid` (`raes_conformance/conformance/target.py:253`),
    `conformance.participant-policy-probe-missing` (`raes_conformance/conformance/participant_policy_probes.py:53`),
    `conformance.realization-harness-missing` (`raes_conformance/realization.py:372`)
    and
    `conformance.native-basis-required` (`raes_conformance/realization.py:405`).
  - Limitations travel as text. Cases carry
    `limitations` (`raes_conformance/conformance/report.py:95`) and
    `explicit_non_claims` (`raes_conformance/conformance/report.py:96`). The
    claim that
    `_bounded_conformance_claim` (`raes_conformance/conformance/report.py:356`)
    builds carries its own limitations and nonclaims.
    `_sanitize_load_error` (`raes_conformance/conformance/profiles.py:185`)
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
    `case_diagnostics` (`raes_conformance/conformance/fixture_suite.py:82`).
    The report adds no diagnostic either. Only `valid: false` with
    `passed: false` marks the failure. No test asserts the
    `conformance.unsupported-surface` path (see C5). Whether diagnostics are
    "sufficient" is a judgment. This map checks only that they exist.
- **Processors: gap.** Processor commands report scenario diagnostics. One
  example is the `diagnostics` list that `raes processor plan` prints, built
  in `_execution_plan_payload` (`raes_cli/processor.py:152`). None of them
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
- A status rests on the cited lines and tests. "Covered" means the cited code
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
- A cited code file is missing, or the cited line no longer holds the named
  symbol. The failure lists the lines that hold the symbol now.
- A cited test module or `module::test` function is missing.
- A link opens no page.

When cited code moves, update its line here in the same change.
