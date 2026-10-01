# Backend materialization attestations

A backend can return the actual world as SDL, including its in-world
instrumentation and rewrites. This is a producer assertion, not independent
evidence that the physical world matches the description.

The contract is explicitly opt-in: add
`backend-materialization-attestation-v1` to the manifest only when the backend
can satisfy the [complete reporting contract](../../../specs/sdl/materialization-attestation.md).
The bundled stubs and emulation backend do not claim this support implicitly.
The configured realization envelope must identify the producer configuration.

## Producer and runtime flow

1. Compile the original SDL normally and plan with `PlanScope(run_id=...)`.
   Negotiated plans retain `materialization_source`: the complete admitted
   instantiated snapshot and original source identities. This field is part of
   authenticated plan identity; do not reconstruct it from resource payloads.
2. After all materialization and setup hooks, construct a `MaterializedScenario`
   using the ordinary SDL vocabulary. Include even no-additions results. Bind
   provenance to the submitted plan, bound operation id, predecessor snapshot,
   producer manifest/configuration and source. Record every node instance and
   every added, changed or removed member. Qualified names remain qualified.
3. Return `ApplyResult(..., materialization_attestation=MaterializationSubmission(sdl=...))`.
   `raes_processor.compiler.materialization_differences` provides value-free
   native-identity differences against the original source; it does not grant
   permission for those differences. Withheld values use existing native
   redaction forms, not raw secrets or opaque snapshot commitments.
4. Configure the runtime's `materialization_archive` with
   `RunMaterializationArchive(Path(...))` from `raes_operations.run_artifacts`.
   Both `RuntimeManager` and `RuntimeControlPlane` accept this dependency.
   Missing archive ownership fails before backend mutation.
5. The runtime runs original authority/preparation checks, admits the report,
   publishes immutable protected bytes, verifies their record, and preserves
   the typed reference in the ordinary snapshot/store codecs. Invalid reports
   or failed publication return failure with valid cleanup state retained;
   they do not undo physical changes. Durable operation idempotency returns the
   saved terminal result after restart without replaying materialization.

The output directory is an operator-selected archive root. SDL files are
restricted (`0600`) and published without following symlinks or replacing an
existing identity. An identical retry is safe; a conflicting retry fails.
File publication and operation-store commit are separate boundaries: a failed
reference commit may leave a protected orphan file, never a false accepted
reference to bytes that were not published. Recovery must not rerun the backend.

## Consumers and run records

`parse_sdl`/`parse_sdl_file` read the artifact; `render_sdl_source` formats it;
`canonical_materialized_sdl_digest` and `compare_canonical_artifacts` compare
its distinct phase identity. Shared compilation and planning work for inspection.
The resulting plans cannot be applied. Explicitly derive and validate a new
authoring document if an operator wants a new execution.

Copy the accepted snapshot's `materialization_attestations` records to the
experiment run. Keep `scenario_snapshot_ref` pointing at the original input.
Augmentation disclosures can use the new reference as a portable carrier while
retaining required visibility classifications, markings, evidence references
and comparability/observer effects. A collector's presence does not prove it
captured evidence. Associated-artifact manifests accept the materialized parent
and validate caller-supplied byte streams without fetching URIs.

The attestation is required operational provenance for the negotiated contract.
It does not request extra probes, override evidence prohibitions, or make the
full document available to participants.
