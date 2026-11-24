# Research discovery architecture preflight

This explanation records design boundaries for issue #1937. The issue is the
delivery contract. It has no formal requirement. This note adds no runtime
behavior and changes no normative meaning. No new ADR is needed.

The inspected source is `e71ddbc29e9e06658ddbe2b2c12edf8ed424f044` on
`1937-research-discovery-paths`. Paths below are relative to this repository.
The [documentation style guide](../explain/reference/documentation-style-guide.md)
owns writing, source review, protected text, and rendered review rules.

## Reader and authority boundaries

Keep `concepts.md` as explanation and `research.md` as an explanation entry.
Keep `citation.md` as a how-to guide and `limitations.md` as reference.
All four paths are under `docs/public/`. Retain their published addresses.
Separate operating procedures only when they obscure the page's purpose.
Keep useful heading anchors, including the four existing concept headings.

The public source root remains `docs/public/`.
Link to exact repository files and sections for specifications, research records,
and ADR rationale. Do not copy or include those records in the hosted build.
The public pages explain the evidence. A directory listing cannot finish a route.

Use the authority classes in `specs/authority/authority-boundary.yaml`, ADR-009,
and ADR-019. Specifications and published contracts define required meaning.
Code and tests establish implemented behavior at a named revision.
Examples, explanations, research notes, and this note cannot redefine a contract.
Report a code/contract conflict and obtain its resolution. Do not hide it through
a prose change or silently strengthen a normative obligation.

Define specialist terms at first use and link to their exact authority.
The [glossary](../explain/reference/glossary.md) and
[canonical reference map](../explain/reference/canonical-reference-map.md)
are discovery aids. Their status statements also need comparison with code.
Keep the technical detail in linked explanations.

## Revision and ownership boundaries

Published instructions describe the supported Python release until the common
cutover. Go source in this checkout does not authorize Go installation guidance.
Issue #1803 owns the build and instruction migration. Issue #1804 owns publication.
Keep Sphinx/MyST, the frozen docs dependencies, and the existing publishers.

Bind each behavior claim to the source actually examined. A branch URL is a
discovery link, not immutable evidence. Use a full commit or verified release tag
for evidence links. Record the mapping between a release and its source commit.
At this checkout, the manifest and Python version file both say `10.2.0`.
Local `git describe --tags --abbrev=0` returns `v3.2.0`.
Neither observation establishes the latest supported public release.
Confirm release identity before delivery. Do not edit release-owned version files.

`OpenRAE/rae` owns the current language, processor, contracts, portable backend
interfaces, and stubs. Concrete backend implementation and credentials belong
to each external backend project. A published envelope does not ship a backend.
The [runtime boundary](issue-1891-runtime-repository-boundary.md) records a split
at cutover. Its working destination name is explicitly unapproved.
Name the actual repository and artifact owner when giving runtime or backend
tasks. Do not present the proposed destination as an available product.

## Research boundaries and existing sources

Each topic needs a question, its significance, defined concepts, an existing
example or inspection task, authoritative sources, evidence, limits, and a
bounded next investigation. Distinguish demonstrated behavior, a hypothesis,
an open question, and a historical finding beside the relevant claim.
These are editorial requirements, not a new machine-readable research schema.

The following source anchors identify existing owners. They are not completed
reader routes or claims that the checks have passed at the supported release.
Python package and test paths below start at `implementations/python/`.

