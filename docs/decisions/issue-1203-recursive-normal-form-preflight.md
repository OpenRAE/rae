# Issue 1203: recursive normal form architecture preflight

Recorded 2026-09-06. Inspected revision: `ca26076c`.

This is requirement-free architecture guidance for GitHub issue #1203. The
issue, ADR-105, and the reviewed partial-description semantics are the governing
contract. This note does not implement the issue, select an implementation
sequence, change a schema, or claim that the acceptance cases pass. The native
#1201 blocker was cleared by merged PR #1215 before implementation began.

## Architecture decision

There must be one recursive semantic authority, owned at the neutral contract
boundary. Evolve `raes_contracts.realization_structure` together with
`raes_contracts.bounded_domains`; do not add a sibling constraint tree, a second
normalizer, or another evaluator. The #1200 `RealizationStructure` is the right
module and carrier seam, but its current value-free exact/open/record/keyed-list
shape is only a compatibility subset. It cannot yet represent presence, scalar
domains at arbitrary leaves, ordered sequences, closure universes, references,
or diagnostic-bearing resource exhaustion. `CapabilityConstraint`, aggregate
`ExplicitnessClass`, and `BackendRealizationEnvelope` are not substitutes:

- `CapabilityConstraint` is pre-instantiation allowed-value provenance with a
  hard-coded pointer allowlist. It may be adapted into the normal form during
  migration, but must not be extended with one package/repository leaf at a
  time.
- `ExplicitnessClass` and `semantic_explicitness_record()` remain summaries and
  provenance. Their weakest-child result must never replace the recursive
  authority.
- `BackendRealizationEnvelope` retains ADR-070's universal capability claim.
  Witness selection and delivery are separate relations owned by #1204.

The normal form is a closed, versioned discriminated tree. Each node preserves
independent axes rather than encoding them in one mode:

| Axis | Required normal-form distinctions |
| --- | --- |
| Presence | required, optional, forbidden; absence is not `null`, unknown, or empty |
| Value | exact typed value, existing bounded `DomainDescriptor`, or delegated value |
| Knowledge | known, unknown/unobserved, redacted, not applicable; this describes facts and never grants authority |
| Shape | scalar, record, stable-key collection, ordered sequence, or reference |
| Membership | required/optional members and cardinality, independently of whether additions are allowed |
| Closure | local open/closed/undefined posture plus a named semantic universe/profile revision |
| Origin | author/default/processor/backend/observation provenance using the existing lifecycle records |

Ordinary authored literals lower to required exact typed leaves; authors need
no wrapper on the common path. The non-ordinary states need an explicit,
discriminated long form. Do not overload Python `None`, empty containers, empty
strings, or the literal strings `unknown`/`other`. `DomainScalar` currently
omits JSON null, so null support needs an explicit domain meaning instead of
using field omission. Keep strict JSON type equality: `true` is not `1`.

An effective scope overlay must be retained as a tree, including declarations
at paths whose descendants are not materialized. The most-specific defined
scope wins; an undefined child does not shadow a concrete ancestor; two
definitions at the same qualified pointer are an error. An inherited open
scope applies to all otherwise-unspecified descendants. Explicit descendant
constraints are conjoined with that freedom and stay binding. Closure belongs
only to its record or collection; an exact child cannot close its parent or
siblings. Normalization must therefore walk authored presence and scope
declarations, not manufacture every optional model field or enumerate a
registry entry for every possible leaf.

Composition remains conjunction/intersection, with conflicts reported rather
than settled by import order. Reuse qualified namespaces, canonical RFC 6901
pointers, `model_fields_set`, `BindingOrigin`, explicitness/designation records,
and `_composition_provenance` rewriting. Defaults stay preferences with their
origin and must not become exact authored facts. The canonical normal form is
the semantic authority; any legacy plan or provenance projection is derived
from it, versioned, lossless for its advertised subset, and rejected if it
disagrees with the accompanying payload. Exact values must not acquire a second
independently editable source of truth.

