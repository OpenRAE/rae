# Processor port verification

This file records the implementation checks for issue 1787.
The compiler, planner, realization owner and comparison owner are implemented.
Local checks select named cases or the repository feedback lane.
Full test, integration, race, coverage, mutation and fuzz suites run in CI.
CI and the pre-push publication decision remain delivery gates.

## Design and ownership

The [design](issue-1787-processor-design.md) defines the owners, flows and threats.
Its design checks passed before the corresponding source changes.
The issue holds the design records and plan.
The final architecture check reports no findings.
Declared public APIs match the implemented APIs and their allowed imports.

`processor.CompiledScenario` is the shared typed model.
Compiler stages retain typed facts in one request-local state.
They read the admitted source model at the input boundary.
`ResourcePayload` retains operation bytes for output projection.
Compiler stages do not exchange or decode those bytes as their model.
Public views copy their owned values.

`processor/realization` owns realization compilation, selection and evaluation.
It also owns portable plan recovery and cleanup diagnostics.
Shared recursive relations remain in contract admission.
Planning uses those owners to build and reconcile execution plans.
It does not own a second realization evaluator.
No execution, ledger, store or publication service is added.

The Python package implementation and published schemas are unchanged.
The existing metadata tool records native model names and SDL ownership.
This is compatibility metadata for the Go owner.
It does not change Python behavior.

## Targeted results

| Surface | Result |
| --- | --- |
| CLI corpus | All 272 selected cases pass: 2 manifests, 93 semantic compilations, 85 plans and 92 reconciliations. |
| Compiled fields | 68 independent reference vectors check runtime, participant and software fields. |
| Participant relations | 204 reference vectors check arguments, action results, outcomes, temporal state, history and joint actions. |
| Semantic comparison | 77 analyses and 8 coordinate records pass. Named tests also check impact scopes, pins, limits, copied values and invalid input. |
| Native SDL comparison | 18 independent projections pass for both revisions, defaults, presence, imports, private JSON and workflow aliases. |
| Portable realization | 62 independent reference cases pass for authority, requirements, evaluation and cleanup. |
| Native realization | 104 constructor cases and named relation tests check source identity, private data, presence, scalar kinds and limits. |
| Prepared plans | Named tests check selected resource context, native references, frozen credentials, readback order and protected values. |
| Recursive relations | 43 cases check exact metadata, depth, node, member, scalar and byte limits. |
| Go source checks | Strict lint reports zero findings across all changed Go owners. |
| Architecture | Both design and actual source checks pass. |
| Repository feedback | `verify-fast-feedback` passes, including the changed metadata tool checks. |
| Native metadata | `tools/parity_authoring_layout.py --check` passes. |

The CLI cases compare each recorded machine-readable result.
Semantic compilation cases include summaries and refusals.
They do not compare every field of every possible compiled model.
The independent SDK vectors check the additional fields and relations named above.
They do not claim exhaustive input enumeration.

The selected corpus command is:

```sh
go -C implementations/go test ./internal/parity \
  -run '^TestCorpus/(cli_processor_(manifest|plan|reconcile)|cli_semantic_compile)$' \
  -count=1
```

The final strict lint run selected these packages:

```text
./processor/... ./contract/admission ./contract/profile ./contract/validation
./sdl/... ./internal/sdl/authoring ./internal/contract/sdlrules
./internal/base/pyrepr ./internal/parity
```

The repository feedback command is:

```sh
env -u A""CES_REQUIREMENT_UID -u RAES_REQUIREMENT_UID \
  uv run --project implementations/tooling/python --frozen --no-default-groups \
  nox -f noxfile.py -s verify-fast-feedback -- --base-rev origin/go-cutover
```

This issue has no requirement UID.
The command removes inherited requirement values for that process only.
The feedback lane did not select a full test suite.

## Source-case evidence

The durable maps name source tests, native tests and fixture hashes:

