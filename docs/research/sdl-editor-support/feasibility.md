# SDL editor support feasibility

Date: 2026-10-09

This note answers issue #1412: should RAES support SDL authoring in VS Code, and what scope
would justify the work? It is research evidence, not contract authority.

The observations use repository revision `35122105b0c1bb648754625d8e3920eafa9bc599`. The
[evidence record](evidence.md) holds the probe inputs and outputs, and IDs such as L4 name its
rows. Claims about the editor client rest on a prototype extension at
[doublewhy/vscode-raes-sdl](https://github.com/doublewhy/vscode-raes-sdl/tree/feac96e0d5262d914c11deecb209426851915763).
The prototype stays outside this repository because the issue asks for an exploration, and an
extension here would be executable adoption.

## Recommendation

Build one language server over the existing helpers and keep each editor client thin. A VS Code
extension is worth having as that thin client. It does not need its own SDL logic.

The smallest useful feature set is:

1. File association for `*.sdl.yaml`.
2. Diagnostics from `language_diagnostics`, debounced while the author types.
3. Reference completion and go to definition from `language_completions` and
   `language_references`.

Leave out formatting, edit actions, and schema diagnostics until the gaps below are closed.
Formatting and structured edits drop comments. Schema diagnostics disagree with RAES validation.

Reusable components already exist. The five helpers carry the semantics. The published schema
serves completion and hover. `raes_contracts.corpus` locates the schema that matches an installed
`raes`. From the prototype, the stdio server and its cursor mapper are reusable starting points.

These helper changes would remove most of the work that each client now repeats:

1. Accept a line and column, or return a map from positions to paths.
2. Give semantic diagnostics a path and a source range.
3. Derive field completion from the model at every depth, not from hand-kept lists.
4. Offer only references that the field's purpose accepts, as #1339 requires.
5. Accept an optional document path, so local imports can resolve.
6. Return a diagnostic for every input instead of raising.

### Alternatives

The issue lists four alternatives:

1. **YAML tooling with the schema association and explicit CLI validation: rejected as the
   main path.** The association gives completion and hover, but its diagnostics disagree with
   RAES (S2, S3 and Y1). `raes semantic validate` reports RAES results only when the author runs
   it. Both remain useful without an extension.
2. **A highlighting and snippet extension: rejected.** Highlighting adds little over YAML, and
   neither feature gives diagnostics or references.
3. **Direct VS Code language-feature providers over the helpers: rejected.** They still need a
   Python process to run the helpers, and they serve only VS Code. Other editors and Monaco would
   each need their own providers.
4. **One language server with thin editor clients: selected.** One server serves every LSP
   client, and the editor-specific code stays small.

## What the language service supports

[`raes.language_service`](../../../implementations/python/packages/raes/language_service.py)
has five helpers that return plain dictionaries. The MCP server wraps them as the
`language_service` tool family. This repository ships no language server.

| Helper | Input | Result | Editor use |
| --- | --- | --- | --- |
| `language_completions` | Text, a JSON-pointer-like `cursor_path`, a prefix | Top-level keys, section fields, or reference candidates | Completion |
| `language_references` | Text, a bare or qualified symbol | Definitions and occurrences with 1-based ranges | Go to definition, find references |
| `language_diagnostics` | Text, a `semantic_validation` flag | Parse, structural, and semantic records | Diagnostics |
| `language_format` | Text | Canonical YAML with migration advisories | Formatting |
| `apply_structured_edit` | Text, an operation, a JSON pointer, a value | Edited YAML with diagnostics | Code actions |

The helpers reuse the repository parser and semantic validator. Each one refuses input over
64 KiB. The [language-service guide](../../explain/sdl/language-service.md) describes the
payloads.

## What the editor integration needs

A VS Code integration needs these parts:

- A language contribution that maps `*.sdl.yaml` to a language identifier.
- A client that starts the server. With `vscode-languageclient`, the prototype's client is 41
  lines.
- A server that turns cursor positions into helper paths and helper ranges into LSP ranges. It
  also debounces diagnostics and copes with documents that do not parse yet.
- A setting that picks the Python interpreter. The `raes` version installed there decides the
  semantics.
- A Workspace Trust declaration, because that setting names a program to run. If the server
  resolves imports, the workspace's `raes-trust.yaml` also decides which registries an import may
  fetch from.
- A package built with `vsce`. A VS Code package cannot declare Python dependencies, so authors
  install `raes` with `pip`.

## What the prototype demonstrates

The prototype has a TextMate grammar, a schema association, and a stdio language server. The
server uses only the Python standard library and `raes`. Sixteen tests drive the server over
stdio with the messages that the VS Code client sends. Nine test the cursor mapper, and six
tokenize SDL with VS Code's YAML grammar. All 31 passed locally against revision `35122105`,
and in [CI run 37926735623](https://github.com/doublewhy/vscode-raes-sdl/actions/runs/37926735623)
with `raes` 6.0.1 from PyPI. In that run, `vsce package` built a 571 KB package. Nothing is
published to the Marketplace, and no test starts VS Code itself.

| Feature | Result |
| --- | --- |
| Diagnostics | Parse and structural errors keep their RAES ranges. Semantic errors have no location, so they appear on line 1 with a note. |
| Completion | Works on documents that parse. Otherwise the server answers from the last version that parsed and marks the items. |
| Go to definition | Works inside one file through `language_references`. |
| Highlighting | Top-level SDL keys and `${variable}` placeholders get their own scopes. A test checks the key list against the schema. |
| Schema association | Completion and hover work in yaml-language-server 1.24.0. Its diagnostics disagree with RAES. |
| Formatting | Not offered, because the helper drops comments. |

The server forwards reference candidates unfiltered, so the #1339 mismatch stays visible. It
drops field names only after `key:` or inside a flow sequence, where no mapping key can go. That
is a YAML rule, not an SDL rule. When a helper raises, the server reports one diagnostic and
keeps running. Two tests check this with helpers that raise on a marker line.

## Gaps

| Area | Observation | Evidence |
| --- | --- | --- |
| Reference completion | For a participant relationship `target`, completion offers six declarations. Validation accepts one, the agent that is not the source. This is the #1339 mismatch. | L1; finding F5 in the [participant identity audit](../participant-identity/audit.md) |
| Field lists | The hand-kept lists miss 69 schema fields across 18 of 33 sections. The `features` list offers `version`, which validation rejects. | L2 and L3; `SECTION_FIELD_COMPLETIONS` in [`_language_metadata.py`](../../../implementations/python/packages/raes/_language_metadata.py) |
| Completion depth | Field completion uses only the section name. `/nodes`, `/nodes/web`, and `/nodes/web/resources` get the same nine fields. | L10; the field branches of `language_completions` in [`language_service.py`](../../../implementations/python/packages/raes/language_service.py) |
| Cursor paths | The helpers take a JSON pointer, so each client derives one from the text. The prototype's mapper has 204 lines and skips multi-line flow collections, block scalars, anchors, tags, and complex keys. | Prototype [`server/sdl_cursor.py`](https://github.com/doublewhy/vscode-raes-sdl/blob/feac96e0d5262d914c11deecb209426851915763/server/sdl_cursor.py) |
| Source ranges | Semantic diagnostics have no path or range. An unknown field is ranged on its value, not its key. A YAML syntax error is a single point. | L5 |
| Incomplete documents | Completion needs a document that parses. An unclosed `[` or a key without its colon gives a parse error and no items. | L4 |
| Imported modules | The helpers take no file path, so a document with `imports` is invalid even without semantic validation. `parse_sdl_file` accepts the same fixture. | L8 |
| Workspace context | The helpers see one document. Nothing indexes the workspace or follows references across files. | [`language_service.py`](../../../implementations/python/packages/raes/language_service.py) |
| Robustness | Every helper turns `SDLParseError` into a result. `language_diagnostics` also turns `SDLValidationError` into one, and `apply_structured_edit` and `language_format` check their output with `language_diagnostics`. But `language_format` lets `SDLValidationError` reach the caller for a document with `materialization_provenance`. For such a document, `parse_sdl` runs the semantic validator even though `format_sdl_source` skips it. Other exceptions reach the caller too, unless a catch listed under inspected seams handles them, so a server must guard every call. | L12; handled exceptions under [inspected seams](evidence.md#inspected-seams) |
| Large scenarios | The largest repository example is 46 KB, under the 64 KiB limit. Each call parses the whole text. On that file a warm call took 160 to 175 ms at load average 7 to 13, and about 375 ms at load average 22. A cold start took 1.2 to 2.9 s. The machine was shared, so the timings are indicative. | L9 and L11 |
| Formatting and edits | Both drop comments and expand shorthand. Formatting also lowers enum case and migrates recognized legacy spellings. | L6 and L7; the `language_format` docstring |
| Schema validation | The schema describes the normalized object, so `x-raes-validates-raw-source` is `false`. It flags accepted shorthand and case variants and misses semantic errors. | S2 to S4 and Y1 |
| Schema versions | The schema's `$id` returned HTTP 404. The schema on `dev` declares `execution_policy`, which `raes` 6.0.1 rejects. | S4 and S5 |

The schema check flags one of the 21 accepted examples (S1): the quickstart's
`first-scenario.sdl.yaml` uses `type: Switch`. Any fix for imports must also handle registry
imports. When `parse_sdl` gets a path and the document has `imports`, it reads `raes.lock.json`
and `raes-trust.yaml` from the document's directory. It refuses an OCI import before any request
unless that trust file lists the import's registry. For a listed registry it fetches the module.
Once the registry's signature policy passes, it writes `.raes/module-cache` next to the document.
The trust file is workspace content, so a path-aware server should resolve imports only in a
trusted workspace (Import trust under [inspected seams](evidence.md#inspected-seams)).

## Answers to the issue's questions

### Which features are most useful

Diagnostics come first. They need no cursor mapping and reuse the full validator. Reference
completion and go to definition come next. They help most on reference-heavy sections, but
completion inherits the #1339 mismatch. Schema hover shows field descriptions. Highlighting adds
little over plain YAML. Snippets and a document outline were not prototyped. Snippets give no
diagnostics or references (alternative 2), so they rank low. None of the five helpers returns the
document's declarations with their ranges, so an outline needs new helper or server work. It
would help in long scenarios, but it ranks after diagnostics and references. Formatting should
wait until comments survive it.

### Can YAML support and the schema provide enough value

They are enough for completion and hover, not for diagnostics. Inside a node, schema completion
offered the 15 node fields not yet present (Y1). The helper's list for nodes has 9 fields in all
(L10). Hover showed the schema's descriptions. But schema diagnostics flagged all five accepted
shorthand and case forms that the probe tried. They also missed an unresolved reference. A
dedicated extension is warranted only to add RAES diagnostics and reference features.

Red Hat's YAML extension serves only the languages in its own document selector ([R2](#references)).
So an extension must choose:

- Its own language identifier, with SDL highlighting but no schema completion.
- The `yaml` identifier, with schema completion but plain YAML highlighting.

The prototype supports both.

### Would an LSP adapter enable reuse

Yes, for desktop editors. Any LSP client can start the same stdio command. VS Code needs the thin
extension described above. Other editors that speak LSP should need only their own settings for
the command and the file pattern. They were not tested.

Monaco is different. A browser page cannot start a Python process. A Monaco client would need a
server reached over a WebSocket, for example through
[monaco-languageclient](https://github.com/TypeFox/monaco-languageclient). Running `raes` in
the browser was not evaluated. [monaco-yaml](https://github.com/remcohaszing/monaco-yaml) gives
Monaco the schema features, as the YAML extension does in VS Code. A VS Code extension does not
run inside Monaco.

### What gaps exist

See [Gaps](#gaps). The cursor-to-path mapping, source ranges, incomplete documents, imports,
workspace context, and large scenarios each have a row there. So does the #1339 completion
mismatch.

### How packaging and versions should work

- **File association.** The repository names 40 SDL files `*.sdl.yaml` (L9). VS Code prefers the
  longest matching extension, so `.sdl.yaml` wins over `.yaml` ([R1](#references)). Files such as
  the composition fixtures end in `.yaml` and need a `files.associations` entry.
- **Version selection.** The server runs in an interpreter that the author picks, and it reports
  the `raes` version. A schema bundled in the extension can drift from that version, as S5 shows.
  The `raes` wheel bundles its own copy, reachable through
  `raes_contracts.corpus.corpus_family_root`, so a server could serve the matching schema.
- **Local and offline use.** The helpers work on the buffer text in-process. They read no other
  document and use no network. Resolving imports would change that, so it should stay opt-in.
  Red Hat's YAML extension downloads the SchemaStore catalog by default
  (`yaml.schemaStore.enable`, [R3](#references)).
- **Packaging.** `vsce package` works without bundling Python. Authors install `raes` from PyPI.
  Version 6.0.1 requires Python 3.11 to 3.14. In Restricted Mode, VS Code ignores a workspace
  value of the interpreter setting if the extension lists it in `restrictedConfigurations`
  ([R4](#references)).

## Compatibility notes

- **SDL semantics stay in RAES.** The prototype server adds no SDL rules. The grammar's key list
  mirrors the schema's top-level properties, and a test checks that they match.
- **No launch and no fetch.** The helpers parse and validate text. Nothing runs a scenario or
  downloads content.
- **Formatting.** `language_format` drops comments, expands shorthand, normalizes enum case, and
  migrates legacy spellings. Format on save would rewrite authored text, so formatting should be
  an explicit command at most.
- **Monaco.** Shared services are the helpers, the published schema, and one language server.
  Editor adapters are the VS Code client, a Monaco client, and other editors' settings.

## Method

The probes call the helpers on small documents and on the repository examples. They compare the
results with the published schema and with yaml-language-server 1.24.0. Version 1.24.0 is the
server that Red Hat's YAML extension 1.24.0 uses. Nothing was mocked. The
[evidence record](evidence.md) gives each probe's input and output and the source locations
behind the other claims. It also links to the scripts that reproduce most probes. They live in
the prototype's repository, not in this one. The prototype's tests and CI run cover only the
editor client.

## References

- R1: VS Code 1.140.0,
  [`languagesAssociations.ts`](https://github.com/microsoft/vscode/blob/1.140.0/src/vs/editor/common/services/languagesAssociations.ts),
  the longest extension match.
- R2: Red Hat YAML extension 1.24.0,
  [`src/extension.ts`](https://github.com/redhat-developer/vscode-yaml/blob/1.24.0/src/extension.ts),
  the client document selector and the `yamlValidation` association.
- R3: Red Hat YAML extension 1.24.0,
  [`package.json`](https://github.com/redhat-developer/vscode-yaml/blob/1.24.0/package.json),
  the `yaml.schemaStore.enable` default.
- R4: VS Code, [Workspace Trust extension guide](https://code.visualstudio.com/api/extension-guides/workspace-trust).
- VS Code, [language server extension guide](https://code.visualstudio.com/api/language-extensions/language-server-extension-guide).
