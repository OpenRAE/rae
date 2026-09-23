# IFC profile variability migration

This is the adoption contract for [ADR-114](../decisions/adrs/adr-114-ifc-profile-variability-and-publication.md)
and [IFC-01–IFC-07](../../specs/formal/participant-semantics/ifc-profile-variability.md).
It publishes no converter, schema, profile artifact or deprecation window.

## Interpretation and historical data

Keep the amendment identity `ifc-profile-variability/rev1` distinct from
`sem-233/rev1`, `sem-235/rev1`, profile revisions/digests and wire/protocol
versions. Do not infer adoption from new prose, a backend name or a generic
modular-control capability. Negotiate exact supported interpretations across
producer, resolver, provider, runtime, store, snapshot and downstream readers.

| Input | Required treatment |
| --- | --- |
| Legacy security profile and relation | Retain exact original bytes, digest, token meaning, source context and release interpretation. Use the legacy reader with its stated limitations. |
| New owner-aware publication | Old readers reject it. New readers require exact publication, schema/content and semantic support, independently trusted bindings and per-obligation release authority. |
| Mixed-revision archive | Route each record through its exact supported reader; retain order and evidence. Unknown or ambiguous interpretation is unsupported/unverifiable, not latest-version fallback. |
| Coarse `restricted` value without owner evidence | Preserve it. Do not invent A/B obligations, map it to public/bottom or claim an owner-aware conversion. |
| Pending effect or retained memory under a replaced profile | Preserve the original identity, labels, provenance, cut, release and outcome records; apply the new-cut rules below before any new action. |

Source and possible-writer provenance never disappears when an obligation is
discharged. Historical `integrity:endorsed` is interpreted by its original
profile and release record; it cannot become universal or per-owner endorsement.
Do not recompute historical permits, mutate labels or replay effects to make
an archive appear newly conforming.

## Explicit conversion

A future published mapping must name source and target profile/semantic/schema
pins, exact source/result identities, transformation authority, affected
coordinates, scope, losses and evidence. Establish that order and conservative
propagation, every required sink and independent release remain sound. Preserve
functional distinctions the author required, not only prohibition safety.
Cross-profile joins/comparisons are unsupported without that relation.

Independent historical owner evidence may support a new derived value through
an authorized mapping; it does not authorize rewriting the source. If evidence
is incomplete, retain unsupported/unverifiable status. An explicit new author
decision may choose a different requirement, but it is a semantic change with
disclosed limits, not a lossless migration. Authorization cannot waive another
owner's unresolved obligation implicitly.

For endorsement, reconcile the semantic discharge relation with the current
wire requirement for source-to-result token replacements. A future carrier or
mapping must preserve the unreleased owners and immutable writer provenance,
and prove exact authority over each changed obligation. Renaming `endorsed`
or adding a token to the legacy artifact does not provide that correspondence.

## Live bindings, memory and pending work

Reuse the [applicability migration contract](control-applicability-and-evaluation.md)
and existing operation lifecycle. Quiesce affected admission, finish or
explicitly reconcile pending claims, then admit a supported binding at a new
cut. Never swap profile interpretation inside a live evaluation. Revalidate
required coverage and guarantees before effects and disclosure; current v1's
non-exact support rejection cannot be bypassed by a migration flag.

Retained participant memory and shared/provider state retain every possible
input obligation. Migration needs exact old/new state scopes, versions,
configuration/authority bindings and supported atomicity. Episode/controller
change and provider replacement do not erase dependencies. Unknown migration
coverage prevents affected release, even if a new profile would otherwise
accept its known tokens.

Preserve effect identities, receipts, history heads, causal roots and consumed
budgets. A new profile is not a new retry key. A prior permit/release is not
authority at a new sink or cut. Indeterminate external effects remain
indeterminate until the existing owner/readback and recovery policy resolve
them; admission or commit is not evidence of application. Retaining a record
does not authorize automatic resumption or repeated dispatch.

## Publication owners and adoption evidence

SEM-233 owns the security invariant and owner-specific release meaning;
SEM-235 owns governed domain publication and composition. API-424 and the
incumbent flow-contract owners must coordinate closed carriers and protocol
consumers, using API-407 support evidence. RUN-320 owns modular orchestration
adoption; concrete backend instrumentation and assurance remain separately
evidenced. This issue changes none of those runtime fulfillment statuses.

Use ADR-009/061 publication records, fixtures, generated-schema parity and
packaged resources. Preserve stable-contract compatibility; record permitted
draft changes without silently changing historical interpretation. Required
real-consumer evidence includes unknown profile/token rejection, shape-valid
but unpublished artifacts, two-owner selective declassification and endorsement,
missing source/sink/control-flow coverage, bounds exceeded, stale cuts,
unexpected weakening, mixed-revision replay and pending-effect reconciliation.
Denied live paths must show zero prohibited calls/disclosures and truthful
durable outcomes. The finite #1354 witnesses do not establish those live claims.
