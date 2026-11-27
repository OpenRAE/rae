# Conformance and support reporting preflight

Issue #222 serves ASR-526.
This note sets the design rules.
It claims no delivered coverage.
The inspected checkout was `a601b696ce6d5d5a84f74305ee77d1983fca8ce8`.

Extend the existing report family.
Both views must read the same checked result.
The report must show what ran, what failed, and what did not run.
A declared feature is not proof that the feature works.
A passing demo cannot replace a failed report.

## Clause coverage and gaps

Package paths start at `implementations/python/packages/`.

| ASR-526 clause | Existing owner | Gap |
| --- | --- | --- |
| Processors and backends | `raes_conformance/conformance/report.py` and `target.py` | Add processor checks through the actual processor. Register `ProcessorManifestV2Model` in the existing validator map. |
| Achieved profile or level | Requested `profile`, `passed`, claim bindings, and `native_conformance` | Show the requested scope apart from the achieved scope. Do not rank profile names. |
| Passed and failed checks | Case verdicts and report diagnostics | Show required checks that did not run. Reject empty or duplicate coverage. |
| Declared and observed gaps | Contract gaps, feature rows, and specialist bindings | Keep declarations, admitted support, and measured facts apart. A missing fact stays unknown. |
| Validation basis | Execution basis, finite scope, governed claims, and evidence refs | Bind the basis to the exact subject. Do not call a processor a backend. |
| Machine and human reports | The existing JSON projection and Typer command | Add text from that checked result. Keep failures, gaps, limits, and safe diagnostic codes. |

## Owners and public boundaries

`raes_conformance.conformance` owns checks, report validation, and projection.
Keep `BackendConformanceReport`, `ConformanceCaseResult`, and their existing imports.
The CLI selects a view and process status.
It must not compute a second verdict.
Existing backend field meanings, JSON defaults, and exit behavior must remain stable.
New metadata must have honest defaults.
Old evidence must not acquire fresh producer pins.
An incompatible saved shape needs a version and migration boundary.

The processor path must call the supplied installed code.
For the reference processor, use `ReferenceProcessor.realize()` or `run_reference_processor()`.
That path parses, instantiates, compiles, and plans.
Keep its stage diagnostics.
A valid `ReferenceProcessorResult` alone is not full processor qualification.
Backend execution belongs to the runtime.
Add no runtime import to `raes_processor`.
Add no arbitrary module loader or plugin framework.

Validate the actual processor manifest through `ProcessorManifestV2Model`.
Do not substitute the reference manifest for another processor.
Reuse backend manifest adapters, `manifest_authority`, controlled vocabularies, and concept-binding checks.
Keep the selected planning backend and its safe configuration pins.
An experiment context must pass `validate_experiment_apparatus_context_against_manifests()` when that context is present.

Keep these subjects and axes distinct:

- Backend capability profile and selected probe suite.
- SDL semantic profile and instantiation profile.
- Validation strength and execution substrate.
- Realization support, realization owner, and evidence origin.
- Feature support, tool support, and behavioral assurance.

`modular-control-runtime/v2` names a suite, not a backend capability profile.
A participant implementation is not an SDL processor.
Use participant support models only for the domains they govern.
Do not turn all processor features into participant features.
Bounded and weak support must retain their constraints, disclosures, and limit refs.

Reuse `select_validation_profile()` for validation-profile claims.
The catalog join, required gates, strength floor, evidence, and audience limits remain binding.
The disclosure contract has no processor subject kind.
A processor extension needs coordinated contract and catalog governance.
A `published_claim` disclosure must identify the report it checks.
Neither path permits invented strength or unrun gates marked passed.
A result below the structural floor must remain reportable without a fabricated strength.

## Report integrity

`validate_backend_conformance_report()` is the one consistency boundary.
Renderers must use it through the existing projection.
Runner conventions alone cannot protect a hand-built report.

