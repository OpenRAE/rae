<a id="ifc-profile-variability-migration"></a>

# Information-flow profile compatibility reference

This reference applies to Python RAES 11.0.2.
The source is the original security profile and its historical meaning.
The target is `participant-owner-flow-policy-v1@rev1` with `owner-ifc/rev1` under provider/v2.
No automatic converter or deprecation window is supplied.

[ADR-114](../decisions/adrs/adr-114-ifc-profile-variability-and-publication.md)
and [IFC-01–IFC-07](../../specs/formal/participant-semantics/ifc-profile-variability.md) own the adoption rules.
Issue #1370 adds the [finite owner publication](../explain/reference/owner-qualified-ifc.md).

## Finite publication adoption (#1370)

Before use, negotiate the new profile ID, revision, and digest.
Negotiate the updated draft flow-relation schema and API-424/v2 schema-content pins too.
Legacy provider/v1 rejects the new profile and fact domain.
Old profile bytes and meanings stay unchanged.
Mixed archives route by exact identity.

The updated flow reader permits at most 256 records in each graph collection.
Larger historical graphs need their original supported reader.
Never truncate them to pass the new bound.

The v2 field `admitted_support` keeps independently admitted support for each obligation.
Historical v2 serialization omits empty snapshots.
That omission preserves original selection digests.
New owner obligations need populated snapshots.
A fresh-cut assessment cannot silently replace an admitted promise.
Do not invent promises or owners for historical obligations.

Changing profile, installation, configuration, or constraint meaning needs admission at a new cut.
Keep old labels, memory, releases, and source/writer provenance.
Keep pending effect identities, receipts, and consumed budgets too.

Deriving owner A/B values from coarse restricted labels needs independent historical evidence.
It also needs a separately authorized published mapping.
No automatic converter supplies that mapping.
New authority never replays old effects.

This owner-profile publication does not implement external release effects.
An unexecuted release intent is not an applied result.
Other supported v2 effects have a separate [support reference](../explain/reference/revised-control-semantics.md).

## Interpretation and historical data

`ifc-profile-variability/rev1` names the amendment.
It is not `sem-233/rev1` or `sem-235/rev1`.
Keep profile revisions/digests and wire/protocol versions separate too.
New prose, a backend name, or generic modular-control capability cannot establish adoption.

Negotiate exact supported meanings across producer, resolver, and provider.
Include runtime, store, snapshot, and downstream readers.
Each input has the following boundary.

### Legacy profile and relation

Keep the exact original bytes and digest.
Keep token meaning, source context, and release interpretation.
Use the legacy reader with its stated limits.

### New owner-aware publication

Old readers reject it.
New readers need exact publication, schema/content, and semantic support.
They need independently trusted bindings and release authority for each obligation.

### Mixed-revision archive

Route each record through its exact supported reader.
Keep its order and evidence.
Unknown or ambiguous meaning is unsupported/unverifiable.
It cannot fall back to the latest reader.

### Coarse restricted values

Keep a coarse `restricted` value when owner evidence is absent.
Do not invent A/B obligations or map it to public/bottom.
Do not claim an owner-aware conversion.

### Pending effects and retained memory

Keep original identity, labels, provenance, cut, release, and outcome records after profile replacement.
The new-cut rules below apply before any new action.

Discharging an obligation never erases source or possible-writer provenance.
Historical `integrity:endorsed` keeps its original profile and release meaning.
It cannot become universal or per-owner endorsement.
Do not recompute old permits, mutate labels, or replay effects to claim new conformance.

## Explicit conversion

A future published mapping must pin source and target profile, semantics, and schema.
It must name exact source/result identities and transformation authority.
It must name affected coordinates, scope, losses, and evidence.
It must establish sound order and conservative propagation.
It must establish soundness for every required sink and independent release.
Keep author-required functional distinctions as well as prohibition safety.
Cross-profile joins or comparisons are unsupported without that relation.

Independent historical owner evidence may support a new derived value through an authorized mapping.
It cannot authorize rewriting the source.
Incomplete evidence keeps the result unsupported/unverifiable.
An author may explicitly select a different requirement.
That choice is a semantic change with disclosed limits, not lossless migration.
Authority cannot implicitly waive another owner's unresolved obligation.

For endorsement, reconcile semantic discharge with the wire's source-to-result token replacement rule.
A future carrier or mapping must keep unreleased owners and immutable writer provenance.
It must prove exact authority over each changed obligation.
Renaming `endorsed` or adding a legacy token cannot establish that correspondence.

## Live bindings, memory and pending work

Use the [applicability migration contract](control-applicability-and-evaluation.md) and existing operation lifecycle.
Stop new affected admission.
Finish or explicitly reconcile pending claims.
Then admit a supported binding at a new cut.
Never change profile meaning inside a live evaluation.

Revalidate required coverage and guarantees before effects and disclosure.
A migration flag cannot bypass current v1's rejection of non-exact support.
Retained participant memory and shared/provider state keep every possible input obligation.
Migration needs exact old/new state scopes and versions.
It also needs configuration/authority bindings and supported atomicity.
Episode/controller changes and provider replacement do not erase dependencies.
Unknown migration coverage prevents the affected release.
This holds even when a new profile accepts the known tokens.

Keep effect identities, receipts, history heads, causal roots, and consumed budgets.
A new profile is not a new retry key.
A prior permit or release grants no authority at a new sink or cut.
Unknown external effects stay indeterminate until the existing owner/readback and recovery policy resolve them.
Admission or commit does not prove application.
A retained record cannot authorize automatic resumption or repeated dispatch.

## Publication owners and adoption evidence

SEM-233 owns the security invariant and owner-specific release meaning.
SEM-235 owns governed domain publication and composition.
API-424 and incumbent flow-contract owners must coordinate closed carriers and protocol consumers.
They must use API-407 support evidence.
RUN-320 owns modular orchestration adoption.
Concrete backend instrumentation and assurance need separate evidence.
This amendment does not change those runtime fulfillment statuses.

Use ADR-009/061 publication records, fixtures, generated-schema parity, and packaged resources.
Keep stable-contract compatibility.
Record permitted draft changes without changing historical meaning silently.
Real-consumer evidence is required for:

- Unknown profile and token rejection.
- Shape-valid but unpublished artifacts.
- Two-owner selective declassification and endorsement.
- Missing source, sink, or control-flow coverage.
- Exceeded bounds and stale cuts.
- Unexpected weakening.
- Mixed-revision replay and pending-effect reconciliation.

Denied live paths must show zero prohibited calls or disclosures.
Their durable outcomes must be truthful.
Finite #1354 witnesses do not establish those live claims.

## Continue

Use [revised-control migration](revised-control.md) to replace a live binding safely.
Read [owner-qualified IFC](../explain/reference/owner-qualified-ifc.md) for the finite publication boundary.
