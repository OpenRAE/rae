# Evaluate the research surface

Use RAES files to inspect a bounded claim, repeat a check, or compare code with
a published contract.

You can inspect:

- specifications and published schemas;
- source code and tests;
- example scenarios and conformance fixtures;
- decisions that explain key design choices;
- research records with searches, comparisons, and known gaps.

Working records remain in the repository for peer review. They are not part of
this hosted guide. Start with the
[formal specifications](https://github.com/OpenRAE/rae/tree/main/specs),
[contracts](https://github.com/OpenRAE/rae/tree/main/contracts), and
[research directory](https://github.com/OpenRAE/rae/tree/main/docs/research).

RAES can support a bounded reproduction attempt. One successful parse,
realization, or replay does not prove scientific reproducibility.

For exact release rules, use the
[formal specification index for RAES 11.0.2](https://github.com/OpenRAE/rae/blob/v11.0.2/specs/formal/README.md)
and [schema reference](https://github.com/OpenRAE/rae/blob/v11.0.2/contracts/schemas/README.md).
Each formal domain gives its model, implementation evidence, and claim limits.
For development checks, use the
[local specification and contract check guide](https://github.com/OpenRAE/rae/blob/dev/docs/develop/check-specification-contracts.md).
That guide names its source revision and does not add support to the released package.

## Follow reasoning and evidence

Use the [research record entry](https://github.com/OpenRAE/rae/blob/dev/docs/research/index.md) for development questions and bounded results.
It separates explanations, exact evidence, and current check procedures.
The [decision index](https://github.com/OpenRAE/rae/blob/dev/docs/decisions/adrs/README.md) shows accepted and superseded decisions.
The [requirement reference](https://github.com/OpenRAE/rae/blob/dev/docs/requirements/README.md) explains status and delivery traceability.
These development links can change; use each record's source revision for an exact citation.
They do not add support to RAES 11.0.2.

A current question concerns researcher accessibility.
The [language-evaluation record](https://github.com/OpenRAE/rae/blob/dev/docs/research/dsl-language-evaluation/index.md) links the protocol and not-started snapshots.
Those snapshots contain no study observations.
A successful parse does not demonstrate accessibility or scientific reproducibility.
