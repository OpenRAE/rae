# SDL editor support evidence

Observed 2026-10-09, and L12 on 2026-10-10, on repository revision
`35122105b0c1bb648754625d8e3920eafa9bc599`. The
[feasibility note](feasibility.md) interprets these observations. The probes
called the language-service helpers in-process, with the working tree at that
revision and the repository Python environment (CPython 3.14.4, free-threaded).
Nothing was mocked, and no scenario was launched. The probes establish helper
and schema behavior on small inputs. They are not a usability, conformance or
security result.

## Minimal probe inputs

Specimen N is a valid document with one feature and one node:

```yaml
name: demo
features:
  app: {type: service, source: webapp}
nodes:
  web:
    type: compute
    os: linux
    resources: {ram: 2 GiB, cpu: 1}
    features: [app]
```

Specimen P is a valid document with a participant relationship:

```yaml
name: audit
entities:
  team: {role: red}
agents:
  one: {affiliations: [team]}
  two: {affiliations: [team]}
propositions:
  ok:
    description: declared state
    subjects: [agents.one]
    basis: declared_state
    predicate:
      kind: boolean
      property: ready
      semantic_ref: urn:raes:declared-property:ready
      operator: equals
      expected: true
assertions:
  done: {proposition: ok, role: postcondition, polarity: positive}
relationships:
  pair:
    type: participant
    source: agents.one
    target: agents.two
    participant: {kind: cooperation}
```

Specimen M is a valid document in which every value has its long form:

```yaml
name: demo
features:
  app: {type: service, source: {name: webapp, version: '*'}}
nodes:
  web: {type: compute, os: linux, resources: {ram: 2 GiB, cpu: 1}, features: {app: client}, roles: {client: {username: www}}}
```

Each row below names the edit that it applies to a specimen. Lines and columns
are 1-based, as the helpers report them.

## Language-service observations