Achievement needs complete evidence for the exact subject, scope, selected obligations, and safe configuration.
Keep the request on failure.
A smaller passing selection does not qualify a larger profile.
Unknown runtime surfaces remain unqualified even when fixtures pass.
Do not infer a fallback profile from enum order or pass rate.

Missing fixtures, empty valid directories, absent context, and absent harnesses must remain visible.
So must omitted obligations, duplicate case identities, and interrupted runs.
A partial result must name its missing coverage.
A run that cannot produce a report keeps its operational error boundary.
Neither path grants a clean qualification.

Count check verdicts, not error severities.
An intended invalid fixture can pass through its expected rejection.
Its error diagnostics must remain in the report.
A negative probe needs the intended refusal at its owning boundary.
An unrelated error or failed dependency does not satisfy it.
Top-level errors and required gaps still block achievement.

Check outcomes and capability strengths have different meanings.
The governed gate outcomes already include partial, unknown, unrun, withheld, and inapplicable checks.
Do not add a competing status taxonomy.
A valid unsupported declaration can pass its declaration check.
It still proves no behavioral support.

Do not derive observed support from manifest validity, method presence, evidence-ref text, or an execution-basis option.
A successful plan proves no native backend effect.
An admission-derived `effective_support_level` is not a measured fact.
A false claim must retain both the declaration and the contrary result.
Observed failure and failed cleanup take precedence over unsupported status.

Keep failed and unsupported cases, residual state, limits, nonclaims, and every cited case.
Native qualification needs all applicable native obligations and bound observations.
One unrelated native case is insufficient.
Fixture and hermetic runs prove neither native nor universal assurance.
Keep catalog validation and the declaration, realization, and conformance prerequisites.

## Delivered specialist evidence

Reuse the existing producers.
Do not copy or rerun their logic inside a reporter.

| Producer | Pins and limits to preserve |
| --- | --- |
| #1071: `run_modular_control_conformance()` | Suite `modular-control-runtime/v2`; selected obligations; claimed and excluded effects; artifact pins; support; call counts; owner readback; replay and refusal evidence. Runtime cases are hermetic. Authored recovery is fixture-only. Native conformance stays false. General native resume remains unsupported. |
| #1017: `run_mixed_backend_conformance()` | Family `mixed-backend-execution`; catalog `mixed-backend-probes/rev1`; component and backend versions; manifest, envelope, configuration, and stage digests; service pins; producers; time mapping; loss; evidence refs. Installed-service execution is hermetic. It grants no native qualification. |

Keep both unsupported combinations:

- `combination-reusable-control-with-mixed-runtime`.
- `combination-distributed-portable-mixed`.

Separate supported paths do not prove joint support.
The [mixed-control demo](../explain/reference/mixed-control-demonstration.md) can succeed with a failed mixed report.
Its expectations must not replace conformance verdicts.
Use the current contracts and refusal categories.
The [modular reference](../explain/reference/modular-control-conformance.md) and [control reference](../explain/reference/revised-control-semantics.md) define the adjacent boundaries.

Keep exact subject and tool versions, contract ids, profile revisions, fixture identity, and probe-set pins.
Keep safe environment pins and all evidence and producer refs.
A schema title alone does not pin contract content.
Reuse `raes_contracts.canonical`, shared digest helpers, and existing evidence carriers.
Add no second hashing format or evidence store.
A digest binds content; it proves no producer identity or independent observation.
Never hash secret values into public configuration pins.
Synthetic, recorded, and observed evidence must remain distinct, as issue #1344 requires.
Missing provenance stays missing.

## Cross-cutting checks

