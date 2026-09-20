# raes-sdl plan rules

Mandatory constraints the `/implement` skill applies during plan phase.
These encode the hard rules previously in `AGENTS.md` prose.

- Plans MUST run `implementations/python/.venv/bin/python tools/check_repo_policy.py`
  before declaring completion.
- Plans MUST run `implementations/python/.venv/bin/python tools/check_requirement_governance.py`
  before declaring completion.
- Plans MUST set `RAES_REQUIREMENT_UID` when the branch name does not
  already contain a UID such as `GOV-918`.
- Plans MUST NOT add new authority-bearing artifacts outside `specs/`,
  `contracts/`, `docs/`, and `implementations/`.
- Plans that change a published schema under `contracts/schemas/` (the
  hand-governed normative authority per ADR-009 §7) MUST record a
  contract-facing change-ledger entry (`last_change`: summary + content hash)
  in `contracts/schema-publication-manifest.json`, and a plan that **removes**
  a published schema MUST record a `removed_schemas` tombstone (schema path +
  summary) in the same manifest. Plans MUST keep the reference implementation
  (`schema_bundle()`) generating an identical bundle so
  `tools/check_generated_schemas.py` passes. The published schema is the
  authority; a generator/Python edit alone is NOT authorization for a schema
  change.
- Plans MUST keep concept-authority artifacts in the approved
  concept-authority surfaces.
- Plans MUST keep IMPLEMENTS and TESTS traceability in Ground Control
  aligned with changed code and tests.
- Plans MUST NOT edit `CHANGELOG.md` or add changelog fragments: release-please
  owns `CHANGELOG.md` and generates it from the Conventional Commit history on
  `main` (#684). There is no `changelog.d/`.
- Plans MUST NOT hand-edit the version
  (`implementations/python/packages/raes/_version.py`); release-please bumps it
  on release.
  Feature PRs squash-merge, so the PR title becomes the commit release-please
  reads: `feat:` → minor, `fix:`/`perf:` → patch, `feat!:` / a `BREAKING CHANGE:`
  footer → major (pre-1.0 demoted to minor); `docs`/`chore`/`refactor`/`test`/
  `ci`/`build` do not release. Use `feat:`/`fix:` for consumer-visible changes so
  release-please actually cuts a release. The PR title MUST still pass the
  `title-guard` gate (`tools/check_pr_title.py`).
