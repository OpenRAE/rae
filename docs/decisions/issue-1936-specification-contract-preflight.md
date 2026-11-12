# Specification and contract documentation preflight

Issue: #1936. Requirement: none. Date: 2026-11-08.
Source revision: `c2fa955ee90d42950b075de3183dc2bef23ad9a4`.

This note explains design guardrails for the prose rewrite.
The supplied issue is the delivery contract. This note does not rewrite the
specifications or give an implementation plan.

## Authority and reader purpose

Keep exact rules at their current paths.
[ADR-009](adrs/adr-009-normative-artifact-authority-and-repository-structure.md),
[ADR-019](adrs/adr-019-normative-authority-boundary-manifest.md), and the
[authority manifest](../../specs/authority/authority-boundary.yaml) govern those locations.
The [style guide](../explain/reference/documentation-style-guide.md) governs prose review.
No new ADR, schema, registry, or tool is needed.

Reader purpose and normative authority are different properties.
Exact language rules are reference, even when their filenames contain “guide”.
Keep their obligations and exceptions. Keep conditions, units, identifiers, and notation.
Move separable rationale to explanation and reproduction steps to how-to guides
under the existing `docs/` structure. Keep links at the original locations.
Do not move binding clauses into a non-normative explanation.
Root indexes can route readers without reproducing contract rules.
Do not create four directory trees merely to represent the four reader purposes.

Code establishes observed usage behavior at the stated revision.
Specs and contracts give required meaning. Their authority does not depend on code.
For a discrepancy, retain the rule and identify the affected implementation,
evidence, and unsupported behavior. Do not weaken the rule to match a defect.
An ambiguous clause needs a recorded interpretation question, not a silent wording choice.
A change of meaning needs its own explicit scope. Existing contract governance applies.

## Documentation families in scope

This table groups the current repo. It includes prose outside Markdown.
It is a review boundary, not a replacement for the authority manifest.
The delivery PR must account for each maintained page and source passage within
these families. Name each protected exclusion and its reason.

| Family | Existing owner and treatment |
| --- | --- |
| `specs/README.md`, `specs/authority/` | Link to exact rules. Keep manifest roots and family IDs. Keep precedence unchanged. |
| `specs/agent-guidance/` | Review YAML comments and maintained guidance strings. Keep rule identities, conditions, and machine-readable shape. |
| `specs/candidate-synthesis/`, `specs/conformance/` | Keep source-neutral synthesis rules. Keep authorization and adapter claim limits. Separate task steps from exact contracts. |
| `specs/concept-authority/` | Preserve adopted, adapted, and native concept distinctions. Link the existing catalogs in `contracts/concept-authority/`. |
| `specs/evolution/` | Preserve versioning, deprecation, migration, and removal conditions. Review maintained context around protected lifecycle records. |
| `specs/sdl/` | Keep the language-neutral reference. Keep complete field, reference-edge, runtime-family, and diagnostic catalogs. Keep parser stages distinct. |
| `specs/supply-chain/` | Keep asset trust, manifests, requirement satisfaction, and control-context asset rules. A digest does not grant disclosure authority. |
| `specs/formal/` root | Review the index, composition and evidence-plane prose, and comments in both assurance YAML files. Keep policy and fulfillment separate. |
| Formal domains: `artifact-transformations`, `assessment`, `behavioral-relations`, `experiment-core`, `exploit-path-analysis`, `objectives`, `planner`, `realization` | Review each domain's prose. Keep equations and invariants. Keep removed features distinct from current features. Link to the source artifacts. |
| Formal domains: `participant-behavior-model`, `participant-episode-model`, `participant-runtime`, `participant-semantics` | Include nested semantic-coverage pages, runtime mappings, and machine-check guides. Keep model, runtime, backend, and proof claims distinct. |
| Formal domains: `runtime-contracts`, `runtime-control-plane`, `scenario-satisfiability`, `scenario-variation-trial-realization`, `sdl-phases`, `time-model`, `validation-admission-profiles`, `workflows` | Preserve phase, state, admission, time, supervision, cleanup, and workflow contracts. Keep formal artifacts and generated evidence intact. |
| `contracts/README.md`, `contracts/schemas/` | Review indexes and schema descriptions at their maintained sources. Published JSON remains normative; generation only proves compatibility. |
| `contracts/fixtures/` | Include all fixture READMEs and maintained reproduction instructions. Preserve fixture payloads, expected refusals, and generated data. |
| `contracts/schema-publication/`, root publication manifest | Review both publication and tombstone READMEs. Keep registry records and manifest shape unchanged. |
| `contracts/concept-authority/`, `profiles/`, `realization-envelopes/`, `provenance/` | Review maintained descriptions at their sources. Keep historical catalog revisions and profile coordinates. Keep provenance records and sealed content. |

