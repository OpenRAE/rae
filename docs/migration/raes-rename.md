# RAES Identity Cutover

RAES is the sole current identity of the Reproducible Agentic Environments
System and its repository-owned ecosystem surfaces.

Issue #908 and GOV-944 complete the hard cut begun by issue #866. The cutover
does not retain public aliases or dual-name compatibility.

## Current Surface Map

| Surface | Current identity | Verification |
|---|---|---|
| Python distribution and imports | `raes` and the owning `raes_*` packages | installed wheel and source-boundary tests |
| CLI and MCP commands | `raes`, `raes-mcp` | CLI and MCP construction tests |
| MCP server and tools | RAES server metadata and `raes_*` tool identifiers | advertised-tool and guidance tests |
| Published schema namespace | `https://openrae.github.io/rae/schemas/` | generated parity and schema-publication checks |
| Contract/profile identities | RAES contract, profile, annotation, and wire identifiers | contract models, fixtures, JSON Schema validation |
| Module artifacts | `raes.lock.json`, `raes-trust.yaml`, `.raes/module-cache`, RAES OCI media types and labels | registry, digest, signature, archive, and CLI tests |
| Runtime and evidence artifacts | RAES schema names, event/status values, evidence ids, and resource names | DTO, fixture, persistence, and backend tests |
| Authentication | RAES trusted-proxy headers | strict-default auth, role, denial-audit, and redacted-error tests |
| Environment/workflow | RAES requirement-governance and real-libvirt inputs | repository policy and opt-in integration tests |
| Host ownership | RAES OCI labels, libvirt names, guest markers, paths, and UUID namespace | conflict, discovery, teardown, guest-probe, and real-daemon tests |
| Documentation and examples | RAES terminology and paths | documentation build and whole-tree naming policy |

## Compatibility Rule

Current readers, writers, commands, and configuration accept only RAES
identities. Existing consumers must update before adopting the cutover release.
There are no aliases, shims, fallback imports, redirects, dual-read paths, or
last-one-wins resolution rules.

Published contract changes still carry their owning schema-publication and
lifecycle evidence. That evidence records what changed; it does not keep the
retired value executable.

## Historical Records

Accepted pre-cutover decisions, release history, provenance, and dated research
or design evidence remain accurate historical records. The whole-tree naming
policy permits such content only through exact path, content digest, record
class, rationale, and occurrence-count entries. It does not exempt a
documentation directory or allow historical wording to become current
guidance.

## Operator Guidance

Use `raes` and `raes-mcp` in automation. Use RAES contract, schema, module,
runtime, header, environment, and host identifiers in newly created artifacts
and deployments.

The hard cut does not automatically rewrite persisted artifacts or clean
resources created under an earlier identity. Operators should complete any
required environment cleanup before deploying the cutover release; the
repository does not discover or destroy old-name resources.

## Downstream Cutover Sequencing

Issue #908 migrated current contract, schema, wire, workflow, runtime, and host
identities together. Consumers pinned to RAES 1.1.0 continue to use that
release's pre-cutover values. They must switch all affected values atomically
when adopting the next breaking RAES release that contains the identity
cutover, targeted as 2.0.0.

Consumers must not guess replacement spellings, mix identities from the two
release lines, or introduce aliases and fallback reads. The release's schemas,
fixtures, and migration evidence are the source of truth for the new values.

## GitHub Organization Rename

The GitHub organization was renamed from RAESystem to OpenRAE. Live repository
configuration, clone URLs, issue links, evidence references, and documentation
now use `OpenRAE/rae`.

The published schema namespace moved with the organization from
`https://raesystem.github.io/rae/schemas/` to
`https://openrae.github.io/rae/schemas/`. Contract ids and schema paths are
unchanged, but consumers that pin or cache schema `$id` values must update them
atomically. The repository does not retain a second accepted namespace or a
fallback reader for the former URI root.

## Scenario And Environment-Pack Vocabulary

`Scenario` remains the RAES SDL authored-content concept, and
`instantiate_scenario()` continues to produce an instantiated scenario. An
**environment pack** is a downstream packaging and distribution unit that may
contain SDL scenarios and other reusable assets. It is not another name for a
scenario, an SDL document phase or model, or a realized environment.

The intended split is therefore: packs are environment packs; the SDL content
they carry remains scenarios. A pack repository owns its layout and release
mechanics, while this repository remains authoritative for SDL, concept, and
reusable-asset trust-policy meanings. The env-packs repository adopted the same
split in [OpenRAE/env-packs#139](https://github.com/OpenRAE/env-packs/issues/139).

## Legacy PyPI Distribution Retirement

The legacy PyPI distribution named in issue #907 is end-of-life, and `raes` is
its replacement. One final 0.23.2 release will be cut from the immutable 0.23.1
legacy lineage with unchanged code behavior and an updated long description
that points consumers to `raes` and this migration guide. It will not depend on
`raes`, install a placeholder, or restore retired import aliases.

After the final artifact name, version, contents, metadata, and replacement
links are verified on PyPI, the legacy project will be archived. Existing
historical releases will remain available rather than being deleted or broadly
yanked. The current release-please workflow remains exclusive to `raes`; the
one-time legacy publication requires an immutable reviewed source, the
protected PyPI environment, and short-lived OIDC credentials rather than a
stored token.
