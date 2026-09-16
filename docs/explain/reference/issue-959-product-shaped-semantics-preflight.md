# GOV-922 / issue 959: Product-shaped SDL semantics audit

Architecture preflight, 2026-09-16; inspected revision `2ed2d97c`.
The supplied GOV-922 requirement and issue #959 define the scope. This note
records architecture boundaries for the audit. It is not an implementation
plan, a completed audit, a new normative contract, or permission to redesign
all candidate surfaces in one change.

The controlling decisions already exist in
[ADR-012](../../decisions/adrs/adr-012-shared-concept-authority-and-aces-extension-discipline.md),
[ADR-049](../../decisions/adrs/adr-049-platform-application-runtime-inventory.md),
the [controlled-vocabulary specification](../../../specs/concept-authority/controlled-vocabularies.md),
the [runtime-inventory specification](../../../specs/sdl/runtime-inventory.md),
and the language-extensibility [design intent](../../research/language-extensibility/design-intent.md).
This preflight does not create another authority surface.

## Architecture decision

Issue #959 is an evidence-backed semantic audit. Its canonical result belongs in
the existing [scope inventory](../../research/language-extensibility/scope-inventory.md).
Use `docs/research/language-extensibility/audit.py` to reproduce candidate
counts and behavioral probes, but never treat its output as a defect list. At
this revision the census finds 972 Python files, 278 SDL enum definitions and
144 SDL enums containing `other` or `unknown`; those numbers are search leads,
not 144 semantic defects or evidence of repository-wide coverage.

Record one disposition for every selected surface and field. The record must
identify:

- the family, field and motivating specimen;
- its ADR, lineage source, current schema/model, validation guard and consumers;
- its semantic owner: portable domain concept, optional authored/configured
  state, capability or requirement, integration/binding,
  policy/authorization/marking, product-native identity or extension,
  realization choice, observation/evidence, or delivery machinery;
- whether it is sound, naming/documentation debt, a local semantic defect, or
  an architectural redesign;
- retained false positives and deliberately product-specific extensions, with
  rationale;
- the existing correction owner or a focused follow-up boundary, including
  compatibility, migration, schema and test impact; and
- inherited delegation, exact-descendant, abstraction-completeness and
  independently requested observation checks.

No disposition is established merely because a token is finite, a field is
named `kind`, a schema has a discriminator, or a model contains an `attributes`
map. Conversely, a syntactically neutral term is not portable when its required
profile still encodes one product's optional deployment shape.

## Existing owners to reuse

| Concern | Canonical incumbent and boundary |
| --- | --- |
| Portable term authority | `contracts/concept-authority/controlled-vocabularies-v1.json`, `raes_contracts.controlled_vocabularies`, `runtime_vocabulary_scopes.py` and the catalog contract models. Do not add an audit-local catalog, regex or parser. |
| Runtime family identity | `raes/_runtime_service_family_registry.py`, `_runtime_service_families.py`, `runtime_inventory.py` and `raes_contracts.addressing`. Product/native identifiers remain data; they do not replace stable local collection identity. |
| Source and model validation | `raes/_yaml_loader.py`, `_source_validation.py`, `_source_profile.py`, `SDLModel`, `raes_contracts.json_ingress` and `ContractModel`. Direct model/JSON paths must retain the same bounded and extra-forbid posture as SDL parsing. |
| Cross-object semantics | The collect-all `raes.validator` pipeline, including declaration indexing, collision checks and family relationship validators. Do not create model-local duplicates of repository-wide reference checks. |
| Recursive realization meaning | Compiler `realization_recursive_constraints.py`, `raes_contracts.realization_structure` and semantic-comparison owners. Preserve missing versus empty, unresolved knowledge versus delegation, source origins and binding exact descendants. |
| Typed extension meaning | `raes_contracts.domain_profiles`, `_domain_profile_admission.py`, pinned profile coordinates, resolution context, support declaration and selected operation. A governed token remains inert identity unless this explicit seam supplies typed meaning. |
| Classification | Existing external concept bindings and #989. Do not turn the controlled-vocabulary catalog into a second classification system. |
| Observation and evidence | `observation_demand*`, compiler observation demands, capture admission and realization-observation contracts. Representation capability, requested collection, reporting, retention and export remain separate choices. |
| Published contract shape | Published schemas under `contracts/schemas` are the hand-governed normative authority per ADR-009 §7. Contract source models, `tools/generate_contract_schemas.py`, `raes_contracts.contracts.bundle` and schema-publication entries must maintain reference-generation parity and the publication ledger. A generator edit alone does not authorize a contract change. |
| Durable control-plane state | `ControlPlaneStore`, local codecs/migrations, revision/CAS, idempotency and append-only audit. A focused runtime correction must not add an audit database, profile sidecar or hidden cache. |
| Workflow governance | `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/check_repo_policy.py`, `tools/check_requirement_governance.py`, `tools/verify_all.py` and concept-authority/schema-publication checks. Set `RAES_REQUIREMENT_UID=GOV-922` when the branch lacks the UID. Release Please owns changelog and version edits. |

