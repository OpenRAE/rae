# Contract bindings and validation preflight

Issue #1780 applies to checkout `ffb54d246`.
This note gives design constraints.
It is not an implementation plan.
ADR-009, ADR-061, ADR-121 and ADR-122 govern the work.
No new ADR is needed.
Python code and published schemas must stay unchanged.

## Authority and design

The checkout has 148 schemas and 148 publication entries.
Read that list through the publication manifest and its entry files.
Do not keep a second hand-written contract list.
Keep the publication, Python schema parity and schema coverage checks.
Each check proves a different claim.

There are 288 annotations and 180 distinct invariant IDs.
The issue's 68 Python-only rules are part of that set.
Extract each rule into `specs/`.
Use existing family specifications where they state the rule.
A Python function name or a count check is not a rule specification.
Read the model checks, helpers and defect tests too.

The Go prerequisites are present on `go-cutover`.
The contract layer has no packages yet.
Declare each package, import and external dependency in the architecture model.
Name the public interfaces in the design.
Pass `archcheck -design` before writing Go code.
A parity runner also needs permission to import the contract layer.
Product code must not import parity or tooling.

## Checks and types

Use one maintained Draft 2020-12 engine for schema checks.
The standard library has none.
Prove that the chosen engine compiles every published schema.
Prove that it gives the recorded reference results.
Do not build a schema engine or copy the Python class tree.
Do not put separate validators in each adapter.

Generate Go types from published schema bytes.
Do not generate the schemas from Go types.
A successful decode does not prove schema validity.
A transport value grants no domain authority.
Types whose methods rely on invariants need checked constructors and private state.
Their zero values must not bypass checks.
Do not expose mutable maps or slices from admitted values.
Check external and restored input at its boundary.

Keep absent members, null and zero distinct.
Keep exact numbers, array roots, field spelling and allowed open maps.
Reject extra members where the schema closes an object.
Do not choose the first decodable union branch.
Do not insert defaults or rely on Go's case-insensitive field matching.
Generated titles and factored definition names are not stable domain concepts.
Do not merge unrelated definitions merely because their names match.

Each contract and invariant ID selects one rule.
Read annotations in definitions and at the root.
Keep their input paths and where they apply.
Do not run a rule from a union branch that does not apply.
Reject duplicate or missing rules and invalid profile or input references.
Missing trusted context must not produce full success.

This issue owns dispatch, bindings and rule specifications.
The maintainer expanded issue #1780 to include the domain rules.
The admission owner implements them within the same contract boundary.
Keep those rules with their owners.
Pass trusted context explicitly.
Do not import processor or runtime services into the contract layer.
Do not add a service locator or trust a payload's claim of authority.
A no-op rule cannot stand in for a missing rule.
State separately what schema checks and semantic checks prove.

## Compatibility and bounds

The bundle uses unions, conditionals, references and array and object constraints.
It includes `contains`, `prefixItems`, `uniqueItems` and typed `additionalProperties`.
Published patterns contain lookahead that Go's standard regex parser rejects.
Do not drop or weaken a pattern or an unsupported keyword.
Check Unicode, search behavior, whole-string matches and numeric equality.
A backtracking engine needs a work bound; a byte limit alone is not enough.

Keep format behavior specific to the reference surface.
The golden schema surface has no format checker.
Domain-profile admission has one.
Use the existing timestamp owner for RFC 3339 and known leap seconds.
A global date-time checker would change acceptance.

Compare raw schema results, Python results and normalized output separately.
Check Boolean and integer distinctions, integral numbers, enums, defaults and lax type conversion.
Keep Python acceptance or record the maintainer's decision for each difference.
Do not enable broad type conversion or weaken a schema.
The narrow #1779 exceptions grant no wider permission.

Use `base/ingress` for bytes, depth, duplicate members, encodings and finite numbers.
Keep its failure order and approved exceptions.
Use the existing value, graph, domain, canonical JSON and digest helpers.
Keep each owner's limits.
Bound schema work, recursion, regex work and error collection too.
Cache only immutable schemas, with safe concurrent access.
Refuse external HTTP and file loads, including implicit schema and metaschema loads.
The current bundle has only local references.
Keep user-supplied domain schemas and their admission limits separate from the trusted bundle.

## Other trust boundaries

Use the existing URI, pointer and secret-reference helpers.
Keep percent decoding, credential refusal and the 256-byte secret-reference limit.
A URI or secret name grants no right to fetch or resolve it.
Keep environment literals, generated values, operator secrets and redaction distinct.
Do not expand variables or read environment values here.
Runtime owners still admit installed components and control-plane configuration.

Existing security owners retain identity, role, target and audience checks.
Keep their strict Boolean fields, request bounds and closed defaults.
Schema success grants no authority to a principal or bearer token.

Use `base/fault` and its six error classes.
Distinguish bad input, missing context and broken packaged resources.
Never expose raw validator errors, values, keys, source paths or causes.
Keep bounded errors in stable order.
Domain diagnostic codes permit dots; fault codes do not.
Diagnostic pointers omit `#`; invariant input paths include it.
Use the existing diagnostic adapters for public surfaces.
Keep CLI exit status 70 and sanitized MCP error envelopes.
Use value-free logging through the existing log owner.

Expose one read-only corpus seam through `io/fs`.
Package every needed family and notice from the published source.
`go:embed` cannot read outside its package tree.
Check the complete packaged copy for missing, extra and changed bytes.
Runtime must need no checkout, Python, shell, Git, network or writable extraction directory.
Keep explicit development roots separate, with no traversal or symlink escape.
Missing or corrupt resources must fail; an empty catalog is not a fallback.

Store owners retain version, scope, digest and recovery checks.
DTOs do not become database schemas or store interfaces.
This issue adds no store, migration or persistence service.

## Evidence and gates

Reuse the existing artifact router, schema coverage tools, parity recorder and result comparator.
The `schema validate` surface records only the schema verdict.
It does not prove Python type conversion or semantic checks.
A `context-invalid` fixture can pass its schema.
Directory names are not expected verdicts.
Not every JSON fixture is an ordinary payload.
Use the recorded reference results.

A missing required runner, fixture or rule must fail its check.
Compile success, inventory rows and skipped tests are not execution evidence.
Compare all generated output with a fresh temporary generation.
A hash header alone does not prove faithful bindings.
Keep Python's independent generation check.
Test built packaging without the checkout in CI.
Read the corpus, ingress, domain-profile and schema-parity tests, including their issue-specific defect cases.

Use the current module files, digest admission, architecture model and canonical CI graph.
Keep the current style, coverage, mutation, fuzz, race, regression, security, policy and Sonar gates.
Do not exempt generated output from assurance or add a parallel release workflow.
Local tests stay targeted.
Do not send source to an external generator or a new service.
