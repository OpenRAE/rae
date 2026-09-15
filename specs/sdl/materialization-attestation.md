# Post-materialization SDL attestation

Issue #1241 extends SEM-225 with `raes-materialization-attestation/v1`.
An attestation is a descriptive SDL document, using the existing scenario
sections and their owning types. It is not a provisioning recipe or a second
node, service, mount, command, or environment vocabulary.

## Document phase and identity

The materialized document has the common `ScenarioContent` fields and one
required `materialization_provenance` field. Authoring machinery (`module`,
`imports`, `variables`, `variation_points`, `realization`) and instantiation
provenance MUST NOT appear in this phase. The ordinary bounded `sdl-yaml/v1`
parser MUST admit the phase, apply its closed shapes and semantic validation,
and preserve qualified declaration identities. It MUST NOT resolve imports or
perform variable substitution while reading it. Unresolved SDL substitution
tokens are invalid. These rules also apply to empty authoring fields.

Materialization provenance identifies the attestation, run, operation,
post-materialization boundary, time, producer name/version, producer manifest
and configuration digests, original authored semantic digest, admitted
instantiated snapshot digest, submitted plan digest, and immediate predecessor
digest. Authored and instantiated digests retain their existing profile labels.
The attestation uses a separate canonical profile. An artifact byte checksum
does not replace any of these semantic or execution bindings.

The provenance also carries value-free origin records and resource bindings.
Origin records distinguish additions, selections/changes and removals by their
source and materialized addresses. A wrapper or listener added within an authored
node requires its own origin; the node's origin is insufficient. Unchanged
content retains the origin of the admitted source, including processor-derived
values. Resource bindings retain source declaration and instance identity so
replicas cannot collapse into a single template. Collection comparisons use
the existing owning semantic identities; ordered commands and rules retain
their order. A producer MUST NOT relabel an authored member as an addition.

For a counted node whose replicas have identical described content, each
instance has a separate binding with the same node/address and an explicit
zero-based `instance_index`; indices cover exactly `0..count-1`. A singleton
may omit the index. Different instance contents MUST NOT be collapsed into a
uniform template. Removed-member pointers resolve in the original source;
added/selected pointers resolve in the description. A removed and an added
keyed member may occupy the same list position without being the same identity.

The canonical input is exactly `{profile: "raes-sdl-materialized/v1", scenario:
M}`, where `M` uses canonical wire names and omits unsupplied optional fields.
It is serialized with RFC 8785 and SHA-256, with array order preserved.

Parsing and planning an attestation preserve its descriptive phase. Executing
it as new desired state requires an explicit authoring derivation. An attestation
MUST NOT replace the source against which the original run is checked.

## Materialization and disclosure

The `raes-materialization-effects/v1` coverage profile covers every authored
materialized element and every in-world effect introduced by the backend,
including additions within an existing element. Existing SDL owners describe
nodes, services, listeners, host exposure, mounts, environment, network
membership, executable commands, and injected file/content identities. The
test is whether an effect could in principle be observed in-world, not whether
the operator calls it apparatus or a participant actually observed it.
Out-of-world bookkeeping is excluded; its in-world effects are included.

A successful materialization under this contract MUST return an attestation,
including when there are no additions. It MUST describe the state after every
materialization hook and evidence-setup rewrite in its producer scope. Distinct
producers retain their own scope and provenance; overlapping contradictory
claims MUST NOT be merged by precedence. An incomplete or stale description
cannot establish completed materialization.

Attestation is required safe operational provenance. It does not implicitly
request a new guest probe, independent observation, experimental evidence
collection, or export. Those operations retain their existing demand,
prohibition, retention, verification and compensation owners. Backend selection
and backend assertions MUST NOT become independently observed evidence.

The existing non-approximation and prepared-membership checks continue to use
the original admitted plan. Required members, exact leaves, bounds, absence and
closure remain binding. Disclosed additions must also be authorized; disclosure
alone MUST NOT grant authority retrospectively. The result boundary MUST reject
undisclosed changes, unauthorized additions, contradicted original constraints,
invalid origins and mismatched execution bindings before accepting success.

Existing native redaction and sensitivity rules apply to added and authored
content alike. Protected values remain omitted using the owning SDL forms;
snapshot commitments are not SDL values. A safely withheld command or value
must not conceal the existence of the added effect. If an effect cannot be
represented safely, the backend cannot claim complete contract support.
Errors contain bounded identities and reason codes, not document excerpts,
input values or backend exceptions. In-world visibility does not authorize
every participant to retrieve the entire document.

## Runtime and archival delivery

Support is explicitly negotiated through the backend manifest's contract
versions. Unsupported consumers MUST reject the contract rather than silently
drop the attestation. Shared result carriers carry the attestation through
runtime admission; opaque details, metadata, audit text and raw logs are not
attestation carriers. Trusted source context is retained separately because a
lossy operation plan or sanitized snapshot cannot reconstruct the source SDL.

The existing run archive MUST contain the admitted SDL bytes and a verified,
typed `materialization-attestation` artifact reference with checksum, size,
sensitivity and execution binding. The run's `scenario_snapshot_ref` continues
to name the admitted input. Existing augmentation disclosures link the added
effects and retain their classification, marking, evidence and comparability
requirements. Neither the attestation nor a collector's existence satisfies
an evidence-capture requirement.

Archive names and destinations are runtime-owned. Publication must be contained,
protected and immutable: a retry may reuse identical bytes, but MUST NOT
overwrite a different result under an existing identity. Publish verified bytes
before their durable accepted reference, retaining recovery information through
the incumbent operation commit and snapshot revision checks. Atomic file
publication is not a transaction with the operation store. Archival failure
MUST NOT claim completed reproducibility or cause automatic rematerialization;
valid cleanup inventory remains available. Returning a prior portable snapshot
does not itself roll back physical infrastructure.

The reference profile is `raes-sdl-materialized/v1`. `ref_path` is the
contained relative path `runs/<run-id>/attestations/<attestation-id>.sdl`;
the artifact URI is the inert `urn:sha256:<byte-checksum>` identity, not a host
path or fetch instruction. Associated-artifact validation binds explicitly
supplied bytes to that identity and to the materialized parent. Run records
carry these joins in `materialization_attestations`; disclosure references must
resolve to a record belonging to the same run.

This contract does not introduce a scenario-wide augmentation-permission
policy, continuous exhaustive host scanning, cryptographic producer proof or
automatic promotion of observations into author intent.
