# Issue #1227: Tested-release publication and recovery preflight

## Decision

Publication and recovery consume the existing admitted distribution set. Its
canonical byte contract is `tools/release_evidence_admission.py`:
`release-evidence-index.json` declares the one wheel and one sdist by relative
path, filename, size, and SHA-256; `verify_admission()` rejects missing, extra,
replaced, or changed subjects before a publisher uses them. Do not introduce a
second release-manifest, digest file, evidence format, service, or persistence
layer.

`admit-release` must run that existing admission validation after its
Actions-artifact download, then derive the two expected basenames and digests
from its validated index. Because publisher jobs must not check out or execute
candidate source, that job is the trust bridge: after successful verification it
may expose the four scalar filename/digest values as job outputs. Publisher jobs
use those outputs to validate their independently downloaded files and rehash
them immediately before each destination operation. The admission boundary, not
a publisher, also rejects names that do not correspond to the resolved
tag/version. The derived wheel built from the sdist is a test subject only; it
is never a publication candidate.

Each destination is reconciled independently and is not transactional:

- an existing PyPI or GitHub asset is successful only when its exact expected
  name and SHA-256 match the admitted original;
- a same-name or same-version mismatch is a visible failure, never an
  overwrite, `--clobber`, moved tag, or rebuild;
- an ambiguous client/API outcome requires a destination readback and the same
  comparison before retrying only the pending destination;
- if the original admitted bytes cannot be recovered from the named Actions
  artifact, stop with that diagnosis. A reviewed normal new-release process is
  the only next path.

The existing release identity checks remain independent of artifact checks:
numeric GitHub Release id, draft state, tag name, and fully dereferenced commit
SHA are checked at their existing publication boundaries. Artifact identity
must not be inferred from release/tag identity, and release identity must not
be inferred from an artifact filename or digest.

## Boundaries

Keep the current machine-authority separation: the exact-SHA verifier and
required real-container lane run before build; build/test, attestation, and
admission have no PyPI environment; only `publish-pypi` retains scoped OIDC
Trusted Publishing; GitHub attachment/finalization stays a separate
`contents: write` job. No publisher checks out or executes candidate source.
Keep pinned actions, `persist-credentials: false`, fixed/validated environment
values, and credentials out of command arguments and diagnostics.

`release_evidence_admission.AdmissionError` and its stable codes are the
failure vocabulary for local artifact admission. Shell/API destination failures
should remain concise, non-secret workflow diagnostics; do not add an exception
hierarchy or logging format. Extend `test_release_workflows.py` for workflow
ordering/permissions and executable shell recovery cases, and reuse the #1226
admission tests for input-shape and digest cases.

## Non-goals

This does not create enterprise storage, promotion/quarantine/revocation
services, a backup or retention guarantee, an independent evidence framework,
a distributed transaction, a public test release, or a recovery rebuild path.
It does not amend ADR-106/107: their current #1313 amendments already confine
this work to ordinary same-byte handoff and partial-publication recovery.
