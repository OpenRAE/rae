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
- On Python 3.11, importing SDL modules from an OCI registry requires Python
  3.11.4 or newer. Earlier 3.11 releases lack the safe tar extraction filter,
  so RAES stops with an error instead of extracting without it.

Use backend reports, test results, provenance, and evidence to state the limits
of a result.