- [Participant map](../../implementations/go/processor/testdata/participant-api-case-map.json): 144 source-test entries.
- [Comparison map](../../implementations/go/processor/comparison/testdata/source-case-map.json): 21 source-test functions and their reference fixtures.
- [Planning map](../../implementations/go/processor/planning/testdata/reference-case-map.json): 31 source modules and 56 named cases.
- [Realization map](../../implementations/go/processor/realization/testdata/reference-case-map.json): 186 source rows, including capture and portable plan consumers.

Each map states its scope and mixed-owner exclusions.
Runtime execution assertions do not prove a pure compiler relation.
The maps identify the pure assertions separately.
Trial work belongs to issue 1788.
Satisfiability, exploit paths and participant opacity belong to issue 1789.
Decision and exposure authority belong to issue 1794.
These boundaries follow the issue's stated scope.
The scoped audit records no known pure implementation or test gaps.
Recorded source hashes and named Go test references were checked.

A broader import inventory was used to find candidate source tests.
An import alone does not establish a behavior mapping.
The durable maps replace that inventory as the scoped evidence.

## Security, limits and recovery

Named tests cover native handle identity before supplied methods can run.
They check copied inputs and outputs, cancellation and phase ownership.
Byte, scalar, depth, node and member limits apply before output encoding.
Comparison also bounds the complete output before publishing repeated projections.

Realization tests preserve closed omissions, local open scopes and exact bindings.
They check source artifact trust and address-local identity.
Capture tests retain all base demands when explicit relations are supplied.
Materialized descriptions cannot invent authored relation authority.
Portable cleanup validates original plan authority before relaxing local omissions.
Cleanup does not report successful provenance.

Prepared plan tests use the actual selected resource specifications.
Frozen source definitions cannot replace those inputs.
Snapshot checks retain ordinary string limits for arbitrary payload keys.
Only existing source document owners have the larger document limit.
Sanitization visits every registered runtime concern at selected node addresses.
It preserves safe sequence order and removes protected values.
Unknown private payload fields keep the reference projection behavior.
They still fail closed when delivery needs a known concern.

## Observed defects and test history

Observed failures led to fixes for authored order and source directory facts.
Other failures exposed absent-output defaults and scope binding order.
Further regressions found coupled capability rows and mixed capture offers.
Independent native cases found workflow model-name and serialization-alias faults.
They also found an aggregate comparison output limit that was checked too late.

Capture regressions found a missing-primary path that dropped base obligations.
Materialized capture also needed an explicit authored relation owner.
Prepared readback tests found lost sequence order and unchecked concern values.
Portable reference cases found canonical bound order and diagnostic priority faults.
Each observed failure passed after its repair.

The new native entry points first failed because their APIs did not exist.
Other reference vectors were added after implementation as characterization checks.
Guard-removal overlays and three targeted mutants were checked after code existed.
Those checks establish defect detection, not an original red-first history.
This record does not claim that every change followed red-first development.

## Issue acceptance mapping

The source label for every item below is `issue`.
There are no in-scope requirement UIDs.
Each item maps the issue contract to an implementation or enforced gate.
A mapped CI gate is not a claim that its hosted run has passed.