| ID | Operation | Observed result | Limit |
| --- | --- | --- | --- |
| L1 | `language_completions(P, cursor_path="/relationships/pair/target")`, then `language_diagnostics` of P with each offered `insert_text` as the target | Context `reference:targetable`, with six items: `agents.one`, `agents.two`, `assertions.done`, `entities.team`, `propositions.ok` and `relationships.pair`. Only `two` is valid. `one` fails with "Relationship 'pair' requires distinct participants". The other four fail because the target must "resolve unambiguously to a declared agent". | Finding F5 in the [participant audit](../participant-identity/audit.md) reports the same mismatch, and #1339 tracks it |
| L2 | Compare each list in `SECTION_FIELD_COMPLETIONS` with the property names that the published schema declares for that section | 18 of the 33 lists differ from the schema. Together they omit 69 schema fields. The `features` list also offers `version`, which the schema does not declare. The table below lists the differences. | The comparison merges every union branch. Nine schema sections have no list. |
| L3 | `language_completions` on a document whose only feature is `app: {type: service}`, with `cursor_path="/features/app"` and `prefix="v"`; then `language_diagnostics` with `version: '1.0'` added to that feature | Completion offers `version`. Diagnostics report `sdl.model.invalid`, "Extra inputs are not permitted", at `/features/app/version`. | |
| L4 | `language_completions(text, cursor_path="/nodes/web/features")` on N and on four edits of N | N gives `ok` with `app`. `features:` with no value gives `ok` with `app`. `features: [` gives `invalid` with `sdl.parse`. `fea` in place of the `features` line gives `invalid` with `sdl.parse`. `type: VM` gives `invalid` with `sdl.legacy_node_type_vm`. | A parse failure anywhere in the document removes every item |
| L5 | `language_diagnostics` on four documents | Adding `colour: blue` under `web` in N gives `sdl.model.invalid` at `/nodes/web/colour`, on line 10, columns 13 to 17. The key starts at column 5. `features: [missing]` in N gives `sdl.semantic` at the `semantic_validation` stage, with no path and no range. `name: demo` followed by `name: again` gives `sdl.mapping_key_conflict` at `/name`, on line 2, columns 1 to 5. An unclosed `web: {type: compute` gives `sdl.parse` with an empty path and one point, line 4, column 1. | The point in the last case is the end of the input |
| L6 | `language_format` on a document with three comments and the feature `app: {type: Service, source: webapp}` | Status `formatted`. The output has no comments. `type: Service` becomes `type: service`, and `source: webapp` becomes a mapping of `name: webapp` and `version: '*'`. | |
| L7 | `apply_structured_edit` on N with two added comments, operation `set`, pointer `/nodes/web/os`, value `windows` | Status `edited`. The output has no comments. `source: webapp` expands as in L6, and `features: [app]` becomes the mapping `app: ''`. | |
| L8 | `parse_sdl_file` and `language_diagnostics` on `contracts/fixtures/sdl/variation-points-v1/composition/root.yaml` | `parse_sdl_file` returns an `ExpandedScenario`. On the same text, `language_diagnostics` returns `sdl.parse`, "SDL imports require file-backed parsing via parse_sdl_file()". Turning off `semantic_validation` gives the same result. | |
| L9 | File sizes of the tracked `*.sdl.yaml` files, against `_MAX_INPUT_BYTES` | The limit is 65,536 bytes. None of the 40 files is over it. The largest is `examples/scenarios/hospital-ransomware-surgery-day.sdl.yaml`, at 46,073 bytes. | |
| L10 | `language_completions(N, cursor_path=path)` for `/nodes`, `/nodes/web`, `/nodes/web/resources` and `/nodes/web/os` | Each call returns context `section:nodes` and the same nine fields: `type`, `description`, `os`, `resources`, `features`, `conditions`, `services`, `roles` and `endpoint_persona`. | |
| L11 | Median of 5 warm calls of `language_diagnostics`, and of `language_completions` at `/nodes`, on the L9 file. Median of 3 fresh interpreters that import `raes` and make one diagnostics call. | At load average 7.2: 172 ms and 159 ms warm, and 1,207 ms cold. At 13.1: 174 ms and 163 ms warm, and 1,297 ms cold. At 22.5: 377 ms and 373 ms warm, and 2,939 ms cold. | An 8-core Apple M3 that other work shared. The timings are indicative. |
| L12 | The five helpers on two documents: `contracts/fixtures/sdl/materialized-scenario-v1/valid/reference.json` with N's node `web` added, and N. In both, the node's `features` is `[missing]`. Completion uses `cursor_path="/nodes/web/features"`, references use the symbol `web`, and the edit is L7's. | On the fixture, `language_diagnostics` returns `invalid` with `sdl.semantic`. `language_format` raises `SDLValidationError`, "Node 'web' references undefined feature 'missing'". Completion and references return `ok`, and the edit returns `edited_with_diagnostics` with `sdl.semantic`. The fixture's JSON text and its YAML dump behave the same. On N nothing raises, and `language_format` returns `formatted_with_diagnostics` with `sdl.semantic`. | |

L2 counts, for each list, the distinct property names that the schema declares
for one entry of the section. For a section that is one object, such as
`realization`, it counts that object's properties. The count follows `$ref` and
merges `anyOf`, `oneOf` and `allOf` branches. These lists differ:

| Section | Offered | In schema | Schema fields not offered |
| --- | --- | --- | --- |
| `accounts` | 7 | 14 | `description`, `disabled`, `groups`, `home`, `mail`, `materialization_profile`, `shell` |
| `agents` | 7 | 12 | `allowed_subnets`, `authority_anchors`, `description`, `observation_boundaries`, `operating_scope` |
| `behavior_specifications` | 17 | 18 | `autonomous_execution` |
| `conditions` | 5 | 10 | `environment`, `name`, `retries`, `start_period`, `timeout` |
| `content` | 7 | 13 | `description`, `destination`, `sensitive`, `tags`, `text`, `text_from` |
| `entities` | 4 | 7 | `description`, `events`, `mission` |
| `events` | 2 | 5 | `description`, `name`, `source` |
| `evidence_requirements` | 17 | 24 | `capture_requirement_ref`, `capture_spec_ref`, `description`, `field_selectors`, `notes`, `observation_demand`, `output_contract` |
| `features` | 4 | 7 | `description`, `destination`, `environment`, `name`. The list also offers `version`. |
| `infrastructure` | 4 | 6 | `acls`, `description` |
| `injects` | 3 | 6 | `description`, `environment`, `name` |
| `nodes` | 9 | 16 | `architecture`, `asset_value`, `injects`, `os_distribution`, `os_version`, `runtime`, `source` |
| `objectives` | 7 | 9 | `description`, `name` |
| `realization` | 2 | 3 | `constraints` |
| `relationships` | 11 | 17 | `database_access`, `description`, `forwarding_edge`, `mail_access`, `proxy_upstream`, `service_integration` |
| `scripts` | 4 | 6 | `description`, `name` |
| `stories` | 2 | 4 | `description`, `name` |
| `workflows` | 2 | 5 | `compensation`, `description`, `timeout` |