## Collections, references, and finite evaluation

Set-like collections use the existing qualified identity discipline from
ADR-076: module namespace, owning collection kind/profile, and local semantic
identity. `collection_identity_fields` is reusable metadata, but it belongs to
the owning typed core model or selected extension profile, not to a manual
leaf-concern registry. A canonical digest may index an identity; it is not the
identity's meaning or a refinement proof.

Required members and exhaustive inventory are separate. A required keyed
member must match exactly one actual member; an optional keyed member may be
absent, but if present must match its child constraint. Open membership permits
additional members only inside the collection's named universe. Closed
membership requires no additional modeled members in that universe. Neither
mode claims completeness for OS dependencies, files, backend-internal
acquisition choices, or observations outside that universe. Duplicate authored
or observed identities, alias collisions, missing identities, and multiple
matches are invalid/ambiguous outcomes; never use first-match or fuzzy matching.

Ordered sequences are a distinct node kind. Position is meaningful there and
duplicates are allowed only as the owning type permits. A list index must not
be reused as stable identity for a set-like collection. Reordering a package
inventory must not retarget `/packages/0/repository` after normalization.

Keep schema/constraint-definition references acyclic. Model graph references
as identity edges rather than recursively expanding them. Missing references
fail semantic admission; graph cycles are valid only for an owning domain that
explicitly permits them. They must not be confused with existing execution
dependency cycles, which retain their current diagnostics and owners.

The extension and resource-control seam is explicit: the normal-form profile
identity/revision supplies collection kind, identity selector, ordering,
aliases, reference policy, and closure universe; every normalize, compose,
match, and refinement call receives an explicit `limits` budget. Core and
selected extension data use the same seam. Profile resolution is pinned and
offline at this layer; no global concern registry, remote `$ref`, dynamic code,
or backend callback participates in the relation.

Reuse `SDLParserLimits` for source bytes, YAML depth/nodes/aliases, imports and
composition. Direct JSON/model construction also needs the neutral semantic
budget: bound recursive depth, total nodes/operations, collection members,
identity/alias work, reference hops, scalar/string/integer size, and emitted
diagnostics. A budget result is `limit-exceeded`/unsupported with a bounded
`Diagnostic`, never `True`, `False`, empty-domain, or successful conformance.
The current `structure_matches()` behavior of returning `False` after depth 64
is therefore not an acceptable issue-1203 boundary.

## Canonical incumbents and cross-cutting obligations

Paths in this table are under `implementations/python/packages/` unless shown
otherwise. These are the existing owners the implementation must reuse.

