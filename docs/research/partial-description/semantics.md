# Candidate semantic contract: review-1

This candidate is the decision surface for #1201 and
[ADR-105](../../decisions/adrs/adr-105-recursive-partial-description-semantics.md).
MUST and MUST NOT below bind this proposed revision. They do not amend current
published SDL or accepted formal contracts. Python constructors in the reference
model are review notation, not a proposed public authoring grammar.

## 1. Independent axes and defaults

The author constrains what matters. An effective open scope delegates remaining
realizable choices recursively. The backend MUST select and deliver a supported
permitted realization; absence of an installation recipe is not itself a defect.
The model MUST support describing deep detail without requiring it everywhere.

| Axis | Decision |
| --- | --- |
| Required presence | The named member MUST exist and satisfy its value/child constraints. |
| Optional presence | It MAY be absent; if present, all attached constraints remain binding. |
| Forbidden presence | The named member MUST be absent. This is author authority, distinct from an observation of absence. |
| Omission / undefined | No local statement. Inherit the applicable scope and selected policy; do not manufacture a literal default or a waiver for each field. |
| Known absence | An information assertion with coverage, time and source, not permission to remove something. |
| Unknown | No known value; never realization permission or an external identity. |
| Redacted | Information withheld under its owner's marking/visibility rules; raw value MUST be absent. |
| Not applicable | The selected semantic profile excludes this concern. Without that profile basis it cannot prove absence or satisfaction. |
| Null / empty | Ordinary exact values where the owning type admits them. An empty collection and an unobserved collection differ. |
| External identity | Exact identity under a named authority; unfamiliar identity is not automatically `other`, unknown, or open. |

There are two operations, resolved separately. Lexical defaults select an
effective posture; conjunction combines binding constraints. The most specific
defined semantic scope wins over an outer default. Undefined does not shadow a
defined ancestor. Equal-scope duplicate declarations are errors, even if input
order or import order differs. Explicit leaf constraints always apply.

For this candidate, an undefined root inherits an explicitly selected execution
profile's default. If none is selected, description exchange remains valid but
execution reports `policy-unselected` to the operator. It MUST NOT ask the author
to enumerate all delegated fields. The finite harness explicitly uses a closed
fallback unless a test selects open. This is not a proposal to change the
legacy SDL fallback implicitly.

A scalar default is a preference for choosing a witness inside the already
conjoined domain. It is not an exact authored fact. An explicit constraint can
exclude it; equal-priority incompatible preferences require an explicit policy
decision. Normalization MUST preserve origin and MUST NOT inject defaults into
captured facts. The prototype normalizer only orders fields and atom sets; it
does not implement scalar preference selection.

## 2. Recursive constraints and scoped closure

Let `R(D)` be the set of worlds satisfying description `D` at its declared
abstraction and profile revision. Conjunction is set intersection:
`R(A ∧ B) = R(A) ∩ R(B)`. A refinement `A'` satisfies `R(A') ⊆ R(A)`.
Composition is commutative, associative and idempotent after scope/default
resolution. Conflicting exact values form an empty domain; neither import order
nor a weaker sibling resolves the conflict. An optional member with an empty
value domain can only be absent; a required member with that domain is impossible.

Leaf domains reuse the accepted bounded-domain categories: type-sensitive exact
values, finite sets, booleans, bounded numeric intervals with units/endpoints,
and governed references. `true` and `1` are different. Domain-owned comparison
normalizes units or versions only when the selected relation authorizes it.
Unsupported comparison reports a limitation instead of treating unequal strings
as equivalent. Arbitrary callbacks, unbounded regex and ambient queries are not
part of the fragment.

Record shape closure rejects unknown *syntax keys*. Scenario record closure
restricts unmentioned fields in a named semantic record universe. Collection
closure restricts additional modeled members in a named inventory universe.
Observation completeness describes coverage. Vocabulary closure describes which
identities/semantics a profile understands. None implies any of the others.

A closed collection includes exactly its required members plus whichever
optional members are present. It does not close member internals or sibling
collections. A closed record with a binding allowed-key set does not become open
because another conjunct mentions an extra key: that is a conflict, requiring a
new authored revision. A local open *default* can override an inherited closed
default, but cannot widen a binding domain or erase binding membership closure.

Each closure names a profile revision, semantic scope and universe. For example,
`modeled-software/v1` concerns modeled scenario software; incidental dependencies
belong to a separate declared projection. That partition is profile-owned,
never a backend's opportunity to relabel a forbidden scenario member as
incidental. Exhaustive OS inventory is a different, explicitly selected domain
with a supported enumeration/coverage obligation. No closure means “there are
no other files anywhere on the machine.”

## 3. Identity, composition and finite recursion

