# IFC profile variability and publication

Semantic amendment: `ifc-profile-variability/rev1`, owned by SEM-233 and
SEM-235, issue #1354 and [ADR-114](../../../docs/decisions/adrs/adr-114-ifc-profile-variability-and-publication.md).
This defines publication and support obligations. It registers no new portable
profile, authoring syntax, provider protocol or runtime behavior. The original
`sem-233/rev1`, `sem-235/rev1` and their published artifacts retain their meaning.

## IFC-01 — Intent, meaning and realization

| Boundary | Required information and authority |
| --- | --- |
| Authored requirement | Independent confidentiality owners/clauses, allowed audiences and destinations, possible writers and integrity obligations, required release distinctions, sources/flows/sinks, memory scope, minimum guarantees and admissible limitations. An exact governed profile/policy reference may supply these; an author assertion grants no release authority. |
| Published semantic profile | Exact carrier and encoding, token meaning, order, conservative join, source/default and sink relations, release and non-influence relations, memory scope, unknown behavior, finite bounds and claim limits. |
| Backend/operator configuration | Installed implementation and configuration identity, admitted principal/source/sink bindings, instrumentation, effective coverage, resources, willingness and independently resolved realization evidence. These instantiate published relations; they cannot redefine them. |

Keep semantic identity, profile ID/revision/digest, policy, schema content,
provider protocol, implementation and configuration pins distinct. A role,
display name, credential, token prefix or participant identity alone does not
identify an obligation owner or prove its release authority. Resolve that
relation through admitted principal and policy context.

The chosen variability is governed publication of closed finite profiles.
It is sufficient for a fixed finite set of owner-qualified obligations without
a new policy language. Backend bindings may vary concrete principals and sinks
only where the published relation already permits those bindings. They may not
silently turn a generic token into a new owner algebra.

This amendment introduces no parameterized owner syntax. Repeated deployment
needs may justify bounded typed owner parameters in a later publication, but
that decision must specify admitted identity scope, canonical binding identity,
finite bounds, authority, validation and every consumer. Arbitrary/unbounded
runtime owners, scenario-selected code, plugin discovery and executable profile
content are unsupported. A new owner outside a published universe requires a
new governed publication or a separately justified parameter contract.

## IFC-02 — Distinctions that an encoding must preserve

For security, retain `P(C) × P(I)` and componentwise union. An obligation names
a revisioned clause, including its owner and independently scoped release
relation where applicable. Owner A's confidentiality clause permits Alice and
Bob; B's permits Bob and Carol. A combination retains `{C_A, C_B}`: only Bob
satisfies both clauses. Joining obligations intersects acceptable audiences;
it never unions them. Equal current reader sets do not make independently
releasable owners equivalent.

Likewise, `{I_A, I_B}` records independent unresolved integrity obligations
from two possible influences. Endorsing A's contribution leaves `I_B` and
both influence histories. A permissive observation sink may accept known
untrusted B influence without endorsement; a later action sink still evaluates
that influence against its own requirements. Unknown source resolution is
never known untrusted input or a public/trusted bottom label.

An encoding is adequate for an authored requirement only if it preserves the
required distinctions through source resolution, derivation, independent
release, memory and every required sink. All encoded permits must respect the
authored prohibitions, and all required functional distinctions must remain
realizable. A conservative refusal of every flow does not satisfy a requirement
that also requires selective authorized sharing.

Collapsing `C_A` and `C_B` into `restricted` cannot directly represent independent
owner release. Independently trusted contextual policy/provenance can impose
additional restrictions, but an exact support claim must demonstrate the full
encoding and release relation. Owner names in audit text or a backend-private
convention are insufficient. Admitted over-restriction may satisfy a narrower
requirement; it is neither exact expressiveness nor a license to discard a
functional obligation. A token cannot be repurposed against its published meaning.

SEM-235 domains in general keep MPC-04's partial order and total conservative
join. They need not be powersets or satisfy an additional least-upper-bound
theorem. This security specialization does not narrow those other domains.

## IFC-03 — Propagation and release

Every opaque summary, parse, redaction, trusted edit, argument/control choice,
retained memory, shared state, handoff and participant/episode crossing carries
the conservative join of every possible input. Missing coverage is unresolved,
not an empty input set. Exclusion needs the published non-influence relation
and its evidence. All historical labels and source/influence refs are immutable.

Declassification discharges only named confidentiality obligations;
endorsement discharges only named integrity obligations. Independently trusted
resolution must establish authority over **each** discharged obligation,
including every affected owner's clause. A grant for A does not cover B.
Approval, authentication, admission, trusted editing and monitor advice imply
neither operation. Both operations bind source and fresh result identity,
unchanged coordinate, exact profile/policy revision, sink/destination/audience,
authority, state cut and evidence. Provenance remains after discharge.

This is the semantic discharge relation. The current wire endorsement carrier
requires nonempty source-to-result token replacements. An owner-aware contract
must publish and verify how its replacements represent discharge while retaining
remaining obligations and writer provenance, or publish a distinct supported
carrier. The existing `integrity:endorsed` token does not mean that all owners
have endorsed every influence. This amendment does not change that carrier.

## IFC-04 — Admission and negotiation

Reuse [CA-01–CA-04](control-applicability-and-evaluation.md), API-407 effective
support and API-424 bindings; do not create a competing strength rank.

At apparatus admission and the relevant exact cut, establish in order:

