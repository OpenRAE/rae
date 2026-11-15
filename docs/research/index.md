# Research records and current questions

Use this entry to find design reasons and exact research evidence.
These records stay in the repository.
They are outside the hosted build and search.
The [public research entry](../public/research.md) gives the reader-facing route.

## Understand a design

These explanations give reasons and relationships.
Each issue and source revision defines a scope.
An accepted decision is a design choice.
It does not prove that code works or an experiment succeeded.

- [Modular participant control](modular-participant-control/index.md) explains the design recorded by accepted ADR-108.
- [Runtime control plane](runtime-control-plane/index.md) explains profiles, state authority, and recovery boundaries under ADR-104.
- [Execution architecture](execution-architecture/README.md) explains ADR-113 and separates local rechecks from earlier cloud observations.
- [Recursive partial descriptions](partial-description/index.md) links the accepted decision and its original finite design check.
- [Realization envelopes](realization-envelope/index.md) separates design rationale from normative semantics.
- [Scoring and reward scope](scoring-scope/index.md) explains the experiment and data-use boundary.
- [Experiment core](experiment-core/index.md) links design research and dated search records.
- [Participant information flow](participant-io-control/index.md) explains control and observation boundaries.

## Inspect exact evidence

These references keep observations, protocols, source pins, and claim limits.
Use their manifests and snapshots for exact identities.
Do not treat an old command as a supported current procedure.

| Reader question | Record and present applicability |
| --- | --- |
| What does the retained semantic corpus demonstrate? | [Formal semantic validation](formal-semantic-validation/index.md) links bounded results. Each snapshot names its source revision. |
| Which specification claims have retained evidence? | [Specification coverage](specification-coverage/index.md) links the protocol and recorded captures. A recorded release need not match current source. |
| How do compared languages differ? | [Related-work comparison](related-work-comparison/index.md) links frozen observations and scope-qualified analysis. It establishes no universal ranking. |
| Has researcher accessibility been demonstrated? | [Language evaluation](dsl-language-evaluation/index.md) links preregistered, not-started studies. A protocol is not an observed result. |
| What does the opacity proof establish? | [Participant opacity](participant-opacity/index.md) links the conditional theorem. It establishes no deployed runtime or backend property. |
| Where is the earlier crossing result? | [Participant bisimulation](participant-bisimulation/index.md) distinguishes historical evidence from currently available artifacts. |
| Which literature supports a claim? | [Primary research snapshots](primary/index.md) give citation metadata and verification status, not normative authority. |

## Investigate a current question

Can the published learning path support researchers without infrastructure expertise?
The [language-evaluation protocol](dsl-language-evaluation/index.md) defines populations, tasks, measures, and missing-data rules.
Its not-started snapshots contain no participant observations.
The next investigation must obey that protocol and its approval conditions.
A successful first-use exercise does not answer the research question.

Can one realization preserve a stated property across backends?
Start with [realization semantics](../../specs/formal/realization/README.md) and the [behavioral relation taxonomy](../../specs/formal/behavioral-relations/README.md).
Select a relation, source revision, and bounded evidence before making a comparison claim.
Parsing, schema validity, finite model checks, and native effects establish different facts.

## Check status and revision

Use the [ADR index](../decisions/adrs/README.md) for decision status and replacement links.
Use [requirements](../requirements/README.md) for statements, status, and delivery traceability.
Use the source commit and artifact digests in each capture, rather than its filename alone.
The [formal capture directory](formal-semantic-validation/captures/) contains branch capture manifests.

Each manifest binds a snapshot and analysis by digest.
The snapshot identifies the observed source state.
The [capture receipts](formal-semantic-validation/capture-records/) retain independent manifest pins.
The [capture how-to guide](../develop/research-captures.md) gives current collection steps.

It separates branch captures from published results.
Historical observations remain valid only within their recorded scope.
An unavailable old environment remains unverified.

## Browse historical investigations

The [research directory](./) retains the remaining investigations at their original paths.
Use the dated search logs, issue numbers, and source pins within each investigation.
These records explain an earlier source state; they do not establish current implementation status.
The [language extensibility review](language-extensibility/design-review.md) links its audits and later decision follow-ups.

The [participant identity audit](participant-identity/audit.md) retains its issue #215 scope.
The [scenario variation investigation](scenario-variation-trial-realization/index.md) links its design criteria and requirement mapping.
The [backend contract investigation](participant-backend-contracts/index.md) separates portable rules from backend realization.
The [validation profile investigation](validation-admission-profiles/index.md) links its requirement mapping.

The [lineage directory](lineage/) retains source audits and exact external excerpts.
The [archive introduction](formal-semantic-validation/archive-contracts/README.md) explains preserved evidence contracts.
Synchronization archive directories retain their own README, source identities, and digest records.
Do not replace their observations with results from current code.
