# Software requirements, acquisition and final repositories

Design rationale: [ADR-034](../../docs/decisions/adrs/adr-034-runtime-software-component-inventory.md).

Status: **normative**. This extends the existing node-local software owner and
the [recursive constraint contract](recursive-realization-constraints.md).
The published SDL and plan schemas are the machine-readable companions.

## 1. One software owner and compatibility

`nodes.<node>.runtime.software_components[]` owns component requirements.
`component_id` is author-owned stable identity, not a package name, installation
method, product catalog entry or evidence identifier. `name` names the component.
Presence defaults to `required`; `optional` means conform if present and
`forbidden` means absent, independently of version. Collection matching MUST
use identity, never list position. An enclosing open realization scope delegates
unspecified descendants; explicit values remain binding.

Authors MAY omit version, manager, package coordinates, acquisition, repository,
digest and provenance detail. Component availability does not establish service
readiness, enrollment, invocation or behavior. Those obligations retain their
existing service, condition, proposition and participant-contract owners.

The optional `package` refinement reuses the exact `RuntimePackage` wire shape:
manager, name and distribution-package version, with optional architecture,
opaque source label, package URL identity and legacy repository. The top-level
node-runtime `packages[]` surface remains its compatibility shorthand. It MUST
retain exact versions and APT v1 final repository/trust meaning; it MUST NOT be
reinterpreted as transient acquisition. Both encodings use the same package
model, architecture checks and recursive conformance relation. There is no
second package comparator or installer for the canonical encoding.
An embedded package on a forbidden component is not a positive installation
requirement and MUST NOT require a matching node architecture.

`package_ref: {manager, name, architecture?}` explicitly relates a component to
exactly one legacy package row on the same node. An absent architecture in the
reference is allowed only when manager/name resolves uniquely. Matching names
alone MUST NOT create correspondence. Explicit component package coordinates,
an embedded package and a referenced row MUST agree when combined. The reference
implies the referenced manager, name and package version in realized component
data; compiler-derived constraints MUST survive portable plan/result admission.
An application version is not one of these implied coordinates.

Unique legacy manager/name rows retain architecture delegation. Repeated
manager/name rows require architecture-disambiguated identity, not positional
matching. The bounded reference implementation rejects ambiguous completions;
it does not infer architecture aliases beyond the existing governed vocabulary
or relax node/package architecture compatibility.

## 2. Version constraints

`version` and `package_version` are independent exact strings. No comparison
relation changes their exact-string meaning. `version_constraint` and
`package_version_constraint` optionally add a `kind: version` predicate with:

- `relation`: exact semantic `authority`, `contract_id`, `revision`, `digest`;
- `lower` and/or `upper`: nonempty strings of at most 256 characters;
- `lower_closed` and `upper_closed`: inclusive endpoints, both default true.

At least one endpoint is required. A lower-only exclusive predicate expresses
newer-than; an upper-only exclusive predicate expresses older-than. Two bounds
express a range. No restriction requires no predicate, not a compulsory exact
version or a sentinel range. An exact string and a predicate conjoin; neither
overrides the other. Known empty intervals and known incompatible exact values
are invalid. Unknown relation identities remain exchangeable, but required
unsupported comparisons MUST be refused before execution.

The reference implementation installs three pure bounded relations under
`https://openrae.org/semantics/versions`, revision `1`. Their digest is the
canonical SHA-256 JSON digest of `{"relation": <contract_id>, "revision": "1"}`.
These revision identities denote the following immutable meanings:

| Contract id | Meaning |
| --- | --- |
| `numeric-triplet` | Exactly three dot-separated unsigned decimal components, each at most nine digits, without leading zeros except `0`; numeric tuple order. This is not general SemVer. |
| `debian` | Debian epoch/upstream/revision ordering, including tilde; the bounded spelling admits alphanumerics, dot, plus, tilde, hyphen and a single optional numeric epoch prefix. Upstream colons are outside this fragment. |
| `rpm` | RPM epoch/version/release ordering, including tilde and caret, over bounded ASCII EVR spellings. |

