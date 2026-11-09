# Specification and contract documentation review

This record gives the scope, sources, results, and limits for issue #1936.
It is a delivery reference. The specifications retain their own authority.
The review baseline is `c2fa955ee90d42950b075de3183dc2bef23ad9a4` on `dev`.
The published Python instructions target RAES 11.0.2.

## Reader purposes

Exact rules remain in `specs/` and `contracts/` as reference material.
Their entry pages link to the existing explanations and authoring guides.
The new [local check guide](../develop/check-specification-contracts.md) has
one purpose: compare a checkout with its specifications and contracts.
It separates a read-only check from a generator that writes published files.
No page moved. No redirect is needed.

The page inventory below accounts for all 122 Markdown pages in these roots.
“Revised” means this delivery changes maintained prose or heading controls.
“Retained” means the existing reference remains suitable for its purpose.
Both groups were included in the rendered review.
The metric exceptions apply only to the exact paths in the second inventory.

## Sources and corrections

All local source paths below refer to the review baseline above.
The four public entry pages link to exact references at tag `v11.0.2`.
The linked files exist at that tag. The development check guide states its
separate revision and does not promise release support for development work.
Issues #1803 and #1804 retain ownership of the Go build and publication.

| Family | Sources checked | Result |
| --- | --- | --- |
| Authority and agent guidance | `specs/authority/authority-boundary.yaml`, ADR-009, ADR-019, `tools/check_authority_boundary.py`, `.pre-commit-config.yaml` | Keep authority roots and governance classifications. Correct the obsolete pre-push claim. |
| SDL catalogs and source format | `raes_contracts`, `raes`, `tools/check_sdl_catalog_parity.py`, `test_sdl_source_format.py` | Keep catalog entries and source rules. Distinguish raw YAML checks from sealed payload checks. |
| Concepts and profiles | `contracts/concept-authority/`, `contracts/profiles/`, ADR-012, `raes_contracts/schema_contributions.py` | Keep concept identifiers, vocabularies, profile rules, and bindings. Repair the ADR-012 link. |
| Evolution and publication | ADR-075, ADR-009 and ADR-061 amendments for #1929, `tools/check_adr_immutability.py`, `tools/check_schema_publication.py` | Describe per-contract publication records. Git stores history; records do not store content hashes. |
| Supply chain and provenance | `contracts/provenance/`, ADR-071, ADR-077, ADR-098, published schemas | Keep trust rules, signatures, identifiers, and pinned lineage records. |
| Objectives and assessment | ADR-079, ADR-109, `raes/objectives.py`, `raes/semantics/objectives.py`, `raes/semantics/objective_semantics/`, targeted semantic tests | Replace retired condition and actor summaries with the accepted assertions and ownership rules. Keep thresholds and time windows. |
| Composition and workflow | ADR-053, `raes_contracts/workflow/semantics.py`, `raes/semantics/`, targeted objective and assessment tests | Describe delivered modules. Remove retired aggregation tests as current evidence. |
| Participant invariants and coverage | `specs/formal/participant-semantics/`, `test_issue_219_participant_semantic_coverage.py`, `test_participant_semantics_invariant_oracle.py` | Keep rule identifiers, heading boundaries, evidence tables, and invariant meaning. Match the I15 source excerpt after punctuation cleanup. |
| Runtime and backend contracts | `raes_runtime`, `raes_contracts`, `raes_processor`, targeted SEM-218 and manifest tests | Correct moved owner paths. Describe all seven SEM-200 phases for SEM-218 without claiming full SEM-200 or native backend support. |
| Formal relations | ADR-081, `tools/check_behavioral_relation_claims.py`, current formal-package guide | Separate historical results, executable checks, and deliberately unproved claims. Repair ADR-070 and the removed reproduction link. |
| Other formal families | Their linked schemas, models, invariant statements, and evidence sections | Keep mathematical notation, units, bounds, obligations, and proof status. No proof artifact changed. |
| Fixture families | Six fixture READMEs, their owning validators, and selected corpus tests below | State what valid, invalid, and context-invalid cases prove. Keep all payload bytes. |

