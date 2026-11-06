# ADR-076: Portable SDL Identifiers and Canonical Addresses

## Status

accepted

## Date

2026-07-11

## Classification

Classification: FM2
Required artifacts: ADR, normative SDL specification, published schema updates,
source-ranged migration diagnostics, cross-stage identity tests, and targeted
property/differential tests
Waivers: No new runtime service, persistence layer, authentication mechanism,
or general-purpose identifier registry is introduced.

## Context

SDL references already fail closed when a bare name is ambiguous, module
composition rewrites imported symbols into namespaces, and the processor emits
canonical runtime addresses. The lexical inputs to those mechanisms are not yet
coherent.

Ordinary section keys may be empty or contain whitespace, delimiters, mixed
case, or arbitrary Unicode. Dots currently mean several different things:
section qualification, a nested entity path, the workflow/step boundary, an
authored node name, and a generated module namespace. Runtime-family ids use
the shared `require_symbol` helper, but that helper only rejects empty values
and variable placeholders. Compiler addresses then join unchecked identity
parts with dots.

This creates two classes of failure. First, a valid declaration may be
impossible to name portably. Second, two different declaration paths can render
as the same string, especially after nested module composition. Existing
indexes often collect strings into sets or dictionaries; if two declarations
already rendered to the same string, those containers erase the evidence of
the collision.

The repository already has the right cross-cutting owners: the SDL section and
reference catalogs, the source-marked YAML loader, published SDL schemas,
`SemanticValidator`'s declaration index, the module symbol/composition layer,
the runtime-family registry, the objective-window semantic IR, the processor
compiler, and the language-service diagnostic envelope. The identifier contract
must strengthen those owners rather than create parallel schemas, reference
resolvers, exception types, or workflow-specific naming rules.

## Decision

### 1. Define one portable local-identifier grammar

A symbol-defining local identifier is an ASCII string matching:

```text
portable-id = id-start *63id-char
id-start    = %x61-7A / DIGIT
id-char     = id-start / "-" / "_"
```

Equivalently, it is a full-string match for
`^[a-z0-9][a-z0-9_-]{0,63}$`. Implementations must use full-match semantics;
they must not rely on a regex engine's `$` anchor alone, because some engines
also match `$` immediately before a trailing line terminator. The JSON Schema
form combines `minLength`/`maxLength`, a valid first-character constraint, and
rejection of every character outside `[a-z0-9_-]` so the same contract rejects
trailing newlines, NULs, and other controls without depending on engine-specific
anchor behavior.

The spelling is exact. SDL does not trim, lowercase, case-fold, Unicode-normalize,
escape, or otherwise repair an identifier. Uppercase, non-ASCII, whitespace,
control characters, `.`, `/`, `:`, and variable placeholders are invalid in a
local identifier. The existing 35-character node-id limit remains a stricter
node-specific constraint on the authored local node segment; composition-added
namespace segments do not consume that local limit.

The grammar is a string grammar. Because `sdl-yaml/v1` applies YAML 1.2 Core
scalar resolution before model construction, an all-digit authored key must be
quoted to remain a string; decoders must not coerce a numeric key into an id.

The grammar applies by semantic role, not by field spelling. It covers:

- `Scenario.name`;
- declaration keys in map-valued SDL sections, including variables;
- nested declaration segments such as entity children, node-local roles,
  workflow steps, participant action preconditions/effects, view transitions,
  and temporal/disclosure records;
- explicitly addressable nested names such as named services, ACL rules, and
  content items;
- the scenario-level `forwarding_agents[*].forwarding_agent_id` list identity;
- every primary and addressable child id in the node-runtime family registry;
- family-local stable ids validated through `require_symbol`, after confirming
  that the field is an ACES-local record key rather than provider/native data;
- any later field that becomes a declaration key or canonical-address segment.

