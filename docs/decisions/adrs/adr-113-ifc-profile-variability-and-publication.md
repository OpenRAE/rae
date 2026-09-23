# ADR-113: IFC Profile Variability and Publication

## Status

accepted

Acceptance takes effect when the delivery PR for
[#1354](https://github.com/OpenRAE/rae/issues/1354) merges. An unmerged copy is
proposed delivery state. This is a semantic decision, not new portable profile
support or runtime adoption.

## Date

2026-09-23

## Classification

Classification: FM3

Required artifacts: [IFC-01–IFC-07](../../../specs/formal/participant-semantics/ifc-profile-variability.md),
[worked cases and bounded evidence](../../research/ifc-profile-variability/cases.md),
[finite interpretation](../../../implementations/python/tests/ifc_profile_variability_model.py),
[behavioral witnesses](../../../implementations/python/tests/test_issue_1354_ifc_profile_variability.py),
[migration obligations](../../migration/ifc-profile-variability.md), and
SEM-233/SEM-235 amendments.

Waivers: the finite interpretation assumes trusted context and comparable
synthetic guarantee facts. It is not an installed engine, public negotiator,
wire reader, instrumentation proof or backend conformance result. No schema,
profile bytes, provider protocol or runtime implementation changes here.

## Context

The [preflight](../issue-1354-ifc-profile-variability-preflight.md) confirms that
SEM-233's product-powerset algebra already supports finite independent owner
obligations. The published digest-pinned security profile has a much smaller
fixed vocabulary. Shape-valid token additions do not pass publication
validation, and modular consumers recognize a closed profile/fact union.
Finiteness is not the problem; losing independent release distinctions is.

ADR-108 permits governed domains without a general interpreter. CA-04 already
defines requirement-relative support, while current v1 composition rejects
non-exact support. Neither a declaration nor acceptance of weaker capability
proves that the authored requirement is satisfied.

## Decision

Adopt `ifc-profile-variability/rev1` under SEM-233 and SEM-235. Authors specify
required owner/release distinctions, scope and guarantees, directly or through
exact governed references. Profiles publish their meaning; backend configuration
binds realizations without changing that meaning.

Use governed closed finite publication for additional justified distinctions.
Independent owners retain independent confidentiality and integrity obligations,
even with equal current audiences. Conservative joins, trusted authority for
every discharged obligation, fresh derived identities and immutable provenance
remain mandatory. Extensibility uses exact profile bindings and the existing
trusted source/sink/authority resolver seam. No owner-parameter syntax, policy
language or plugin facility is justified by these finite cases.

Require separate evidence for expressibility and realization, then apply CA-04
to the actual authored coverage and constraints. An admitted bounded guarantee
is legitimate where the requirement permits it; losing an admitted promise
during execution blocks the affected mandatory release and requires an explicit
new admission to change the promise. Authority to downgrade does not establish
satisfaction or remove another owner's obligation.

Publish exact current limits and migration obligations. Independent-owner
examples are semantic witnesses, not new registered profiles. Adding tokens
requires coherent release correspondence, contracts, readers, capability,
runtime and backend evidence before any operational claim. Preserve ADR-101's
security meanings, ADR-108's declared-world boundary and CA-01–CA-09.

## Alternatives Considered

- Collapse every owner into `restricted`: conservative blocking can be a
  disclosed limit, but cannot supply independently authorized selective sharing.
- Encode new meaning in backend configuration or audit names: cannot establish
  portable profile semantics, complete propagation or per-obligation authority.
- Add arbitrary labels, callbacks or a policy/plugin language: the finite cases
  need none; they would introduce interpretation and executable authority.
- Adopt owner parameters immediately: potentially useful for repeated finite
  deployments, but needs a concrete unmet case and a separate closed binding
  contract. This decision leaves that justified extension possible.
- Treat all bounded support as success, or every bounded guarantee as runtime
  failure: both ignore the requirement and the guarantee actually admitted.

## Consequences

The support boundary becomes reviewable: a valid requirement can be refused
because no profile expresses it, because no backend realizes it, or because
an admitted guarantee was lost. Supported policy denial remains a different
outcome. Historical records retain their original evidence and limitations.

The cost of new variability is governed publication and coordinated consumer
adoption. This decision neither certifies a contextual encoding of independent
owners under the legacy vocabulary nor broadens existing implementation claims.