The old condition-template diagnostics are not current conformance evidence.
The current compiler reports `evaluation.condition-template-ref-unbound`.
The processor manifest rejects `realization_support`; the backend manifest
owns that field. Shared manifests can carry `concept_bindings`.
The schema index now states these existing boundaries.

The historical crossing evidence is available at
[its original revision](https://github.com/OpenRAE/rae/blob/4120ee77a49e89dfe273016e7721b52b3b1b7dfd/specs/formal/participant-semantics/participant-crossing-reproduction.md).
Commit `80b089b55b1f09ce594657d9c81cfa1f9a05e8a7` removed the retained captures
and reproduction records under #1949. The current package does not supply
an independent reproduction. The introduction states that limit.
The historical result and its proof limits remain separate from current checks.

## Protected material and schema descriptions

No JSON schema, fixture payload, proof source, generated bundle, legal text,
external quotation, version, or changelog changed.
Existing fenced and indented code blocks in the revised reference pages are
identical to the baseline. The five edited YAML files parse to the same data.
Only their maintained leading comments changed:

- `specs/agent-guidance/agent-guidance.yaml`
- `specs/authority/authority-boundary.yaml`
- `specs/evolution/deprecation-records.yaml`
- `specs/formal/assurance-policy.yaml`
- `specs/formal/assurance-fulfillment.yaml`

Schema descriptions were traced through the existing source owners:

- `implementations/python/packages/raes_schemas/bundle.py`
- `implementations/python/packages/raes_contracts/schema_contributions.py`
- `implementations/python/packages/raes/schema_contributions.py`
- `implementations/python/packages/raes_processor/schema_contributions.py`
- `implementations/python/packages/raes_contracts/contracts/schema_invariants.py`

Model fields and annotations supply generated descriptions.
`add_raes_invariant` supplies invariant text to the bundle.
These descriptions are part of published schema bytes. They were reviewed
with their reference links and retained. Editing them independently would
break the byte-equality contract. This delivery does not change schema meaning
or bypass schema governance.
The publication, profile, concept, provenance, and realization catalogs retain
their typed records and identifiers. They are not substitute prose registries.

## Language review and exceptions

The language review used ASD-STE100 Issue 9 and the repository style guide.
The official local PDF has SHA-256
`d1f4ea9e7cd6e46b47aa9057209f99e78c0e9cfc4e27a5b07895b05c1a166431`.
The standard and its dictionary were not copied into the repository.
The review shortened sentences, used direct verbs, and kept each rule's
conditions, actor, obligation, and technical terms.
Exact identifiers, mathematical expressions, technical names, and schema fields
remain unchanged. A clean Vale result does not certify full STE conformance.

Vale 3.15.2 still gave 93 whole-page reading grades above 11 after prose edits.
The table below records those scores before the exceptions.
These pages contain required domain terms, catalogs, and formal rule names.
Changing those terms to lower a whole-page metric would damage exact reference.
The existing `.vale.ini` therefore disables only `RAES.ReadingLevel` for
each listed path. It does not disable any other rule.
Inline controls did not affect this metric in the pinned Vale version and were
removed. Heading controls retain exact rule names and parser boundaries.

The existing documentation-tool test module now checks the actual Vale binary.
The listed-path control first failed with grade 26.52; three other cases passed.
After the config change, all four cases pass. An unlisted reference and an
ordinary guide still fail the metric. Plain-word and repetition checks still
fail in a listed reference. No new analyzer or dependency was added.

## Local verification

The checks ran on Linux with the frozen Python and tooling environments.
They used Python 3.14.7, Sphinx 9.1.0, and uv 0.11.8.
Commands ran from the repository root with an empty requirement UID.
The issue has no requirement scope, so no requirement state changed.
Full test, integration, fuzz, policy, and completion suites were not run locally.
CI owns those suites.

| Selected check | Command or exact test selection | Result |
| --- | --- | --- |
| Prose | Tooling project: `nox -s docs-prose -- --base-rev origin/dev` | 108 maintained files, including this record; no errors, warnings, or suggestions. |
| Schema equality | Python project: `python tools/check_generated_schemas.py` | Pass; generated and published bytes agree. |
| Authority | Python project: `python tools/check_authority_boundary.py` | Pass. |
| SDL catalogs | Python project: `python tools/check_sdl_catalog_parity.py` | Pass. |
| Publication | Python project: `python tools/check_schema_publication.py --base-rev origin/dev` | Pass. |
| Assurance | Python project: `python tools/check_assurance_policy.py` | Pass. |
| Formal claims | Python project: `python tools/check_behavioral_relation_claims.py` | Pass. |
| Semantic sources | `test_issue_219_participant_semantic_coverage.py`, `test_semantics_assessment.py`, `test_semantics_objectives.py`, `test_issue_1338_participant_identity.py` | 97 passed. |
| Invariant mutation oracle | Coverage module above and `test_participant_semantics_invariant_oracle.py::test_each_invariant_rejects_its_targeted_mutation` | 48 passed after the I15 excerpt repair. |
| Fixture evidence | Raw YAML corpus, mixed control corpus, inject delivery corpus, runtime package repositories, variation points, and adaptive difficulty corpus | 54 passed. |
| Runtime evidence | Selected SEM-218 runtime and processor/backend manifest rejection cases | 9 passed. |
| Vale controls | The two new `test_reference_metric_exception_*` cases in `test_issue_1931_documentation_tools.py`, selected with `-m integration` | 4 passed. |
| Python style | Tooling project: Ruff check and format check of the changed test module | Pass. |
| File policy | `tools/check_repo_policy.py --check-set file-local` on changed and added paths | Pass before this record. |
| Public HTML | Python project: `python -m sphinx -b html -a -W docs/public /tmp/1936-public-html` | Build succeeded. No publication. |

The fixture selection used these exact nodes under
`implementations/python/tests/`:

- `test_sdl_source_format.py::test_normative_source_profile_fixture_corpus`
- `test_act_617_mixed_control.py::test_published_valid_and_invalid_sdl_fixtures_exercise_mixed_control_boundary`
- `test_dsl_142_participant_inject_delivery.py::test_published_valid_and_invalid_delivery_fixtures`
- `test_issue_847_runtime_package_repositories.py`
- `test_sdl_variation_points.py`
- `test_sce_003_adaptive_difficulty.py::test_positive_boundary_unsupported_and_policy_violation_fixtures`

The runtime selection used `test_sem_218_runtime_realization.py` and these nodes:

- `test_processor_manifest.py::test_processor_manifest_v2_rejects_realization_support_section`
- `test_backend_manifest.py::test_backend_manifest_v2_rejects_hollow_realization_support`

Use `uv run --project implementations/python --frozen` for Python checks.
Use `uv run --project implementations/tooling/python --frozen --no-default-groups`
for tooling commands. The check guide gives runnable examples.
An initial partial Sphinx build lacked its full search index. The complete
local HTML render above passed. An initial tooling environment lacked the
model dependencies; the frozen Python environment passed the model checks.
The default pytest marker filter deselected the new Vale cases. Their explicit
selection above ran all four cases.

These checks establish only the stated local evidence. They do not prove
native backend effects, deployed behavior, or independent formal reproduction.

The pre-push review found one class of defect across 18 invariant headings.
Their case no longer matched the exact text in the executable oracle catalog.
The existing `test_oracle_and_spec_headings_map_both_directions` failed before
the repair. All 18 headings were restored to their baseline spelling.
The oracle and its synchronization assertion remain unchanged.
The complete invariant-oracle module and semantic-coverage module then passed.
This is a prose repair with an existing executable check.
The I15 table excerpt still matches its source clause after punctuation cleanup.

## Rendered review

Existing MyST and Sphinx rendered the sources to local temporary files.
Chrome 156.0.8078.79 inspected all 122 reference pages, the three design and
guide pages, and four changed public pages. No hosting was used.
The browser had outbound access blocked during this review.

The 129 rendered pages have no skipped heading levels, empty link labels,
or images without text alternatives. The changed reference pages retain all
baseline heading fragments. Existing Markdown link targets in both roots
resolve to files. The repaired historical link uses an immutable Git revision.
No published page URL changed.

Actual Tab key input reached links on both root indexes, the new check guide,
and the four changed public pages. This included the new reference links.
The review inspected screenshots of the two root indexes, check guide,
SDL guide, and shared-contract API page. Link text names its destination.
Text and structure carry meaning without color. Existing Mermaid source
remains readable text in the local reference render; this check does not
claim to exercise GitHub's diagram renderer. No diagram image was added.

## Acceptance map

| Issue criterion | Delivery evidence |
| --- | --- |
| Each maintained family and page | Sources table and complete page inventory below. |
| One reader purpose and routes | Reference indexes, existing explanation links, new local check guide. |
| Current code and explicit limits | Source corrections and selected checks above; historical evidence limit. |
| Normative equivalence | Protected material checks, unchanged code blocks and YAML data, source review. |
| Schema identity and examples | Byte equality, catalogs, selected corpus and semantic tests. |
| STE and existing tools | Language review, exact exceptions, real Vale controls, changed-path lint. |
| Release and ownership | Versioned public links; runtime and backend owner paths; no Go publication. |
| Heading links and accessibility | Rendered review, preserved fragments, actual keyboard input. |

## Page inventory

| Reference path | Treatment |
| --- | --- |
| `contracts/README.md` | Revised |
| `contracts/fixtures/experiment-core/adaptive-difficulty/README.md` | Revised |
| `contracts/fixtures/sdl/mixed-control-v1/README.md` | Revised |
| `contracts/fixtures/sdl/participant-inject-delivery-v1/README.md` | Revised |
| `contracts/fixtures/sdl/runtime-package-repository-v1/README.md` | Revised |
| `contracts/fixtures/sdl/sdl-yaml-v1/README.md` | Revised |
| `contracts/fixtures/sdl/variation-points-v1/README.md` | Revised |
| `contracts/schema-publication/README.md` | Retained |
| `contracts/schema-publication/tombstones/README.md` | Retained |
| `contracts/schemas/README.md` | Revised |
| `specs/README.md` | Revised |
| `specs/authority/README.md` | Revised |
| `specs/candidate-synthesis/source-neutral-sdl-candidates.md` | Revised |
| `specs/concept-authority/autonomous-behavior-vocabularies.md` | Revised |
| `specs/concept-authority/classification-migration.md` | Retained |
| `specs/concept-authority/concept-authority.md` | Revised |
| `specs/concept-authority/controlled-vocabularies.md` | Revised |
| `specs/concept-authority/external-concept-bindings.md` | Revised |
| `specs/concept-authority/participant-control.md` | Retained |
| `specs/concept-authority/reference-models.md` | Revised |
| `specs/concept-authority/semantic-profiles.md` | Revised |
| `specs/concept-authority/semantic-projection-reports.md` | Revised |
| `specs/conformance/authoring-adapters.md` | Retained |
| `specs/evolution/README.md` | Revised |
| `specs/evolution/progressive-semantics.md` | Retained |
| `specs/evolution/versioning-deprecation-and-migration.md` | Revised |
| `specs/formal/README.md` | Revised |
| `specs/formal/artifact-transformations/README.md` | Revised |
| `specs/formal/assessment/README.md` | Revised |
| `specs/formal/assessment/pipeline-consistency.md` | Revised |
| `specs/formal/behavioral-relations/README.md` | Revised |
| `specs/formal/composition-readiness.md` | Revised |
| `specs/formal/experiment-core/README.md` | Revised |
| `specs/formal/exploit-path-analysis/README.md` | Revised |
| `specs/formal/objectives/README.md` | Revised |
| `specs/formal/objectives/declarative-objective-semantics.md` | Revised |
| `specs/formal/objectives/proposition-and-assertion-semantics.md` | Revised |
| `specs/formal/objectives/window-consistency.md` | Revised |
| `specs/formal/observability-evidence-plane.md` | Revised |
| `specs/formal/participant-behavior-model/README.md` | Revised |
| `specs/formal/participant-episode-model/README.md` | Revised |
| `specs/formal/participant-runtime/README.md` | Revised |
| `specs/formal/participant-semantics/README.md` | Revised |
| `specs/formal/participant-semantics/adversarial-flow-control.md` | Revised |
| `specs/formal/participant-semantics/autonomous-execution.md` | Revised |
| `specs/formal/participant-semantics/control-applicability-and-evaluation.md` | Revised |
| `specs/formal/participant-semantics/cross-backend-participant-control.md` | Revised |
| `specs/formal/participant-semantics/delivery-tool-actions.md` | Retained |
| `specs/formal/participant-semantics/ifc-profile-variability.md` | Revised |
| `specs/formal/participant-semantics/information-flow-control.md` | Revised |
| `specs/formal/participant-semantics/local-outcomes.md` | Revised |
| `specs/formal/participant-semantics/modular-participant-control.md` | Revised |
| `specs/formal/participant-semantics/participant-crossing-bisimulation.md` | Revised |
| `specs/formal/participant-semantics/participant-crossing-counterexamples.md` | Revised |
| `specs/formal/participant-semantics/participant-crossing-machine-check.md` | Retained |
| `specs/formal/participant-semantics/participant-crossing-models.md` | Revised |
| `specs/formal/participant-semantics/participant-crossing-multi-operation-models.md` | Revised |
| `specs/formal/participant-semantics/participant-crossing-runtime-mapping.md` | Retained |
| `specs/formal/participant-semantics/participant-predicate-opacity.md` | Revised |
| `specs/formal/participant-semantics/reusable-mixed-control.md` | Revised |
| `specs/formal/participant-semantics/semantic-coverage.md` | Revised |
| `specs/formal/participant-semantics/semantic-coverage/behavior-model-and-runtime.md` | Revised |
| `specs/formal/participant-semantics/semantic-coverage/design-commitments-sem-208-to-211.md` | Revised |
| `specs/formal/participant-semantics/semantic-coverage/design-commitments-sem-212-to-215.md` | Revised |
| `specs/formal/participant-semantics/semantic-coverage/family-rows.md` | Retained |
| `specs/formal/participant-semantics/semantic-coverage/invariants-i1-to-i18.md` | Revised |
| `specs/formal/planner/README.md` | Revised |
| `specs/formal/planner/dependency-ordering.md` | Revised |
| `specs/formal/realization/README.md` | Revised |
| `specs/formal/realization/envelope-semantics.md` | Revised |
| `specs/formal/realization/explicitness-and-realization.md` | Revised |
| `specs/formal/runtime-contracts/README.md` | Revised |
| `specs/formal/runtime-contracts/backend-operation-supervision.md` | Retained |
| `specs/formal/runtime-contracts/backend-result-admission.md` | Retained |
| `specs/formal/runtime-contracts/evaluator-results.md` | Revised |
| `specs/formal/runtime-contracts/participant-backend-contracts.md` | Revised |
| `specs/formal/runtime-contracts/workflow-results.md` | Revised |
| `specs/formal/runtime-control-plane/README.md` | Revised |
| `specs/formal/runtime-control-plane/supervision.md` | Revised |
| `specs/formal/scenario-satisfiability/README.md` | Revised |
| `specs/formal/scenario-variation-trial-realization/README.md` | Revised |
| `specs/formal/scenario-variation-trial-realization/cleanup-contracts.md` | Retained |
| `specs/formal/sdl-phases/README.md` | Revised |
| `specs/formal/time-model/README.md` | Revised |
| `specs/formal/validation-admission-profiles/README.md` | Revised |
| `specs/formal/workflows/README.md` | Revised |
| `specs/formal/workflows/compensation.md` | Revised |
| `specs/formal/workflows/goal-oriented-steps.md` | Revised |
| `specs/formal/workflows/state-machine.md` | Revised |
| `specs/sdl/README.md` | Revised |
| `specs/sdl/account-credential-bindings.md` | Revised |
| `specs/sdl/augmentation-scope.md` | Retained |
| `specs/sdl/authored-domain-topology.md` | Revised |
| `specs/sdl/backend-realization-preparation.md` | Retained |
| `specs/sdl/cloud-resource-access.md` | Retained |
| `specs/sdl/diagnostics.md` | Revised |
| `specs/sdl/document-model.md` | Revised |
| `specs/sdl/enterprise-deployment-tenancy.md` | Revised |
| `specs/sdl/execution-recovery.md` | Revised |
| `specs/sdl/external-injects.md` | Revised |
| `specs/sdl/initial-service-state.md` | Revised |
| `specs/sdl/materialization-attestation.md` | Retained |
| `specs/sdl/observability-and-evidence.md` | Revised |
| `specs/sdl/participant-control-context.md` | Revised |
| `specs/sdl/participant-identity.md` | Revised |
| `specs/sdl/participant-relationships.md` | Revised |
| `specs/sdl/plan-realization-profiles.md` | Retained |
| `specs/sdl/profile-selections.md` | Retained |
| `specs/sdl/recursive-realization-constraints.md` | Retained |
| `specs/sdl/references.md` | Revised |
| `specs/sdl/runtime-inventory.md` | Revised |
| `specs/sdl/scientific-scenario-completeness.md` | Revised |
| `specs/sdl/sections.md` | Revised |
| `specs/sdl/software-requirements.md` | Retained |
| `specs/sdl/stateful-resources.md` | Revised |
| `specs/sdl/variables-and-instantiation.md` | Revised |
| `specs/sdl/variation-points.md` | Revised |
| `specs/supply-chain/README.md` | Revised |
| `specs/supply-chain/artifact-requirement-satisfaction.md` | Revised |
| `specs/supply-chain/associated-artifact-manifests.md` | Revised |
| `specs/supply-chain/participant-control-context-assets.md` | Retained |
| `specs/supply-chain/reusable-asset-trust-integrity.md` | Revised |

## Exact reading-grade exceptions

| Reference path | Grade before exception |
| --- | --- |
| `contracts/README.md` | 13.48 |
| `contracts/fixtures/sdl/mixed-control-v1/README.md` | 11.81 |
| `contracts/fixtures/sdl/participant-inject-delivery-v1/README.md` | 13.72 |
| `contracts/schema-publication/README.md` | 11.30 |
| `contracts/schemas/README.md` | 13.33 |
| `specs/authority/README.md` | 11.26 |
| `specs/candidate-synthesis/source-neutral-sdl-candidates.md` | 13.69 |
| `specs/concept-authority/autonomous-behavior-vocabularies.md` | 13.64 |
| `specs/concept-authority/classification-migration.md` | 14.75 |
| `specs/concept-authority/concept-authority.md` | 12.23 |
| `specs/concept-authority/controlled-vocabularies.md` | 11.19 |
| `specs/concept-authority/external-concept-bindings.md` | 11.95 |
| `specs/concept-authority/participant-control.md` | 14.42 |
| `specs/concept-authority/reference-models.md` | 12.27 |
| `specs/concept-authority/semantic-projection-reports.md` | 13.34 |
| `specs/conformance/authoring-adapters.md` | 12.33 |
| `specs/evolution/README.md` | 11.87 |
| `specs/evolution/progressive-semantics.md` | 13.75 |
| `specs/formal/artifact-transformations/README.md` | 11.67 |
| `specs/formal/assessment/README.md` | 12.11 |
| `specs/formal/assessment/pipeline-consistency.md` | 11.96 |
| `specs/formal/behavioral-relations/README.md` | 14.16 |
| `specs/formal/composition-readiness.md` | 11.93 |
| `specs/formal/experiment-core/README.md` | 13.25 |
| `specs/formal/objectives/README.md` | 12.26 |
| `specs/formal/objectives/declarative-objective-semantics.md` | 13.34 |
| `specs/formal/objectives/proposition-and-assertion-semantics.md` | 11.91 |
| `specs/formal/observability-evidence-plane.md` | 15.30 |
| `specs/formal/participant-behavior-model/README.md` | 13.82 |
| `specs/formal/participant-episode-model/README.md` | 13.79 |
| `specs/formal/participant-runtime/README.md` | 13.99 |
| `specs/formal/participant-semantics/README.md` | 14.00 |
| `specs/formal/participant-semantics/adversarial-flow-control.md` | 14.20 |
| `specs/formal/participant-semantics/autonomous-execution.md` | 12.24 |
| `specs/formal/participant-semantics/control-applicability-and-evaluation.md` | 14.56 |
| `specs/formal/participant-semantics/cross-backend-participant-control.md` | 13.26 |
| `specs/formal/participant-semantics/delivery-tool-actions.md` | 13.05 |
| `specs/formal/participant-semantics/ifc-profile-variability.md` | 15.26 |
| `specs/formal/participant-semantics/information-flow-control.md` | 13.84 |
| `specs/formal/participant-semantics/local-outcomes.md` | 12.80 |
| `specs/formal/participant-semantics/modular-participant-control.md` | 14.00 |
| `specs/formal/participant-semantics/participant-crossing-counterexamples.md` | 11.76 |
| `specs/formal/participant-semantics/participant-crossing-models.md` | 11.88 |
| `specs/formal/participant-semantics/participant-crossing-multi-operation-models.md` | 12.34 |
| `specs/formal/participant-semantics/participant-crossing-runtime-mapping.md` | 12.23 |
| `specs/formal/participant-semantics/participant-predicate-opacity.md` | 13.74 |
| `specs/formal/participant-semantics/reusable-mixed-control.md` | 13.96 |
| `specs/formal/participant-semantics/semantic-coverage/behavior-model-and-runtime.md` | 11.23 |
| `specs/formal/participant-semantics/semantic-coverage/design-commitments-sem-208-to-211.md` | 11.02 |
| `specs/formal/participant-semantics/semantic-coverage/family-rows.md` | 13.10 |
| `specs/formal/planner/README.md` | 14.33 |
| `specs/formal/realization/README.md` | 14.67 |
| `specs/formal/realization/envelope-semantics.md` | 11.22 |
| `specs/formal/realization/explicitness-and-realization.md` | 13.76 |
| `specs/formal/runtime-contracts/README.md` | 13.77 |
| `specs/formal/runtime-contracts/backend-operation-supervision.md` | 13.62 |
| `specs/formal/runtime-contracts/participant-backend-contracts.md` | 12.05 |
| `specs/formal/runtime-control-plane/README.md` | 13.57 |
| `specs/formal/runtime-control-plane/supervision.md` | 13.63 |
| `specs/formal/scenario-satisfiability/README.md` | 12.51 |
| `specs/formal/scenario-variation-trial-realization/README.md` | 13.55 |
| `specs/formal/sdl-phases/README.md` | 12.11 |
| `specs/formal/validation-admission-profiles/README.md` | 12.52 |
| `specs/formal/workflows/goal-oriented-steps.md` | 14.44 |
| `specs/sdl/README.md` | 12.29 |
| `specs/sdl/account-credential-bindings.md` | 14.31 |
| `specs/sdl/augmentation-scope.md` | 14.49 |
| `specs/sdl/backend-realization-preparation.md` | 15.30 |
| `specs/sdl/diagnostics.md` | 12.99 |
| `specs/sdl/document-model.md` | 12.04 |
| `specs/sdl/enterprise-deployment-tenancy.md` | 12.42 |
| `specs/sdl/execution-recovery.md` | 14.32 |
| `specs/sdl/external-injects.md` | 14.01 |
| `specs/sdl/initial-service-state.md` | 12.22 |
| `specs/sdl/observability-and-evidence.md` | 13.43 |
| `specs/sdl/participant-control-context.md` | 12.23 |
| `specs/sdl/participant-identity.md` | 12.70 |
| `specs/sdl/participant-relationships.md` | 13.93 |
| `specs/sdl/plan-realization-profiles.md` | 14.06 |
| `specs/sdl/profile-selections.md` | 13.59 |
| `specs/sdl/recursive-realization-constraints.md` | 13.61 |
| `specs/sdl/references.md` | 13.25 |
| `specs/sdl/runtime-inventory.md` | 13.13 |
| `specs/sdl/scientific-scenario-completeness.md` | 13.78 |
| `specs/sdl/sections.md` | 12.64 |
| `specs/sdl/software-requirements.md` | 13.15 |
| `specs/sdl/stateful-resources.md` | 12.58 |
| `specs/sdl/variables-and-instantiation.md` | 11.98 |
| `specs/supply-chain/README.md` | 14.37 |
| `specs/supply-chain/artifact-requirement-satisfaction.md` | 13.49 |
| `specs/supply-chain/associated-artifact-manifests.md` | 12.50 |
| `specs/supply-chain/participant-control-context-assets.md` | 13.08 |
| `specs/supply-chain/reusable-asset-trust-integrity.md` | 14.46 |
