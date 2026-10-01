# Retained production-evidence shape contracts

These frozen JSON Schemas validate the structure of production evidence in the
historical formal-validation corpus. They are research integrity artifacts, not
published language contracts or readers that execute legacy SDL semantics.

`manifest-v2.json` records each originating repository revision, schema path,
and exact frozen-schema SHA-256. The schemas retain both the pre-cutover v1 and
progressive v2 semantic identities used by releases through 16.0.0. Their
top-level required fields cover the complete serialized evidence envelope.
Only reachable definitions are retained.

The satisfiability shape narrows the witness snapshot to the three exact snapshots
already retained in `finite-domain-satisfiable-v2.json`,
`finite-domain-satisfiable-v3.json`, and `finite-domain-satisfiable-v4.json`.
This admits the recorded corpus without
introducing a general legacy scenario reader. Missing members, unknown members,
malformed nested structures, and changed snapshot constraints are rejected even
when surrounding manifest and observation digests have been rebound.

The offline gate checks these shapes before projecting historical identity joins.
Policy constants independently pin the manifest and the canonical digests of the
twelve retained evidence records. Rebinding artifact, observation, or manifest
metadata cannot authorize a replacement schema or an unrecorded historical
artifact. Computed checks verify model, graph, configuration, snapshot and witness
digest joins, source/authored joins, core references, and recorded witness steps.
The finite corpus pins also preserve the original records' remaining invariants.
It uses an empty external-reference registry and never invokes current artifact
models, analyzers, solvers, or CLI replay for historical evidence. Shape admission
and recorded digest agreement do not constitute semantic execution or establish
compatibility. Current release evidence still uses current models and replay.

The original `manifest-v1.json` and its narrower pre-cutover shapes remain
independently pinned. `manifest-v2.json` supplies frozen shapes for retained
progressive evidence records that became historical with the materialization
capture. The gate accepts a retained record through either frozen shape
version, then checks the complete record's immutable identity and joins.
Current release 21.0.0 uses production APIs and CLI replay; archival admission
never substitutes for that current-code check.
