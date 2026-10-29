# Revised control semantics and current support

RAE executes control through explicitly installed owners and retained evidence.
This reference describes current support after #1018 and #1374.
The [examples](../../examples/revised-control.md) exercise existing RAE paths with controlled test providers.
The [migration guide](../../migration/revised-control.md) identifies the producer and reader changes.

## Terms and authorities

| Term | Meaning | Authority |
| --- | --- | --- |
| Policy | Reusable permissions, states, authority constraints, and validity rules. An edge does not schedule itself. | [MC-01–MC-09](../../../specs/formal/participant-semantics/reusable-mixed-control.md) |
| Occurrence | One attempted application at an exact policy, episode, state, order, and evidence cut. | [API-409 v2 schema](../../../contracts/schemas/participant-runtime/participant-control-occurrence-v2.json) |
| Admitted apparatus | The complete pinned selection of profiles, mechanism instances, configurations, authorities, and support obligations. | [CA-01](../../../specs/formal/participant-semantics/control-applicability-and-evaluation.md) |
| Applicable slots | The relevant subset of that apparatus at one cut, including declared input dependencies. | [API-424 reference](modular-participant-control-contracts.md) |
| Required result | A result in the required-input closure of an applicable obligation or mandatory consumer. | [CA-02–CA-04](../../../specs/formal/participant-semantics/control-applicability-and-evaluation.md) |
| Optional contribution | Advice outside that closure. Invalid output becomes bounded lost-advice evidence without its payload, state proposal, or effects. | [Applicability migration](../../migration/control-applicability-and-evaluation.md) |

Coverage accounts for every required profile obligation.
It records applicability, proven inapplicability, or unresolved status.
Missing results and provider `None` do not prove inapplicability.
An empty applicable subset needs complete coverage and all ordinary gates.
Required advice must be available, but its opinion has no direct veto.
An admitted decision rule interprets it.

Parent decisions are permit, deny, or withhold.
A complete deny decision is not a missing provider result.
An effect after denial needs independent authority and satisfied prerequisites.
A prepared evaluation permits no dispatch.
The atomic commit records the actual receipt and dispatchable effect identities.

## Outcomes are separate facts

| Boundary | Evidence established there | What remains unproved |
| --- | --- | --- |
| Request | A valid, identified request naming exact inputs and expected state | Authorization, admission, or effects |
| Admission | Required authority, support, context, and a retained claim when accepted | Successful execution or cessation |
| Execution | Validated owner outcome and effect readback for the claimed invocation | Participant delivery or observation |
| Delivery | The exact recipient, audience, policy, result join, and admitted delivery boundary | External transport or consumption beyond that boundary |
| Observation | A separate authenticated observation under the selected observer profile | Broader participant knowledge or universal equivalence |

An accepted operation receipt can identify a failed or indeterminate operation.
An inject can change the world and still fail.
A delivery failure does not undo that world effect.
Missing delivery or observation proves neither success nor policy denial.
Cancellation acceptance and backend acknowledgement do not prove cessation.

The [inject contracts](inject-occurrence-contracts.md) define per-binding readback and aggregation.
Unknown effects remain indeterminate until the owning evidence path establishes more.
Reconciliation retains linked facts. It does not rewrite the original outcome or restore consumed dispatch authority.

## Supported arrangements

These rows describe the configured RAE runtime, not a backend certification.
Contract declarations alone do not install any row.

| Arrangement | Required installation and pins | Demonstrated behavior and limit |
| --- | --- | --- |
| Repeated control | Compiled rev1 policy, API-409 v2 reader, `MixedControlRuntimeBinding`, trusted live-cut owner | Two edges support two cycles in one episode. Each application has fresh identities and evidence. Exact retry adds no occurrence. |
| Modular evaluation | API-424 v2 selection/evaluation content pins, provider/v2, complete coverage and authorized stage inputs | Required dependencies govern release. Optional malformed advice is isolated. Supported effects use separately installed owners. |
| Participant-free inject | Original plan, exact node bindings, `InjectExecutionResolver`, operation provider and evidence resolver | An authored world effect has its own occurrence and outcome. No participant is synthesized. |
| Directed delivery | Matching compiled inject/control bindings, crossing owner and `resolve_delivery_cut` | Exact accepted control and successful world result can produce a governed local carrier. This establishes no participant observation. |
| Simultaneous mixed execution | `MixedRuntimeBinding.backend_installations`, exact composition/mapping/time pins and separate bridge, coordinator and readers | Two active component runtimes execute a mapped action. Delivery and observation have separate stage evidence. |
| Staged handoff | Admitted phase transition, installed transfer owner, time coordination and independent owner readback | The phase advances only after verified transfer. Stale or contradictory ownership cannot establish success. |
| Reusable control plus mixed runtime | No supported joint installation | Configuration refuses the combination. Separate passing rows do not establish joint support. |
| Distributed dispatcher plus portable mixed services | No installed remote mixed-worker authority | Configuration refuses the combination. Local portable mixed execution remains available. |

Directed delivery still requires its original authored schedule anchors.
An independent world occurrence can execute without them, but its participant join is refused.
Provider support determines which bindings, placements, and inputs an inject can execute.
General resume, new-trial allocation, and reset/compensate repetition remain unsupported by the current native execution carrier.
The [authored recovery guide](execution-recovery-migration.md) separates representable requests from executable admission.

## Architecture and evidence

The [runtime architecture](../sdl/runtime-architecture.md#control-and-effect-evidence-flow) shows the owning boundaries and stores.
The [mixed execution model](../../migration/mixed-backend-execution.md#runtime-installation) defines stage settlement and authenticated readback.
The [demonstration](mixed-control-demonstration.md) pins its executing test apparatus and compares fresh processes.
Its mixed report retains `passed: false` because it includes unsupported combinations.
The demonstration succeeds when all results match their declared expectations.
It does not change the report verdict.

The evidence supports bounded RAE behavior through test implementations.
It establishes no native backend qualification, physical timing guarantee, universal equivalence, or simulation-to-operation transfer.
A fresh second process is not evidence that an independent party ran it.

The [opacity migration](../../migration/participant-opacity-observed-evidence.md) requires execution observations and fresh backend readback.
Its reference profile establishes runtime-mediated behavior under its uniform-denial limits.
It does not establish useful allowed-action opacity, backend-native ownership, or a completed bisimulation proof.

## Historical and requirement records

API-409 occurrence v2 and API-424 evaluation v2 are independent lineages.
Semantic revisions, wire versions, schema hashes, profile revisions, and store versions remain separate pins.
Historical v1 records keep their original readers, policies, identities, and limitations.
Accepted ADRs and retained reports describe their original publication or execution cut.
For example, the reusable-control specification's introductory runtime-refusal statement describes its publication-time implementation boundary.
The current installed path is documented in [reusable participant control](reusable-participant-control.md).
That implementation update does not change MC-01–MC-09.

[API-409](../../requirements/API-409/requirement.md), [API-424](../../requirements/API-424/requirement.md),
[RUN-310](../../requirements/RUN-310/requirement.md), and [RUN-320](../../requirements/RUN-320/requirement.md) retain their recorded completion scope and traceability.
Their ACTIVE status does not certify every backend or composition.
[ASR-537](../../requirements/ASR-537/requirement.md) remains DRAFT for its broader realization and transfer protocol.
The #1018 demonstration and this documentation do not promote it.
Identity migration and replay remain under their existing owners.
