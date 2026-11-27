# Issue 1757: Consumer Parsing of Pinned Local Imports

Architecture guidance for issue #1757. The supplied issue is the contract;
there is no attached requirement. This note describes boundaries for an
unimplemented operation, not an implementation plan or a claim of admission.

## Decision and ownership

Add a public consumer parse operation owned by `raes.parser`, exported through
`raes`'s existing lazy public facade. It accepts caller-supplied bytes and
logical source identities and returns the existing semantically validated
`Scenario` or `ExpandedScenario`. It must use the existing source parser,
module composition coordinator and semantic validator. Do not create a pack
model, alternate SDL grammar, second composition engine or consumer scenario DTO.

This is a stricter admission boundary alongside ordinary authoring APIs.
Preserve `parse_sdl`, `parse_sdl_file`, editor operations and CLI resolution
behavior. The consumer operation offers no semantic-validation skip, registry
opt-in, optional pin/lock switch or fallback to authoring resolution.

Build on [ADR-053](../../decisions/adrs/adr-053-sdl-module-composition-for-inventory-backed-scenarios.md)
without inheriting its filesystem/workspace-policy discovery step. Keep the
identity, integrity and authenticity distinction in
[ADR-071](../../decisions/adrs/adr-071-reusable-asset-trust-and-integrity-policy.md):
a supplied digest and lock demonstrate consistency with supplied bytes. They
do not authenticate the publisher, establish root-document trust, grant host
authority or prove the scenario safe to execute.

## Byte boundary and recursive policy

The root, every reachable module and every applicable lock come exclusively
from immutable bytes supplied for this call. A simple in-memory inventory is
sufficient. Keep source and lock associations stable for the whole request;
capture each admitted source once and hash and parse that same byte sequence.
Never reopen a source or hash rendered YAML, normalized text, a
semantic scenario digest or an OCI archive in place of local module bytes.

Source IDs are logical pack-relative names. Resolve relative imports against
the importing document with pure lexical operations under an explicit bundle
root. Reuse the normalization/confinement semantics of
`module_registry/_verified_sources.py`, including nested sibling references
that remain inside the bundle. Reject root escape, absolute/drive/UNC paths,
NULs and ambiguous inventory keys after normalization. Do not call
`Path.resolve`, `absolute`, `expanduser`, `exists`, `stat`, `open`, `getcwd`,
environment lookup or any filesystem-backed canonicalization. Preserve
checkout-independent POSIX identities in provenance and diagnostics.

At **every import edge**, require a normalized `local:` source before target
lookup or source dispatch. Reject `oci:`, `locked:`, URLs and unknown schemes,
including a `locked:` reference that would eventually select a local source.
The deprecated `ImportDecl.path` spelling already normalizes to `local:`; if
accepted, it passes exactly the same pin, lock and confinement gates.
Pack-supplied `raes-trust.yaml` cannot authorize anything and is not loaded.

Lock selection is part of the supplied source context, scoped to the importing
document. Preserve directory-local lock association when modeling existing
file parsing; a shared pack lock is usable only with an explicit association.
Never silently inherit a root lock, search ancestors or substitute a lock for
another module. `resolve_lock_records()` currently generates direct-import
records only; it is not a recursive consumer-admission operation.

Require an explicit well-formed SHA-256 pin and exactly one matching lock
record for every reachable edge, including repeated imports and nested modules.
Use the incumbent record key `(normalized_source, namespace,
requested_version or '*')`. Bind its content digest to both the pin and the
exact source bytes, and compare its resolved local identity, module ID/version
and export hash with the actual resolution. Reject absent, ambiguous, malformed
or stale records. An unused unrelated lock record is not an import and must
never trigger resolution. Local records legitimately have empty OCI manifest
and signer fields; do not require OCI metadata or claim signature verification.

Decode supplied locks with `raes_contracts.json_ingress.parse_bounded_json_object`
before `Lockfile.model_validate`: reject duplicate JSON members, non-finite
numbers, excessive size/depth, closed-key violations and unsupported versions.
`Lockfile.schema_version` is currently a plain string with a default, so model
construction alone does not reject an unsupported version; compare the
effective version with `LOCKFILE_SCHEMA_VERSION`. Reuse `Lockfile`/`LockRecord`,
not a new lock schema. Apply caller-selected limits consistently to locks as
well as SDL, including aggregate lock work; repeated locks must not create an
unbounded parse/scan loop.

