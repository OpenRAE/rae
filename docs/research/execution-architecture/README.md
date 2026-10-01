# Execution architecture — issue #1350

The accepted decision is [ADR-113](../../decisions/adrs/adr-113-reusable-execution-machinery.md):
self-hosted Temporal and PostgreSQL for distributed execution, existing library
and SQLite compositions for local profiles, with RAE retaining semantic authority.
No paid software is required. This delivery selects and documents the design;
it does not deploy a service, add runtime dependencies or enable P3.

The scope includes CTFs, OT twins, AI security research/sandboxes, product testing
and mixed IT/OT disaster recovery. Their failure responses and validity rules
can differ, including within one scenario. Authors select contextual policies,
scenario defaults, nested defaults and local overrides; engine retries cannot
supply those decisions.

## Reading order

1. [ADR-113](../../decisions/adrs/adr-113-reusable-execution-machinery.md): selection,
   component/interface diagram, responsibilities, deployment and consequences.
2. [Authored failure/retry policy](authored-retry-policy.md): contextual responses,
   scoped defaults, attempts, fresh trials and the implementation boundary.
3. [Execution protocol](execution-protocol.md): authorization, ledger/engine
   reconciliation, stale ownership, partitions and restore.
4. [Candidate comparison](candidate-comparison.md): mechanisms, free-software
   observations, retained duties and selection rationale.
5. [Experiment report](experiment-report.md), [sources](experiments/README.md),
   [original evidence](evidence.json), and [local recheck](local-recheck.json).
6. [Requirement disposition](decision-discussion.md) and
   [preflight](../../decisions/issue-1350-execution-architecture-preflight.md).

## Evidence provenance

The workspace contained the seven-candidate experiment bundle when this delivery
began. Its thirteen source hashes match the retained files. The original report
and [cleanup record](cloud-cleanup.json) describe that earlier synthetic cloud
run; this delivery did not provision cloud resources. A new local run rechecked
AnyIO, SimPy, DBOS, Temporal and SQLite publication with the same source bytes,
and ran the three witness tests. A further Temporal run checked terminal status
and result/error types through a verifier with four negative-control tests,
while keeping the original thirteen source files unchanged.
ROS/Ray/BehaviorTree.CPP results remain from the
original retained run. The two evidence records must not be conflated.

The [issue](https://github.com/OpenRAE/rae/issues/1350),
[#1348 decision](../../decisions/issue-1348-operation-lifecycle.md) and
[Hub #3](https://github.com/OpenRAE/hub/issues/3) establish scope and responsibility.
RAE determines admitted execution and validates outcomes; backends realize
resources, report effects and enforce contextual limits. A cancellation receipt,
engine success, checkpoint or process death cannot establish physical cessation.

Production persistence, tenant isolation, distributed ownership, co-simulation
fidelity and backend containment are not demonstrated by these bounded probes.
The design states how to handle their limits and what executable delivery must
verify. It does not use the local quickstart to limit either backend product.