It does not apply merely because a field is named `name` or ends in `_id`.
Display labels, descriptions, usernames, DNS names, URLs, file paths, LDAP DNs,
environment-variable names, versions, contract ids, CVEs, package coordinates,
provider/native ids, external ids, and opaque evidence/provenance refs retain
their owning contracts. If a value must be both human-facing data and an
addressable symbol, its symbol role is the portable id; display or provider data
must remain a separate field rather than weakening the id grammar.

Declaration identity and reference values remain distinct. A reference-valued
field may continue to accept a full-value variable placeholder where its owning
contract already permits one; instantiation may select a declared target, but it
must never rename or create the target. Variable declarations, module parameter
names, import-parameter keys, and
`scenario-instantiation-request-v1.parameters` keys use the same portable-id
grammar. Parameter *values* retain their owning field contracts and never enter
an address segment.

Applying the lexical grammar does not make every stable local id a generic
relationship/objective target. Canonical addressability and targetability are
separate catalogued properties: a node-local role can have a stable internal
address without becoming a valid generic target.
`Scenario.name`, `module.id`, and import namespaces identify document and
composition boundaries; they do not become in-scenario generic targets merely
because they use the same segment grammar.
The semantic-role audit must account for every ACES-local declaration identity,
including list-valued and deeply nested records; it must not infer declaration
status from a field suffix or stop at the existing generic-reference targets.
Each in-scenario declaration identity receives one owner-relative canonical
address, while the existing owning catalog records whether that address is
externally targetable.

### 2. Give modules explicit, segment-safe identity

`module.id` uses exactly `portable-id "/" portable-id` for
`publisher/name`. Every import declares an explicit `namespace`, and that
namespace is one `portable-id`; filenames, source paths, OCI repository names,
or module display text are never silently converted into namespaces.

An imported unit that participates as a module declares its module descriptor;
the registry must not manufacture `module.id` from a filename or source path.
`module.exports` keys are existing section-catalog literals, not user ids, and
each exported member must resolve to an actual declaration of that section.
Nested export members such as entity paths are validated as typed declaration
paths, not blindly with the local-id regex and not by arbitrary `getattr` lookup.
The list-valued `forwarding_agents` section participates by its
`forwarding_agent_id`: composition rewrites that id, preserves the list value
shape, and detects collisions by canonical address before concatenating lists.
It must not be dropped because the existing map-section composition loop does
not enumerate it, converted into a public map-shaped SDL section, or exempted
from exports and private-prefix handling.

Nested imports retain namespace structure as a tuple of segments. Composition
may render that tuple as a dotted prefix, but only the composition layer may
create such generated qualified identities. The generated `__private` segment
is reserved to composition and is never valid author input. Raw/normalized SDL
declarations therefore contain local ids, while expanded SDL may contain
validated generated namespace paths. A local-id validator must not be applied
blindly to trusted expanded keys, and expanded-key acceptance must not become a
way for raw callers to bypass local-id validation.

The existing `Scenario` / `ExpandedScenario` distinction is the phase and trust
boundary. Public YAML, normalized JSON, and direct model construction validate
`Scenario` local declarations. Only the composition path may construct an
internal `ExpandedScenario`, after validating every imported `Scenario`, module
descriptor, import namespace, and namespace tuple. There is no caller-settable
`expanded=true`, validation-context flag, or permissive fallback that authorizes
dotted declarations. `ExpandedScenario` is not a second public authoring
contract.

Instantiation preserves the identity phase of its input. A flat authored
scenario produces local keys; a composition-expanded scenario produces the same
validated generated namespace paths. The published instantiated-scenario
contract may therefore describe generated qualified keys, but `parse_sdl` must
never use that derived-document shape to admit dotted raw declarations.
Rebuilding the concrete model must preserve the namespace tuple and prior
collision proof rather than treating the rendered dotted key as trusted by
itself.

### 3. Treat dots as address syntax, not identifier content

Canonical declaration addresses are built from typed path parts. Examples are:

