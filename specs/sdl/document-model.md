# SDL document model

This reference defines SDL encoding, top-level structure, required fields, identifiers, and structural closure.
It also defines the document phases from authoring to instantiation.

See [`sections.md`](sections.md) for the per-section catalog,
[`references.md`](references.md) for reference resolution, and
[`variables-and-instantiation.md`](variables-and-instantiation.md) for variable
and instantiation rules.

## 1. Source profile: `sdl-yaml/v1`

Canonical SDL source uses the versioned profile `sdl-yaml/v1`. A conforming
strict decoder **MUST** apply all of the following rules before model
construction:

1. The byte stream **MUST** be valid UTF-8 and contain exactly one YAML 1.2.2
   document. Its root **MUST** be a mapping. A sequence, scalar, null root, or
   multi-document stream is invalid.
2. Untagged plain scalars **MUST** resolve with the YAML 1.2.2 Core schema
   ([§10.3](https://yaml.org/spec/1.2.2/#103-core-schema)). Thus `true`, `FALSE`,
   `null`, `0o12`, and `0x0a` are typed Core values, while `yes`, `on`, a date
   spelling, `1_000`, and `-0x0a` are strings. This rule applies in key position:
   unquoted `true` is a boolean key and is invalid, while unquoted `on` is a
   string identifier.
3. Every mapping key **MUST** construct as a string. Complex keys and scalars
   resolved to null, boolean, integer, or float are invalid as keys. Quoting a
   Core-looking identifier is sufficient to keep it a string.
4. Explicit tags and YAML directives **MUST NOT** appear. Only safe standard
   construction of implicitly resolved Core values is permitted. Document
   start/end markers are presentation syntax, not directives, and **MAY** appear.
5. Constructed values **MUST** be in the JSON data domain: null, boolean,
   arbitrary-precision integer, finite binary64-compatible float, Unicode
   string, sequence, or string-keyed mapping. Timestamps, sets, language-native
   objects, non-finite floats, and other tag-specific values are invalid.
6. Anchors and aliases **MAY** share acyclic representation nodes; their names
   and sharing carry no SDL meaning. Cyclic aliases are invalid. The YAML 1.1
   `<<` merge extension is not YAML 1.2.2 Core syntax and is invalid canonical SDL.
   Section 5 defines its explicit migration treatment.
7. Every authored mapping entry **MUST** remain distinguishable until key
   uniqueness is checked. Exact duplicates and canonical-field collisions are
   invalid; a decoder **MUST NOT** construct a last-write-wins mapping first.
8. No Unicode normalization is performed. Code-point sequences remain as
   authored after YAML escape processing.

Each source document has these fixed denial-of-service bounds:

- at most 8 MiB of UTF-8 source;
- 1 MiB in one scalar;
- depth 128;
- 100,000 unique representation nodes;
- 256 alias occurrences;
- 250,000 nodes of alias-expanded traversal work.

Exceeding any bound is a source error.
A future syntax, scalar policy, or incompatible limit
set requires a new source-profile identifier.

A file-backed composition request additionally carries one aggregate budget
across the complete import graph. It bounds the number of imports, aggregate
decoded scalar bytes, aggregate structured nodes, recursion depth, generated
namespace depth, and qualified-name length. The structured-node count is also a
conservative declaration bound because every declaration consumes at least one
counted node. Exceeding any aggregate bound is a source error; recursively
starting a fresh per-file budget is non-conforming.

This uniqueness rule follows the YAML 1.2.2 representation model.
A mapping is an unordered association of unique keys.
Non-unique keys are a loading failure
([YAML 1.2.2 §§3.2.1.1, 3.3](https://yaml.org/spec/1.2.2/)).

## 2. Top-level organisation

The top-level fields divide into two kinds, which **MUST** be kept distinct:

- **Metadata and composition fields** describe the document itself and how it
  composes with other documents. They are not authoring sections.
- **Authoring sections** carry the scenario content. Most are **maps** keyed by
  user-defined identifiers; one is a **list** (see [`sections.md`](sections.md)).

The complete, authoritative enumeration of top-level fields, their kinds, value
shapes, and requiredness is the [section catalog](sections.md), which is written
to match `contracts/schemas/sdl/sdl-authoring-input-v1.json`.

> **Reconciliation note.** Earlier descriptions treated the authoring surface
> as uniformly map-keyed. The live contract is **not** uniform:
> `forwarding_agents` is list-valued, and the participant surfaces (`action_contracts`,
> `observation_boundaries`, `outcome_interpretation_rules`) and shared time
> surfaces (`time_domains`, `clocks`, `time_domain_mappings`,
> `time_progression_policies`, `temporal_constraints`) are present. The
> section catalog states and mechanically checks the live set; this specification reconciles the
> language to the published schema rather than freezing a historical count.

## 3. Normalized-authoring requiredness

1. `name` is the only **REQUIRED** top-level field. A document without `name` is
   invalid.
2. Every other top-level field is **OPTIONAL**. An omitted authoring section is
   equivalent to an empty one (an empty map, or an empty list for the
   list-valued section); an omitted metadata field takes its documented default.
3. The section schema governs required fields within each element, such as a node.
   Runtime families also use their owning family ADR
   ([runtime-inventory.md](runtime-inventory.md)).

These rules describe `sdl-authoring-input-v1`. Derived phase contracts add
their own required members: an instantiated scenario requires
`instantiation_provenance`, and an instantiated snapshot requires both
`profile` and `scenario` (§7). A materialized description requires
`materialization_provenance` rather than instantiation provenance.

## 4. Structural closure (fail-closed)

1. SDL models are **closed**: an unknown key — at the top level or anywhere
   within a nested model — **MUST** be rejected, not ignored. There is no
   permissive "extra fields allowed" mode.
2. Rejection of an unknown or malformed key is a **parse/structural** failure
   (see [`diagnostics.md`](diagnostics.md)). It occurs before semantic validation and is fatal.
3. Closure exists so that a typo in a field name (`vulnerabilites`) fails the
   document rather than silently dropping content. Authors **MUST NOT** rely on
   undeclared keys to carry data.
4. Anchors and aliases do not weaken closure or uniqueness. Migration-mode
   merge input is accepted only when every inherited and local effective field is disjoint.
   Override precedence is never SDL semantics.

> *Implementation evidence (non-normative): the reference models reject
> unknown fields through their shared SDL base model.*

## 5. Canonical fields, literal keys, and migration

1. Enum-valued fields accept their value case-insensitively.
   They accept a hyphen as an alias for an underscore in the value text.
   Thus `search-index` and `search_index` denote the same enum member. This
   is an authoring convenience; the normalised (canonical) form is what the
   document means.
2. A structural field key **MUST** use its exact lower-case `snake_case` schema
   spelling. `semantic_version` is canonical; `semantic-version`,
   `Semantic_Version`, and `SEMANTIC_VERSION` are not canonical SDL source.
3. A tool **MAY** offer an explicit migration operation that recognizes legacy
   case and hyphen spellings and `<<` merges. Migration is never implicit: the
   strict/default policy rejects each construct. An accepting migration policy
   **MUST** emit a source-ranged advisory for every rewritten field or merge.
   Its output **MUST** pass strict `sdl-yaml/v1` decoding. Unrecognized
   fields remain errors.
4. Migration aliases do not create a precedence rule.
   Two keys addressing one canonical field make an effective mapping ambiguous, including through a YAML merge.
   The mapping **MUST** fail during parsing before model construction. The diagnostic contract is defined in
   [diagnostics.md §6](diagnostics.md).
5. Field recognition applies only while traversing a schema-defined
   structural mapping. It **MUST NOT** be applied to user-defined identifier
   maps, extension maps, or native option/label maps. Keys in those maps are
   preserved verbatim, including case, hyphens, and underscores; only exact
   duplicate identifiers are rejected. Core scalar resolution still applies,
   so boolean/null/numeric-looking identifiers must be quoted when necessary.
6. A field that holds a variable placeholder (`${…}`) is **not** normalised as an enum value.
   The placeholder is preserved until instantiation
   ([variables-and-instantiation.md](variables-and-instantiation.md)).

Formally, let `c_scope(k)` lowercase a key and replace hyphens with underscores
in a structural mapping, and be the identity function in a literal mapping.
Canonical source additionally requires `c_scope(k) = k`. For every
pair of distinct entries `i` and `j` in an effective mapping (including merge
contributions), well-formedness requires
`c_scope(key_i) != c_scope(key_j)`. This injectivity condition is checked over
the authored node graph; mapped values do not participate in the comparison or
its diagnostics.

## 6. Portable identifiers and declaration identity

Every RAES-local **declaration identity** uses one portable local-identifier
grammar:

```text
portable-id = id-start *63id-char
id-start    = %x61-7A / DIGIT
id-char     = id-start / "-" / "_"
```

Equivalently, a portable id is a full-string match for
`^[a-z0-9][a-z0-9_-]{0,63}$`. Implementations **MUST** use full-match semantics;
a `$`-anchored regex alone is insufficient in engines that match before a final
line terminator. The spelling is exact: an implementation **MUST NOT** trim,
case-fold, Unicode-normalize, escape, sanitize, or repair it. Uppercase,
non-ASCII, whitespace, controls, `.`, `/`, `:`, and `${…}` are invalid.

The rule applies by semantic role, not field spelling.
It covers these identities:

- the top-level `name`.
- Map-valued section and variable keys.
- Nested entity, role, and workflow-step keys.
- Named services, ACLs, and content items.
- Scenario-level forwarding-agent ids.
- Every RAES-local primary or child id in the runtime-family registry.

It does **not** apply merely because a field is called `name` or ends in `_id`.
Display labels, usernames, DNS names, URLs, paths, LDAP DNs, environment names,
versions, external/native/provider ids, and opaque evidence refs retain their
owning types. Where one object needs both a stable identity and a filename or
label, those are separate fields.

Identifiers **MUST** be unique within their owning collection. Before aliases
are deduplicated, every declaration is also entered in a document-scoped typed address index.
Two distinct declarations that render the same canonical address make the document invalid.
The admitted-document invariant is:

```text
for all d1,d2 in Declarations(document):
  render(address(d1)) = render(address(d2)) implies d1 = d2
```

Variables parameterise values, never declarations. A placeholder **MUST NOT**
appear in any defining identity, and changing a parameter mapping **MUST NOT**
change the declaration set or any canonical address. Node local ids retain the
stricter 35-character maximum. Because YAML Core resolution precedes model
construction, an all-digit id must be quoted so it remains a string.

Composition is the only operation that creates a **qualified name**: zero or
more portable namespace segments followed by one portable local id, rendered
with `.` separators. The reserved `__private` namespace segment may be generated
for non-exported module declarations but is invalid author input. Qualified
names are bounded to 2048 characters. Raw and normalized authoring objects admit
local ids only; expanded, instantiated and materialized objects may carry generated qualified
top-level identities. Nested owner-local ids, including node runtime-family ids,
remain local.

## 7. Document phases and schema boundaries

SDL has one source presentation and distinct authoring, instantiated and descriptive data forms. Their
object shapes are closed independently; a field absent from a phase is
forbidden rather than represented by an empty compatibility shell.

| Form | Required/phase-specific members | Forbidden authoring machinery | Publication |
|------|---------------------------------|-------------------------------|-------------|
| Source | YAML presentation governed by `sdl-yaml/v1` | n/a | source profile and YAML fixtures |
| Normalized authoring | executable sections; `name`; optional `module`, `imports`, `realization`, `variables` | none | `sdl-authoring-input-v1` |
| Expanded authoring | executable sections; `name`; root `variables`; typed `expansion_provenance` | `module`, `imports`, `realization` | internal trusted representation |
| Instantiated | executable sections; `name`; required `instantiation_provenance` | `module`, `imports`, `realization`, `variables`, any `${…}` token | `instantiated-scenario-v1` |
| Canonical instantiated snapshot | required `profile` and admitted `scenario` | all authoring machinery at the envelope; the nested scenario obeys the instantiated row | `instantiated-scenario-snapshot-v1` |
| Materialized description | common scenario sections; `name`; required `materialization_provenance` | all authoring machinery, `instantiation_provenance`, any `${…}` token | `materialized-scenario-v1` |

The **normalized authoring object** exists after safe source construction,
canonical field recognition, shorthand expansion, enum/scalar typing, and
structural closure. It may contain imports and placeholders. Its published
schema validates that JSON-compatible object, not raw YAML or presentation
syntax.

The **expanded authoring object** exists after trusted module resolution and
namespace rewriting but before final root-variable binding. Public exports have
their declared namespace prefix and non-exported declarations have the generated
`__private` prefix
([ADR-053](../../docs/decisions/adrs/adr-053-sdl-module-composition-for-inventory-backed-scenarios.md)).
Composition consumes `module`, `imports`, and the authored `realization` block.
Verified resolution facts and normalized realization-designation records move
into typed expansion provenance. Only the composition path may create this
internal representation or generated qualified declaration keys. Full semantic
validation applies to it.

The public binding operation validates its input, selects and checks every binding, and substitutes values.
It rebuilds the closed concrete shape, checks provenance consistency, and reruns semantic validation.
The **instantiated scenario** exists after these checks.
Its provenance retains the normalized realization
designations without retaining the authoring block. Provenance is part of the
portable artifact, not implementation-private context. Direct/deserialized
artifacts must pass the same structural and semantic admission before
compilation.

The **canonical instantiated snapshot** is a sealed identity envelope, not
input to source parsing, composition, or substitution. Its profile is
`raes-sdl-instantiated-snapshot/v2`; §9 defines its bytes and digest.

The source -> normalized -> expanded -> instantiated progression refines the two-phase
authoring/instantiation model of
[ADR-001](../../docs/decisions/adrs/adr-001-scenario-description-language.md) and
the runtime-layering boundary of
[ADR-004](../../docs/decisions/adrs/adr-004-sdl-runtime-layer.md) and
[ADR-036](../../docs/decisions/adrs/adr-036-sdl-processor-runtime-module-boundaries.md).
Delivery-level realization remains downstream of the author-facing realization designation.
It is outside the authoring model's scope.

The **materialized description** reports the full world after backend hooks,
including in-world additions and changes. It uses ordinary SDL parsing,
validation, formatting, compilation and planning, with inspection-only plans.
Its source/execution bindings, native member origins, instance identities and
distinct `raes-sdl-materialized/v1` canonical identity follow
[materialization-attestation.md](materialization-attestation.md). Reading it
does not import, instantiate, execute, authorize additions or acquire evidence.

## 8. Canonical semantic identity

The v2 profiles in this section and §9 apply to both tagged and untagged
current artifacts. They replace the pre-cutover v1 profiles. Current snapshot
and provenance admission reject v1 profile identifiers; changing a stored label
does not migrate its content or authenticate a new digest. Reconstruct current
artifacts and reissue linked sidecars through their owning APIs.

The canonicalization profile `raes-sdl-semantic/v2` identifies one semantically
validated, expanded authoring scenario independently of YAML layout, map order,
recognized migration spelling, and documented shorthand spelling. It does not
identify raw source, an instantiated scenario, a compiled runtime model, a
module bundle, evidence, or a run.

The canonical input is the following JSON object:

```json
{
  "profile": "raes-sdl-semantic/v2",
  "scenario": {},
  "module_variable_specs": {},
  "module_node_variable_refs": {}
}
```

`scenario` is the validated expanded authoring object serialized with canonical
wire field names while omitting fields that were not authored or introduced by
normalization/composition. The two legacy-named module maps are compatibility
projections derived from typed expansion provenance: the imported finite domains
and the concrete fields that depend on them. They preserve this profile's bytes
and meaning; they are not live variable definitions and do not appear as fields
of `instantiated-scenario-v1`. Array order is significant; object member order
is not. Authored omission is significant, so an omitted optional field and an
explicitly authored default are distinct.

The envelope **MUST** satisfy the I-JSON input constraints and be serialized
with the JSON Canonicalization Scheme (JCS), RFC 8785. JCS preserves Unicode
code points without normalization, sorts object properties by UTF-16 code
units, preserves array order, emits UTF-8, and rejects non-finite or out-of-domain
numbers. The profile digest is SHA-256 over those bytes and is rendered
`sha256:<64 lower-case hexadecimal digits>`. A change to the envelope,
presence rule, or canonicalization algorithm requires a new profile identifier.

JCS is the serialization rule for this profile; it is not the source of SDL's
identifier grammar or address semantics. RFC 8785 does not normalize Unicode,
and SDL likewise preserves display/data strings exactly while restricting only
declaration identities to the portable ASCII grammar above.

## 9. Canonical instantiated snapshot

The `raes-sdl-instantiated-snapshot/v2` profile identifies one semantically
admitted instantiated artifact, including its portable derivation evidence. Its
canonical input is exactly:

```json
{
  "profile": "raes-sdl-instantiated-snapshot/v2",
  "scenario": {}
}
```

`scenario` **MUST** validate against `instantiated-scenario-v1`, pass provenance
consistency checks, and pass the ordinary SDL semantic validator. Snapshot
construction is not a way to canonicalize an invalid direct model. The profile
and scenario members are both required; unknown envelope members are forbidden.

The envelope is serialized and digested with the same JCS/SHA-256 rules in §8.
Any change to concrete content or `instantiation_provenance` changes the
canonical input. This digest establishes artifact identity under the named
profile. It does **not** establish that the recorded derivation activity occurred or that external module sources remain available.
It also does **not** establish equal scenario behavior or observationally equivalent executions.

## 10. Infrastructure

`infrastructure` maps node identifiers to deployment topology declarations.
Each key **MUST** select a same-named entry in `nodes`.
A node need not have an infrastructure entry.
Omission of the section means an empty map.
The section persists through the document phases in §7.

Each normalized entry is a closed object with these fields:

| Field | Shape and meaning | Default |
| --- | --- | --- |
| `count` | Integer instance count, at least `1`, or an integer variable reference | `1` |
| `links` | List of distinct switch-backed infrastructure references; network connectivity | Empty list |
| `dependencies` | List of distinct infrastructure references; deployment prerequisites | Empty list |
| `properties` | Subnet object, list of per-link address maps, or null | null |
| `acls` | List of network access control rules | Empty list |
| `description` | Descriptive string | Empty string |

In source, `web: 3` is shorthand for `web: {count: 3}` within `infrastructure`.
A full-value count placeholder has the same shorthand treatment.
A switch **MUST** have count `1`.
A compute node with attached conditions **MUST** also have count `1`.
Links express connectivity; dependencies express prerequisites.
Neither creates a node or an implicit feature binding.

Reference resolution follows [the reference catalog](references.md).

A subnet object contains required strings `cidr` and `gateway`, plus optional `internal`, which defaults to `false`.
`cidr` **MUST** describe an IPv4 or IPv6 network; host bits do not invalidate its network prefix.
`gateway` **MUST** be an IP address within that network.
`internal` expresses whether the network is internal.
Its authored value is a boolean or boolean variable reference.
This declaration does not prove backend enforcement of network isolation.

Each per-link address map associates linked switch-backed infrastructure identifiers with IP address strings.
Each target **MUST** declare subnet properties.
Each concrete address **MUST** belong to that target's CIDR.
Placeholders defer concrete value checks until instantiation, which reruns validation.

Each ACL rule is a closed object with these fields:

| Field | Shape and meaning | Default |
| --- | --- | --- |
| `name` | Optional portable local identifier; nonempty names are unique within the infrastructure entry | Empty string |
| `direction` | Direction string | Empty string |
| `from_net`, `to_net` | Network reference strings; nonempty concrete references select switch-backed infrastructure | Empty strings |
| `protocol` | Protocol string | `any` |
| `ports` | List of integer ports from `1` through `65535`, or integer variable references | Empty list |
| `action` | `allow`, `deny`, or an enum variable reference | `allow` |
| `description` | Descriptive string | Empty string |

Direction and protocol strings do not acquire additional enums from this reference.
Named ACL addresses follow [the reference catalog](references.md).
ACL declarations express network policy intent.
They do not grant operator authority or establish packet-filter precedence or backend enforcement.

## 11. Features

`features` maps identifiers to reusable software declarations for compute nodes.
Omission means an empty map.
The section persists through the document phases in §7.
A declaration is distinct from a node service or observed runtime software inventory.
It has these closed fields:

| Field | Shape and meaning | Presence/default |
| --- | --- | --- |
| `type` | `service`, `configuration`, or `artifact`; enum normalization follows §5 | Required |
| `name` | Display name string; the map key remains the declaration identity | Empty string |
| `source` | Artifact source object, or null | null |
| `dependencies` | List of feature references; prerequisites for this feature | Empty list |
| `destination` | Destination string for feature content | Empty string |
| `environment` | List of environment strings | Empty list |
| `description` | Descriptive string | Empty string |

A source string is shorthand for an object with that `name` and version `*`.
Source objects retain the published schema's optional build provenance and artifact-requirement refinements.
They identify artifacts without authorizing retrieval or proving installation.
Feature environment strings do not carry the typed runtime environment or secret-reference contract.

`nodes.<node>.features` binds declarations to a compute node.
A list of feature identifiers means bindings without roles.
A map associates each feature identifier with a node-local role, or an empty string for no role.
Nonempty roles **MUST** exist on that node.

Dependencies **MUST** resolve to declared features and form an acyclic graph.
Each dependency **MUST** also be bound on the same node before runtime planning can succeed.
Compilation diagnoses a missing binding; it does not install an unbound dependency implicitly.

## 12. Duration values

This grammar applies to `scripts.*.start_time`, `scripts.*.end_time`, `scripts.*.events.*`, and `workflows.*.timeout.seconds`.
These fields normalize concrete durations to integer seconds before normalized-object schema validation.
A scalar `workflows.*.timeout` is shorthand for an object whose `seconds` field contains that value.
It does not apply to every field that measures time.
Condition polling, execution-policy delays, and [shared rational clocks](../formal/time-model/README.md) retain their own contracts.
Duration notation does not select a clock, epoch, or runtime pacing policy.

### Numeric and string forms

A numeric source value denotes seconds.
It **MUST** be finite and nonnegative; booleans are invalid.
Zero stays `0`; a positive fractional value rounds upward to the next integer second.
For example, numeric `1.2` becomes `2`.
Numeric exponent notation follows source scalar decoding in §1.

For a string, remove leading and trailing whitespace first.
Then remove ASCII spaces and underscores, replace `µ` with `u`, and lowercase the text.
Internal tabs and line breaks are not separators.
The resulting string **MUST** match this grammar completely:

```text
duration = { "+" }, term, { { "+" }, term }, { "+" } ;
term     = number, [ unit ] ;
number   = digit, { digit }, [ ".", digit, { digit } ] ;
```

Here, braces mean repetition, brackets mean optional content, and commas mean concatenation.
`digit` is a Unicode decimal digit; `unit` is an alias from the table below.
Scan the longest number first, then the longest matching unit alias.
An omitted unit denotes seconds.
Terms can touch, or have one or more plus signs between them.
Leading and trailing plus signs are also accepted; at least one term is required.

Negative strings, empty strings, unknown units, exponent strings, and incomplete decimal fractions are invalid.
For example, `-1s`, `1e3`, `.5s`, and `1.s` are invalid strings.
Full-value variable references remain unresolved until instantiation and subsequent validation.

### Units and rounding

| Unit | Accepted aliases after normalization | Seconds per unit |
| --- | --- | --- |
| Year | `y`, `year`, `years` | `31536000` |
| Month | `mon`, `month`, `months` | `2592000` |
| Week | `w`, `week`, `weeks` | `604800` |
| Day | `d`, `day`, `days` | `86400` |
| Hour | `h`, `hr`, `hour`, `hours` | `3600` |
| Minute | `m`, `min`, `mins`, `minute`, `minutes` | `60` |
| Second | `s`, `sec`, `secs`, `second`, `seconds` | `1` |
| Millisecond | `ms`, `msec`, `millisecond`, `milliseconds` | `0.001` |
| Microsecond | `us`, `usec`, `usecond`, `microsecond`, `microseconds` | `0.000001` |
| Nanosecond | `ns`, `nsec`, `nanosecond`, `nanoseconds` | `0.000000001` |

Months always mean 30 days; years always mean 365 days.
These are fixed conversions, not calendar arithmetic.
Convert terms to decimal seconds and add them before rounding.
Round the total upward to the least integer greater than or equal to it.
Do not round each term separately.
The rule does not establish arbitrary-precision arithmetic for implementations.

| Source value | Normalized seconds |
| --- | --- |
| `0` or `"0s"` | `0` |
| `"1h 30min"` | `5400` |
| `"1m+30"` | `90` |
| `"400ms 400ms"` | `1` |
| `"1001 ms"` | `2` |
| `"1 µs"` or `"1 ns"` | `1` |
| `"1_000 MS"` | `1` |
| `"+1s++"` | `1` |

Consumer bounds apply after conversion.
Script end time **MUST** be at least its start time.
Each event time **MUST** lie within those inclusive bounds.
Workflow timeout seconds **MUST** be positive; zero is invalid there.
