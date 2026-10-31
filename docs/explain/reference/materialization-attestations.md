# Backend materialization attestations

A backend can return the actual world as SDL. The SDL can include in-world
instrumentation and rewrites. This SDL is a statement by the producer. It is
not independent evidence that the physical world matches the description.

The contract is opt-in. Add `backend-materialization-attestation-v1` to the
manifest only when the backend can satisfy the
[complete reporting contract](../../../specs/sdl/materialization-attestation.md).
The bundled stubs and the emulation backend do not claim this support.
The configured realization envelope must identify the producer configuration.

## Producer and runtime flow

1. Compile the original SDL. Plan with `PlanScope(run_id=...)`.
   A negotiated plan keeps `materialization_source`. This field holds the
   complete admitted instantiated snapshot and the original source identities.
   The field is part of the authenticated plan identity. Do not rebuild it
   from resource payloads.
2. After all materialization and setup hooks, make a `MaterializedScenario`
   with the ordinary SDL vocabulary. Include a result that has no additions.
   Bind the provenance to the submitted plan, the bound operation ID, the
   previous snapshot, the producer manifest and configuration, and the source.
   Record each node instance. Record each added, changed or removed member.
   Qualified names stay qualified.
3. Return `ApplyResult(..., materialization_attestation=MaterializationSubmission(sdl=...))`.
   `raes_processor.compiler.materialization_differences` gives value-free
   differences against the original source. It does not give permission for
   those differences. Withheld values use the existing native redaction forms.
   Do not use raw secrets or opaque snapshot commitments.
4. Set the runtime `materialization_archive` to
   `RunMaterializationArchive(Path(...))` from `raes_operations.run_artifacts`.
   `RuntimeManager` and `RuntimeControlPlane` both accept this dependency.
   If no archive is set, the operation fails before the backend changes anything.
5. The runtime runs the original authority and preparation checks. Then it
   admits the report, publishes protected bytes and verifies their record.
   The ordinary snapshot and store codecs keep the typed reference.
   An invalid report or a failed publication returns a failure. The runtime
   keeps a valid cleanup state, but it does not undo physical changes.
   After a restart, the durable operation returns its saved result. It does
   not run materialization again.

The operator selects the output directory as the archive root. SDL files are
restricted (`0600`). The archive does not follow symbolic links. It does not
replace an existing identity. A retry with the same bytes is safe. A retry with
different bytes fails. File publication and the operation-store commit are
separate steps. A failed reference commit can leave a protected orphan file.
It never leaves an accepted reference to bytes that were not published.
Recovery must not run the backend again.

## Size limits

One limit, `MATERIALIZATION_MAX_BYTES`, bounds each materialization document.
The limit is 4 MiB (4,194,304 UTF-8 bytes).
It applies to the source snapshot, the submitted SDL and the prospective augmentation content.
It also applies to archive publication, archive readback and the size in an archive record.
The archive checks the incoming text and the rendered bytes, because rendering can make a document larger.

These budgets are different:

| Budget | Value | Scope |
| --- | --- | --- |
| Materialization document | 4 MiB | One source, report or prospective document. |
| SDL parser input | 8 MiB | Any SDL document. |
| Portable runtime value | 1 MiB for each value, 8 MiB total | All other runtime values. |
| Operation plan nodes | 262,144 | Plans from the planner and their compiled realization authority. |
| HTTP request | 1,000,000 bytes by default | Control-plane requests. A larger plan needs an explicit `max_request_bytes`. |

The runtime gives the document limit only to contract fields that declare a document body.
Another string keeps the 1 MiB value limit.
A source above the limit fails planning with `materialization.source-limit-exceeded`.
A missing run identity or target scope fails with `materialization.source-context-required`.

## Consumers and run records

`parse_sdl` and `parse_sdl_file` read the artifact. `render_sdl_source` formats
it. `canonical_materialized_sdl_digest` and `compare_canonical_artifacts`
compare its separate phase identity. Shared compilation and planning work for
inspection, but the resulting plans cannot be applied. To start a new
execution, derive and validate a new authoring document.

Copy the `materialization_attestations` records of the accepted snapshot to
the experiment run. Keep `scenario_snapshot_ref` on the original input.
An augmentation disclosure can use the new reference as a portable carrier.
It must keep the required visibility classes, markings, evidence references
and comparability or observer effects. A collector that is present did not
necessarily capture evidence. Associated-artifact manifests accept the
materialized parent. They validate byte streams from the caller and do not
fetch URIs.

The attestation is required operational provenance for the negotiated
contract. It does not request more probes. It does not override evidence
prohibitions. It does not give participants access to the full document.
