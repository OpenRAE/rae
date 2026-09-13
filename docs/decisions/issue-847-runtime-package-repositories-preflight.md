# Issue 847 Runtime Package Repository Preflight

Date: 2026-09-04

Issue: #847. Requirement: none; the issue is the authoritative delivery
contract.

Status: architecture guidance only. This note does not change SDL syntax,
models, schemas, compiler behavior, backend support, or package installation.
Existing decisions already own the relevant boundaries, so no new ADR or ADR
amendment is required.

Scope clarification (2026-09-12): this note preserves the legacy exact APT
shorthand's meaning. Its closed profile-union direction, final-state coupling
and verification obligations are not general requirements for software
outcomes or backend-internal acquisition. For the corrective #1205 design,
use the [software outcomes preflight](issue-1205-software-outcomes-preflight.md)
and its governing references; do not weaken existing `apt`/`1` semantics.

## Architectural Diagnosis

`RuntimePackage` is currently a closed object only in the Pydantic/JSON Schema
sense. Its `manager`, `name`, `version`, `source`, and `purl` members are plain
strings, and neither `source` nor `purl` defines an executable package-source
contract. They must not acquire private APTL semantics:

- `purl` is package identity metadata. It is not a repository locator, signing
  key, acquisition route, or trust assertion.
- `source` remains an opaque, non-executable source/provenance label for
  compatibility. A backend must never parse it as a repository line, options
  map, URL bundle, shell fragment, or command.
- `RuntimeSoftwareComponent`, `Source.build`, `ArtifactRequirement`, module
  registry trust, associated artifacts, and experiment evidence have adjacent
  identity/provenance roles, but none is the effective package-manager
  repository configuration of a node. Reusing one would conflate artifact
  identity, build provenance, reusable-asset acquisition, or evidence with
  package installation state.

At the same time, issue #1078 already makes `runtime.packages` the exact,
guest-observed `runtime-packages` SEM-218 concern. The compiler, plan authority,
support admission, returned-snapshot validation, and persistence path all
consume that one concern. A second `package-repositories` runtime collection,
compiler resource, realization kind, or backend-local side table would split
one package requirement across duplicate authorities without being necessary
for the Wazuh/Grafana shape.

## Contract Boundary

Add one optional, closed `repository` child to `RuntimePackage`. Absence keeps
the current meaning: the package is obtainable through the selected target's
ordinary configured package sources. Presence requires the backend to realize
the declared source and trust binding before installing the exact package. The
repository and dedicated trust binding are required final node state, not a
transient bootstrap hint; a future remove-after-install lifecycle would need
separately typed semantics rather than an undocumented cleanup step.

The child is a discriminated, versioned profile union. The initial profile is
APT only and has this semantic shape (field spelling is fixed here so
downstream implementations do not invent alternatives):

```yaml
runtime:
  packages:
    - manager: apt
      name: wazuh-agent
      version: 4.12.0-1
      repository:
        repository_profile: apt
        profile_version: "1"
        uri: https://packages.wazuh.com/4.x/apt/
        suite: stable
        components: [main]
        signing_key:
          uri: https://packages.wazuh.com/key/GPG-KEY-WAZUH
          format: openpgp-ascii-armored
          digest: sha256:<64-lowercase-hex-digits>
```

The profile means a binary APT repository with the exact base URI, suite, and
component set, trusted only by the exact public signing-key bytes named by the
SHA-256 digest. `format` is initially the closed set
`openpgp-ascii-armored` / `openpgp-binary`; a backend must not sniff content to
decide whether to dearmor it. `components` is non-empty, duplicate-free, and
set-like for semantic comparison. `suite` and component members are bounded
APT tokens, not whitespace-bearing source fragments.

The package `manager` and profile discriminator must agree (`apt` with `apt`).
The profile does not silently normalize `apt-get`, `debian`, `dpkg`, or another
manager spelling to `apt`. Existing packages without `repository` retain their
current compatibility; governing every historical manager/name/version string
is outside this issue. When this profile is present, however, APT package name,
version, URI, suite, component, key format, and digest values must pass the
profile's closed validation before compilation.

