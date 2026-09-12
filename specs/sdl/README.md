# SDL Specification

Status: **normative**. This directory is the language-neutral authority for the
RAES **Scenario Description Language (SDL)** authoring model and portable
derived phase contracts. It is binding on
the ecosystem independent of any reference implementation or code-generation
pipeline, per [ADR-009](../../docs/decisions/adrs/adr-009-normative-artifact-authority-and-repository-structure.md)
and the [authority boundary manifest](../authority/authority-boundary.yaml).

The SDL itself is established by
[ADR-001 (Scenario Description Language)](../../docs/decisions/adrs/adr-001-scenario-description-language.md):
a backend-agnostic, declarative language for specifying security experiment
scenarios. This specification states the **authoring model** — the structure of
an SDL document, how its parts reference one another, how it is parameterised
and instantiated, and how it is diagnosed — in SDL terms, so that an independent
implementation can answer structural questions without reading the reference
Python.

## Authority relationship

Three artifact classes describe the SDL, with distinct authority:

1. **This prose specification (`specs/sdl/`)** is the language-neutral
   normative authority. It defines externally visible meaning in SDL concepts.
2. **The published JSON Schemas (`contracts/schemas/sdl/*.json`)** are the
   machine-readable normative companion. They are the hand-governed schema
   authority under [ADR-009 §7](../../docs/decisions/adrs/adr-009-normative-artifact-authority-and-repository-structure.md)
   and the [schema publication manifest](../../contracts/schema-publication-manifest.json).
   The prose and the schemas describe the same language and **MUST** agree; a
   divergence between them is a defect to be reconciled, not a license for
   either to override the other. Where this prose states a structural fact
   (a section's presence, requiredness, or value shape), the applicable
   `sdl-authoring-input-v1`, `instantiated-scenario-v1`, or
   `instantiated-scenario-snapshot-v1` schema is the authoritative enumeration
   the prose is written to match. The authoring schema validates the normalized
   object, not raw YAML presentation; `document-model.md` §1 and the
   `contracts/fixtures/sdl/sdl-yaml-v1/` corpus define the raw source profile.
3. **Reference implementations (`implementations/`)** consume both. No Python
   model, validator function, or generator defines ecosystem meaning; it is
   evidence of one conforming realisation. This specification names
   implementation symbols only in clearly marked, non-normative
   *implementation-evidence* notes.

`docs/explain/sdl/sections.md` and the rest of `docs/` are explanatory and
**non-normative**. They are useful learning and migration aids, but they are
not referenced here as authority and **MUST NOT** be cited as the normative
source.

## Conventions

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**,
**SHOULD**, **SHOULD NOT**, **MAY**, and **OPTIONAL** in this specification are
to be interpreted as described in RFC 2119 and RFC 8174 when, and only when,
they appear in all capitals.

Throughout, *section* means a top-level authoring surface of an SDL document;
*identifier* means an author-chosen key that names an element; *reference*
means one element naming another by identifier; and *instantiation* means the
phase that resolves a parameterised authoring document into a concrete one.

## Document set

The specification is organised as a small set of normative **catalogs** so that
adding a future SDL section or runtime family is a new row plus its schema and
tests, rather than a prose rewrite. The catalogs are:

| File | Catalog | Covers |
|------|---------|--------|
| [`document-model.md`](document-model.md) | — | Document encoding, the metadata/composition vs. authoring-section split, requiredness, identifier rules, structural closure, and the normalized -> expanded -> instantiated -> snapshot phases. |
| [`sections.md`](sections.md) | **1. Section catalog** | Every top-level field: kind, value shape (map-keyed vs. list-valued vs. scalar), requiredness, key shape, and the sections it references. |
| [`references.md`](references.md) | **2. Reference-resolution catalog** | Reference forms (bare, qualified, nested runtime-family, workflow-step, module-composed), the resolution algorithm, the fail-closed ambiguity rule, and the cross-section reference-edge catalog. |
| [`variables-and-instantiation.md`](variables-and-instantiation.md) | **3. Variable / instantiation catalog** | Variable types, defaults, `allowed_values`, `${…}` substitution, the instantiation algorithm, and post-instantiation exclusions. |
| [`variation-points.md`](variation-points.md) | — | Closed scenario-family variation kinds, bounded domains, typed target slots, structural constraints, composition, and phase behavior. |
| [`runtime-inventory.md`](runtime-inventory.md) | **4. Runtime-family index** | The node-scoped runtime-inventory index — family key, collection name, primary `<noun>_id`, child-ref collections, owning ADR — and the shared invariants stated once, delegating per-field semantics to the family ADRs. |
| [`recursive-realization-constraints.md`](recursive-realization-constraints.md) | — | The versioned recursive constraint normal form: independent presence, knowledge, closure, identity, sequence/reference, provenance, composition, and bounded relation semantics. |
| [`authored-domain-topology.md`](authored-domain-topology.md) | — | Authored identity domains, controller/member topology, account domain bindings, compiled ordering, provisioner capability, admission, and readback invariants. |
| [`account-credential-bindings.md`](account-credential-bindings.md) | — | Typed account fixture/operator credential bindings, normalization, lifecycle, capability admission, redaction, and participant disclosure boundaries. |
| [`initial-service-state.md`](initial-service-state.md) | — | Service-target content materialization, tenant/reset ownership, exact backend admission, readback, and observational equivalence. |
| [`observability-and-evidence.md`](observability-and-evidence.md) | **5. Observability and evidence planes** | Scenario-native observability, authored evidence requirements, processor/backend operational observability, captured evidence, derived analysis, and augmentation classification rules. |
| [`scientific-scenario-completeness.md`](scientific-scenario-completeness.md) | — | REV1 intended-use profiles, atomic concern dispositions, separately revisioned delivery assessment, computed completeness, and explicit scientific non-claims. |
| [`diagnostics.md`](diagnostics.md) | — | The parse / semantic-validation / instantiation stages, direct-artifact admission, and the normative error-vs-advisory classification criterion. |

## Acceptance-question map

An implementer can answer each structural question from the named file alone:

- *Which sections exist, which are required, and what shape is each?* →
  [`document-model.md`](document-model.md) and [`sections.md`](sections.md).
  The nox contracts gate runs `tools/check_sdl_catalog_parity.py` to prove the
  catalog, published schema, and reference registries remain reconciled.
- *Which raw YAML documents are canonical SDL, and what receives a stable
  semantic digest?* → [`document-model.md`](document-model.md) §§1, 5, 7-9.
- *What is a valid identifier for a user-defined key?* →
  [`document-model.md`](document-model.md).
- *How does a reference resolve, and what happens when it is dangling or
  ambiguous?* → [`references.md`](references.md), including its checked
  editor-visible edge index and distinct candidate-domain classifications.
- *What is legal to instantiate, and what does instantiation reject?* →
  [`variables-and-instantiation.md`](variables-and-instantiation.md).
- *How is a bounded scenario family authored without embedding selection
  policy?* → [`variation-points.md`](variation-points.md).
- *What is the runtime-inventory surface and which ADR owns each family?* →
  [`runtime-inventory.md`](runtime-inventory.md).
- *How is domain-backed realization authored without inferring topology from runtime inventory?* →
  [`authored-domain-topology.md`](authored-domain-topology.md).
- *How is fixture or operator-managed credential material bound to an account without becoming an implicit runtime lookup?* →
  [`account-credential-bindings.md`](account-credential-bindings.md).
- *How is required service-owned initial state authored and controlled without a historical-data ontology?* →
  [`initial-service-state.md`](initial-service-state.md).
- *How are scenario-native observability systems and authored evidence
  requirements kept distinct?* →
  [`observability-and-evidence.md`](observability-and-evidence.md).
- *When is a problem an error versus an advisory?* →
  [`diagnostics.md`](diagnostics.md).
- *When is valid SDL sufficient for deployment, participant evaluation,
  controlled experimentation, or a reproducible benchmark claim?* →
  [`scientific-scenario-completeness.md`](scientific-scenario-completeness.md).

## Scope

In scope: the SDL authoring model and portable derived phase contracts —
document structure, references, variables, instantiation/provenance,
scenario-family variation declarations, canonical snapshots, the runtime-inventory index, observability/evidence plane
rules, authored identity-domain topology, and the diagnostic boundary.

Out of scope: delivery-level concerns (container, infrastructure-as-code, and
cloud-API mechanics), processor and backend execution contracts, and the
per-field semantics of each runtime family (owned by the family ADRs and indexed
here). The normative error-vs-advisory classification criterion is stated in
[`diagnostics.md` §5](diagnostics.md) (resolving review IMP-3); the
classification of an individual condition follows from that criterion.
