# Issue 1374: Observed runtime opacity evidence

Date: 2026-10-28

Contract: issue #1374 and its acceptance criteria; no formal requirement is
attached. This is architecture guidance, not an implementation plan or evidence
that opacity has been realized.

## Decision and current repository boundary

Keep evidence collection in the existing portable conformance/runtime seams.
The runner must derive its transcript from execution and independently bound
readback. A harness-returned transcript, even after a counted backend call,
cannot establish that crossing, denial, retry, delivery, or scheduling occurred.

No new ADR is needed. ADR-081/099 govern claims and opacity; ADR-095 governs
delivery; ADR-104/113 govern runtime ownership and execution machinery;
[ADR-115](adrs/adr-115-concrete-backends-owned-outside-raes.md) governs the
current backend boundary. The
[issue 965 note](issue-965-participant-opacity-backend-realization-preflight.md)
remains useful for assurance separation, but its reference-backend and report
writer instructions describe removed code. Do not edit that profile-pinned
source note to describe new observations.

The issue's historical `reference_participant_opacity.py` and diagnosis path
are absent from this checkout. Concrete backends, native lifecycle tooling,
and `write_backend_conformance_report()` are no longer RAES responsibilities.
The replacement seam is `ParticipantOpacityProbeHarness`, injected through
`run_target_conformance()`; see
[the migration guide](../migration/concrete-backends.md). Do not restore the
removed backend, inspect another checkout, or add a daemon dependency to solve
this issue. Backend distributions own live execution, readback, cleanup, and
their live release evidence. This repository can validate that boundary and
exercise the portable runtime with explicitly synthetic doubles. Missing live
evidence must remain non-passing for a native claim.

The current runner in `participant_opacity_probes.py` checks two returned
observations against `expected_observation`, a call count, and an owner label.
The double in `test_issue_965_participant_opacity_backend.py` returns the expected
constant from `participant_relation_probe()`. That tests runner mechanics, not
observed realization of the claimed mechanisms. The support constants in
`raes_contracts.participant_opacity_runtime` likewise describe the admitted
finite model; they are not measurements of a running system.

## Evidence ownership and claim discipline

Use `participant_policy_execution.py` as the incumbent pattern: typed case
inputs, a real `RuntimeControlPlane` on the supplied `RuntimeTarget`, scoped
instrumentation, operation/status readback, and committed history validation.
Reuse its instrumentation and validation where applicable; any shared extension
belongs in that common seam rather than a second call-counting framework.
Its legacy final-sink opt-out is not an implicit authorization to disable
current enforcement in new opacity evidence.

Backend-specific setup/readback stays in the injected harness. The runner owns
execution accounting, completeness checks, projection, comparison, and verdict.
Expected observations and reported observations are separate from measured
facts. A fixed expected normal form is valid as an oracle; copying it into the
measured result is not. Required facts need a specific execution/source binding,
not a harness pass boolean, arbitrary method invocation, or ownership assertion.

Keep three independent coordinates: execution substrate (`ExecutionBasis`),
realization owner (`ParticipantOpacityRealizationOwner`), and synthetic-model
versus observed-execution evidence. An in-process substrate can exercise real
code; a test double on it still supplies synthetic evidence. `native-live`,
`backend-native`, and `BackendConformanceReport.native_conformance` are not
synonyms. Preserve the actual per-case basis through result construction and
serialization: `_run_case()` currently validates the supplied basis but leaves
the result at its default `fixture-only`. Do not overwrite every case with a
run-wide native label to fix that discrepancy.

Uniform denial intentionally prevents protected backend actions. Zero such
calls can be the correct containment result. Setup, binding, initialization,
and readback calls must be distinguished from an attempted protected effect;
none proves backend ownership of denial. Runtime normalization establishes
runtime mediation. A backend-native claim additionally needs causal evidence
of the backend-owned mechanism, sensitive to a dishonest or no-op backend while
the runtime configuration is held fixed. If the runtime shields that mechanism
from observation, retain runtime-only evidence and refuse the stronger claim.

Use the existing `BehavioralClaimBindingModel` axes separately for declaration,
realization, and conformance. The report's relation stays
`bounded-probe-success`. Failed, unsupported, incomplete, and synthetic cases
must not acquire positive observed native claims or disappear from aggregates.
`validate_backend_conformance_report()` and
`backend_conformance_report_payload()` remain the shared finalization boundary.
Enforce any new evidence prerequisite there and in the executing runner. Then
manually constructed reports cannot bypass it.

