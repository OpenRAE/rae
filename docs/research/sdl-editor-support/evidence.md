# SDL editor support evidence

Observed 2026-11-12 on repository revision
`c7d499979eb32e16d9a2c46ca10b5aa1403b4511`, except L11 and Y1. The
[feasibility note](feasibility.md) interprets these observations. The probes
called the language-service helpers in-process, with the working tree at that
revision and the repository Python environment (CPython 3.14.7). Nothing was
mocked, and no scenario was launched. The probes establish helper and schema
behavior on small inputs. They are not a usability, conformance or security
result.

The rows were first observed on 2026-10-09 and 2026-10-10 at revision
`35122105b0c1bb648754625d8e3920eafa9bc599`, with CPython 3.14.4, free-threaded.
L11 and Y1 were not run again, and they remain observations of that revision.
[Changes since the first observation](#changes-since-the-first-observation)
lists the rows whose results changed.

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
| L1 | `language_completions(P, cursor_path="/relationships/pair/target")`, then `language_diagnostics` of P with the offered `insert_text` as the target, and with each of the other five declarations of P as the target | Context `reference:eligible:participant_endpoint`, with one item: label `two`, detail `agents.two`. P with target `two` is valid. `agents.one` fails with "Relationship 'pair' requires distinct participants". `assertions.done`, `entities.team`, `propositions.ok` and `relationships.pair` fail because the target must "resolve unambiguously to a declared agent". | At `35122105`, completion offered all six declarations. Finding F5 in the [participant audit](../participant-identity/audit.md) reports that mismatch, and #1339 closed it. |
| L2 | Compare each list in `SECTION_FIELD_COMPLETIONS` with the property names that the published schema declares for that section | 18 of the 34 lists differ from the schema. Together they omit 69 schema fields. The `features` list also offers `version`, which the schema does not declare. The table below lists the differences. | The comparison merges every union branch. Eleven schema sections have no list. |
| L3 | `language_completions` on a document whose only feature is `app: {type: service}`, with `cursor_path="/features/app"` and `prefix="v"`; then `language_diagnostics` with `version: '1.0'` added to that feature | Completion offers `version`. Diagnostics report `sdl.model.invalid`, "Extra inputs are not permitted", at `/features/app/version`. | |
| L4 | `language_completions(text, cursor_path="/nodes/web/features")` on N and on four edits of N | N gives `ok` with `app`. `features:` with no value gives `ok` with `app`. `features: [` gives `invalid` with `sdl.parse`. `fea` in place of the `features` line gives `invalid` with `sdl.parse`. `type: VM` gives `invalid` with `sdl.legacy_node_type_vm`. | A parse failure anywhere in the document removes every item |
| L5 | `language_diagnostics` on four documents, and on the second document again with a `path` to a file that holds it | Adding `colour: blue` under `web` in N gives `sdl.model.invalid` at `/nodes/web/colour`, on line 10, columns 13 to 17. The key starts at column 5. `features: [missing]` in N gives `sdl.semantic` at the `semantic_validation` stage, with no path and no range. With the `path`, the same diagnostic has path `/nodes/web` and a range on the key `web`, line 5, columns 3 to 6. `name: demo` followed by `name: again` gives `sdl.mapping_key_conflict` at `/name`, on line 2, columns 1 to 5. An unclosed `web: {type: compute` gives `sdl.parse` with an empty path and one point, line 4, column 1. | The point in the last case is the end of the input. The ranged semantic diagnostic marks the owner declaration, not the reference `missing`. |
| L6 | `language_format` on a document with three comments and the feature `app: {type: Service, source: webapp}` | Status `formatted`. The output has no comments. `type: Service` becomes `type: service`, and `source: webapp` becomes a mapping of `name: webapp` and `version: '*'`. | |
| L7 | `apply_structured_edit` on N with two added comments, operation `set`, pointer `/nodes/web/os`, value `windows` | Status `edited`. The output has no comments. `source: webapp` expands as in L6, and `features: [app]` becomes the mapping `app: ''`. | |
| L8 | `parse_sdl_file` and `language_diagnostics` on `contracts/fixtures/sdl/variation-points-v1/composition/root.yaml`; then `language_diagnostics` and `language_format` with `path` set to that file | `parse_sdl_file` returns an `ExpandedScenario`. On the same text without a `path`, `language_diagnostics` returns `sdl.parse`, "SDL imports require file-backed parsing via parse_sdl_file()". Turning off `semantic_validation` gives the same result. With the `path`, `language_diagnostics` returns `valid` and `language_format` returns `formatted`. | The fixture has only local imports |
| L9 | File sizes of the tracked `*.sdl.yaml` files, against `_MAX_INPUT_BYTES` | The limit is 65,536 bytes. None of the 60 files is over it. The largest is `examples/scenarios/hospital-ransomware-surgery-day.sdl.yaml`, at 46,073 bytes. | |
| L10 | `language_completions(N, cursor_path=path)` for `/nodes`, `/nodes/web`, `/nodes/web/resources` and `/nodes/web/os` | Each call returns context `section:nodes` and the same nine fields: `type`, `description`, `os`, `resources`, `features`, `conditions`, `services`, `roles` and `endpoint_persona`. | |
| L11 | Median of 5 warm calls of `language_diagnostics`, and of `language_completions` at `/nodes`, on the L9 file. Median of 3 fresh interpreters that import `raes` and make one diagnostics call. | At load average 7.2: 172 ms and 159 ms warm, and 1,207 ms cold. At 13.1: 174 ms and 163 ms warm, and 1,297 ms cold. At 22.5: 377 ms and 373 ms warm, and 2,939 ms cold. | Observed at `35122105` only. An 8-core Apple M3 that other work shared. The timings are indicative. |
| L12 | The five helpers on two documents: `contracts/fixtures/sdl/materialized-scenario-v1/valid/reference.json` with N's node `web` added, and N. In both, the node's `features` is `[missing]`. Completion uses `cursor_path="/nodes/web/features"`, references use the symbol `web`, and the edit is L7's. | On the fixture, `language_diagnostics` returns `invalid` with `sdl.semantic`. `language_format` raises `SDLValidationError`, "Node 'web' references undefined feature 'missing'". Completion and references return `ok`, and the edit returns `edited_with_diagnostics` with `sdl.semantic`. The fixture's JSON text and its YAML dump behave the same. On N nothing raises, and `language_format` returns `formatted_with_diagnostics` with `sdl.semantic`. | |
| L13 | The four path-aware helpers on `root.sdl.yaml` in an empty directory, with `path` set to that file. The document imports `oci:127.0.0.1:9/acme/shared`. A `raes-trust.yaml` beside it lists that registry with `require_signatures: false`. A wrapper around `raes.module_registry.urlopen` recorded each request. | `language_diagnostics` and `language_format` return `sdl.import.source-refused`, "Registry import 'oci:127.0.0.1:9/acme/shared' is not resolved in editor path mode; validate with parse_sdl_file()", at `/imports/0`. Completion at the top level and references for `shared` return `ok`. The wrapper recorded no request, and no `.raes` directory appeared. | The diagnostic's range is line 1, column 1, not the import entry |

L2 counts, for each list, the distinct property names that the schema declares
for one entry of the section. For a section that is one object, such as
`realization`, it counts that object's properties. The count follows `$ref` and
merges `anyOf`, `oneOf` and `allOf` branches. These lists differ:

| Section | Offered | In schema | Schema fields not offered |
| --- | --- | --- | --- |
| `accounts` | 7 | 14 | `description`, `disabled`, `groups`, `home`, `mail`, `materialization_profile`, `shell` |
| `agents` | 8 | 13 | `allowed_subnets`, `authority_anchors`, `description`, `observation_boundaries`, `operating_scope` |
| `behavior_specifications` | 19 | 20 | `autonomous_execution` |
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
`observation_boundaries`, `outcome_interpretation_rules`, `persistent_volumes`,
`safe_state` and `trial_parallelism`. The schema's other four top-level
properties are scalars.

## Schema observations

S1 to S3 load each document with `yaml.safe_load` and validate it against
`contracts/schemas/sdl/sdl-authoring-input-v1.json` with the
`Draft202012Validator` of `jsonschema` 4.26.0. That is how an editor association
checks raw source.

| ID | Operation | Observed result | Limit |
| --- | --- | --- | --- |
| S1 | The 27 `*.sdl.yaml` files under `examples/` and `docs/public/_static/examples/`. Diagnostics use each file's `path`. | `language_diagnostics` accepts all 27. The schema rejects one, `docs/public/_static/examples/first-scenario.sdl.yaml`: its `/nodes/lab-network/type` is `Switch`, and the schema allows only `compute` and `switch`. | |
| S2 | Six documents that `language_diagnostics` accepts: P without `relationships`, four edits of M, and a document with the node `web` and `infrastructure: {web: 2}` | P without `relationships` has no schema error. The other five have one each. The edits of M are `type: Service` in the feature, `source: webapp`, `features: [app]` in place of the node's `features` and `roles`, and `roles: {client: www}`. | |
| S3 | Four documents that `language_diagnostics` rejects | `features: {missing: client}` in M (`sdl.semantic`) passes the schema. So does `name: demo` followed by `name: again` (`sdl.mapping_key_conflict`). `colour: blue` in M's node (`sdl.model.invalid`) and the key `Features` in M (`sdl.noncanonical_field`) fail it. | `yaml.safe_load` keeps only the last duplicate key, so the schema never sees the first |
| S4 | Read the schema's annotations, and request its `$id` with `curl -L` | `x-raes-validates-raw-source` is `false`. `$id` is `https://openrae.github.io/rae/schemas/sdl-authoring-input-v1.json`. The request returned HTTP 404 on 2026-10-09 at 11:45 UTC and on 2026-11-12 at 05:38 UTC. | |
| S5 | Compare the schema at tag `v6.0.1` with this revision. Run `language_diagnostics` on `name: demo` plus `execution_policy: {}` at both. | At `v6.0.1` the schema has 45 top-level properties and 602 `$defs` entries, and no top-level `execution_policy`. At this revision it has 49 and 656, including `execution_policy`, `safe_state` and `trial_parallelism`. The document is valid at this revision. With the `v6.0.1` package tree on `PYTHONPATH`, it fails with `sdl.model.invalid`, "Extra inputs are not permitted", at `/execution_policy`. | `v6.0.1` is still the latest release tag. Its run is from 2026-10-09 and used the dependencies of `35122105`, not the wheel's. |
| Y1 | yaml-language-server 1.24.0 from npm, over stdio, with the association that a VS Code `yamlValidation` entry for `*.sdl.yaml` produces. The schema is the prototype's copy of the file at `35122105`, SHA-256 `162121460f19a555f4e7c469a3e4574fe4ed5ecabe628836bf1880ede5f1aba0`. | 20 of the 21 S1 files at `35122105` get no diagnostics. `first-scenario.sdl.yaml` gets "Value is not accepted" on `type`. Each of the five accepted shorthand and case forms in S2 gets one diagnostic, and the unresolved reference in S3 gets none. On an empty line inside `/nodes/web`, where only `type` is present, completion offers 15 fields. Hover on `type` shows the `NodeType` description. | Observed at `35122105` only. The schema at this revision has SHA-256 `9acc517a1ed8dbdb466b3658aede90456cf5c5972e86d061d414944328deb2ce`, and S1 to S3 repeat the same schema results with it. Red Hat's YAML extension 1.24.0 uses this server version. VS Code itself was not started. |

## Inspected seams

These source locations support the claims that a probe does not show. All
package paths are relative to `implementations/python/packages/`.

| Concern | Source and inspected symbol |
| --- | --- |
| Field lists | `raes/_language_metadata.py`: `SECTION_FIELD_COMPLETIONS`, a hand-kept tuple of field names for each section |
| Completion depth | `raes/language_service.py`: `language_completions`. A path of one section name, and any longer path that does not end in a reference field, both read `SECTION_FIELD_COMPLETIONS[pointer[0]]`. |
| Reference completion | `raes/_language_metadata.py`: `REFERENCE_COMPLETION_TARGETS`; `raes/language_service.py`: `_completion_target_section`, `_reference_completion_items`, `_purpose_completion_items`; `raes/_reference_targetability.py`: `purposes_for_domain`; `raes/_language_relationship_candidates.py`: `filter_relationship_candidates` |
| Completion on text that does not parse | `raes/_language_context.py`: `load_completion_data` returns the parse diagnostic instead of items |
| Semantic diagnostics | `raes/language_service.py`: `language_diagnostics` uses the entry of `SDLValidationError.diagnostics` for a message when one exists. Otherwise it makes an `sdl.semantic` record without a path or range. `raes/_declaration_sources.py`: `semantic_source_diagnostics` makes an entry only for a finding whose owner declaration has a recorded source, and it ranges the entry on that declaration's key. |
| Document context | Each helper takes the text and an optional `path`. With a `path`, `_local_traversal` starts `CompositionTraversal.local_root` (`raes/_composition_budget.py`), and `raes/module_registry/resolution.py` refuses a registry import in that mode before any request. The helpers read no other open document. |
| Handled exceptions | `raes/language_service.py`: `language_diagnostics` catches `SDLParseError` and `SDLValidationError`. `language_format` catches `SDLParseError`. `apply_structured_edit` catches `SDLParseError` and `InvalidInputError`, and `_split_pointer_or_empty` catches `InvalidInputError`. `raes/_language_context.py`: `load_completion_data` and `reference_context` catch `SDLParseError`, `_composed_data` catches `SDLError` and the pydantic `ValidationError`, and `_validated` catches `ValidationError`. `raes/_language_relationship_candidates.py`: `_semantic_errors` catches `SDLValidationError`, and `_candidate_scenario` catches `ValidationError`. `raes/_language_structural_variation.py`: `_child_candidates` and `_record_candidates` catch `ValueError`. `raes/_language_references.py`: `_compose_yaml`, which `find_references` calls, catches `SDLParseError`. `_qualified_symbol_section`, `_is_variation_member_symbol` and `_bare_symbol` catch `TypeError` and `ValueError` from symbol parsing. `format_sdl_source` (`raes/formatting.py`) re-parses its output with `parse_sdl(..., skip_semantic_validation=True)`, and `parse_sdl` (`raes/parser.py`) still runs `SemanticValidator` for a `MaterializedScenario`, so `language_format` lets `SDLValidationError` reach the caller. Any other exception reaches the caller. |
| Input limit | `raes/language_service.py`: `_MAX_INPUT_BYTES`, `_size_error` |
| Formatting | `raes/language_service.py`: `language_format`, whose docstring reads "Migrate recognized legacy spellings and return canonical SDL YAML"; `raes/formatting.py`: `format_sdl_source` |
| Module cache | `raes/module_registry/__init__.py`: `_oci_cache_dir` returns `.raes/module-cache` under the base directory |
| Import trust | These steps apply to `parse_sdl` and `parse_sdl_file`, not to the helpers' path mode. `raes/composition/_expand.py`: `expand_sdl_modules` calls `load_lockfile` and `load_trust_policy` on the document's directory. `raes/module_registry/models.py`: `load_trust_policy` returns `TrustPolicy()`, with no registries, when `raes-trust.yaml` is missing; `RegistryTrustPolicy.require_signatures` defaults to `True`. `raes/module_registry/resolution.py`: `_resolve_oci_import` raises "is not allowed by trust policy" for an unlisted registry before any request. For a listed registry it then fetches the manifest, config and bundle, checks signatures if the registry requires them, and only then calls `_extract_bundle_to_cache`. The integration test `test_untrusted_and_unsigned_oci_imports_fail_closed` in `implementations/python/tests/test_sdl_module_registry.py` asserts both refusals. |
| Schema for an installed `raes` | `raes_contracts/corpus.py`: `corpus_family_root`. The wheel build bundles the contract corpus at `raes_contracts/_corpus`, as the comment above `[tool.hatch.build.targets.wheel.hooks.custom]` in `implementations/python/pyproject.toml` describes. |
| Python range | `implementations/python/pyproject.toml` at tag `v6.0.1`: `requires-python = ">=3.11,<3.15"` |

## Reproduce

The prototype's
[evidence scripts](https://github.com/doublewhy/vscode-raes-sdl/tree/feac96e0d5262d914c11deecb209426851915763/evidence)
automate L1 to L11, S1 to S3 and Y1 as they ran at `35122105`. Each script
takes the path of a RAES checkout and runs under that checkout's Python
environment. The Y1 script also takes the directory where
`yaml-language-server@1.24.0` is installed. At `35122105` the scripts printed
the first results, and L11 records three runs of the latency script. S4 and S5
used `curl`, `git show` and `git archive` on tag `v6.0.1`.

The 2026-11-12 run at this revision called the helpers directly, in-process, on
the inputs that each row names. L1, L5, L8, S1 and L13 add calls that the
prototype's scripts do not make. L2 used the comparison that the paragraph
under the table describes. It also gave the first L2 result when it read the
schema and lists at `35122105`.

## Changes since the first observation

These rows changed between `35122105` and this revision:

| ID | At `35122105` | At this revision |
| --- | --- | --- |
| L1 | Six reference items for the participant target, five of them invalid | One item, `two`, which is valid |
| L2 | 33 lists, 9 schema sections without a list | 34 lists, 11 schema sections without a list. The 18 differing lists and 69 missing fields are the same. |
| L5 | The helpers took no `path` | With a `path`, an owned semantic diagnostic has a path and a range on its owner's key |
| L8 | No `path` parameter, so the fixture could not be checked | With a `path`, the fixture is valid |
| L9 | 40 files | 60 files, with the same largest file |
| L13 | No `path` parameter | Path mode refuses registry imports without a request |
| S1 | 21 example files | 27 example files, with the same single schema rejection |
| S5 | 46 top-level properties and 606 `$defs` entries | 49 and 656 |

L3, L4, L6, L7, L10, L12, S2, S3 and S4 gave the same results at both
revisions.