These schema sections have no list: `action_contracts`, `execution_policy`,
`forwarding_agents`, `generated_artifacts`, `imports`, `module`,
`observation_boundaries`, `outcome_interpretation_rules` and
`persistent_volumes`. The schema's other four top-level properties are scalars.

## Schema observations

S1 to S3 load each document with `yaml.safe_load` and validate it against
`contracts/schemas/sdl/sdl-authoring-input-v1.json` with the
`Draft202012Validator` of `jsonschema` 4.26.0. That is how an editor association
checks raw source.

| ID | Operation | Observed result | Limit |
| --- | --- | --- | --- |
| S1 | The 21 `*.sdl.yaml` files under `examples/` and `docs/public/_static/examples/` | `language_diagnostics` accepts all 21. The schema rejects one, `docs/public/_static/examples/first-scenario.sdl.yaml`: its `/nodes/lab-network/type` is `Switch`, and the schema allows only `compute` and `switch`. | |
| S2 | Six documents that `language_diagnostics` accepts: P without `relationships`, four edits of M, and a document with the node `web` and `infrastructure: {web: 2}` | P without `relationships` has no schema error. The other five have one each. The edits of M are `type: Service` in the feature, `source: webapp`, `features: [app]` in place of the node's `features` and `roles`, and `roles: {client: www}`. | |
| S3 | Four documents that `language_diagnostics` rejects | `features: {missing: client}` in M (`sdl.semantic`) passes the schema. So does `name: demo` followed by `name: again` (`sdl.mapping_key_conflict`). `colour: blue` in M's node (`sdl.model.invalid`) and the key `Features` in M (`sdl.noncanonical_field`) fail it. | `yaml.safe_load` keeps only the last duplicate key, so the schema never sees the first |
| S4 | Read the schema's annotations, and request its `$id` with `curl -L` | `x-raes-validates-raw-source` is `false`. `$id` is `https://openrae.github.io/rae/schemas/sdl-authoring-input-v1.json`, and the request returned HTTP 404 on 2026-10-09 at 11:45 UTC. | |
| S5 | Compare the schema at tag `v6.0.1` with this revision. Run `language_diagnostics` on `name: demo` plus `execution_policy: {}` at both. | At `v6.0.1` the schema has 45 top-level properties and 602 `$defs` entries, and no top-level `execution_policy`. At this revision it has 46 and 606, including `execution_policy`. The document is valid at this revision. With the `v6.0.1` package tree on `PYTHONPATH`, it fails with `sdl.model.invalid`, "Extra inputs are not permitted", at `/execution_policy`. | The `v6.0.1` run used this revision's dependencies, not the wheel's |
| Y1 | yaml-language-server 1.24.0 from npm, over stdio, with the association that a VS Code `yamlValidation` entry for `*.sdl.yaml` produces. The schema is the prototype's copy of this revision's file, SHA-256 `162121460f19a555f4e7c469a3e4574fe4ed5ecabe628836bf1880ede5f1aba0`. | 20 of the 21 S1 files get no diagnostics. `first-scenario.sdl.yaml` gets "Value is not accepted" on `type`. Each of the five accepted shorthand and case forms in S2 gets one diagnostic, and the unresolved reference in S3 gets none. On an empty line inside `/nodes/web`, where only `type` is present, completion offers 15 fields. Hover on `type` shows the `NodeType` description. | Red Hat's YAML extension 1.24.0 uses this server version. VS Code itself was not started. |

## Inspected seams

These source locations support the claims that a probe does not show. All
package paths are relative to `implementations/python/packages/`.

