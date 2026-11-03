# Go architecture contract preflight

[Issue #1859](https://github.com/OpenRAE/rae/issues/1859) defines this work.
This note guides the design. It does not claim that checks already exist.
[ADR-122](adrs/adr-122-go-architecture-model.md) remains the decision owner.

## Current state

The model owns modules, layers, package owners and imports.
Seven product primitive packages exist. The parity harness and tools also exist.
The other product layers are planned. Python is their behavior reference.
The current checker has no typed API snapshots or pre-code package-cycle check.

Keep these boundaries separate:

- Exported Go names.
- Visibility between internal layers.
- Import access from a downstream Go module.
- Authority to invoke a product operation.

## API and dependency guardrails

Extend `arch`. Do not add a second framework.
Use package directories as owner keys. Use module paths as Go identities.
Every package needs an intended API and an owning design, including private-to-layer packages.
Use standard Go type data or declarations. Do not create a signature language.
Cover functions, receiver method sets, aliases, fields, tags and embedded members.
Cover promoted API, interfaces, type constraints, variables and exact constants.
Include private types reached through the API. Exclude unrelated private code changes.
Keep one intended interface list, not two editable copies.

The design must commit to the exact API. A link or file touch is insufficient.
A source-only API change must fail. A snapshot-only change must also fail.
Generation prints a candidate. It must not approve an interface change.
Snapshots prove structure, not semantics, human approval or design timing.

The pre-code check must work before product files exist.
Version the new model shape. Update strict loading and fixtures together.
API extraction must cover explicit platform and tag contexts.
Reject unknown or uncovered contexts. Do not merge exclusive platform types.
Keep tests out of the product API. Preserve test import checks.
Use Go's parser and type checker. Keep dependency loading offline and read-only.
Do not run proposed code, generators, or commands from metadata.

Reject cycles in the declared package graph, including same-layer and disconnected cycles.
Keep the layer graph check separate. Report a stable cycle path and fix.
Validate node identities and references. Keep findings in a stable order.
The compiler remains an independent check of actual cycles and internal access.

## Consumer API ownership

[Issue #1825](https://github.com/OpenRAE/rae/issues/1825) owns consumer package locations and API policy.
Until that design lands, show its boundary as planned.
Do not invent a facade or move internals here.
Show environment packs, LilRAE and Coldlight outside the Go module boundary.
Future public APIs need usable public types and downstream compile tests.
Do not strand callers on inaccessible internal types.
The checker must not need a switch for each new consumer package.

## Current system views

Keep one current overview. Link it from `docs/README.md` and owning designs.
The old checker diagram remains tooling evidence.
Show actual package edges separately from allowed layer edges.
State which code exists and which layers remain planned.
Show embedders, transports, shared services, admission, processor, runtime and store.
Show injected backend and provider boundaries.
Include untrusted input, validated values, actor-bound operations and backend effects.
Keep authoritative state, evidence, audit and value-free logs distinct.
Keep native credentials and resource life cycles outside RAES under ADR-115.
P0/P1/P2 reference behavior is not Go delivery. P3 remains a nonclaim.

Derive mechanical views from the model. Compare output without overwriting reviewed files.
Bind authored views to stable model components and local evidence by content.
Check missing sources, new components, stale status and changed edges.
A timestamp, valid link or model hash alone does not prove view freshness.
Review still checks whether the security explanation is true.
Use the existing go-architecture CI gate, including for documentation changes.
No hosted renderer or external upload is needed.

## Reuse and security checks

Use the existing loader, findings, graph traversal and command.
Use the admitted standard libraries and x/tools facilities.
Keep new code in the tooling module. Do not import product internals from it.
Bound parsing. Reject unknown fields, duplicate keys, bad paths and excessive depth.
Use rooted file access. Lexical paths and `os.DirFS` alone do not contain symlinks.
Read failures are errors. Policy violations are findings with a fix.

Reuse these product owners as slices land:

| Concern | Owner and rule |
| --- | --- |
| Ingress | `base/ingress.Parse`; bounded parsing precedes schema and semantic admission |
| Primitives | `base/canonjson`, `digest`, `randstream`, `jsonpointer`, `address`, and `urisafety` |
| Contracts | Published schemas and concept authority under ADR-009; no parallel wire envelopes |
| Access | ADR-104 core actor, scope and target checks; one transport authority per route |
| Secrets | Logical references and value redaction; secret files stay off limits |
| Errors | ADR-116; fixed refusals, value-free logs, and no new error hierarchy |
| State | ADR-104 store, lease, CAS and atomic terminal commit rules |
| Distribution | ADR-113 composition; no second operation runtime in an adapter or embedder |

Preserve the security settings shape checks and frozen principal maps.
A bad bearer credential must not fall back to proxy headers.
P2 admin admission grants no participant or controller authority.
Do not pass secret values in argv, URLs, snapshots or child output.
Keep logs separate from audit and evidence under ADR-066.

Preserve compatibility reasons in the #1779 primitive designs.
Do not replace JCS with sorted Python JSON or change random-stream profiles.
Keep URI and ingress error precedence and documented Unicode differences.
The #1778 parity harness owns behavioral evidence. API snapshots do not replace it.

## Repository checks

Keep the existing toolchain locks, lint settings, mutation setup and CI graph.
Do not add a second workflow. Keep `GOTOOLCHAIN=local` and read-only module flags in CI.
No runtime schema or release/version changes are needed.
An ADR-122 edit needs an amendment and a matching ADR index pin.
Update the rule registry and its fixtures with the rule table.
Use MOD-001 and maintain code/test trace links.

Tests must reject changed exports, signatures, fields, constants and missing designs.
Test snapshot updates without matching design commitments.
Test private-only stability, tagged exports, cycles, stale evidence and escaping references.
Assert command failures include a rule, location and fix.
Use targeted tests and file-local policy checks locally.
CI owns full, race, fuzz and full mutation suites.
Keep all discovered real failures as repair obligations.

## Non-goals

Do not port product code or design #1825's API here.
Do not add services, plugins, runtime migrations, generic validators or graph frameworks.
Do not make every package public. Do not bypass core policy in an adapter.
Do not change published schema authority or treat compile success as API approval.