- [x] Typed compiled model and no untyped stage model: `implementations/go/processor/model.go:163` and `implementations/go/processor/compile.go:118`.
- [x] One realization owner: `implementations/go/processor/realization/compile.go:21` and `implementations/go/processor/planning/plan.go:119`.
- [x] Compilation, plans, manifests and reconciliation match their corpus cases: `implementations/go/internal/parity/corpus_test.go:15` and the selected 272-case run above.
- [x] Published plans are checked against their contracts: `implementations/go/processor/planning/projection.go:153`.
- [x] Processor manifest contents retain the published contract: `implementations/go/processor/manifest.go:16`.
- [x] Diagnostic order is retained: `implementations/go/processor/planning/projection.go:44`, `implementations/go/processor/planning/plan.go:151` and the exact reference cases.
- [x] Input limits, security, error and recovery behavior have native tests: the four source-case maps above, starting at line 1 of each map.
- [x] Scoped issue defect cases have native tests: the four source-case maps above, starting at line 1 of each map.
- [x] Duplicate Python transport models do not carry into Go: `implementations/go/processor/model.go:14`, `implementations/go/processor/planning/plan.go:13` and generated contract bindings.
- [x] Mutable stage dictionaries are replaced by typed state. Its diagnostic slice stays in the compiler owner: `implementations/go/processor/compile.go:30` and `implementations/go/processor/model.go:163`.
- [x] Idiomatic Go, simple native owners and standard library use: `implementations/architecture.json:1` and the zero-finding strict lint and architecture checks.
- [x] Design was recorded and checked before implementation: `docs/decisions/issue-1787-processor-design.md:1` and the timestamped issue design records.
- [x] Contracts guide construction and refusal: `implementations/go/processor/planning/admission.go:16` and `implementations/go/processor/planning/projection.go:153`.
- [x] SDL, Python behavior and published schemas are preserved: the corpus checks and the changed-path audit described above.
- [x] Runtime consumers use public processor and contract packages: `docs/decisions/issue-1825-public-go-api.md:1` and `implementations/go/processor/realization/planned.go:72`.
- [x] Full suites remain hosted gates: `.github/workflows/ci.yml:39` and `.github/workflows/canonical-verification.yml:590`.
- [x] Standards, architecture, coverage, mutation policy and regression gates are required: `.github/workflows/canonical-verification.yml:590`; their pass state is checked at PR readiness.

## Review input repair

The first required review returned no verdict.
Its engine failed after completing 70 of 104 slices.
The service reported six oversized slices.
No review cycle was consumed.
The failure is recorded on issue 1787.

Six fixture files each had a line larger than 256 KiB.
Those lines ranged from 275 KB to 3.6 MB.
This matched the number of oversized slices.
The closed failure report does not identify the failed engine requests.
It does not prove that line size was the only cause.

Twelve long fixture files now use bounded record lines.
The format keeps the original key order, number spelling and string escapes.
The standard Go JSON compactor produced identical bytes before and after each change.
The largest resulting line is 129,908 bytes.
Fixture hash pins are refreshed after this format change.
No Go source or expected result changes are part of this repair.
All 325 participant, tool and comparison reference cases pass after the format change.
The augmentation preparation reference test also passes.
All recorded source and fixture hashes match.
The retry completed all 139 slices with no oversized input.
It produced the seven findings recorded below.

## Review repairs

