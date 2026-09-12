# Issue 985 Runtime-Configuration Realization Concerns Preflight

Correction recorded 2026-09-05: the aggregate weakest-child rule below records
the #985 behavior, not the intended mixed-constraint contract. For #1200,
[the corrective preflight](issue-1200-mixed-runtime-constraints-preflight.md)
requires binding leaves and collection membership to survive open siblings,
while inherited openness continues to delegate unspecified choices.

## Scope

Issue #985 extends the existing SEM-218 concern authority; it does not create a
second realization mechanism. The implementation should lower these authored
node-runtime dimensions as one concern per node and dimension:

| Authored path | Concern kind | Provisioning/snapshot payload path |
| --- | --- | --- |
| `nodes.<node>.runtime.environment` | `runtime-environment` | `spec.node.runtime.environment` |
| `nodes.<node>.runtime.mounts` | `runtime-mounts` | `spec.node.runtime.mounts` |
| `nodes.<node>.runtime.linux_capabilities` | `linux-capabilities` | `spec.node.runtime.linux_capabilities` |
| `nodes.<node>.runtime.network.published_ports` | `published-ports` | `spec.node.runtime.network.published_ports` |
| `nodes.<node>.runtime.forwarding_agents` | `forwarding-agents` | `spec.node.runtime.forwarding_agents` |
| `nodes.<node>.runtime.service_listeners` | `service-listeners` | `spec.node.runtime.service_listeners` |

The kind strings are backend-neutral realization vocabulary. They describe the
portable concern, not a Docker, Compose, Kubernetes, or libvirt operation.
Each requirement retains the existing aggregate explicitness classification for
its authored dimension. The classifier remains authoritative: an aggregate
containing a variable is constrained, and an aggregate containing an
`unknown`/`other` enum sentinel is open under the existing weakest-child rule.

`identity_authorities` and `operational_policy` are candidates, not part of
this issue's initial registry widening. Their identity/policy semantics and
secret-bearing children need a separate concern review before admission.
Health and readiness stay observed/evidence-only. Issue #761 removed authored
runtime health, ADR-043 keeps listener readiness as evidence, and `conditions`
owns authored health/readiness checks.

## Architecture Decisions

### Extend the canonical concern descriptor

`raes_processor.semantics.realization_concerns` remains the single registry.
Its descriptor must be able to express:

- a nested authored path suffix;
- the stable concern kind;
- the plan/snapshot payload path;
- a concern-specific canonical comparison projection; and
- where necessary, a bounded inclusion rule.

Registration, compilation, open-envelope path projection, admission, and
runtime disclosure must consume that same descriptor. Do not add parallel
kind/path tables in the compiler, planner, runtime adapter, conformance code, or
backends. `CompiledRealizationRequirement` remains model-side metadata and must
not enter `resource_payload()`.

The descriptor is the extensibility seam. Adding the next runtime dimension
should add one descriptor and its projection tests, without editing the
planner's explicitness dispatch or adding a backend-specific branch.

### Compare portable meaning, not serialized container accidents

Raw Python equality is insufficient for these aggregate concerns. A canonical
projection must:

- retain every field named by the issue's semantic contract;
- omit descriptions, evidence references, backend-native inspect data, and
  other non-realization annotations;
- order keyed collections by their existing stable identity
  (`name`, `target`, `forwarding_agent_id`, or `service_listener_id`);
- normalize set-like capability lists and option lists without weakening
  duplicates or contradictions already rejected by model validators;
- retain the complete published-port tuple
  `(host_ip, host_port, container_port, protocol)`;
- retain mount kind, source posture, target, filesystem type, read-only state,
  options, propagation, stability, and backend-generated posture; and
- retain capability `required`, `effective`, `add`, `drop`, and scoped process
  overrides rather than checking mere presence.

Canonicalization is comparison-only. It must not rewrite the authored plan or
backend snapshot, and it must not replace model or semantic validation.
Use the repository's RFC 8785/JCS helpers in `raes_contracts.canonical` for
commitments; do not add another JSON canonicalizer or digest format.

### Preserve the secret boundary

ADR-056 and `raes.runtime_values.enforce_observed_value_redaction` remain the
authoring/model authority. `redacted` and `operator_secret` members must omit
raw values. Forwarding enrollment posture remains a closed classification with
no raw identity field.

