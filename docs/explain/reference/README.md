# Reference notes

These notes are for people who work on the code. They are not normative
specs or ADRs.

- [coding-standards.md](coding-standards.md)
  - Coding rules for the repo
- [canonical-reference-map.md](canonical-reference-map.md)
  - Where the main source for SDL, contract, processor, runtime, and
    experiment reference material lives now
- [documentation-style-guide.md](documentation-style-guide.md)
  - Repo-wide style, citation, and tone rules for docs
- [fixture-provenance.md](fixture-provenance.md)
  - How a test fixture that stands in for an external system shows
    where its shape came from
- [glossary.md](glossary.md)
  - Current terms for SDL, contracts, processing, runtime, experiments,
    and ecosystem concepts
- [shared-concept-model.md](shared-concept-model.md)
  - Design guidance for `GOV-917` and related shared concept model work
- [shared-semantic-integrity.md](shared-semantic-integrity.md)
  - Design rules for `SEM-200` shared semantic integrity work
- [backend-conformance.md](backend-conformance.md)
  - Design rules for `ASR-502` backend conformance work
- [normative-artifact-authority.md](normative-artifact-authority.md)
  - Design rules for `ASR-517` normative authority boundary work
- [published-schema-coverage.md](published-schema-coverage.md)
  - The `ASR-501` rule that each published schema must carry corpus,
    formal, or declared coverage evidence
- [published-contract-requirement-tracing.md](published-contract-requirement-tracing.md)
  - The rule requiring every published schema to trace to a live governing
    requirement through an `IMPLEMENTS → SPEC` link
- [assessment-semantics.md](assessment-semantics.md)
  - Design rules for `SEM-206` assessment semantics work
- [objective-semantics.md](objective-semantics.md)
  - Reference for those who build `SEM-207` declarative objective semantics
- [explicitness-realization-semantics.md](explicitness-realization-semantics.md)
  - Design rules for `SEM-218` explicitness and realization work
- [domain-profiles.md](domain-profiles.md)
  - Portable typed profile names, offline lookup, support checks, opaque
    data kept as is, and where data came from
- [scenario-variation-and-trial-realization.md](scenario-variation-and-trial-realization.md)
  - The full SCE-002 design: phases, owners, names, random streams, trial
    plans, runtime facts, migration, and follow-on design
- [experiment-binding-contracts.md](experiment-binding-contracts.md)
  - The contracts that bind an experiment to its scenario, participants,
    and apparatus, and how its settings are realized
- [participant-decision-surface-v2-migration.md](participant-decision-surface-v2-migration.md)
  - How to move to version 2 of the participant decision surface: how it
    is shown, sent, declared, admitted, reset, kept in memory, and logged