The complete review covered all 449 changed files.
Its verdict was `ship-with-fixes`.
The [finding record](https://github.com/OpenRAE/rae/issues/1787#issuecomment-6841539941) names all seven issues.
Each repair has an observed failing test and a passing regression.

| Finding | Repair and regression |
| --- | --- |
| `core-F1` | Constraint normalization keeps exact JSON numbers. `TestConstraintNormalizationPreservesLargeExactIntegers` checks a root and a record containing an integer above float64 range, including a distinct neighbor. |
| `core-F2` | Policy origins use the compiled inject-binding identity. `TestCompileBindingExecutionPoliciesUseConstructedResourceIdentities` and `TestPlanInjectBindingKeepsDefaultAndApplicationPoliciesAndEnforcesSupport` check default and explicit policies and target support. |
| `core-F3` | Capability checks use exact integral arithmetic for decimal and exponent spellings. Seven new capacity tests cover all four reviewed sites, resource-pool messages, exact thresholds and input bounds. Four targeted mutants were detected. |
| `core-F4` | Portable OS bounds use the same dedicated observation as the registered evaluator. `TestPortableOSBoundsCheckTheDedicatedObservedValue` rejects conflicting or missing evidence without OS provenance. |
| `core-F5` | Designation queries use the retained native expansion before instantiation. `TestImportedRealizationDesignationsMatchInstantiatedQueries` checks imported scopes, defaults, nested namespaces and copied results. |
| `security-F1` | OS evidence must match the current operation and selected apparatus. `TestOSEvidenceMatchesTheCurrentOperationAndApparatus` checks both native and portable evaluation. Posture checks retain their independent role. |
| `security-F2` | Supplied trust governs every workspace import after integrity checks. Four `TestSourceContext` regressions cover nested callbacks, registry policy and verified facts. `TestCompositionUsesVerifiedRegistrySources` retains the verified bundle boundary with unsigned workspace sources disabled. |

The capability repair passed 16 named tests with 97 cases.
These include 50 new cases.
The OS repair passed 48 guard and success cases.
The closest reference groups contain 469 relation, 62 portable and 15 evaluation cases.
The final CLI run still passed all 272 recorded cases after the repairs.
Combined strict lint reports zero issues after the review repairs.
The final actual API and dependency check also reports zero findings.
Targeted prose checks pass for all six changed documents.

Seven isolated Python helper records omit the source observation-binding context.
Five occur in the relation group and two in the portable group.
Their original fixture bytes and expected helper outputs are unchanged.
The Go tests classify these inputs from their OS evidence and plan facts.
They require refusal and no OS provenance at the public SDK boundary.
They do not select expectations by fixture name.

The [source binding owner](../../implementations/python/packages/raes_contracts/realization_observation_binding.py) requires the current operation and selected apparatus.
A helper's `binding_verified` value does not establish that separate relationship.
New positive cases supply the complete binding context.
Bounds-only OS checks also use the dedicated observation owner.
They do not reuse the isolated helper's inventory fallback.
The realization evidence map records this source-owner distinction.

The trust repair retains the existing verified bundle rule.
Bundled child sources remain confined to the admitted immutable source map.
Workspace source admission still applies pins, locks, exports and caller policy.
The internal trust and metadata API additions passed the design check before implementation.
Actual source API and dependency checks also pass.

## Publication decision and consistency

The user chose to continue after all seven review findings were fixed and verified.
The additional review had not returned a verdict at that decision.
It is not included in the completed review evidence.

One post-review consistency check compared the implementation, accepted design and related documents.
It found stale planned-state labels and an obsolete public-package statement in the architecture explanation.
The explanation and its diagrams now identify the implemented SDL and processor owners.
Trial compilation and runtime remain planned.
The API reference also identifies the implemented facade and comparison owner.
These are documentation corrections; they change no API or execution behavior.

The publication hook also enforced the 500 KiB new-file limit.
Six reference fixtures exceeded it.
Each now has JSON parts below that limit.
All original record tokens, order, metadata and expected values are unchanged.
The test loaders combine the parts and retain their complete inventory checks.
They retain 48 comparison artifacts, 8 coordinates, 77 analyses and 15 augmentation records.
They also retain 39 participant compilations, 120 history and joint cases, and 531 realization relation cases.
The old loaders failed those checks after the split.
The updated loaders pass all affected reference tests.
The source-case maps record the split parts and current hashes.

Hosted checks also required a documentation dependency lock update and a shell-command spelling correction.
The lock selects Soup Sieve 4.0 without other package changes.
A small Sphinx/Furo HTML build passes with that selection.
The product lock scan and identity check pass after these repairs.

## Requirement traceability

Requirement transition is a no-op because the issue names no requirement UID.
The touched-file scan found existing architecture links under `MOD-001`.
Those links still name the architecture model and its generated view.
The existing tooling still enforces that requirement.
No linked implementation was deleted or moved.
No issue 1787 requirement link needed repair.

## Documentation review

The changed documents use the repository documentation style guide.
The review uses the pinned `OpenRAE/doc-tools` skill at commit `9c5c00a892285a0e95bbaccb404b4ae8ca96e865`.
Claims were compared with the current source and recorded results.
Code fences, API names, hashes and normative meaning were preserved.
Vale checks prose style on explicit changed paths.
It does not establish factual accuracy or complete STE conformance.
The official STE source could not be accessed; no dictionary-conformance claim is made.