| Concern | Source and inspected symbol |
| --- | --- |
| Field lists | `raes/_language_metadata.py`: `SECTION_FIELD_COMPLETIONS`, a hand-kept tuple of field names for each section |
| Completion depth | `raes/language_service.py`: `language_completions`. A path of one section name, and any longer path that does not end in a reference field, both read `SECTION_FIELD_COMPLETIONS[pointer[0]]`. |
| Reference completion | `raes/_language_metadata.py`: `REFERENCE_COMPLETION_TARGETS`; `raes/language_service.py`: `_completion_target_section`, `_reference_completion_items` |
| Completion on text that does not parse | `raes/language_service.py`: `_load_completion_data` returns the parse diagnostic instead of items |
| Semantic diagnostics | `raes/language_service.py`: `language_diagnostics` turns each message in `SDLValidationError.errors` into an `sdl.semantic` record without a path or range |
| Document context | Each helper takes text only. `language_diagnostics` calls `parse_sdl` without a path. |
| Handled exceptions | `raes/language_service.py`: `language_diagnostics` catches `SDLParseError` and `SDLValidationError`. `_load_completion_data`, `_try_declaration_index` and `language_format` catch `SDLParseError`. `_declaration_index_from_data` catches the pydantic `ValidationError`. `apply_structured_edit` catches `SDLParseError` and `ValueError`, and `_split_pointer_or_empty` catches `ValueError`. `raes/_language_references.py`: `_compose_yaml`, which `find_references` calls, catches `SDLParseError`. `_qualified_symbol_section`, `_is_variation_member_symbol` and `_bare_symbol` catch `TypeError` and `ValueError` from symbol parsing. `format_sdl_source` (`raes/formatting.py`) re-parses its output with `parse_sdl(..., skip_semantic_validation=True)`, and `parse_sdl` (`raes/parser.py`) still runs `SemanticValidator` for a `MaterializedScenario`, so `language_format` lets `SDLValidationError` reach the caller. Any other exception reaches the caller. |
| Input limit | `raes/language_service.py`: `_MAX_INPUT_BYTES`, `_size_error` |
| Formatting | `raes/language_service.py`: `language_format`, whose docstring reads "Migrate recognized legacy spellings and return canonical SDL YAML"; `raes/formatting.py`: `format_sdl_source` |
| Module cache | `raes/module_registry/__init__.py`: `_oci_cache_dir` returns `.raes/module-cache` under the base directory |
| Import trust | `raes/composition/_expand.py`: `expand_sdl_modules` calls `load_lockfile` and `load_trust_policy` on the document's directory. `raes/module_registry/models.py`: `load_trust_policy` returns `TrustPolicy()`, with no registries, when `raes-trust.yaml` is missing; `RegistryTrustPolicy.require_signatures` defaults to `True`. `raes/module_registry/resolution.py`: `_resolve_oci_import` raises "is not allowed by trust policy" for an unlisted registry before any request. For a listed registry it then fetches the manifest, config and bundle, checks signatures if the registry requires them, and only then calls `_extract_bundle_to_cache`. The integration test `test_untrusted_and_unsigned_oci_imports_fail_closed` in `implementations/python/tests/test_sdl_module_registry.py` asserts both refusals. |
| Schema for an installed `raes` | `raes_contracts/corpus.py`: `corpus_family_root`. The wheel build bundles the contract corpus at `raes_contracts/_corpus`, as the comment above `[tool.hatch.build.targets.wheel.hooks.custom]` in `implementations/python/pyproject.toml` describes. |
| Python range | `implementations/python/pyproject.toml` at tag `v6.0.1`: `requires-python = ">=3.11,<3.15"` |

## Reproduce

The prototype's
[evidence scripts](https://github.com/doublewhy/vscode-raes-sdl/tree/feac96e0d5262d914c11deecb209426851915763/evidence)
automate L1 to L11, S1 to S3 and Y1. Each script takes the path of a RAES
checkout and runs under that checkout's Python environment. The Y1 script also
takes the directory where `yaml-language-server@1.24.0` is installed. At this
revision the scripts printed the results above, and L11 records three runs of
the latency script. S4 and S5 used `curl`, `git show` and `git archive` on tag
`v6.0.1`. L12 called the helpers directly, in-process, on the inputs that its
row names.
