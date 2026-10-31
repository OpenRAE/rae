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
No published schema, policy rule, deployment configuration, or ADR needs a change.
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
