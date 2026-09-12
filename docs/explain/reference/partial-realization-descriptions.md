# Partial realization descriptions

A description reports what a producer actually knows. It can carry a selected
family without a release, or several components with different amounts of
detail. It never fills deployment defaults or changes the original request.

Existing experiment evidence records and realized-form disclosures accept an
optional `typed_description`. Each fact has a semantic pointer, knowledge state
and an optional recursive value. Observer, version, time, window, achieved basis
and limitations accompany the description; individual facts may override their
provenance. `known-absent` means positive knowledge of absence, while
`not-observed` and `withheld` provide no value. Collection coverage names its
universe and profile separately from author collection closure.

The Python reference API exposes `TypedRealizationDescriptionModel` from
`raes_contracts.contracts`. `parse_realization_description` in
`raes_contracts.description_reporting` admits bounded JSON without duplicate
members. Private profile bindings retain exact coordinates and inert values;
`admit_description_profiles` requires an explicit offline context and policy.
Opaque acceptance does not enable semantic comparison.

`assess_realization_description` in `raes_contracts.description_projection`
compares against the original constraint document and its digest. Known facts
can disprove exact requirements even when the report is partial. Whole-object
conformance requires compatible complete coverage. Conflicting observations are
retained during interchange and diagnosed during comparison; observations from
different windows cannot silently become one state. Overlapping partial record
projections require explicit reconciliation.

`promote_description` in `raes_contracts.description_promotion` takes selected
known scalar fact IDs, the original constraints, an actor, decision ID, time and
new target identity/version. It returns a new document and transformation
record after checked composition and refinement. It performs no authoring write
or execution. The original document and unselected facts remain intact.

Existing observation demand selectors reach describers before they acquire
detail. Projection and protection run before retention. A selected structured
fact containing an excluded descendant is omitted as a whole, preserving the
exclusion without inventing a partial value. Producers can supply separate leaf
facts when callers need finer selection. Backend selection implementations and
scenario content belong to their downstream owners; RAE supplies these shared
contracts and conformance checks.

For profile data, the owner address must stay within the enclosing fact and the
owner's contract/phase must match the evidence or run carrier. Nested profile
provenance must agree with the fact's basis. Observed reference IDs must join the
reference accepted by the outer evidence verifier; profile carriage alone does
not verify them. The reporting API verifies an unqualified evidence-record ID,
so retained claims cannot add a different kind, version, digest or path. It
checks each retained fact's or coverage item's effective provenance; an
overridden default does not become an additional evidence claim.
Exhaustive description requests additionally require matching
complete coverage for the selected scope and profile. Partial coverage remains
reportable under selected demand.
