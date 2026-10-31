# Runtime constraint scope lookup

## Architecture

The public interface remains `evaluate_realization_constraint` in `raes_contracts.realization_structure`.
The evaluator builds one private scope tree after document admission.
Each tree edge is a decoded JSON Pointer token.
Each node holds its scope closure and child edges.
The tree serves inherited closure lookup and closed-scope child lookup.
Local closure takes priority over inherited closure.
The deepest matching scope takes priority over the document default.
The evaluator shares the tree across definition references.
The tree lasts for one evaluation.

Tree construction charges each scope and token against `RelationBudget`.
Lookup charges each visited edge against the same budget.
Exhaustion returns `limit-exceeded` through the existing diagnostic helpers.
Default limits and public contracts stay unchanged.
Legacy projection and compatibility helpers retain their existing lookup implementation.
The runtime lookup fix changes no published schema or deployment configuration.
This implementation follows ADR-070 and the issue preflight guidance.

## Security and data flow

The assets are authored constraints, observed values, and the caller's CPU and memory.
Caller data crosses the evaluator's admission boundary before tree construction.
Document admission bounds scope count, pointer size, depth, and scalar bytes.
Value admission bounds the observed tree before comparison.
Budget charges bound tree construction and lookup work.
Only `conformant` permits success.
Exact leaves, scope overlays, and collection identities remain enforced.
Tests check changed leaves, closed descendants, escaped tokens, and exhausted work.
No data leaves the process, and diagnostics contain no input values.

```text
Caller (untrusted document and value)
  -- constraint document --> Document admission [trust boundary]
  -- observed value ------> Value admission [trust boundary]
Document admission -- bounded scopes --> Scope tree [temporary memory]
Scope tree -- inherited closure and declared children --> Relation evaluator
Value admission -- bounded value --> Scope overlays and relation evaluator
RelationBudget -- work allowance --> Tree construction and all evaluation
Relation evaluator -- bounded status and diagnostics --> Caller
```

This data flow also supplies the component diagram.
No additional deployment diagram is needed because process boundaries stay unchanged.
The existing finite-work checks supply policy enforcement.
The private tree implements the architecture without a new public abstraction.
Remaining risk is legitimate input exceeding a finite budget; failure remains closed.

## References and document review

- Python 3.14, Built-in Types, mapping types: <https://docs.python.org/3.14/library/stdtypes.html>.
  Use dictionaries for decoded token edges and preserve exact token equality.
- MITRE CWE-400, version 5.0, architecture and implementation mitigations:
  <https://cwe.mitre.org/data/definitions/400.html>.
  Bound resource use and retain safe failure outcomes.
- ASD-STE100 official site: <https://asd-ste100.org/>.
  The site refused access during this run.
  Review used the skill's stated sentence limits and terminology rules; full standard compliance is not asserted.

Review kept sentences short and technical names consistent.
This document describes system behavior; implementation tasks remain in the issue plan.

## Routine verification and retained research

Routine CI checks behavior with the current implementation.
A saved research snapshot records an earlier observation.
Its package hashes describe that observation; they do not prove current behavior.
Research selection uses capture dates, not equality with the whole live source tree.
Live replay still checks expected outcomes and artifact integrity.
Package source hashes remain recorded provenance, with bounded shape validation.
They no longer require a new publication after each source edit.

The finite model CI job runs current graphs and the fixed negative controls.
It requires the expected positive baseline decision.
Routine CI does not publish or independently reproduce a saved historical capture.
Explicit research publication and reproduction commands retain their selected-subject checks.
Historical inventories and file pins remain intact.
Tests of retained records check archive integrity separately from current behavior.
No old record is relabeled as a new observation.

The assets are accurate claims, source history, and useful release checks.
The threat is stale evidence being presented as current verification.
The control is separation of stored provenance from current executable checks.
A changed behavioral result still fails CI.
A source-only edit does not require a new research record.
No network, credential, storage, or execution privilege changes are needed.

## Integration with the published finite result

The development branch now provides a narrower subject-source identity and a shared reproduction-record reader.
Use those owners for publication and retained-record admission.
The routine model job uses their existing `machine_check replay` command.
It checks the expected finite decision and negative controls without uploading or independently reproducing a research record.
Retained-record admission uses the shared `reproduction_record` reader.
The published machine-check design remains part of the original pinned subject.
This note and the tooling README describe the reduced routine CI path.
The published claim, retained records, and their new coverage remain intact.
