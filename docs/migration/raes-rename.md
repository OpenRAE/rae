# RAES identity cutover

## Historical version boundary

This record describes the identity cut from RAES 1.1.0 toward the planned 2.0.0 breaking release.
It also records the later organization rename and the legacy package retirement plan.
The retirement plan below does not confirm that publication or archival occurred.
Use the [RAES 11.0.2 guides](../public/guides/cli.md) for current commands.
Use [backend migration](concrete-backends.md) before relying on old native-resource instructions.

Issue #908 and GOV-944 completed the hard cut begun in issue #866.
RAES became the sole current identity of the Reproducible Agentic Environments System.
The change covered this repository and its owned ecosystem surfaces.
It retained no public aliases or dual-name compatibility.

## Current surface map

These were the identity surfaces and their verification routes:

- Python distribution and imports: `raes` and the owning `raes_*` packages.
  Installed-wheel and source-boundary tests checked them.
- CLI and MCP commands: `raes` and `raes-mcp`.
  CLI and MCP construction tests checked them.
- MCP server and tools: RAES server metadata and `raes_*` tool identifiers.
  Advertised-tool and guidance tests checked them.
- Schema namespace: `https://openrae.github.io/rae/schemas/`.
  Generated parity and schema-publication checks covered it.
- Contracts and profiles: RAES contract, profile, annotation, and wire identifiers.
  Models, fixtures, and JSON Schema validation checked them.
- Module artifacts: `raes.lock.json`, `raes-trust.yaml`, and `.raes/module-cache`.
  They also included RAES OCI media types and labels.
  Registry, digest, signature, archive, and CLI tests covered them.
- Runtime and evidence artifacts: RAES schema names, event/status values, evidence IDs, and resource names.
  DTO, fixture, persistence, and backend tests checked them.
- Authentication: RAES trusted-proxy headers.
  Strict-default authentication, role, denial-audit, and redacted-error tests checked them.
- Environment and workflow: RAES requirement-governance and real-libvirt inputs.
  Repository policy and opt-in integration tests checked them.
- Host ownership: RAES OCI labels, libvirt names, guest markers, paths, and UUID namespace.
  Conflict, discovery, teardown, guest-probe, and real-daemon tests checked them.
- Documentation and examples: RAES terms and paths.
  The documentation build and whole-tree naming policy checked them.

This historical test inventory does not restore removed backend support.

## Compatibility rule

The cutover's readers, writers, commands, and configuration accept only RAES identities.
Existing consumers must update before adopting that release.
There are no aliases, shims, fallback imports, or identity redirects.
There are no dual-read paths or last-one-wins rules.

Published contract changes keep their owning schema-publication and lifecycle evidence.
That evidence records the change. It does not keep a retired value executable.

## Historical records

Accepted pre-cutover decisions remain historical records.
So do release history, provenance, and dated research or design evidence.
The whole-tree naming policy permits old content only through exact recorded identities.
Each entry needs its path, content digest, record class, rationale, and occurrence count.
The policy does not exempt a whole documentation directory.
Historical wording must not become current guidance.

## Operator guidance

Use `raes` and `raes-mcp` in automation.
Use RAES contract, schema, module, runtime, header, environment, and host identifiers for new artifacts and deployments.

The cut does not rewrite persisted artifacts automatically.
It does not clean resources created under an earlier identity.
Operators should finish required environment cleanup before deploying the cutover release.
The repository does not discover or destroy old-name resources.

## Downstream cutover sequencing

Issue #908 changed contract, schema, wire, workflow, runtime, and host identities together.
Consumers pinned to RAES 1.1.0 keep that release's pre-cutover values.
They must switch all affected values atomically when adopting the next breaking release with the cutover.
The recorded target for that release was 2.0.0.

Do not guess replacement spellings or mix identities from the two release lines.
Do not add aliases or fallback reads.
Use the release's schemas, fixtures, and migration evidence for the new values.

## GitHub organization rename

The GitHub organization changed from RAESystem to OpenRAE.
Live repository configuration, clone URLs, issue links, evidence references, and documentation use `OpenRAE/rae`.

The published schema namespace moved from `https://raesystem.github.io/rae/schemas/`
to `https://openrae.github.io/rae/schemas/`.
Contract IDs and schema paths stayed unchanged.
Consumers that pin or cache schema `$id` values must update them atomically.
The repository keeps no second accepted namespace or fallback reader for the former URI root.

## Scenario and environment-pack vocabulary

`Scenario` remains the RAES SDL authored-content concept.
`instantiate_scenario()` still produces an instantiated scenario.
An **environment pack** is a downstream unit for packaging and distribution.
It can contain SDL scenarios and other reusable assets.
It is not a scenario, an SDL document phase or model, or a realized environment.

A pack repository owns its layout and release mechanics.
This repository owns the SDL, concept, and reusable-asset trust-policy meanings that packs use.
The env-packs repository adopted that split in [OpenRAE/env-packs#139](https://github.com/OpenRAE/env-packs/issues/139).

## Legacy PyPI distribution retirement

The legacy PyPI distribution named in issue #907 is end-of-life.
`raes` is its replacement.
The recorded plan specifies one final 0.23.2 release from immutable legacy lineage 0.23.1.
That release keeps code behavior unchanged.
Its updated long description points readers to `raes` and this migration guide.
It does not depend on `raes`, install a placeholder, or restore retired import aliases.

Under that plan, archival follows verification on PyPI.
Verification covers the final artifact name, version, contents, metadata, and replacement links.
Historical releases remain available. They are not deleted or broadly yanked.
The current release-please workflow remains exclusive to `raes`.
The one-time legacy publication needs immutable reviewed source and the protected PyPI environment.
It uses short-lived OIDC credentials, not a stored token.