Do not expose an authored `signed_by`, source-list filename, keyring filename,
raw `deb ...` line, arbitrary options dictionary, install command, environment
map, or script. Those are OS rendering details. A supporting backend derives
collision-resistant owned filenames from the canonical repository/package
identity and always scopes that repository to its dedicated keyring. This
prevents SDL from choosing arbitrary root-owned paths or adding global trust.

The key digest is mandatory. HTTPS without a pinned trust-root payload is not
sufficient for exact repeatable realization, and a key URL or claimed key id is
not integrity. The digest binds bytes; it does not by itself prove that the
author selected the correct vendor key. Signing-key material is public
verification material, never a private key or credential.

Scalar leaves may use the repository's existing whole-field variable mechanism
only where the authoring schema represents the literal-or-variable union. A
bound value must pass the same concrete validator during normal instantiation.
The profile/version discriminator and collection structure are never variable.
No unresolved repository value may reach backend admission.

## Ownership, Realization, And Extensibility

The repository child remains inside the existing `runtime-packages` semantic
identity and projection. It does not add a 33rd `RuntimeConfiguration` field or
a second realization concern. The package collection's stable identity remains
the normalized `(manager, name, architecture)` tuple identified by the #1078
boundary audit; duplicate identities, conflicting versions, and conflicting
repository definitions for that identity fail closed rather than relying on
list order or last-write-wins behavior.

The existing typed runtime projector should include the closed repository
profile, normalize set-like `components`, and retain package/repository/key
identity. It must not retain downloaded key bytes, rendered files, native
package-manager output, cache state, commands, or backend paths. Exact
realization means the backend independently verifies the installed package
tuple, effective APT source tuple, dedicated key binding, and fetched key
digest before returning the matching safe projection. Echoing the submitted
payload or reporting only a successful `apt-get` exit status is not readback.

The extensibility seam is `repository_profile` plus `profile_version` on a
discriminated union. A future RPM/DNF/YUM, APK, Zypper, or authenticated private
repository gets its own closed profile with its own native semantics and
capability/readback evidence. It does not add optional RPM fields to the APT
profile, an `options: {}` escape hatch, or backend-product conditionals to the
SDL/compiler. Additive APT semantics require an explicit profile-version
decision rather than changing what profile `apt`/`1` means silently.

## Canonical Incumbents To Reuse

- **SDL shape and module boundary:** `raes._base.SDLModel(extra="forbid")`,
  `raes.runtime_values`, `raes.runtime_configuration`, and the facade exports
  in `raes.nodes`. Keep cohesive package repository models in a dedicated
  `raes.runtime_packages` module so `runtime_configuration.py` remains below
  ADR-015's 500-line cap; do not create a new top-level Python package.
- **URI and digest safety:** reuse
  `raes_contracts.uri_safety.validate_safe_absolute_uri` for absolute,
  credential-free URI parsing and the repository's canonical SHA-256 digest
  grammar. Add only the profile-specific HTTPS and fragment restrictions; do
  not add another URL parser, checksum object family, or cryptographic helper.
- **Parsing and validation:** `raes._yaml_loader.load_sdl_yaml`,
  `SDLParserLimits`, `raes.parser`, `SemanticValidator`, `SDLParseError`,
  `SDLValidationError`, `instantiate_scenario()`, and
  `SDLInstantiationError` remain the only language ingress and error
  hierarchy. Local profile invariants belong on the closed model; only
  cross-node/package relations belong in the existing node semantic pass.
- **Author intent:** preserve `model_fields_set`, `raes.explicitness`,
  `raes.realization_designation`, instantiation provenance, and concrete
  revalidation. Do not infer declaration or defaults from `model_dump()`.
