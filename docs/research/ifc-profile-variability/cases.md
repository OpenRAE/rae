# IFC profile variability: cases and evidence

This is the bounded evidence record for [ADR-113](../../decisions/adrs/adr-113-ifc-profile-variability-and-publication.md)
and [IFC-01–IFC-07](../../../specs/formal/participant-semantics/ifc-profile-variability.md).
The examples use synthetic owners and references, not proposed SDL syntax or
new registered profile artifacts.

## Independent owners

A's confidentiality policy admits Alice/Bob; B's admits Bob/Carol. A derived
summary has both obligations. Its confidentiality outcomes are:

| Reader | A's clause | B's clause | Joined summary |
| --- | --- | --- | --- |
| Alice | satisfied | unsatisfied | deny |
| Bob | satisfied | satisfied | permit if every other gate passes |
| Carol | unsatisfied | satisfied | deny |

At an exact sink/cut, A may authorize a fresh derived result discharging A's
clause. B's remains, so Carol can then satisfy confidentiality while Alice
cannot. A cannot discharge B's clause. If both initially name the same reader
set, they still remain distinct because A and B may release independently.
Mapping both to one `restricted` token either loses that distinction or blocks
sharing the authored requirement demands. The current artifact does not
directly support this case; a new finite publication and coordinated consumers
are needed. This is not evidence that every contextual encoding is impossible.

For integrity, independent possible influences create `{I_A, I_B}`. A's
endorsement of its contribution leaves `I_B`; an action requiring no unresolved
integrity obligations still denies. A deliberately permissive observation
policy can accept known B influence without endorsement, but that observation
does not delete B's influence from a later proposal. Confidentiality and writer
provenance remain unchanged. The model's discharge is semantic: the current
wire replacement carrier needs the explicit correspondence described by IFC-03
before supporting an owner-aware publication.

## Support and failure cases

| Case | Expected decision and evidence |
| --- | --- |
| Two independent owners mapped to distinct known tokens in each coordinate | Expressible in the synthetic finite profile; still requires complete realization evidence. |
| Missing mapping, duplicate owner binding, collapsed owners, unknown token or unresolved token used as an owner | Unsupported expression. An unresolved token is not extra expressiveness. |
| Owner token added to the real v1 JSON | Shape-valid but rejected by exact published-profile validation. The original profile remains loadable and unchanged. |
| Complete encoding but missing source, memory path or required sink instrumentation | Unsupported realization. Profile membership cannot replace coverage. |
| Evidenced bounded explicit-boundary guarantee admitted by the requirement | Admissible semantic case; current v1 composition still rejects non-exact support. No runtime adoption is claimed. |
| Requirement demands an additional guarantee that the realization lacks | Refuse admission, regardless of downgrade authority. |
| Run admitted additional guarantees, then loses one while still meeting the earlier floor | Record weakened and block affected release; do not silently lower the promise. |
| Profile/configuration changes or evidence becomes unresolved | Unsupported current binding; independently admit a new binding at a new cut. |
| A's grant used for B, another source/profile, sink or cut | Refuse release; no obligation or history is rewritten. |
| Opaque combination, retained memory, handoff or episode change | Preserve both coordinates and provenance; unknown coverage never permits a sink. |

The finite model uses independently trusted coverage and grants and a set of
comparable synthetic guarantee facts. It does not define a universal ordering
for arbitrary backend limitations or solve general contextual encodings. Its
singleton-token encoding fragment requires independent release, so mappings
must distinguish each required owner. Finiteness alone places no one-owner
limit on the SEM-233 algebra.

## Verification and clause map

`implementations/python/tests/ifc_profile_variability_model.py` reuses the
incumbent SEM-233 finite model for derivation, sink conjunction, coordinate
rewrites and immutable provenance. It adds a finite expression/admission check,
admitted-versus-observed comparison and scoped grants. The companion
`test_issue_1354_ifc_profile_variability.py` drives the separating cases above
and the actual published profile model/schema. These are behavioral checks,
not assertions that prose contains its own terminology.

`test_issue_1354_governance.py` exercises the real requirement ownership and
issue-scope evaluators, including refusal to treat runtime implementation as
SEM-235 semantic-publication work. Its tests were observed failing before the
new exact-path ownership/scope data was added. The semantic tests were observed
failing before their finite interpretation existed; additional source/profile
grant cases exposed the missing grant binding before its repair.

| Acceptance/requirement clause | Satisfying artifact and evidence |
| --- | --- |
| Issue: authored/profile/backend distinctions and owner-qualified cases | IFC-01–02; owner encoding, audience intersection and selective release tests. |
| Issue: unsupported expression/realization and admitted strength versus weakening | IFC-04–05 and support tests; CA-04 remains the canonical satisfaction relation. |
| Issue: conservative propagation, independent coordinates, release authority and provenance | IFC-02–03; scoped grant, endorsement, retained-memory tests and incumbent SEM-233 behavioral tests. |
| Issue: accepted decision, exact limits, requirement/ADR amendments and migration | ADR-113, IFC-06–07, SEM-233/235 and ADR-101/108 amendments; actual profile rejection, ownership/scope and ADR pin checks. |
| SEM-233: independent coordinates, propagation, authority distinctions and final-sink contract | Incumbent adversarial-flow-control.md and its existing contract/runtime links remain authoritative; IFC-01–07 clarify expressibility and publication without changing those implementations. |
| SEM-235: revisioned domains, joins, defaults, memory, release and finite composition | Incumbent MPC-01–MPC-15 remain; IFC-01–03/06 specialize publication limits and retain non-security domains. |
| SEM-235: coverage, dependencies, advice, bounded support, atomic state and effects | CA-01–CA-09 remain; IFC-04–05 explicitly compose with them. Existing #1352 finite witnesses exercise those retained clauses; no runtime fulfillment upgrade. |
| SEM-235: fresh transformations/injects, visibility, provenance, admission and budgets | Incumbent MPC-09–MPC-14 and CA-05–CA-09 remain; IFC-05/07 and migration preserve them across profile changes. |

Local verification uses only the new focused modules, relevant existing
SEM-233/#1352 modules and changed-artifact policy checks. Full suites remain in
CI. New backend adoption still requires the real consumer evidence listed in
the migration contract: the finite model proves no live mediation, portable
owner-aware reader, arbitrary noninterference, durable atomicity, recovery,
intentional-subversion robustness or installed backend capability.
