# Migration Notes

This note records the major documentation and repository-structure moves that
established the current layout. The paths below describe historical moves, not
current uncertainty about where authoritative material lives.

The current project identity migration is recorded separately in
[RAES Identity Cutover](raes-rename.md). That note records the final hard
cutover across repository-owned live surfaces and the exact historical-record
boundary.

The explicit opt-in from fixed-cadence autonomous participant execution to the
governed activity profile is documented in
[Autonomous Execution V2 Migration](autonomous-execution-v2.md).

Scoped participant, tenant, shared-service, and fleet resource governance is
an explicit v3 opt-in documented in
[Autonomous Execution V3 Migration](autonomous-execution-v3.md).

Backends that declare autonomous participant execution must adopt the portable
execution-service surface described in
[Participant Execution Control Migration](participant-execution-control.md).

The staged legacy, opt-in, and required adoption of participant
information-flow control is documented in
[Participant Information-Flow Control Migration](participant-information-flow-control.md).

The fail-closed adoption of coherent backend capture offers and content-backed
evidence satisfaction is documented in
[Required Capture Admission Migration](required-capture-admission.md).

Producer and reader obligations for the published mixed-backend execution
binding and stage-report contracts are documented in
[Mixed-Backend Execution Contracts Migration](mixed-backend-execution.md).

Participant-scoped tool-affordance bindings, which let one behavior
specification serve as a reusable tool profile, are documented in
[Participant tool profiles migration](participant-tool-profiles.md).

The explicit conversion of a legacy fixed-coordinate `mixed_control`
declaration to a rev1 finite script is documented in
[Mixed-Control Finite-Script Conversion](mixed-control-finite-script-conversion.md).
The [reusable mixed-control adoption contract](reusable-mixed-control.md)
remains the producer and reader boundary.

The removal of the bundled reference and libvirt backends, and the move of
concrete realization to backend distributions such as LilRAE, is documented in
[Concrete Backends Migration](concrete-backends.md).

Backend-owned participant-opacity harnesses supply reported transcripts and
backend readback as described in
[Participant-Opacity Observed Evidence Migration](participant-opacity-observed-evidence.md).

The reorganization moved existing material into the current long-term buckets:

- root `schemas/` -> `contracts/schemas/`
- root `conformance/fixtures` and `conformance/profiles` -> `contracts/`
- `docs/adrs/` -> `docs/decisions/adrs/`
- `docs/sdl/` -> `docs/explain/sdl/`
- Python implementation code and tests -> `implementations/python/`

The authoritative locations listed above are the intended home for current
work. Remaining inconsistencies should be recorded as issues, ADR amendments,
or contract/spec changes rather than described here as open-ended migration
work.

The working order for reconciling the current implementation to that layout is
captured in [ADR-010](../decisions/adrs/adr-010-repository-realignment-order-and-compatibility-policy.md).

[Progressive SDL semantics migration](progressive-semantics.md) covers the breaking
cutover, source-bound adoption and classification binding coordination.

[Reference eligibility migration](reference-eligibility.md) lists the reference
fields whose eligible declaration kinds narrowed and how to rewrite them.

[Participant tool support migration](participant-tool-support.md) covers processor
and backend declarations, profile semantic revisions, capacity, and admission.
