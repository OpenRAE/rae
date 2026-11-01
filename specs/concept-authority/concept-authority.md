# Concept Authority

## Scope

This specification defines the canonical concept authority for cyber-domain
concepts used across RAES SDL, manifests, contracts, provenance, reporting,
and related ecosystem artifacts.

It establishes what concept families exist, where their meaning comes from,
and how the ecosystem distinguishes imported meaning from native extensions.

## Decision Record

[ADR-012](../../docs/decisions/adrs/adr-012-shared-concept-authority-and-raes-extension-discipline.md)
is the architectural decision that governs this specification.

## Layer Model

The shared concept model has three layers.

### 1. Concept Authority Layer

Defines what relevant cyber-domain concepts mean.

UCO (Unified Cyber Ontology) is the semantic authority for cyber-domain
concept families. This is a concept-authority relationship, not an
authoring-syntax or schema-structure requirement.

The fidelity of this concept-authority relationship is recorded in the
machine-checkable UCO alignment artifact
`contracts/concept-authority/uco-alignment-v1.json` (schema `uco-alignment/v1`).
It pins the reviewed UCO version and maps every adopted and adapted cyber-domain
family to the UCO object types it aligns to, stating each adapted family's
divergences explicitly so the alignment can be reviewed rather than assumed.

### 2. RAES Concept Layer

Defines concepts that RAES needs beyond the cyber-domain authority. These
are RAES-native extensions for experiment, runtime, apparatus, provenance,
and governance concerns.

### 3. Artifact Binding Layer

Where SDL, manifests, contracts, provenance, and reports bind their declared
meaning to canonical concepts. This layer prevents artifact-local strings
from becoming de facto semantics.

Native apparatus vocabulary-to-family bindings and authored external concept
assertions are distinct surfaces. Portable assertions relating an exact RAES
subject to a concept in an arbitrary versioned scheme are governed by
[Portable External Concept Bindings](./external-concept-bindings.md). They
complement native manifest `ConceptBinding` entries without changing their
scope or authority.

[Semantic Projection Reports](./semantic-projection-reports.md) define the
separate reporting surface that groups governed native predicate results by
those external concepts. The projection frame preserves native authority,
explicit denominators, evidence boundaries, ambiguity, and information-flow
controls; it never turns an external classification into runtime truth.

[Autonomous Behavior Vocabulary Bindings](./autonomous-behavior-vocabularies.md)
apply that portable surface to exact participant behavior specifications using
pinned ActivityStreams and FIPA sources. The external identifiers remain
descriptive assertions; they are not new native concept families or SDL
vocabularies.

## Surface

A **surface** is a named, bounded, contract-bearing scope of an RAES artifact
or apparatus — owned by a single declaring authority — across which concept
bindings, governed vocabularies, and conformance rules apply. "Surface" is the
ecosystem's central organizing term: authoring (the SDL surface), processing
and contracts (the contract, control-plane, and runtime surfaces), the
apparatus (processor, backend, participant, live-execution, evidence, and
provenance surfaces), and authority itself (normative-prose, schema, and
governance-guidance surfaces) are all surfaces in this sense. A surface is not a
file, a package, an endpoint, a schema, or a concept family; any of those may
carry, realize, or sit within a surface, but the surface is the governed scope,
not its container.

A surface has three defining properties:

- **Named and bounded** — it has an identity and an explicit edge; a fact is
  either inside it or outside it.
- **Singly owned** — exactly one declaring authority owns the meaning on the
  surface, so artifact-local strings cannot become de facto semantics (the
  Artifact Binding Layer above is where surfaces bind to canonical concepts).
- **Contract-bearing** — the surface is the unit against which conformance,
  parity, and governed vocabularies are defined.

### One Surface Versus Two

When two facts arise, the inventory program decides whether they belong to one
surface or two using a single rule established by
[ADR-033](../../docs/decisions/adrs/adr-033-scenario-delivery-boundary-for-runtime-node-state.md):

- Two facts belong to the **same surface** when they share the same semantic
  boundary *and* the same typed owner.