- **Compilation and admission:** reuse `_compile_node_runtimes()`, the existing
  node `spec.node.runtime.packages` payload, `RuntimeConcernProfile("packages",
  "runtime-packages")`, `RealizationConcernDescriptor`,
  `CompiledRealizationRequirement`, plan-owned realization authority,
  `realization_support_diagnostics()`, and realization-envelope admission. No
  repository DTO, resource, plan, concern kind, support boolean, or manifest is
  justified.
- **Execution and evidence:** reuse `Provisioner.validate`,
  `raes_runtime.backend_calls._call_backend_apply`,
  `realization_authority_disclosure()`, `Diagnostic`, `ApplyResult`,
  `RealizationObservationDisclosure`, and the existing
  `runtime.backend-contract-invalid` failure. A backend may add support only
  when its selected configuration advertises complete `runtime-packages`
  exact support and matching configuration-scope, guest-observed capability.
- **Persistence and API:** reuse `RuntimeSnapshot`, `SnapshotEntry`,
  `RealizationProvenanceEntry`, `RuntimeSnapshotEnvelopeModel`,
  `ControlPlaneStore`, its existing serializers, and authorized snapshot
  routes. Do not add a repository cache, database table, sidecar, metadata
  escape hatch, or log-only evidence path.
- **Normative contract workflow:** ADR-009/061, the four Node-bearing schemas
  (`sdl-authoring-input-v1`, `instantiated-scenario-v1`,
  `instantiated-scenario-snapshot-v1`, and
  `scenario-satisfiability-evidence-v1`), `schema_bundle()`, positive and
  negative SDL fixtures, `contracts/schema-publication-manifest.json`,
  `tools/check_generated_schemas.py`, and
  `tools/check_schema_publication.py` move together. `docs/explain/sdl/sections.md`
  must describe the public field semantics; Python docstrings alone are not the
  portable contract.
- **Repository workflow:** `.ground-control.yaml`, `.gc/plan-rules.md`,
  ADR-015 module/size checks, repo policy, requirement-free issue handling, and
  `tools/verify_all.py` remain the verification authority. `CHANGELOG.md` and
  package versions remain release-please owned.

## Cross-Cutting Security And Runtime Gates

1. **Source/parser shape.** Bounded UTF-8 safe-YAML loading, alias/depth/node
   limits, duplicate/merge-key rejection, canonical key handling, and closed
   model validation run before any URI or package can become executable. URI
   validation is inert and performs no DNS or network access.
2. **SDL/config shape.** Repository and key URIs are HTTPS, absolute, bounded,
   and free of userinfo, secret-bearing query fields, and fragments. The key
   digest is canonical lowercase SHA-256. Suite/components/package tokens
   exclude whitespace, control characters, leading option syntax, and source
   line delimiters. Profile fields are closed; arbitrary APT options fail.
3. **Semantic/instantiation shape.** Repository/profile/manager agreement,
   unique package identities, architecture compatibility, variable provenance,
   and concrete post-binding validation finish before compilation. The compiler
   does not parse YAML, URLs, APT lines, or reimplement these checks.
4. **Plan/manifest/config admission.** The enriched value flows through the
   existing `runtime-packages` payload and concern. Exact support is valid only
   for a backend configuration that supports the APT profile, key verification,
   package pin, and independent readback as one complete operation. The generic
   concern-kind token alone is not a value-level package-manager claim; the
   selected configuration's existing realization envelope must bound the
   manager/repository profile it actually supports. Existing stub/reference/
   libvirt manifests must not be widened just to accept fixtures.
5. **Network/SSRF boundary.** The SDL URI is data, not permission for arbitrary
   egress. A supporting backend must apply its canonical egress policy before
   fetching, reject disallowed hosts/addresses and DNS rebinding, revalidate
   every redirect, bound redirects/bytes/time, stream to protected temporary
   storage, and verify the digest before parsing or installing the key. If that
   backend has no such policy/channel, it reports the profile unsupported.
6. **Trust and filesystem boundary.** Never use `apt-key` or a global trusted
   keyring. Render a dedicated source file and `signed-by` keyring at
   deterministic backend-owned paths; reject unowned collisions and symlinks,
   use restrictive creation/atomic replacement, and clean up only owned files
   on failure. Reconciliation must be idempotent and serialize through the
   target package manager's existing lock rather than racing concurrent
   updates.