The runtime comparison projection must never place an environment or
forwarding-setting raw value in a snapshot, provenance entry, diagnostic,
audit event, log, fixture, or exception. Compare these records by stable
identity, provenance, classification, and a versioned, domain-separated
non-reversible commitment when a value is present. A backend must derive the
observed commitment from independent readback; echoing the planned commitment
is not readback evidence.

There is no declared value from which to derive equality for an
`operator_secret` or `redacted` member. For those classifications the gate can
enforce identity, provenance, classification, omission of raw material, and
presence posture, but must not claim value equality. A stronger claim requires
a separately governed secret-binding/verifier input; it must not be simulated
by hashing an empty string or by adding a raw secret field. Deliberate
`secret_fixture` content follows its existing authoring contract, but its
snapshot comparison still uses a commitment rather than redisclosing the
value.

The generic `SnapshotEntry.payload` contract currently accepts arbitrary
JSON-like dictionaries and the control-plane store/API copy them verbatim.
Therefore the backend-return boundary must validate the projected runtime
concern before persistence or API conversion. Authentication does not make
secret-bearing snapshot payloads acceptable.

### Keep mounts and persistent state separate

`persistent_volumes` is the sole portable stateful-volume desired-state
authority and already compiles to its own exact SEM-218 requirement and stable
resource address. The `runtime-mounts` concern covers non-stateful node-runtime
mount realization, specifically bind/tmpfs declarations. It must not reinterpret
`RuntimeMountSourceKind.VOLUME` as a `persistent_volume`, and it must not lower
the same `(node, target)` through both concerns.

The existing stateful-resource consumer/destination validation in
`raes._stateful_resource_references` remains authoritative. Semantic admission
must reject an authored runtime mount whose node/target is already owned by a
generated artifact or persistent volume. Backends must not satisfy a
`persistent-volume` requirement by returning a matching runtime mount.

### Keep adjacent meanings distinct

- `service-listeners` means in-node bind state; it is not `Node.services` and
  not host publication.
- `published-ports` means host/container exposure; it is not proof of listener
  ownership or readiness.
- `forwarding-agents` means the typed source/transform/target/buffer runtime
  family; it is not a generic service or relationship replacement.
- `linux-capabilities` is the authored effective/policy shape; it is not the
  backend's coarse “privileged” flag.
- SEM-218 requirement kinds are distinct from
  `raes_contracts.realization_envelope.RealizationConcern` observation-strength
  categories. Do not merge their vocabularies or registries.

## Canonical Incumbents

The implementation must build on:

- SDL shape and local validation: `raes._base.SDLModel`,
  `raes.runtime_configuration`, `raes.runtime_mounts`,
  `raes.runtime_capabilities`, `raes.runtime_network`,
  `raes.runtime_forwarding_agent`, `raes.runtime_listeners`, and
  `raes.runtime_values`;
- cross-model admission: `raes.validator.SemanticValidator`, especially
  `_runtime_services`, `_runtime_platform`, `_runtime_identity_data`, and the
  stateful-resource reference checks;
- author intent: `raes.explicitness`, `raes.realization_designation`,
  instantiation provenance, and concrete revalidation;
- compilation: `raes_processor.compiler.realization_requirements`,
  the existing node address helpers, `RuntimeModel.realization_requirements`,
  and `resource_payload()`;
- admission and open envelopes:
  `realization_support_diagnostics()`,
  `realization_envelope_diagnostics()`, and canonical
  `subsumes(offered, requested)`;
- manifest contracts: `RealizationSupportDeclaration`,
  `RealizationSupportDeclarationModel`, `BackendManifestV2Model`, manifest
  serializers, concept bindings, and backend manifest fixtures;
- execution and errors: `raes_runtime.backend_calls._call_backend_apply`,
  `realization_disclosure()`, `Diagnostic`, `ApplyResult`, and the existing
  `runtime.backend-contract-invalid` fail-closed path;
- observation and persistence: `RuntimeSnapshot`, `SnapshotEntry`,
  `RealizationProvenanceEntry`, `RuntimeSnapshotEnvelopeModel`,
  `_snapshot_payload()`, `_snapshot_from_payload()`, and `_snapshot_model()`;
- canonical commitments: `raes_contracts.canonical`;
- backend honesty/conformance: the existing realization-honesty and
  cross-backend conformance corpus, without replacing its independent
  observation-strength vocabulary; and
- repository workflow: `.ground-control.yaml`, `.gc/plan-rules.md`,
  generated-schema parity, schema-publication governance, repo policy,
  requirement governance, and `tools/verify_all.py`.

