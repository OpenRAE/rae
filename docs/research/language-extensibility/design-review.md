# Issue 1198: progressive specification and extensible domain descriptions

Status: design review and remediation proposal; not an accepted language change.
Reviewed 2026-09-04 against `dev` at `384e8b19` (RAES 3.5.0 lineage).
Tracking: [RAE #1198](https://github.com/OpenRAE/rae/issues/1198).
Published review and research: [#1201](https://github.com/OpenRAE/rae/issues/1201).
Remediation: [milestone 70](https://github.com/OpenRAE/rae/milestone/70).

## Governing intent, clarified 2026-09-05

The author constrains what matters. The backend resolves the remaining
materialization choices. RAE can describe the result at the requested depth.
The [maintainer's clarified design intent](design-intent.md) governs this review
and the remediation acceptance criteria.

We are deliberately correcting a tendency **against that design intent**:
installation recipes and captured specimens have become mandatory author
detail, centrally enumerated implementation catalogs, completeness guards and
unconditional evidence expectations. An extensible catalog alone is not the
fix. Open scopes must save authors from specifying irrelevant descendants;
abstract scenarios can already be complete; requested observation is independent
of realization detail. This clarification corrects the first review's own
overemphasis on completing concrete descriptions and reporting every choice.

## Finding

This is a class of language-design problems, not an isolated missing DNF profile.
RAE sometimes treats the vocabulary known to its implementation as the set of
things the language can describe. More fundamentally, some of its validation
and realization machinery conflates incomplete knowledge, permission to choose,
structural completeness, and exact requirements. Adding another repository
variant would fix one syntax rejection while leaving these problems intact.

The existing architecture also contains substantial parts of the solution:
typed domain models, stable references, scoped realization intent, bounded
constraint domains, artifact mechanism profiles, governed vocabulary extensions,
provenance, and separate admission and evidence contracts. Preserve these and
make their treatment of abstraction, delegated choices, partial information and
requested observations compositional. A wholesale rewrite,
an untyped configuration bag, and an exhaustive catalog of implementations are
all unnecessary.

The highest-priority correctness finding is that a known exact leaf can lose
its binding force when a sibling uses `other` or `unknown`. A bounded probe
reproduces this through the compiler and the registered-concern runtime
evaluator. This warrants a focused correction ahead of the larger migration.

## Intent and evidence basis

The maintainer's brief establishes the product requirement: researchers should
describe scenarios to arbitrary useful depth, selecting open, closed, and
undefined meaning at granular scopes. Backends should communicate additional
realized or captured detail using compatible descriptions. Neither researchers
nor core maintainers should have to enumerate irrelevant public or private
package repositories, products, or deployment routes.

[OpenRAE/hub#3](https://github.com/OpenRAE/hub/issues/3) assigns RAE semantics,
contracts, and conformance; Catalog reusable assets; LilRAE local realization
and evidence; and BigRAE organizational realization and operations. Its
ten-minute journey makes unnecessary author detail a product defect. Inspectable
results and honestly scoped evidence matter, but this is not authority to collect
or export every internal materialization choice on every run.
[Hub#29](https://github.com/OpenRAE/hub/issues/29) reinforces this division.
Neither issue says every backend must implement every valid description.

[RAE#847](https://github.com/OpenRAE/rae/issues/847) correctly identified that
putting undocumented repository syntax into `source` would create private
semantics. Its implementation, [#1194](https://github.com/OpenRAE/rae/pull/1194),
introduced the narrower APT-only contract. The latest
[env-packs#312 evidence](https://github.com/OpenRAE/env-packs/issues/312#issuecomment-5536029161)
reports four APT endpoints and two DNF endpoints; the latter remain blocked.
That is downstream evidence, not a backend run performed for this review.
The same pack requires endpoint identity, enrollment, service readiness, and
telemetry. Merely installing an arbitrary package is not equivalent to that
outcome. Conversely, requiring an enrolled Wazuh agent does not inherently
require the researcher to select its acquisition route.

The [scope inventory](scope-inventory.md) records coverage, false positives,
affected owners, and existing issues. The [research note](research.md) connects
primary sources to design decisions and records limitations. The executable
[audit](audit.py) reproduces the static census and behavioral probes. The
[remediation plan](remediation-plan.md) defines sequencing and acceptance.

### Breadth and limits

The static census covers all 801 Python files under
`implementations/python/packages` and all 105 published JSON schemas at the
reviewed revision. It finds 425 enum definitions, 700 `Literal` annotations,
and 277 enums in `raes`, of which 144 contain `other` or `unknown`. These are
candidate counts, **not 144 demonstrated bugs**. Schema occurrences repeat
definitions across contracts and must not be counted as distinct problems.

Semantic inspection covers all 17 indexed runtime families, the remaining
runtime configuration surfaces, core authoring, artifact generation and
materialization, manifests, concern compilation, runtime comparison,
observations, external bindings, variation, and published contract boundaries.
The review follows common validators and projections across those surfaces.
It does not claim a proof over every execution path, independent backend
conformance, or an exhaustive survey of possible domains. Static extraction
does not fully resolve aliases, computed enum values, arbitrary validators, or
hardcoded dictionaries; targeted source inspection supplements it.

## Confirmed findings

### F1. APT-only repository syntax also mixes outcome, acquisition, and final state

[`runtime_packages.py`](../../../implementations/python/packages/raes/runtime_packages.py)
fixes the repository discriminator to `apt`, requires an exact profile version,
and makes the repository and its signing key required final node state.
`RuntimePackage` requires `manager`, `name`, and `version`. A package without
`repository` is documented as using the target's ordinary configured sources.
The maintainer cannot describe only a software requirement in this model and
defer its package representation. Nor can a backend use this field to report
an unfamiliar repository in a typed way.

Three distinctions matter:

1. A repository *instance* is already data: the APT URI can name a private host.
   RAE does not enumerate every APT repository URL. The closed set is the
   repository protocol/profile shape and its trust/acquisition assumptions.
2. A software identity or capability requirement can be less specific than a
   package-manager coordinate. Even version equivalence is profile-owned:
   application `4.12.0` and distribution package `4.12.0-1` are not interchangeable
   strings without a defined relation.
3. An acquisition route can be temporary. Fetching through a cache, mirror,
   offline artifact, or prebuilt image need not leave a repository configured
   on the node. Requiring a repository to remain installed is a separate,
   legitimate scenario constraint.

The current schema's HTTPS and exact key-digest requirements can be useful in
a selected acquisition/trust profile. They should not become universal
requirements for expressing software presence, capturing a repository, or
describing a deliberately insecure repository in a research scenario.
Backend supply-chain authorization remains independently enforceable.
An unspecified software version may be completely irrelevant, not missing
information that an author must resolve. Even when an execution policy needs a
concrete installation recipe, that recipe need not enter authored SDL or an
experimental dataset. A selected version range is a binding constraint, not a
requirement for the author to choose one exact version.

### F2. Sentinel taxonomies are lossy extensions and unsafe realization signals

The normative [runtime-family invariant](../../../specs/sdl/runtime-inventory.md)
calls `unknown` and `other` an open enum tail. They mean respectively “not
determined” and “outside the closed set.” Nevertheless,
[`explicitness.py`](../../../implementations/python/packages/raes/explicitness.py)
classifies either sentinel in any enum as `OPEN`, and derives a container's
classification from its weakest child. The compiler's
[`semantic_explicitness_record`](../../../implementations/python/packages/raes_processor/compiler/realization_concern_explicitness.py)
also takes the weakest leaf over a whole registered concern.

Examples of affected externally owned identities include database engines,
datastore engines, DNS implementations, forwarding implementations, security
monitoring implementations, network sensors/detection engines, orchestration
engines, and service managers. Protocols, formats, provenance sources, and
product-shaped settings also use this pattern. An unrecognized implementation
token is rejected by `parse_runtime_enum_or_var`; `Enum | str` generally admits
variables, not arbitrary implementation identifiers.

Two private engines mapped to `other` become indistinguishable in that field.
Some models offer names, settings, software-component records, or evidence
references that preserve additional text elsewhere. Those do not automatically
define an exact engine identity, typed extension semantics, or comparison rule.
`unknown` is an information state, not an implementation identity or a grant of
discretion. `other` can be a known, exact value outside a standard vocabulary.

The probe authors `database_service_id: db` and `engine: other`. The ID is
classified exact, but the compiled database collection is open. Supplying a
synthetic, shape-valid observation of `different-db` with matching observation
capability/disclosure produces no diagnostic in the registered-concern runtime
evaluator. The open branch never compares the original ID. This is a bounded
compiler/evaluator counterexample, not a claim that a real backend was deployed
or that all independent gates would accept every mutation.

### F3. Registered collection boundaries defeat arbitrary-depth specificity

[`realization_runtime_concern_profiles.py`](../../../implementations/python/packages/raes_processor/semantics/realization_runtime_concern_profiles.py)
registers whole collections such as `packages` and `database_services`.
[`realization_requirements.py`](../../../implementations/python/packages/raes_processor/compiler/realization_requirements.py)
resolves one aggregate posture at the registered path. The designation table
can address deeper JSON pointers, but that is not sufficient to make their
meaning survive concern compilation.

The probe supplies an exact package and an `open` override on
`/nodes/host/runtime/packages/0/repository`. Compilation emits one exact
`runtime-packages` authority entry. The nested opening does not survive as
independent authority. The reverse problem occurs with the sentinel in F2:
one incomplete leaf opens the whole collection. Making every leaf a manually
registered concern would replace a semantic problem with an unmaintainable
registry.

Exact projection also normalizes through the full SDL type, including defaults.
That supports deterministic equality but is not a general partial-description
relation. “These two packages must exist” and “these are all packages” need
different collection semantics. So do a known empty collection, an unobserved
collection, and a collection observed only in part. A single aggregate
exact/open flag cannot carry all these distinctions.

The current `unspecified` cascade ignores local unspecified entries while an
outer concrete posture exists; without one it delegates, with a closed fallback.
The probe confirms that behavior. It matches the current specification and is
**not classified as an implementation bug**. Its terminology must be reconciled
with undefined information and explicit delegation in the new design.

Inherited openness must work as a subtree rule, not per-property opt-outs.
Five Linux boxes with open descendants requires the backend to choose five
conforming boxes, not request a completed OS/image/package form. An abstract
two-computer/three-action model may already be complete without any of those
physical details. Neither case is fixed merely by making a concrete schema's
fields optional.

### F4. Some type guards require complete specimen-shaped configuration

Current examples include:

- `RuntimeDatastoreService`: `key_value` requires persistence;
  `search_index` requires index partitions, shard/replica geometry and mappings;
  `wide_column` requires keyspaces and replication configuration.
- `RuntimeForwardingAgent`: `log_forwarder` requires buffer policy and ingestion
  target; `content_sync` requires API pull, IOC-to-rule transform and reload.
- `RuntimeOrchestrationAuthority`: host-root-equivalent classification requires
  a concrete control-interface reference.

These checks are visible in the corresponding `runtime_*.py` models. They can
be sensible requirements for a particular executable profile. They reject
truthful partial descriptions and incomplete captures when placed in base
model validation. Some also overstate the portable concept: a key-value service
need not persist, and content synchronization need not involve IOCs or reloads.
Security-relevant execution still requires enough authority information to
admit the operation; accepting a partial description must not authorize it.

[Issue #956](https://github.com/OpenRAE/rae/issues/956) already exposed this
failure with MISP sharing groups. Its shipped platform-application correction
uses composable capabilities and optional configured state. Do not restore the
old guard or create a duplicate issue for that fixed instance.
[Issue #959](https://github.com/OpenRAE/rae/issues/959) is the existing broader
product-shaped-semantics audit; this review supplies overlapping evidence and
extends it to information/authority semantics and the lifecycle.

### F5. The same catalog pressure exists outside runtime product enums

`GeneratedArtifactKind` admits only certificate bundles, rendered configuration,
and SSH key bundles. Content service-materialization authoring has a closed
union of two profiles. Interactive access admits SSH/RDP. Authored identity
domains admit an Active Directory profile; identity facades admit OIDC. These
are useful initial profiles, but their containing surfaces offer no equivalent
way to describe and admit a private typed profile without a core schema change.
Their backend capability fields sometimes already permit governed extensions,
creating an authoring/capability mismatch.

Retain concrete, checked profile definitions. Extend the containing profile
selection/description contract. An exact `profile_version: '1'` inside one
version's definition is correct; the problem is treating that definition's
closed union as the universe of describable implementations.

Externally sourced classification fields are another instance of catalog
pressure. [#986](https://github.com/OpenRAE/rae/issues/986) has delivered generic
external bindings; [#989](https://github.com/OpenRAE/rae/issues/989) already owns
migration of the domain-shaped fields. External classification remains an
assertion about native meaning, not an executable escape hatch.

### F6. Capture fidelity and author authority need a shared representation boundary

[`validate_typed_runtime_observation`](../../../implementations/python/packages/raes_processor/semantics/realization_concern_observations.py)
validates observations through the same SDL types and defaults. Consequently,
F1, F2 and F4 affect representable observations as well as authors. A backend
can retain raw evidence elsewhere, but that is not a recursively typed,
comparable description of unfamiliar domain detail.

Representability is not compulsory observation. The ability to report selected
Linux distributions, or captured package detail, must not force every run to
collect, retain or export an exhaustive inventory. Scenario specificity,
realization reporting, experimental measurement demand and internal operational
needs require distinct scope and policy. The first review did not state this
independence strongly enough; L13 now owns the missing demand contract.

The repository correctly distinguishes authored, defaulted, planned, realized,
observed and derived authority in ADR-033 and its lifecycle contracts. Keep that
distinction. Sharing a description algebra does not make every observation an
author requirement, nor does it establish truth or completeness. A capture may
contradict a requirement, miss a field, redact it, or observe another time.
Only a conforming realization projected onto the author's owned scope can be
said to refine the requirement. Evidence and interpretation require their own
relations and provenance.

## Cause and architectural interpretation

The history suggests a recurring mechanism: a concrete inventory gap motivates
a typed family; a specimen supplies enums and required child profiles; tests
lock down that shape; the same model later becomes realization authority.
Closed parsing, reproducibility, and opposition to untyped payloads then make
the accidental completeness requirement look necessary. This is an inference
from ADR-029/033/048/049/050/051, the shared inventory invariants, #847, #956,
#959, and current code—not an attribution of motive to contributors.

Four different closures have been conflated:

| Closure | Question | Appropriate owner |
|---|---|---|
| Syntax/schema | Is this property or encoding understood? | Versioned schema and selected extensions |
| Vocabulary | Can a new external identity be represented? | Stable identifiers and vocabulary policy |
| Scenario structure | Are additional members/properties permitted here? | Author constraint at that scope |
| Knowledge | Does this capture account for everything in this scope? | Observer coverage and evidence |

Rejecting misspelled keys remains valuable. It does not establish a closed-world
claim about everything running on a machine. Conversely, an open vocabulary
does not grant permission to substitute an exact selected identity.

## Recommended design

### 1. Define a small recursive description and constraint algebra

Treat a requirement as a set of acceptable states, with typed records and
collections as compositions of constraints. If `D2` refines `D1`, then
`States(D2)` is a subset of `States(D1)`; conjunction is intersection and a
conflict has no satisfying state. This applies to declared properties within
their owned scope, not to scientific equivalence of whole experiments.

Keep these axes independent in the semantic representation:

| Axis | Distinctions that must survive |
|---|---|
| Presence | Required, optional, forbidden |
| Value restriction | Exact value, bounded domain, deliberately open |
| Information | Known value, unknown/unobserved, withheld/redacted, not applicable |
| Structure | Open or closed record/collection membership at each scope |
| Authority | Author constraint, explicit delegation, selected policy, backend claim, observation, derivation |

The model's abstraction level and its observation/reporting demand are also
independent. They belong at their existing semantic owners, not in a mandatory
wrapper on every value. A detailed filesystem specification can request no
experimental telemetry; an abstract model can request every action trace.

Undefined means no local statement; inheritance and an explicitly selected
realization policy determine its effect. It must not be silently converted
into unknown evidence, an exact default, or unrestricted mutation authority.
An `open` child delegates within its declared type and all applicable safety
and capability constraints; an inherited open scope also covers unspecified
descendants without listing them. Explicit descendants remain binding and do
not close their siblings. A `closed` record/collection constrains additions;
it does not mean boolean false or a globally empty runtime. Explicit presence
and absence must be representable without abusing empty strings or sentinels.

Use one normal form for known core models and selected extension models.
Carry leaf constraints separately from container closure and preserve both
through compilation and runtime checks. Address set-like collections by stable
identity; use indices only for genuinely ordered sequences. Define duplicate
identity, aliasing, ordered-list versus set semantics, and ambiguous matches.
An opening in one branch must never weaken an exact sibling.

“Arbitrary depth” means the same rules compose at any finite domain depth,
including nested extension data. It does not require unbounded memory,
undecidable constraints, or arbitrary executable predicates. Advertised limits
on bytes, nesting, references, and validation work should yield explicit
unsupported/limit diagnostics. General recursive schemas and recursive values
are distinct choices; begin with finite trees and named acyclic schema
references, retaining stable graph references for cross-object relations.

Build on SEM-218, SEM-219 and the bounded-domain contracts. Do not create a
second incompatible realization language. The distinction from SCE-002 remains:
variation chooses an experimental case; realization fills only the freedom
left inside that selected case.

Do not confuse selection with a universal capability promise. A delegated
request needs a backend-supported witness satisfying the authored constraints
and selected policy, not support for every possible open completion. ADR-070
and the existing envelope formal contract define the stronger subset relation;
`realization_envelope_diagnostics` also invokes subsumption for open demand.
L2/L5 must distinguish the quantifier at each boundary, retaining universal
conformance guarantees where actually requested. This is a source-backed
contract-alignment concern, not a newly demonstrated full execution failure or
permission to silently redefine `subsumes`.

### 2. Make domain extension explicit, typed, and independently distributable

Use stable qualified identity for externally owned concepts, optionally paired
with a standard classification. Preserve existing canonical terms and the
repository's governed-extension form during migration. A private identity must
be meaningful and preservable without public registration. Namespace ownership,
comparison, case normalization, and collision behavior need an explicit
contract; an `x-` spelling alone is not proof of uniqueness or trusted authority.

For unfamiliar structure, reuse the existing artifact/profile infrastructure:
an extension definition has an authority, identity, immutable revision/digest,
schema, semantic contract, composition rules and optional comparison/admission
capabilities. Bind it to an existing concept and lifecycle surface. Core schema
keys remain checked. Extension keys are checked against the selected extension
schema, which may itself declare further typed children and closure.

An unresolved extension may be preserved as an explicitly opaque, bounded
artifact for exchange/inspection. It must not be advertised as semantically
validated. Required execution or comparison semantics must be understood or
reported unsupported before mutation. A preserved annotation is different from
a required constraint. Unknown required meaning must never be silently ignored.

Schema retrieval and validator execution are explicit operations governed by
local trust and resource limits. Ordinary parsing performs no network lookup,
credential acquisition, or installation of arbitrary code. Support private and
offline schemas through pinned local inputs and existing artifact distribution.
Reuse the artifact-mechanism and external-binding admission patterns; avoid a
parallel global registry or plugin manager.

This permits domain authors to extend RAE while RAE retains authority over the
meaning of extension, composition, support, disclosure, and conformance.
Public reusable profiles can live with catalog content; private profiles can
remain local. Backend code owns realization mechanisms. None of those roles
permits pack-local reinterpretation of existing core fields.

This extension machinery is needed when a profile is described, constrained or
exchanged. It is not a requirement to expose every backend-internal choice as
an SDL profile. An irrelevant private repository can remain an internal
acquisition detail with no author registration, profile declaration or research
provenance obligation.

### 3. Separate software requirements, acquisition constraints, and repository state

Provide a minimal software/component requirement with progressively optional
identity, version, package coordinates, service/behavior constraints and
acquisition restrictions. Reuse `software_components`, artifact requirements,
and proposition/service contracts where their meaning fits; decide the exact
authoring owner during the first design issue to avoid creating another
competing software inventory.

The following is semantic pseudocode, **not supported SDL syntax**:

```text
host.software[agent]:
  identity = Wazuh endpoint agent
  enclosing materialization scope = open

optional refinements, only if important to the scenario:
  application-version = exact value or defined older/newer/range constraint
  enrollment/readiness/behavior = declared requirements
  package/source/final repository configuration = declared constraints

backend responsibility:
  choose and realize a conforming agent within the inherited freedom

report, when requested and at the requested depth:
  describe the choices actually made and their actual knowledge/evidence basis
  include acquisition or inventory detail only within the selected report policy
```

Neither a version field nor explicit per-field package-manager/acquisition
waivers are required for the minimal request. Operational telemetry that a
declared Wazuh behavior needs is also distinct from an experimental request to
collect or retain that telemetry. This pseudocode illustrates semantic owners,
not a new software surface or one combined node/evidence configuration object.

Authors can then refine the requirement to a particular DNF profile, an exact
APT repository and key, a private mirror, an offline artifact, or “no repository
configuration may remain.” Those refinements must be binding. The backend must
satisfy the software and behavior requirement; openness is not license to
install a vaguely similar agent. The selected verification/evidence policy
determines which checks and returned basis are required. This does not impose
independent measurement, package digests or acquisition provenance on every run.

An optional, final-state repository description should have its own identity
and references so shared repositories/trust state are not duplicated across
package rows. Keep APT-specific suite/components inside the APT profile.
Provide APT, DNF and private/offline examples using the same extension contract.
Do not make delivery of one more built-in profile the completion condition.

### 4. Validate description, admission, realization, and evidence separately

A partial but well-typed description should be inspectable, composable, and
exchangeable. An abstract description may already be complete at its chosen
level. Admission determines whether a selected backend can realize the declared
semantics and resolve delegated choices under the selected policy. Genuine
missing meaning, unavailable capabilities or conflicting policy can block it;
deliberately unspecified implementation choices should not be returned to the
author as mandatory input when the backend can resolve them.
A stronger completeness profile can demand more fields without making them
mandatory for every use of the base type. Captures report observed coverage
instead of inventing missing fields to satisfy deployment guards.

Use the same description structures for backend claims and capture facts,
with distinct lifecycle envelopes and provenance. Preserve author constraints
immutably. Backends must be able to report their actual choices at the requested
depth. A requested claim records relevant choices and a refinement relation;
a requested observation records source, scope, time, coverage and limitations.
Neither requires collecting or exporting every possible field. A deliberate
promotion operation creates a new authored artifact from selected observed
facts. It must not freeze incidental package inventories, generated IDs, or
backend defaults just because they appeared in a capture.

Completeness is relative to a selected scope and vocabulary/profile revision.
Closing one DNS RRset is meaningful; claiming complete knowledge of an entire
host from a partial scanner result is not. Retain conflicting observations as
evidence and report unresolved satisfaction rather than overwrite authority.

L13 defines no experimental data, operational-only, inherited/no-preference and
scoped detailed/exhaustive observation demand, including retention and export.
These are independent of how precisely the environment is specified. Existing
#1112 continues to enforce genuinely required capture; the correction must
prevent invention of unrequested evidence obligations, not waive declared ones.
Claim strength remains honest when corroboration was not requested or performed.

### 5. Keep the common authoring path small

Do not require a wrapper around every scalar, explicit namespace boilerplate
for every built-in field, or a dissertation in every scenario. Keep ordinary
YAML literals as exact statements, offer reusable profiles and concise scope
defaults, and reserve long form for partial domains, closure and extensions.
The normal form can be richer than the surface syntax.

Tooling should answer: what have I constrained; what remains undefined; what
may this backend choose; why is admission blocked; what did it choose; and
what did we actually observe? Show requested versus operational data, inherited
posture and its source; offer deeper realization reports without imposing them.
Explain
that closing a collection affects extra members and that naming one component
does not silently close a machine's entire inventory.

## Alternatives and tradeoffs

| Option | Assessment |
|---|---|
| Add DNF and keep extending core unions | Immediate local relief; preserves catalog growth, partiality loss and authority bugs. Insufficient outcome for #1198. |
| Change all enums to strings or allow arbitrary keys | Preserves spelling but loses portable semantics, typo checks, comparison, and admission. Reject. |
| Use only `other`, `unknown`, free-form settings or raw evidence | Useful for limited observations; insufficient for exact private identity and typed recursive constraints. Reject as the universal mechanism. |
| Make author-relevant runtime detail inexpressible and exclusively backend-private | Breaks deep researcher control and requested typed capture; conflicts with ADR-033. Reject. Irrelevant, unconstrained backend choices may remain internal. |
| Require complete executable declarations everywhere | Makes partial authoring/capture impossible and forces irrelevant backend choices. Reject. |
| Adopt CUE wholesale | Strong semantic precedent and potential prototype/oracle; introduces a language/runtime migration and still needs RAE authority/evidence contracts. Evaluate experimentally, not required. |
| Small recursive core plus reusable typed domain profiles | Recommended only with inherited delegation, complete abstract models and independent observation demand. Extensible profiles alone do not cure forced specification. Requires deliberate migration and useful tooling. |

The cost is real: partial comparison and closure are harder than full object
equality; extension schemas need distribution and trust; and not every consumer
will understand every profile. The alternative already incurs distributed
catalog maintenance and repeated correctness fixes. An early, explicit
semantic revision is preferable to claiming backward compatibility while
silently changing what omitted fields authorize.

## Decisions needed before implementing the new language contract

The remediation's semantic-contract issue (L2) should settle and record concrete examples for:
the omission/undefined default in a new authoring version; the surface syntax
for nested closure; stable identities for package and extension collections;
the minimal software requirement's owner; extension schema and semantic-profile
packaging; delegated-choice versus universal-capability admission; independent
observation/reporting/retention policy; and the migration boundary. The Linux,
Kali, abstract-machine and cross-axis evidence cases in [design intent](design-intent.md)
are mandatory acceptance anchors. These are design choices to review with
the proposed examples, not reasons to defer the confirmed bug fixes or the
creation of a remediation backlog.

No runtime/schema semantics change in this review. Existing scenario meaning
must remain explicit until a versioned migration or a targeted correctness fix
is delivered. The milestone closes on demonstrated semantics and migration,
not on the existence of this document.