Set-like collections use `(module namespace, collection kind, local semantic id)`
and their profile's identity relation. IDs are stable through composition and
capture; duplicates or multiple candidate matches fail. A captured row without
sufficient identity remains unmatched evidence, not a best-effort overwrite.
Explicit aliases need a single collision-free mapping before comparison. Fuzzy
name matching, variable-generated IDs and first-match-wins are prohibited.
Reordering set-like inventory does not retarget constraints. Ordered sequences
retain order and use their own sequence/occurrence identities; they are not
silently converted into sets. Cardinality is independent of child precision.

The finite model uses tuples of semantic path components and record keys for
collection identities. Production serialization must reuse qualified identity,
the composition symbol map and canonical RFC 6901 addressing; raw list indices
cannot be the durable semantic address. Canonical ordering preserves meaning,
not authority. Production digests reuse existing canonical SDL/JCS helpers over
an explicitly versioned semantic projection; digest equality is not refinement.

Recursively nested finite values are supported with a maximum depth. The first
candidate fragment permits only acyclic schema/constraint definition expansion.
Self-recursive schema definitions are rejected as unsupported, not unfolded
until they happen to fit a fixture. Ordinary domain graph references may cycle
only where the owning domain permits a graph cycle; they remain identity edges,
not recursive value expansion. Execution dependency cycles still use their
existing domain diagnostics. Missing references fail before semantic admission.

Portable limits must be carried by the selected revision. This prototype bounds
depth at 32, semantic operations at 4,096 per relation, scope/source counts at
256, reference hops at 256, scalar strings at 4,096 characters and integer
width at 256 bits. Values and constraints supplied directly to Python are
bounded too. Its budget counts validation, comparisons and enumeration, not
merely serialized size. Budget exhaustion is `limit-exceeded`, never an empty
set, successful validation or proof of unsatisfiability. Production also needs
byte, alias/import, matching, diagnostic and wall-time bounds from its existing
parser and executor owners; this in-process oracle is not that service.

## 4. One witness and universal coverage

For delegated execution, choose `w ∈ R ∩ B ∩ P`, where `B` is the backend's
actual supported offer and `P` the selected execution policy. Then deliver `w`
and enforce all authored constraints. Finding an overlap or selecting a
dictionary does not establish delivery. A failure can be unsatisfiable demand,
unsupported semantics, unavailable capability, policy conflict or exhausted
search; these outcomes MUST remain distinguishable.

Universal capability claims retain `subsumes(B, R) ⇔ R ⊆ B`. One permitted
Linux distribution can satisfy a delegated Linux request without proving
support for every distribution. Conversely, one witness cannot establish a
universal promise. The empty request set is a subset of every offer but never
successful operational admission. Allocation/randomization selects experimental
factors before backend realization; backend choice cannot substitute another
factor or consume an experiment random stream.

The audit below records current code at the preflight revision `164dd140`.
Package paths are relative to `implementations/python/packages/`.

| Boundary | Current quantifier / obligation | Candidate decision |
| --- | --- | --- |
| `raes/realization_envelope.py::subsumes` and ADR-070 §2 / formal R4 | Every requested world belongs to the offer. | Preserve universal subset semantics and closure checks. |
| `member` | One concrete instance satisfies an envelope after SDL validation. | Preserve membership; no capability or evidence-strength inference. |
| `witness` | Construct one envelope member and validate SDL. | Keep conformance witness generation separate from backend choice and experiment allocation. |
| `raes_processor/semantics/realization.py::realization_envelope_diagnostics` | Open non-substrate paths are projected into a request and checked by universal `subsumes`. | #1204 must introduce a negotiated delegated-selection boundary with a delivered witness; never replace the shared relation globally. |
| `_compute_substrate_claim_admits` | The disclosed mechanism is a member of the requested value domain, with the existing strength check. | This is already a single-mechanism check, not proof of universal substrate coverage; preserve exact constraints and review strength through #1212. |
| Planner and `raes_runtime/control_plane_submission.py` | Existing plan-owned authority, selected configuration and envelope checks before mutation. | Both entry paths must consume the versioned admission result; no alternate-submission bypass. |
| `raes_conformance/realization.py::run_realization_conformance` | Configuration-identity match, generated positive and negative probes, observed execution basis. | Keep refusal probes and native-basis safeguards. The finite probe suite falsifies dishonesty; it is not an enumeration proof over every possible world. |
| Runtime snapshot/observation admission | Enforce actual constraints and required corroboration under current contracts. | Validate delivered choices and independently requested evidence separately, while preserving honest validation-strength caps. |

## 5. Software and extensions

The minimal software requirement belongs to
`Node.runtime.software_components` (ADR-034), using stable component identity
and required presence. Version is optional. `runtime.packages` remains an
explicit package-manager-coordinate refinement; its existing APT v1 declaration
continues to require the documented final repository/trust state. The candidate
does not reinterpret `source` as an executable recipe or create a third inventory.

Versions may be exact, bounded ranges, older or newer under a named relation.
Application version and distribution package version are not interchangeable.
The prototype's `numeric-triplet/v1` orders three integer components and rejects
package suffixes; it is deliberately not a universal SemVer/APT/RPM comparator.
Production profiles must define equivalence, incomparable versions, epochs,
suffixes, endpoint inclusion and units where applicable.

