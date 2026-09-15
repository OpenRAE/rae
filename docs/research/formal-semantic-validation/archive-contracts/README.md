# Retained production-evidence shape contracts

These frozen JSON Schemas validate the structure of production evidence in the
historical formal-validation corpus. They are research integrity artifacts, not
published language contracts or readers that execute legacy SDL semantics.

`manifest-v1.json` records each originating repository revision, schema path,
and exact frozen-schema SHA-256. The schemas originate from the pre-cutover
contracts at that revision. Their top-level required fields cover the complete
serialized evidence envelope. Only reachable definitions are retained.

The satisfiability shape narrows the witness snapshot to the two exact snapshots
already retained in `finite-domain-satisfiable-v2.json` and
`finite-domain-satisfiable-v3.json`. This admits the recorded corpus without
introducing a general legacy scenario reader. Missing members, unknown members,
malformed nested structures, and changed snapshot constraints are rejected even
when surrounding manifest and observation digests have been rebound.

The offline gate checks these shapes before projecting historical identity joins.
Policy constants independently pin the manifest and the canonical digests of the
eight original evidence records. Rebinding artifact, observation, or manifest
metadata cannot authorize a replacement schema or an unrecorded historical
artifact. Computed checks verify model, graph, configuration, snapshot and witness
digest joins, source/authored joins, core references, and recorded witness steps.
The finite corpus pins also preserve the original records' remaining invariants.
It uses an empty external-reference registry and never invokes current artifact
models, analyzers, solvers, or CLI replay for historical evidence. Shape admission
and recorded digest agreement do not constitute semantic execution or establish
compatibility. Current release evidence still uses current models and replay.

`manifest-v2.json` adds frozen shapes for the four progressive evidence records
from release 16.0.0, which became historical with the issue-1241 capture. Each
shape enumerates the exact retained records; it is not a general reader for
their SDL revision. Independent manifest and record pins select this archive.
The same computed integrity checks verify their joins. The original v1
manifest, shapes, and eight pre-cutover records remain unchanged. No historical
case invokes a current model, analyzer, solver, or CLI.
