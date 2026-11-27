# Issue 1710: Shared primitives architecture preflight

Date: 2026-10-31

Contract: the supplied issue #1710; no Ground Control requirement. Scope is
every package under `implementations/python/packages/`. This is design guidance,
not an implementation plan. Inspection used checkout `e74eb280f`; the issue's
counts describe an older revision. ADR-117 and its structural tooling are present;
the issue's prerequisite that chunk 00 (#1734) be complete still applies.

## Ownership and reuse

Use small public functions in the incumbent neutral package, `raes_contracts`.
Keep domain projections, admission decisions and boundary error translations in
their current owners. One implementation per behavior does not mean one behavior
for superficially similar operations. Keep existing public interfaces where
callers depend on them; a delegating domain adapter is acceptable, a second
algorithm is not.

| Primitive | Owner and boundary |
| --- | --- |
| JSON Pointer tokens | Extend `raes_contracts.json_pointer`, introduced by #1678. It currently owns `array_index` and `is_array_index_token`, not escaping. Add public token operations there; retain domain-specific traversal and failure contracts. |
| JCS bytes and digests | Retain `raes_contracts.canonical.canonical_json_bytes` and `canonical_json_digest`, backed by `_canonical` and the locked `rfc8785` 0.1.4. `raes.canonical` still owns validated SDL projections and their profile-labelled identities. |
| Existing JSON text profiles | A cohesive public `raes_contracts.json_serialization` module should own the extracted, explicitly named encoder variants. These are distinct from JCS. Group by actual encoder behavior, not by caller or a new profile registry. |
| SHA-256 | A public, standard-library-only `raes_contracts.digests` module should own byte hashing and raw-byte, hexadecimal and `sha256:` renderings as needed by current consumers. Serialization, domain prefixes and commitment framing remain explicit. |
| Graph mechanics | A public `raes_contracts.graphs` module should own extracted ordering/cycle variants. Build on `graphlib` where equivalent; retain one shared custom implementation where exact ordering or all strongly connected components require it. |
| Operational timestamps | A public, standard-library-only `raes_contracts.timestamps` module should own extracted parsing variants and UTC wall-clock reading/formatting. Semantic clocks remain with the existing time-model owners. |

These modules must not import SDL, processor, runtime, backend implementations,
the aggregate `raes_contracts.contracts` facade, or application configuration.
Keep `raes_contracts.__init__` inert. In particular, timestamp parsing must not
import `contracts.base` when that model layer consumes it. Byte hashing must not
import canonicalization or immutable history. Preserve `_canonical`'s deferred
history conversion in `jsonable_fallback`; an eager history import would create
a cycle through `immutable_history`'s existing canonical import.

ADR-036's package permissions and ADR-117's actual import graph both apply.
`tools/policy/adr_policy.yaml` permits some legacy reverse imports, but
`tools/policy/import_contracts.toml` ratchets them as debt. They are not precedents
for new reverse dependencies. Import shared public names directly; do not create
private aliases/facades or function-local/dynamic imports to conceal cycles.
Drain exact removed debt from the existing structural baseline/import ignores;
never regenerate a larger baseline or trade removed debt for a new identity.
ADR-015's 1,000-line cap is a backstop, not a reason to split cohesive code.

## Compatibility guardrails

**Pointers.** Escape `~` before `/`; unescape `~1` before `~0` so `~01` stays
`~1`. Keep token conversion separate from whole-pointer syntax validation,
URI-fragment decoding, dotted addresses and domain resolution. Preserve `""`
versus `"/"`, empty tokens, Unicode and existing malformed-token behavior.
Do not add strict rejection or percent decoding to a previously permissive
replacement operation. Preserve mapping keys such as `"01"` while retaining
canonical ASCII array indices, leading-zero rejection, bounds and digit-limit
guards. Missing/scalar/index failures currently differ between walkers; do not
replace their `None`, sentinel, boolean or exception contracts with one resolver.
Reuse `DiagnosticModel` and the existing `JsonPointerString`/instance-path types;
their distinct address grammars must not be merged or broadened.

