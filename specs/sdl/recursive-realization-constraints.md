# Recursive realization constraint normal form

Status: **normative contract boundary**. The authoritative portable schema is
[`recursive-realization-constraint-v1.json`](../../contracts/schemas/realization-constraints/recursive-realization-constraint-v1.json).
ADR-105 supplies the reviewed semantic design. The contract has draft
stability while later migration issues adopt it at parser, compiler, planner,
backend and observation boundaries. Issue #1204 adopts this contract at the
existing compiler, authenticated plan and runtime result boundaries; see
[backend preparation](backend-realization-preparation.md) and
[plan-level profiles](plan-realization-profiles.md). Public SDL profile
attachment syntax is not part of that adoption.

## 1. Purpose and authority

`recursive-realization-constraint-v1` represents what a description constrains
without turning omitted implementation detail into an author obligation. It is
one closed, discriminated tree shared by core and selected extension data.
Implementations MUST NOT replace it with aggregate explicitness, a list of
registered leaf concerns, an installation recipe, an observation inventory, or
an ADR-070 capability envelope.

Ordinary JSON literals normalize directly: a scalar becomes an exact typed
`literal`, a mapping becomes a `recursive-record`, and an ordinary list becomes
an ordered `sequence`. Explicit nodes are required only for a bounded domain,
delegated value, non-known knowledge state, conditional presence, keyed
collection, definition or graph reference, or non-default closure. JSON `null`,
empty strings, empty records and empty sequences remain exact values. Omission
is not `null`; unknown is not delegation.

Each recursive node carries presence and origin independently:

- `required` MUST be present and conform;
- `optional` MAY be absent but MUST conform when present;
- `forbidden` MUST be absent;
- `author`, `default`, `processor`, `backend`, and `observation` identify why
  the value or rule exists and do not change its authority by themselves.

The `knowledge` node records `unknown`, `redacted`, or `not-applicable` without
a raw value. Evaluation returns `unresolved`; it never treats those states as
permission or a conformance claim. `delegated` is the explicit permission for a
backend-owned value and is separate from evidence or reporting.

## 2. Records, scopes and closure

A record names recursive field constraints. Closure is local to that record and
has three postures: `open`, `closed`, or `undefined`. Every concrete posture
MUST name both its semantic universe and profile revision. Closed means no
additional members in that named universe; it never means no other file,
dependency, backend-internal setting, or observation exists anywhere.

Undefined makes no local statement. The most-specific concrete lexical scope
applies; otherwise the document default applies. Equal-pointer scope duplicates
are invalid. An inherited open scope covers unspecified descendants without
materializing one waiver per field. Explicit descendants are still evaluated,
and a locally closed child remains closed without closing its parent or sibling.
Scope overlays are evaluated even when their path crosses an additional member
or delegated subtree that has no materialized constraint node. A descendant
scope supplies structural meaning to its addressed member; if a collection
address cannot be interpreted with the available keyed or sequence shape, the
result is `unsupported`, not silent acceptance. An unselected effective closure
also returns `unsupported`, not conformance.

## 3. Collections and identities

`keyed-collection` is set-like. Its identity is the declared tuple of concrete
identity fields under the named collection kind/profile. Each constraint member
retains that tuple; a canonical digest may index it in an address but is not the
identity's meaning. Input order does not affect matching.

A required identity must match exactly once. An optional identity may be absent
and must conform when present. A forbidden identity must not match. Missing,
non-scalar, duplicate, or ambiguous identities are invalid. Collection
cardinality and the presence of declared members are independent. Open closure
permits additional modeled members in the collection's universe; closed closure
does not. Neither posture claims completeness for incidental OS dependencies or
files outside that universe.

Identity aliases are explicit collision-free mappings to a declared canonical
identity. An alias and its canonical spelling in one observed collection are an
ambiguous duplicate and fail validation; first-match and fuzzy matching are
never used. Alias resolution is charged to the same bounded identity-work
budget as ordinary matching.

Normalization may accept a positional pointer from the current authored list
surface, but it MUST immediately rewrite that position to the selected member's
semantic-identity address. Subsequent reordering cannot retarget the scope.
Profile metadata is passed explicitly per collection boundary; adding extension
data does not add a leaf concern to a global registry.

