# Check current limits

Read these limits before you choose RAES for a study or an app.

- RAES is an academic and engineering project, not a managed service.
- The repository does not include a production deployment backend.
- A valid SDL file may request features that a chosen backend does not
  support.
- Validation cannot guarantee that a runtime behaves deterministically.
- Saved inputs and evidence support another attempt; they do not guarantee
  equal outcomes, exact replay, scientific validity, or reproducibility.
- The project currently has one maintainer. It does not require a second
  maintainer or independent reviewer for every change.
- Public schemas have their own stability labels. A versioned name does
  not by itself mean that a schema is stable.

Use backend reports, test results, provenance, and evidence to state the limits
of a result.

The runtime can run installed mixed paths and staged handoffs.
The tests use controlled providers. They check bounded RAE behavior.
Reusable control with mixed runtime remains unsupported.
Remote dispatch with local mixed services is also refused.
Two passing paths do not prove that they work together.
Read the [control support reference](https://github.com/OpenRAE/rae/blob/dev/docs/explain/reference/revised-control-semantics.md)
for the selected bindings and evidence limits.
