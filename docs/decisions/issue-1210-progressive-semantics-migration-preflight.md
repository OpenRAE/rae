# Issue 1210: Progressive semantics migration preflight

## User clarification: breaking cutover

On 2026-09-14 the user directed: “no legacy preservation required. this can be a
breaking change.” This supersedes the legacy reader, archive and interpretation
preservation requirements below. The delivery uses current-only revision reading
and explicit adoption into current contracts. The remaining input, authority,
privacy and target-admission guidance applies. The revised plan is recorded in
[issue #1210](https://github.com/OpenRAE/rae/issues/1210#issuecomment-5658296318).

## Original assessment

Date: 2026-09-14. Inspected revision: `a7c6b55c`.

Contract: the supplied #1210 title, scope and acceptance criteria, including
the corrective design intent of 2026-09-05 and GOV-903. This is architecture
guidance, not an implementation plan, semantic release, compatibility claim, or
claim that the broad ecosystem requirement is complete.
No runtime, schema, evidence or package version changes accompany this note.
Native blocker clearance was not queried: existing dependency code is not proof
that scheduling gates are cleared. Dependent implementation remains conditional
on the issue's native blockers, including #1212; preliminary design is permitted.

## Decision and authority

Use the existing surface-local versioning policy in
[the evolution specification](../../specs/evolution/versioning-deprecation-and-migration.md),
[ADR-061](adrs/adr-061-published-schema-evolution-policy.md), and
[ADR-105](adrs/adr-105-recursive-partial-description-semantics.md).
ADR-075 is still marked proposed; the evolution specification declares itself
normative. This note neither ratifies that ADR nor amends accepted ADR content.

The migration boundary must identify the **source and target semantic revisions**,
their owning reader/schema, and their canonicalization/comparison profiles.
Changed omission, closure, sentinel, admission-quantifier or evidence-floor
meaning requires an explicit revision even when accepted JSON shapes overlap or
a schema is draft. A publication hash records content; it does not select a
historical semantic reader. Package SemVer, scenario/module `version`, YAML
source format, schema lineage, and domain-profile revision are separate axes.
Do not repurpose any one of them as a universal version switch.

Reader dispatch belongs before interpretation/default insertion at each owning
ingress. Use exact carried contract/profile identity or explicit source context
bound to the artifact's provenance. Unsupported, contradictory or ambiguous
selection fails through that surface's diagnostics. Do not infer a revision
from installed package version, the presence of a new field, current defaults,
or trial-and-error validation. The concrete new identifiers must be declared
together with their compatibility scope; this preflight does not invent syntax.

Compatibility reading, author-authorized conversion, formatting, and current
execution admission are separate operations. Reading an old artifact preserves
its original meaning. Conversion produces a new artifact and a deterministic
report; it never rewrites historical evidence or grants execution permission.

## Incumbents and concrete hazards

Package paths in this note are relative to `implementations/python/packages/`.

| Boundary | Canonical incumbents and required treatment |
| --- | --- |
| Source and lifecycle | `raes/parser.py`, `_source_profile.py`, `formatting.py`, `composition/`, `phase_contracts.py`, `instantiate.py`, `canonical.py`. `sdl-yaml/v1`, `raes-sdl-semantic/v1` and `raes-sdl-instantiated-snapshot/v1` currently remain distinct v1 identities. Carry semantic selection through the top-level parser, fragments, imports, expansion, instantiation and emitted source. |
| Explicitness and recursive meaning | `raes/explicitness.py`, `realization_designation.py`, `raes_contracts/realization_structure/`. The legacy enum classifier treats `other`/`unknown` as open and reduces containers to the weakest child. Neither is authority for the new recursive contract. Reuse `RealizationConstraintDocument`, presence/origin/knowledge/closure types, semantic addresses, relation budgets and `upgrade_legacy_realization_structure()` / `downgrade_recursive_realization_structure()`. Their checked compatibility subset is not a universal SDL migrator. |
| Software | `raes/runtime_software.py`, `runtime_packages.py`, `raes_contracts/software_versions.py`, and [software requirements](../../specs/sdl/software-requirements.md). Keep the component owner, exact package shorthand, explicit `package_ref`, shared repository/trust identities and existing profile refinements. Legacy APT repositories remain final state with their HTTPS/key-digest guards; opaque `source` labels never become acquisition instructions. Application/package versions and exact strings/named ordering relations remain distinct. |
| Profiles and private values | `raes_contracts/domain_profiles.py`, `_domain_profile_resolution.py`, `_domain_profile_validation.py`, `_domain_profile_admission.py`, `profile_selections.py`; `raes/_mapping_scopes.py::PROFILE_JSON_FIELDS` and `composition/_profiles.py`. Reuse exact definition/schema/semantic identities and operation-specific support. Preserve literal private keys and values; retarget declared binding owners and children only. No recursive discovery of references in arbitrary JSON. |
| Transformation and #989 | `raes/transformations.py`, `_transformation_types.py`, `_transformation_support.py`, `_transformation_bindings.py`, `classification_migration.py`; `ArtifactTransformationReportModel`. Reuse all-or-none results, explicit loss policy, source/target/policy/derivation digests, preservation checks, identity maps and linked-binding retargeting. [Classification migration](../migration/external-classifications.md) owns external assertions; #1210 must coordinate its input/output contracts rather than copy its mappings or sidecar logic. |
| Comparison and identity | `raes/canonical.py`, `raes_contracts/canonical.py`, `raes_processor/semantic_comparison.py`, `semantic_comparison_adapters.py`, `semantic_comparison_projections.py`. Reuse RFC 8785 identities and owner projections. Canonical SDL identity is `raes-sdl-semantic/v1`, but the scenario comparison adapter independently declares `raes-canonical-sdl/v1`, digests a default-filled current `Scenario`, and recursively strips every `description` key from its projection. That fork is not a sound preservation oracle for omission provenance or private-profile data containing that key. Align or explicitly version these owner profiles; projection ownership must distinguish editorial SDL fields from semantic profile payloads. Until a historical owner projection is selected, refuse cross-revision scenario comparison rather than reinterpret it through the current model. |
| Published readers and generated artifacts | Hand-governed `contracts/schemas/`, `raes_contracts/versions.py`, `manifest_authority.py`, `contracts/bundle.py::schema_bundle()`, and `raes/schema_catalogs.py`. The bundle currently generates v1 authoring/instantiated schemas from current model classes; retaining filenames alone cannot freeze legacy behavior. Keep explicit historical reader/projection ownership and transitive nested contract references consistent. Manifest allowlists currently name exact supported IDs, including `sdl-authoring-input-v1`; changing a producer without its support declarations is incomplete. |
| Admission and observation | Existing compiler/planner realization owners, `backend-realization-preparation-v1`, `plan-realization-profiles-v1`, `compiler/observation_demands.py`, `raes_contracts/observation_demand*.py`, description projection/reporting, validation disclosures and runtime result admission. Preserve #1204's opt-in supported-completion protocol separately from legacy universal envelopes. #1212 owns scoped demand, including the legacy evidence-requirement adapter; #1112 owns actual capture admission. Do not recreate either policy in a migrator or formatter. |
| Presentation | `raes_cli/main.py`, `_semantic_sdl.py`, `_semantic_result.py`; `raes_mcp/tools/language_service.py`, `authoring/`, `inspection/`, `completeness.py`; language catalogs, shipped examples and public docs. Expose author constraints, permitted backend choices and requested observations separately. Explain inherited openness as policy and abstract completeness at its declared level. A specimen/template/completeness UI must not force infrastructure or hidden evidence requirements. |

## Preservation obligations and refusal examples

These are semantic acceptance anchors, not proposed new wire syntax:

| Source situation | Required result |
| --- | --- |
| Legacy omitted or closed collection | Evaluate with its named original omission/default and closure rules. An explicit conversion may represent those rules in the recursive contract; it must not silently grant additional membership. |
| Open parent, exact child, unspecified siblings | Keep the exact child binding and inherited delegation for siblings. Formatting cannot generate per-property opt-outs, freeze defaults, or add packages/OS details. |
| Legacy enum `other` or `unknown` | Retain the original reader's interpretation. Conversion requires field-specific provenance or a recorded author decision distinguishing knowledge, exact private identity and delegation. No exact product identity or permission may be invented. |
| Explicit null, omitted key, empty collection, observed absence | Preserve each owning meaning, origin and scope. A generic `exclude_none`, `exclude_defaults`, truthiness test or default-filled round trip is not sufficient. `RealizationLiteral` already explicitly retains null. |
| Optional constrained member or local closed child | Preserve conditional constraints and named closure universe, including under an open parent. Required, optional, forbidden, unknown, redacted and not-applicable cannot collapse to one nullable field. |
| Private profile unavailable to a tool | Retain exact identity and bounded exchange data where its owner permits opaque exchange; disclose unsupported semantics. Required semantic comparison/execution cannot succeed by ignoring it. Downgrade refuses unless its lossless subset can represent the meaning. |
| Mixed-revision import graph | Read each module under its own pinned contract and retain origin through namespace composition. Either use an explicit supported compatibility mapping or refuse the combination; a root revision cannot reinterpret imported defaults. Conflicts and duplicate identities must survive until diagnosed. |
| Old admission or implicit observation floor | Preserve the old quantifier/floor under the old contract. Conversion explicitly records any changed permission or obligation and its basis. One supported and delivered witness never proves universal envelope coverage; a descriptive constraint never creates observation demand. |
| No experimental data, operational-only, inherited/default or selected demand | Preserve purpose, mode, origin, selector/exclusions, collection, retention, export and reporting basis independently through all round trips. Inherited/default is not an explicit opt-out. A conflict with mandatory operational inputs requires admission refusal, not hidden collection. |

`format_sdl_source()` currently enables `SDLMigrationPolicy.ACCEPT`, constructs
the current `Scenario`, and reparses with semantic validation skipped. Its
`ValidationError` path also uses `str(exc)`. These are concrete boundaries to
review: spelling normalization cannot authorize semantic conversion, shape-only
formatting cannot certify equivalence, and raw validator text is not a safe
public migration diagnostic. `render_sdl_source()` already re-admits emitted
source; preserve that pattern with the explicitly selected target contract.

Conversion must be deterministic and idempotent for a named version pair,
source-preserving and all-or-none, including sidecars. Missing author decisions
produce stable bounded refusal diagnostics with safe locations and a migration
reference. Do not invent a timestamp, identity, provenance or default authority.
The current report has one `canonicalization_profile` field: cross-profile
conversion must make both digest interpretations unambiguous through the owning
contract/profile mapping or a governed report revision, never an untyped metadata
bag. Chained #989 conversion must bind each report and sidecar to the correct
intermediate/final digest; `semantic-omission` is not blanket permission to
weaken realization or observation obligations.

## Immutable evidence and honest status

Keep original bytes, contract/profile identities, historical canonical
projections, digests and joins readable. A derived view or migrated copy has its
own identity and provenance; it cannot replace the source or become a current
conformance result merely by passing a reader.

`raes/canonical.py` already authenticates legacy snapshot joins before converting
VM/default shapes. `_legacy_snapshot_classifications.py` removes only exact empty
retired classification containers; nonempty classifications still require explicit
migration. Neither adapter supplies a complete progressive legacy reader. Do not
generalize these transformations into silent evidence cleanup or accept arbitrary
old/current digest alternatives. Authenticate against a named historical
projection before any change and preserve the original external reference.

Reuse `tools/research_evidence.py`, `tools/formal_semantic_validation/`,
`tools/specification_coverage/`, and `test_issue_989_versioned_evidence.py` for
archived-byte integrity, exact release selection and historical/current separation.
Historical integrity validation must not run current semantics against old claims;
current claims must bind current implementation/complete output and actually replay.
Unknown future versions fail closed. Do not recapture historical baselines, drop
archives or relabel `not_run`/partial results to make migration checks green.

`ControlPlaneStore` / `LocalControlPlaneStore`, store codecs and
`control_plane_store_record_migration.py` remain the persistence owners. Database
layout versions do not select SDL semantics. Preserve atomic terminal-state and
retained-observation writes, immutable joins and recovery behavior; reading or
converting evidence must not resume operations, resolve secrets or invoke a backend.

## Cross-cutting gates

These are requirements on the intended implementation, not claims that new paths
have passed security tests. The pure migration core needs no new auth surface.

| Layer and incumbent | How the design must satisfy it |
| --- | --- |
| Source/JSON ingress | `raes/_yaml_loader.py`, `_source_validation.py`, `_mapping_key_analyzer.py`, `SDLParserLimits`; `raes_contracts/json_ingress.py`. Apply safe parsing, duplicate/tag/key guards and byte/depth/node/alias limits before version dispatch. Bound direct JSON/model inputs, historical archives, profile definitions and composed graphs too; legacy mode is not a bypass. |
| Model and semantic/config shape | `SDLModel`, `ContractModel`, `SemanticValidator`, instantiation admission, recursive relation budgets and profile admission. Validate source under its original contract and target under its selected contract. Keep `extra="forbid"` for syntax; it does not close semantic collections. Preserve identities, references, authority and cross-field checks. Never set private validation flags or use unchecked model construction to bless a conversion. |
| Environment and secret bindings | `raes/runtime_environment.py`, `runtime_values.py::enforce_observed_value_redaction`, generated-artifact validators, `raes_contracts/secret_references.py`, `contracts/experiment_bindings.py::BindingValue`, `participant_configuration.py`. Preserve literal/secret-reference and literal/`value_from` exclusivity, environment-name/uniqueness rules, sensitivity, producer-output entitlement and configuration-target ownership. Migration context is typed explicit data, not ambient environment lookup; private profiles do not authorize secret resolution or declassification. |
| URI/schema/import trust | `uri_safety.py::validate_safe_absolute_uri`, `_domain_profile_schema_registry.py::profile_schema_registry`, bounded profile validators, `raes/module_registry/` verified sources/cache/extraction/trust checks. Use pinned offline definitions; prevent automatic HTTP/file `$ref` retrieval, executable plugin loading and path escape. Preserve literal profile keys. Any existing explicit fetch still needs its trust, destination/redirect, size and integrity checks; URI validity and digest identity alone are not authorization. |
| API authentication and authorization | `RuntimeControlPlane`, `ControlPlaneSecurityConfig`, `_ControlPlaneApiAuth`, `RequestSizeLimitMiddleware`, existing route DTOs, target/role checks, idempotency and audit. If tools expose conversion/reading, reuse these boundaries and private-data access rules. Authored provenance/profile authority is not an authenticated caller or backend capability. CLI/MCP adapters stay within existing package boundaries. |
| Execution and backend results | Compiler/planner authority checks, preparation admission, direct control-plane submission and runtime result admission must consume the same selected contracts and capability context. Validate any chosen completion before effects and its delivered result afterward. Reading/migrating does not perform apply, reconciliation, refresh or cleanup. Delegation is no additional host privilege. |
| Observation and participant exposure | Shared #1212 resolution/lifecycle, typed descriptions, snapshot sanitization, validation-basis disclosure, participant visibility and flow-policy gates. Apply prohibitions before collection, buffers, persistence and export. Keep report depth and basis honest. Existing limits include rejection of mandatory observation combined with mutation and requested export without a governed delivery owner; migration cannot claim those capabilities into existence. |
| Errors/logging | `SDLError`, `SDLParseDiagnostic`, `_model_diagnostics.py`, `raes_contracts/diagnostics.py`, typed transformation reports, operation receipts/status, API `_operation_routes.py::_install_request_guards()`, CLI/MCP renderers and conformance `sanitized_failure_message()`. Reuse stable codes, bounded value-free messages and redacted 422/500 envelopes. Do not echo rejected values, whole profiles, Pydantic inputs, URIs with credentials, native output, environment or tracebacks. Length bounding alone is not redaction. No parallel exception tree, logger or audit sink. |
| Host/process/filesystem | Pure parsing, conversion and comparison do not spawn commands, load native drivers or fetch definitions. Existing CLI output paths must preserve source and publish complete results/sidecars coherently. Any generator subprocess uses fixed argument vectors, bounded input/output, timeouts and restricted environment; no tokens/private payloads in argv, shell interpolation, permissive temporary files or host paths in public diagnostics. |
| Persistence/publication | Use the incumbent store/codec and immutable artifact boundaries above. Keep protected retained values and terminal state atomic; no new evidence database or migration service. `contracts/schema-publication-manifest.json` indexes per-contract `entries/` and removal `tombstones/`; update the owning hash/`last_change`, not a duplicate ledger. Preserve schema/model/fixture parity and transitive historical schema availability. |

## Extensibility, verification and boundaries

The extension seam is an **explicit source/target profile pair plus bounded,
digest-bound migration context** at the existing parser/contract/transformation
owners. It carries author decisions and pinned definition resolution where needed.
Comparison and digest projections are selected by the same semantic identity.
Another revision extends its owning adapter/profile mapping; another private
profile uses the existing definition/namespace/support seams. Neither needs a
global registry, a new enum of products, copied recursive schema, central migration
service, arbitrary callback loading, or duplicated workflow.

Evidence for implementation must cover producer/consumer version pairs and name
the compatibility direction and dimension: structural acceptance, semantic
equivalence, behavioral compatibility and operational interoperability. Reuse
`test_sdl_source_format.py`, `test_sdl_format_cli.py`, `test_sdl_canonicalization.py`,
`test_artifact_transformations.py`, `test_classification_migration.py`,
`test_issue_989_versioned_evidence.py` and the #1203–#1209/#1212 regression families.
The anchors above must survive formatting, repeat conversion, mixed imports,
instantiation, canonicalization, semantic diff, generated schemas/bindings and
portable plan/evidence round trips. Include negative cases for private
`description` keys, null/default provenance, unsupported downgrades, tampered
historical joins, conflicting revisions, budget exhaustion and value leakage.
Same-version current-model round trips alone cannot prove legacy preservation.

Reuse `tools/check_generated_schemas.py`, `check_schema_publication.py`,
`check_deprecation_lifecycle.py`, SDL catalog/reference parity and relevant docs
checks. Deprecations belong in `specs/evolution/deprecation-records.yaml`;
compatibility limitations and version-pair examples belong in migration/public
docs. Generated bindings must derive from the selected published contracts,
without a second hand-maintained validation schema. Keep ADR-015/036 import
boundaries and source-size rules in `tools/policy/adr_policy.yaml`.
`.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`, `tools/check_repo_policy.py`,
`tools/check_requirement_governance.py` and `tools/verify_all.py` own workflow;
release-please owns package versions/changelog. The branch does not carry a UID,
so implementation workflow commands must set `RAES_REQUIREMENT_UID=GOV-903`.
Do not disguise an unavailable governance check as a pass.

Non-goals include redefining the #1201/#1202–#1209/#1212 semantic contracts or
implementing #989 again. They also include installing backend recipes, creating
mandatory catalog entries, expanding abstract models into infrastructure, or
adding observation/export capabilities. Do not upgrade historical evidence
strength, create universal migration, add APIs/stores/controllers, or weaken
auth, secret, and configuration gates.
The implementation boundary is explicit versioned interpretation, honest
conversion and preservation across existing authoring and reader surfaces.
