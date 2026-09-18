# Releasing RAES via raes

`raes` is published to **PyPI**, and releases are automated with
[release-please](https://github.com/googleapis/release-please) (#684). You never
hand-edit the version or `CHANGELOG.md`: release-please derives both from the
Conventional Commit history on `main`.

`raes` also ships the published contract corpus as package data, so
`raes conformance backend` and SDL semantic validation work from an installed
wheel. Every release binds the code and the corpus in one versioned artifact
(#537). PyPI publication additionally requires the repository's canonical
verification graph to pass for the exact commit named by the release (GOV-928).

## How a release happens

1. Feature PRs **squash-merge** (into `dev`, then promoted to `main`) with a
   Conventional Commit **PR title** — the squashed commit is what release-please
   reads. The required `title-guard` check enforces the shape.
2. On every push to `main`, `.github/workflows/release-please.yml` maintains a
   **release PR** titled `chore(main): release X.Y.Z` that bumps the version and
   regenerates `CHANGELOG.md` from the commits since the last release.
3. **Merge that release PR.** Release Please tags `vX.Y.Z`, creates a **draft**
   GitHub Release, and returns the commit SHA that it tagged. Forced tag creation
   keeps draft releases discoverable by Release Please. The release workflow
   requires that tag and SHA to match and that the commit belong to `main`.
4. The workflow invokes `.github/workflows/canonical-verification.yml` for that
   exact SHA. This is the same proof-bearing, exact-commit verification graph
   used by CI: the same nox test, coverage, policy, contract, and proof lanes,
   now distributed across concurrent jobs, with the same 90% coverage floor. The
   release caller leaves the SonarCloud quality gate disabled. It does not poll
   branch status or accept a check from another commit.
5. A separate read-only job checks out that SHA and must complete the RUN-314
   reference-backend tests against a real container runtime. Before the lane
   runs, the native runtime pulls the pinned platform manifest from the public
   registry. The lane verifies daemon OS, architecture, and uncompressed layer
   identities against `implementations/tooling/artifacts.lock.json`.
   Release-required mode fails when the runtime or reviewed image is unavailable,
   its identity differs, pytest collects zero tests, or any selected test skips.
   Retired mirror/pre-seed environment switches are rejected. The ordinary
   PR/local Docker lane remains optional.
6. A read-only job checks out the verified SHA, builds the corpus-bundled wheel
   and sdist, checks the corpus in both archives, installs each exact artifact in
   its own fresh environment, and runs `raes conformance backend --profile
   provisioning-only` outside the checkout.
7. An admission job downloads those distributions and their evidence, runs the
   full evidence admission, and checks that the admitted wheel and sdist
   filenames correspond to the resolved tag version. Because it is the last job
   permitted to run repository code, it is the trust bridge: on success it
   exports only four validated scalars — the wheel and sdist basenames and
   their SHA-256 digests — as job outputs. A refused release exports nothing.
8. Only those tested distributions cross into the `pypi` environment. Each
   publisher independently downloads the artifact, requires exactly the two
   admitted filenames, and rehashes the bytes against the admitted digests
   immediately before its destination operation. Neither publisher checks out
   or executes repository source, so publication credentials never coexist
   with candidate code in the same job; the identity checks they need are made
   over the API.
9. Each destination is then reconciled independently — this is deliberately
   not a transaction:
   - **PyPI.** The workflow queries the release's JSON API before uploading.
     PyPI reports a SHA-256 for every file it stores, so an "already exists"
     answer is never taken as proof of byte identity. Every expected file
     already present with matching bytes means there is nothing to upload; a
     missing file leaves that upload pending; a same-name file with different
     bytes fails the run. An unreachable or unexpected API response fails
     rather than being read as "not published".
   - **GitHub.** The job revalidates the Release object id, draft state, exact
     tag ref, and fully dereferenced commit SHA, then reconciles every asset
     it writes — both distributions and the retained evidence — one at a time.
     GitHub publishes no server-side asset digest, so presence comes from the
     Release's asset listing and identity from a byte comparison. Exactly three
     outcomes are allowed: matching existing bytes (already published),
     confirmed absence (upload, then read the stored bytes back and compare),
     or failure. An asset listing or download that does not succeed is never
     read as absence, so a transient API error cannot become an overwrite, and
     nothing is ever overwritten. The Release identity is re-read after
     attachment before the numeric Release id is made public.

   Keeping these jobs separate means a failed attachment or finalization is
   retried without attempting a second PyPI upload. If the public-finalization
   response was lost after GitHub applied it, the retry accepts the
   already-public Release only after downloading and byte-comparing both
   attached distributions and rechecking the id, tag, and commit SHA.

GitHub exposes draft Releases only to push-capable identities. Consequently,
the release-resolution job and the pre-PyPI revalidation job each need
job-scoped `contents: write` even though their release operations are reads.
The workflow default, canonical verifier, real-container gate, and build job
remain `contents: read`; the GitHub finalization job already needs write access
for attachment and publication. Checkouts in either write-scoped job must not
persist the elevated credential, and the permission correction must not
introduce a PAT or long-lived publication secret.

Nothing is hand-run, and feature PRs never touch `CHANGELOG.md` (release-please
owns it) — no fragment collisions.

## Version rubric (PR-title type → bump)

| Type | Releases? | Bump |
|---|---|---|
| `feat` | yes | minor |
| `fix`, `perf` | yes | patch |
| `feat!` / `fix!` / `BREAKING CHANGE:` footer | yes | major (pre-1.0 demoted to minor) |
| `docs`, `chore`, `refactor`, `test`, `ci`, `build` | no | — |

Use `feat:`/`fix:` for consumer-visible changes so release-please cuts a release.

## Configuration

- `release-please-config.json` — package at repo root (so `CHANGELOG.md` stays at
  the root), `release-type: python`, `package-name: raes`. The actual version
  literal lives in a dedicated RAES package file and is bumped via `extra-files`
  (`implementations/python/packages/raes/_version.py`).
- `.release-please-manifest.json` — the version source of truth: `{".": "X.Y.Z"}`.
- `implementations/python/packages/raes/_version.py` — build version source
  (release-please rewrites it). `raes.__version__` derives from the installed
  `raes` distribution metadata.
  The `raes` and `raes-mcp` console scripts are the only current commands.
- `.github/workflows/canonical-verification.yml` — reusable exact-commit
  verification graph called by both ordinary CI and the release workflow. Its
  input is a full commit SHA, not a branch or tag; the proof-bearing nox job
  checks out and binds itself to that value.
- `release-please-config.json` creates releases as drafts and forces the tag to
  exist immediately. Only the gated GitHub publication job removes draft state.

## Release evidence: SBOM, build inventory, and provenance

Every release produces evidence bound to the exact bytes it publishes (#1226):

- **Runtime SBOMs** in CycloneDX 1.6, one for the wheel and one for the sdist.
  Each names the distribution's runtime dependency closure with its dependency
  edges, and binds the SHA-256 of the artifact it describes.
- **A build/tool/native input inventory**, recorded separately from runtime
  dependencies. It carries the interpreter and closure profile, the build
  backend, the reviewed tool inputs, the pinned actions, and the lock and policy
  hashes, along with the repository, source commit, producer workflow, run id,
  and run attempt.
- **A release evidence index** binding the published subject set and every
  evidence document by size and digest.

The runtime SBOM is **not** a dump of the smoke environment. That environment
installs the full projected requirements and then the candidate with
`--no-deps`, so it also holds the published `dev` and `docs` extras — reading it
back would file Sphinx and pytest as runtime dependencies of `raes`. The closure
is instead reconciled from three independent sources: the built wheel's own
`Requires-Dist` metadata, the reviewed lock, and the observed installation. Any
disagreement fails the release rather than silently dropping a dependency edge.

The wheel, the original sdist, and the wheel rebuilt from that sdist are three
distinct subjects. The sdist SBOM binds the original `.tar.gz`; the rebuilt
wheel is recorded as a derived test subject and never stands in for either
published artifact.

### How it is signed and admitted

Signing runs in its own `attest-release` job through
`actions/attest-build-provenance`. That job checks out nothing, holds no PyPI
environment and no `contents: write`, and measures the bytes it received before
signing them — so an attestation credential cannot authorize publication.

A separate `admit-release` job then verifies each subject with
`gh attestation verify`, pinned to the issuer, repository, and signer workflow
recorded in `implementations/tooling/admission-policy.json`. Those approved
identities come from reviewed policy, never from the bundle being verified. Both
publishers depend on that job, so absent or rejected evidence blocks the handoff
instead of being an optional report. A cryptographically valid signature over
the wrong repository, workflow, run, attempt, or subject is a rejection.

### Where it is retained

The evidence is attached to the GitHub Release beside the wheel and sdist, and
read back and digest-compared after upload, so it outlives the seven-day Actions
artifact retention. Retention owner: Release; the
supported-release-lifetime-plus-one-year rule in
[operations](../decisions/package-artifacts/operations.md) applies.

### Verifying a release as a consumer

```console
$ gh attestation verify raes-1.2.3-py3-none-any.whl \
    --repo OpenRAE/rae \
    --signer-workflow OpenRAE/rae/.github/workflows/release-please.yml
```

Download the SBOM and build inventory from the same Release to inspect the
recorded dependency closure and build inputs.

## Release bookkeeping does not re-run checks

The release PR, the `main` → `dev` back-merge PR opened by the `sync-dev` job,
and the pushes that merging them produces change only the files Release Please
manages: `CHANGELOG.md`, `.release-please-manifest.json`, and
`implementations/python/packages/raes/_version.py`. Every check already ran on
the `dev` → `main` promotion, so the check workflows list exactly those files
under `paths-ignore` and do not trigger on these events (#1266). The Docs
deployment on the `main` push is not filtered, because the published docs
render the release version. `test_release_workflows.py` keeps the ignored set
identical across workflows and equal to the Release Please configuration.

Because the check workflows do not trigger, the required status checks never
report on either bot PR. **Admin-merge** both. Adding any other change to
either PR brings the full check suite back.

Research evidence captures bind a digest of the reference-package sources
(source profile `python-reference-source/v2`). That digest replaces the marked
Release Please version literal with a placeholder, so the release commit's
version bump cannot invalidate the evidence. Any other change to `_version.py`
still changes the digest, and a version file without exactly one marked literal
fails closed.

Skipping checks cannot bypass publication verification. After the release PR lands,
the release workflow keeps the GitHub Release private as a draft while it runs
the canonical graph against the exact tagged commit. PyPI upload,
GitHub artifact attachment, and public Release finalization depend directly on
that successful graph. On automatic pushes, release resolution also requires
the Release Please job itself to finish successfully; an output from a skipped,
cancelled, or failed job is never sufficient.

## External tag-protection control

Configure a GitHub tag ruleset for `v*` that prevents tag deletion and updates
outside the explicitly approved release authority. The repository workflow
revalidates mutable GitHub state at both publication boundaries, but it cannot
make a tag immutable after PyPI accepts an artifact, and repository-owned code
must not grant itself permission to rewrite live organization rulesets. This
ruleset remains a maintainer-owned external control and a release-readiness
requirement.

## Recovering a partial publication

Publication is two independently reconciled destinations, so a run that
published to PyPI and then failed on GitHub is a normal, recoverable state. The
governing rule is that recovery republishes **the original tested bytes** and
never rebuilds a new artifact under an existing version.

**Start here: re-run the failed jobs on the original run.** In the Actions UI,
open the release run and use **re-run failed jobs**. This reuses that run's own
distribution and evidence artifacts, so `build-release` does not run again and
the bytes are the ones that were admitted. The publishers reconcile each
destination and complete only what is outstanding:

| Observed state | What the re-run does |
| --- | --- |
| PyPI published, GitHub not attached | Skips the PyPI upload (digests already match) and attaches/finalizes GitHub. |
| PyPI partially uploaded | Uploads only the missing file; the present one is verified byte-identical first. |
| GitHub asset or evidence already attached | Leaves it in place after a byte comparison. |
| Outcome uncertain (lost API response) | Queries each destination and compares bytes before doing anything. |
| Destination query itself fails | Stops. An unavailable answer is never read as "not published". |
| Same version, different bytes at a destination | Fails visibly. See below. |

Actions artifacts are retained for **seven days**. Within that window the
re-run is the whole procedure.

**If the artifacts have aged out.** The distribution artifact is the only
source of publishable bytes; no publisher can rebuild. When the download fails,
that failure *is* the diagnosis: stop. Do not dispatch a fresh run to recreate
the version — a rebuild is not guaranteed to reproduce the published bytes, and
replacing an already-published version silently is exactly what this design
forbids. Cut a new patch release through the normal reviewed process instead.
The release evidence itself outlives the artifact window, because it is
attached to the durable GitHub Release.

**A same-version digest mismatch is an incident, not a retry.** If PyPI or the
Release already stores a file under an expected name with different bytes, the
run fails and says so. Do not overwrite it, move the tag, or rebuild. Establish
where the divergent bytes came from, then publish a new version.

### Dispatching the workflow for an existing tag

`workflow_dispatch` accepts an existing stable-SemVer tag (`vX.Y.Z`) that
resolves to a commit reachable from `main` and has a policy base. The workflow
resolves it once to a full SHA and runs the whole graph — canonical
verification, the required real-container lane, build, corpus checks, the exact
wheel and sdist installation/conformance smokes, evidence admission, and the
OIDC publication chain.

Use this for a draft created by an older run that failed **before** PyPI
publication: it preserves the bound tag, commit, and numeric Release identity
while applying the current publication gates, rather than re-running a stale
workflow definition. It is not the recovery path for a version that is already
on PyPI — that run rebuilds, and the destination digest comparison will reject
the result unless the rebuild is byte-identical. Manual dispatch is not a
verification bypass and never builds from the current branch head.

## First release

`main` starts at `0.18.0` (the manifest/pyproject baseline; the historical
changelog through `0.18.0` is preserved in `CHANGELOG.md`). The first `feat:`/
`fix:` merged to `main` after adoption produces a release PR bumping from
`0.18.0`; merging it publishes the first PyPI artifact.

## PyPI trusted publishing (one-time, maintainer)

Register a **pending** trusted publisher on PyPI before the first upload (no
token stored):

- PyPI → *Your projects* → *Publishing* → *Add a pending publisher* → GitHub
- PyPI Project Name: `raes`
- Owner: `OpenRAE`  ·  Repository: `rae`
- **Workflow name: `release-please.yml`**  ·  Environment name: `pypi`

> If you previously registered the publisher against `release.yml`, update it to
> `release-please.yml` (or add a second pending publisher) — the workflow filename
> must match or only the PyPI publish step 403s.

The `pypi` environment and `id-token: write` permission exist only on the PyPI
upload job. That job also has job-scoped `contents: write` solely so its
post-approval identity check can see the still-draft GitHub Release. Configure
the environment's deployment branch policy for `main`. Resolution, canonical
verification, distribution installation, GitHub attachment, and CLI execution
cannot mint the PyPI publishing credential.

## Pinning from a downstream backend

```
raes==<X.Y.Z>
```
