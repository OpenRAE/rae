# ADR-119: Consumer Parse of Supplied SDL Sources

## Status

accepted

## Date

2026-10-31

## Classification

Classification: FM1
Required artifacts: invariant list (Decision §6), unit tests (`implementations/python/tests/test_issue_1757_supplied_sources.py`)
Waivers: none

The decision adds static admission rules to import resolution.
It adds no state machine and no new graph semantics.

## Context

A consumer, such as the env-packs pack checker, checks an untrusted pack before it admits the pack.
Packs that `raes-pack-kit add` makes have `local:` imports with digest pins and a `raes.lock.json` file.
RAES 10.0.0 has no safe public operation for these packs:

- `parse_sdl_file()` reads the root, the imported modules, `raes.lock.json` and `raes-trust.yaml` by pathname.
- A `raes-trust.yaml` file in the pack can trust a registry. An `oci:` import then makes network requests.
- Digest pins and lock records are optional.
- `language_diagnostics(path=...)` returns diagnostics, not a scenario.
- An import refusal is an `SDLParseError` without a structured code.

[ADR-053](adr-053-sdl-module-composition-for-inventory-backed-scenarios.md) defines module composition.
Its first validation step loads trust and lock policy from the filesystem.
[ADR-071](adr-071-reusable-asset-trust-and-integrity-policy.md) separates integrity from authenticity.

## Decision

### 1. One public consumer operation

`raes.parser.parse_sdl_sources(sources, root, *, source_format, migration_policy, limits)` parses SDL from caller-supplied bytes.
The `raes` package exports it.

- `sources` maps canonical POSIX relative paths to bytes.
- `root` is the path of the root document in `sources`.
- The result is a semantically validated `Scenario` or `ExpandedScenario`.
- No option skips semantic validation, trusts a registry or makes pins and locks optional.

The operation uses the existing source parser, composition coordinator and semantic validator.

### 2. One source context for the request

`raes._supplied_sources.SuppliedSources` holds an immutable copy of the supplied bytes.
`CompositionTraversal` carries it through the import graph, together with the budget.

- Each document has the virtual path `/<logical path>`. All path operations are lexical.
- A relative import resolves against the directory of the importing document. The result must stay in the source set.
- The lock of a document is the `raes.lock.json` entry in the same directory. No other directory supplies a lock.
- The operation decodes a lock only for a document that has imports.
- The operation never reads `raes-trust.yaml`.

The OCI module cache and the source context share one path-confinement function.

### 3. Admission at each import edge

In a supplied-source parse, each import edge at each depth must satisfy these rules:

1. The normalized source starts with `local:`. Other sources, which include `oci:` and `locked:`, are refused before resolution.
2. The import has a digest pin of the form `sha256:<64 lowercase hex digits>`.
3. The pin equals the SHA-256 digest of the supplied bytes of the target.
4. The importing document has a lock, and the lock is valid `raes-lock/v1` JSON.
5. Exactly one lock record has the key of the import: source, namespace and requested version.
6. That record agrees with the resolution: content digest, resolved source, module id, module version and export hash. Its manifest digest and signer id are empty.

The existing version, parameter, descriptor, export, namespace, revision, cycle, collision and budget checks also apply.

### 4. Typed refusal

`SDLImportError` derives from `SDLParseError`.
Its `code` attribute is an `SDLImportErrorCode` value.
Its diagnostic has the same code, the path of the importing document and the JSON Pointer of the import.

The existing import checks of the authoring paths raise the same type with their existing messages.
The shared path-confinement message no longer names the path.
New refusals use fixed messages without authored values.

| Code | Condition |
| --- | --- |
| `sdl.import.source-refused` | The source class is not admitted on this path. |
| `sdl.import.phase-refused` | A supplied root carries `materialization_provenance`. |
| `sdl.import.path-invalid` | The path is empty, absolute or has a drive or NUL, or it escapes its base. |
| `sdl.import.source-missing` | The target document is not available. |
| `sdl.import.source-unreadable` | The target file cannot be read. |
| `sdl.import.local-disabled` | The trust policy disables unsigned local sources. |
| `sdl.import.registry-untrusted` | The trust policy does not allow the registry. |
| `sdl.import.descriptor-missing` | The imported unit has no module descriptor. |
| `sdl.import.version-mismatch` | The module version does not satisfy the requested version. |
| `sdl.import.parameter-refused` | The module does not declare an import parameter. |
| `sdl.import.digest-missing` | The import has no digest pin. |
| `sdl.import.digest-invalid` | The digest pin is not well-formed. |
| `sdl.import.digest-mismatch` | The pin or the lock digest does not match the content. |
| `sdl.import.lock-missing` | No lock applies to the importing document. |
| `sdl.import.lock-invalid` | The lock or a lock record is not valid. |
| `sdl.import.lock-record-missing` | No lock record matches the import. |
| `sdl.import.lock-ambiguous` | More than one lock record matches the import. |
| `sdl.import.lock-mismatch` | The lock record does not agree with the resolution. |
| `sdl.import.namespace-invalid` | The namespace is reserved or makes an invalid identifier. |
| `sdl.import.revision-mismatch` | The semantic revision differs from the root revision. |
| `sdl.import.export-invalid` | The module descriptor exports an unknown or undefined name. |
| `sdl.import.collision` | Two imports declare the same identifier. |
| `sdl.import.cycle` | The import graph has a cycle. |
| `sdl.import.budget-exceeded` | The composition exceeds a resource limit. |

### 5. One lock decoder

`decode_lockfile()` decodes lock bytes on the filesystem path and in the source context.
It uses `parse_bounded_json_object`.
It refuses duplicate members, non-finite numbers, excess size or depth and an unsupported schema version.
In a supplied-source parse, lock bytes count toward the composition byte budget.

### 6. Invariants

- **I1** A supplied-source parse calls no filesystem, network, subprocess or environment function. Module loading at first use in a process is outside this invariant.
- **I2** Each admitted import at each depth is `local:`, has a pin and has exactly one matching record in the lock of its importing document.
- **I3** The pin, the lock content digest and the digest of the parsed bytes are equal.
- **I4** A refused import raises `SDLImportError` with a code from §4, and no registry request occurs.
- **I5** The result passed full semantic validation.
- **I6** A root with `materialization_provenance` is refused.
- **I7** `parse_sdl`, `parse_sdl_file` and the editor operations keep their admission rules. Only §5 lock decoding becomes stricter.

## Alternatives Considered

- **A flag on `parse_sdl_file()`.** It still reads pathnames, and a file can change between the check and the use.
- **A resolver callback.** A callback can select sources and weaken admission.
- **Reuse of the OCI verified-source bundle.** It inherits the root lock, and its path functions read the current directory.
- **An extension of `language_diagnostics()`.** It returns diagnostics, not a scenario.

## Consequences

### Positive

- A consumer can admit kit-composed packs through a public operation.
- A consumer handles each import failure by its code, not by message text.
- Authoring and consumer paths share one resolver and one lock decoder.

### Negative

- A lock with duplicate members or an unsupported schema version now fails on the authoring path too.
- A pack must contain a lock for each directory that has an importing document.

### Risks

- The parse does not authenticate the root document or the publisher.
- The returned model is mutable, so it is not a durable admission token.