**Serialization.** Compare exact encoded bytes, not decoded JSON equality.
Preserve sorting, separators (including noncompact comparison keys),
`ensure_ascii`, `allow_nan`, fallback callbacks, encoding and return type.
Current compact variants include ordinary ASCII JSON, `default=str` history
heads, finite-only immutable history, Unicode audit text, and Unicode finite-only
observation text. `participant_resource_types` also has unsorted compact JSON.
Keep each used combination visible in its name; avoid a bag of flags at every
call site. A domain-specific conversion callback may be passed explicitly,
without importing its model into the serializer. Preserve `model_dump` options,
projection exclusions and the order of validation and conversion.

JCS changes Unicode/key ordering, numeric rendering and accepted values; it
cannot replace sorted `json.dumps` merely because both are deterministic.
`jsonable_fallback`'s stable carrier marker is not equivalent to `default=str`.
Keep NaN/infinity, large integers, negative zero, surrogates and unsupported
carriers on their current acceptance/error paths. Do not silently harden a
legacy encoder or add coercion. CLI/MCP pretty output, lockfile text and schema
factoring/comparison keys also have observable formatting; account for them
without routing every ordinary JSON output through a new canonicalizer.

**Digests and durable identity.** Distinguish exact source bytes, JCS bytes,
legacy JSON bytes, raw digests, hex text, prefixed digests, URNs and truncated
name suffixes. Preserve algorithm, framing, encoding and case. Examples beyond
simple JSON hashes are `immutable_history`'s previous-digest bytes plus record,
`participant_tool_actions` identities, `raes_backend_protocols.naming` suffixes,
run-archive checksums, and the binary-derived PostgreSQL `_OWNER_LOCK` constant.
Never hash a hex string where the incumbent hashes digest bytes, or reserialize
stored text before checking its integrity. No digest/profile/version migration
is authorized. If equivalence cannot be established, retain the code and raise
the question to the maintainer, recording the issue finding's disposition.

**Graphs.** The validator's `_topological_sort` traverses successors;
`TopologicalSorter` takes predecessors. The planner normalizes to known nodes,
uses `canonical_resource_identity`, a FIFO ready queue with sorted initial
nodes/dependents, and appends sorted residual nodes on cycles. Preserve these
rules, duplicate-edge handling, input insertion order, return container types,
self-loops, isolated/unknown nodes and failure timing. A heap that globally
sorts ready nodes is a behavior change. Keep planner address validation,
ordering-versus-refresh edges and reconciliation/delete policy in
`raes_processor.semantics.planner`; pass ordering keys to generic mechanics.

The planner's Tarjan traversal is already iterative to survive long chains;
retain that property and its member/component ordering. `graphlib.CycleError`
reports one cycle, not all cyclic strongly connected components. Existing
direct `graphlib` consumers already share the standard-library implementation;
do not add a wrapper just to eliminate the import. Preserve their graph
construction and insertion order. Translate cycle failures only at the existing
validator/domain boundary, preserving messages and aggregated validation.

**Timestamps.** Preserve these four distinct parser behaviors rather than
substituting a Pydantic datetime field or universal normalizer:

| Incumbent | Behavior that must survive extraction |
| --- | --- |
| `contracts.base._parse_rfc3339_datetime` | Governed RFC 3339 grammar, lowercase `t`/`z`, explicit offsets, existing leap-second date table and rollover; field-specific errors and original offset. |
| `control_plane_workflows.parse_timestamp` | Explicit-offset ISO input normalized to UTC; fixed value-free error and guarded conversion overflow. |
| `runtime_fact_dispatch._parse_datetime`, exposed by `runtime_fact_binding_policy.parse_datetime` | Offset required; lowercase `z` accepted; original offset retained; field-labelled, value-free refusals. |
| `raes_runtime.diagnostics._parse_timestamp` | Naive/date-only values interpreted as UTC; offset retained otherwise; underlying parser errors preserved. This permissive behavior must not reach freshness/admission checks. |

