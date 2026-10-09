# Mixed-backend execution contracts migration

Issue #1371 publishes portable contracts for the executable mixed-backend
obligations defined by the
[issue #1355 decision](../decisions/issue-1355-executable-mixed-mapping-time-preflight.md):

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
`wall_clock_only`, `unknown` and `unsupported` bases cannot be expressed. An edge
binding also carries the declared mapping loss, a delivery reader, an optional
observation reader and the edge's evidence references.

Services are pinned by `service_ref`, `version` and `digest`. A service
reference is an identity, never a module, path, URL, command or credential.
Decoding a binding installs nothing, selects no provider and grants no
authority.

## Stage reports

Each report repeats the exact `binding` of one shared operation invocation,
the canonical digest of its request, and a positive `sequence`. Its `stage` is
one of:

| Stage | Fact it reports |
| --- | --- |
| `time-grant` | Coordinator grant over the bound clocks: mapping, ordering basis, order reference, comparison, both coordinates and the mapping and timing evidence. |
| `execution` | Bridge execution with status `succeeded`, `failed`, `partial` or `unknown`. Known effects need readback evidence. A known failure needs cessation evidence. |
| `delivery` | Destination receipt read back independently of the bridge result. |
| `observation` | Participant and audience readback after delivery. |
| `handoff` | Native transfer disposition at the predecessor history head and phase revision. |
| `owner-readback` | Native responsibility owner read back after the transfer attempt. |

Execution, delivery and observation are separate facts. One success value
cannot create another stage, and partial or unknown execution keeps its own
status. The reports are evidence proposals: RAES validates them and alone
commits operation state, composition history and terminal outcomes.

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
- A service reports each stage at most once per invocation, after its
  prerequisite stage. Execution and native transfer reports need an `ordered`
  grant and an accepted acknowledgement, so no invocation stage follows a
  refusal.
- A proposed shared outcome may claim success or known failure only when the
  stage reports establish it. Shared evidence may cite only stage reports that
  the invocation supplied.

## Reader obligations

Readers resolve the sealed profile, resolution context, time-model declaration
and shared transcript through their owning authorities. They then call these
pure validators from `raes_contracts.contracts`:

1. `validate_mixed_backend_bindings()` requires exactly one matching binding
   for each edge active in an admitted phase. It requires one binding for each
   transition that replaces exactly one component with another. It refuses
   missing, foreign, duplicate or contradictory bindings. It also refuses an
   edge with an ungoverned order and a transition that changes components in
   any other way. Alternative profiles admit no binding.
2. `require_mixed_backend_admission()` joins the request to the binding, then
   applies the shared capability and exact-context willingness checks before
   any invocation.
3. `validate_mixed_backend_stage_reports()` checks one invocation's reports
   against the binding, the request and its response transcript.

The stage validator compares a proposed `SUCCEEDED` or `FAILED` outcome with
the state the stages establish. It uses the reference coordinator's settlement
rules:

- An edge succeeds only with `succeeded` execution and destination delivery.
  Observation is a separate optional stage. Failed execution with cessation
  evidence is a known failure. Partial, unknown or undelivered execution is
  `INDETERMINATE`.
- A handoff succeeds only when a `committed` transfer is followed by an owner
  readback naming the destination owner at the next phase revision. A `failed`
  or `stale` transfer whose readback still names the source owner at the same
  revision is a known failure. Every other combination is `INDETERMINATE`.

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

The corpus under `contracts/fixtures/control-plane/` carries five transcripts.
Each one has a request, its responses and its stage reports:

| Example | Meaning |
| --- | --- |
| `mixed-edge` | Ordered grant, succeeded execution, destination delivery and participant observation; the shared outcome succeeds. |
| `mixed-edge-partial` | Partial execution after an ordered grant; the shared outcome is `INDETERMINATE`. |
| `mixed-edge-refused` | Contextual refusal at admission; no invocation stage can follow. |
| `mixed-handoff` | Committed native transfer with a destination owner readback at the next phase revision. |
| `mixed-handoff-stale` | Stale transfer whose readback retains the source owner; the shared outcome is a known failure with no effect. |

Each new contract also has `invalid/` and `context-invalid/` examples. Run the
focused checks from the repository root with
`uv run --project implementations/python --frozen --all-extras python -m pytest implementations/python/tests/test_issue_1371_mixed_backend_contracts.py -q`.

## Limits

The validators perform no I/O, dispatch or state mutation. Passing them proves
neither backend truth nor installation, conformance or runtime authority.
These contracts add no generic federation framework, HLA, FMI or HELICS
support, common clock or physical-OT timing guarantee. They also add no
exactly-once effects, multi-controller authority or backend equivalence.
