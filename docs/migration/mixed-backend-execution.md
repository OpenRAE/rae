# Mixed-backend execution contracts migration

Issue #1371 publishes portable contracts for the executable mixed-backend
obligations that
[ADR-102](../decisions/adrs/adr-102-mixed-cross-backend-participant-control.md)
section 13 adopted for issue #1355. The
[issue #1355 preflight](../decisions/issue-1355-executable-mixed-mapping-time-preflight.md)
is architecture guidance for that amendment, not a normative decision. The
two contracts are:

- [`mixed-backend-execution-binding-v1`](../../contracts/schemas/control-plane/mixed-backend-execution-binding-v1.json)
  is the plain-data form of one installed bridge, time coordinator and set of
  readers for one admitted `sem-234/rev1` edge or native handoff.
- [`mixed-backend-stage-report-v1`](../../contracts/schemas/control-plane/mixed-backend-stage-report-v1.json)
  carries one correlated stage fact for one invocation of the shared
  [backend operation protocol](../../specs/formal/runtime-contracts/backend-operation-supervision.md).

This note defines producer and reader obligations. It is not a migrator.
Publication changes no runtime behavior: the reference coordinator described in
[mixed participant composition](../explain/reference/mixed-participant-composition.md)
still executes its in-process `MixedEdgeExecutionBinding` and
`MixedHandoffBinding`. No runtime, store or HTTP path reads or writes the new
carriers, and no executable or runtime adoption is claimed.

## Execution bindings

A binding names its sealed profile by `profile_id`, `profile_revision` and
`profile_digest`. Its `subject` is either an `edge` or a `handoff`:

- An edge binding fixes the operation kind to `participant-crossing`. It names
  the destination provider as `owner_component_id` and its action allocation as
  `owner_allocation_id`. It also carries the participant and audience of the
  edge's crossing subject, the source and destination action addresses, and the
  pinned bridge. The only subject transformation is `compiled-identity`, so both
  action addresses must be equal. Native translation stays inside the pinned
  bridge. Owning the effect confers no controller, disclosure or terminal-commit
  authority.
- A handoff binding fixes the operation kind to `composition-phase`. It names
  the leaving and joining components, their native ownership references, the
  pinned transfer service and the native owner reader.

Both kinds carry a time requirement: the time model reference and digest, the
source and destination clocks, the clock mapping, a governed ordering basis and
the pinned coordinator. The required comparison is always `ordered`.
`wall_clock_only`, `unknown` and `unsupported` bases cannot be expressed. An
edge's time requirement also carries the admitted edge's `temporal_coupling`:
`tight`, `bounded-asynchronous` or `asynchronous`. A transition declares no
coupling, so a handoff carries none. An edge binding also carries the declared
mapping loss, a delivery reader, an optional observation reader and the edge's
evidence references.

Services are pinned by `service_ref`, `version` and `digest`. A service
reference is an identity, never a module, path, URL, command or credential.
Each role has its own service: within one binding, no two of the bridge or
transfer service, the coordinator and the readers share a `service_ref` or a
`digest`. A binding that pins one service to two roles is invalid. Decoding a
binding installs nothing, selects no provider and grants no authority.

## Stage reports

Each report repeats the exact `binding` of one shared operation invocation
and the canonical digest of its request. Its `stage` is one of the kinds
below. Its `sequence` is fixed by that stage: the stage's position in its
chain, as the table shows. Each producer therefore numbers its own report
without seeing the other reports. This differs from the shared protocol's
response sequence, which one backend assigns in order. Every stage names its
`producer`, which must equal the service that the binding pins for that
stage:

| Stage | Sequence | Producer | Fact it reports |
| --- | --- | --- | --- |
| `time-grant` | 1 | `time.coordinator` | Grant at the committed coordinates of both bound clocks: mapping, ordering basis, order reference, comparison, both coordinates and the mapping and timing evidence. |
| `execution` | 2 | `bridge` | Bridge execution with status `succeeded`, `failed`, `partial` or `unknown`. Known effects need readback evidence. A known failure needs cessation evidence. |
| `delivery` | 3 | `delivery_reader` | Destination receipt read back by the delivery reader, not by the bridge. |
| `observation` | 4 | `observation_reader` | Participant and audience readback after delivery. A binding without an observation reader admits no observation stage. |
| `handoff` | 2 | `transfer` | Native transfer disposition at the committed composition history head and phase revision. |
| `owner-readback` | 3 | `owner_reader` | Native responsibility owner read back after the transfer attempt. |

Execution, delivery and observation are separate facts. One success value
cannot create another stage, and partial or unknown execution keeps its own
status. The reports are evidence proposals. A reader must validate them as
described below, and only RAES may commit operation state, composition history
and terminal outcomes.

## Digests

The binding reference digest and each stage-report citation digest are SHA-256
over RFC 8785 canonical JSON of the complete validated model, including
materialized defaults and null values, with array order preserved. A digest is
written as `sha256:` followed by 64 lowercase hexadecimal digits. The reference
encoders are `mixed_backend_binding_reference()` and
`canonical_json_digest(report.model_dump(mode="json"))`. The request digest
follows the backend operation protocol's own rule.

## Producer obligations

- An edge bridge or native transfer service implements both the shared
  `BackendOperationProvider` protocol and `MixedBackendBridge`. A coordinator
  implements `MixedTimeCoordinator`, and a reader implements `MixedStageReader`.
  These protocols live in `raes_backend_protocols.mixed_backend`.
  `require_mixed_backend_service()` checks the declaration and installed call
  shapes without invoking code.
- A service declares both contract IDs in `supported_contract_versions`. A
  bridge also declares the four backend operation contracts. The declaration is
  opt-in and is not effective support; it adds no API-407 feature term or
  support level.
- A shared request commits to one binding. Its `command` is the reference
  returned by `mixed_backend_binding_reference()`. Its `backend_id` names the
  pinned bridge or transfer service, and its operation kind matches the binding.
- Each stage report names the producing service exactly as the binding pins
  it. Because every role has its own service, a bridge never reports a time
  grant, delivery or observation. A transfer service never reports a time
  grant or its own owner readback.
- A coordinator grants over the committed time readback that it receives, and
  both coordinates in its grant equal that readback. It reports `ordered` only
  when the mapped source coordinate does not pass the destination coordinate
  within one segment. Otherwise it reports `incomparable`.
- A transfer service names the committed composition history head and phase
  revision that it acted on.
- A service reports each stage at most once per invocation, under the
  stage's fixed `sequence` from the table above. A retransmitted report
  carries identical content. A transcript that holds a stage must also hold
  its prerequisite stage. Readers accept reports in ascending `sequence`, so
  the order in which reports arrive does not matter. Execution and native
  transfer reports need an `ordered` grant and an accepted acknowledgement,
  so no invocation stage follows a refusal or an `incomparable` grant.
- A proposed shared outcome may claim success or known failure only when the
  stage and settlement model below establishes it. Shared evidence may cite
  only stage reports that the invocation supplied.

## Reader obligations

Readers resolve the sealed profile, resolution context, time-model declaration,
shared transcript and their own time and composition readbacks through their
owning authorities. They then call these pure validators from
`raes_contracts.contracts`:

1. `validate_mixed_backend_bindings()` requires exactly one matching binding
   for each edge active in an admitted phase. It requires one binding for each
   transition that replaces exactly one component with another. It refuses
   missing, foreign, duplicate or contradictory bindings, including an edge
   binding whose temporal coupling differs from the admitted edge. It also
   refuses an edge with an ungoverned order and a transition that changes
   components in any other way. Alternative profiles admit no binding.
2. `require_mixed_backend_admission()` joins the request to the binding, then
   applies the shared capability and exact-context willingness checks before
   any invocation.
3. `validate_mixed_backend_stage_reports()` checks one invocation's reports
   against the binding, the request and its response transcript. Its
   `context` argument is a `MixedBackendStageContext` that holds these trusted
   inputs:
   - `time_model`: the declaration resolved from the binding's time
     requirement.
   - `time_model_ref` and `time_model_digest`: the reference and digest that
     the caller resolved `time_model` under. They must equal the binding's
     time requirement.
   - `time_state`: the committed time readback that the coordinator received.
     It must validate against `time_model` and cover both bound clocks.
   - `post_time_state`: RAES's own time readback after the invocation, or
     `None` when none was taken. When present, it must validate against
     `time_model`.
   - `composition_state`: the committed composition state of the binding's
     profile. A handoff requires it. When present, it must still activate a
     bound edge. For a handoff, its active components must include the source
     component and exclude the destination component.

## Stage and settlement model

The stage validator enforces this abstract model for one invocation. The rules
apply to the published carriers only. They do not describe the in-process
coordinator, which does not read the carriers.

**State.** The record holds the accepted stage reports, at most one of each
kind. It also records whether the response transcript holds an accepted
acknowledgement and whether time is confirmed. Time is confirmed when
`post_time_state` is present and neither bound clock coordinate in it is lower
than in `time_state`. Coordinates compare by segment, then tick, then
microstep.

**Preconditions.** Before any report is accepted, the trusted inputs must
match the binding. `time_model_ref` and `time_model_digest` equal its time
requirement, and `time_state` covers both bound clocks. A `composition_state`
belongs to its profile, and it activates the bound edge or precedes the bound
handoff as described above.

**Transitions.** Reports are accepted in ascending `sequence`, which is chain
order, whatever order they are supplied in. A report is accepted only when its
`sequence` is its stage's position from the stage report table, its
prerequisite was accepted before it and its joins hold:

| Stage | Prerequisite | Joins |
| --- | --- | --- |
| `time-grant` | None | Both coordinates equal `time_state`. Mapping and ordering basis equal the binding. The grant cites the admitted evidence. An `ordered` grant has the mapped order within one segment. |
| `execution` | `ordered` grant and accepted acknowledgement | Action addresses and declared loss equal the binding. |
| `delivery` | Execution that did not fail | The destination component is the destination provider. |
| `observation` | Delivery | Participant and audience equal the binding. |
| `handoff` | `ordered` grant and accepted acknowledgement | The order reference equals the grant. History head and phase revision equal `composition_state`. The report cites the admitted evidence. |
| `owner-readback` | Handoff | None beyond the producer. A readback naming neither owner stays a valid, contradictory fact. |

Every report must also name the pinned producer for its stage and repeat the
invocation binding and request digest. A repeated sequence number must carry
identical content, and a transcript holds at most 64 reports.

**Settlement.** The accepted stages establish exactly one state:

| Kind | Established state | Condition |
| --- | --- | --- |
| Edge | `SUCCEEDED` | `succeeded` execution, delivery and confirmed time. |
| Edge | `FAILED` | `failed` execution, or an `incomparable` grant with no execution stage. |
| Handoff | `SUCCEEDED` | `committed` transfer, an owner readback naming the destination owner at the committed revision plus one, and confirmed time. |
| Handoff | `FAILED` | `failed` or `stale` transfer, an owner readback naming the source owner at the committed revision, and confirmed time. An `incomparable` grant with no handoff stage also establishes `FAILED`. |
| Either | `INDETERMINATE` | Every other combination. |

**Observation rules.** A proposed `SUCCEEDED` or `FAILED` outcome must equal the
established state. A `CANCELLED` or `INDETERMINATE` proposal is checked only by
the shared protocol's own rules. Only an explicit `incomparable` grant shows
that no invocation could start. An `ordered` grant without an invocation stage,
or no grant at all, establishes no failure, because an unreported invocation
may have started.

**Invariants.** No invocation stage follows a refusal or an `incomparable`
grant. No stage is accepted from a service other than its pinned producer, and
no service holds two roles in one binding. A success never rests on a
backend's own time or composition claims. It needs the committed and
post-invocation time readbacks, and a handoff also needs the committed
composition state. A violated join refuses the whole transcript instead of
settling it.

## Compatibility

Both contracts are new IDs with draft stability under ADR-061. The
`supported_contract_versions` enums of `backend-manifest-v2` and
`backend-profile-v1` gain the two IDs. Existing manifests and profiles remain
valid. The stub and reference backends do not declare the new IDs.

The meaning of a published `sem-234/rev1` profile is unchanged. Historical
reference-only records stay reference-only: no reader may reinterpret their
`success`, mapping references or timestamps as delivery, observation or
governed timing evidence. The in-process runtime bindings and the published
carriers are not converted into one another. The binding has no field for
callables, module paths, URLs, commands, credentials or open metadata.

## Examples

The corpus under `contracts/fixtures/control-plane/` carries six transcripts.
Each one has a request, its responses and its stage reports:

| Example | Meaning |
| --- | --- |
| `mixed-edge` | Ordered grant, succeeded execution, destination delivery and participant observation; the shared outcome succeeds. |
| `mixed-edge-partial` | Partial execution after an ordered grant; the shared outcome is `INDETERMINATE`. |
| `mixed-edge-refused` | Contextual refusal at admission; no invocation stage can follow. |
| `mixed-edge-time-refused` | The destination clock has entered a later segment, so the grant is `incomparable`. The bridge accepts the start but reports no execution stage, and it proposes a known failure with no effect. |
| `mixed-handoff` | Committed native transfer with a destination owner readback at the next phase revision. |
| `mixed-handoff-stale` | Stale transfer whose readback retains the source owner; the shared outcome is a known failure with no effect. |

Each new contract also has `invalid/` and `context-invalid/` examples. The
binding's `bridge-as-reader` and `transfer-as-owner-reader` examples are
invalid because they pin one service to two roles. Run the focused checks from
the repository root with
`uv run --project implementations/python --frozen --all-extras python -m pytest implementations/python/tests/test_issue_1371_mixed_backend_contracts.py -q`.

## Limits

The validators perform no I/O, dispatch or state mutation. Passing them proves
neither backend truth nor installation, conformance or runtime authority. They
compare the producer that each report names with the binding. The caller must
authenticate that a report came from that service. The binding model refuses
one service reference or digest in two roles, but whether two distinct
services are operationally independent is a deployment property that no
validator can prove.

These contracts add no generic federation framework, HLA, FMI or HELICS
support, common clock or physical-OT timing guarantee. They also add no
exactly-once effects, multi-controller authority or backend equivalence.
