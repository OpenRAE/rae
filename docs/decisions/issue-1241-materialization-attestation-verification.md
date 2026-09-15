# Issue #1241 acceptance mapping

This change extends the existing ACTIVE SEM-225 contract. The implementation
uses common SDL content, not a second world-description model.

- [x] Issue: valid SDL, ordinary parsing, formatting, inspection planning and
  comparison → `implementations/python/packages/raes/materialization.py:16`,
  `implementations/python/packages/raes/canonical.py:74`, and shared compiler
  `pipeline.py`; verified by `test_issue_1241_materialized_sdl.py` and
  `test_issue_1241_inspection_plans.py`.
- [x] Issue: distinguish full authored content from in-world additions/changes,
  including wrappers and rewritten files →
  `implementations/python/packages/raes_processor/compiler/materialization_origins.py:22`;
  verified by `test_issue_1241_materialization_origins.py` with native keyed
  collections, ordered commands, qualified imports and field-level pointers.
- [x] Issue: complement rather than replace original realization authority →
  `implementations/python/packages/raes_runtime/backend_materialization.py:28`
  after the incumbent result gate, and
  `implementations/python/packages/raes_processor/planner/materialization_admission.py:36`;
  verified by truthful-but-unauthorized, stale-binding, omitted-inventory,
  cross-domain and complete replica-binding tests.
- [x] Issue: return the attestation and archive the reproducibility record →
  `implementations/python/packages/raes_operations/run_artifacts.py:82`, typed
  `ApplyResult`/`RuntimeSnapshot`, and existing control-plane codecs; verified
  by runtime, immutable-byte, associated-artifact and restart tests.
- [x] SEM-225: define environment-visible, participant-visible and
  comparability-relevant augmentation semantics →
  `specs/sdl/materialization-attestation.md`,
  `implementations/python/packages/raes_contracts/contracts/experiment_disclosure.py:78`,
  and `materialization_attestation.py:55`; verified by
  `test_issue_1241_materialization_artifacts.py` and the incumbent SEM-225 suite.
- [x] Issue: no-additions results, protected values and operational provenance
  remain explicit → negotiated mandatory delivery, closed native redaction,
  value-free failures, restricted immutable files and separate evidence
  requirements, exercised by the issue-focused runtime/SDL/archive suites.

The source remains authenticated full instantiated SDL. The attestation has
its own canonical profile and cannot be executed implicitly. The original run
`scenario_snapshot_ref` is unchanged. Publication precedes durable accepted
references; invalid descriptions or archive failure preserve valid cleanup
inventory without claiming physical rollback or authorizing automatic replay.

The ADR-078 amendment and its pin, phase catalog parity checker, published
schemas, valid/invalid fixtures and per-contract change ledgers are part of the
delivery diff. Schema metadata distinguishes structural validity from the
source/execution/byte context required for full admission.

## Review regression coverage

- F1: `test_issue_1241_schema_omissions.py` exercises all twelve consumers of
  shared value-redaction admission, plus command and filesystem omission rules,
  against authoring, instantiated and materialized schemas and published bytes.
  It covers withheld/empty/plain values, classification aliases, Boolean flag
  aliases, and each present-only filesystem field. A source sweep locks the
  set of shared redaction consumers. The owning models share schema helpers;
  no materialized-only exception is introduced.
- F2: `test_issue_1241_planner_inventory.py` covers planned and backend-selected
  profile bindings and both random-artifact regeneration scopes across all
  three operation phases. Positive and tampered cases bind comparison metadata
  to prepared operations or the trusted predecessor, never the returned report.
  The reference-backend apply test executes real profile preparation and
  archives the accepted result. Original authority checks remain unchanged.
- Publication budget: `test_issue_1241_schema_publication_size.py` requires the
  self-contained schema to fit the existing 500 KB file limit and exactly match
  `schema_bundle()`. Repeated subschemas use local definitions, with one
  definition per line. Expanding those references must recover the complete
  original schema, including every annotation. Nested reference scopes are
  refused; data-valued keywords and existing definition names are preserved.

## Integration verification

The merge retains the published coverage release 15.0.0 and formal release
17.0.0 from `dev`. Fresh execution captures the combined implementation in
coverage release 16.0.0 and formal release 18.0.0, with explicit compiler-digest
deviations and unchanged bounded outcomes. The historical no-replay regression
also covers formal release 17.0.0. Archived shape and computed integrity checks
remain separate, with all twelve retained production records independently pinned.
`test_each_source_bound_release_checks_its_explicit_baseline` checks every admitted
release's baseline mapping and rejects a substituted baseline, including release 18.
