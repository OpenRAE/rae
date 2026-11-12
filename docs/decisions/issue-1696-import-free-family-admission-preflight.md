# Issue 1696: Import-free family admission

Date: 2026-10-29. The contract is issue #1696. It has no requirement UID.
This note states design rules. It is not an implementation plan.

A pure public function admits an import-free `Scenario` as an `ExpandedScenario`.
The caller first parses SDL through the existing parser.
The parser return types and strict experiment input types stay unchanged.
The public function belongs to `raes`, with its existing lazy exports.

[ADR-078](adrs/adr-078-closed-sdl-phase-contracts-and-portable-derivation-evidence.md) defines the closed phases.
[ADR-084](adrs/adr-084-scenario-variation-and-deterministic-trial-realization.md) defines families, selection, and trials.
This change closes the case with zero imports.
It adds no phase or public exchange schema.
No new ADR is needed.
ADR-015 and ADR-036 still govern package dependencies.

## Input and validation

The input is a normalized authoring model without imports.
Other phases and unresolved imports are rejected.
A valid family can have no variation points.
Parameters and choices remain unresolved until selection or instantiation.
Admission grants no permission to execute.
It does not prove backend support.

Raw text still uses `parser.py`, `_yaml_loader.py`, and `_source_validation.py`.
Their owners enforce canonical keys, finite values, and resource limits.
File input still uses bounded UTF-8 loading through `read_sdl_source`.
Typed admission cannot certify the original source spelling or byte limits.
No second YAML loader is needed.

The closed `Scenario` model must check current nested input content.
`_base.py::SDLModel` remains the shared owner for structural rules.
`_identifiers.py` checks local declaration keys.
`_behavior_authoring.py` rejects authored private behavior references.
Only trusted composition can introduce qualified declaration keys.
Direct `ExpandedScenario` construction cannot replace these checks.

The full `SemanticValidator` pipeline must check the output.
Its owners include `_core.py::VALIDATION_PASSES` and `_declarations.py`.
Checks cover references, collisions, graphs, variables, variation, and participants.
They also cover runtime configuration, execution policy, realization, and explicitness.
A validation flag is set only after success.
Advisories are recomputed.
There is no semantic-skip option.

## Runtime and secrets

The existing runtime models remain binding.
These include `runtime_environment.py`, `runtime_generated_value.py`, and `runtime_values.py`.
`_stateful_resource_references.py` still owns output visibility checks.
Nested reconstruction must preserve literal and generated-value exclusivity.
Withheld values remain redacted.
Generated secrets require their existing classification.
Missing outputs and `producer_private` outputs remain invalid for consumers.

Env-file names stay portable identities rather than host paths.
`name_indicates_secret` is only advisory.
It does not replace explicit classifications or ban valid fixture values.
Participant secret references remain owned by `raes_contracts/secret_references.py`.
Admission resolves no secrets and reads no host environment.

## Phase evidence and identity

Phase projection removes only `module`, `imports`, and `realization` after their checks.
`phase_contracts.py::ExpansionProvenance` carries the derived context.
The existing `designation_records` and `constraint_records` helpers preserve realization intent.
Zero imports means empty import lineage, not necessarily empty provenance.
The function must not invent bindings, namespace ancestry, or explicitness records.
Existing validation and instantiation owners derive those facts.

`canonical_sdl_digest` identifies the admitted output for downstream pins.
The canonical profile does not change.
Normalized and expanded digests need not match when their phase fields differ.
Expanded families remain in-process objects.
Existing instantiated snapshots and admitted trial plans remain the persistence formats.
No new store or cache is needed.

## Mutation and host boundaries

An existing Pydantic instance can bypass reconstruction.
A private validation flag can survive nested edits.
The result must be independent of the input.
No validation session or cache can be reused across mutated inputs.
The existing admission functions provide patterns, not permission to copy these limitations.

Field presence affects canonical bytes and listener semantics.
A full dump makes omitted defaults explicit.
An exclude-unset dump can discard edits to omitted default containers.
The conversion must preserve current content or reject these edits explicitly.
It must not silently lose them.
Source diagnostics and declaration locations remain separate from portable provenance.
Returned models are mutable and require admission again after edits.

The composition coordinator reads workspace policy even with zero imports.
Admission must not call it with a dummy path.
It must not invent an import, temporary module, lockfile, or source path.
Module acquisition and trust stay with the existing file-backed composition path.
The pure phase transition is the extension seam.
Future source conveniences must reuse it and the existing parser options.

SDL exceptions and bounded model diagnostics remain the error interface.
Source-aware semantic diagnostics must retain available declaration locations.
Values, documents, raw Pydantic input, and tracebacks must not enter secondary responses or logs.
Portable adapters keep the existing diagnostic envelopes.
No new logger or error hierarchy is needed.

Admission adds no endpoint, subprocess, credential lookup, or ambient configuration discovery.
It cannot turn names into host paths or put credentials in process arguments.
Later execution keeps the existing authentication, role, audit, and redacted-response controls.
Semantic validity never replaces execution authorization.

## Consumer evidence

All four consumers must accept a family built through the public function.
Evidence must include a typed selection descriptor and actual trial compilation.
Request construction alone is not compiler acceptance.
Existing joins, domains, complete selections, and post-selection validation stay binding.
Later gates still check participant configuration, capture, control-context pins, and execution authority.
They also check realization envelopes.

Tests cover invalid shapes and semantics, stale flags, and nested edits.
They also cover forged identifiers, private references, imports, and wrong phases.
Source locations, realization intent, field presence, and canonical identity need protection.
A valid structure-only parse must receive full semantic admission.
An invalid structure-only parse must fail.
Ambient I/O is prohibited.
Existing imported parsing and rejection behavior stay unchanged.

Relevant tests include `test_sdl_parser.py` and `test_sdl_phase_contracts.py`.
They also include `test_sdl_canonicalization.py` and the selected-scenario and trial-compiler tests.
The `test_issue_1665_*` tests cover typed selections.
`test_issue_1074_generated_artifact_env_consumers.py` covers nested runtime boundaries.
Intentional negative private-construction tests remain useful.

## Delivery

Existing workflow, policy, hook, package, and release owners remain authoritative.
These include `.ground-control.yaml`, `.gc/plan-rules.md`, and `tools/policy/adr_policy.yaml`.
They also include `tools/check_repo_policy.py`, `noxfile.py`, and `.pre-commit-config.yaml`.
The Python project and hatch build own package distribution.
`raes/__init__.py` owns public exports.
The public Python guide and API reference describe the function.
This internal note stays outside the curated public docs.

Local checks remain targeted.
Full suites and installed-distribution tests run only in CI/CD.
The existing corpus packaging and release checks protect installed use.
Release Please owns versions and changelogs.
A releasable `feat:` or `fix:` squash title is required.
The [release process](../explain/releasing.md) requires exact-commit checks and tested distributions.
The release criterion requires a published version containing the function.
An unreleased checkout does not satisfy it.

The change adds no new schema, validation profile, or phase type.
It does not change env-packs, other repositories, selection rules, or backends.
It adds no pack discovery, persistence migration, network access, or secret resolution.
It does not redesign mutation handling across existing APIs.

The preflight ran targeted policy, local-link, and whitespace checks.
A local model probe confirmed the mutation and field-presence hazards.
The separate design at `docs/explain/scenario-family-admission.md` records the chosen conversion.
