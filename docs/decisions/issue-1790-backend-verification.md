# Backend port verification

This record covers issue #1790 against the Python source on `go-cutover`.
The machine-readable source-case map is in
`implementations/go/backend/testdata/source-case-map.json`.
It records 49 source modules and routes 398 named source tests to their portable owner or runtime boundary.
A routing entry does not claim that a runtime wrapper test ran in Go.

## Acceptance mapping

| Issue criterion | Implementation and evidence |
| --- | --- |
| Small interfaces with published payloads | `backend/roles.go`, `backend/optional.go`, `contract/runtime`; typed API declarations and architecture checks |
| Manifest, capability, and envelope golden results | Existing portable and full-admission corpus checks for the four scoped contract families; existing capability, domain, and membership reference vectors |
| Runtime-free stub behavior | `backend/stub`; 64 manifest option cases, lifecycle and action-history fixtures, evaluator reference cases, envelope identity refusal, retained observations, and stop order |
| Input limits and security checks | Materialization byte/UTF-8 boundaries; transport and aggregate fragment bounds; foreign callback refusal; owned copies; exposure and temporal joins; recovery classification; explicit role opt-in; corrupt-state privacy |
| Envelope relations | Shared admission owner for subsumption and projections; native SDL witness and probe admission; independent fixture comparisons, Unicode and numeric digest regressions, widening diagnostics, and constructive/refusal probes |
| Existing defects and helper lessons | Source-case map plus existing admission and processor tests for feature evidence, resource budgets, capture offers, private services, topology, account placement, operation truth, and contextual joins |
| Findings that do not require a second Go hierarchy | Published bindings replace Python capability classes and structural attribute protocols; immutable packaged profiles expose no arbitrary path loader |
| Runtime split | Live target factories, trial/inject adapters, native dispatch, execution grants, stores, and runtime-dependent assertions remain with #1894 |
| Design before implementation | Recorded design and architecture preflight on the issue thread; initial and final `archcheck -design` results |
| Required delivery gates | Targeted local checks precede review and publication; CI owns full coverage, regression, mutation, and fuzz checks |

## Reference boundaries

The fixtures under `backend/stub/testdata` and `contract/admission/testdata/backend`
were recorded by running the unchanged Python reference.
They supplement the existing golden corpus.
They are ordinary test vectors, not numbered research or specification captures.

The source refuses 48 of the 64 stub manifest option combinations because disabled roles leave incompatible declarations.
The Go constructor preserves those refusals.
It does not alter Python or the normative fixture to make those combinations pass.

The fixed generated snapshot carrier uses maps.
For stop results, the double retains its own operation order and sorts imported entries whose prior insertion order the carrier cannot express.
The published plan also omits the Python resolver's private resource index.
Running status uses portable operations and startup order.
These native representation limits are stated in the design and require no schema change.

The Go role interfaces provide method presence at compile time.
They do not reproduce Python keyword validation or dynamic signature inspection.
Contract admission, explicit installation, effective capability, and runtime authority remain separate checks.

## Verification record

Targeted checks exercise the new contracts, doubles, relations, SDL seams, and the changed observation selector.
The scoped portable and full-admission golden cases pass.
The code-level architecture check passes.
The focused strict lint run passes.
Full CI results are recorded on the delivery pull request.

## Review execution and publication decision

Three pre-push attempts reached the twenty-minute deadline without a verdict.
The station reported 21 bounded review slices and no oversized slice.
The [review record](https://github.com/OpenRAE/rae/issues/1790#issuecomment-6943708799) records the failed attempts.
The repository's supported one-hour timeout setting passed configuration validation, but the third attempt still ended after twenty minutes.
That ineffective setting was removed.
The completed-cycle cap remains one.
A timed-out attempt consumes no completed cycle and supplies no findings or approval.
On 2026-11-18, the user explicitly authorized publication without a fourth attempt and manual Git/GitHub delivery.
No completed automated review is claimed.
Commit checks and CI remain required.
