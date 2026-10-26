# Post-materialization SDL attestation

Issue #1241 extends SEM-225 with `raes-materialization-attestation/v1`.
An attestation describes the world in SDL. It uses the existing scenario sections and their types.
It is not a recipe to build the world. It does not add a second vocabulary for nodes, services, mounts, commands or the environment.

## Document phase and identity

The materialized document has the common `ScenarioContent` fields and one
required `materialization_provenance` field. Authoring machinery (`module`,
`imports`, `variables`, `variation_points`, `realization`) and instantiation
provenance MUST NOT appear in this phase. The bounded `sdl-yaml/v1` parser MUST admit this phase.
It MUST check closed shapes and meaning and preserve qualified declaration identities. It MUST NOT resolve imports or
perform variable substitution while reading it. Unresolved SDL substitution
tokens are invalid. These rules also apply to empty authoring fields.

Materialization provenance identifies the attestation, run, operation, boundary and time.
It names the producer and its version.
It binds digests for the producer manifest and configuration, original authored source, admitted input, submitted plan and immediate predecessor.
Authored and instantiated digests keep their existing profile labels.
The attestation uses a separate canonical profile.
A byte checksum does not replace any of these bindings.

The provenance also carries value-free origin records and resource bindings.
Origin records distinguish added, chosen, changed and removed members.
They use source and materialized addresses. A wrapper or listener added within an authored
node requires its own origin; the node's origin is insufficient. Unchanged content keeps the origin of the admitted source.
This includes values derived by the processor. Resource bindings keep the source declaration and instance identity.
Replicas MUST NOT collapse into a single template. Collection checks use their existing semantic identities.
Ordered commands and rules keep their order. A producer MUST NOT relabel an authored member as an addition.

A counted node can have replicas with the same described content.
Each instance MUST have its own binding with the same node/address and a zero-based `instance_index`.
The indices MUST cover exactly `0..count-1`. A singleton
may omit the index. If instances differ, they MUST NOT collapse into a uniform template. Removed-member pointers resolve in the original source;
added/selected pointers resolve in the description. A removed keyed member and an added keyed member may occupy the same list position.
They need not share an identity.

The canonical input is exactly `{profile: "raes-sdl-materialized/v1", scenario:
M}`, where `M` uses canonical wire names and omits unsupplied optional fields.
It is serialized with RFC 8785 and SHA-256, with array order preserved.

Parsing and planning an attestation keep its descriptive phase.
To run it as new desired state, an author MUST first derive an authoring document. An attestation
MUST NOT replace the source against which the original run is checked.

## Materialization and disclosure

The `raes-materialization-effects/v1` coverage profile covers every authored
materialized element and every in-world effect introduced by the backend,
including additions within an existing element. Existing SDL owners describe
nodes, services, listeners, host exposure, mounts, environment, network
membership, executable commands, and injected file/content identities. An effect is in scope if it could be observed in the world.
This holds even if the operator calls it apparatus or no participant saw it.
Out-of-world bookkeeping is excluded; its in-world effects are included.

A successful materialization under this contract MUST return an attestation,
including when there are no additions. It MUST describe the state after every materialization hook in its producer scope.
This also includes each rewrite that sets up evidence. Each producer keeps its own scope and provenance.
If their claims overlap and conflict, they MUST NOT be merged by precedence. A partial or stale report cannot prove that materialization is complete.

The attestation is required for safe records of runtime origin. It does not implicitly
request a new guest probe, independent observation, experimental evidence
collection, or export. Their existing rules still decide when those actions are required, allowed or forbidden.
The rules for retention, checks and compensation also still apply. Backend selection
and backend assertions MUST NOT become independently observed evidence.

Checks on exactness and prepared members still use the original admitted plan. Required members, exact leaves, bounds, absence and
closure remain binding. Disclosed additions must also be authorized; disclosure
alone MUST NOT grant authority retrospectively. Before accepting success, the runtime MUST reject hidden changes, added members without permission and breached source constraints.
It MUST also reject invalid origins and mismatched execution bindings.

Existing rules for redaction and sensitivity apply to both added and authored content. Protected values stay omitted through their owning SDL forms.
Snapshot digests are not SDL values. A safely withheld command or value
must not conceal the existence of the added effect. If an effect cannot be
represented safely, the backend cannot claim complete contract support.
Errors contain bounded identities and reason codes, not document excerpts,
input values or backend exceptions. An effect visible in the world does not grant every participant access to the whole document.

## Runtime and archival delivery

The backend manifest names supported contract versions. Unsupported consumers MUST reject the contract rather than silently
drop the attestation. Shared result carriers take the attestation through runtime checks.
Opaque details, metadata, audit text and raw logs MUST NOT carry it. Trusted source context is kept separately.
A lossy operation plan or sanitized snapshot cannot restore the source SDL.

The existing run archive MUST contain the admitted SDL bytes.
It MUST also contain a checked, typed `materialization-attestation` artifact reference.
The reference binds checksum, size, sensitivity and execution. The run's `scenario_snapshot_ref` continues
to name the admitted input. Existing augmentation disclosures link the added effects.
Their rules for classification, marking, evidence and comparability still apply. Neither the attestation nor a collector's existence satisfies
an evidence-capture requirement.