`sequence` is ordered. Position is meaningful, duplicates remain distinct, and
closed sequence closure rejects additional occurrences. A sequence index is not
a set-member identity.

## 4. Domains, references and composition

`domain` reuses the bounded-domain algebra. The recursive revision adds an
explicit `null` domain without changing older contracts that reference the
non-null `DomainDescriptor`. Strict JSON equality applies: `true` is not `1`.

`definition-reference` resolves only within the document's closed definition
map. Definitions MUST be acyclic and resolution is hop-bounded. Missing or
cyclic definitions are invalid. `graph-reference` is instead a governed scalar
identity edge with an explicit `allow` or `forbid` cycle policy. It is never
recursively expanded; the owning graph profile evaluates whole-graph cycle
rules when `forbid` is selected.

Conjunction is canonical, commutative, associative and idempotent for the
supported fragment. A delegated value contributes no value restriction. An
exact value inside a domain normalizes to that exact value. Conflicting exact
typed values produce `nonconformant`; input or import order never chooses a
winner. Constraints that cannot be safely folded remain a canonically ordered
`all-of`. The refinement helper recognizes a candidate when conjunction with
the baseline leaves the candidate unchanged. It MUST return `unsupported`
rather than inventing a relation for incompatible profiles or unresolved
semantics.

Presence is intersected separately from value restrictions. Required combined
with optional is required; forbidden combined with optional is forbidden;
required combined with forbidden is inconsistent. An `all-of` retains the
resulting presence instead of resetting it to required.

The legacy `RealizationStructure` exact/open/record/keyed-collection form is a
compatibility subset. Conversion binds its value-free exact nodes to the
existing admitted baseline, retains semantic member identities, and refuses a
lossy conversion of presence, provenance, domains, knowledge, references,
taxonomy sentinels, suffixed-field reinterpretation, unbound closed-record
defaults, collection aliases or non-default cardinality. A sequence is
projected to legacy exact authority only when its closure and recursive
children prove that the baseline is its sole accepted value. Compatibility is
established by matching equivalence over the supported subset, not DTO
round-trip equality or one conforming witness. The compatibility projection
MUST NOT become a second editable authority.

## 5. Bounded outcomes

Every normalization, evaluation, composition, refinement and compatibility
conversion receives positive limits for recursive depth, nodes, operations,
collection members, identity work, definition hops, scalar size, and emitted
diagnostics. Constraint nodes, optional or forbidden children, domains,
closures, scopes, aliases, profiles, origins, definitions and actual values are
admitted before their related work. Identity canonicalization is charged before
each keyed lookup or rewrite. Direct model/JSON construction is covered, not
only YAML parsing. Exhaustion returns `limit-exceeded` with a bounded,
value-free `Diagnostic`. Invalid shape, nonconformance, unresolved knowledge,
unsupported semantics, and exhaustion are distinct outcomes. Only `conformant`
is a success claim.

The pure relation layer performs no network fetch, plugin/profile code
execution, secret lookup, subprocess, filesystem mutation, backend call,
observation, persistence, or export. Diagnostic messages do not include raw
values, credentials, native paths, or backend exceptions.

## 6. Governing examples and migration boundary

Exactly five declared Linux nodes can use a locally closed node membership
universe plus one inherited open descendant scope. Their Linux constraints stay
exact while distributions, releases, resources and other unspecified details
remain delegated. A Kali refinement may add an exact release and required or
optional packages without closing sibling fields or incidental dependencies.
An optional package is absent or present-and-conforming.

An abstract two-computer/three-action transition model is complete at its
declared level. Literal normalization does not synthesize an OS, image, package,
filesystem, network mechanism, or observation request beneath it.

This contract does not change universal envelope subsumption or select and
deliver a backend witness (#1204). It does not migrate the public software
authoring surface (#1205), define realization reporting (#1209), negotiate all
legacy compatibility boundaries (#1210), supply integrated conformance (#1211),
or select observation, retention and export demand (#1212).
