# Finite owner-qualified IFC

Issue #1370 implements [ADR-114](../../decisions/adrs/adr-114-ifc-profile-variability-and-publication.md)
through the inert publication `participant-owner-flow-policy-v1@rev1`, with
RFC 8785 digest
`sha256:0a7872665ca0cf435bddcd0d6a39b89d20a8f5f6a5e8ca8abdf1d4f77da774df`.
The artifact resides alongside the historical security profile in
`contracts/profiles/participant-boundary-flow-policy/`. Both use the existing
bounded, duplicate-rejecting loader and packaged corpus. Revision/digest
mismatches never fall back to another profile.

## Published meaning

| Owner | Confidentiality clause | Permitted reader references | Integrity replacement |
| --- | --- | --- | --- |
| `owner:a` | `confidentiality:owner-a` | `reader:alice`, `reader:bob` | `integrity:owner-a:untrusted` → `integrity:owner-a:endorsed` |
| `owner:b` | `confidentiality:owner-b` | `reader:bob`, `reader:carol` | `integrity:owner-b:untrusted` → `integrity:owner-b:endorsed` |

These fixed semantic references are neither owner parameters nor authenticated
usernames. Trusted source/principal/sink/grant resolution binds deployment
identities within the published relation. Names, roles, credentials, token
prefixes and provider responses establish none of that trust. Additional owners,
clauses or reader relations require another governed publication and consumers.
Editing this artifact fails its digest check. The original security profile's
bytes, digest and meanings remain unchanged; there is no new SDL syntax or
executable policy language.

Labels keep independent confidentiality/integrity sets. The incumbent SEM-233
derivation unions every possible input's obligations, provenance and influences.
Both confidentiality clauses together permit Bob, not the union of audiences.
If a deployment restricts current audiences to Bob for both clauses, A and B
still remain independently releasable. Opaque/control inputs, memory and handoff
retain both. The unknown tokens remain unresolved, never spare owners, known
untrusted input or bottom.

Declassification removes only the named confidentiality clause. Endorsement
replaces only one owner's untrusted token with that owner's endorsed token.
This is the explicit carrier correspondence for discharging that owner's
unresolved integrity obligation; other owners remain. Trusted-integrity sinks
accept endorsed markers, while an observation policy may explicitly accept
known untrusted markers. Neither operation nor observation erases writer
provenance or changes the other coordinate. Fresh result identities and
immutable lineage remain mandatory.

The incumbent release-authority coordinate is necessary. In addition, trusted
`ParticipantFlowObligationAuthorityCoordinate` entries must authorize **each**
discharged owner/clause and the digest of the complete release record. This binds
kind, source/result identities and labels, profile, policy/cut, authority,
sink/destination/audience and evidence. An A grant never releases B and cannot
be reused at another source/result, cut, profile or destination.

`ParticipantOwnerFlowSinkResolution` independently identifies all reader
principals in the exact sink audience and its integrity posture. Empty, unknown
or missing bindings fail closed. Every reader must satisfy every remaining
clause. The validator recomputes both coordinates before conjoining the existing
crossing, action-admission, capability and history-head gates. Relation graph
collections have a 256-record bound before traversal. Crossing carriers retain
the incumbent revision and/or digest identity, including runtime digest-only
subjects; neither identity may be missing.

## API-424 admission

The new profile requires provider/v2 and both profile-owned IFC fact obligations,
`ifc-owner-a` and `ifc-owner-b`. Their existing v2 obligation carries resolved,
installed `admitted_support` snapshots. Every applicable instance needs its exact
promise. Complete apparatus, total coverage, proven inapplicability and required
dependency closure remain API-424's incumbent carriers and trusted resolutions.

The closed v2-only fact domain `owner-ifc/rev1` names the exact profile, owning
SEM-233 relation, effective label, sink decision and disposition. Trusted context
checks these against the actual relation and exact crossing. Legacy/teaching
facts cannot discharge owner obligations. A supported sink denial remains deny;
unresolved/unsupported/stale facts are not successful required inputs. A provider
cannot certify its own disposition. Legacy provider/v1 rejects the new profile
and fact domain.

API-407 declarations, installed implementation/configuration, actual coverage,
constraint compatibility and evidence remain separate. Generic modular-control
support and profile membership certify no realization. The operator's existing
trusted support resolver must establish source/control-flow/memory/sink/release
coverage and constraints; missing evidence prevents affected backend calls and
disclosure.

Snapshots preserve promises above the author's minimum. A fresh-cut assessment
must retain declaration, installation, strength, constraint/limitation meanings
and all promised evidence. No ordering of opaque constraints is inferred.
Lost promises make composition weakened and block affected required invocation
even when CA-04 still accepts the original floor. Changed interpretation requires
explicit new admission; downgrade authority never waives another owner's clause.
Empty snapshots are omitted for historical v2 obligations, preserving their
original selection digests.

The explicitly selected SEM-233 final-sink adapter also consumes the new profile
through these same flow validators. Its trusted resolver still owns admitted
deployment coverage and current capability gates. Neither path selects scenario
code. A valid release relation is not proof of an external release effect:
v2 executable effect dispatch remains unsupported.

## Evidence and limits

The three `test_issue_1370_ifc_*` modules exercise real loaders, context/admission
consumers, joins, scoped grants, sink resolution, unknown-token rejection,
immutable publication, historical digests and admitted promises. Live runtime
tests show selective sharing calls the backend once; rejected sharing, missing
grants, untrusted integrity and lost promises cause zero prohibited calls.
Incumbent SEM-233 tests retain memory/handoff and final-gate evidence. Synthetic
resolvers and instrumented backends establish reference-consumer behavior, not
production instrumentation, universal noninterference, intentional-subversion
robustness or covert-channel control. All profile nonclaims remain.

Primary references consulted: Cornell's [DLM](https://www.cs.cornell.edu/jif/doc/jif-3.3.0/dlm.html)
and [selective downgrading](https://www.cs.cornell.edu/jif/doc/jif-3.3.0/language.html),
and the cited [Fides](https://arxiv.org/html/2505.23643v2) and
[CaMeL](https://arxiv.org/html/2503.18813v2) papers. They inform independent
coordinates, scoped authority and instrumentation/threat-model limits. This
finite RAES profile does not implement Jif's complete principal-relative DLM or
inherit those systems' guarantees.