| Layer | Canonical incumbents | Required treatment |
| --- | --- | --- |
| Module/authority boundary | `raes_contracts.realization_structure`, `bounded_domains`, ADR-036, `tools/policy/adr_policy.yaml` | Keep neutral DTOs and pure relations in `raes_contracts`; authoring lowering in `raes`; compiler use in `raes_processor`. Do not deepen the legacy `raes_contracts -> raes` import cycle or let CLI, MCP, runtime, or a backend become the semantic owner. |
| Source parsing and shape validation | `raes._base.SDLModel`, `_yaml_loader`, `_source_validation`, `_mapping_key_analyzer`, `_source_profile.SDLParserLimits`, `SemanticValidator` | Preserve safe YAML, duplicate/key/source-location diagnostics, `extra="forbid"`, typed core keys, and selected extension validation. Syntax closure detects unknown syntax; it does not close a runtime inventory. Direct constructors must receive equivalent semantic bounds. |
| Composition, instantiation, and provenance | `composition._expand`, `_composition_budget`, `_composition_provenance`, `_references`, `instantiate`, `phase_contracts`, `explicitness`, `realization_designation` | Reuse the single expansion coordinator, namespace/symbol map, exact reference resolution, aggregate composition budget, concrete revalidation, `model_fields_set`, binding origin, and designation source. Preserve absent/default/authored/derived distinctions through round-trip; no second pointer rewriter or provenance ledger. |
| Domain and relation validation | `bounded_domains.scalar_in_domain`, `realization_structure.structure_matches`, `realization_envelope.subsumes`, `raes.canonical`, `raes_contracts.canonical` | Reuse domain-owned equality/version/unit rules and JCS helpers. Extend one recursive relation surface to return structured outcomes. Do not enumerate Cartesian products, use Python truthiness/equality, or treat digest equality as semantic refinement. Universal subsumption is unchanged. |
| Compiler and plan carriage | `compiler.realization_requirements`, `compiler.realization_structure`, `realization_concern_explicitness`, `planning.ResolvedRealizationAuthority`, `contracts.realization_plans` | Lower once from the authoritative normal form. Keep current concern descriptors only as owners of top-level runtime projection and legacy adapters, not as a leaf taxonomy. Any plan carrier must preserve recursive authority through closed DTO serialization and reject unsupported/lossy cases before mutation. Runtime selection/enforcement remains #1204. |
| Configuration, secrets, and trust | `runtime_environment`, `runtime_values.enforce_observed_value_redaction`, `raes_contracts.secret_references`, generated-artifact validators, `uri_safety`, `module_registry`, ADR-056/057/071 | Keep literal/reference exclusivity, environment-name uniqueness, producer entitlement, credential-free identities, path confinement, integrity and size checks. Constraint/profile parsing performs no secret lookup, network fetch, import installation, or executable validation. Unknown/open extensions cannot bypass configuration authority or redaction. |
| API and authorization | `RuntimeControlPlane`, `ControlPlaneSecurityConfig`, `control_plane_api._auth`, `control_plane_api_guards.RequestSizeLimitMiddleware`, operation DTOs | Issue #1203 adds no endpoint or authorization surface. If the normal form later crosses the control plane, retain request limits, constant-time bearer matching, role/target/participant checks, trusted planner identity/digest, idempotency, bounded denial audits, and closed DTO conversion. Description/report depth never grants data access. |
| Errors, logging, and operational observability | `raes._errors`, `_model_diagnostics`, `raes_contracts.diagnostics.Diagnostic`, operation receipts/status, API redacted handlers | Source/model/instantiation failures use the existing error classes; portable semantic results use bounded `Diagnostic`. Distinguish invalid shape, conflict, ambiguous identity, missing/cyclic reference, unsupported semantics, nonconformance, and limit exhaustion. Messages and logs must be value-free: no raw Pydantic input, profile payload, path outside the portable pointer, secret, backend exception, or traceback in a public envelope. No new exception hierarchy or logging channel. |
| Persistence | `ControlPlaneStore`, `LocalControlPlaneStore`, `control_plane_store_payloads`, records/snapshots/compatibility codecs | Issue #1203 needs no new store. If a carrier is persisted by an existing plan/snapshot path, validate the closed contract on write and reload, preserve current atomic/durable operation semantics and sanitization, and fail on unknown incompatible revisions. Do not add a constraint ledger or inventory database. |
| Backend, host, and OS exposure | `raes_backend_protocols`, reference/libvirt driver boundaries, process resource-limit policy | The normalizer and pure relations perform no subprocess, filesystem mutation, network access, shell interpolation, or environment export. They expose no native path/ID or secret through argv/logs. Backend translation, privileges, package installation, timeouts and output limits remain later admission/execution concerns; author openness never authorizes them. |
| Observation, evidence, retention, and export | `realization_concern_observations`, `realization_snapshot_sanitization`, `RuntimeSnapshot`, evidence/capture contracts, ADR-064/066 | Preserve actual knowledge, coverage, time and claim basis separately from author constraints. Do not infer observation demand, exhaustive capture, retention, export, or conformance from model detail or collection closure. #1212 and #1209 retain those responsibilities. |
| Published contracts and workflow | `contracts/schemas`, `contracts/fixtures`, `contracts/schema-publication/entries`, `schema-publication-manifest.json`, `raes_contracts.contracts.bundle.schema_bundle`, ADR-009/061/075, `.ground-control.yaml`, `.gc/plan-rules.md` | A changed public shape or meaning needs an explicit contract/semantic revision, authoritative schema, valid/invalid fixtures, publication metadata/hash, and generator parity; old readers must not silently ignore authority. Use repo-policy, requirement-governance and canonical verification. This issue is requirement-free: use the supported skip-requirement path and do not invent a UID. Leave release-owned version/changelog files alone. |

