# Participant crossing compatibility

This reference covers the SEM-230/API-423/RUN-319 boundary in RAES 11.0.2.
Use [adopt governed participant crossings](../../migration/participant-information-flow-control.md) for the task procedure.

## Compatibility contract

A compatibility statement must name its producer and consumer.
It must give the direction, dimension, and source/target revision.
Accepting a shape does not establish semantic equivalence or behavioral compatibility.
It does not establish operational interoperability, runtime realization, or noninterference.

### SDL authoring

Source: an SDL author using `sdl-authoring-input-v1`.
Consumer: the current `raes` parser, validator, instantiator, and compiler.
The claim is backward structural and semantic acceptance.
Existing scenarios keep their authored meaning.
Paired SDL fixtures and the parser test show that no rewrite occurs.
An environment inject does not become participant-directed by inference.

### Existing participant records

Source: an API-406/API-409 producer.
Consumer: an API-423-aware history reader.
The claim is backward structural acceptance only.
Lifecycle, behavior, observation, control, and outcome records keep their shape.
Without a companion crossing record, their crossing status is legacy/unknown.
That absence establishes no permit, denial, delivery, observation, or exact enforcement.

### Runtime snapshots

Source: a legacy `runtime-snapshot-v1` writer.
Consumer: the current snapshot reader.
The claim is backward structural acceptance.
`participant_crossing_history` may be absent.
Before defaults apply, `participant_crossing_history_presence()` distinguishes absent, explicitly empty, and populated source payloads.
Empty history is not evidence of historical enforcement.

### Decision surfaces

Source: a decision-surface v1 producer.
Consumer: a decision-surface v2 reader.
The required change is manual semantic reprojection.
V1 remains historical evidence.
Do not copy `observation_order` to `decision_epoch`.
Use the ADR-095 reprojection procedure and its existing tests.

### Backend manifests

Source: a backend-manifest v2 producer.
Consumer: current manifest/profile admission.
The claim is backward structural acceptance and profile-relative operational support.
Missing participant-policy features stay unsupported.
Positive API-407 features need an exact `feature_support` entry.
They also need required contracts, evidence, a resolver, and profile admission.
The paired manifest fixtures exercise the existing typed adapter and bounded-strength declaration.

### Participant implementation manifests

Source: a participant implementation manifest v1 producer.
Consumer: current apparatus admission.
The claim is backward structural acceptance with explicit v2 opt-in.
Implementations opt into participant-facing decision-surface v2.
They do not declare the API-423 assurance/history carrier merely to signal migration.

### Backend profiles

Source: a backend-profile v1 producer.
Consumer: current target admission.
The claim is exact profile-relative operational support.
`full-remote-control-plane` explicitly requires API-409/API-423 carriers.
Other profiles gain no participant-policy meaning by implication.

### Transport projections

Source: an API-408 HTTP client.
Consumer: RUN-319 governed runtime projection.
The path supports backward legacy behavior or governed operational enforcement.
Without a resolver, the legacy projection stays available.
With a resolver, the HTTP adapter passes the authenticated identity.
Before lookup, it requires a candidate participant/audience binding.
It obtains evidence from `resolve_participant_view_evidence()`.
It commits the crossing before serialization.
Headers and query values cannot author policy, audience, state-cut, or crossing evidence.

### Historical claims

Source: a historical behavioral-claim or conformance producer.
Consumer: an exact catalog/report reader.
The claim is backward, revision-pinned interpretation.
Keep historical relation, projection, quantifier, evidence, and limitation scope.
Do not relabel a rev1 record as rev3 or `policy-noninterference`.

## Published carriers

The directly affected authored and derived inputs are:

- `sdl-authoring-input-v1`.
- `instantiated-scenario-v1`.
- `orchestration-plan-v1`.

The decision and crossing carriers are:

- `participant-decision-surface-v1` and `participant-decision-surface-v2`.
- `participant-control-occurrence-v1`.
- `participant-crossing-occurrence-v1`.
- `participant-observation-envelope-v1`.
- `participant-lifecycle-event-v1`.

The state and projection carriers are:

- `participant-episode-state-envelope-v1`.
- `participant-episode-history-event-stream-v1`.
- `participant-behavior-history-event-stream-v1`.
- `participant-context-view-v1`.
- `participant-history-view-v1`.
- `participant-status-view-v1`.
- `runtime-snapshot-v1`.

The apparatus carriers are:

- `backend-manifest-v2`.
- `backend-profile-v1`.
- `participant-implementation-manifest-v1`.
- `participant-implementation-provenance-v1`.
- `participant-configuration-result-v1`.

The operation and claim carriers are:

- `operation-receipt-v1`.
- `operation-status-v1`.
- `behavioral-relations-v1`.
- The non-schema `BackendConformanceReport`.

Other carriers are transitively gated.
These include execution binding/control/service state, shared state, joint action, time, outcome, evidence, and provenance.
They round-trip unchanged and carry no adoption flag.

## Compatibility fixture evidence

The corpus checks legacy SDL before and after opt-in selection.
It checks absent versus explicitly empty crossing history.
Incumbent behavior history stays byte-for-byte equivalent in those cases.
It exercises legacy and bounded API-407 manifest declarations through the existing v2 adapter.
It checks participant-manifest v2 opt-in without exposing API-423 assurance.
It also checks legacy and required backend-profile admission.

Issue #802 adds shipped compatibility evidence, not a new normative external derivation.
The lineage ledger and source audit stay unchanged.
The scientific-completeness assessment already cites RUN-319 and ASR-535 evidence.
This migration does not promote that assessment.
