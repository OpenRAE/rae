# ADR-043: Generic Runtime Service Listener Surface

## Status

accepted

## Date

2026-05-29

## Context

Issue #431 identifies an SDL expressivity gap for observed generic runtime
listeners. ACES can declare a node transport service through `Node.services`,
and it can record host/container publication through
`runtime.network.published_ports`, but neither surface owns the bind endpoint
of the process inside the node namespace.

The motivating MISP inventory needs to preserve these facts without hiding
them in prose:

- nginx listens on `0.0.0.0:80`, `[::]:80`, `0.0.0.0:443`, and `[::]:443`
- supervisord listens on `127.0.0.1:9001`
- a local runtime listener exists on `127.0.0.1:50000`
- Docker embedded DNS listens on `127.0.0.11:53`

Adjacent ACES surfaces already have narrower jobs:

- `Node.services` declares authored service identity by port, protocol, and
  optional name.
- `runtime.network.published_ports` records host-published bindings, not the
  process bind address inside the node.
- `runtime.applications`, `runtime.database_services`, `runtime.dns_services`,
  `runtime.mail_services`, `runtime.security_monitoring_managers`, and
  `runtime.file_services` own protocol or domain-specific logical inventory.
- `runtime.processes` records process identity and command posture, not socket
  endpoint facts.
- `runtime.local_control_interfaces` owns path-local control APIs such as Unix
  sockets and named pipes, not generic TCP/UDP listener state.

Prior art points in the same direction. osquery's `listening_ports` separates
address, port, protocol, and owning PID. Docker distinguishes container
listeners from published host ports. Kubernetes keeps container ports,
Services, EndpointSlices, and probes as separate concerns. systemd socket units
bind socket addresses and can activate services. Nmap scan output can observe
remote port state and service hints, but it cannot prove the local bind
address or owning process. OpenTelemetry distinguishes server address/port
attributes from transport/protocol telemetry. OCSF network endpoint objects
provide vendor-neutral endpoint vocabulary, but ACES should not import OCSF
events as SDL runtime inventory.

The design risk is to overload `Node.services` or `published_ports` until
authored service intent, in-node listener state, and host exposure all mean the
same thing.

## Decision

### 1. Model generic service listeners under node runtime

Add `Node.runtime.service_listeners` as optional observed runtime inventory.
Each listener has a stable `listener_id` and may carry transport protocol, port
or Unix socket path, bind address and/or interface, address family, listener
scope, optional same-node service reference, optional process owner reference,
typed published-port correlation refs, readiness/probe evidence, provenance,
and evidence refs. The inventory admits truthful partial descriptions; stable
identity does not imply that a complete bind endpoint has been observed or
selected.

The owning node is implicit from the enclosing node. The surface is observed
runtime state; it must not mutate `Node.services`, `runtime.network`, source
image metadata, infrastructure topology, or host publication records.

### 2. Preserve the three adjacent meanings

The implementation keeps these concepts distinct:

- `Node.services[]`: authored or curated service identity.
- `runtime.service_listeners[]`: observed listener state inside the node
  namespace.
- `runtime.network.published_ports[]`: host/container publication mapping.

A listener may reference a same-node `Node.services[].name`. When it does, and
both sides have concrete values, the listener port/protocol must match the
service. A listener may also correlate to `published_ports[]` through a typed
tuple because `RuntimePublishedPort` does not have stable ids. Absence of a
published port does not invalidate an in-node listener.

### 3. Validate scope without inferring host exposure

Listener scope is explicit. `wildcard`, `loopback_only`, `network_facing`,
`node_local`, `local_socket`, `unknown`, and `other` classify the bind endpoint
inside the node namespace. The model rejects obvious contradictions, such as
`network_facing` on `127.0.0.1`, `loopback_only` on a non-loopback concrete IP,
or Unix socket listeners with a TCP/UDP port.

A container listener on `0.0.0.0` is a wildcard in the container or node
namespace. It is not automatically host-public. Host exposure remains the job
of `runtime.network.published_ports`.

### 4. Publish qualified runtime refs with matching composition aliases

Generic service listeners may be referenced through qualified refs:

`nodes.<node>.runtime.service_listeners.<listener_id>`

Named-reference validation and module-import alias rewriting recognize that
shape so relationships and composed scenarios cannot silently point at stale
or un-namespaced listener records.

### 5. Separate description validity from complete endpoint admission

Base listener validation rejects contradictions in supplied facts, not missing
knowledge. Port bounds, stable identity, duplicate rejection, incompatible
supplied Unix/network shapes, concrete address-family/scope contradictions, and
concrete reference integrity remain binding. A partial TCP listener need not
name an address or interface, a partial Unix listener need not name its socket
path, and an unknown, other, variable, or governed private transport must not be
classified as a network endpoint merely because it is not the core `unix`
token.

Missing, explicitly empty, unknown, and concrete values remain distinct.
Source-preserving serialization uses field presence and does not materialize an
omitted field. For compatibility, the historical omitted `protocol` default is
still `tcp` in an instantiated artifact; instantiation provenance and recursive
constraint origin must retain that it was a default rather than an authored or
observed fact. An instantiated default must not erase an exact authored child,
close an inherited open scope, or become evidence that TCP was observed.

An inherited open scope may let an admitted backend select an omitted bind
choice while every supplied descendant, such as an exact port, remains binding.
When an operation or coverage-qualified effective-listener claim truly requires
a complete endpoint, enforce that requirement at the existing owner: recursive
realization authority plus backend preparation and the backend's installed
`validate` semantics before apply, or coverage-aware description assessment for
a complete report. The canonical `service-listeners` observed validator remains
a shape, contradiction, and safe-projection gate; partial observations must not
be rejected merely for being partial. Do not put an operational precondition
back into general SDL parsing. A partial record grants no socket access,
service authority, host publication, observation, retention, or export.