## Cross-Cutting Gates

- **Parser and closed-model gate.** Existing Pydantic fields, enum parsers,
  path/port validators, profile guards, duplicate checks, and
  `extra="forbid"` remain authoritative. The registry consumes validated
  models; it does not parse YAML or accept free-form concern payloads.
- **Semantic validation gate.** Existing service/listener/published-port,
  process, forwarding-target, and identity references must resolve before
  compilation. Add only the missing runtime-mount/stateful-destination
  exclusivity rule; do not duplicate local validators in the compiler.
- **Instantiation gate.** Preserve `model_fields_set`, explicitness, parameter
  provenance, scoped realization designation, and concrete revalidation. Do
  not infer explicitness from a serialized payload.
- **Manifest/config gate.** New kind strings flow through the existing
  `supported_constraint_kinds`, exact `declared-capability-match`,
  `open-realization`, disclosure-kind, concept-binding, and backend-manifest-v2
  validation surfaces. Do not add per-dimension booleans or a new manifest.
- **Envelope gate.** Open nested runtime paths use the existing
  `RealizationEnvelopeModel` tokenization and subsumption relation. The
  descriptor supplies the authored field path; it must not invent an envelope
  dialect.
- **Backend-return gate.** `_call_backend_apply()` remains the only acceptance
  point. Omission or mismatch of an exact projected concern yields the existing
  sanitized `runtime.backend-contract-invalid` diagnostic and restores the
  baseline snapshot.
- **Persistence/schema gate.** Accepted snapshots must round-trip through the
  existing store and `RuntimeSnapshotEnvelopeModel`. If a portable commitment
  carrier changes a published schema, update the hand-governed schema,
  `schema_bundle()`, fixtures, publication manifest ledger, and generated
  parity together. Do not use `metadata`, `details`, or a sidecar store.
- **Authentication/authorization gate.** Snapshot reads continue through
  `ControlPlaneSecurityConfig`, verified identity/bearer authentication,
  backend/operator/auditor role checks, target binding, request-size guards,
  and audit recording. No new endpoint or unauthenticated read path is needed.
- **Error-envelope gate.** Diagnostics may name only address, authored field
  path, concern kind, and the coarse mismatch/omission reason. Existing backend
  exception reduction and the redacted HTTP 500 envelope remain in force; no
  raw payload, value, commitment input, native exception text, or traceback may
  be rendered.
- **Host/OS exposure gate.** Registry/compiler work performs no subprocess or
  environment lookup. Backend follow-up must not pass environment values,
  enrollment material, tokens, or mount secrets in process argv. Use the
  backend's existing fixed-argv, no-shell runner and a bounded protected input
  channel when materialization needs secret input.

## Gotchas And Anti-Patterns

Avoid:

- adding only `CONCERN_PAYLOAD_PATH` entries and relying on raw equality;
- comparing list order instead of portable keyed/set semantics;
- hashing an entire raw record, which can preserve accidental descriptions,
  evidence refs, or backend-native data as realization meaning;
- treating a plain SHA-256 of a low-entropy operator secret as a safe verifier;
- echoing plan payloads or commitments into the snapshot as “independent”
  readback;
- recording commitments in `realization_provenance`, whose contract deliberately
  carries no realized value;
- weakening an exact aggregate because one backend can realize only some
  members;
- treating exact support for one runtime concern as support for all six;
- duplicating classifier, support, envelope, exception, persistence, logging,
  or conformance workflows;
- conflating runtime listeners, host-published ports, service declarations,
  readiness evidence, and realization-envelope observation categories; or
- widening stub/reference/libvirt manifests merely to keep existing scenarios
  green. A backend should claim a new kind only when it can materialize and
  independently observe the complete canonical projection.

## Non-Goals And Boundaries

- No issue implementation is performed by this preflight.
- No new SDL runtime fields, top-level sections, parser, exception hierarchy,
  persistence store, API endpoint, logging stack, or backend-specific dialect.
- No readiness/health realization concern.
- No initial lowering of `identity_authorities`, `operational_policy`, other
  `RuntimeConfiguration` families, or scenario-level forwarding agents.
- No redesign of `dynamic-composition`, artifact mechanisms, realization
  envelopes, observation-strength conformance, or backend capability profiles.
- No claim that runtime disclosure alone proves independent observation;
  backend conformance/evidence remains responsible for that stronger claim.
- No raw operator-secret equality claim without a separately governed
  secret-binding/verifier contract.