- They belong to **separate surfaces** when they sit at different semantic
  boundaries — authored scenario intent, observed runtime state, source-artifact
  and image provenance, and backend or host delivery mechanics are four distinct
  boundaries — **even when the same real-world evidence supports both**.
  Surfaces do not collapse into each other.

Worked example (ADR-033): a container-side service listener, a host-published
port binding, and an image-default exposed port are three different facts on
three different surfaces, even though one inspection of a running container can
produce all three. The shared evidence is not a reason to merge them; the
differing semantic boundary is the reason to keep them apart.

The [glossary](../../docs/explain/reference/glossary.md) carries a reference-aid
entry for "surface" that points back to this normative definition.

## Provenance Categories

Every concept family declares its provenance:

| Category | Meaning |
|----------|---------|
| `adopted` | Imported from the external authority with equivalent meaning. |
| `adapted` | Derived from the external authority with RAES-specific modifications. |
| `native` | Defined by RAES with no external authority source. |

## Concept Families

### Cyber-Domain Families

These families use UCO as the concept authority.

| Family | Provenance | Scope |
|--------|-----------|-------|
| `assets` | adopted | Nodes, infrastructure, networks, and deployable resources. |
| `identities` | adopted | Accounts, entities, roles, and identity-bearing participants. |
| `relationships` | adapted | Typed associations between scenario elements. |
| `observables` | adopted | Conditions, metrics, telemetry, and observable properties. |
| `actions-and-events` | adopted | Events, injects, workflow steps, and executable actions. |
| `tools-and-artifacts` | adopted | Features, content, software, and deployable artifacts. |

The `relationships` family uses `adapted` provenance because existing
relationship types draw from STIX 2.1 Relationship SROs and OCR dependency
patterns, not from UCO alone.

### RAES-Native Families

These families have no external authority. They are defined by RAES for
ecosystem-specific concerns.

| Family | Scope |
|--------|-------|
| `scenarios` | SDL scenarios, compositions, modules, and authoring constructs. |
| `tasks-runs-studies` | Execution lifecycle, run records, and study organization. |
| `behavioral-relations` | Revisioned validation, conformance, comparison, refinement, equivalence, and empirical claim semantics. |
| `episodes` | Participant runtime episode identity, lifecycle state, and history boundaries. |
| `runtime-inventory` | Observed and declared runtime configuration state attached to scenario nodes. |
| `apparatus-declarations` | Processor, backend, and participant-implementation manifests. |
| `realization-and-disclosure` | Instantiation, planning, compilation, and realization artifacts. |
| `provenance-and-evidence` | Run provenance records, evidence expectations, and audit artifacts. |
| `time-and-apparatus` | Clocks, timing constraints, and apparatus-level concerns. |

The `episodes` family is native because participant episode semantics are an
RAES runtime boundary, not a UCO cyber object and not a task/run/study alias.
It covers participant-scoped episode identity, lifecycle state, reset/restart
boundaries, and append-only episode history. Episode-bound behavior events,
observables, actions, tools, artifacts, and evidence still bind to their
narrower concept families when those records are the artifact's subject.

The `runtime-inventory` family is native because observed node runtime state is
an RAES extension over the cyber-domain authority, not a UCO object in its own
right and not a task/run/study or apparatus declaration. It covers the typed
runtime inventory carried under `nodes.*.runtime` — services, platforms,
packages and software components, controls and security posture, filesystem and
mounts, processes and scheduled jobs, and other node-scoped apparatus state.
Individual inventory fields that denote a narrower cyber-domain object — an
asset, identity, observable, tool, artifact, or relationship — still bind to
that narrower family. Runtime inventory records the observed or declared state,
never the actions or events that produce, change, or react to it.

The `behavioral-relations` family is native because RAES must govern how its
artifacts bind formal and empirical relations to carriers, observation
projections, quantifiers, evidence boundaries, and assurance states. The
individual mathematical relations retain their revision-pinned publication
lineage in the behavioral-relation catalog; this family owns RAES's claim
discipline, not a replacement definition of actions, observations, scenarios,
apparatuses, runs, studies, or evidence.

## Extension Discipline

