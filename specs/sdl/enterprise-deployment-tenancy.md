# Enterprise identity and deployment tenancy

This extension adds portable authoring intent for enterprise forests, identity
facades, endpoint personas, deployment tenants and cells, carrier placement,
and shared multi-tenant services. It does not add provider allocation,
credentials, mapper configuration, runtime identity inventory, or proof that a
realizer established the declared state.

## Identity

`identity_forests` is keyed by stable SDL identity. Each forest declares one
`root_domain_ref` and a non-empty complete `domain_refs` list. Those references
reuse `identity_domains`; a forest does not redeclare DNS, NetBIOS, controller,
join, or account facts. When forest authoring is present, every authored
identity domain belongs to exactly one forest and the explicit root is one of
that forest's members.

`identity_facades` identifies an existing named compute service that exposes a
closed protocol, initially `oidc`. The facade is authored intent and remains
separate from observed `Node.runtime.identity_authorities`.

The specialized `forest_trusts` relationship connects two distinct forests and
carries `forest_trust.trust_type` plus direction. The specialized
`directory_federates_to` relationship connects one authored domain or forest
to one facade. Its `identity_federation` detail declares only direction,
portable protocol, group/role mapping intent, and facade ownership of a named
server-controlled tenant claim. It cannot carry claim values, credentials,
client configuration, or provider mapper documents.

## Endpoints and cells

`Node.endpoint_persona` is a closed scenario-function classification:
`workforce`, `engineering`, `privileged_admin`, `participant`, `service`, or
`carrier`. It is valid only for compute nodes and is independent of node login
`roles`, participant agents, accounts, authorization, and operating system.

`deployment_tenants` declares portable tenant identity. `deployment_cells`
binds one tenant to a non-empty set of nodes and the `default_deny`
cross-tenant isolation posture. When cells are present, every compute node belongs to
exactly one cell. Cells do not carry cloud projects, regions, quotas,
subnets, provider resource names, or capacity policy.

The specialized `placed_on_carrier` relationship preserves both endpoint
identities while declaring that one compute node is realized on another compute node with either a
`shared_kernel` or `separate_kernel` boundary. A source has one carrier; the
target has the `carrier` persona; placement is same-cell, non-self,
non-nested, and acyclic. Placement does not imply sharing any network, PID,
mount, IPC, UTS, user, or cgroup namespace.

## Shared services

The specialized `uses_shared_service` relationship connects one deployment
tenant to an existing named compute service. Its `shared_service` detail keeps four
axes independent:

- tenant isolation: `none`, `stateless`, or `tenant_partitioned`;
- workload authentication: `none`, `shared_credential`,
  `workload_identity`, or `tenant_scoped_workload_identity`;
- mutable state references and owner: `none`, `consumer_tenant`, or
  `shared_service`; and
- reset-generation owner using the same ownership vocabulary.

Cross-tenant use requires `stateless` or `tenant_partitioned` isolation and
tenant-scoped workload identity. Mutable state references resolve to existing
`persistent_volumes`. Ownership must agree with those volumes' consumers,
state cannot receive conflicting owners, and reset ownership follows mutable
state ownership. `stateless` forbids shared-service-owned state;
`tenant_partitioned` requires shared-service-owned state and reset generation.
An ordinary relationship can connect a node or named service in one cell to a named service in another cell.
Admission requires an explicit `uses_shared_service` binding from the caller's tenant to that exact target service. Identity,
topology, placement, and generic infrastructure edges never grant that access.

## Composition and realization boundary

All declaration and relationship references use the canonical section symbol
maps. Module composition namespaces them before merge and instantiated
admission reruns every invariant after variable substitution.

The instantiated scenario is the authored authority. Compiler node specs and
relationship metadata preserve these declarations, but this contract does not
create provider-policy plan resources or claim realization support. A
domain-controller bootstrap resource remains governed separately, and carrier
placement is not a substitute for network-namespace sharing.
