# SDL language and authoring preflight

Issue #1786 is the contract for this requirement-free change.
This note sets design guardrails. It does not approve the future design or give implementation steps.
Inspection baseline: `29a0d35a5c3753d234fb790933adc70642c60bf4`.
The Python paths below are relative to `implementations/python/packages/`.
Go package paths are relative to `implementations/go/`.

## Ownership and dependencies

Keep language and authoring services in `rae`, with thin CLI and MCP adapters under #1797.
Use the existing `app` layer for shared flows and their results.
Keep SDL behavior in the SDL layer and published-contract rules in the contract layer.
The broad layer rules in `implementations/architecture.json` do not permit authoring services to import runtime.
The #1891 repo boundary and #1825 consumer API set that narrower rule.

| Concern | Existing owner to build on |
| --- | --- |
| Ordered YAML, source ranges, duplicate keys, migration and parser budgets | `internal/sdl/source`; #1782 source design |
| SDL documents, admission, imports, binding, edits and identity | `internal/sdl/authoring`; #1783–#1785 designs |
| Declarations, reference purposes and runtime collection identities | Authoring declaration/reference rules and `internal/contract/sdlrules`; #1784 collection descriptors |
| Schemas, defaults, model rules and context checks | `contract/binding`, `contract/validation`, `contract/admission`, `contract/concept` and `internal/contract/corpus` |
| Structured findings and operational failures | `contract/diagnostic`, `base/fault` and `internal/base/logrecord`; ADR-116 |
| Pointers, addresses, value bounds and identities | `internal/base/jsonpointer`, `base/address`, `internal/base/value`, `base/canonjson` and `base/digest` |
| Registry trust, locks, verified source snapshots and cache recovery | `sdl/module`; #1785 module design |
| Behavioral comparison and surface coverage | `internal/parity`, its runner inventory and `tools/parity_corpus.py`; #1778 design |

The public `sdl` and `sdl/language` APIs are planned. They do not yet exist at this baseline.
Their declarations name edits, completions, diagnostics and formatting. They do not cover every MCP tool or option.
For example, the service must also cover navigation and structural-only diagnostics.
MCP-only tools do not each need a public package or consumer API.
Any needed public API change must agree with #1825 and its declared types.
Do not expose `internal` types that public callers cannot import.

