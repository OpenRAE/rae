# Issue #1330: Published-schema coverage preflight

Date: 2026-09-20

Authority: ASR-501 and issue #1330, including its dependency on #712.
This note is design guidance, not an implementation plan or a
claim that either issue is complete. Existing ADR-007/018 (assurance), ADR-009/019
(authority), ADR-014 (verification), and ADR-061 (publication) suffice; no new ADR
or amendment is needed.

## Readiness and observed gaps

The issue starts only after #712 works and a concrete published contract has a
coverage gap that review cannot reliably catch. This checkout's publication
validator passes, but checks inventory, hashes, stability and evolution, not
governing requirements. The existing requirement-governance checker concerns
change ownership/traceability; it is not evidence of a complete schema-owner
inventory. Inspection did not locate the dedicated #712 check. Its prerequisite
is therefore **unconfirmed**, not satisfied by this preflight. Preserve the
separation: #1330 must not implement or silently absorb #712.

There are 123 publication entries. A conventional directory scan finds 23 without
both `valid/*.json` and `invalid/*.json` cases. This is not a missing-coverage
verdict: `random-stream-vector-v1` uses `contracts/fixtures/random-stream-vectors/`,
SDL examples pass through normalization, and `test_reference_processor.py`
constructs a `workflow-cancellation-request-v1` payload directly. The latter has
no conventional corpus and is a candidate for examination, not proof of absent
tests. Do not encode these counts or a filename heuristic as the rule.

A concrete detection weakness is already visible: `run_fixture_suite()` checks
that a valid directory exists but permits an empty directory and optional invalid
cases; its universe is also limited to the selected backend profile. Fixture
loops in `test_runtime_contracts.py` can execute zero cases. Removing all cases
can therefore evade those individual checks. Before enabling a new gate, identify
the actual affected contract and its claimed coverage; do not infer that all
other repository checks also miss it. A missing conventional directory alone
does not establish the issue's full start condition.

## Coverage boundary and extension seam

- The denominator is every current JSON schema under `contracts/schemas/`,
  reconciled by `validate_schema_publication_manifest()` and read through
  `load_schema_publication_catalog()` in `tools/check_schema_publication.py`.
  Include draft and stable entries; exclude tombstones, generated package
  copies, internal tooling schemas and unpublished models. The catalog loader
  normalizes v1/v2 storage; loading alone is not full publication validation.
- Coverage is a join from an exact schema path/contract version to concrete
  fixture sources and applicable formal subsystem/artifact references. Reuse
  existing corpus routing and execution owners. A directory, README, arbitrary
  test filename, schema hash, requirement owner or substring match is not proof
  that the contract is exercised. Inventory presence is distinct from successful
  execution and neither proves exhaustive semantic correctness.
  Allow many schemas to reference shared evidence and one schema to reference
  multiple evidence sources; each association must identify the behavior and
  validation phase it supports. Internal `$defs` are not separate publication
  entries. Version suffixes alone are insufficient identity for mutable draft
  schemas: evaluate evidence against the current checked-in schema, and do not
  reuse an earlier passing result after the manifest content hash changes.
- Keep the eventual rule explicit about required evidence for each claim.
  Fixture coverage must resolve to nonempty cases exercised by the existing
  runner; rejection coverage, where required, belongs to its actual validation
  layer. Do not impose JSON-Schema rejection on semantic-invalid fixtures:
  `test_runtime_contracts.py` explicitly has schema-valid, semantics-invalid
  experiment-core cases. State which positive/negative cases the rule requires
  and how existing alternate corpora satisfy it in contributor documentation.
- Keep published-schema validation distinct from reference-model acceptance.
  `check_json_artifacts.py` validates checked-in schemas; some conformance and
  domain tests instead consume `schema_bundle()` and depend on the separate
  generated-parity gate. A model-only test cannot establish published-schema
  coverage by itself. `test_example_schema_conformance.py::VALIDATION_CORPUS`
  already supplies an explicit corpus/loader/serialization/schema association
  with non-vacuity and negative controls. Its normalized SDL serialization uses
  `model_dump(mode="json", by_alias=True)`; raw YAML is a different boundary.
  Reuse this precedent for supplemental test evidence without promoting
  `examples/` to normative conformance fixtures: the authority manifest
  explicitly classifies worked examples as non-normative.