ADR-049 and issue #956 are a delivered corrective precedent: capability,
product/version identity, configured content, binding, policy and evidence have
separate owners. Do not reopen that correction. Issue #1206 owns governed
runtime identity conformance, #1207 owns compulsory profile-guard corrections,
#1205 owns acquisition versus final software state, #1208 owns adjacent typed
profile work, #1209 owns capture/report integration, and #1212 owns observation
demand. Issue #959 records cross-family dispositions and creates focused gaps;
it must not absorb those implementations.

## Cross-cutting gates for any focused correction

The audit document itself has no runtime ingress, authorization, persistence or
host-execution path. A later focused correction is incomplete unless it passes
every applicable row below.

| Layer | Required treatment |
| --- | --- |
| YAML/JSON and config shape | Preserve UTF-8 and input/scalar/depth/node/alias limits, safe YAML, duplicate-key/member rejection, non-finite rejection, strict core keys, variable grammar and post-instantiation revalidation. Widen only the disposed field's owned identity grammar. |
| Domain-profile admission | Reuse pinned coordinates, namespace and digest checks, bounded offline resolution, acyclic local references, inert schema-keyword allowlists, support declaration and operation admission. No network retrieval, ambient filesystem/environment discovery, dynamic import or profile-selected handler. |
| Identity/reference validation | Preserve local/child uniqueness, qualified reference resolution, ordered-versus-keyed collection meaning and bounded semantic addresses. A provider identifier or vocabulary token is not a collection key or an authorization principal. |
| Secrets, environment and URIs | Reuse `runtime_values.enforce_observed_value_redaction`, `runtime_environment.py`, `runtime_generated_value.py`, `secret_references.py` and `uri_safety.py`. Preserve literal/source exclusivity, raw-value exclusion for protected values, generated-output ownership and inert credential-free URI validation. A private sensitivity token cannot bypass closed protection semantics. |
| Compilation and comparison | Preserve exact identity, alias rules owned by the vocabulary, variables, missing/empty/unknown distinctions, inherited open scope, exact descendants and source/default origin. Schema acceptance or a product name is not semantic support or realization authority. |
| Planner, backend and authorization | Reuse source-bound authority, backend-manifest support, target configuration, trusted profile context and selected-operation admission. Revalidate the whole core/profile conjunction before an effect; an open parent delegates only unmentioned choices. |
| API authentication and error envelopes | Reuse `ControlPlaneSecurityConfig`, API `_auth.py`, request guards, bounded audit queues, stable response envelopes, `raes._errors`, `Diagnostic` and `portable_diagnostic_payload()`. Some operation routes expose `str(ValueError)` in 409 responses: downstream validation messages must therefore be value-free. The catalog helper currently includes a rejected token in its direct error text; use the existing sanitizing runtime boundary rather than exposing that text. Bounding or schema-validating a diagnostic is not redaction. |
| Persistence and result publication | Validate the actual admitted completion before publication or storage. Reuse revisions, atomic terminal transitions, idempotency, reconciliation, sanitized snapshots and existing codecs/migrations. Preserve the trusted predecessor and exact coordinates on rejection or reload. |
| Observability and disclosure | Reuse operational audit/status and explicit observation-demand/capture admission. Do not log raw profiles, Pydantic inputs, protected native values or backend output. Precise authored state must not implicitly request collection, retention, export or experimental telemetry. |
| OS/host execution | Parsing, vocabulary lookup and profile resolution perform no subprocess, shell, host-environment lookup or file/network access. Drivers retain fixed argv, no shell, bounded timeout, private file modes/path checks and suppressed native stdout/stderr. Never put tokens, profile payloads, locators or secrets in process argv. |

