# Typed domain profiles

Typed domain profiles let standard and private domain structure travel through
RAES contracts without making every domain a core catalog, every backend
choice an authoring obligation, or profile data executable. The reference
contract and offline admission engine live in
`raes_contracts.domain_profiles`.

This is a neutral contract seam. It does not add an SDL field, migrate the
legacy identity-domain profile vocabulary, register plugins, discover files,
fetch schemas, invoke backends, or authorize capture and retention.

## Contract roles

The implementation keeps four roles distinct:

| Role | Meaning |
| --- | --- |
| Definition | An authority-qualified namespace and profile id at one exact revision and RFC 8785 digest, with a pinned schema, semantic-contract coordinate, and allowed host contexts. |
| Binding | Profile data attached to an explicit owning contract address, concept family, lifecycle phase, context, and use. Nested bindings use the same contract and are never silently dropped. |
| Resolution context | Immutable caller-supplied namespace admissions, locally admitted definitions with separate trust provenance, operation support, and resource limits. |
| Support declaration | Exact support for a profile coordinate and semantic-contract coordinate, split by structural validation, semantic validation, refinement, comparison, interpretation, execution, and typed reporting. |

Standard and private profiles use the same models. A private definition is not
less complete because it is absent from a public catalog. Namespace ownership
comes from `DomainProfileNamespaceAdmissionModel`, not from a self-asserted
name inside profile data.

`seal_domain_profile_definition()` computes the definition digest from its
semantic projection without self-reference. `DomainProfileSchemaModel`
separately binds the embedded schema to its schema id, revision, and digest.
Digest equality proves content identity; it does not prove trust, semantic
equivalence, support, execution, or observation.

## Offline resolution and admission

`resolve_domain_profile_definition()` searches only the supplied
`DomainProfileResolutionContextModel`. It diagnoses unadmitted or colliding
namespace authorities, absent definitions, incompatible revisions, digest
mismatches, and same-coordinate/different-digest collisions. It never uses
ambient filesystem search, environment variables, package entry points,
network retrieval, or revision fallback.

`admit_domain_profile_bindings()` resolves and negotiates the complete binding
tree before a caller performs mutation. Constraint bindings require structural
and semantic-validation support; typed reports require structural-validation
and typed-report support. Callers can require additional operations through
`DomainProfileAdmissionPolicyModel`. A support row contains data only—it cannot
name a Python object, import path, command, callback, or package installer.
Semantic handlers and interpreters remain pre-installed caller code selected by
the exact semantic-contract coordinate after admission.

Each binding admission retains its exact resolution outcome. Callers can
therefore distinguish an unavailable definition, incompatible revision, digest
mismatch, namespace refusal, and coordinate collision even when admission maps
them to the common `resolution-refused` safety outcome.

Structural validation is deliberately narrow and inert:

- JSON ingress is byte-bounded and rejects duplicate members and non-finite
  values.
- Definitions use the pinned `jsonschema==4.26.0` Draft 2020-12 validator.
- Required schema vocabularies and used keywords must be explicitly supported.
- Only bounded, acyclic local JSON Pointer references are admitted; remote
  references are refused before the validator runs.
- Regex-bearing and unknown/custom keywords are outside the initial safe
  subset, so profile data cannot activate custom format or keyword code.
- Depth, node, scalar-byte, reference, evaluation, binding, definition, and
  diagnostic limits are host-owned.
- Diagnostics contain stable codes and generic messages, not private values,
  schemas, locators, or native exceptions.

## Unknown profiles and provenance

An absent definition may be preserved only when all of these conditions hold:

1. the binding use is `opaque-exchange`;
2. the host explicitly enables `allow_opaque_exchange`;
3. no validation, comparison, execution, reporting, or other semantic
   operation is required; and
4. the value stays within the configured limits.

The resulting `opaque-preserved` outcome is not structurally valid,
semantically supported, comparable, executable, or observed. Namespace
collisions, incompatible revisions, and digest conflicts are never converted
to opaque success.

Definition source/trust provenance and binding provenance are independent.
Bindings distinguish `author-supplied`, `backend-selected`, and `observed`
bases. Only an observed binding may carry observation evidence, and an observed
binding must carry it. A backend-selected typed report therefore describes the
backend's choice without pretending that an independent scanner observed it.

## Backend-owned choices

An unmentioned private repository, generator, or other backend-internal
materialization choice creates no profile binding, registry entry, report, or
provenance requirement. When an author explicitly constrains that detail, or a
caller requests it in a typed report, it uses the shared coordinate, schema,
context, provenance, and support contract. Missing required meaning then fails
honestly before backend or store mutation.

The existing `capabilities.provisioner.supported_domain_profiles` field remains
the compatibility surface for authored identity-domain topology. It is not the
authority for this contract and is not automatically projected into these
operation-specific support declarations.

Issue #1203 owns recursive public authoring syntax. Issue #1204 owns
compiler/planner/runtime carriage and mutation-boundary integration. Later
profile-specific migrations can reuse this seam without changing its exact
identity or offline-resolution rules.