## Observation boundary

Resolve the exact catalog/profile revision and digest. The current
`participant-opacity-runtime-reference-v1@sem-231/runtime-rev2` admits only
uniform denial, one individual observer, current cuts, retained cross-episode
memory, active probes, total logical order, and untimed, progress-insensitive
observations. Reuse `ParticipantOpacityObservationInventoryModel` and
`validate_participant_opacity_runtime_enforcement()` for the complete concrete
surface set. A list of broad channel names or the eleven transcript fields is
not equivalent to that inventory, especially for participant-state surfaces.

| Claimed behavior | Required basis for the derived observation |
| --- | --- |
| Crossing, decision, failure, action availability | Actual typed ingress/control call, operation receipt **and terminal status**, committed requested/decided records, uniform refusal outcome, and scoped backend-effect accounting. `accepted=True` means operation admission; a denied crossing can still have an accepted receipt and failed operation. |
| Delivery, omission, payload | Actual egress opportunity and returned/refused result, joined to the committed `delivery-attempted` record and its `withheld` disposition. Under denial there is no delivered view or delivered/observed event. Missing records or a never-attempted opportunity are not evidence of withholding. |
| Retry/replay | Repeated identical request/key in the same admitted context, the same operation identity, and unchanged existing history/effects. Changed binding or stale-cut conflict is distinct from successful replay. |
| Scheduling, latency, order | Actual bounded scheduler/shared-clock execution and committed causal order at the named cut. Reuse the participant scheduler, `clock_coordinate()`, and canonical policy binding. The logical bucket is the profile's abstraction of these facts; literal timing/order strings and wall-clock sleeps do not exercise scheduling. |
| Policy/release, participant state | Exact admitted binding, policy/release cut, and inventory reachability restrictions. Retained history survives reset; policy changes cannot silently reuse old evidence. Administrative read access is an observer's measurement tool, not a new participant-visible channel. |
| External effects | Scoped calls plus fresh backend-owned before/after readback of the affected state, tied to the same case. An unchanged portable snapshot cannot exclude native effects. Unknown or unavailable readback is incomplete evidence, never `external_effect="none"` by default. |

Validate records with `ParticipantCrossingOccurrenceModel` **and**
`validate_participant_crossing_occurrence_context()`; then rejoin opacity
bindings through the trusted runtime support context. Shape-valid records with
wrong subjects, predecessors, audiences, evidence refs, or cuts are invalid.
Readback must reject missing, duplicated, stale, or wrong-case facts. Reuse the
freshness, source-strength, origin, and configuration-binding discipline in
`_realization_validation.py` and `RealizationObservation` where their existing
concerns apply. Do not mislabel opacity as a provisioning concern or use
`envelope_digest` for a relation profile.

Compare the derived transcript both with the reported transcript and the
profile's expected projection. Equality between two fabricated or equally
wrong transcripts is insufficient. Preserve meaningful order and opportunity
structure; do not sort away leaks. Runtime-generated UUIDs, administrative
timestamps, and private instrumentation are not participant observations:
project only as the governed profile permits. Finite-model analysis remains in
the existing opacity analysis/model-check contracts with its own provenance;
it cannot authenticate source execution or replace missing runtime facts.

## Cross-cutting layers and canonical incumbents

