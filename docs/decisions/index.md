<a id="architecture-decisions--design-notes"></a>

# Architecture decisions and design notes

Use the [ADR index](adrs/README.md) for decision status, dates, and replacement links.
Decision rationale is explanation.
Exact status and amendment records are reference.
An accepted decision does not prove that its implementation has shipped.

The [decision directory](./) retains the complete working-note archive.
Design and preflight notes describe the issue and source state named in each record.
They are historical reasoning, not current operating procedures.
Check later ADRs and linked implementation evidence before applying an earlier recommendation.
Keep dated findings and accepted decision text unchanged.

For example, accepted [ADR-115](adrs/adr-115-concrete-backends-owned-outside-raes.md) replaces the earlier backend decision in ADR-063.
The ADR index links both records and shows their status.
Use Git history at the revision under review for exact text and amendment history.

The [package and artifact explanation](package-artifacts/README.md) gives the design for issue #1168.
The [research entry](../research/index.md) links bounded observations and open questions.
The [development workflow](../DEVELOPMENT_WORKFLOW.md) gives current contributor procedures.

```{toctree}
:maxdepth: 1
:caption: Architecture Decision Records
:glob:

adrs/README
adrs/adr-*
```

```{toctree}
:maxdepth: 1
:caption: Design & Preflight Notes
:glob:

cage-*
issue-*
sem-*
```
