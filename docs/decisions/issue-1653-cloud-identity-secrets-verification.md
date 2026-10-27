# Issue 1653 verification

The issue has no formal requirement UID.
These checks cover its five acceptance criteria.
Package paths below start at `implementations/python/packages/`.
Test paths start at `implementations/python/tests/`.

- [x] Issue 1: Extend existing owners with the smallest connected description.
  `raes/runtime_identity_resources.py:35` and `raes/runtime_secret_service.py:129`
  join cloud scopes, identity use and application-owned secrets.
  `examples/scenarios/cloud-secret-cross-project.sdl.yaml` shows the complete use case.
- [x] Issue 2: Preserve ownership, provider identity and exact references.
  `raes/validator/_cloud_resources.py:48` checks kinds, providers, ancestry and cycles.
  `test_issue_1653_cloud_references.py:148` keeps repeated native names distinct.
- [x] Issue 3: Keep identity use, policy, secret state and access reports separate.
  `raes/runtime_identity_resources.py:48` defines identity use, bindings and observations.
  `raes/runtime_secret_service.py:21` defines versions and consumer selection.
  `test_issue_1653_cloud_models.py:35` checks inert conditions and no inferred access.
  The reference tests check inherited policy sources and version ownership.
- [x] Issue 4: Preserve meaning across the language and runtime boundaries.
  `raes/composition/_cloud.py:6` rewrites only declared reference fields.
  `test_issue_1653_cloud_lifecycle.py` covers repeated imports, substitution,
  compile/plan encoding, materialized documents and disk-store reload.
  It verifies that unsupported execution stops before the provisioner runs.
- [x] Issue 5: Keep optional detail open and protect value boundaries.
  `test_issue_1653_cloud_references.py:140` accepts partial ownership.
  `raes_processor/semantics/realization_runtime_concern_profiles.py` excludes access
  reports and selector-resolution reports from configuration requirements.
  Version models reject raw payload fields and destroyed versions with live payloads.
  The public parser error test checks that rejected secret material is not echoed.

Location, replicas, encryption, service limits and lifecycle owners are optional typed fields.
The design preserves existing content, disclosure, credential and evidence owners.
It adds no native cloud executor or IAM evaluator.

## Targeted checks

- The three issue test modules plus application-authorization and family-invariant
  modules passed: 91 tests before the added disk-store test.
- The disk-store test and two existing runtime result-rejection tests passed: 3 tests.
- Existing identity and platform tests in `test_sdl_models.py`, `test_sdl_validator.py`
  and `test_runtime_models.py` passed: 13 selected tests.
- Generated-schema parity, schema-publication checks, SDL catalog parity and the
  example-library check passed.
- The new language reference and design note passed repository Vale rules.
  Older reference files and the generated preflight retain existing style findings.
  The trusted pre-push check independently tests the final changed documents.

Traceability was checked against changed paths.
No files were removed or renamed, and no requirement status changed.
Existing links remain valid.
New links record the example, application-owned secret model and realization tests.
Full test and integration suites remain CI responsibilities.

## Review repairs

The full review covered 41 files in six slices.
Four finding records identified three defects.
All three were reproduced before repair.

- `core-F1` and `core-F2`: Shared policy schema rules now match model checks.
  `test_published_policy_schemas_reject_invalid_field_combinations` checks both rules
  in all five affected published schemas.
- `core-F3`: Bounded node checks now rebuild content declarations from admitted placements.
  `test_live_payload_content_reference_retains_bounded_validation_context` checks preparation,
  inventory acceptance and refusal when the content is absent.
- `core-F4`: Version ancestry now follows the owning secret to its project.
  `test_version_inherits_project_policy_through_its_owning_secret` checks that link.
  Existing tests still reject inheritance between sibling secrets.

These tests are in the issue's model, reference and lifecycle modules.
The repair tests and existing prepared-node admission tests passed: 79 tests.
Generated-schema parity and schema-publication checks were repeated after the repair.

## Source-bound research evidence

Fresh branch captures bind the existing research protocols to the combined source.
The specification artifacts and their typed pointers were replayed.
The formal cases, four production analyses and 14 participant test cases were replayed.
The formal capture retains its partial status and existing limits.
No published history or baseline pin was changed.
These captures make no claim of live cloud support.