## Cross-cutting layers and canonical incumbents

Package paths here are relative to `implementations/python/packages/`.

| Layer / incumbent | Guardrail |
| --- | --- |
| Source ingress: `raes/parser.py`, `_yaml_loader.py`, `_source_profile.py`, `_source_validation.py`, `_mapping_key_analyzer.py` | Reuse UTF-8 and byte bounds, YAML 1.2 Core, safe tags, mapping-key collision checks, finite JSON-domain construction, normalization and strict migration defaults. Apply them to root and imported bytes; do not replace them with `yaml.safe_load`. |
| Authored shapes: `_base.py::SDLModel`, `_module_declarations.py::ImportDecl/ModuleDescriptor`, `scenario.py::Scenario` | Preserve closed fields, portable IDs/namespaces, version constraints, parameters and descriptors. Admit authored source before constructing expanded models. Reject supplied expanded/instantiated/materialized phase carriers and forged provenance; the `materialization_provenance` dispatch in ordinary `parse_sdl` must not bypass consumer import admission. |
| Resolution: `module_registry/models.py::ResolvedModule`, `module_registry/resolution.py`, `_digests.py` | Reuse record identity, version satisfaction, descriptor/export hashing and allowed-parameter checks. Strengthen pin/lock requirements only for this consumer boundary. `raes_contracts.digests` owns SHA-256; `json_serialization` owns the incumbent export-hash encoding (ADR-118). No alternative digest framing. |
| Composition: `composition/_expand.py::expand_sdl_modules`, `_import_admission.py::admit_import_source`, `_composition_budget.py` | Preserve module-local structural/effect-target admission, semantic-revision agreement, parameter binding, exports/private-symbol rules, namespacing, collision and cycle refusal. Carry one policy/source context and aggregate budget throughout recursion, including leaves without imports. Keep ancestry separate from source memoization: shared dependencies are not cycles, but each expansion still consumes budget. |
| Final validation: `validator.SemanticValidator`, `_declarations.py`, `_declaration_sources.py` | Run the ordinary full semantic pass after composition; preserve declaration/source ranges, warnings, field presence and the validated flag. Descriptor/digest checks and model construction are not semantic validation. A mutable returned model is not an enduring admission token. |
| Secrets, environment and configuration: `runtime_values.py::enforce_observed_value_redaction`, `runtime_environment.py`, `runtime_generated_value.py`, `runtime_configuration.py`, `raes_contracts.secret_references` | Preserve redaction classifications, literal/`value_from` exclusions, environment-name uniqueness and generated-output reference checks through the same SDL models and validator. These describe scenario data; they never read the host environment, resolve operator secrets or realize generated outputs during parsing. |
| Authority and host boundary: existing authored authorization models; runtime/processor admission remains downstream | Parsing grants no application RBAC, tenant/principal authority, preparation permission, listener publication or execution authority. No network client, socket, subprocess, shell, CLI, archive extraction, secret provider or host probe is involved; thus no token reaches argv, URLs or process environment. Do not add runtime/control-plane dependencies to `raes`. |
| Portable output: `phase_contracts.py::ResolvedImportProvenance/ExpansionProvenance`, `_composition_provenance.py` | Preserve source/digest formats and bounded provenance fields. These reject absolute host paths, registry userinfo and malformed digest spellings after resolution; validate consistently before reaching them. Do not invent a trusted-pack flag or parallel provenance record. |
| Errors and logs: `_errors.py`, `_model_diagnostics.py`, `_language_diagnostics.py`, `raes_contracts.errors/operational_logging` | Extend the SDL error family; reuse source diagnostics and shared logging policy. See the refusal boundary below. No logging setup or new error envelope in the library. |
| Persistence and configuration: `module_registry/models.py` workspace readers/writers; OCI cache/extraction helpers | None is an admissible I/O path for this operation. No temporary files, cache, lockfile creation/update, trust-policy discovery or persistent repository. Caller-owned capture/storage stays outside parsing. |

## Refusal boundary

Provide a public typed import refusal under `SDLParseError` (and therefore
`SDLError` / `InvalidInputError` / `RaesError`), with a stable structured code.
Retain compatibility with callers catching existing bases. Reuse
`SDLParseDiagnostic` for source, pointer and range; expose the code without
requiring message parsing. Do not introduce another exception hierarchy or
error DTO. Follow [ADR-116](../../decisions/adrs/adr-116-shared-exceptions-and-operational-logging.md).