Keep `Rfc3339DateTimeString`'s published pattern/format and semantic leap-second
validation: satisfying a string shape does not prove the instant is valid.
Do not change model fields from strings to datetime objects during extraction.

Also account for direct parser calls in `operation_control_budget` and
`runtime_trial_unit`. The control budget deliberately refuses lowercase `z`
and leap seconds that its wire contract admits; widening support changes
behavior. Preserve deadline inequalities, precision, rounding, capacity limits
and rejection before dispatch. Host time formatting includes `Z`, `+00:00`,
automatic fractional precision and quarantine filename `strftime` forms; keep
each representation and the number/placement of reads. Preserve one captured
instant where multiple fields currently share it.

The extensibility seam is a public callable returning an aware UTC `datetime`,
supplied through existing trusted constructor/application boundaries and passed
to consumers; formatting should also accept an explicit instant. Reuse existing
`now`/`reconciliation_clock` arguments. Resolve the default read at invocation,
not import time; a test must control actual runtime/backend paths through the
public seam. Avoid global clock setters or patches of private imported aliases.
If a constructor option is needed, keep `ControlPlaneOptions`,
`ControlPlaneConfiguration` and constructor forwarding consistent; it is a
trusted Python dependency, not an SDL, environment or HTTP setting.
Keep monotonic watchdogs, Temporal `workflow.now()`/replay behavior and ADR-090's
exact semantic clocks separate. This refactor cannot switch time authorities.

## Cross-cutting layers the extraction must pass

Package paths below are relative to `implementations/python/packages/`;
filenames grouped under a package belong to that package.

| Layer and canonical incumbents | Required invariant |
| --- | --- |
| Ingress and shape: `raes/`: `parser.py`, `_yaml_loader.py`, `_source_profile.py`; `raes_contracts/`: `json_ingress.py`, `admitted_trial_plan_ingress.py`, `_domain_profile_validation.py`, `_base.py`, `contracts/base.py` | Keep safe YAML, duplicate/nonfinite JSON refusal, byte/depth limits, closed models, readmission and domain-profile limits. Serialization is not admission; hashing does not certify a model. Do not add parallel data models, schemas or validators. |
| Auth and policy: `raes_runtime/`: `control_plane_security.py`, `control_plane_api/_auth.py`, `control_plane_api_guards.py`; runtime-fact freshness/visibility and participant crossing/state-cut owners | Keep immutable principal/config shapes, route composition seals, role/target/actor/audience checks, admission before body validation, request/concurrency limits and authority-bound no-store responses. Reusing a pointer/hash/parser must not bypass or relocate these gates. |
| Secrets and bindings: `raes/runtime_values.py::enforce_observed_value_redaction`, `runtime_environment.py`; `raes_contracts/secret_references.py`, `experiment_bindings.py`; `raes_processor/trial_compiler/bindings.py` | Preserve literal/`value_from` exclusion, secret-reference grammar, operator-secret restrictions, raw-value omission and protected-sink visibility. Shared functions neither resolve secrets nor log payloads. Hashing is not redaction or authorization. |
| Errors and output: `raes_contracts.errors`, `raes_contracts.operational_logging`, `raes_contracts.diagnostics`; `raes/_model_diagnostics.py`, `raes_runtime/control_plane_api/_responses.py`, API model/exception handlers, CLI entrypoint and MCP result boundaries; ADR-116 and `docs/develop/exceptions-and-logging.md` | Keep existing exception identity/category, messages, causes/suppression, diagnostic pointers/ranges and bounded envelopes. Value validators retain `ValueError`/Pydantic aggregation; boundary owners retain domain translation. No primitive-specific hierarchy, new logging, raw exception/payload output or changed CLI/MCP stdout. |
| Persistence and evidence: `raes_runtime/`: `control_plane_store_local_codec.py`, local/PostgreSQL stores, `control_plane_store_history.py`, `participant_crossing_state_cut.py`; `raes_contracts/immutable_history.py`, `raes_operations/run_artifacts.py` | Keep exact committed bytes, digest formats, append-only heads, the 128-level durable nesting bound, revision/idempotency checks, transactions/rollback, atomic publication and audit semantics. Preserve observation text's 16,384-byte limit. No rewrite of old rows, caches, manifests or evidence. |
| OS, filesystem and workers: `raes/module_registry/_cache_integrity.py`, `_verified_sources.py`, `_archive.py`; store ownership/scope modules; Temporal workflow/activity owners | Keep bounded streaming, no-follow descriptors, regular-file/identity/mode checks and archive/source limits. Share hash mechanics without replacing secure open/read loops with `Path.read_bytes()` or unbounded `file_digest`. Keep subprocess argument lists, credential delivery, file permissions and process locks. No tokens in argv/logs, new I/O, sinks, external services or workflow retries. |