`docs/explain/sdl/validation.md` is currently stale: it still describes
`require_profile_for_data_model`, `require_profile_for_agent_kind` and
`require_profile_for_privilege_class` as active guards. Current family models,
`specs/sdl/runtime-inventory.md` and the issue #1207 clause mapping instead allow
partial descriptions and move actual prerequisites to selected-operation
admission. Treat the discrepancy as an audit finding to reconcile; do not use
the stale prose to restore product-shaped completeness guards.

## Extension seam

Choose the seam from the concept's owner, not from the motivating specimen:

- Stable portable identity uses the existing owning catalog scope. Adding a
  private product inside an established governed-extension scope requires no
  core catalog edit or registration.
- Rich structure or operations use an explicit domain-profile coordinate and
  `DomainProfileResolutionContextModel`, with the required semantic operation
  admitted independently. This is the parameter for the next provider or
  version; it is not a generic `extensions` bag.
- Externally governed classifications use concept bindings with source
  coordinates, not privileged SDL enum values.
- A backend-owned choice omitted under inherited open scope needs no token,
  replacement catalog or author-supplied profile. If selected, it must still
  satisfy exact authored descendants and the admitted operation.

Do not case-fold, slug or alias an external identifier unless its owning
contract explicitly authorizes that normalization. Native identifiers whose
case or punctuation is meaningful stay in typed native-identity fields.

## Gotchas and prohibited patterns

- Do not create a second census, runtime-family registry, controlled-vocabulary
  catalog, schema authority, validation pipeline, exception hierarchy,
  diagnostic envelope, persistence store or backend admission path.
- Do not globally loosen `Enum | str`, `parse_enum_or_var()` or shared core
  normalization. Closed operations, grants, protection classes and structural
  discriminators must remain closed.
- Do not treat `other`, `unknown`, omission and delegation as synonyms. Known
  private identity stays exact; unknown records lack of knowledge; omission
  inherits scope; delegation grants only a bounded materialization choice.
- Do not use a generic attribute map as portable semantics, executable profile
  data, authorization, evidence or schema evolution. Legacy carriage does not
  establish comparison support.
- Do not infer completeness, conformance, successful observation, namespace
  ownership, protocol compatibility or execution authority from schema
  validity, vocabulary membership, a definition digest or advertised support.
- Do not manufacture OS, package, filesystem, network or telemetry prerequisites
  for a complete abstract model. Base validity is not a backend deployment
  recipe or a stronger completeness claim.
- Do not make either a core catalog or a replacement private-extension catalog
  compulsory for unmentioned backend choices.
- Do not rewrite accepted historical ADRs. Record current corrective guidance
  under the ADR follow-up policy and update the current normative owner.

## Non-goals and implementation boundary

This audit does not replace domain standards with one universal application or
configuration bag, remove useful domain typing, prohibit bounded product-native
data, change all finite enumerations, or implement every confirmed defect. It
does not redesign #956, pre-implement the focused issue owners above, change
backend extraction, add telemetry, or claim that ordinary SDL validity proves
completeness or backend conformance.

The implementation boundary for #959 is the documented method, selected-family
inventory, evidence-backed dispositions, retained false positives, focused gap
ownership and a recurrence-prevention rule or check. Each confirmed defect that
requires behavior or contract migration belongs in a focused follow-up with its
affected authorities, compatibility strategy, validation impact and tests.
