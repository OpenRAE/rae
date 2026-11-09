# Shared documentation package preflight

This reference gives architecture boundaries for issue #1954. It does not
implement the integration or give an implementation plan. The issue supplied
for this review is the delivery contract. No formal requirement is attached.

The inspected revision is `c8fc7245381742610f9ccf693ee47f81ba26b3d9`.
The current guide uses local Vale rules and Docutils. It installs no shared
STE package or documentation skill. The supplied issue does not identify a
released package, version, digest, distribution format, or public interface.
Those inputs need review when extraction delivers them. This preflight makes
no claim about an upstream release or its supported formats.

## Ownership and scope

Consume the extracted package through its released interface. Keep only the
RAE configuration and integration needed by existing consumers. Do not copy
its skill, checker, integrity code, or general writing rules into RAE.
No new ADR is needed: ADR-009, ADR-014, ADR-059, ADR-106 and ADR-116 already
govern authority, verification, protected decisions, acquisition and errors.
Use the current scope amendment of ADR-106, not its superseded service design.

| Owner | Boundary |
| --- | --- |
| Shared package | Released Diataxis and STE skill, selected general STE checks, shared integrity checks, and explicit-path interface. Confirm each capability against the release. |
| RAE writing policy | `.vale.ini`, `styles/RAES/`, and `styles/config/vocabularies/RAES/accept.txt` own local terms and contract-specific rules. Reconcile overlapping shared checks by rule and meaning. Keep one active owner for each duplicated check. |
| RAE source and meaning review | The documentation style guide owns source paths, revision evidence, Diataxis purpose, manual STE review, and preservation of obligations. A style result cannot establish code accuracy or normative correctness. |
| RAE workflow | Existing nox stages own selection and stage results. Native CI workflows own orchestration and permissions. The package must not create another verification graph. |
| RAE publication | Existing Sphinx/MyST sources, guards and publishers retain their boundary. A repository-wide prose check grants no permission to publish repository-only material. |

Update the existing authoring guide and agent entry only where integration
changes their instructions. Keep the section rewrites of milestone 75 outside
this delivery. The general acceptance criteria apply to prose changed here.
They do not expand this issue into a corpus rewrite.

## Cross-cutting layers

The intended flow is a reviewed release into the existing local tool environment,
then selected repository files into local checks. Results enter the existing
nox report. Public source checks and rendering retain their separate boundary.
No prose flows to an acquisition endpoint or remote analyzer.

| Layer | Canonical incumbent and required treatment |
| --- | --- |
| Dependency authority | `implementations/tooling/README.md` defines ownership. Python tools use the tooling `pyproject.toml` and `uv.lock`; project docs dependencies use the existing docs extra and project lock. Keep development checks out of product runtime dependencies. `tools/tooling_artifact_policy_python.py` requires exact `==` direct pins. A commit-pinned VCS dependency does not satisfy that shape. |
| Generic artifact admission | For a non-Python release, reuse `tools/vale_tool.py` as the integration example. `artifacts.lock.json`, `profiles/development-profiles.json`, `admission-policy.json`, and `selector-bindings.json` under `implementations/tooling/` retain authority. `tools/tool_versions.py` is a checked projection. Use existing artifact classes and schemas, not a second package lock. |
| Shape validation | `tools/check_tooling_artifact_policy.py` and `tools/tooling_artifact_policy_common.py` validate bounded, duplicate-free records and closed schemas. Schema references stay local. `tools/tooling_policy_gate.py` validates the selected version, platform, profile and response shape. Updating a consumer alone cannot authorize bytes rejected by these layers. |
| Acquisition and cache | `tools/maintained_client_acquisition.py` owns qualified curl acquisition. `tools/verified_tool_installation.py` owns verified installation of generic tools. Retain reviewed hashes and sizes, safe extraction, private ownership, no-follow checks, locking, complete installed identity and atomic publication. Use the existing verified-tree helpers if the release needs a tree. No HTTP stack, live digest discovery, mutable release selector or personal installation fallback. |
| Shared integrity checks | Consume the package's integrity interface where applicable. Its asset checks and RAE's release admission protect different boundaries. Do not remove RAE admission because the package checks itself. Do not retain a copied shared verifier after consumers use the released one. |
| Path selection | `tools/nox_support/test_lanes.py` owns `_selected_prose_paths`, `_protected_prose_paths` and `_run_docs_prose`. Reuse `tools/verification_plan.py`, `tools.policy.common.safe_repo_path`, NUL-safe Git selection, rename/deletion handling and batching. Keep explicit paths, staged selection and the verified CI base. Reject external paths and escaping symlinks before a checker reads them. Use argument arrays and option terminators supported by the released CLI. |
| Protected text | Reuse `docs/decisions/adrs/adr-index.yaml`, `tools/policy/historical_identity_records.json`, and their validators. Retain exact-file exclusions, frozen ADR review and failure on malformed catalogs. Root legal and changelog exclusions do not exempt nested maintained pages. New maintained passages in protected files still need separate checks. |
| Parser and format safety | Keep Vale/Docutils for `.rst` and manual STE review for unsupported formats. The pinned Vale passes `--no-file-insertion` to `rst2html`; preserve the regression that checks this. Keep `UV_PROJECT_ENVIRONMENT` resolution for the selected docs environment. Do not assume that a shared Markdown checker handles reStructuredText, MyST directives, or all Sphinx output. |
| Authentication and secrets | This integration needs no new account, token or runtime auth surface. Keep credential-free approved acquisition and existing read-only PR jobs. `tools/tooling_policy_gate.py` restricts the validator environment to named process essentials and fixed uv settings. Do not broaden it to pass arbitrary environment values or credentials. Retain hygiene and Gitleaks. |
| OS exposure | Invoke the admitted executable from the selected environment, not an ambient personal binary. Keep prose in files or the existing stdin interface. Do not put prose or credentials in process arguments, URLs or shell substitutions. Review package defaults for network use, telemetry, file inclusion and source modification. Do not enable remote analysis or automatic prose edits. |
| Errors and observability | Reuse `raes_contracts.errors`, existing artifact error families, `tools.policy.common.PolicyFailure`, and `raes_contracts.operational_logging`. Nox retains `SessionReporter` and Sphinx retains native warnings. Distinguish check findings from unavailable tools or invalid configuration. All required failures remain nonzero. Keep errors bounded; do not echo URLs, credentials, environment dumps or raw foreign tracebacks. No new exception hierarchy or result envelope. |
| Public build and host | `noxfile.py`, `tools/nox_support/config.py`, `_run_docs`, and `tools/nox_support/graph.py` retain the verification graph. `tools/check_public_docs.py`, `tools/public_docs_markup.py`, `tools/public_docs_guard.py`, and `docs/public/conf.py` retain source and output containment. Preserve warning-strict Sphinx/MyST, executable examples, redirects and output inventory. |
| CI and publishing | `.github/workflows/canonical-verification.yml` passes the verified base to `docs-local`. `.github/workflows/docs.yml` and `.readthedocs.yaml` retain frozen dependencies and current publication routes. Preserve main-only Pages deployment and separate publisher permissions. `.pre-commit-config.yaml` stays limited to hygiene and secrets. Full checks remain in CI. |
| Persistence and contracts | Git stores reviewed configuration, dependency pins and notices. Existing caches and `docs/_build/` hold disposable local output. No database, controller, DTO, service, repository class, runtime schema, SDL validator or new authority manifest is needed. Development package identity does not change SDL package semantics. |