| Boundary and existing owner | Binding rule |
| --- | --- |
| Corpus: `corpus`, `backend_profiles`, and `profiles.py` | Keep packaged roots and explicit overrides. Keep profile-id grammar, filename identity, and root confinement, including symlinks. Bound new inputs before decoding. Reject bad UTF-8, JSON roots, and decoder limits. Refs remain inert data. |
| Contracts: `ContractModel`, `schema_bundle()`, and the existing registry | Reuse schema-first and contextual checks. Unknown contracts fail closed. `contract_validation_strength()` and missing-context diagnostics bound claims. Keep SDL parser limits, import policy, instantiation, and revalidation. Weaken no validator for a fixture. |
| Manifests and support | Keep vocabulary, concept bindings, compatibility, capacity, constraints, and disclosures at their existing owners. Accepted declarations prove no behavior. |
| Runtime: `RuntimeTarget`, `ControlPlaneOptions`, and installed-service checks | Use specialist runners for live evidence. Keep component presence, signatures, pins, and supervision checks. Revalidate rebuilt installations. Keep final-sink policy, idempotency, exact-cut admission, and retained results. |
| Auth: `RuntimeControlPlane`, identity, and security config | Reports grant no call rights. Live probes need an authorized installed target and identity. Keep roles and subject bindings. Existing HTTP paths retain auth, sealed settings, size guards, audit, redacted errors, and response models. Add no service. |
| Secrets: runtime environment and configuration types | Add no credential discovery. Keep name uniqueness, literal versus `value_from`, provenance, secret refs, and value-free account projections. Keep operator secrets, plans, and environment maps out of reports. |
| Host and filesystem | Put no tokens or raw evidence in argv. Run no command, import, download, or connection from report data. Keep temporary-store permissions and cleanup. Durable output needs an explicit caller destination. Never upload reports or follow refs. |
| Errors: shared diagnostics and ADR-116 | Keep safe codes, stage/check addresses, and bounded repair context. Reuse `sanitized_failure_message()`. Keep raw exceptions, rejected values, host paths, source snippets, and provider objects private. Escape terminal controls. Governed transports retain portable diagnostic bounds and JSON-Pointer conversion. |
| Logs | Reuse shared logging and `foreign_failure_record()`. Log unexpected failures once, value-free, on stderr. Keep JSON stdout parseable. Expected findings remain diagnostics. Failure to produce a result remains a shared operational error. Logs are neither evidence nor audit records. |
| Stores | Add no database. Keep existing store lifetimes and histories. Projection runs no probe and changes no store. Snapshot metadata and logs cannot replace governed evidence. |
| Repository | Keep ADR-015 limits, ADR-117 public imports, Python 3.14, frozen tooling, and packaging. Schema changes need ADR-061 compatibility, publication ledger, generated parity, and fixtures. Report JSON remains an implementation output. |

## Design and verification

The extension seam is exact subject identity, profile or suite, and required-check coverage.
Keep corpus roots and selected obligations as parameters.
Add no parallel report family, schema registry, validator stack, or central profile ladder.
Use the Typer format-selection precedent.
Do not wrap reports in the unrelated semantic-command envelope.
Do not inherit its read-only filesystem claim for live probes.

Both formats must expose each failed, unsupported, partial, or unrun required check.
Keep mismatches, material limits, and the evidence scope in both views.
Text may shorten other detail.
Test valid, failed, incomplete, unsupported, and false claims for both subjects.
Compare verdicts, scope, leakage, and exact specialist pins.
Keep the backend CLI, facade, processor, honesty, #1071, and #1017 tests.
Installed runners must not depend on checkout test doubles or pytest discovery.
Keep wheel and sdist corpus checks in CI.

Use repository policy before and after edits.
Set `RAES_REQUIREMENT_UID=ASR-526`.
Run targeted local tests only.
Full, integration, fuzz, and completion suites stay in CI.
Keep schema, claim, and traceability gates.
Do not alter ADR acceptance pins, release versions, changelogs, or research captures for reporting.
Existing ADR-008/009/019/036/061/072/102/110/113/115/116/117 cover these boundaries.
No new ADR is needed.

New runtime semantics, backend features, native resume, provisioning, credential handling, hosting, and persistence platforms remain outside this reporting design.
