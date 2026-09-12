# Backend realization preparation

`backend-realization-preparation-v1` is an opt-in, read-only selection protocol.
It is separate from ADR-070's universal `subsumes(B, R)` relation. A preparation
response proposes **one jointly supported completion** of the submitted request;
it neither establishes universal coverage nor observes successful delivery.

The normative response shape is
[`backend-realization-preparation-v1.json`](../../contracts/schemas/plans/backend-realization-preparation-v1.json).
Its input reuses the provisioning-plan and runtime-snapshot contracts. No new
author installation recipe or catalog of complete manifest offers is required.

## Negotiation and binding

A backend MUST advertise the preparation contract and expose a callable
`prepare(plan, snapshot)` alongside its existing `validate(plan)` and
`apply(plan, snapshot)` methods. A legacy backend that does not advertise it
retains its existing validation and universal-envelope admission contract.
Advertising preparation does not authorize a backend to omit other selected
support, policy, profile, or observation obligations.

The planner seals `preparation.contract_id` and the canonical digest of the
complete selected backend manifest into the original provisioning plan. The
ordinary authenticated planner-plan commitment covers these fields. The
manifest commitment includes the realization envelope and its configuration
identity. A digest alone does not grant execution authority.

The runtime binds an operation identity before preparation. The response MUST
echo the domain-tagged digest of that exact plan and the canonical digest of the
immediate portable predecessor. A response for another request, operation,
manifest/configuration, or predecessor MUST fail before apply. Preparation
receives isolated value carriers; this prevents ordinary aliasing mistakes, not
hostile in-process code or external configuration races.

## Selection before mutation

Preparation MUST NOT mutate resources, collect observation data, resolve ambient
secrets, or publish state. It may use the selected backend's configured support
and existing supplied predecessor to choose values. It returns a closed response
with a boolean success claim, bounded diagnostics and provisioning operations.
Unknown fields, invalid identities/actions, duplicate operation addresses,
invalid or excessive payloads, and invalid diagnostic carriers are rejected.
Work bounds apply to the complete proposal and predecessor, before recursive
copying or serialization; individually bounded entries do not exempt the
aggregate. The input and authority commitments must identify the same submitted
operation even when the caller supplies detached value copies.
Portable apply and validation inputs are bounded before isolation or hashing.
The runtime budget includes a total scalar-byte limit, not just per-value sizes.
Native value arguments and supplemental realization requirements are included;
injected service dependencies are not traversed as portable values. Invalid
Unicode is a rejected input, not an escaping serialization error.

The runtime admits the completion against the original authority before invoking
apply. This includes recursive exact descendants, domains, local closure,
presence, identity and dependency rules; static non-realization control values
cannot be rewritten as delegated choices. Backend envelope membership includes
closed record and ancestor scopes, not only independently matching leaf domains.
For typed concerns, default-presence rules are recovered through the existing
concern validator and shared envelope engine. Serialized defaults do not become
extra realizable dimensions. Domain checks still use the safe supplied values;
reconstructed placeholders for committed material are never treated as observed
values. A finite-domain template is one allowed member, not a requirement to
select that same member.
Public typed runtime scalar domains are retained from whole-field finite
variables through instantiation and lowered at their original source pointers.
The recursive document owns those nested domains; it does not need a second
editable flat bound list. Classification- or sensitivity-governed records are
not a source of raw alternate values in phase provenance: a domain that cannot
be represented by its safe owning projection is rejected before execution.
An exact scalar creates no otherwise unnecessary collection-default decision.
Specialized runtime collections retain their owning comparison policy through
recursive carriage. Mount targets, published host endpoints, forwarding and
listener IDs, and compound process-limit selector identities remain distinct
from inventory order. Capability and mount-option sets use comparison-only
scalar records; finite scalar and record-key choices carry bounded collision-free identity aliases
while actual selected values remain independently constrained. These records
do not change native persistence shapes. Ambiguous identities fail closed.
An operating-system choice must match a compatible configured row; mixing the
family from one row with the distribution or version from another is invalid.
Unknown support is not an executable completion.
Optional extension constraints use the explicitly negotiated
[plan-level profile host](plan-realization-profiles.md), independently pinned
target support and an installed semantic validator over the selected joint plan.
Portable compute-substrate constraints require non-delete node operations and
the selected backend manifest; stale or mistargeted constraints do not authorize
a backend call.