| Question boundary | Existing authority and inspection material | Evidence limit |
| --- | --- | --- |
| What meaning survives scenario variation or another realization? | `specs/sdl/document-model.md`, `specs/formal/scenario-variation-trial-realization/README.md`, ADR-084; `packages/raes/parser.py`, `packages/raes_processor/trial_compiler/`; `tests/test_sce_002_trial_compiler.py` | Scenario meaning, selected trial identity, scheduling, and backend effects remain separate. Deterministic compilation does not prove deterministic execution. |
| What does a realization difference establish? | `specs/formal/realization/envelope-semantics.md`, ADR-070; `contracts/realization-envelopes/`; `packages/raes_contracts/realization_envelope_carrier.py`; `tests/test_realization_envelope_contract.py` and `tests/test_realization_envelope_relation.py` | Keep backend concern declarations distinct from scenario-envelope relation checks. Disposition, observation source, configuration, and actual native readback are separate facts. Historical libvirt evidence is not current backend qualification. |
| What can a participant infer or control? | `specs/formal/participant-semantics/participant-predicate-opacity.md`; `contracts/profiles/behavioral-relation/participant-opacity-baseline-v1.json`; `packages/raes_processor/participant_opacity/`; `tests/test_issue_961_participant_opacity.py` | A finite possible-point analysis needs its exact profile, bounds, observer, memory, strategy, and order. It proves neither runtime mediation nor backend security. Control permission, execution, delivery, and observation remain distinct. |
| What evidence supports another investigation? | ADR-055 and ADR-066; `contracts/schemas/experiment-core/experiment-evidence-record-v1.json`; `packages/raes_contracts/contracts/experiment_run_evidence_validation.py`; `tests/test_exp_732_evidence_provenance.py` | A reference or matching digest identifies material. Content-backed validation checks additional joins. Neither proves scientific validity, equal outcomes, exact replay, or independent reproduction. |
| What does formal assurance establish? | `specs/formal/participant-semantics/isabelle/Participant_Opacity.thy` and `participant-opacity-proof-evidence.json`; `docs/research/formal-semantic-validation/`; `tools/check_participant_opacity_proof.py` | Separate bounded tests, finite model checking, abstract theorem proof, runtime enforcement, and backend realization. The pinned theorem evidence excludes correspondence with the Python checker and concrete deployment claims. |

The short route starts from `docs/public/tutorials/first-scenario.md` and its
checked-in example. Describe its parse and formatting results accurately.
The deeper route reaches specific specifications, code, evidence records, and
ADR rationale. At least three distinct research routes must reach concrete
material and a bounded next question. Cover all five topic boundaries above.

Primary literature must support an exact attributed claim. Existing research
notes supply leads, not verified citations or authority for RAES semantics.
Compare the original publication with the claim and retain its bibliographic
facts. Do not turn citations into an unrelated reading list.

## Cross-cutting layers to retain

| Layer | Canonical owner and design constraint |
| --- | --- |
| Public source and configuration | `tools/check_public_docs.py`, `tools/public_docs_markup.py`, `tools/public_docs_guard.py`, and `docs/public/conf.py` own containment, markup inspection, dependency checks, and output inventory. Keep bounded inputs, regular files, and the prohibition on escaping includes, downloads, file URLs, and symlinks. Do not add remote includes or executable page extensions. |
| Source and artifact shapes | `raes.parse_sdl_file`, the bounded YAML loader, typed models, and `SemanticValidator` own SDL admission. `raes_contracts.json_ingress` and the owning contract models admit JSON and profile inputs. Use public entry points in examples. Do not replace these layers with generic YAML loading, unchecked dictionaries, or a documentation-only validator. |
| Runtime configuration and authorization | The discovery route needs no live service. If a linked task exercises runtime behavior, retain `ControlPlaneConfiguration`, `control_plane_security.py`, `control_plane_api/_auth.py`, and `control_plane_api_guards.py`. Existing installed-provider checks, principal/target authorization, and request limits still apply. Do not relax them to complete an example. |
| Secrets and environment binding | Use synthetic checked-in examples. Keep credentials, private locators, hidden participant information, host paths, and environment dumps out of pages and reports. Secret references remain references. This work adds no environment-driven source root, version, provider binding, or token requirement. Pre-commit private-key and Gitleaks checks remain in place. |
| Host tools and process arguments | `tools/vale_tool.py`, `tools/verified_tool_installation.py`, and the tooling artifact lock own tool selection and byte verification. Use frozen environments and explicit repository paths. Do not add an unpinned installer, shell interpolation of document text, credentials in process arguments, or a new external processor. |
| Failures and observability | Retain `PolicyFailure`, `InvalidInputError`, `OperationalError`, `run_application`, and nox `SessionReporter`. Keep parser diagnostics and Sphinx/Vale failure status. Do not create another exception hierarchy, result envelope, logger, or audit stream. Do not publish raw exceptions, response bodies, secrets, or private evidence to explain a failure. |
| Evidence and persistence | Reuse existing run, capture, provenance, sensitivity, redaction, and evidence models and their content-backed validation. ADR-066 separates operational observation from research evidence. This change needs no database, store, repository class, DTO, or new citation/evidence manifest. Raw records remain outside the public build. |
| Build and publication | `tools/nox_support/config.py` and `test_lanes.py`, `noxfile.py`, `docs/Makefile`, `.readthedocs.yaml`, and `.github/workflows/docs.yml` define the existing path. Retain the installed-distribution version and honest unknown fallback. This issue changes no publisher permissions, destination, workflow, or release authority. |