```text
<section>.<qualified-symbol>
entities.<qualified-entity-path>
forwarding_agents.<forwarding-agent-id>
nodes.<qualified-node>.roles.<role-id>
nodes.<qualified-node>.services.<service-id>
infrastructure.<qualified-infra>.acls.<acl-id>
content.<qualified-content>.items.<item-id>
nodes.<qualified-node>.runtime.<family>.<id>[.<child-family>.<child-id>...]
workflows.<qualified-workflow>.steps.<step-id>
```

`<qualified-symbol>` is a composition-generated namespace path followed by one
local id. Fixed words such as `runtime`, `services`, `acls`, `items`, `steps`,
and registered runtime collection names are grammar literals in their typed
positions. They are not globally banned as local ids; typed construction and
canonical collision detection provide the boundary. Generated `__*` control
segments remain reserved.

Bare references and compact `<qualified-workflow>.<step-id>` window references
are lookup aliases, not additional canonical identities. A qualified reference
resolves by exact canonical-address lookup. Resolution must not guess by first
match, declaration order, source locality, delimiter partitioning, or a
longest-node-name heuristic.

Every declaration is entered into the canonical-address index with its kind and
source provenance before aliases are deduplicated. Two distinct declarations
that render to the same canonical address are a fatal collision, even if a set
or dictionary would otherwise collapse them. This covers collisions between
root and imported declarations, nested entities and namespace paths, and
namespace paths that resemble nested collection paths.

Processor runtime addresses remain derived artifacts, distinct from SDL
authoring addresses. Existing compiler address builders must consume validated,
structured identity parts, preserve namespace tuples, and reject duplicate
derived addresses before constructing resource dictionaries. Planner,
snapshot, and persistence layers consume those canonical strings; they do not
reinterpret or repair SDL identifiers.

The compiler boundary must enforce the identity and duplicate-address invariants
even when a caller intentionally skips unrelated semantic checks. The planner
must not merge runtime-family dictionaries with last-write-wins assignment.
Existing planning, backend-result, runtime-snapshot, and persistence contracts
must preserve address equality across every redundant representation: a
snapshot map key equals its embedded `SnapshotEntry.address`, and an operation
or changed-address value denotes the same compiler-owned address used by its
resource or snapshot transition. A mismatch is a contract failure at the
existing `PlanOperationModel` / `RuntimeSnapshotEnvelopeModel` /
`OperationStatusModel`,
`aces_runtime.backend_calls`, or `aces_runtime.control_plane_store` boundary; it
is never repaired by choosing one copy or by parsing the address as an SDL
reference.

### 4. Enforce the contract at every existing ingress

The hand-governed schemas under `contracts/schemas/sdl/` remain the normative
machine-readable authority. Identifier-bearing map keys use scoped
`propertyNames` constraints and identifier-bearing fields use the same pattern.
Literal/native maps and reference-keyed maps must not acquire those constraints.
This includes `scenario-instantiation-request-v1.parameters`; its values remain
unconstrained JSON values at that boundary. The Python `schema_bundle()` must
continue to generate identical schemas.

Schema constraints are phase-specific. The authoring-input schema applies the
local-id grammar to authored declaration keys. The instantiated-scenario schema
must separately describe composition-generated qualified top-level keys while
continuing to constrain local nested segments. Reusing the authoring
`propertyNames` fragment blindly for instantiated output would reject valid
expansion; reusing the instantiated fragment for authoring would admit forged
dotted identities. Generated schemas, the hand-governed copies, and the schema
publication manifest remain synchronized through their existing checks and
change-ledger rules.

`MappingScope.LITERAL` only means "do not normalize this key as a structural
field"; it is not an identity classification. Source validation must distinguish
declaration keys, reference-keyed maps (for example script event bindings), and
native/data maps (for example labels, facts, driver options, and extensions).
Only the first receives the local-id rule. Reference-keyed maps use their owning
reference grammar, and native/data maps preserve their existing key contract.