- Negative evidence must reject for the claimed reason at the claimed layer.
  `_fixture_case_diagnostics()` can return
  `conformance.semantic-context-required`; `run_fixture_suite()` currently
  treats any diagnostic as a passing invalid case. Missing semantic context is
  unevaluated evidence, not demonstrated rejection of the intended invariant.
  Resolve context through existing domain runners, and distinguish expected
  validation failures from setup, parsing or execution failures.
- Formal obligations come only from `specs/formal/assurance-policy.yaml` and
  `assurance-fulfillment.yaml`, validated by `check_assurance_policy.py`.
  Reference existing subsystem IDs and delivered artifacts; do not duplicate
  FM-level requirements or infer FM3 from a schema's name. FM0 prohibits TLA+
  and Alloy; FM3 requires an abstract state-machine model, not a particular
  prover. Preserve existing dated, tracked, justified waivers as waivers, never
  relabel them as delivered coverage. No formal obligation and an unresolved
  obligation are different states. Fixtures and formal evidence are not a
  blanket interchangeable `fixtures OR model` condition.
- The missing seam is the schema-to-evidence association, not another inventory
  or assurance framework. Prefer minimal declarative references alongside the
  existing per-contract publication records, coordinated with #712's final
  representation. Derive conventional routes; record only necessary alternate
  sources and formal bindings. Validate any new metadata explicitly: current
  entry validation does not automatically validate arbitrary added keys. Keep
  the closed v2 root manifest shape and sharded storage; preserve normalized
  v1/v2 reader compatibility and cover added metadata in publication tests.
  Missing formal association must not silently mean "not applicable": record
  applicability with its policy basis, without creating a second FM ladder.
  Adding another contract
  or corpus route must not require a hard-coded per-contract checker branch;
  adding an assurance artifact kind must continue through the canonical policy.

The delivered rule must report each missing obligation by schema path with a
stable reason, deterministically, and distinguish malformed associations from
missing evidence. Unknown references, duplicates, stale versions, empty matches
and ambiguous corpus roots cannot silently become coverage or exemptions.

## Cross-cutting layers and canonical incumbents