7. **Process/argv boundary.** Render structured source data, never shell text.
   Package-manager and GPG invocations use fixed executables, argument arrays,
   no shell, `--`/manager-specific end-of-options handling, bounded stdin/files,
   controlled environment and working directory, and timeouts. Repository
   URLs, keys, packages, or versions never become executable fragments. No
   credential is permitted in SDL, environment, argv, or generated filenames.
8. **Secret/auth surface.** Public key bytes and digests are non-secret. Private
   repository credentials, bearer tokens, client keys, proxy credentials, and
   private signing keys are unrepresentable in this profile. Repository URIs
   become scenario/snapshot data visible through existing authorized reads, so
   authors must not use credential-bearing or secret locators. A future private
   repository needs the existing secret-reference/binding discipline and a
   separately governed profile; it must not add a password field here.
9. **Backend return and error envelope.** `_call_backend_apply()` remains the
   sole acceptance boundary. Invalid/missing observation, digest mismatch,
   package mismatch, malformed result, or native failure returns the baseline
   snapshot with a coarse addressed diagnostic. Diagnostics, audit, API 422/500
   envelopes, and logs may name package/repository profile and stable reason
   code, but never key bytes, response bodies, full URIs with query data,
   rendered files, argv, native stderr, exception text, or tracebacks.
10. **Persistence/observability.** Only the validated safe package/repository
    projection, value-free provenance, and typed observation disclosure enter
    snapshots/stores. Download buffers, key material, package-manager caches,
    output, and temporary files remain backend-private. Existing strict control
    plane authentication, roles, target binding, request-size/idempotency
    guards, and audit apply; authentication does not make unsafe payloads safe.

## Gotchas And Anti-Patterns

Avoid:

- encoding `repo=...;key=...`, JSON, YAML, a `deb` line, or a command in
  `source`, `purl`, or another string;
- treating purl, HTTPS, a key URL, a short key id, TLS success, package install
  success, or plan echo as repository/key integrity or realization evidence;
- accepting an unpinned key, trusting a global keyring, calling `apt-key`, or
  allowing an authored root path;
- using a generic `url/key/options` bag across APT and RPM-family managers;
- duplicating one repository under a new top-level runtime family, concern,
  compiler resource, DTO, manifest flag, exception tree, store, or logger;
- selecting the repository from package name, OS hints, backend defaults,
  ambient environment, or the controller host;
- silently accepting conflicting duplicate package/repository rows or relying
  on list order;
- passing a rendered source line to a shell, interpolating fields into argv
  fragments/filenames, or logging subprocess output and downloaded key bytes;
- adding credentials to the URI, SDL, plan, snapshot, environment, command
  line, audit event, fixture, or diagnostic; or
- claiming `runtime-packages` support when only default-repository packages are
  implemented or when repository/key readback is absent.

## Non-Goals And Implementation Boundaries

- This preflight does not implement models, schemas, validators, backend
  materialization, APTL changes, or conformance tests.
- The issue does not standardize all package managers, package-name/version
  grammars, dependency resolution, repository mirrors, pin priorities,
  authenticated/private repositories, proxies, source packages, key rotation,
  revocation, transparency, or offline bundles.
- It does not reinterpret or remove the existing `source`/`purl` fields, import
  raw SBOM/package-manager output, or turn package repositories into reusable
  `Source`, build provenance, experiment evidence, or artifact-requirement
  graphs.
- It does not require in-repository reference or libvirt support. Those
  backends remain honest/unsupported until they implement the whole declared
  profile and independent observation contract. Downstream APTL owns its
  privileged runner, egress controls, rollback, and actual cutover.
- Backend-specific repository filenames, keyring paths, cache layout, command
  choice, privilege mechanism, transaction/rollback implementation, and host
  configuration remain backend-private. Their effects must satisfy the
  portable profile; their native representation does not enter SDL.
