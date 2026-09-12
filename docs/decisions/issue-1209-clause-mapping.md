# Issue 1209: partial description acceptance evidence

This change implements generic description interchange and conformance in RAE.
The component values in tests are fixture data. Backend selection, probes and
scenario recipes remain downstream, following OpenRAE/hub issue 3.

| Acceptance clause | Implementation and verification |
| --- | --- |
| 1. Typed recursive detail in existing lifecycle envelopes, with coverage and provenance | `contracts/realization_descriptions.py` and `contracts/experiment_evidence.py`; `test_partial_description_round_trips_through_existing_evidence_envelope`, `test_collection_identity_must_match_the_supplied_member` and offline profile carriage test in `test_issue_1209_descriptions.py`. |
| 2. Missing, absent, withheld and contradictory remain distinct; no defaults | Explicit fact states and bounded recursive values; empty-value and nonknown-state tests in `test_issue_1209_descriptions.py`; absence and conflict tests in `test_issue_1209_description_relations.py`. |
| 3. Original intent remains immutable; comparison requires conforming projection | `description_projection.py` invokes canonical realization evaluation only with complete compatible coverage. Partial, wrong-value, complete, mixed-window and original-immutability tests in `test_issue_1209_description_relations.py`. |
| 4. Explicit promotion of selected detail with provenance | `description_promotion.py` returns a new constraint document and existing transformation report after canonical composition/refinement; promotion selection, immutable source, conflicting and absent-ancestor tests in `test_issue_1209_description_relations.py`. |
| 5. Partial, private, offline and conflicting interchange; unsupported relations honest | Exact profile bindings use the existing offline admission context. Opaque carriage requires explicit host policy; comparison/promotion refuse unsupported private semantics. Private offline round-trip, keyed reordering, conflict, duplicate-ingress and finite-budget tests in the description suites. |
| 6. Capture admission and actual evidence remain mandatory | Existing #1112 admission and byte validation owners are reused. `test_typed_evidence_does_not_replace_required_emitted_bytes` in `test_issue_1209_description_lifecycle.py` and `test_issue_1112_capture_admission.py` cover this boundary. |
| 7. Selected backend detail at requested depth | Existing describer receives selector before acquisition. `description_reporting.py` bounds and selects supplied facts; five-component, protection-restores-depth, requested-window and excluded-descendant tests exercise generic callback fixtures. |
| 8. Collection, retention and export remain independent | Existing #1212 lifecycle owns admission/protection/persistence. Typed description retention/recovery and redaction tests in `test_issue_1209_description_lifecycle.py`; required-export and pre-mutation refusal tests in `test_issue_1212_runtime_boundaries.py`. |
| 9. Realization detail and telemetry completeness remain independent | Existing `test_issue_1212_observation_demand.py` tests detailed realization without experimental demand and abstract exhaustive capture; new five-component fixture has backend-selected detail with zero observed evidence. No deployment normalization runs during description admission or projection. |
| 10. Refinement, provenance and conditional augmentation remain governed | Canonical realization relation/composition and `ArtifactTransformationReportModel` retain the ADR-064/066 and #341/#342 authority boundary. Existing run augmentation validation is unchanged. Promotion records original/source/target digests and explicit actor, decision and time. |

Production paths above are relative to
`implementations/python/packages/raes_contracts/`; test paths are relative to
`implementations/python/tests/`. Runtime carriage uses the existing
`raes_runtime/observation_execution.py` and `observation_results.py` owners.
The published evidence/run schemas and their publication entries accompany
reference model changes; valid partial and invalid withheld-value fixtures
exercise the existing experiment evidence contract.

SEM-218 stays ACTIVE. Its existing exact-authority implementation remains in
place; this diff adds descriptive evidence and explicit promotion without
turning coverage, backend choice or schema validity into author authority.

Verification also replays fresh specification-coverage 8.0.0 and formal
semantic-validation 10.0.0 captures. These bind the new implementation digest
while retaining every previous capture and the preregistered outcome and
missing-concept denominators. The supported-release checks advance with the
new immutable records; they still reject unsupported future revisions.

## First review remediation

