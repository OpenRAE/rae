# raes-sdl plan rules

Mandatory constraints the `/implement` skill applies during plan phase.
These encode the hard rules previously in `AGENTS.md` prose.

- Plans MUST follow `/implement`'s proportionate local verification rules:
  run targeted tests and checks for the changed behavior locally. CI owns
  repository-wide verification, completion, and policy suites. Preserve the
  mandatory pre-publish hook, review, CI, SonarCloud, and readiness gates.
- Local test and completion commands MUST remain targeted. Never select a full
  test, integration or fuzz suite locally, even on unknown changes, source edits,
  base synchronization or review repairs. Full verification is CI/CD only.
- Plans MUST set `RAES_REQUIREMENT_UID` when the branch name does not
  already contain a UID such as `GOV-918`.
- Plans MUST NOT add new authority-bearing artifacts outside `specs/`,
  `contracts/`, `docs/`, and `implementations/`.
- Plans MUST name the module that owns each piece of new code. For Go code, the
  owner is a package that `implementations/architecture.json` declares. Plans
  MUST also name the public interface that other modules or packages use to
  reach that code (ADR-117, ADR-122).
- Before implementation starts, plans for Go code MUST declare their design in
  `implementations/architecture.json`. The design is each new or changed
  module, layer, package, import, and external entry. Plans MUST name the
  exported identifiers that each new or changed package adds or changes. The
  design check `archcheck -design` MUST pass on the changed model before
  implementation starts (ADR-122).
- The published schemas under `contracts/schemas/` are the hand-governed
  normative authority (ADR-009 §7). A plan that changes a published schema MUST
  record a contract-facing change-ledger entry in
  `contracts/schema-publication-manifest.json`. The entry is `last_change`, with
  a summary and a content hash. A plan that **removes** a published schema MUST
  record a `removed_schemas` tombstone in the same manifest, with the schema
  path and a summary. Plans MUST keep the reference implementation
  (`schema_bundle()`) generating an identical bundle, so that
  `tools/check_generated_schemas.py` passes. A generator or Python edit alone
  does NOT authorize a schema change.
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

- Routine source edits do not require new research captures. Live behavioral
  checks remain required. When a task deliberately records source-bound formal
  or specification research evidence, it MUST use immutable,
  content-addressed branch captures via `python -m tools.research_capture record`.
  Feature branches MUST NOT allocate the next numbered research release, extend
  hard-coded revision lists, rewrite published history, or append a capture to
  shared narrative indexes. Preserve capture retention records and baseline pins.
  Numbered publication receipts are assigned only on a clean `dev` integration
  checkout via `python -m tools.research_capture publish`. See
  `docs/develop/research-captures.md` for collection and integration instructions.