The same rule is enforced at these existing boundaries:

- the source-marked YAML/key preflight, for precise key ranges and strict
  `sdl-yaml/v1` behavior;
- Pydantic model construction, so direct Python and normalized-JSON callers do
  not bypass source parsing;
- import-shape validation before resolution, and descriptor/lock validation at
  the existing registry boundary before the values are used for composition or
  filesystem output;
- module expansion and the semantic declaration index, for generated-address
  collisions and exact reference resolution;
- instantiation, which rebuilds the concrete model and re-runs semantic checks;
- language-service completions, references, edits, formatting, and diagnostics;
  and
- compiler/canonical-serialization boundaries, which may consume identifiers
  but never normalize them.

Per-document `SDLParserLimits` enforcement is not an aggregate import-graph
budget. A single request-scoped composition budget, carried through the existing
`SDLSourceParseOptions` and registry/composition recursion, must additionally
bound import depth and document count, aggregate decoded bytes and constructed
object/YAML nodes (which conservatively bounds declaration count),
namespace depth, and rendered canonical-address size. Exhaustion fails before
further expansion or compilation through the existing bounded import/parse
diagnostic path. This extends the source-limit seam; it is not a new limits
subsystem, an environment-selected language profile, or a backend setting.

The existing `VARIABLE_NAME_PATTERN`, runtime `require_symbol`, and the duplicate
stable-id helper in `runtime_ssh_server` must converge on this contract instead
of remaining competing regex/validator families. Every stable-id helper caller
is audited by semantic role before the shared helper is tightened; an
incorrectly classified provider/native field must return to its owning validator
rather than weakening the portable grammar. Existing object-name, path, DNS,
environment-name, and provider/native validators remain distinct because those
values are data, not declarations.
Runtime-family discovery continues to come from
`RUNTIME_SERVICE_FAMILIES`; section and reference discovery continues to come
from the existing SDL catalogs and indexes. `tools/check_sdl_catalog_parity.py`
remains the whole-repository drift gate. The list-valued scenario-level
`forwarding_agents` identity surface remains catalogued explicitly and must not
disappear behind map-only key handling. The language service and MCP inspection
surfaces may retain partial-document presentation logic, but valid-document
definitions and references must come from, or be differentially checked against,
the same declaration index. Existing inventories are reconciled or parity-tested
at their current ownership boundaries; no additional section list, runtime
family list, reference-edge registry, or best-effort semantic resolver is
introduced solely for identifier validation.

### 5. Fail closed with the existing diagnostic and security boundaries

Lexically invalid declarations are structural errors. Canonical-address
collisions and reference ambiguity are static-semantic errors. They use the
existing `SDLParseError` / `SDLParseDiagnostic` and `SDLValidationError`
envelopes; no new exception hierarchy is added. Where source marks exist, a
diagnostic identifies the RFC 6901 path and offending declaration-token range,
whether that declaration is a mapping key or a scalar id field. A collision
diagnostic identifies both declarations and their source provenance.
The existing diagnostic records may gain optional related-source/provenance
fields for cross-file collisions; that is an envelope extension, not a parallel
error type. The authoring envelope must not be conflated with
`aces_contracts.diagnostics.Diagnostic`, whose owner is planner/runtime
reporting. `SDLInstantiationError` continues to wrap failures discovered while
rebuilding and revalidating the concrete model, and `ScenarioValidationError`
remains only the existing scenario-loader compatibility adapter. Import/model
validation must not leak a raw Pydantic `ValidationError` through parser or
language-service entry points.

Migration is explicit and non-lossy. Diagnostics may suggest a conforming id,
but ordinary parsing and `SDLMigrationPolicy.ACCEPT` do not silently trim,
case-fold, normalize Unicode, replace dots, or rewrite references. Any future
rename operation must update a declaration and every resolved reference
atomically, prove that the rename is injective, and fail on ambiguous or lossy
input.