| Layer | Required reuse and guardrail |
| --- | --- |
| Authority and publication shape | `specs/authority/authority-boundary.yaml`, `check_authority_boundary.py`, publication catalog/validator and ADR-061. Metadata is repository governance, not a new public payload schema. Preserve `last_change`, hashes and tombstones; actual schema changes also require `check_generated_schemas.py` parity with `schema_bundle()`. No public schema change is needed merely to inventory coverage. |
| Fixture validation and execution | `check_json_artifacts.py` owns `ValidationTarget`, corpus routing, metaschema and valid-payload checks, including special vector/profile routes. `raes_conformance/conformance/{profiles,fixture_suite,semantics}.py` owns profile selection and semantic fixture execution. Existing domain tests own further model/semantic negatives. Share routing where necessary; do not copy its tables, use backend profile membership as the denominator, or build another JSON Schema/Pydantic validator. `raes_contracts/corpus.py` owns source-versus-packaged corpus resolution; this repository gate inspects canonical checked-in sources. |
| Formal and other coverage | `check_assurance_policy.py` owns fulfillment validation. `check_semantic_coverage.py` owns construct-family realization/test links; `check_specification_coverage.py` owns revisioned research evidence. Neither is schema-level coverage and neither should be repurposed. A pointer into a formal domain is not a proof that its model covers the schema's claimed behavior. |
| PR-controlled paths and parsing | Reuse `tools/policy/common.py::safe_repo_path` and `load_bounded_json_object` for new JSON metadata. Enforce normalized relative paths, supported roots, regular files, size limits, duplicate-key rejection and closed field/type shapes before use. `is_regular_repo_file` in `tooling_artifact_policy_common.py` already rejects symlinks component by component; share that primitive if needed, without invoking the whole tooling policy. `tools/policy/requirement_scope.py` demonstrates their composition with exact-path grammar and bounded closed metadata. Containment alone does not reject all in-repo symlinks or special files. Apply checks to discovered files as well as explicit references, before reading. Reject control characters, secret-file paths and candidate-supplied unrestricted globs; bound aggregate discovery. Existing catalog readers must not be assumed to provide these stronger checks automatically. |
| Auth, secrets and host exposure | The coverage relation is local and read-only: no GitHub/Ground Control request, token, secret file, runtime credential binding, controller, service or database is needed. Do not read environment/credential files from candidate paths or execute/import commands named by metadata. Existing fixed nox runners own subprocesses; keep shell-free argument lists and repository-relative paths, with no credentials in argv or logs. Schema-reference handling must stay local through existing validation owners; new metadata must not introduce network retrieval. |
| Environment and configuration | `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/requirement_context.py` and `tools/nox_support/runner.py` own workflow context. This issue is requirement-backed: set `RAES_REQUIREMENT_UID=ASR-501` when the branch lacks the UID, as on `1330-schema-coverage-gate`; do not use `--skip-requirement` to bypass its governance. Any issue scope must agree with the supplied requirement through the existing scope validator. No new env-binding shape is needed. If reusing JSON validation, preserve `RAES_JSON_SCHEMA_WORKERS`' existing integer/minimum-one validation. Frozen project/tooling dependencies and existing tool selection remain authoritative. |
| Errors and observability | Use `PolicyFailure`, `failures_to_json` and `SessionReporter`; no new exception hierarchy or logging service. Convert anticipated parse, path and I/O failures into stable, bounded diagnostics with schema paths. Do not dump fixture contents, raw exceptions, absolute host paths, environment values or validator payload excerpts. Report missing, malformed, waived and unevaluated states honestly; a failed read or validator crash is not a successful negative fixture. |
| Workflow and persistence | Wire coverage once into ADR-014's `noxfile.py` / `tools/nox_support/policy_lanes.py` graph, consumed by `verify_all.py`, Make, hooks and `.github/workflows/canonical-verification.yml`/`ci.yml`. Keep `SessionReporter` results visible. A full inventory must catch deletion-only changes: `common.changed_paths()` excludes deletions, so a changed-file-only gate is insufficient. No cache, database, generated coverage ledger or second CI graph is required. Repository size/import rules, authority checks and ADR pins remain in force. |

These are design obligations, not a claim that every incumbent helper currently
enforces every boundary. Reuse the appropriate primitive without importing an
unrelated runtime/tooling subsystem's policy or broadening this issue into a
repository-wide security rewrite.

## Acceptance guardrails and non-goals

Follow the temporary-repository tests in `test_repo_policy_tools.py` and
`test_assurance_policy.py`. The issue's positive/negative tests must demonstrate
a covered published schema passing and removal of its required evidence failing
with the exact schema path. Include non-vacuity and prove a structural contract
passes without a formal model. Relevant regression boundaries include alternate
corpus routing, schema-valid semantic negatives, unsafe paths, malformed joins,
stale formal references/waivers and deletion-only changes. Test the gate's
behavior, not merely the presence of strings in this note.

Non-goals: implementing #712, requirement discovery, raising assurance levels,
running a new prover, changing runtime/API/auth/persistence contracts, changing
published payload shapes, or claiming semantic completeness from file counts.
Avoid a universal fixture-layout rule, arbitrary test-file scanning, duplicated
FM tables, unconditional blanket exemptions and self-reported coverage booleans.
Do not bulk-create placeholder fixtures/models to turn the gate green. Concrete
coverage repairs must follow the owning contract's existing validation and
assurance rules. This preflight changes guidance only.
