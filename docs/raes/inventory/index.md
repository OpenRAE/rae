# RAES asset inventory methodology

Use this entry to select the capture procedure or inspect its supporting evidence.
RAES owns the participant-discoverable asset inventory methodology.
Downstream backends own their capture tools and original proof bundles.
The methodology defines inclusion rules, semantic gates, and capture-to-specification steps.

## Complete a capture task

- [Asset inventory methodology](asset-inventory-methodology.md) gives the canonical workflow, evidence boundary, mapping dispositions, and gap rules.
- [Reference issue template](asset-inventory-issue-template.md) gives the issue structure that a backend can copy into its own repository.

## Inspect the reasoning and evidence

- [Methodology assurance report](methodology-assurance-report.md) gives the verification, supply-chain, and research basis for the method.
- [SCN-010 gap analysis](scn010-expressivity-gap-analysis.md) records the APTL TechVault investigation and requirements DSL-132 through DSL-139.
- The preflight links below preserve imported validation records from that investigation.
  They illustrate earlier captures; they do not replace the maintained methodology.

The original TechVault proof bundles remain in APTL.
Their recorded source revisions and observations define their applicability.
A methodology document does not establish that a later backend capture passed its checks.
Use the [research entry](../../research/index.md) for other bounded results and current questions.

```{toctree}
:maxdepth: 1

asset-inventory-methodology
methodology-assurance-report
asset-inventory-issue-template
scn010-expressivity-gap-analysis
issue-516-redaction-boundary-preflight
webapp-preflight
kali-preflight
ad-preflight
```