All six findings in the [review record](https://github.com/OpenRAE/rae/issues/1209#issuecomment-5648017546)
are addressed in the local delivery diff. Coverage consumers were swept across
report projection, exhaustive demand and authored assessment; profile owners
were swept across both lifecycle carriers and every nested binding.

| Finding | Regression evidence |
| --- | --- |
| Numeric type erased in conflict markers | `test_literal_conflicts_preserve_integer_versus_float_type` in `test_issue_1209_description_review.py` |
| Coverage not bound to the boundary it satisfies | `test_required_exhaustive_description_rejects_unmatched_coverage`, `test_conformance_requires_root_effective_coverage_universe` and `test_conformance_rejects_coverage_of_wrong_kind`, `test_narrow_report_does_not_retain_a_broader_complete_claim`, `test_selector_exclusions_remove_complete_coverage_claims`, and `test_coverage_cannot_claim_stronger_basis_than_the_report` in the same file |
| Mixed windows hide a known author violation | `test_mixed_windows_do_not_hide_a_known_author_violation` in the same file |
| Profile owner escapes the selected fact or lifecycle carrier | `test_profile_owners_are_bound_to_fact_and_lifecycle_carrier` in `test_issue_1209_description_profiles.py`, including both carriers and nested owners |
| Protection changes carrier to escape projection | `test_protector_cannot_escape_typed_projection_by_changing_carrier` in `test_issue_1209_description_review.py` |
| Nested profile basis or evidence is forged | `test_backend_selected_fact_cannot_forge_observed_profile_basis` and `test_profile_evidence_must_join_the_externally_verified_reference` in `test_issue_1209_description_profiles.py` |

## Second review remediation

Both findings in the [second review record](https://github.com/OpenRAE/rae/issues/1209#issuecomment-5648736094)
are addressed. Evidence verification resolves provenance per retained fact and
coverage claim, then uses the existing complete experiment-reference key to
compare against the reporting API's unqualified evidence-record identity. The
class sweep includes inherited and overridden provenance, nested profile IDs,
both projection passes around protection, and the existing runtime disclosure
writer, which already interprets the outer identifier as an evidence-record ID.

`test_projection_checks_effective_evidence_provenance` and
`test_inherited_provenance_still_requires_verified_reference` in
`test_issue_1209_description_evidence.py` pin override semantics.
`test_reporting_rejects_unverified_reference_qualifiers` in the same file
rejects forged kind, version, digest, path and differently qualified duplicate
IDs at each reporting boundary, including nested profiles and protection.
The new cases reproduced both defects before the fix and pass after it.

## Test-quality review remediation

The [test-quality findings](https://github.com/OpenRAE/rae/issues/1209#issuecomment-5648929880)
are addressed with test changes. Existing production validators and recorded
research outcomes remain unchanged.

| Finding | Regression evidence or test repair |
| --- | --- |
| 1. Nested profile forgery was masked by a fact-level forgery | `test_nested_profile_reference_cannot_escape_verified_fact` exercises admission and protection; `test_nested_profile_evidence_is_checked_independently_by_report_join` isolates the nested evidence join. |
| 2. Coverage arithmetic reused its own generated result as oracle | `test_analysis_arithmetic_has_an_independent_mixed_classification_oracle` and `test_noncritical_evidence_status_is_derived_independently` use hand-authored counts and outcomes. |
| 3. Evidence-validator rules lacked negative cases | The specification-coverage integrity table and formal-semantic-validation review suite exercise the previously unasserted rules. Exception tests cover both retained replay versions and both production replay modes. |
| 4. Coverage tests depended exclusively on committed research data | `test_specification_coverage_units.py` supplies independent arithmetic, source, request and execution-error fixtures. |
| 5. Shared rule IDs hid which check failed | Production-tamper assertions name the exact message and snapshot path; dedicated tests cover missing command selection, extra selected artifacts, and the retest commit pin. |
| 6. Production tampering covered only satisfiability | All four tamper tests now cover satisfiability and exploit-path evidence. |
| 7. Participant-trust test invoked unrelated release replay | The test directly exercises `_participant_replay_failures` with a minimal release and controlled runner. |
| 8. Promotion assertions matched unrelated guard messages | Each promotion rejection now names its intended complete guard message. |
| 9. Repeated evidence loads lacked explicit isolation | Cached committed loads return deep copies; `test_cached_evidence_is_loaded_once_and_copied_per_test` pins isolation. Loader-specific tests retain real loader calls. |
| 10. Retention checks depended on `repr` formatting | Retention and redaction inspect stored scalar values structurally. |
| 11. Coverage kind and universe cases had asymmetric assertions | Separate named tests cover wrong kind and effective universe. |
| 12. Ownership assertions only counted failures | The test asserts each forbidden path and its ownership rule ID. |