Identifiers are public structural metadata, never a secret-bearing channel.
Diagnostics and logs may name a validated id. An invalid authored key is
untrusted input: any rendered spelling must be escaped and length-bounded, while
the structured source range remains the primary locator. Neither form may
include adjacent values, the whole document, parameter maps, trust material,
credentials, or tracebacks. Restricting valid identifiers to bounded ASCII
prevents control-character/log injection and prevents module ids or namespaces
from becoming path traversal or shell syntax; it does not make raw invalid-key
rendering safe.

Module trust, digest/signature verification, registry allowlists, source-size
limits, archive extraction containment, and local-import path containment remain
mandatory and unchanged. Authored namespaces and local module descriptors are
validated before import resolution. A remote descriptor can only be validated
after its bounded, digest-bound config is fetched; it must be validated before
signature acceptance, archive extraction, composition, lockfile emission, or
output/cache path construction. Module ids already flow into signature payloads,
OCI annotations, lock records, and OCI-layout directory names, so those consumers
must receive the validated value and must not re-sanitize it independently.
Validation of `module.id` does not make adjacent `version`, `source`, or
`root_file` values safe path components; their owning version, URL, archive, and
containment checks remain independently mandatory, and an output boundary must
validate or encode every component it places in a filesystem path.
Identifiers are not secret or environment-binding values, and the language
grammar is not selected through an environment variable, deployment setting, or
backend config. Existing OCI and host-tool realization seams retain fixed
list-form argv (never `shell=True`), bounded execution, runtime/tool allowlists,
and native-output redaction. The existing TechVault initramfs seam is narrower
but different: it places a derived hostname into a generated guest `/bin/sh`
script and must retain its dedicated `_shell_quote` boundary; no additional
identifier interpolation or general shell-command builder is introduced there.

Language-service/MCP symbol, pointer, and prefix arguments and control-plane
compiled-address path parameters remain caller-controlled even after the authored
grammar is tightened. They must be length-bounded at their existing entrypoint
limit/config seam, escaped when rendered, and resolved by exact index/snapshot
lookup. Identifier or migration results may return declaration names and source
ranges, but never adjacent parameter values or document fragments. The runtime
control plane continues to apply `ControlPlaneSecurityConfig` authentication,
authorization, and request guards; it does not parse a URL path value as an SDL
authoring reference or echo an unbounded invalid value in an error envelope.

Plan submission is a separate runtime trust boundary. `PlanOperationModel` and
its provisioning/orchestration/evaluation envelopes are authenticated wire
input, not proof that an address came from this compiler. Their existing
`ContractModel` / FastAPI conversion boundary is the incumbent shape gate, but
it currently provides closure rather than proof of canonical address
provenance. It must be strengthened, without adding parallel DTOs, to reject
non-canonical or overlong operation addresses, duplicate operation addresses,
dependency or startup-order entries that do not resolve in the admitted plan /
snapshot set, and address / domain / resource-type incoherence before
execution. Backend `ApplyResult` values and locally persisted snapshots are
rechecked independently; neither is trusted merely because an earlier boundary
validated the plan.

The reusable downstream seam is one bounded compiled-address contract in the
existing `aces_contracts.planning` boundary, consumed by processor plan models,
wire DTOs, runtime state, backend-result gates, and persistence loaders. The
processor's existing `_address` construction helpers remain the renderer and
must emit values accepted by that contract. The address-size bound is a named,
schema-visible contract constant shared by those consumers, not an environment
setting or a collection of endpoint-local limits. This is distinct from the
local SDL identifier validator: it validates compiler address form and size,
not authoring references or provider names.

Default 4xx rendering, `str(ValueError)` conflict responses, and caught backend
exception text are not currently a sufficient disclosure boundary. Paths that
can include caller- or backend-controlled address text must translate failures
through the existing bounded runtime diagnostic and redacted API envelopes and
must not disclose whole plans, payload values, credentials, tracebacks, or
unbounded address data.