## Acceptance and review guardrails

The design oracle in `test_issue_1201_partial_description.py` and lifecycle
examples in `test_issue_1201_description_lifecycle.py` define useful algebraic
anchors; they are not production integration evidence. Reuse the #1200 mixed
runtime tests, SEM-218 explicitness/designation tests, phase-contract tests,
canonicalization tests, composition/reference tests, parser-limit tests,
schema fixtures/parity checks, and diagnostic-boundary tests.

Review evidence must cover positive and negative pairs for:

- inherited open parent, exact and closed children, undefined descendants, and
  sibling preservation at more than one depth, including selected extension
  data without a new concern descriptor per leaf;
- omitted optional package, conforming present package, wrong present package,
  required member, permitted additional member, forbidden additional member,
  empty inventory, unknown inventory, reordered set, duplicate/ambiguous
  identity, and a genuinely ordered duplicate-bearing sequence;
- absent versus JSON null versus empty string/record/list versus unknown or
  redacted fact, plus author/default/processor/backend origin after parse,
  composition, instantiation and contract round-trip;
- missing reference, forbidden schema cycle, permitted graph cycle, excessive
  reference hops, excessive nesting/member/payload/work limits, and bounded
  diagnostics with no false conformance result;
- the five Linux boxes and Kali refinement ladder under one inherited open
  scope, with exact children preserved and no claim over incidental OS
  dependencies/files; and
- the complete abstract two-computer/three-action model remaining executable
  at its declared level, with no synthesized concrete machine or observation
  obligation.

Conjunction should be checked for commutativity, associativity and idempotence;
refinement for transitivity; normalization and serialization for semantic
round-trip. Conflicts must be deterministic and type-sensitive. One supported
witness must not be reported as universal backend support, and an inconsistent
empty request must not pass by vacuous subsumption.

## Gotchas, rejected shortcuts, and boundaries

Do not solve this issue by broadening `_is_ordinary_constraint_pointer`, adding
package leaf concerns, taking the weakest explicitness as authority, making all
fields optional, changing enums to strings, accepting arbitrary dictionaries,
or treating `extra="forbid"` as whole-machine closure. Do not use list position,
canonical sort order, or hash alone as semantic identity. Do not silently turn
limits or ambiguity into mismatch, unsupported into open, observation unknown
into backend discretion, or a backend-selected/default value into author intent.

Do not auto-expand graph references, auto-fetch schemas, run profile-supplied
code, add a solver/service/registry, or normalize an abstract model by filling
an irrelevant machine subtree. Avoid wrappers around every scalar, side-table
constraint bags, parallel validation engines, per-backend SDL interpretation,
unbounded recursion/matching/diagnostics, and silent changes to an existing v1
contract's meaning.

This issue owns the shared normal form, recursive composition/validation,
collection/reference semantics, provenance-preserving round-trip, and bounded
relation outcomes. It does not own extension distribution/trust (#1202),
backend witness selection and end-to-end enforcement (#1204), software model
migration (#1205), realization reporting/capture lifecycle (#1209), full
compatibility migration (#1210), integrated conformance (#1211), or observation
demand/retention/export (#1212). It adds no backend recipe, compulsory catalog,
new persistence service, experimental evidence requirement, or concrete-machine
requirement for a complete abstract model.
