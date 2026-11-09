# Authored identity-domain topology

Status: **normative**. This specification defines the SDL realization-intent
surface established by
[ADR-082](../../docs/decisions/adrs/adr-082-authored-identity-domain-topology.md).
It is distinct from the observed runtime directory identity inventory governed
by ADR-032.

## 1. Domain declarations

`identity_domains` is an optional map keyed by a portable SDL identifier. Each
value is an `IdentityDomain` with these required fields:

| Field | Meaning |
| --- | --- |
| `profile` | Closed realization profile. The initial standard value is `active_directory`. |
| `dns_name` | Concrete DNS domain name, or a whole-field variable before instantiation. |
| `netbios_name` | Concrete NetBIOS domain name of at most 15 characters, or a whole-field variable before instantiation. |
| `authority_account_ref` | Reference to the account authorized as the domain authority principal. |

DNS and NetBIOS values MUST satisfy their structural name constraints after
instantiation. Domain declarations contain no password, credential source,
backend endpoint, or provider resolver configuration.

## 2. Typed topology relationships

A controller role is a relationship with:

```yaml
type: domain_controller_for
source: <compute-node-ref>
target: <identity-domain-ref>
domain_controller: {}
```

A member join is a relationship with:

```yaml
type: joins_domain
source: <compute-node-ref>
target: <identity-domain-ref>
domain_join:
  controller_refs: [<compute-node-ref>, ...]
```

`controller_refs` is ordered, non-empty, and duplicate-free. Every candidate
MUST be a controller for the relationship's target domain. A topology
relationship's type and typed detail MUST agree; generic `properties` do not
carry controller or membership authority.

## 3. Account bindings

`accounts.*.domain_ref` explicitly binds an account to an identity domain. The
account's target node MUST be a controller or member of that domain. An account
with a non-empty `spn` MUST declare `domain_ref`; an implementation MUST NOT
derive the domain from the SPN, username, node operating system, or account
name.

The `authority_account_ref` on a domain is also an explicit domain binding. It
MUST resolve to an account placed on one of that domain's controller nodes.

## 4. Active directory invariants

For the initial `active_directory` profile, semantic validation MUST reject:

- a domain with no controller;
- a controller or member edge whose source is not a compute node;
- duplicate controller or member facts;
- a node that both controls and joins the same domain;
- a node belonging to more than one Active Directory domain;
- a member whose selected controller does not control the same domain;
- an authority account outside the domain's controllers;
- a domain-bound account outside the domain; and
- an SPN-bearing account without explicit `domain_ref`.

Unresolved whole-field variables defer the affected cross-reference check until
instantiation. The instantiated scenario MUST satisfy every invariant.

## 5. Composition and references

Module composition namespaces domain keys and rewrites all topology-bearing
references: account `domain_ref`, domain `authority_account_ref`, relationship
endpoints, and `domain_join.controller_refs`. Bare and section-qualified
references follow the resolution rules in [references.md](references.md).

## 6. Compiled realization contract

Each participating node and domain-bound account compiles to a
`DomainTopologyBinding` containing:

- the normalized domain identifier and profile;
- DNS and NetBIOS names;
- the canonical authority account address;
- the node role (`controller` or `member`); and
- canonical, ordered controller addresses.

These bindings are normalized topology context and exact readback carriers.
They are not, by themselves, an instruction to bootstrap a controller.

Each `domain_controller_for` node/domain fact MUST additionally compile to one
`domain-controller-placement` provisioning resource. The placement MUST target
that controller node and carry the same `DomainTopologyBinding`; it MUST NOT
copy the domain into a second payload shape. The placement is the portable
instruction to establish the controller role and MUST order after its target
node.

Member node resources MUST order after the selected controllers' placement
resources. Every account placement bound to the domain, including the logical
authority account, MUST order after the domain's controller placements as well
as its own target node. This preserves bootstrap order without making the
controller placement depend on an account that cannot exist until the domain
is established. Reverse deletion therefore removes domain accounts and members
before their controller placement and node.

The same normalized binding MUST appear on a placement and its target
controller node, and on a domain-bound account placement and its target node.

Provisioners declare supported profiles through
`capabilities.provisioner.supported_domain_profiles`. Generic account or SPN
support does not satisfy this capability. Planning and direct provisioning
admission MUST validate the effective graph across resources, non-delete
operations, and admitted snapshot entries before invoking a backend.

## 7. Realization and evidence

Every topology carrier, including `domain-controller-placement`, is an exact
`domain-topology` realization requirement under SEM-218. A returned snapshot
MUST preserve the whole normalized binding. Omission or a different binding is
silent approximation and MUST be rejected as a backend-contract error.

This readback proves carrier fidelity, not successful controller promotion or
guest domain membership. Those claims require explicit backend or guest
evidence from a separately defined realization mechanism.