Acquisition route, package coordinates and final repository configuration are
independent refinements when relevant. A backend may internally use a private
cache, repository, offline artifact or prebuilt image under operator supply-chain
policy without author registration or experimental provenance collection.
If the author constrains that route or final repository, the constraint binds.
Software presence alone does not establish enrollment, readiness, invocation or
behavior; those use SEM-219, service, proposition and task owners.

Reuse governed concept authority and artifact/profile distribution contracts.
Required semantics bind an authority identifier, exact profile revision and
content identity; identical display labels do not merge namespaces. Identity
strings are inert, credential-free and case-sensitive unless the authority
defines normalization. No automatic remote resolution, plugin execution or
credential lookup occurs during parsing/comparison. Offline resolution uses
pinned local artifacts through existing trust controls; a digest is integrity,
not trust. Unknown bounded extensions may be exchanged opaquely with disclosed
limitations. An annotation may be ignored for execution only when explicitly
nonbinding; unsupported required meaning MUST stop semantic admission.

## 6. Lifecycle and observation demand

Authored intent is immutable during realization. A selected choice, delivered
state, capture fact and promoted author constraint have different authority.
Selection reports may honestly say “backend-selected”; they MUST NOT claim an
independent scanner measured that selection. Captures retain their actual source,
time, coverage, marking and limitations, including contradictions. Partial facts
can leave satisfaction unresolved. A promotion selects facts and creates a new
authored artifact with provenance; it does not overwrite the original or freeze
every incidental field. The finite model demonstrates scalar promotion and
possible-world assessment, not a production provenance envelope.

The lifecycle is `authored → admitted selection → attempted delivery → reported
delivery`, with failure at admission or delivery preserving authored intent.
Observation is a separately demanded branch of execution; it can support,
contradict or leave claims unresolved. Promotion is a new `authored` root with a
derivation link, never a backwards mutation. Cleanup/termination remains the
execution owner's responsibility even when no experimental output is selected.

Existing ADR-064 capture specs and ADR-066 planes own the policy. #1212 supplies
scoped correction; #341 owns task/run/study refinement, #340 augmentation
conformance and #342 source provenance. Do not put all these controls into nodes.

| Mode at a named scope | Meaning |
| --- | --- |
| No experimental demand | Select no experimental streams; absence of demand is not an explicit prohibition. |
| Explicit prohibition | Forbid the selected purpose/stream before collection, buffers, persistence and export. Descendants cannot override it. |
| Operational only | Permit required execution, reconciliation and cleanup inputs; no automatic experimental retention/export. |
| Inherit / no preference | Use the applicable outer or explicitly selected default policy, never capture-everything. |
| Selected | Name fields/streams, scope, timing/window, coverage and retention/export. |
| Exhaustive | All events within the explicitly named supported domain and finite bounds, with loss/coverage disclosure; not everything everywhere. |

Scope defaults resolve by specificity; explicit mandatory capture requirements
are conjoined separately and cannot be discarded by a weaker local preference.
The prototype models scoped defaults and monotone prohibitions, with a single
finite source window per invocation. It does not implement the full task/run
refinement algebra. Retention and export are independent selections. Operational
inputs conflicting with a prohibition cause admission failure; they are neither
secretly collected nor silently waived. Precise constraints do not choose strong
evidence, and rich measurements do not require concrete infrastructure.

The abstract example is exactly two counters with a directional mailbox link.
Each computer has increment, send and receive transitions; mailbox preconditions
govern admission. No OS, package, filesystem or packet network is necessary.
The same transitions execute with trace collection disabled, or with every
requested action recorded. This is an executable abstract model, not a claim of
equivalence to every concrete computer implementation.

## 7. Compatibility and adoption decision

Public syntax is deliberately unselected until the executable proposal is
reviewed. Ordinary scalar literals should remain concise exact constraints;
reusable scopes/profiles should avoid wrappers around every scalar. The eventual
syntax must pass the same examples and round-trip authored provenance.

Production adoption MUST negotiate an explicit new semantic/authoring revision
and profile identity across parser, compiled authority, planner/direct submission,
backend offer and reports. No new published contract ID is allocated here.
Legacy omitted `realization`, `unspecified`, sentinel classification, APT v1,
profile guards, universal envelopes and corroboration keep their current meaning.
Migration must explicitly reconcile the registered-concern/closed-default and
“complete enforcement” clauses in the existing SEM-218 formal spec, and the
sentinel/profile-guard clauses in `specs/sdl/runtime-inventory.md`. Their current
ACTIVE status is not evidence of the new semantics.

The migration review must provide accepted ADR amendments/pins or a superseding
decision, published schema ledgers and generator parity, old/new positive and
negative fixtures, descendant-preserving compiler/runtime tests, and honest
validation-basis disclosures. A schema-only consumer may validate structure but
cannot claim unsupported semantic comparison. This issue supplies the design
contract; it does not claim those production migrations are complete.