| Layer | Required reuse and guardrail |
| --- | --- |
| Target, manifest, capability admission | `RuntimeTarget` shape checks, `BackendManifestV2Model`/manifest dataclass parity, `ParticipantFeatureSupport`, `PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS`, and `resolve_participant_feature_support()`. Preserve exact bounded profile constraints, evidence, limitations, and authorized weakening. No new opacity policy feature or parallel manifest. |
| Profile, configuration, provenance | Exact-revision corpus loaders, `canonical_json_digest()`, `PrefixedDigestString`, and `ControlPlaneConfiguration`. Bind runtime implementation/version, backend implementation/manifest, profile/catalog/inventory, observer, run/cut, strategy/scheduler, actual nonsecret configuration, probe set, and collector/tool/environment identity. Label/marker hashes alone do not identify executed code or configuration. Bound collections and validate supplied shapes; type annotations alone are not validation. |
| Runtime authority and policy | `ControlPlaneIdentity`, target roles, controller/audience subject bindings, deny-first crossing gates, feature admission, final-sink flow control, and current participant initialization/effect authority. Install required typed resolver/compiler context; do not patch normalization, fabricate histories, or relax policy to obtain a passing probe. A configuration limitation removes the stronger claim. |
| HTTP, if exercised | P2 is administrative-only. Retain `ControlPlaneSecurityConfig.strict_defaults()`, `_ControlPlaneApiAuth`, the checked/sealed route-authority inventory, bounded-body admission, and no-store responses. Administrative authorization neither grants participant visibility nor proves HTTP participant opacity. No new route is needed for in-process collection. |
| Secrets, environment, host | Use typed in-process injection. No new env-binding format, secret lookup, subprocess, socket, privilege, or host-service discovery is needed. Backend credentials/native lifecycle stay downstream. Only explicit nonsecret configuration/environment allowlists feed provenance; never hash full environments, credentials, predicates, memories, or raw hidden state into reports. Tokens/secrets must not enter argv, filenames, test ids, logs, or exception text. |
| Errors and observability | Reuse `Diagnostic`/`Severity`, stable `conformance.*` codes, and `sanitized_failure_message()`. Distinguish measured uniform refusal from unexpected backend/store/parser failure; an exception is not automatically a successful denial. Preserve stable HTTP 401/403, conflict, validation, and redacted 500 envelopes. `require_audit_event_fields()` admits closed bounded details: do not attach transcripts, backend objects, arbitrary config, rejected input, or tracebacks to audit/logs. |
| Durability and concurrency | `RuntimeSnapshot`, operation records, append-only crossing histories, `ControlPlaneStore.commit_participant_transition()`, expected history heads/revisions, idempotency, and persisted-context restart validation. Collect committed facts at one identified cut; reset per-case accounting after setup and isolate paired executions so retained state cannot contaminate the alternative case. A commit conflict or unfinalized effect cannot yield a positive result. No second ledger/store. |
| Report and publication | Reuse `ConformanceCaseResult`, the shared report validator and serializer, safe refs, bounded summaries, and nonsecret digests. The serializer is not a generic redaction service. Backend owners persist live reports; do not resurrect removed artifact writers. If portable contracts change, use `ContractModel(extra="forbid")`, published schemas, `schema_bundle()` parity, fixtures, publication ledger/hashes, exports, and compatibility gates together. Do not introduce a duplicate runtime-evidence schema in formal-analysis artifacts. |

The extension seam is the existing typed harness/case boundary, parameterized
by exact profile coordinates, backend/runtime/configuration identity, case and
state cut, observer/collector version, and evidence origin. Extend it only as
needed to carry independently checkable facts and completeness, retaining one
canonical transcript projection and report family. Another backend supplies a
different adapter; another profile requires governed support admission. Neither
justifies backend-name dispatch, dynamic callable imports, a generic evidence
service, or a second observation inventory.

## Verification and non-goals

Reuse the adversarial patterns in `test_issue_965_participant_opacity_backend.py`,
the runtime denial/retry/egress/restart cases in
`test_issue_964_participant_opacity_runtime.py`, and independent-readback cases
in `test_realization_honesty_conformance.py`. They should distinguish a constant
transcript after an unrelated call, false no-effect reports, missing channels,
stale/wrong provenance, malformed histories, unequal scheduling/order, and
secret-bearing failures. Keep synthetic doubles explicitly synthetic; tests
cannot substitute for a backend distribution's live evidence.

Follow `.ground-control.yaml`, `.gc/plan-rules.md`, repo policy tooling, and
targeted local checks; full test/integration/fuzz/completion suites belong to
CI. Do not invent a requirement UID for this requirement-free issue. New
source-bound research evidence uses `tools.research_capture` and
`docs/develop/research-captures.md`; this guidance is not a research capture.
Preserve historical profile/catalog pins and published evidence.

This issue does not add useful allowed-action opacity, delivered participant
views, new SDL syntax, or supervisor synthesis. It does not add a new
scheduler, retry, or delivery engine, backend lifecycle services,
cross-backend equivalence, or unfinished bisimulation proofs. It makes no universal, all-strategy, all-schedule, timed,
progress-sensitive, probabilistic, quantitative, coalition, partial-order, or
whole-deployment claim. More instrumented executions strengthen only the named
finite evidence boundary; they do not prove the finite carrier complete for
an arbitrary live deployment.
