# Participant-control concept placement

Placement revision: `participant-control-concepts/rev1`, for
[`sem-235/rev1`](../formal/participant-semantics/modular-participant-control.md).
Authority: ADR-012, ADR-108, GOV-917–922 and SEM-235.

The canonical [concept-family catalog](../../contracts/concept-authority/concept-families-v1.json)
continues to own family identities. This publication maps semantic terms to
existing families and owners; it creates no catalog family, reference model,
controlled wire vocabulary or new manifest binding scope.

| Concept | Placement and exact meaning |
| --- | --- |
| Profile/mechanism selection and implementation identity | `apparatus-declarations`: exact selected/effective bindings, capability and limitations under MPC-01/13. |
| IFC carrier, order, join and policy relation | Formal relation definitions under MPC-04/05. Claims about their satisfaction use `behavioral-relations`; the labels are not themselves noninterference claims or cyber-domain objects. |
| Participant identity and affected cyber objects | Existing `identities`, `assets`, `tools-and-artifacts` and their narrower bindings; a control mechanism does not redefine them. |
| Inject, transformed proposal, handoff and lifecycle occurrence | `actions-and-events` for occurrences; DSL-111/142, API-409/423 and RUN-310 retain their typed meanings. |
| Participant episode and memory scope | `episodes` for identity/lifecycle, SEM-230 for memory and prior delivered knowledge. Reset does not remove provenance or causal budgets. |
| Experimental treatment influence | `tasks-runs-studies` for experimental intent and `provenance-and-evidence` for recorded influence/derivation. The teaching domain is a native RAES semantic construction, not an extension to UCO or SEM-233. |
| Resolution, conflict, admission and realization evidence | `provenance-and-evidence` for records; `realization-and-disclosure` for effective support/loss. A record does not make its subject a claim of successful execution. |
| Noninterference or behavioral comparison | `behavioral-relations`, retaining the existing `policy-noninterference` catalog relation and exact SEM-230/233 quantifiers. Modular composition supplies no new equivalence relation. |

Participant-control profiles are distinct from
[shared semantic interoperability profiles](semantic-profiles.md),
[SDL extension-profile selections](../sdl/profile-selections.md), and SEM-234
backend allocation profiles. Reuse their revision discipline, without treating
their identifiers as interchangeable or as executable code selection.

API-424 publishes any required portable fields and their governed scopes.
Until then, a semantic term does not authorize an empty scope or placeholder
wire schema. New domains require their own published algebra, closed carrier,
source/sink rules, memory/release relations, fixtures and contract support.
An arbitrary label map, advisory score or provider callback cannot extend
semantic authority.