Further extension belongs in narrow parameters already justified by these
behaviors: a graph ordering key, an explicit serialization conversion callback,
and the trusted clock callable. Domain naming/framing and error labels stay with
their owners. Do not invent an algorithm registry, generic service/repository,
base-class hierarchy, middleware chain, universal resolver or timestamp schema.

## Verification boundaries and non-goals

Reuse the existing public-behavior tests, particularly `test_semantics_planner`,
`test_sdl_canonicalization`, `test_issue_1678_cycle2_pointers`,
`test_issue_1373_history_prefixes`, `test_runtime_workflow_timeout_reconciliation`,
`test_issue_1541_runtime_fact_timestamp_offsets`, module-registry/archive tests,
API trust-boundary tests and ADR-116 failure-boundary tests. Preserve existing
assertions and fixtures; the issue allows changes to existing tests only to
replace imports/patches of removed private names with public interfaces.
Supplement with fixed byte/digest vectors and exact-order/error/offset cases
where existing coverage is missing. Helper-to-helper equality alone cannot
prove compatibility; exercise persisted records and actual public consumers.
Keep long-chain and hostile-pointer coverage, and test independent clock
instances without real sleeps or private patches.
Account for current call sites and aliased imports, including newer participant
execution/tool-action clock helpers, rather than stopping at the issue's counts.

Repository-wide inspection includes the ten packaged roots and the canonical
build/policy/runtime consumers: `implementations/python/pyproject.toml`, its
lockfile/build hook, `contracts/schemas/` and publication manifest,
`tools/check_generated_schemas.py`, `tools/policy/adr_policy.yaml`,
`import_contracts.toml`, `structural_baseline.json`, `.ground-control.yaml`,
`.gc/plan-rules.md`, `noxfile.py`, `tools/nox_support/`, hooks and
`.github/workflows/`. Use their existing gates; no replacement workflow.
Published schemas remain authoritative and generated bundles must still match;
do not republish schemas or edit the publication ledger to bless output drift.
Preserve installed-wheel imports and the Python 3.12 bootstrap import closure
of `raes_contracts.__init__`, `errors` and `operational_logging`; application
code targets Python 3.14. Local verification is targeted only; full, integration,
fuzz, completion and repository-wide policy suites belong in CI. This run has
no requirement UID; do not fabricate one or weaken governance to bypass it.

Non-goals: issue implementation in this preflight; changes to `tools/` or
`implementations/formal/` primitive call sites (chunk 21); new dependencies,
external processing, schema/SDL/API changes, security hardening that changes
admission, digest migrations, graph-policy changes, timestamp normalization of
stored values, workflow/state-machine consolidation or broad test rewrites.
The existing ADRs cover these boundaries; no accepted ADR amendment is needed.

Source basis: [RFC 6901 sections 3–6](https://www.rfc-editor.org/rfc/rfc6901)
defines token decoding and distinct pointer representations;
[RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) and the
[incumbent implementation](https://github.com/trailofbits/rfc8785.py) define JCS;
Python 3.14's [JSON encoder](https://docs.python.org/3.14/library/json.html),
[graphlib](https://docs.python.org/3.14/library/graphlib.html) and
[datetime](https://docs.python.org/3.14/library/datetime.html) document encoder
options, insertion-sensitive ordering/one-cycle reporting and datetime behavior.
These support the design distinctions, not a claim of verified refactor parity.