Codes must distinguish disallowed source, missing/invalid/mismatched pin,
missing/invalid/ambiguous/mismatched lock, unavailable source, path escape and
invalid imported content/descriptor. Import graph, budget, parameter, export
and namespace failures also need structured refusal, not a message-only
escape. Attach codes at the owning checks; never infer them from exception
text or collapse every failure into “invalid pack.” Preserve useful underlying
diagnostic codes. Ordinary root syntax/model errors and final scenario semantic
findings retain their established SDL error meanings.

Expose bounded, value-free refusal messages and safe logical source metadata.
An import source or lock field may contain credentials or control characters;
do not echo it merely because it is called an identifier. Never serialize
Pydantic inputs, raw YAML/JSON, parameter values, foreign exception text or
tracebacks into a consumer envelope. `_model_parse_error` bounds text but does
not redact arbitrary validator prose: inspect the consumer-facing error path.
Map expected foreign/value failures once at their owning boundary; retain
cancellation and programming failures. Library code does not configure logging
or log and rethrow the same failure; use the shared value-free logging helpers
only when the existing policy calls for a record. CLI/MCP/API handlers continue
to own their established envelopes.

## Extensibility and repository guardrails

The needed seam separates **source bytes and logical identity/lock lookup**
from composition and import policy. Keep it request-scoped and thread it
through the existing coordinator. A future caller can supply archive-captured
or pre-opened bytes through that seam without adding a filesystem adapter or
changing the fixed local-only policy requiring pins and lock records. It must
not be an arbitrary resolver callback capable of selecting sources or weakening
admission.

`_VerifiedSourceBundle` demonstrates immutable captured-source consumption,
but it is an OCI cache implementation, not a public consumer contract: its
capture and identity helpers include filesystem/cwd operations and its lock
inheritance has different semantics. Reuse/extract the pure mechanics with a
named module owner and an interface intended for cross-module use. Do not
expose cache internals, import private siblings or add facade aliases just to evade
[ADR-117](../../decisions/adrs/adr-117-ratcheted-structural-checks.md).
Respect ADR-015's file cap, ADR-036's package direction and the canonical
`tools/policy/adr_policy.yaml`, `import_contracts.toml` and structural baseline;
do not expand debt baselines to accommodate the feature.

The SDL source/model and lock formats stay incumbent. Published schema changes,
if actually needed, follow ADR-009 and schema-publication ledger/generated-bundle
equality checks; do not fork schemas to express a Python operation's policy.
Use `.ground-control.yaml`, `.gc/plan-rules.md` and existing verification tools.
Keep this requirement-free issue as the delivery contract; do not fabricate a
requirement UID or traceability. Public API documentation belongs in the
existing parser/API surfaces when the operation ships, without claiming the
authoring APIs are safe for untrusted consumers.

## Acceptance evidence and non-goals

Required evidence includes an attributable `raes-pack-kit add` output captured
as bytes, with its pins and lock associations preserved. Existing env-packs
module fixtures under `implementations/python/tests/data/issue_1481` cover
module content, not that producer's pack/lock output. Verify its digest spelling, export hash
and nested-lock layout; a hand-built happy path alone cannot prove producer
compatibility. No external checkout is needed for this preflight.

Use targeted cases in the existing parser/module-registry, source-format,
import-safety/editor and phase-contract test families. Cover root and nested
scheme refusals (including locked-to-local), every pin/lock failure, ambiguous
locks/paths, sibling paths, cycles versus shared dependencies, resource bounds,
secret/env-shape rejection and safe diagnostics. Successful and failing calls
must be exercised with filesystem, environment, network and process access
trapped, including workspace-policy readers and path canonicalization. Preserve
authoring/editor/CLI behavior. CI owns full, integration and fuzz suites.

Non-goals: implementing env-packs admission or LilRAE integration; pack-kit
generation; archive extraction or secure file capture; registry/signature
retrieval; publication; root/publisher authentication; host sandboxing; new
lock/trust/SDL schemas; compilation, instantiation of the root, provisioning,
execution, secret resolution, persistence or workflow redesign. The caller
still owns secure capture and any later decision to execute the returned SDL.
