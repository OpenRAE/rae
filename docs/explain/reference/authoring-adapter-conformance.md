# Authoring-adapter conformance

Use the published authoring vectors to compare the output of two paths through
an adapter. The same interface supports a CLI, MCP or agent tool, graphical
editor, and documentation workflow. The reference runner tests the submitted
results; it does not launch those products or authenticate their identities.

The normative contract is
[`specs/conformance/authoring-adapters.md`](../../../specs/conformance/authoring-adapters.md).
Vectors and their fixed expected observations ship under
`contracts/fixtures/authoring-adapters-v1/cases`. The first profile covers strict,
self-contained SDL validation and declaration rename, including parse and
rename refusals. It does not cover module composition, materialized artifacts,
unstructured advisory prose, pack operations, or runtime outcomes.
The `rename-invalid-source` vector covers rejection before rename executes:
it requires structured parser diagnostics, but no transformation report.
Rename refusals after successful source admission still require provenance.

## Submit two results

Load a vector with `load_authoring_vectors()` from
`raes_conformance.authoring_adapters`. Give its `input_source` and `operation`
to both paths. For each result, construct an `AuthoringPathOutput` with the
exact input, emitted SDL source (or `None` on refusal), incumbent structured
diagnostics, and the existing transformation report when the operation produces
one. Call `compare_authoring_paths(vector, left, right)` with optional descriptive
`left_path` and `right_path` identifiers.

The runner reparses emitted source and derives artifact evidence itself.
`reference_authoring_output(vector)` exercises the production parser, renderer
and rename API for a local baseline. Its output is checked against the fixed
fixture oracle; it does not replace that oracle. Actual transport integration
tests should submit results captured from their own adapter boundary.

## Read the result

`comparison.report` separates canonical artifact, diagnostic, provenance and
semantic relations. `left_matches_expected` and `right_matches_expected` check
each path independently. The Python `conformant` property is true only if both
match the vector and all four relations are equivalent or not applicable.
The property is derived; portable JSON consumers apply the same rule to the
published fields.

`comparison.semantic_result` retains the existing semantic comparison result
when both paths return artifacts. Keep it alongside the report and verify its
digest against `semantic_result_digest`. It identifies changed subjects and
preserves uncertainty. The canonical artifact digest and semantic comparator
coordinate use different named projections; do not interchange them.

For example, an editorial description change can produce `artifact_relation:
different` and `semantic_relation: equivalent`. A changed declaration produces
a semantic difference. A stale transformation source digest makes the
observation invalid. An alternative derivation digest produces a provenance
difference even if artifact semantics match. Two identical wrong outputs fail
their independent oracle checks.

Diagnostic equality uses code, domain or stage, severity and canonical address,
including duplicate counts. It excludes human wording and source ranges.
Retain the original diagnostic carriers and transformation reports to review
their evidence digests. Invalid observations produce fixed reason codes; the
comparison report never copies source text or exception details.

The result establishes consistency for the exact vector and profile digests.
It does not prove universal adapter equivalence, stronger validation assurance,
backend behavior, or completion of a user journey.
