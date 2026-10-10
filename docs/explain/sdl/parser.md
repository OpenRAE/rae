# SDL Parser Behavior

The parser (`raes.parser`) transforms raw YAML into a validated
`Scenario` object through `sdl-yaml/v1` decoding, source-marked safe
composition, canonical-field validation, shorthand expansion, and typed model
construction.

This layer is intentionally about syntax, normalization, and structural model
construction. It is usually an `FM0` surface under the repository's
[coding standards](../reference/coding-standards.md): parser work normally
needs ordinary tests, not state-machine modeling or solver-backed formal
artifacts, unless it also introduces new semantic invariants above raw syntax.
The mapping-key gate is `FM1`; portable declaration identity, canonical-address
injectivity, and cross-stage coherence are `FM2`. Table-driven, property, and
differential tests pin grammar parity, ambiguity rejection, literal-map
preservation, and processor/runtime agreement.

## Canonical Fields and Migration

Canonical SDL structural fields use exact lower-case `snake_case`:

- `name` is canonical; `Name` is migration syntax.
- `start_time` is canonical; `start-time` is migration syntax.
- `semantic_version` is canonical; `Semantic-Version` is migration syntax.

Declaration identities are preserved exactly but must already use the portable
local-id grammar `^[a-z0-9][a-z0-9_-]{0,63}$` (node local ids have a 35-character
maximum). The parser never lowercases or sanitizes an invalid id. Native/data
map keys such as entity facts remain under their own contracts.

```yaml
# "my-switch" is a portable declaration id; structural field "type" is exact.
nodes:
  my-switch:
    type: switch
```

Ordinary parsing is strict. Callers doing a deliberate conversion can select
`SDLMigrationPolicy.ACCEPT` or use `raes sdl format`; each recognized rewrite
produces a source-ranged `sdl.noncanonical_field` or
`sdl.noncanonical_merge` warning. The formatter emits strict, typed, longhand
YAML and never invents identifier renames.

Field aliases do not imply precedence. Writing both `Name` and `name`, or both
`password-strength` and `password_strength`, in one structural mapping is a
fatal `sdl.mapping_key_conflict`. Exact duplicates are also fatal in
user-defined and native maps, but distinct valid declaration ids such as
`web-app` and `web_app` remain distinct.

The check runs over the composed YAML node graph before a Python dictionary is
constructed, so it retains both authored spellings and source ranges. YAML
anchors remain supported. A `<<` merge is rejected by strict parsing and is
accepted only by explicit migration when all inherited and local effective
keys are disjoint; cyclic aliases are rejected.

## Source Profile

`sdl-yaml/v1` is UTF-8, exactly one YAML 1.2.2 document, and uses Core-schema
scalar resolution. Explicit tags/directives, non-string keys, non-finite or
non-JSON values, cyclic aliases, and resource-budget exhaustion fail before
model construction. Unlike PyYAML's default YAML 1.1 resolver, `yes`, `no`,
`on`, and `off` remain strings. The normative rules and exact budgets are in
`specs/sdl/document-model.md`.

## Shorthand Expansion

Several shorthand forms are expanded before model construction:

| Shorthand | Expands To |
|-----------|------------|
| `source: "pkg-name"` | `source: {name: "pkg-name", version: "*"}` |
| `infrastructure: {node: 3}` | `infrastructure: {node: {count: 3}}` |
| `roles: {admin: "username"}` | `roles: {admin: {username: "username"}}` |
| `features: [svc-a, svc-b]` (on nodes) | `features: {svc-a: "", svc-b: ""}` |

Source expansion only applies to actual SDL `source` fields. It is skipped inside `relationships` and `agents` where `source` is a plain string reference, and it does not fire on user-defined map keys that merely happen to be named `source`.

Shorthand expansion also works when the shorthand value is a full variable
placeholder. For example, `infrastructure: {web: ${replicas}}` expands to
`infrastructure: {web: {count: ${replicas}}}`.

## Variables

Full-value `${var_name}` placeholders and embedded `${var_name}` tokens are
preserved as literal strings during parsing. Variable names use the same
portable local-id grammar. Structural validation accepts placeholders only in
fields whose owning contract permits parameterization. The parser does not
substitute variables or evaluate expressions, and no placeholder may define or
rename an SDL identity.

The intended boundary is:

- **Concrete identifiers**: mapping keys that define named scenario elements such as `nodes.web`, `features.apache`, `accounts.db-admin`, `relationships.app-to-db`
- **Variable-backed values**: attributes on those elements such as hostnames, ports, counts, CIDRs, paths, timings, descriptions, and other field values

So a hostname may come from `${hostname}`, but a node key like `web` may not.

## OCR Duration Grammar

Script and event times accept the documented OCR time units:

- `y`, `year`
- `mon`, `month`
- `w`, `week`
- `d`, `day`
- `h`, `hour`
- `m`, `min`, `minute`
- `s`, `sec`, `second`
- `ms`, `us`/`µs`, `ns`

Durations may be written with spaces or `+` separators, such as `1h 30min`
or `1m+30`. Sub-second values are rounded up to whole seconds, so `1 ms`
parses as `1`. Negative numeric durations are rejected rather than silently
coerced.

