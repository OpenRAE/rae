# Contribute to RAES

Use this guide to prepare a checkout, check a change, and submit a pull request.
Start with [setup](#set-up-the-repository), then run a
[targeted check](#run-the-checks).
Report vulnerabilities through [SECURITY.md](SECURITY.md).

The checkout uses Python. Go build migration belongs to issue #1803.
Issue #1804 owns publication at cutover.
These instructions do not qualify a Go release or a live backend.

## Choose the right route

- For a small docs fix, typo fix, or narrow test improvement, a pull request
  is enough. Use `No issue: <brief reason>` in its Related Issues section.
- For SDL language changes, contract changes, processor behavior changes, or
  backend conformance changes, open an issue first.
  Use a standalone `Refs #N` line when its Requirements section declares UIDs.
  Use `Closes #N` otherwise. Those changes can affect authored scenario
  meaning and generated artifacts.
- Keep unrelated work in separate pull requests.
- Base pull requests on `dev`, not `main`. `main` is the stable release line;
  `dev` is the integration branch.

Requirement-backed issues stay open at merge. The delivery workflow verifies
the merged requirement status and traceability, records its final report, and
then closes the issue. The body guard checks scope from the linked issue, not
from a self-declaration in the PR.

Pull request bodies use the section structure that the Ground Control delivery
workflow renders, so a rendered body passes the body guard unmodified. The
[pull request template](.github/PULL_REQUEST_TEMPLATE.md) lists the sections:
Summary, Requirement UIDs, Related Issues, ADR Impact, Changes, Test Plan,
Ground Control Checks, Traceability, and Checklist.
Documentation is an optional section. Each required section appears exactly once and has
content. The guard also enforces the following rules:

- The Summary describes the change in non-placeholder prose.
- Related Issues declares exactly one tracking route: standalone `Refs #N` or
  `Closes #N` lines, or one substantive `No issue:` declaration.
- The Test Plan records the commands run and their outcomes, or a reason a
  check was not run. Checklist items alone are not evidence.
- No other part of the body uses a GitHub closing reference: a closing keyword
  such as `fixes` or `closes`, directly followed by a reference to an issue in
  this repository. GitHub reads that as a closing route, so reword the mention,
  for example as "the issue 1219 migration". Other issue mentions are accepted.

The executable body rules are in `tools/check_pr_body.py` and the
[PR template](.github/PULL_REQUEST_TEMPLATE.md).
The base revision supplies the validator.
A reviewed migration can admit a pinned replacement bundle.
Do not change validator pins to bypass a failed check.

## Set up the repository

An optional [development container](docs/explain/development-container.md)
provides automated setup for the reviewed x86_64 image. The guide labels each
start route verified or unverified, and records the evidence behind those
labels. The container cannot run the Isabelle proof lane; CI runs that gate.

To set up natively instead:

Prerequisites:

- a standard CPython 3.14 payload admitted by the
  [development profile](implementations/tooling/README.md); 3.14t is preview-only
- the exact uv payload selected by the development artifact lock

The host profile also requires Git, trusted CA roots, and SHA-256 tooling.
GitHub operations require GH CLI.
Generic acquisition requires curl 8.4.0 or newer with verified unknown-length size enforcement.

An older client is a hard failure for generic
artifact acquisition. Provision native prerequisites from the reviewed host
image or signed package repositories. Connected setup acquires exact Python,
uv and generic-tool inputs against their reviewed identities. Do not pipe
a remote installer into a shell.

Install the separate locked project and verification-tool environments:

```shell
git clone https://github.com/OpenRAE/rae.git
cd rae
git switch dev
uv sync --project implementations/python --all-extras --frozen
uv sync --project implementations/tooling/python --frozen --no-default-groups
```

Specialized TLS acquisition fixtures use the tooling `acquisition-tests`
dependency group; ordinary tooling sync does not need it. The existing Intel
Mac restriction is not lifted by that separation: patched runtime dependencies
and actual target smoke evidence are still required. No vulnerable dependency
downgrade or untested support is implied.

Both sync commands must exit `0` before you run the checks.
If acquisition fails, read the named prerequisite or digest failure.
Keep the lock and host checks enabled.
Use the [tooling guide](implementations/tooling/README.md) to inspect supported profiles.

The [developer documentation index](docs/README.md) links to architecture,
research, migration, release, and workflow records that are not part of the
hosted reader guide.

## Make a change

1. Fork the repository and create a branch from `dev`.
2. Make the smallest coherent change that solves the issue.
3. Add or update tests when behavior changes.
4. Update examples, schemas, contracts, or documentation when the public
   surface changes.
5. For public docs changes, follow
   [`docs/explain/reference/documentation-style-guide.md`](docs/explain/reference/documentation-style-guide.md).
6. Use a [Conventional Commit](https://www.conventionalcommits.org/) PR title,
   such as `feat:` or `fix:`. Release Please reads that title.
7. Run the relevant checks locally.
8. Open a pull request against `dev` with a concrete description of what
   changed and why.

## Run the checks

Commit hooks run file-scoped hygiene and secrets checks: whitespace, final
newlines, YAML/JSON syntax, file size, conflict markers, private keys, and
Gitleaks. No pre-push check is configured. Full tests, policy, contracts,
lint, proof, and documentation validation remain required in CI/CD.

Full verification and proof replay run in CI/CD.
CI acquires proof inputs through the
[canonical verification workflow](.github/workflows/canonical-verification.yml).
Do not disable isolation to make a proof check pass.

Run the change-aware local gate while iterating:

```shell
uv run --project implementations/tooling/python --frozen --no-default-groups nox -f noxfile.py -s verify-changed
```

It runs changed-file checks and directly changed test modules against the
branch's upstream ref. Uncertain classification never triggers a full local
suite. Select relevant test modules or cases explicitly for source-only changes.
Full test, integration, fuzz and completion suites run in CI/CD only. The
unconditional `verify` graph remains a CI/CD entry point.

For a runtime-model change, run the selected test module below.
For prose, replace `CONTRIBUTING.md` with your changed paths.
Use `-l` to list sessions; it does not run them.

```shell
uv run --project implementations/python --frozen pytest implementations/python/tests/test_runtime_models.py -q
uv run --project implementations/tooling/python --frozen --no-default-groups nox -s docs-prose -- CONTRIBUTING.md
uv run --project implementations/tooling/python --frozen --no-default-groups nox -f noxfile.py -l
```

Run targeted checks for the changes you make. CI/CD runs the full gate before
merge, including language, contract, generated-artifact, and shared-runtime checks.

## Let Release Please write the changelog

`CHANGELOG.md` is generated by
[release-please](https://github.com/googleapis/release-please) from the
Conventional Commit history on `main`; do not hand-edit it or add changelog
fragments. The Conventional Commit PR title is the entry release-please reads.
See [`docs/explain/releasing.md`](docs/explain/releasing.md).

## Report security issues privately

Do not open public issues for suspected security vulnerabilities. See
[SECURITY.md](SECURITY.md).

## Follow the community rules

Participation in this project is covered by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Find release and legal records

Read the [release procedure](docs/explain/releasing.md) before proposing a release.
[CHANGELOG.md](CHANGELOG.md) records generated release entries.
[LICENSE](LICENSE) gives the repository license.
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) gives component notices and license boundaries.
These records do not replace the private security-reporting route.