RAES-native families must be explicit extensions over the shared concept
authority, not implicit forks of adopted or adapted cyber-domain meaning.

Each `native` family must declare:

- `extension_scope`: the RAES-specific concern covered by the family
- `relation_rules`: how the native concept may relate to adopted, adapted, or
  other native families
- `non_ambiguity_constraints`: constraints that prevent the native concept
  from duplicating or shadowing shared cyber-domain concepts

Native families must use these fields to state when an artifact should bind to
the native family and when it should instead bind to a narrower adopted or
adapted family from the shared authority.

### Adding a Runtime Inventory Field or Family

Runtime inventory is the largest extension surface, so the decision path for
adding to it is explicit. A contributor can determine the required governance
steps from this section and the machine-readable catalog alone:

1. **Extend the existing runtime surface first.** A new observed node fact
   should extend `RuntimeConfiguration` and register through the canonical
   runtime service-family registry (`raes._runtime_service_families`)
   instead of introducing a new top-level concept family. The
   `runtime-inventory` family and the `nodes.*.runtime` reference model are the
   shared seam for this surface.
2. **Pass the cross-family invariant lint.** Every registered runtime service
   family must satisfy the single structural invariant set enforced by
   `implementations/python/tests/test_runtime_family_invariants.py` (the runtime
   SDL cross-family consistency epic
   [#439](https://github.com/OpenRAE/rae/issues/439) and children
   #442 / #443 / #444): a `Runtime<Noun>` model class, a
   `singular(collection_name) + "_id"` primary identifier, and a plural
   typed-child container registered in the registry. A new family that violates
   an invariant fails the suite immediately.
3. **Keep observed values redaction-safe.** Values that can carry secrets must
   route through the runtime redaction helpers (ADR-056 / ADR-057,
   `raes_contracts.runtime_values`); raw credential material is unrepresentable on the
   model surface.
4. **Add controlled vocabulary, not free strings.** New enumerated terms belong
   in `contracts/concept-authority/controlled-vocabularies-v1.json` (GOV-922),
   not as artifact-local labels.
5. **Promote to a new concept family only when warranted.** A genuinely new
   concept that is not a runtime sub-surface requires an ADR, a catalog entry in
   `concept-families-v1.json` declaring `extension_scope`, `relation_rules`, and
   `non_ambiguity_constraints` (the discipline above), and a reference-model
   entry when it has a recurrent SDL structure.

## Machine-Readable Catalog

The authoritative concept family catalog is published at:

`contracts/concept-authority/concept-families-v1.json`

The catalog is a keyed map. `families` is an object whose property names are
the canonical family identifiers, and each property value is the family
definition. The family identifier is authoritative at the map key and is not
duplicated inside each family object.

The catalog must not be empty. Each family entry must declare a non-empty
`title` and `description`.

The machine-readable catalog also makes the provenance rules normative:

- `adopted` and `adapted` families must declare both `authority` and
  `authority_reference`
- `native` families must not declare either authority field
- `native` families must declare non-empty `extension_scope`,
  `relation_rules`, and `non_ambiguity_constraints`

The JSON Schema for the catalog format is published at:

`contracts/schemas/concept-authority/concept-families-v1.json`

## Relationship to Implementation

Implementation code may define enums and models that correspond to concept
families, but the normative catalog is the authority for what families exist
and where their meaning comes from.

## Relationship to Other Requirements

- GOV-917: This specification (concept authority definition).
- GOV-918: Cross-artifact concept binding, including
  [portable external concept assertions](./external-concept-bindings.md).
- GOV-919: Extension discipline (rules for adding new concepts).
- GOV-920: Shared semantic profiles ([semantic-profiles.md](./semantic-profiles.md)).
- GOV-921: Shared reference models ([reference-models.md](./reference-models.md)).
- GOV-922: Controlled vocabularies and enumerations ([controlled-vocabularies.md](./controlled-vocabularies.md)).
- ACT-611: Autonomous service and agent vocabulary assertions
  ([autonomous-behavior-vocabularies.md](./autonomous-behavior-vocabularies.md)).
