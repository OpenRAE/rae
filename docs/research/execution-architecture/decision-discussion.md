# Decision disposition and canonical traceability

[ADR-113](../../decisions/adrs/adr-113-reusable-execution-machinery.md) is the
single accepted execution-architecture decision for #1350. It replaces the
provisional Temporal/PostgreSQL discussion previously kept here. Acceptance
selects an architecture; it does not claim a runtime implementation or P3.

The design resolves the earlier worker-authorization, ledger/history and
stale-owner questions in the [execution protocol](execution-protocol.md).
[Contextual failure and retry policy](authored-retry-policy.md) records author
control, scenario/scoped defaults, and distinct experiment, twin, IT and OT
responses. The [comparison](candidate-comparison.md) and
[experiments](experiment-report.md) retain alternatives and evidence limits.

## Canonical requirement mapping

API-404 is the issue's assigned requirement and remains ACTIVE for its existing
P0–P2 clauses. Add DOCUMENTS traceability for this design and mechanism evidence;
retain existing IMPLEMENTS/TESTS assertions at their stated scope. Other owners
below retain their statements and statuses, including all DRAFT time owners.
This disposition does not claim their missing implementation has shipped.

| Canonical owner | Evaluation relationship and remaining boundary |
| --- | --- |
| [API-404](../../requirements/API-404/requirement.md), C1–C4 | Single state authority, atomic settlement, startup without implicit replay, bounded served supervision and profile nonclaims. Toy publication and candidate probes are not production conformance evidence. |
| [API-402](../../requirements/API-402/requirement.md), [API-403](../../requirements/API-403/requirement.md), [RUN-304](../../requirements/RUN-304/requirement.md) | Submission/status/history remain portable; any new invocation/control/evidence carriers need governed publication. |
| [RUN-300](../../requirements/RUN-300/requirement.md), [ASR-532](../../requirements/ASR-532/requirement.md) | Shared RAE runtime drives backends and validates results; worker/library adoption does not transfer semantic authority. |
| [DSL-113](../../requirements/DSL-113/requirement.md), [SEM-203](../../requirements/SEM-203/requirement.md), [SEM-204](../../requirements/SEM-204/requirement.md) | Authored workflow/attempt/retry and compensation rules govern effects, rather than engine retry defaults. |
| [SEM-227](../../requirements/SEM-227/requirement.md), [SEM-228](../../requirements/SEM-228/requirement.md), [SEM-229](../../requirements/SEM-229/requirement.md), [RUN-317](../../requirements/RUN-317/requirement.md), [RUN-318](../../requirements/RUN-318/requirement.md), [API-421](../../requirements/API-421/requirement.md) | Scenario-time pause and apparatus time are distinct. SimPy demonstrates a mechanism only; clock mappings, restart continuity and multiple time domains remain untested. DRAFT owners remain DRAFT. |
| [SCE-006](../../requirements/SCE-006/requirement.md), [SCE-007](../../requirements/SCE-007/requirement.md), [EXP-706](../../requirements/EXP-706/requirement.md), [EXP-712](../../requirements/EXP-712/requirement.md), [SCE-002](../../requirements/SCE-002/requirement.md) | No framework restart may silently allocate another attempt/trial or establish clean state. The probes do not implement trial admission or cleanup verification. |
| [RUN-310](../../requirements/RUN-310/requirement.md), [RUN-311](../../requirements/RUN-311/requirement.md), [SEM-222](../../requirements/SEM-222/requirement.md) | Participant episode/termination authority is separate from an engine task or backend goal lifecycle. No participant semantics changed. |
| [RUN-316](../../requirements/RUN-316/requirement.md) | Operational status is distinct from experiment evidence. The independent witness deliberately measures effects separately from framework status. |

## Acceptance mapping

| Issue criterion | Delivered artifact and verification |
| --- | --- |
| Compare applicable patterns and reusable seams | Candidate comparison and ADR-113 alternatives; primary sources, explicit deployment/license observations and seven retained candidate probes. |
| State/worker ownership, supervision, scheduling, persistence, backend/deployment/failure boundaries | ADR-113 component/interface diagram and execution protocol; single semantic authority and explicit loss-window table. |
| Bounded evidence for blocked calls, cancellation, recovery and duplicate effects | Original source-hashed evidence/report plus independent local recheck; witness assertions distinguish effects from framework status. |
| One accepted decision with canonical traceability | ADR-113, ADR index/pin and API-404 DOCUMENTS entries; targeted governance and pin checks. |
| Author retry/default/context clarifications | Authored retry-policy design, scenario/nested/local resolution, context-specific failure response and mixed-scope compatibility. Future schema/compiler/runtime support is explicitly unclaimed. |

API-404-C1 is preserved by one state writer and atomic publication; C2 by
retained claims and observation before a newly authorized effect; C3 by scoped
supervisory authorization and bounded control paths; C4 by keeping P3 unavailable
and excluding implicit tenant/coordination claims. Existing supervision and
profile tests check their current boundaries, not distributed conformance.