The source and license record must identify the actual release artifact, its
immutable source revision, digest, license and included notices. An upstream
MIT notice does not establish permission to redistribute the ASD dictionary
or the full standard. Do not add a dictionary-copy pipeline.
Keep exact third-party notice text when updating `THIRD_PARTY_NOTICES.md`.
Do not rewrite historical verification records to describe the new setup.

## Extension boundary

Keep the release pin in its existing dependency authority. Keep the local
rule selection, vocabulary and supported-format selection in configuration
accepted by the released package. These are the seams for a later upgrade
or another supported format. Do not hard-code RAE terms into the shared skill.
Do not build a plugin registry or a second configuration schema for this seam.

If the package cannot express the needed boundary, resolve its interface
before deleting local behavior. Do not fork it inside RAE.

Separate general checking from the Sphinx invocation. Issues #1799, #1803 and
#1804 own the Go guards, build migration and publication. A later build cutover
must retain the same writing and meaning checks without embedding them in a
new builder. This issue must not publish future Go instructions early.

## Delivery evidence and gotchas

The extraction and #1931 are prerequisites for integration. The eventual RAE
PR must set and read back native GitHub blocking relations to both issues.
Linked prose is insufficient. This preflight changes no GitHub relations and
does not verify upstream readiness. LilRAE consumer work is not a prerequisite.
Use the requirement-free issue route; do not invent a requirement UID.

The integration needs evidence from a clean setup with no personal skill.
Record exact release inputs, platform, commands and results in its single PR.
Document the upgrade route and rollback to reviewed pins and compatible config.
A failed install or integrity check must not fall back to an unpinned tool.

Reuse `test_issue_1931_documentation_tools.py`, `test_vale_tool.py`,
`test_tooling_artifact_policy.py`, `test_public_docs_policy.py`, and
`test_issue_954_docs_publication_boundary.py` under
`implementations/python/tests/` for the boundaries they already cover.
The integration must demonstrate a failing Markdown sample for an enabled
shared STE rule and a passing correction. An existing RAES-only failure is
insufficient evidence that the shared checker runs.

Preserve code blocks, inline literals, exact output and source files.
Keep coverage of reStructuredText, unusual filenames, unsafe paths, malformed
catalogs, selected environments and failure propagation. Targeted mutation
checks should show that removing a required check or its failure status fails
the relevant case. Full documentation, integration and corpus checks stay in CI.

Record which actual assets became duplicates and where each consumer moved.
Delete only those duplicates after the shared consumer works. Similar prose
alone does not make local source contracts or vocabulary duplicate assets.
Reconcile severity, rule identifiers and narrow exceptions when rules overlap.
Do not enable a whole shared rule set without examining conflicts.

Manual review still checks Diataxis purpose, STE meaning and code accuracy.
Keep normative obligations, quantities, conditions, useful anchors and URLs.
Review changed prose in its rendered form, including links and text alternatives.
Test keyboard access if navigation changes. A passing linter is not proof of
STE conformance, accessibility or correct behavior.

This delivery does not introduce a custom analyzer, hosting service, preview
publisher, runtime dependency, corpus cleanup, or Go build migration.
It does not remove the existing reStructuredText route or replace legal text,
generated evidence, source verification, or RAE semantic authority.

## Preflight verification

File-local repository policy and the verified Vale check passed for this file.
The `docs-prose` command stopped during frozen environment sync: an uncached
dependency was unavailable offline. The direct Vale check used `ensure_vale()`
and `.vale.ini`. It did not establish that the complete nox stage passed.

Local HTML rendering and heading-order checks passed. Browser visual review
was unavailable because the sandbox refused a Chrome socket operation.
No executable behavior changed, so no tests or mutation checks ran here.
