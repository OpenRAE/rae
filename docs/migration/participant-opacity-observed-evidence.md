# Participant-opacity observed evidence migration

Issue #1374 changes the participant-opacity probe harness in
`raes_conformance.conformance.participant_opacity_probes`.
The runner now derives the observation transcript from runtime execution and backend readback.
The [design](../decisions/issue-1374-observed-opacity-evidence-design.md) defines the evidence boundary.

Update a backend-owned harness as follows:

1. Replace `observe()` with `reported_observation()`.
   It returns the transcript that the backend reports for one point.
2. Add `backend_readback(target, case, request)`.
   Read backend-owned state each time the runner calls it.
   Return `ParticipantOpacityBackendReadback` with the exact `ParticipantOpacityReadbackRequest`.
   Include a state source label and a `sha256:` state digest.
   Do not cache a response, because each request carries a fresh runner nonce.
3. Supply `protected_point` and `complement_point` as `ParticipantOpacityProbePoint` values.
   Each point binds a point reference to one exact-cut crossing policy resolver.
4. Supply the participant, episode, behavior, action request, identity, crossing evidence, and idempotency key.
5. Remove `expected_observation`, `realization_owner`, and `execution_basis` from each case.
6. Remove `manifest_digest`, `configuration_digest`, and `tool_digest` from each case.
   The runner computes these values.

The runner owns the expected normal form for each admitted profile revision.
It derives the realization owner from committed runtime records.
Under `participant-opacity-runtime-reference-v1`, a passing case is `runtime-mediated`.
That case keeps only the backend-declaration claim.

A harness without readback cannot pass.
A reported transcript that differs from the measured transcript fails the case.
Final-sink flow control stays enabled unless the case disables it explicitly.
