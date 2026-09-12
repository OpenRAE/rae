# Runtime Control-Plane Architecture

Issue [#1151](https://github.com/OpenRAE/rae/issues/1151) defines what the
RAES runtime control-plane is: a portable contract with profiled
implementations spanning hermetic tests, single-user local execution,
embedded RAE/env-pack/ETV consumers, air-gapped deployments, and served
topologies. It answers the state-authority, operation-lifecycle,
concurrency, and failure-recovery questions that issue #1092 and PR #1136
exposed, and it disposes of those surfaces explicitly.

- [Architecture preflight](../../decisions/issue-1151-runtime-control-plane-architecture-preflight.md)
- [ADR-104](../../decisions/adrs/adr-104-runtime-control-plane-architecture.md)
- [CP-2 unified-mutation preflight](../../decisions/issue-1181-unified-control-plane-mutations-preflight.md)
- [Current-state assessment](current-state-assessment.md)
- [Composition architecture](composition-architecture.md)
- [Requirement and surface disposition](requirement-disposition.md)
- [Implementation program](implementation-program.md)
- [Machine-readable program](implementation-program.json)
- [FM3 abstract operation model](../../../specs/formal/runtime-control-plane/README.md)

The requirement authority is `API-404` (ACTIVE). The implementation program
is owned by the **Runtime Control-Plane** milestone; every work package is
filed as a concrete issue and linked from the program.

Issue #1151 does not implement or select a storage engine by code change,
publish new portable schemas, change runtime execution behavior, or claim a
distributed or highly available topology. Profile P3 (coordinated
multi-process ownership) is recorded as a seam and an explicit nonclaim; no
consistency, coordination, or recovery guarantee named in this set is
claimable before its implementation issue lands with tests.