Debian and RPM ordering follow their respective primary specifications:
[Debian Policy §5.6.12](https://www.debian.org/doc/debian-policy/ch-controlfields.html#version)
and [RPM version semantics](https://rpm.org/docs/6.0.x/man/rpm-version.7).
Strings outside an installed relation's admitted syntax return `unresolved`;
unrecognized full relation coordinates return `unsupported`. Neither outcome
means a proven contradiction, conformance or permission to approximate.
Composition MUST retain such predicates rather than discard them beside an
exact value. Comparator selection MUST NOT import code, fetch definitions,
execute commands or inspect the host from author-supplied data.

A `version-correspondence` refinement MAY select a defined profile-owned
application/package relation. Its installed semantic validator owns that joint
relationship. Core MUST NOT equate the two versions by stripping suffixes,
normalizing names or observing coincidental equality.

## 3. Optional typed refinements

Components carry optional `refinements[]`, each with a unique `refinement_id`,
`purpose`, immutable `definition` and bounded JSON `profile_value`. Components
MUST accept only `acquisition` and `version-correspondence` purposes. Repository
and trust constraints MUST attach to their respective shared identity owners,
never directly to a component. Published schemas and runtime validation MUST
enforce the same owner/purpose restrictions. Definition
identity, schema identity, semantic contract identity, namespace admission and
operation-specific support follow the existing domain-profile contracts.
JSON data keys inside `schema_document` and `profile_value` retain their exact
spelling; they are not structural SDL field aliases. Duplicate YAML keys and
source resource limits still apply.

| Owner | Purpose | Plan-host context |
| --- | --- | --- |
| Component | `acquisition` | `artifact-acquisition` |
| Component | `version-correspondence` | `software-version-correspondence` |
| Repository | `repository-state` | `software-repository-state` |
| Trust binding | `repository-trust` | `software-repository-trust` |

Refinements lower into the existing
[plan profile host](plan-realization-profiles.md), not a parallel execution
protocol. Bindings carry the node resource address and an identity-derived
binding id; their source reference identifies the component, repository or
trust identity and refinement id. Definition integrity provenance marked
`author-constraint-only` is not target trust or acquisition authorization.
An independently configured, digest-bound target resolution context and
installed comparison/execution support are REQUIRED. The native joint
profile/core validator remains mandatory before effects.

Profile values inherit concrete enclosing realization posture, including local
closed children within an open parent. Exact leaves always bind. The current
authoring adapter requires a resolved enclosing posture for profile values;
it refuses unresolved apparatus-default profile closure instead of silently
selecting one. Profile definitions are public exchange data, never executable
code, secret containers or implicit support declarations.

APT, RPM/DNF, private APT instances, private protocols, cached/offline artifacts
and prebuilt images are acquisition choices that installed profiles and
backends MAY realize. Their names in profile data MUST NOT activate core
installers. No profile, package digest or acquisition provenance is compulsory
when the route is left internal. Describing an insecure repository/trust
posture is permitted by an appropriate typed profile; that description MUST
NOT grant network, credential, trust-bypass or installation authority.

## 4. Shared final repository and trust state

`runtime.repository_state` separately owns bounded `repositories[]` and
`trust_bindings[]` collections. Their stable local identities are
`repository_id` and `trust_id`, respectively. Each accepts independent
required/optional/forbidden presence and optional refinements; repositories
accept only `repository-state` refinements and trusts only `repository-trust`.
A repository's optional `trust_ref` resolves one trust binding on that node.
Component `repository_refs[]` resolve shared final repository identities as an
unordered set. Reordering references MUST NOT affect conformance. Open sets may
contain additional valid references; closed sets require the same identities.

Duplicate identities, duplicate references and dangling references are invalid.
A required source cannot depend on optional or forbidden final state. An
optional source cannot depend on forbidden final state. Optional references
are also checked against the actual returned collections when their source is
present; absence must not leave a dangling realized link. Multiple components
can share a repository and trust identity without copying their definitions.
Identity without a concrete refinement does not assert a particular key,
repository URL, signature policy or secure configuration.

Acquisition does not imply retention of its repository or trust configuration.
Explicit forbidden final-state members MUST be absent after realization. The
legacy package repository contract remains an explicit final-state constraint,
including its credential-free HTTPS, exact key-byte digest and dedicated trust
semantics. Free-form `source` labels remain opaque.

## 5. Admission, reporting and evidence

Required comparisons need concern-specific constraint support, not merely
exact-value support. Unknown profiles/relations or unsupported target behavior
MUST fail honestly. Shared recursive constraints and pinned profile authority
survive compiler, portable plan, preparation and result boundaries. Rejected
results MUST NOT replace trusted predecessor state.

Component presence alone does not add a guest scan, package digest, acquisition
telemetry, experimental evidence, retention or export obligation. Existing
explicitly selected stronger operational/behavior contracts and legacy package
verification obligations remain independent and binding. The observation-demand
contract selects software/OS realization-description detail at the requested
basis and depth. Backend-selected values MUST NOT be reported as observations;
unrequested internal routes MUST NOT become public report detail. Collection,
retention and export remain independently governed.

RAE conformance tests qualify these generic contract boundaries. They do not
claim a native installer works, a service is ready, or a scenario journey has
been qualified. Those effects and cross-repository acceptance are external to
the language and its conformance implementation.