## Format and Schema Boundaries

The parser accepts one source profile:

- **`sdl-yaml/v1`:** top-level `name` plus SDL sections under the source rules above.

Older metadata/mode-based scenario YAMLs are intentionally rejected. They must
be migrated to SDL before parsing.

`contracts/schemas/sdl/sdl-authoring-input-v1.json` validates the normalized,
typed authoring object after source decoding and shorthand expansion. It is not
a raw-YAML grammar and cannot validate tags, aliases, duplicate keys, scalar
resolution, or source limits. Canonical shipped examples use longhand values so
their strict decoded object validates against it directly.

## Validation Pipeline

1. **Source-profile preflight** — enforce UTF-8 size, tokens, aliases, and YAML 1.2 Core rules
2. **Safe YAML composition** — build a source-marked standard-tag node graph
3. **Mapping-key preflight** — reject exact/canonical collisions and migration syntax by default
4. **Safe construction** — construct JSON-domain native values only after ambiguity checks
5. **Typed normalization** — expand shorthands and normalize declared field values
6. **Pydantic construction** — structural validation (types, ranges, required fields)
7. **Module expansion** — resolve descriptor-bearing file-backed imports with explicit namespaces and one aggregate composition budget
8. **Declaration indexing** — retain typed provenance, reject canonical-address collisions, and build aliases
9. **Semantic validation** — exact cross-reference checks plus variable-reference checks (see [validation.md](validation.md))

On success, the returned `Scenario` may still carry non-fatal advisories in `scenario.advisories` (for example, compute nodes without explicit `resources`).

## API

```python
import json
from pathlib import Path

from raes import parse_sdl, parse_sdl_file
from raes import (
    SDLMigrationPolicy,
    admit_instantiated_scenario,
    canonical_instantiated_sdl_digest,
    canonical_sdl_digest,
    format_sdl_source,
    instantiate_scenario,
    load_sdl_fragment,
)

# Parse from string
scenario = parse_sdl(yaml_string)

# Parse from file
scenario = parse_sdl_file(Path("scenario.yaml"))

# Structural validation only (skip cross-reference checks)
scenario = parse_sdl(yaml_string, skip_semantic_validation=True)

# Explicit legacy conversion; ordinary parsing remains strict.
migrated = format_sdl_source(legacy_yaml)
scenario = parse_sdl(legacy_yaml, migration_policy=SDLMigrationPolicy.ACCEPT)

# Versioned semantic identity requires successful semantic validation.
digest = canonical_sdl_digest(parse_sdl(yaml_string))

# Instantiation returns the closed portable artifact; direct JSON artifacts use
# the same admission gate before compilation or snapshotting.
concrete = instantiate_scenario(scenario, parameters={})
restored = admit_instantiated_scenario(json.loads(concrete.model_dump_json()))
snapshot_digest = canonical_instantiated_sdl_digest(restored)

# Advanced authoring tools can preflight a fragment at its final address.
nodes = load_sdl_fragment(
    nodes_yaml,
    mapping_keys="literal",
    base_pointer="/nodes",
)
```

Use `parse_sdl_file(...)` for SDL that uses top-level `imports:`. Import
expansion is file-backed and deterministic, so in-memory `parse_sdl(...)`
rejects module/import composition by design. This determinism is witnessed by
`implementations/python/tests/test_pipeline_determinism.py`, which runs the
`parse → instantiate → compile` pipeline twice over representative scenarios
(including a module-import scenario) and under varied `PYTHONHASHSEED`, and
asserts the compiled output is byte-identical.

Top-level composition supports:

- explicit `module` descriptors on every imported unit
- `imports` using backward-compatible `path:` or canonical `source:`
- `source:` classes `local:`, `oci:`, and `locked:`
- repo-owned trust and resolution files:
  - `raes.lock.json`
  - `raes-trust.yaml`

Import `source:` values are not treated as ordinary SDL package-source
shorthand. They are resolved by the composition layer, not expanded into
`{name, version}` package dictionaries.

Every import supplies one portable `namespace`; filenames and source paths are
never converted into identity. Composition alone creates dotted qualified
names and the reserved `__private` segment. Raw dotted declaration keys are
invalid, including when migration acceptance is enabled.

## Error Types

- `SDLParseError` — YAML syntax errors and structural validation failures;
  mapping-key failures carry structured `.diagnostics` with stable code, JSON
  Pointer, authored spellings, and source ranges; invalid declaration keys and
  scalar ids use `sdl.identifier.invalid` and do not echo the invalid spelling;
  other typed-model failures use `sdl.model.invalid` with a control-escaped,
  512-character-bounded domain message and no Pydantic input rendering
- `SDLValidationError` — semantic validation failures (has `.errors` list with all issues)

In an imported unit, typed-model failures raise a raw pydantic `ValidationError`
instead, and a malformed import `version` range raises
`packaging.specifiers.InvalidSpecifier`. YAML syntax and mapping-key failures
in an imported unit still raise `SDLParseError`. The Fulfillment boundary in
`docs/requirements/DSL-116/requirement.md` records both gaps.
