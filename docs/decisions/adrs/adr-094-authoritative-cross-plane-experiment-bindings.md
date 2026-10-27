# ADR-094: Authoritative Cross-Plane Experiment Bindings

## Status

accepted

## Date

2026-07-26

## Classification

Classification: FM2

Required artifacts: ADR, published schemas, schema-publication records,
positive and negative fixtures, conformance registration, reference
implementation, and behavioral tests.

Waivers: no runtime mutation, provider selection, scheduling, secret
resolution, HTTP endpoint, CLI command, or MCP tool is introduced.

## Context

`ExperimentParameterModel` and condition-assignment parameters record a name,
scalar value, value kind, and redaction posture. They do not identify an
authoritative configuration plane, canonical owner target, source factor and
condition, exact scalar type, validator, default, or realized-value
provenance. Inferring those facts from names, prefixes, free-text constraints,
or matching backend fields permits cross-plane configuration injection.

ADR-084 already assigns scenario variation to SDL variation points and public
instantiation. ADR-041 assigns participant implementation declaration and
selection to participant manifests and provenance. Processor and backend
manifests separately own apparatus capability. The missing surface is a
portable, typed bridge between experiment intent and those existing owners.

## Decision

Publish `experiment-binding-descriptors-v1` as one closed descriptor family
with three planes:

- `scenario`;
- `participant-implementation`; and
- `apparatus`.

Each descriptor records an explicit factor id, factor-level id, condition id,
plane-specific target, exact JSON scalar type, literal or secret-reference
value, and governing contract/validator identity. Plane is discriminated data;
it is never inferred. Scenario targets identify a scenario family, variation
point, and owner target. Participant and apparatus targets identify the
selected manifest owner and a manifest-declared configuration target.

Canonical target resolution is owner-specific. SDL variation authority
resolves scenario targets. Participant, processor, and backend manifests may
publish a typed `configuration_registry` containing canonical ids, bounded
aliases, scalar types, allowed value kinds, sensitivity, defaults, and a
governed validator identity. Aliases are accepted inputs, not identities.
Resolution preserves all inputs until collisions are checked. Two bindings in
one condition that resolve to the same canonical target fail even when their
values match.

`ExperimentSpecModel` gains explicit binding semantics. The
`explicit-required` posture requires descriptors, rejects legacy
`required_parameters`, and verifies every descriptor's factor, level, and
condition join against the allocation. Existing descriptive authoring remains
valid only under the `descriptive` posture and makes no mutation claim.

Participant configuration realization is a complete atomic operation:

1. resolve all canonical ids and aliases;
2. reject unknown or duplicate canonical targets;
3. apply owner-declared defaults and overrides without coercion;
4. require every target with no default;
5. invoke an optional trusted complete-configuration validator;
6. preserve default/override provenance; and
7. emit one `participant-configuration-result-v1` with an RFC 8785/JCS digest.

Normalization cannot change target identity or JSON scalar type. No partial
result is emitted on failure.

Literal values and secret references are a discriminated union. Portable
contracts carry only a bounded, non-sensitive reference identity. They have no
field for a resolved value, provider credential, environment variable, file
path, command, or backend-native locator. Resolved secret material never
participates in canonicalization, diagnostics, fixtures, or provenance.

`experiment-run-v1` may archive realized binding provenance. The provenance
embeds the admitted descriptor, default/override/selection origin, and the
authoritative configuration digest when the binding belongs to participant or
apparatus configuration.

## Validation and compatibility

Strict Pydantic scalars distinguish Boolean, integer, number, string, and null.
Strings are not parsed as numbers or booleans, Boolean is not integer, and
non-finite numbers fail before canonicalization. The reference implementation
uses `canonical_contract_digest()` rather than a binding-specific serializer.

The affected published schemas are `draft` under ADR-061. Their in-line
changes remain reviewable through per-contract `last_change` hashes. The two
new roots are registered with the existing conformance runner and carry valid
and invalid fixtures.

## Consequences

Experiment authors can state binding intent without encoding authority in a
name. Participant and apparatus owners can publish a portable target surface
without exposing private backend schemas. Downstream trial compilation can
resolve every target before mutation and reuse the public SDL instantiation,
manifest, and provenance paths.

Adding a target or validator version extends an owner registry. Adding an
authority plane requires a new contract-lineage and ADR change. The design
does not create a global configuration registry, generic patch language,
plugin dispatcher, secret resolver, or second SDL binder.

## References

- [ADR-041](adr-041-participant-implementation-manifest-and-provenance.md)
- [ADR-061](adr-061-published-schema-evolution-policy.md)
- [ADR-074](adr-074-experiment-authoring-input-contract-boundary.md)
- [ADR-084](adr-084-scenario-variation-and-deterministic-trial-realization.md)
- [Experiment binding contracts](../../explain/reference/experiment-binding-contracts.md)