The fixture introductions currently cover adaptive difficulty and SDL mixed
control, participant inject delivery, runtime package repositories, variation
points, and `sdl-yaml/v1`. Other fixture families still need accounting for
maintained descriptions; absence of a README is not an exclusion rule.

Schema prose can originate in model docstrings, `Field` descriptions, explicit
schema dictionaries, and invariant annotations outside `specs/` and `contracts/`.
Follow each changed output to its owner. Do not infer ownership from extension.
Put review evidence in the existing PR sections. Do not add another registry.

## Validation and generation

`raes_schemas.schema_bundle()` is the composition seam under ADR-121.
It joins public contributions from `raes_contracts`, `raes`, and `raes_processor`.
It then applies existing annotations and transforms.
Use those owners for maintained descriptions; do not add a parallel model or
import an upper package into a lower one to share prose.

`tools/generate_contract_schemas.py::write_schema_bundle(destination)` accepts
an explicit destination. Use a disposable repository-local or temporary
destination for comparison. Its command-line entry point writes published
schemas directly; it is not a read-only drift check.
`tools/check_generated_schemas.py` generates into a temporary directory and
compares file sets and exact bytes. Equal accepted inputs alone do not pass.

An equivalent description correction must remain limited to reviewed prose.
Keep contract IDs, filenames, `$id`, and references unchanged.
Keep defaults, constraints, and enum terms unchanged.
Keep invariant IDs, validator locators, and profile coordinates unchanged.
Review the published correction and owning source together under existing
governance. Do not overwrite authority with unreviewed generator output.
A published annotation edit is still a schema-file change.
Name its explicit scope and governance review. A prose label is not an exemption.
Descriptions affect output bytes and can affect shared-schema factoring.
Inspect every resulting bundle difference, including indirect model descriptions.
Unrelated generated data and formal proof artifacts remain unchanged.
If a correction changes contract meaning, it exceeds this issue's scope.
Flag any conflict between a requested description edit and a byte-frozen artifact
before editing. Do not change only its source and leave the bundle out of sync.

The publication checker reads the v2 manifest and per-contract records.
Records contain `contract_id`, `schema_path`, and `stability`.
They do not contain `content_hash` or `last_change`.
The amendment to ADR-061 records this change; its original body is historical.
`contracts/README.md` still claims hashes and a change ledger are required.
Correct that maintained guidance against the current checker and amendment.
Do not restore retired fields to satisfy stale prose.
Keep published identity unchanged. The compatibility checker ignores some annotations.

Reuse these independent validation layers:

- `raes/parser.py`, source-profile decoding, typed models, `raes/validator/`,
  and phase admission: raw YAML has its own rules. Normalized authoring objects,
  instantiated objects, materialized objects, and snapshots have distinct rules too.
- `tools/check_json_artifacts.py`, published schemas, owner model validators,
  and contextual resolvers: JSON Schema checks shape. It cannot prove cross-artifact
  truth or grant authority.
- `raes_contracts.contract_seals.seal_contract_fixture`: valid and
  context-invalid fixtures receive derived seals; invalid fixtures remain unchanged.
  A context-invalid fixture can pass structure and fail contextual admission.
- The existing validation-profile catalog and validation-basis disclosures:
  profile selection, achieved strength, limitations, and results are distinct.
- `raes_contracts.corpus`: installed package data and checkout defaults share
  one resolver. Explicit fixture/profile roots remain loader inputs.
  Preserve packaging through `implementations/python/pyproject.toml` and `hatch_build.py`.

## Shared layers and trust boundaries