Compilation/planning (#1787), the stub manifest (#1790), and pure conformance (#1796) are also later owners in the current model.
Complete #1786 acceptance needs those owners too. The issue names only #1784/#1785 as prerequisites.
Declare the seams at their callers. Use the owners' native types as they become available.
Do not copy their logic or supply fake successes. Claim full parity only when those operations use real Go services.
Python subprocesses are not a port.

## One workflow, distinct phase contracts

One application flow owns parse, semantic admission, instantiation, compilation and reference planning.
It retains stage order and classifies failures.
CLI, MCP and parity runners call it. They do not copy the flow.
Inputs select the required phase and existing migration/binding policy.
Do not force every operation through planning or semantic admission.
`semantic parse` is structural; `semantic compile` uses the authored compilation entry point.
The MCP compilation flow explicitly instantiates first.
Preserve both behaviors through the owning compiler APIs.

One failure model must still serve each wire envelope.
Keep the semantic command result, MCP JSON records, prose results and protocol errors distinct.
The application owner maps each result. Adapters only bind inputs and render it.
Semantic exits remain success `0`, invalid `1`, usage `2`, unsupported `3`, operational `4`, and internal `70`.
Preserve stage order, advisories, null versus absent fields, empty arrays, validation strength, profiles and provenance.
SDL `semantic conformance` remains unsupported; portable conformance uses its registered contract owner.
A schema check alone proves neither context checks nor execution admission.

The reference stub manifest remains the default planning target. Get it from its single backend owner.
Pass the manifest at the application boundary.
A future choice of manifest must not require changes to either adapter or a copied manifest.
Do not add a new public flag or target behavior in this issue.
Planning proves a dry run, not execution, participant skill, visibility, causality or evidence quality.

`internal/parity/semantic_operations.go` already handles normalize, resolve and transform.
Move those decisions behind the application owner when adding the services.
Retain the existing runner keys and cases. The harness only adapts corpus inputs and results.
Do not leave this third workflow beside the CLI and MCP workflows.

## Security and validation boundaries

Each row is a separate gate; passing a later gate cannot replace an earlier one.

| Layer touched | Required control and incumbent |
| --- | --- |
| CLI/MCP argument boundary | Keep live command/tool names, parameter shapes, defaults and selector checks. `raes_mcp/server.py` names rejected declared arguments and expected types. It omits supplied values and nested error locations. #1797 retains protocol handling. |
| Limits and option shapes | Reuse source `Limits.Validate`, parser options and revision/migration checks. Limits must be positive. Zero cannot disable a ceiling. Charge combined inputs and import work before allocating their output. |
| Source and JSON decoding | Reuse bounded source decoding and `base/ingress` for strict portable JSON. Preserve UTF-8, duplicate-key, scalar, depth, node, alias and numeric checks before model construction. SDL and experiment YAML have different profiles. |
| Schema and model admission | Reuse packaged schemas, schema-derived bindings, constructor defaults and predicates. Then run the owning semantic/reference rules. Preserve `binding.Field` presence/null distinctions. Never copy schemas or validators into tools. |
| References and authored authority | Use declaration purposes, qualified addresses, ambiguity and namespace rules from the authoring owner. Targetability does not grant participation, authority or visibility. Inspection permits known SDL sections only, never arbitrary attribute or reflection traversal. |
| Source filesystem and module policy | Source maps stay isolated. They never fall back to host reads. Use explicit contained filesystems, such as host-granted `os.OpenRoot` access. `os.DirFS` alone does not contain symlinks. Root identity grants no access. Reuse workspace trust, locks, import budgets and copied verified bytes. |
| Network and authentication | Content-only MCP calls gain no filesystem or registry authority. Path-mode editor helpers compose local imports without registry fetches or cache writes. Semantic commands remain offline and read-only. No runtime HTTP, bearer/proxy authentication, principal or tenant model belongs in these services. |
| Secrets, environment bindings and OS exposure | Reuse `contract/admission/sdl_environment.go` and `sdl_secrets.go`, plus the SDL semantic checks. Keep logical secret IDs and URI checks with `internal/base/secretref` and `internal/base/urisafety`. Values stay inert. Do not read host environment values, look up credentials, execute commands or pass secrets in argv. No temporary scripts or network fallback are needed. The host owns native secrets. |
| Faults, diagnostics and logs | Use ADR-116 categories with standard error traversal and `contract/diagnostic.Error`. Operational fault codes obey `base/fault` syntax; dotted diagnostic codes are separate identifiers. Keep raw parser, OS, compiler and planner causes out of response envelopes. Use constant log messages through `logrecord`; log unexpected failures once at the outer boundary. |
| Results and persistence | Return copied bytes, collections and metadata. Edits affect only the root buffer. No service store, session database, autosave, implicit publication or second module cache is needed. The module owner keeps its locks, staging, integrity checks and recovery. |

Operational logs cannot contain source text, parameters, secret values or diagnostic messages that quote authored data.
The log handler sanitizes failures. It does not make all string attributes safe to log.
Source diagnostics can name authored identifiers where their owning contract allows it.
Semantic command refusals use narrower, value-free results.
Keep the fixed MCP unexpected-error response. Only protocol output goes to stdout; logs use the error stream.
Do not convert unexpected defects into valid, invalid-input or empty-success results.

## Compatibility traps

- MCP source operations and language helpers use 64 KiB limits.
  Each operation defines which section/context or source/parameter sizes it adds together.
  The SDL parser default and portable semantic JSON limit are 8 MiB.
  Keep each ceiling and its failure stage; do not replace them with one universal limit.
- Python parameter/edit JSON uses `json.loads`, while portable JSON uses strict ingress.
  Their duplicate-member, root-type, non-finite, integer and recursion behavior can differ.
  Check these differences with reference cases and the existing ingress owner.
  Do not silently tighten all surfaces or build another generic JSON parser.
- Experiment authoring uses a 64 KiB, single-document YAML profile with alias rejection, duplicate-key rejection, string keys and finite values.
  It performs no SDL shorthand normalization or import expansion.
  Keep invalid-date recovery (#1563) and the 32-detail error bound.
  Match an optional supplied task reference without fetching the task.
  Contract rules stay in `contract/admission`. This issue supplies the bounded authoring decode and results.
- Completion/navigation must work on incomplete documents.
  Reuse the declaration builder for entries that pass their own checks. Keep top-level names, as `raes/_language_context.py` does.
  A partial index grants no semantic admission.
  Preserve typed endpoint conjunctions, operating scopes, imported provenance and ambiguous-name refusals.
- The admitted `Document.ReferenceBindings` is insufficient for partial editor navigation.
  Extend the owning declaration view only as needed. Do not create a second symbol database in the application layer.
  Keep source ranges in the source owner's Unicode code-point convention, including imported locations.
- Editor pointers treat both empty text and `/` as root.
  The general JSON Pointer helper treats `/` as an empty member.
  Reuse token helpers. Keep the editor rule, canonical array indices, root-operation rules and fixed refusal reasons.
  Edits may return changed content with diagnostics. They must not forge admission or change caller/import buffers.
- Preserve formatter migration policy, field order, literal map keys and generated diagnostics.
  Canonical semantic JSON, formatted YAML and sorted Python-compatible JSON are distinct profiles.
  Do not use map iteration order, generic marshaling or `Error()` strings to derive behavior.
- Section validation sets its synthetic name after merging context and then installs the selected section.
  Preserve literal section keys, duplicate detection before reserialization and structural-only behavior when context is absent.
  Scaffolds keep literal brace substitution. Do not evaluate templates or execute authored content.
- The four inspection reference extractors identified in the issue are presentation projections, not the complete semantic reference graph.
  Reuse typed owner facts and simple field descriptors where useful. Keep covered edges and their order.
  Do not add graph edges that change results. Do not invent a generic reflection framework.

## Resources, extensibility and repository checks

The service selects resources through explicit read-only `fs.FS` access and fixed allowlists.
Keep `specs/agent-guidance/` and `examples/library/` as their existing authority surfaces.
Keep the reference Markdown, scenario examples, experiment examples and scaffold templates served by the Python tools.
The library catalog is not the same thing as the MCP example allowlists.
Reuse the packaged-corpus pattern for local assets where needed. Do not walk the host for `.git`.
Keep missing-resource operational failures. Preserve served content, audience filters and example IDs.
Use `tools/check_agent_guidance.py` and `tools/check_example_library.py` when those resource surfaces change.
No remote retrieval, new hosting or source transfer is authorized.

The useful seams are existing source context, operation/phase policy, explicit manifest input and a read-only resource filesystem.
Keep reference eligibility in its single owner. The next runtime family must serve both validation and the editor from there.
Keep parser caches immutable and import budgets local to each request.
Pass cancellation contexts through existing context-aware operations.
Do not add a service locator, workflow engine, plugin registry or global mutable session state.

The design must name packages, imports and exact exported identifiers in `implementations/architecture.json` before implementation.
Bind the owning design, consumer declarations and current `docs/develop/go-architecture.md` view under ADR-122.
Pass `archcheck -design` on that proposed model before coding.
A check of the unchanged model establishes the baseline. It does not approve the future service design.
Preserve `.ground-control.yaml`, `.gc/plan-rules.md`, ADR-121/122 and accepted ADR pins.
No requirement UID is attached to this issue; do not invent one to satisfy requirement-backed checks.

Use `internal/parity` coverage/inventory checks and the existing recorder. Never rewrite expected results to match Go output.
The live tool registry, not a copied count of 31, determines required tool coverage.
Each relevant security check, limit, refusal, recovery path and issue-named defect needs a native Go test.
The corpus can omit prose wording and cannot prove these internal properties alone.
Start the behavioral inventory from `test_language_service.py`, `test_mcp_server.py`, `test_semantic_cli.py`, and the #1339 editor tests.
Include #1543 argument privacy, #1563 date recovery, #1678 unexpected failures and relevant #1710 pointer/JSON cases.
Follow their imported helpers and recorded regression origins. This list is not exhaustive.
Use ADR-121 regression naming and its base-failure check for new regression cases where applicable.

Keep local verification targeted to changed paths or selected cases, including `docs-prose` for this note.
CI owns full corpus, standards, architecture, coverage, race, regression, fuzz and scheduled mutation checks.
Reuse `.github/workflows/canonical-verification.yml`, `implementations/.golangci.yml`, `implementations/.gremlins.yaml` and the locked toolchains/dependencies.
Do not add another gate or workflow to bypass these conventions.

## Non-goals

This preflight changes guidance only.
Implementation must not change Python, SDL semantics, published schemas, the corpus comparison policy, release ownership or the #1804 cutover.
It must not implement runtime execution, live conformance, transport registration, new authentication or backend/compiler/planner substitutes.
Public command composition stays with #1797's `command/authoring.Commands` contract.
It must preserve injected streams and exit statuses without calling `os.Exit` or importing runtime into `rae`.
No new ADR, exception hierarchy, persistence layer or cross-repository work is needed for these guardrails.
