# Research and decision records preflight

Issue: #1939. Requirement: none. Date: 2026-11-10.
Source revision: `e64ef3030f158e1cd5979df427e57423ead6ec2d`.

Purpose: explanation for the later implementation.

Keep evidence fixed and improve the routes to it.
The supplied issue defines delivery. The
[adoption design and ownership table](https://github.com/OpenRAE/rae/issues/1909#issuecomment-6669941664)
define the section boundaries. This note adds guardrails, not an implementation plan.

No new ADR, schema, tool, or runtime component is needed.

## Reader purpose and authority

Use existing entry pages and local indexes before adding another destination.
`docs/public/research.md` owns the hosted research route.
`docs/README.md` and `docs/decisions/index.md` expose repository records.
`docs/decisions/adrs/README.md` remains the human ADR index.

Do not build a second document or evidence registry.

Decision rationale and current research questions are explanation.
Exact requirements, findings, captures, and formal results are reference.
An entry page can link to each form without copying its contents.
Keep active procedures separate from dated accounts of commands and results.

An old command is evidence of an observation, not necessarily a supported procedure.

Keep these distinctions visible in maintained introductions:

- Decision status is not evidence status or implementation status.
  An accepted ADR does not prove that its design has shipped.
  Preserve the ADR-021 claim states and their stated scope.
- `docs/specs/formal.md` is an introduction; normative authority remains in
  `specs/` and `contracts/` under ADR-009 and ADR-019.
  Reuse `specs/authority/authority-boundary.yaml` and `tools/check_authority_boundary.py`.
- Requirement snapshots in `docs/requirements/` retain their statements and metadata.

  Their dates and status do not establish current delivery.
  Governance scope JSON is workflow authority, not a product schema.
- `docs/raes/inventory/` owns the capture methodology.
  Backend proof bundles retain their backend owner.
  `docs/lessons/README.md` defines dated integration findings, not another decision log.

For each route, expose the record's revision, status, replacement link where applicable,
and present applicability. Use the existing record as the source for these facts.
Keep release, source commit, capture identity, and observation date distinct.
Do not replace them with one ambiguous version label.

Check current claims against code at the named release or commit.
Check historical claims at their pinned revision and preserve any reproduction limit.
Report a conflict with normative meaning; do not repair it through explanatory prose.

## Preservation and coverage

Keep accepted ADR text, amendments, superseded decisions, capture bytes, published
research, quotations, formal artifacts, and historical findings at their existing paths.
Use surrounding maintained context to explain their current relevance.
Do not add status banners inside an immutable record merely to improve navigation.

ADR-059's amendment for #1929 and `tools/check_adr_immutability.py` govern current ADR checks.
`adr-index.yaml` holds accepted paths and amendment references, without content digests.
The gate needs the real base revision to detect unrecorded edits.
Do not restore retired digest fields from the ADR's original description.

ADR-096's current historical catalog uses occurrence counts, not whole-file hashes.
Neither a catalog exemption nor a passing identity check proves byte preservation.
Use the Git comparison and each evidence family's existing checks for that purpose.
Keep superseded and deprecated ADRs frozen even though they leave the accepted set.

The delivery PR reconciles tracked documentation across the repository with #1909.
The seven issue roots are not the whole coverage boundary.
Every maintained page needs its existing delivery owner and reader purpose.
Each preserved artifact needs a reason and a useful entry route.

Reuse prior section evidence, including the #1936 verification record, at its stated revision.
Refresh coverage at the actual delivery base; old file counts are not a complete inventory.
Record coverage and exclusions in the PR's existing evidence sections.

Classify content by its consumers as well as its extension.
Planned `.go.txt` signatures, dependency lists, smoke inputs, and Vale vocabulary are code or data.
Preserve them and review their maintained descriptions and links.
Include introductions to JSON evidence, proof sources, diagrams, and other non-Markdown artifacts.

Do not omit mixed pages because a checker excludes one preserved passage.
#1909 assigns root release and legal navigation to #1938.
`CONTRIBUTING.md` already links those records at this revision; verify the final route.
Keep legal text and release-please output unchanged.

## Cross-cutting layers

The flow is maintained source to local checks and rendered review, then the existing CI boundary.
Hosted pages link to repository records; they do not read those records into the build.
This work adds no application service, controller, DTO, state store, or trust boundary.

| Layer | Existing owner and required treatment |
| --- | --- |
| Paths and markup | Reuse `safe_repo_path` in `tools/policy/common.py`, `tools/public_docs_markup.py`, and Sphinx/MyST. Preserve path containment, parser behavior, and directive checks. A hidden toctree does not exclude files from search or downloads. |
| Hosted source and output | Reuse `tools/check_public_docs.py`, `tools/public_docs_guard.py`, and `docs/public/conf.py`. Keep includes, assets, downloads, and file dependencies inside `docs/public/`. Use explicit repository URLs for outside records. Preserve the checks of HTML routes, search, sitemap, and published assets. |
| Configuration shapes | Preserve the exact redirect-map contract in `check_public_docs.py`. Keep ADR and historical catalog shapes under their current validators. Leave requirement-scope bindings, authority manifests, locks, and workflow settings unchanged. Do not add frontmatter fields that imply a new registry. |
| Evidence shapes and persistence | Reuse `tools/evidence_bundle_index.py`, `tools/research_evidence.py`, and the formal and specification checker packages. They own bounded JSON loading, closed fields, path checks, digests, joins, history retention, and capture receipts. Keep their identities and schemas unchanged. |
| Prose selection and protection | Reuse `_run_docs_prose` in `tools/nox_support/test_lanes.py`. Its explicit paths or verified base revision select changed prose. Its catalog validators and ADR status parser identify protected files. An exemption still requires meaning review of new maintained passages. |
| Tool acquisition and host | Reuse `tools/vale_tool.py`, `tools/documentation_tools.py`, frozen environments, and `implementations/tooling/artifacts.lock.json`. Keep verified installation, local checking, fixed argument lists, and `--` before prose paths. Do not bypass failed acquisition or file-insertion restrictions. |
| Authentication and secrets | No runtime authentication or environment-binding surface changes. Preserve the existing Pages workflow permissions and main-only deployment. Retain commit secrets checks. No credentials, private environment dumps, tokens in argv, or raw private logs belong in prose or PR evidence. Do not access the user's secret file or transfer artifacts to another service. |
| Errors and observability | Reuse `PolicyFailure`, `raes_contracts.errors`, `operational_logging.run_application`, and nox `SessionReporter`. Keep bounded diagnostics and check results distinct from research observations. No new exception hierarchy, log sink, API error envelope, or diagnostic dump is needed. |
| Workflow and verification | Reuse `.ground-control.yaml`, `.gc/plan-rules.md`, the PR template, `noxfile.py`, and canonical CI. This is requirement-free: do not invent a UID or scope manifest. Preserve existing CI gates and issue ownership. |

Runtime credentials, config validators, and API refusals are outside this change's execution path.
If a maintained procedure includes them, verify it against its owning code and supported revision.
Do not turn a historical backend probe into a current authenticated runtime procedure.
OpenRAE/rae owns portable contracts; backend distributions own native effects and credentials.

Name the actual repository and artifact owner without inspecting another checkout.

## Extensibility and design traps

Stable destination links are the seam for later research questions and evidence families.
Status and applicability belong in maintained context, sourced from the owning record.
New evidence uses existing family discovery, not a hard-coded list of newest files.
`latest_recorded_release_path` selects recorded cases for replay;
`current_release_path` with a repository root checks for matching live source.

Neither a filename nor the largest release number alone proves current applicability.

Routine prose edits do not require research captures.
If new source-bound research is deliberately recorded, use the existing
[capture workflow](../develop/research-captures.md).
Do not repin old observations, allocate numbered releases on a feature branch,
or append new captures to shared narrative indexes.
Do not run historical scripts that provision services merely to check a link.

Two inspected routes show why present context matters:
`docs/research/partial-description/index.md` still describes ADR-105 as proposed,
while the ADR is accepted. Preserve dated design evidence while correcting maintained context.
The #1936 verification record also identifies crossing evidence removed under #1949.
Use its original revision where needed; do not restore deleted artifacts or claim present reproduction.

Research questions must distinguish hypotheses, accepted design, bounded results, and unverified behavior.

## Delivery boundaries and evidence

The later PR must check five routes from the entry pages.
These lead to an accepted ADR, a superseded decision, a formal result, a research capture, and a current question.
Each route must expose status, source revision, applicability, and evidence limits.
Follow the final research and exact-reference routes after all section rewrites.

Repeat first use from a clean setup with stated release artifacts and no undeclared local dependencies.
Record source paths, revisions, commands, results, corrections, and preserved uncertainty in the PR.

Use explicit changed paths with `docs-prose` and targeted local checks.
Full documentation builds, link checks, formal replay, integration, and test suites stay in CI.
The formal evidence checker can execute participant replay; it is not a link-only command.
Sphinx ignores this repository's GitHub URLs during link checking.

Verify repository paths, pinned revisions, useful fragments, and any redirects separately.
Review rendered repository prose as well as hosted pages for headings, link text, and diagram alternatives.
Check keyboard access when navigation changes. Do not use color alone for status.

Vale does not prove accuracy, page purpose, or full STE conformance.

This preflight does not rewrite the records or complete those reader journeys.
The implementation stays within one PR for #1939.
No runtime repair, contract change, generated evidence churn, new inventory framework,
custom documentation tooling, publication, or build migration belongs in it.
#1803 owns Go instructions and build migration; #1804 owns publication at cutover.
Keep published instructions aligned with the supported release and verify that release before editing.