Archive names and destinations are runtime-owned. Publication MUST be contained, protected and immutable.
A retry may reuse the same bytes.
It MUST NOT overwrite a different result under an existing identity. Publish checked bytes before their durable accepted reference.
Keep recovery data through the existing operation commit and snapshot revision checks. Atomic file
publication is not a transaction with the operation store. If the archive write fails, the runtime MUST NOT claim that the result can be reproduced.
It MUST NOT rerun apply on its own.
Valid cleanup inventory remains available. Returning a prior portable snapshot
does not itself roll back physical infrastructure.

The reference profile is `raes-sdl-materialized/v1`. `ref_path` is the
contained relative path `runs/<run-id>/attestations/<attestation-id>.sdl`;
the artifact URI is the inert `urn:sha256:<byte-checksum>` identity, not a host
path or fetch instruction. Associated-artifact checks bind supplied bytes to that identity and to the materialized parent. Run records
carry these joins in `materialization_attestations`; disclosure references must
resolve to a record belonging to the same run.

Addition permission is governed separately by [augmentation scope](augmentation-scope.md).
Omission means open; explicit closure is checked before materialization using
the same in-world effect definition as this report. The attestation does not
grant permission retrospectively. Neither contract scans all hosts on a continuous basis or proves producer identity through cryptography.
Neither turns observations into author intent on its own.

## Runtime descendant inventory

`backend-runtime-descendants-v1` extends this attestation through explicit backend negotiation.
The producer MUST also support `backend-materialization-attestation-v1`.
Other phase attestations MUST NOT carry a runtime inventory report.
Use provisioning refresh for later inventory.
The additional `materialization_provenance.inventory` field contains the bounded report.
Node values MUST remain in ordinary materialized SDL.
The report MUST NOT contain another world description or a runtime provenance ledger.

The provisioning request contains a runtime-bound `inventory_attempt_id`.
The report binds that identity, the original source digest and run.
Its target scope MUST match the trusted source context and invoking runtime target.
The enclosing attestation binds the operation, plan, producer configuration and immediate predecessor.
Supervised execution uses its admitted attempt identity for this binding.
The inventory sequence MUST increase within the same producer, source and run.
The report covers the producer's complete `/nodes` inventory.
If a scan is incomplete or evidence is unavailable, the runtime MUST NOT accept success.

Each descendant binds three addresses: its own canonical address, the responsible source and its causal parent.
Its native identity digest and creation receipt MUST remain stable across reports.
The parent instance index names the responsible replica.
Descendants use separate single-instance portable addresses in this profile.
A creation operation and a reporting operation have separate identities.
The same holds for their attempts.
Creation receipts MUST identify their run, operation, attempt and content-bound native evidence.
An ancestry chain MUST reach its named original source.
It MUST have bounded depth and no cycles.
Names, placement and dependency ordering MUST NOT substitute for causal evidence.
Native receipts remain claims by the producer.
Only an independent owning contract can establish stronger evidence.

The runtime MUST check each member against the original enclosing collection rule.
Node-local openness does not open a closed containing collection.
Imported namespace restrictions and required members remain binding.
Native node semantics, capabilities, dependencies and safe value projections remain mandatory.
Initial materialization MUST preserve applicable prospective augmentation checks.
Reporting observed deviations grants neither permission nor conforming membership.
Direct snapshot additions and backend-written realization provenance remain forbidden.

`inventory_refresh=true` identifies a distinct provisioning mutation request.
The refresh flag is part of the published request digest.
It is also part of the identity used for saved retries.
Refresh uses the original planner-authorized plan and a new operation and reporting attempt.
The backend's `refresh_inventory(request, predecessor)` method MUST be read-only.
It MUST return the unchanged predecessor and a separate materialization submission.
Refresh MUST NOT replay provisioning or create a new observation demand.
The runtime validates and projects reported descendants through the same admission contract.
The caller still needs permission to change state through the control plane.
Its supervision, audit and terminal commit rules still apply.

Omission MUST NOT imply termination or removal.
A `terminated` record requires separate lifecycle evidence and retains its inventory entry.
An `autoremoved` record requires separate lifecycle evidence and excludes the resource from live SDL.
The accepted report retains the removed identity as a tombstone.
Retained identities MUST NOT be replaced, resurrected or assigned another parent.
Replanning MUST NOT dispose of accepted descendants merely because authored SDL omits them.
If a closed collection conflicts with live children, their lifecycle must be resolved explicitly.
Explicit teardown operates on accepted live inventory.

The runtime derives concern provenance through registered native concern owners.
Original author and processor origins remain intact.
New descendant values have backend origin under the admitted open collection.
`backend_selections` identifies an admitted OPEN or CONSTRAINED concern by address, field and concern kind.
The runtime records that selected value as backend-realized even when it equals a processor template.
The producer MUST NOT relabel an EXACT concern.
Explicitness and value origin remain separate facts.
The same holds for strength of proof, ownership and visibility.

An invalid successful report MUST preserve the immediate trusted predecessor and empty changed addresses.
The refusal MUST identify the violated invariant without exposing rejected values.
The descendant path also preserves that predecessor when archive delivery fails.
This differs from independently validated legacy partial-failure cleanup.
The runtime MUST publish protected SDL bytes first.
It can then accept their typed archive reference and inventory metadata.
Snapshot codecs and run records MUST keep that metadata.
They MUST also keep the origin of each concern.
Native result digests identify backend proposals.
Terminal accepted-state digests identify the state derived by the runtime.

See the [backend integration procedure](../../docs/explain/reference/runtime-descendant-inventory.md).