Schema status comes from `contracts/schema-publication-manifest.json` and its
registered publication entries. A versioned filename does not imply stability.
Reuse `tools/check_project_positioning.py` for bounded capability claims,
`tools/check_behavioral_relation_claims.py` for relation claims, and the existing
authority, concept-authority, SDL-lineage, and example-library gates.
Do not reproduce these checks in Vale rules or another documentation script.

## Citation, links, and delivery evidence

Keep the existing BibTeX author's name, title, year, license, and repository URL.
The index has the same citation. Avoid contradictory copies.
Explain exact software version/commit, scenario identity, backend artifact and
configuration, contract/profile revisions, and evidence identity using existing
carriers. Include digests where the carrier defines them.
Do not invent a DOI, release receipt, backend certificate, or validation result.
Explain unavailable or restricted evidence without publishing it.

`limitations.md` is the public limits page. The separate
`docs/explain/sdl/limitations.md` is a repository explanation, not a second
hosted source. Its historical corpus counts and status claims need fresh review
before reuse. Maintainer facts come from `MAINTAINERS.md` and `GOVERNANCE.md`.
Capability limits need the relevant code, contracts, tests, and evidence.

Incoming public links include `README.md`, `docs/public/index.md`,
`docs/public/sdl/index.md`, and `docs/public/participant-control.md`.
Search the whole repository for incoming paths, hosted URLs, and fragments.
Keep the established map in `docs/public/redirects.json`.
`check_public_docs.py` checks its exact map and generated redirect output.
Page redirects do not establish that old heading fragments still resolve.

Sphinx link checking ignores links into `OpenRAE/rae` and the retired repository
identity. Check those targets and anchors locally at the referenced revision.
A file present at HEAD does not prove that it exists in a cited release.
Check external primary links through the existing link-check lane.

Use changed-path `docs-prose` and file-local repository policy for local feedback.
Reuse focused cases in `tests/test_public_docs_policy.py` for executable snippets
and redirect behavior. Add tests only for changed executable behavior.
Full documentation, policy, proof, integration, and test suites remain in CI.
This prose-only preflight needs no mutation test or Go architecture-model change.
Use `tools/requirement_context.py` and the existing requirement-free gate path.
Do not fabricate a requirement UID for #1937.

The delivery PR records each section's purpose, sources, exact revision, commands,
results, corrections, unverified claims, and protected-text exclusions.
Follow both newcomer and experienced-researcher routes through their endpoints.
Distinguish an author walkthrough from actual user testing.
Review rendered heading order, descriptive links, diagram alternatives, and
keyboard access for changed navigation. Check redirects and useful fragments.
A source review or clean Vale result cannot establish accessibility or full
ASD-STE100 conformance. Record what was examined and what remains untested.

## Extension seam and non-goals

Extend research discovery through curated question sections and ordinary links
under the existing public root. Each route names its own source revision,
contract/profile version, backend configuration, and evidence boundary.
These coordinates allow another backend or study to differ without changing
canonical contracts. They do not require a registry, route schema, or generator.

This issue adds no runtime feature, parser, API, backend, security policy,
schema, proof, research campaign, or hosted audit archive.
It does not migrate the build, publish Go instructions early, create a service,
or transfer data to a new destination. Keep one implementation PR.
Keep dependency management in the existing GitHub blocking API.
Do not rewrite pinned captures, accepted ADRs, legal text, or generated output.
New deliberate source-bound research uses `tools.research_capture record` under
the existing [capture rules](../develop/research-captures.md).
Routine documentation verification needs no new capture or numbered publication.

## Preflight verification

File-local repository policy passed before and after this note was added.
The existing `docs-prose` session passed on this file, with no Vale findings.
The default uv cache was read-only. The successful run used a temporary cache
and offline mode with the existing frozen environments.

Three explicit cases in `implementations/python/tests/test_public_docs_policy.py`
passed: the legacy redirect contract, the repository link-check exclusion, and
the checked-in first-scenario parse. No full suite ran.

The installed Markdown parser rendered this note to a local temporary HTML file.
Structural review found eight headings in order and five existing local targets.
Chrome could not start because the sandbox refused its crash-reporting socket.
Visual and keyboard review remain unverified. No diagrams or controls were added.
The public pages and reader routes are unchanged and have not been user-tested.
