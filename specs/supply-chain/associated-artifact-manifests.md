# Associated Artifact Manifests

Status: normative

Decision: [ADR-077](../../docs/decisions/adrs/adr-077-associated-artifact-manifest-boundary.md)

This specification defines the portable RAES contract for non-semantic
artifacts associated with a scenario, sealed scenario snapshot, or experiment
artifact. The normative machine-readable surface is
`associated-artifact-manifest-v1` under
`contracts/schemas/associated-artifacts/`.

## 1. Claims and identities

A conforming implementation MUST keep these claims distinct:

1. the SDL semantic digest identifies validated, expanded SDL meaning;
2. the associated-artifact set digest identifies one parent reference plus one
   exact artifact-reference set;
3. each artifact checksum identifies concrete payload bytes; and
4. authenticity is a separately verified signature/trust-policy result.

Associated artifacts do not change the semantic SDL digest or the identity of
an experiment task, authoring input, apparatus context, run, or study.

## 2. Manifest contract

The manifest is closed and contains:

- `schema_version`: `associated-artifact-manifest/v1`;
- `manifest_id` and `manifest_version`: stable logical manifest identity;
- `canonicalization_profile`: `associated-artifact-set/v1`;
- `scope`: `scenario` or `experiment`;
- `parent_ref`: one constrained typed reference;
- `artifacts`: a non-empty object keyed by stable local artifact id; and
- `set_digest`: a derived lowercase `sha256:<hex>` digest.

Scenario scope permits only `scenario` and `scenario-snapshot`. A generic
scenario reference is id-only. A snapshot may bind version and the incumbent
canonical SDL digest. Experiment scope permits only `task`, `authoring-input`,
`apparatus-context`, `run`, and `study`. Experiment parent references may bind
id and version but MUST NOT carry a digest or path until that parent family has
a normative canonical payload profile and concrete-payload validator.

Every artifact entry reuses the `ExperimentArtifactRefModel` shape: stable
`artifact_id`, closed role, media type, absolute non-secret URI, checksum, byte
size, creation time, source assertion, applicable evidence/provenance links,
sensitivity, and optional description. URI is a locator, not integrity
evidence. It MUST NOT contain userinfo or secret-bearing query fields.

Within one manifest:

- each object key MUST equal its embedded `artifact_id`;
- artifact ids are opaque, case-sensitive, manifest-local identities, not paths
  or content ids;
- duplicate JSON member names MUST be rejected before object construction;
- exact descriptors under different ids are invalid aliases;
- one URI MUST NOT carry conflicting checksum, size, or media-type claims; and
- the same checksum under distinct ids is permitted only when the remaining
  descriptors deliberately express distinct roles or locators.

No attachment is inherited. Scenario attachment does not imply task
attachment; task attachment does not imply authoring-input, apparatus, run, or
study attachment; and study membership does not import member attachments.
Another attachment requires another conforming manifest naming that parent.

## 3. Set canonicalization

`associated-artifact-set/v1` serializes this projection with RFC 8785:

```text
{
  "profile": canonicalization_profile,
  "scope": scope,
  "parent_ref": exact non-null parent reference fields,
  "artifacts": exact keyed non-null artifact descriptor fields
}
```

Checksum hex and prefixed parent digests are case-normalized before
canonicalization. Opaque ids, URI strings, descriptions, and other values are
not filesystem- or platform-normalized. SHA-256 of the canonical bytes,
rendered as lowercase `sha256:<hex>`, is the set digest.

The projection excludes `set_digest`, logical manifest id/version, traversal
order, archive metadata, filesystem paths, permissions, symlink targets,
manifest filenames, export tiers, and packaging layout. A parent change or any
canonical artifact-entry change MUST change the set digest.

## 4. Full conformance and byte binding

Schema/model validation establishes structural validity only. Full conformance
requires `validate_associated_artifact_manifest()` with:

- the validated manifest;
- the concrete parent artifact; and
- exactly one concrete byte reader for every artifact id.

A generic `scenario` parent retains the id-only `Scenario` association
contract. A `scenario-snapshot` concrete parent MUST be a semantically validated
normalized `Scenario` or composed `ExpandedScenario`, matching the authoring
phases admitted by `canonical_sdl_digest()`. An unvalidated authoring object or
an `InstantiatedScenario` MUST NOT satisfy a scenario-snapshot parent reference.

The validator MUST:

1. match parent kind, id, version, and snapshot digest where applicable;
2. recompute and compare the set digest;
3. reject missing, extra, digest-only, path-only, URI-only, or boolean bindings;
4. stream each reader, recompute checksum and byte size, and compare both; and
5. enforce caller-supplied artifact-count, per-artifact-byte, and total-byte
   limits, rejecting declared excess before reading and reading at most the
   declared size plus one byte for mismatch detection.

The validator MUST NOT acquire URIs, traverse directories, extract archives,
resolve credentials, invoke subprocesses, or infer payloads from filenames.
Callers own acquisition and immutable staging.

Stable error diagnostics include:

| Condition | Diagnostic code |
|---|---|
| Missing concrete bytes | `associated-artifact.payload-binding-missing` |
| Invalid or digest-only binding | `associated-artifact.payload-binding-invalid` |
| Undeclared binding | `associated-artifact.payload-binding-unexpected` |
| Checksum mismatch | `associated-artifact.payload-checksum-mismatch` |
| Size mismatch | `associated-artifact.payload-size-mismatch` |
| Set digest mismatch | `associated-artifact.set-digest-mismatch` |
| Parent mismatch | `associated-artifact.parent-mismatch` |
| Resource limit exceeded | `associated-artifact.resource-limit-exceeded` |

Diagnostics MUST be bounded and MUST NOT include payload bytes, full rejected
objects, credentials, environment data, or credential-bearing locators.

## 5. Trust policy

The manifest/set is the `associated_artifact_set` reusable-asset family. The
derived set digest is its required `integrity_digest`; concrete payload
verification supplies required `artifact_checksum` evidence. A downstream
signature over the derived set digest may supply `authenticity_signature`, but
integrity alone never proves authenticity, authorization, sensitivity handling,
or entitlement. Associated bytes do not contribute to the parent asset's
integrity mechanism.

## 6. Packaging and consumer boundary

Environment-pack tooling owns filesystem layout, manifest filename, archive/OCI
layout, traversal rules, release tiers, catalog metadata, and safe
materialization. It MUST select a stable byte set before producing this
manifest; a walk over a mutable live directory is not an atomic snapshot.

Consumers own acquisition, immutable staging, storage, entitlement, atomic
promotion, retention, and use-time verification. They validate the parent and
every staged payload, derive rather than trust the set digest, retain the
manifest with verified bytes, and reverify before use when storage guarantees
do not make that redundant. A caller-supplied package digest may be retained as
untrusted metadata, but cannot become RAES conformance or trust evidence unless
it equals the validator-derived set digest.