Provider host/resource names continue through their existing driver-specific
mapping and validation. The portable SDL grammar rejects leading option markers,
path separators, whitespace, and control characters, but it is not a Docker,
libvirt, DNS, hostname, or cloud-provider naming contract. A provider name is a
derived value and never replaces the canonical SDL identity. Bounded provider
names must be deterministically collision-resistant for the complete canonical
address, for example a sanitized readable prefix plus a digest suffix; plain
truncation is not an identity-preserving mapping.

### 5.1 Formal obligations

Let `P` be the set of portable local identifiers, `N = P*` the finite namespace
paths generated by composition, and `Q = N x P` the qualified symbols. Let
`D(S)` be the declarations of a validated expanded scenario `S`, with each
declaration retaining its semantic kind and owner path. The typed canonical
address renderer `A_S : D(S) -> String` must satisfy document-scoped
injectivity:

```text
forall d1, d2 in D(S): A_S(d1) = A_S(d2) implies d1 = d2
```

This is proved operationally by retaining every declaration and its provenance
until collision checking completes; inserting rendered names into a set or map
before that check is not a proof. The renderer is not claimed to be globally
injective over untyped strings. Its domain includes the declaration kind,
owner-relative path, registered fixed segments, namespace tuple, and local id.

Instantiation parameters are identity-independent. If `instantiate(S, p)` and
`instantiate(S, q)` both succeed for parameter environments `p` and `q`, their
declaration-address domains are equal. Parameter values may select references
or data but cannot create, delete, or rename declarations:

```text
dom(A_instantiate(S, p)) = dom(A_instantiate(S, q)) = dom(A_S)
```

Every resolved reference must have cardinality exactly one in the typed
declaration index. Zero matches is unresolved; more than one is ambiguous.
Resolution order, source proximity, and delimiter partitioning do not alter that
cardinality.

Across processor, plan, backend, and snapshot stages, canonical addresses form a
commuting identity carrier: redundant representations must compare equal to the
compiler-emitted address, and a transition may mention only admitted addresses.
Provider naming is a projection from that complete address into a provider's
bounded name domain. It is never the inverse identity map and therefore retains
a deterministic digest of the complete source address.

### 5.2 Standards lineage and limits

The grammar notation follows RFC 5234 ABNF conventions. The segment/delimiter
separation is influenced by RFC 3986, but a canonical SDL address is not a URI
and does not inherit URI resolution, normalization, percent-encoding, or
equivalence semantics. RFC 6901 defines diagnostic JSON Pointer locations; a
pointer is not an SDL declaration identity or reference. RFC 8785 defines the
canonical JSON serialization used for document semantic identity; it does not
define SDL identifier equality or lineage.

Unicode Standard Annex #15 and Unicode Technical Standard #39 inform the
decision to avoid silent normalization and confusable-sensitive identifier
repair. ACES does not claim conformance to a Unicode identifier profile: SDL
structural identifiers deliberately use bounded lowercase ASCII, while display
and data fields retain their owning Unicode contracts.

This identifier decision does not claim or define Park bisimulation, labelled
transition-system equivalence, observational equivalence, or multi-agent
behavioral equivalence. Those concepts apply to the behavior and observation
semantics of scenarios, not to the lexical identity carrier established here.
Any future bisimulation-based scenario equivalence must state its transition
system, labels, observations, and equivalence relation independently; stable
injective addresses are supporting structure, not evidence of behavioral
equivalence.

Canonical SDL authoring semantic identity remains RFC 8785 over the validated
expanded authoring model.
Display/data strings retain their authored Unicode code points; only identifiers
are restricted to ASCII. The control-plane authentication/authorization gates
and atomic local snapshot store remain downstream consumers of compiled
addresses and gain no new authoring ingress. Compiled addresses may appear as
snapshot/audit keys and workflow URL path parameters, but runtime DTOs, backend
validators, and persistence must treat them as typed compiler output rather than
re-parsing or repairing authoring references. Downstream planner and backend code
may use the compiled address grammar for deterministic ordering or provider-name
derivation only at their existing, explicit seams.