## Security and Validation Gates

- Parser/model gate: listener ids are concrete stable symbols, not mapping keys
  or `${var}` placeholders.
- SDL model gate: duplicate listener ids in a node runtime block are rejected.
- Shape gate: partial descriptions may omit endpoint fields. Supplied
  Unix/network fields must remain mutually compatible; port bounds and field
  shapes remain enforced.
- Scope gate: concrete IP/socket facts must not contradict address family or
  listener scope.
- Semantic validation gate: same-node service refs resolve and supplied known
  service/listener port+protocol values match. Missing or unknown listener
  values defer agreement; a governed private identity is concrete and binding.
- Process-reference gate: `process_ref` resolves to a same-node runtime process
  name or PID when set.
- Published-port correlation gate: `published_port_refs[]` entries resolve to
  `runtime.network.published_ports[]`; they match supplied known listener
  container-side port/protocol facts without inventing omitted ones.
- Realization/admission gate: reuse recursive realization constraints,
  `service-listeners` projection, selected backend preparation, installed
  backend validation, and coverage-aware effective-observation assessment.
  Shape admission alone never proves endpoint completeness, and partial
  coverage remains valid without satisfying a complete-report claim.
- Contract/schema gate: published JSON Schemas under `contracts/schemas/` are
  the governed authority. Keep the reference model/schema bundle identical and
  update only affected schema-publication records when the contract changes.
- Evidence gate: readiness probes, process names, scanner outputs, and native
  payloads remain evidence or bounded text. Do not store credentials, bearer
  tokens, raw secret probe headers, or raw backend inspect blobs in this
  surface.

## Guardrails

- Do not put bind addresses or listener scope only in `description`.
- Do not extend `Node.services` with observed bind semantics.
- Do not treat host-published ports as proof of in-node process bind state.
- Do not infer host-public exposure from a wildcard address inside a container.
- Do not treat Nmap output alone as proof of local bind address or owning
  process.
- Do not treat omission, an empty value, `unknown`, a variable, and a governed
  private identity as interchangeable.
- Do not replace an omitted bind with `0.0.0.0`, `::`, a port, interface,
  socket path, or a compulsory profile/catalog entry.
- Do not make parser acceptance satisfy a selected operation's endpoint,
  access, publication, or verification prerequisites.
- Do not make uniqueness only `(protocol, port)`: IPv4/IPv6, wildcard,
  loopback, interface-specific, and Unix socket listeners can coexist.
- Do not add backend-specific raw Docker, Kubernetes, systemd, scanner, or
  OCSF payloads as the portable SDL schema.

## Non-Goals

- Building Docker, Kubernetes, systemd, osquery, Nmap, or OpenTelemetry capture
  adapters.
- Replacing protocol-specific runtime inventories such as DNS, mail, database,
  HTTP application, file service, or security-monitoring manager state.
- Redesigning process inventory, host firewall policy, published-port
  semantics, runtime snapshots, control-plane APIs, persistence, logging, or
  workflow semantics.
- Loosening `RuntimeSshServer.service`. ADR-031 deliberately models an sshd
  daemon-policy record bound to an owning same-node service, not a generic
  partial endpoint observation; broader partial SSH authoring requires its own
  contract decision.
- Adding a listener profile catalog, backend capture adapter, automatic socket
  probe, or new observation/retention/export demand.
- Requiring existing inventories that only use `Node.services[]` to change.

## Consequences

### Positive

- ACES can encode generic TCP/UDP/SCTP and Unix-socket listener facts without
  free-text-only semantics.
- Sparse listener knowledge can round-trip without fabricated endpoint facts,
  while selected complete endpoints remain subject to operation-specific
  admission.
- Local-only, wildcard, network-facing, and node-local listeners are
  distinguishable.
- APTL's MISP inventory can record the nginx, supervisord, local runtime, and
  Docker DNS listener facts directly.
- Service, process, and published-port relationships are validation-backed
  while preserving their separate meanings.

### Negative

- Node runtime gains another optional inventory list.
- Consumers that need full backend-native socket, namespace, or probe detail
  still need separate evidence artifacts.

### Risks

- Downstream consumers may overread `wildcard` as host-public exposure; the
  docs and validators keep that distinction explicit.
- Scanner-only evidence can misidentify owner or bind state; provenance and
  evidence refs must remain visible.
- A future protocol-specific surface should not duplicate generic listener
  semantics when a service ref is enough.

## References

- [Lineage and Prior Work](../../explain/sdl/lineage.md) and
  [Design Precedents](../../explain/sdl/precedents.md).
- [osquery `listening_ports` table](https://fleetdm.com/tables/listening_ports).
- [Docker port publishing](https://docs.docker.com/get-started/docker-concepts/running-containers/publishing-ports/).
- [Kubernetes Services](https://kubernetes.io/docs/concepts/services-networking/service/),
  [EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/),
  and
  [container probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/).
- [systemd.socket](https://www.freedesktop.org/software/systemd/man/latest/systemd.socket.html).
- [Nmap XML output](https://nmap.org/book/output-formats-xml-output.html).
- [OpenTelemetry semantic conventions for attributes](https://opentelemetry.io/docs/specs/semconv/attributes-registry/server/).
- [Open Cybersecurity Schema Framework](https://schema.ocsf.io/).

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-09-17 | #1299 | Separated partial listener descriptions from complete endpoint admission, preserved presence/default provenance, and retained the narrower ADR-031 SSH service binding. |