The backend's ordinary `validate` method receives the admitted concrete plan
before `apply`. For this negotiated contract it is not required to validate the
unselected template as though all choices were already concrete. A rejected
proposal or failed validation MUST NOT reach apply. Preparation failure is
reported without exposing candidate values or backend exception text.
Valid preparation and validation warnings remain in the apply result. Existing
credential-bearing diagnostic redaction still applies to those warnings.

An empty authored operation list does not exempt a conditional plan from
planner authorization or mandatory-observation/mutation atomicity admission.
Preparation does not itself grant authority for new portable resource members:
such additions require an independently admitted enclosing collection, including
its universe, identity, cardinality, domain and dependency rules.

## Prepared portable membership

`preparation.node_collection` carries the authenticated enclosing `/nodes`
authority using the `raes/portable-node-membership/v1` semantic profile. Its
single recursive document partitions qualified names by composition namespace.
The namespace inventory is closed; each namespace contains a keyed portable-node
collection, identified by canonical compiled address. Its closure is resolved
from the enclosing designation, independently of any child node's openness.
An open root does not override a closed imported collection or create a new
module namespace. Unresolved apparatus policy is not a positive addition grant.

Membership projects only address, resource type and qualified name. Authored
members remain required and exact. Payloads are not manifest recipes. Before
the read-only callback, the runtime verifies the binding between this document
and the submitted membership. Preparation MUST declare every additional portable
node or network operation before apply. Internal implementation details that do
not become portable members do not acquire portable resource identities.

Admission uses existing node/infrastructure types, reference dependencies,
ordering-cycle analysis, configured capability and concern support, artifact
availability, and joint offer membership. Retained additions are included when
checking total capacity and changed backend support. Unknown counts, unavailable
references and unsupported choices fail before apply. Collection membership
does not independently grant participant roles, feature/control bindings or
identity-domain membership.
The existing semantic validator checks the selected portable node context,
including node-local services, network references, package architecture and
unresolved variables. Existing generated-artifact and persistent-volume codecs
recover their native validation shapes. A node cannot add a generated-artifact
delivery consumer without the artifact's own admitted delivery authority.

Added-node choices use the existing safe concern projections and shared recursive
relation, with backend origin rather than fabricated author provenance. Apply
must deliver that admitted projection; later selection changes and unprepared
members are rejected. Replanning an open collection preserves admitted extra
nodes by omission, without granting permission to modify them. Preparation may
propose explicit updates or deletions within the same enclosing authority. A
closed collection schedules absent members for deletion; explicit runtime
teardown deletes the complete trusted portable inventory, including additions.

## Delivery and publication

Apply consumes the admitted completion. Its successful result must still satisfy
the original recursive authority and deliver the selected values. A different
allowed value is not interchangeable with the supported completion admitted for
this operation. This exact-completion comparison uses the authenticated recursive
projection: ordered positions remain distinct even when their allowed domains
overlap. Existing set-like concern identities remain order-independent.
Available operating-system observations are compared with that
completion as well as with the original author constraint. Independently
applicable observation scope, strength and corroboration floors remain binding.

Selection is a `backend-selected` basis, not guest or independently observed
evidence. Exact detail and preparation create no experimental collection,
retention or export demand. Requested descriptions remain subject to the
existing demand, disclosure and information-flow owners.

The existing runtime result boundary checks shape, authorized transitions,
identity, honest change accounting and specialized carrier owners before lossy
sanitization. Safe projections preserve ordered sequences and the meaning of
set-like collections. Credential egress is validated against the admitted
completion before native concern sanitization. Sanitization failure retains its
own invariant diagnostic instead of being reinterpreted as failed delivery. The sanitized
candidate is checked again against the same constraints and already-admitted
transient observations before runtime-owned provenance and durable publication;
this second check does not collect or retain observations. Native participant
result types are retained. Stateful service dependencies remain injected services,
not cloned value carriers. Non-provisioning calls cannot replace realization
envelopes or realization observations.
A rejected successful claim returns the immediate trusted predecessor with no
candidate details, changed addresses or success provenance. Honest, valid partial
failure cleanup remains distinct from a rejected successful claim.

This protocol does not certify backend honesty, roll back infrastructure,
contain malicious backend code, promise exactly-once execution or authorize
automatic apply replay. Publication still uses the existing durable revision
and history-head checks.