### 6. Preserve the extension seams already present

Namespace depth is represented as a sequence (`namespace_path` already exists
in the objective/reference semantic IR), not inferred by repeatedly splitting a
rendered string. Composition, declaration indexing, semantic IR, and compiler
address construction carry that sequence until one canonical renderer produces
the external string. A new top-level section extends the existing
section/reference catalogs; a new runtime family extends
`RUNTIME_SERVICE_FAMILIES`; both then use the same local-id and address rules
automatically.

A future internationalized identifier grammar, escaping syntax, or different
case policy is a new language/contract decision with an explicit migration and
schema-version assessment. It is not an in-place widening of this regex.
The grammar and its length bound are therefore versioned language seams, not
runtime configuration parameters.

On acceptance, the normative SDL document model, section/reference/runtime
catalogs, diagnostics, variable/instantiation contract, composition guidance,
and parser guide must be reconciled in one change. In particular, the current
dotted-node and longest-match rules and the current implicit local-import
namespace behavior are superseded. Accepted ADRs remain immutable; conflicting
guidance in ADR-003 or ADR-053 is changed only through this explicit superseding
decision and corresponding normative documentation, not by editing their
accepted records in place.

## Guardrails

- Do not validate every `name`, `id`, or mapping key as an SDL symbol; classify
  the field's semantic role first.
- Do not implement the schema rule with a `$`-anchored pattern alone; prove
  parity for final line terminators, controls, and maximum length across YAML,
  Pydantic, and the published JSON Schemas.
- Do not treat `_mapping_scopes.MappingScope.LITERAL` as proof that a key is a
  declaration, or as proof that it is native data.
- Do not keep dotted authored node ids as a special case.
- Do not derive namespaces from paths or sanitize invalid ids into valid ones.
- Do not synthesize module identity from a descriptor-less import path, or treat
  module export section names as arbitrary attributes.
- Do not treat one validated path component as validation of an output path that
  also contains version, source, archive-member, or provider-native data.
- Do not expose a public trusted/expanded switch or accept authored dotted keys
  through `ExpandedScenario` as a convenience path.
- Do not make identifier grammar, normalization, or maximum length selectable
  through environment, backend, parser, or deployment configuration.
- Do not exempt synthetic wrapper/scaffold identifiers used by MCP, language
  service, tests, or fixtures; those callers enter through the same authoring
  contract and must use conforming local ids.
- Do not treat per-document parser limits as protection against an aggregate
  nested-import expansion; carry one bounded composition budget through the
  complete import graph.
- Do not parse qualified refs independently in each section with `split`,
  `partition`, or `rsplit`; resolve through the canonical declaration index.
- Do not let a set/dict insertion serve as collision detection after provenance
  has already been erased.
- Do not apply the authoring key regex to composition-generated instantiated
  keys, or use the instantiated key shape as an authoring bypass.
- Do not let compiler semantic-validation options bypass identity/collision
  checks, merge planner resources with last-write-wins behavior, or accept a
  snapshot whose map key differs from its embedded address.
- Do not treat authentication, a recognized address prefix, or Pydantic shape
  validation alone as proof that a plan, backend result, or persisted snapshot
  carries coherent compiler-owned addresses.
- Do not omit or map-convert `forwarding_agents` during composition merely
  because the incumbent composition registry is map-section-oriented; compose
  the list by its declared identity and preserve its published list shape.
- Do not add schema-only, Pydantic-only, or semantic-validator-only enforcement;
  raw YAML, normalized JSON, direct model construction, module expansion, and
  compiled output must agree.
- Do not add a second exception hierarchy, migration policy, section catalog,
  runtime-family registry, or workflow-step resolver.
