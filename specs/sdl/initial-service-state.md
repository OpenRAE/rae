# Initial Service State

Status: **normative**.

This contract governs scenario content that must be established through a
named service rather than copied onto the service's node. It extends the
existing `content` declaration and `content-placement` lifecycle. It does not
define historical data, product adapters, event replay, or a second state
authority.

## 1. Authority

Top-level `content` is the sole authored authority for initial files,
directories, datasets, messages, records, and comparable data. The stable
authored identity is `content.<id>` in the instantiated scenario. Age,
represented business time, or a narrative about prior activity MUST NOT create
a different SDL object class.

Ordinary node placement remains the default. A content entry MAY carry
`service_materialization` only when establishing the required state through the
named service is materially different from node placement.

## 2. Service Materialization Binding

`service_materialization` is a closed discriminated profile. Every profile
shares the target, ownership, ordering, assertion, evidence, and observation
references below.

### 2.1 Owned Content Profile

The `service-content` version `"1"` profile is a closed object with these
fields:

| Field | Shape | Requirement |
|---|---|---|
| `target_service_ref` | exact named-service reference | REQUIRED |
| `interface_profile` | literal `service-content` | OPTIONAL; defaults to the literal |
| `profile_version` | literal `"1"` | OPTIONAL; defaults to the literal |
| `requirements.operation` | literal `ensure-owned-items` | REQUIRED |
| `requirements.conflict_policy` | literal `reject-unowned-collision` | REQUIRED |
| `requirements.readback` | literal `canonical-content-digest` | REQUIRED |
| `shared_service_relationship_ref` | relationship reference | OPTIONAL except for cross-tenant state |
| `ordering_content_refs` | unique content references | OPTIONAL; defaults empty |
| `readback_assertion_refs` | non-empty unique assertion references | REQUIRED |
| `evidence_requirement_refs` | non-empty unique evidence-requirement references | REQUIRED |
| `observation_boundary_refs` | non-empty unique participant-observation-boundary references | REQUIRED |

### 2.2 Search-Index Field-Schema Profile

The `service-search-index-schema` version `"1"` profile expresses schema-only
desired state for a service-owned search index:

| Field | Shape | Requirement |
|---|---|---|
| `interface_profile` | literal `service-search-index-schema` | REQUIRED discriminator |
| `profile_version` | literal `"1"` | OPTIONAL; defaults to the literal |
| `requirements.operation` | literal `ensure-search-index-field-schema` | REQUIRED |
| `requirements.conflict_policy` | literal `reject-unowned-collision` | REQUIRED |
| `requirements.readback` | literal `canonical-portable-field-schema-digest` | REQUIRED |
| `requirements.field_semantics` | non-empty portable field-name map | REQUIRED |

Every map value is one of:

- `exact-token`: equality or term matching without analysis or tokenization;
- `full-text`: analyzed or tokenized text search;
- `integer`: integral numeric comparison;
- `temporal`: date/time comparison through the backend's portable projection;
  or
- `boolean`: two-valued boolean comparison.

This profile uses `type: dataset` without `source` or `items`. It establishes
the exact portable semantic of every declared top-level field. Undeclared
native fields are outside the version 1 claim. A missing, ambiguous, or weaker
declared field fails reconciliation. Vendor literals, raw mappings, analyzers,
native index names, endpoints, queries, credentials, and arbitrary options are
not valid SDL.

`content.target` remains the owning compute node. `target_service_ref` MUST resolve
to an exact `nodes.<node>.services.<service>` declaration on that same compute node.
Every ordering reference MUST resolve to another content declaration;
self-dependency is invalid. Local deployment tenancy is derived from the
owning node and MUST NOT be redundantly authored in this binding.

Every readback assertion MUST be a postcondition over an observed-state
proposition for the exact content subject. Every bound evidence requirement
MUST be required by that proposition. Every observation boundary MUST expose
the exact content subject. These references define the portable observed
result and participant projection; neither planned state nor a backend success
response satisfies them.

Cross-tenant state requires `shared_service_relationship_ref`. That
relationship MUST be a typed `uses_shared_service` edge to the exact target
service and MUST assign mutable-state and reset-generation ownership under
ADR-087. The compiler derives consumer tenancy and ownership from this typed
relationship.

## 3. Compilation And Control

The binding compiles as the existing `content-placement` resource. Compilation
MUST retain:

- canonical content identity;
- exact service and owning-node addresses;
- interface profile, profile version, and exact operation requirements;
- canonical content digest;
- for the search-index profile, the portable field map and its separate RFC
  8785/JCS canonical field-schema digest;
- derived tenant ownership and the shared-service relationship reference;
- content ordering;
- readback assertion addresses; and
- evidence-requirement references;
- observation-boundary addresses.

The owning node and ordered content placements are provisioning dependencies.
No separate plan, lifecycle engine, scheduler, result store, or reset authority
is created.

The provisioner manifest capability terms `service-content-v1` and
`service-search-index-schema-v1` in
`supported_service_materialization_profiles` are independent of
`supported_content_types`. The latter claims the complete closed version 1
field-semantic set; partial support cannot advertise it. Admission requires the
content type, exact interface/profile version, exact requirements, a
recomputed digest, and profile-specific SEM-218 exact-requirement support. A
claimed profile also requires a realization-envelope
`content-placement` concern with `realized` disposition and at least
`daemon-observed` independent readback. Missing support is fatal before backend
I/O. Direct plan submission MUST repeat these checks.

## 4. Backend Conformance And Equivalence

RAES standardizes the portable profile without selecting a product or backend.
A backend MAY claim either standardized profile only when its own conformance
evidence demonstrates native materialization through the RAES control path,
fresh independent readback, reset ownership, and the declared participant
projection. For the search-index profile, native readback projects exactly the
declared field names back to the portable semantic set before digest comparison.
A mutation acknowledgement, returned desired-state snapshot, cached mapping, or
manifest claim is not execution evidence.

Two realizations are equivalent only with respect to the admitted portable
contract and declared participant-visible assertions/evidence. They need not
share provider resources, product adapters, deployment topology, bootstrap
mechanisms, native identifiers, or implementation code.

## 5. Non-Goals

This contract does not:

- classify content as historical;
- author native product identifiers, endpoints, commands, queries,
  credentials, or adapter options;
- prove product-native creation time or audit history;
- define an event sequence or replay trajectory;
- make runtime inventory authored authority; or
- permit an environment pack to define materialization control semantics.