Existing checks read maintained source. Readers then use a rendered repo page
or checked public HTML. Schema source also passes through the bundle builder
and equality check. This issue does not authorize publication.

| Layer | Canonical incumbent and required treatment |
| --- | --- |
| Authority and policy shapes | `check_authority_boundary.py`, `check_agent_guidance.py`, `check_assurance_policy.py`, `check_deprecation_lifecycle.py`, and concept-authority gates retain their YAML/JSON shapes and IDs. Change prose without changing policy decisions. |
| Parsed documentation | `tools/sdl_catalog_parity/` reads exact headings, columns, code-formatted tokens, summary comments, and owner links. Preserve its grammar and the marked implementation-evidence blocks in `specs/sdl/diagnostics.md`. Do not weaken checks to admit missing rules. |
| Evidence and security claims | Reuse `check_behavioral_relation_claims.py`, schema coverage and requirement-tracing gates, semantic-coverage tests, and existing formal evidence checkers. Finite examples, exhaustive bounded checks, runtime enforcement, backend conformance, and proof establish different claims. Waivers are gaps. |
| Authentication and authorization | No new endpoint or identity. Use `raes_runtime/control_plane_security.py` and `control_plane_api/_auth.py` for runtime examples. Keep strict config types, target-bound principals, and route authority. Keep participant/controller/audience bindings distinct. Role or schema validity does not grant every operation. |
| Secrets and environment shapes | Reuse `raes_contracts/secret_references.py`, account credential contracts, `raes/runtime_environment.py`, and existing redaction validators. Keep literal values and `value_from` exclusive, preserve sensitivity/provenance, and keep operator secrets outside authored SDL. Use synthetic references, never host credentials. |
| OS and tool execution | Reuse frozen environments, admitted tools, fixed argument lists, and safe output paths. Keep tokens out of process arguments. Do not interpolate secrets in shell commands or read secret files. Do not provision native resources or add an unapproved tool source. Formal replay keeps its offline sandbox and resource limits. |
| Prose selection | `docs-prose` uses `safe_repo_path`, catalog validation, and Vale arguments after `--`. Retain `.vale.ini`, `styles/RAES/`, `tools/vale_tool.py`, and locked artifact admission. No new analyzer or external prose processing. |
| Public source and output | `check_public_docs.py`, `public_docs_markup.py`, and `public_docs_guard.py` contain Sphinx reads and output within `docs/public/`. Link repository authorities with absolute repository URLs; do not include or copy them into the hosted tree. |
| Build and host config | Reuse `noxfile.py`, `tools/nox_support/`, `docs/public/conf.py`, `redirects.json`, `docs/Makefile`, `.readthedocs.yaml`, and `.github/workflows/docs.yml`. Keep current roots and token permissions. Keep deployment conditions. No build migration. |
| Errors and observability | Reuse `raes_contracts.errors`, `diagnostics.portable_diagnostic_payload`, `operational_logging.run_application`, `PolicyFailure`, and `SessionReporter`. HTTP uses `control_plane_api/_responses.py`; CLI and MCP keep their existing sanitized boundaries. Do not show raw exception values, credentials, input documents, or tracebacks in revised output examples. |
| Storage and workflow | Use maintained files, temporary build output, the packaged corpus, and existing PR evidence. No database, DTO, controller, service, or repository class is needed. No new error hierarchy, logger, validator, or workflow engine is needed. Keep hygiene, private-key checks, and Gitleaks. |

Security examples must retain the difference between a reference, authorization,
delivery, and evidence of an effect. Hashing does not declassify private content.
Do not execute a target-conformance or reproduction command merely because it
appears in a guide. Check its effects, prerequisites, output, and owner first.

## Existing check contracts and delivery evidence

The current authority, SDL catalog-parity, schema-publication comparison against
`HEAD`, and generated-schema equality checks pass at the source revision above.
These results give a baseline. They do not prove unchanged meaning or full conformance.

`test_issue_219_participant_semantic_coverage.py` parses clause excerpts,
invariant headings, family rows, and code blocks.
When prose changes, its crosswalk excerpts can need the same change.
Keep the source clause and evidence relation; do not delete coverage assertions.
The assurance checker registers formal subdirectories by their README files.
Do not create or move domain READMEs as an incidental navigation change.
Proof manifests, research captures, historical catalogs, ADR pins, and lineage
records can bind paths or bytes. Check their owners before changing adjacent prose.
Use the research-capture procedure if the work records new source-bound research
evidence. This rewrite does not require a new capture.