- Do not change display labels, provider-native ids, paths, URLs, DNS names,
  environment names, or external contract identifiers to make them resemble
  SDL symbols.
- Do not use provider-safe runtime names as canonical SDL identities or assume
  the portable-id grammar satisfies every provider's length and hostname rules.
- Do not truncate provider names without retaining a deterministic digest of the
  complete canonical address.
- Do not surface raw Pydantic error renderings when they can include adjacent
  values; translate failures into the existing bounded diagnostic envelopes.
- Do not write an invalid key verbatim to logs or diagnostics; escape and bound
  its presentation and use the source range as the locator.
- Do not echo unbounded language-tool query strings, URL path parameters,
  document fragments, or instantiation values in identifier diagnostics.
- Do not expose raw backend exception text or complete invalid plan/payload
  values through 4xx responses, runtime diagnostics, logs, or audit events.
- Do not interpolate identifiers into new shell command strings; retain the
  dedicated quoting boundary on the existing generated guest-init script.

## Non-Goals

- Escaping arbitrary legacy identifiers inside the current dotted syntax.
- Automatic or best-effort renaming of existing scenarios.
- Case-insensitive or Unicode-normalized identity.
- New variable types, substitution syntax, binding precedence, or parameter
  value semantics; this decision only prevents values from changing declaration
  identity.
- Changing bare-reference ambiguity semantics or allowing implicit target
  creation.
- A general redesign of the source/normalized/expanded/instantiated document
  phases beyond the identity provenance needed to keep qualified segments safe.
- Redesigning module trust, OCI transport, lockfiles, runtime authentication,
  persistence, or backend protocols.
- Making compiled runtime addresses interchangeable with SDL authoring
  references.
- Promoting every local stable id to generic relationship/objective targetability.
- Changing environment-variable, provider/native, external, display, path, URL,
  DNS, or other data-field grammars.
- Adding a universal identity service or value-object hierarchy.

## Alternatives Considered

### Keep arbitrary ids and use longest-match parsing

Rejected. Meaning would depend on the declarations currently in the symbol
table, and newly imported declarations could change how an existing string is
parsed. It also leaves compiler and persistence addresses structurally opaque.

### Escape dots and other delimiters

Rejected for the current language. Escaping would have to agree across YAML,
JSON Schema, module rewriting, workflow-step refs, compiler addresses,
language-service tools, logs, and persisted snapshots. A small portable segment
grammar is easier to implement consistently and audit.

### Normalize case or Unicode

Rejected. Normalization is lossy, can merge previously distinct declarations,
and creates cross-language/version dependencies. Lowercase ASCII ids plus
unrestricted Unicode display/data fields make the boundary explicit.

### Apply one regex to every `name`, `_id`, and map key

Rejected. Many such fields are labels, provider data, external identifiers,
native option maps, or references rather than SDL declarations. Suffix- or
shape-based validation would conflate concepts and break legitimate data.

## Consequences

Every valid SDL declaration has exactly one portable canonical address, and any
collision is reported before composition, compilation, or persistence can
silently overwrite it. Reference tooling and runtime compilation can share one
identity contract without losing the existing section-, workflow-, or
runtime-family-specific semantics.

The change is intentionally strict and therefore migration-bearing. Existing
dotted nodes, mixed-case/file-like targetable names, descriptor-less imported
fragments, implicit local-import namespaces, and other nonconforming declarations
must be migrated explicitly.
Published SDL schemas are currently `draft`, but every tightening still follows
ADR-061 and the schema-publication manifest/change-ledger rules.

The grammar does not make every dotted string self-describing. Canonical
addresses remain typed paths, and collision-free meaning comes from structured
construction plus exact declaration-index lookup. This avoids both a global
reserved-word list and a new general-purpose address parser.

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-11-06 | #1929 | The schema-publication change ledger is removed (ADR-061 amendment, #1929). Schema synchronization is governed by the generated-schema check and ADR-061 breaking-change detection. |