1. Resolve the authored requirement and every mandatory obligation independently
   of provider responses. Proven inapplicability, absence and unresolved
   coverage retain their different meanings.
2. Resolve the exact published profile/encoding and all supported readers.
   Establish IFC-02 expressibility, source/default semantics and IFC-03 release
   authority. Unknown identities, tokens, revisions, mappings or ambiguous
   interpretations are unsupported, regardless of schema validity.
3. Resolve installed and effective realization for the required sources,
   explicit data/control paths, memory/crossing scope, sinks, release operations,
   finite bounds and evidence. A declaration, configuration digest, method name
   or generic modular-control feature is insufficient.
4. Apply CA-04 satisfaction to that coverage, guarantee, admissible loss and
   evidence. Record required, declared, installed, effective and admitted
   guarantees and limitations separately. Incomparable or unknown evidence
   cannot satisfy an obligation. Bounded support is admissible only when the
   authored requirement already permits those precise bounds.

Failure to express a requirement and failure to realize an expressible one are
distinct unsupported reasons. Neither is an ordinary policy denial inside a
supported profile. All prevent the affected mandatory release. A supported
policy may separately deny a particular flow. Optional advice cannot authorize
a mandatory IFC operation or hide missing coverage.

## IFC-05 — Admitted strength and execution weakening

An admitted bounded guarantee is the guarantee the run promised, within its
authored constraints. It is not an unexpected downgrade from an implicitly
perfect implementation. Conversely, a later loss of promised coverage,
enforcement, authority, freshness or evidence is weakening/failure even if an
earlier minimum requirement would still have accepted the reduced capability.
It must be recorded; it cannot silently redefine the admitted binding.

Before each affected external effect or disclosure, revalidate the exact
binding, current cut and effective guarantees with all incumbent gates. Missing
required evidence, unsupported binding, stale cut or unaccepted weakening
prevents release. Evaluate and commit through the existing atomic transition
before dispatch; committed intent is not proof of external application.

A separately authorized new requirement/profile binding at a new cut may
accept different limits only if every remaining owner and mandatory obligation
is satisfied. Downgrade authorization alone is not satisfaction. Replacing a
provider, configuration or profile does not reinterpret old decisions, erase
memory or authorize replay. Preserve CA-01–CA-09's dependency closure, advice
limits, scoped state, phase-independent parent decisions, independent effect
authority and finite causal budgets.

## IFC-06 — Governed publication and exact present limits

A new finite profile publication must include its full IFC-01 contract,
separating cases and bounds, conservative propagation and release evidence,
semantic identity, compatibility/migration rules and claim limits. Portable
adoption additionally needs coherent closed models, schemas, fixtures,
allowlisted loaders, modular fact/selection dispatch, trusted context and
per-obligation authority validation, capability negotiation, runtime/history
readers and conformance. Use ADR-009/061's existing publication ledger,
`schema_bundle()` parity and packaged corpus. A new JSON file or relaxed digest
check alone is insufficient. Stable breaking contracts require a new contract
identity; draft mutability never permits silent semantic reinterpretation.

| Surface at the #1354 design cut | Exact supported meaning and limit |
| --- | --- |
| General SEM-233 algebra | Finite owner-relative clauses are expressible in principle; synthetic models do not publish portable profiles. |
| `participant-boundary-flow-policy-v1@rev1` | Exactly `confidentiality:restricted`, `confidentiality:unknown`; and `integrity:endorsed`, `integrity:unknown`, `integrity:untrusted`. No independent owner tokens or owner parameters. Unknown is unresolved, never a spare owner slot. |
| Profile loader/model | Exact allowlisted ID/revision/digest and fixed semantic authority; no latest fallback. The schema's maximum 128 entries per coordinate is a shape bound, not extensibility authorization. |
| Modular profile/fact consumers | Closed security and teaching revision-1 cases. `teaching-influence/rev1` has coached-hint/worked-example tokens and no confidentiality, integrity or release claim. A generic reference cannot add a domain. |
| Release contracts | Scoped contextual release validation and token replacement; no published generic owner-token grant carrier. A new owner claim needs explicit per-obligation authority correspondence. |
| Support composition | Current v1 rejects non-exact effective support. CA-04 and IFC-04 define semantic obligations for future adoption; this delivery does not make v1 accept bounded support. |
| Runtime/backend claims | Depend on the exact implemented profile and independently evidenced coverage. No new owner-aware realization, universal noninterference, covert-channel, opaque-internal or backend-equivalence claim is established here. |

Thus the worked independent-owner cases require a new governed finite profile
and corresponding consumers for direct portable representation; they remain
unsupported by the current security vocabulary. A concrete contextual encoding
may be assessed under IFC-02, but none is certified by this delivery. Arbitrary
cross-profile comparison and automatic conversion remain unsupported.

## IFC-07 — Migration and evidence

The [migration contract](../../../docs/migration/ifc-profile-variability.md)
governs source/target pins, mappings, authority, loss, retained memory, pending
work and mixed-revision readers. Unknown old owners cannot be reconstructed
from coarse labels. New-cut evaluation never rewrites a historical release.

[Worked cases and verification](../../../docs/research/ifc-profile-variability/cases.md)
separate a finite design projection, real incumbent parser/governance checks
and required future consumer evidence. No finite model or ACTIVE semantic
requirement status certifies an installed provider, end-to-end mediation,
durable recovery, adversarial robustness or general formal proof.