Use existing targeted checks for changed families: authority and catalog parity,
publication and generated equality, explicit JSON-artifact paths, and relevant
parser, contract, seal, or semantic-coverage test modules/cases.
Use `docs-prose` on explicit changed Markdown/reStructuredText paths.
Review YAML/JSON descriptions, source docstrings, and other unsupported prose manually.
The style guide supplies the existing Vale stdin route for maintained passages
inside protected files. A clean lint result proves neither accuracy nor STE conformance.
Full test, integration, fuzz, proof, and completion suites remain CI/CD work.
No behavior changes are proposed here, so mutation testing adds no evidence for this note.

Record each page's purpose, source paths, and revision in the delivery PR.
Record the review of unchanged meaning. Give commands, results, gaps, and exclusions.
Review each changed section, not only representative pages.
Follow exact reference links from relevant SDL, backend, API, and contributor pages.
Keep useful heading anchors; a page redirect does not preserve a removed fragment.
Sphinx link checks ignore some repository URLs, so verify paths and fragments explicitly.
Use `docs-local` and `docs-links` for affected public links and rendered pages.
Repository-only prose needs a local rendered view as well.
Check heading order, descriptive links, diagram text alternatives, and keyboard
access for changed navigation. Record unverified rendering separately.

## Extension seams and boundaries

Stable reference URLs and existing indexes are the reader-facing extension seam.
A later explanation or procedure can link to the same rule without copying it.
The authority manifest owns classification; existing catalogs own terms and profiles.
The schema contribution functions own descriptions.
`write_schema_bundle(destination)` selects output paths. Corpus loaders accept explicit roots.
`PUBLIC_DOCS_ROOT` sets the published source root. Keep these parameters.
Do not add path heuristics or a second registry for the next prose family.

OpenRAE/rae owns portable language, processor, runtime admission, contracts,
and conformance artifacts. Backend distributions own native effects and cleanup.
OpenRAE/lilrae owns its backend; Shifter owns its integration artifacts;
OpenRAE/env-packs owns pack authoring and distribution.
State the actual repository, artifact producer, and revision for each runtime
or backend instruction. Fixture success does not qualify a live backend.

The checkout reports RAES 11.0.2 and retains the Python Sphinx/MyST build.
That fact does not establish the deployed site's revision.
Keep supported-release instructions separate from development-only references;
do not link unreleased rules as if the supported package implements them.
Issue #1803 owns Go build and instruction migration; #1804 owns publication.

Non-goals are runtime or parser repairs, schema semantics or identity changes,
new schemas or validators, formal proof changes, fixture-data rewrites, backend
integration, release metadata edits, publication, and build migration.
Do not rewrite frozen history, duplicate normative text, promote finite evidence
to universal claims, suppress failing checks, or add a custom documentation tool.
One later implementation PR delivers #1936 through the existing requirement-free
route. Do not invent a requirement UID to satisfy requirement-backed gates.

## Preflight verification

These commands passed with the existing checkout environment:

```shell
implementations/python/.venv/bin/python tools/check_authority_boundary.py
implementations/python/.venv/bin/python tools/check_sdl_catalog_parity.py
implementations/python/.venv/bin/python tools/check_schema_publication.py --base-rev HEAD
implementations/python/.venv/bin/python tools/check_generated_schemas.py
implementations/python/.venv/bin/python tools/check_repo_policy.py --check-set file-local docs/decisions/issue-1936-specification-contract-preflight.md
```

The `docs-prose` session stopped at environment setup: it could not fetch pinned
`hatchling==1.33.0` from PyPI. No prose stage ran in that session.
A direct check through `tools.vale_tool.ensure_vale` passed with `.vale.ini`.
The existing MyST HTML5 renderer produced local HTML with file insertion and
raw content disabled. Its heading order, two tables, and four link targets were
reviewed. No diagrams or controls were added. Browser visual and keyboard
review were not performed. No full test suite or publication ran.
