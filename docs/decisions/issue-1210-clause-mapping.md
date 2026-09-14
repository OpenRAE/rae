# Issue 1210 acceptance mapping

The [revision contract](../../specs/evolution/progressive-semantics.md) and
[migration guide](../migration/progressive-semantics.md) implement a breaking
cutover. The user explicitly removed legacy-preservation requirements on
2026-09-14. The revised plan is recorded in
[issue #1210](https://github.com/OpenRAE/rae/issues/1210#issuecomment-5659105396).
GOV-903 remains ACTIVE.

## Acceptance evidence

Implementation paths are relative to `implementations/python/` below.

| Issue clause | Implementation | Regression evidence |
| --- | --- | --- |
| Explicit semantic boundary | `packages/raes/semantic_revisions.py`; parser rejects unsupported revisions before normalization; no legacy reader or execution mode | `tests/test_issue_1210_semantic_revisions.py` |
| No inferred sentinel identity or delegation | `packages/raes/_semantic_migration_decisions.py`; typed source-bound author decisions in `packages/raes_contracts/sdl_semantic_migration.py` | Missing decision, exact identity, knowledge and unauthorized delegation tests in `tests/test_issue_1210_semantic_migration.py` |
| Legacy evidence compatibility | Not delivered, per the user's explicit breaking-change decision. Existing research records retain their integrity checks; these are not a legacy artifact reader | Current reader and formatter reject legacy revision selection |
| Formatting, imports, canonicalization, comparison and generated contracts | Current revision propagation, versioned canonical envelope, scenario/task projections v2, schema bundle and publication records | Lifecycle, mixed import, private JSON, omission/empty collection and task observation tests |
| Coordinate #989 and disclose limits | `packages/raes/semantic_migration.py` reuses binding retargeting and admission; source and intermediate digest joins remain explicit | Classification migration chain and atomic missing-scheme refusal tests |
| No property waivers or invented infrastructure | Adoption retains authored presence and existing realization scope; it never executes a backend | Omitted OS/runtime, exact APT values, open abstract formatting and rejected unauthorized delegation tests |
| Separate constraints, choices and observation demand | Inspection axes in `packages/raes_cli/_semantic_sdl.py`; task v2 demand projection | Omitted, inherited, no-data and operational-only modes in `tests/test_issue_1210_formatting.py` |
| Explicit changed admission and observation semantics | Required named admission/observation adoption; report disclaims equivalence and execution permission | Missing/stale context, exact Boolean schema/model parity and report identity tests |

## Verification and traceability

Red/green tests exposed revision ambiguity, unsupported legacy selection,
omission loss in comparison, private description loss, missing observation
projection, formatter value leakage and mixed import acceptance. Incumbent
classification, formatting, canonicalization, recursive, private-profile and
observation suites cover integration.

The current lineage ledger advances to `sdl-lineage-ledger-v2.json`. Formal
release 16.0.0 and coverage release 14.0.0 execute current code and retain the
previous research records without promoting their claim strength. These updates
satisfy existing evidence gates; they provide no product compatibility layer.

No previously tracked files were deleted or renamed. Existing parser, registry,
composition, schema and comparison traceability remains valid. GOV-903 gains
current revision, migration and test links; GOV-904 gains comparison evidence;
ASR-530 gains current replay records. No requirement status transition is needed.

## Review repairs

Current authoring and snapshot identity uses profiles v2 throughout canonical
digests, instantiation provenance, migration targets, bindings and CLI output.
ADR-080 and ADR-095 amendments, SEM-230 traceability, the package loader and
installed-corpus probe now select lineage ledger v2. Every JSON claim pointer
is dereferenced by the lineage gate; the removed vulnerability claim points
to removal authority. Dated preflights and frozen research records remain
historical references, not current lineage selectors. Module composition is
excluded from inspection constraints.

Regression evidence includes
`test_current_identity_cannot_reuse_pre_cutover_authoring_or_snapshot_profiles`,
`test_canonical_lineage_loader_selects_the_current_ledger`,
`test_claim_json_pointer_must_resolve_against_its_artifact`, and
`test_inspection_excludes_authored_module_composition_from_constraints`.
Current formal release 16 uses corpus revision 3 and production evidence v4;
original captures retain exact identities without current-model admission.
