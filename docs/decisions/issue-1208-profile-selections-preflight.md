# Issue 1208: Profile selections architecture preflight

Date: 2026-09-13. Inspected revision: `d36608e8`.

Contract: the supplied title, body and acceptance criteria of GitHub #1208,
including the 2026-09-05 corrective intent. This is a requirement-free design
review, not an implementation plan, accepted ADR, schema change, or claim of
delivered support. Native blocker clearance remains a prerequisite for
implementation; source presence alone does not establish GitHub blocker status.

## Decision and existing foundations

Extend the containing selections with the existing
[`domain_profiles`](../explain/reference/domain-profiles.md) contract. Preserve
precise built-in profiles and closed operational/security controls. A private
namespace is not a core vocabulary release, an executable plugin, or permission
to bypass an owner's invariants. Definition, binding, local resolution context,
and operation-specific support remain separate roles. Reuse exact authority,
revision, schema/semantic-contract identity and digest; no second profile DTO,
resolver, registry, canonicalizer or generic action language.

The [governing intent](../research/language-extensibility/design-intent.md)
applies recursively: an effective open scope delegates unspecified descendants;
explicit constraints remain binding. Omitted generators, identity setup and
resource mechanisms create neither author declarations nor capture records.
Abstract models can be complete without any concrete implementation of them.
Selected executable profiles can have real prerequisites. Requested typed
reports retain exact identities and honest authored/backend-selected/observed
bases; reporting, operational checks, experimental observation, retention and
export are distinct decisions.

The current [plan-profile host](../../specs/sdl/plan-realization-profiles.md)
already carries public, bounded bindings through preparation, execution,
reconciliation and snapshots. It is programmatic provisioning input, not SDL
syntax, a credential carrier, or participant-control authority. Its reference
handler implements only `portable-resource-labels`. Reuse this carriage where
its owner fits; add the needed typed semantics at existing owners instead of
claiming that labels demonstrate generation, account realization or accounting.

## Candidate ownership and disposition

Package paths below are relative to `implementations/python/packages/`.

| Candidate | Existing owner and disposition |
| --- | --- |
| Generated artifact kind | `raes/stateful_resources.py::GeneratedArtifact.generator`, shared `raes_contracts.vocabulary.GeneratedArtifactKind`, compiler `stateful_resources.py`, planner `stateful_admission.py`. Extend generator selection with a typed profile; preserve built-in certificate/SSH behavior. Lifecycle, sensitivity, output disposition, delivery mode and read/write access remain closed controls. Source artifact satisfaction (`artifact_requirements`, ADR-098) is a different owner. |
| Service content materialization | `raes/content.py::ServiceMaterializationProfile`, validator `_service_materialization.py`, compiler `placement.py`, `raes_backend_protocols/service_materialization.py`. Extend the containing profile selection. Retain exact `service-content/v1` and `service-search-index-schema/v1` operations, conflict rules, service/tenant ownership and selected readback obligations. Do not turn account creation into dataset insertion. |
| Account/mailbox materialization | `raes/accounts.py::Account`, `AccountPlacement`, runtime-mail `RuntimeMailMailbox.account_ref`. Attach public materialization meaning to the existing account-placement owner; bind the exact service-local mailbox to its account. Account credential bindings remain the only material owner. A mailbox reference/inventory record alone is not an instruction to provision credentials. |
| Authored domain identity | `raes/identity_domains.py`, authored topology analysis and `raes_backend_protocols/domain_topology.py`. Extend the profile selection around the precise AD case; DNS/NetBIOS/controller/join rules stay with AD. Preserve canonical domain/account authority and relationship endpoints, rather than requiring AD fields for unrelated identity profiles. Runtime directory/local/app/database identities remain separate inventories. |
| Enterprise identity/federation | `raes/enterprise_identity.py`, enterprise semantic analysis and topology admission. Facade protocol and federation protocol/mapping/trust profile selections can use the common seam. Forest membership, trust direction, authority-to-facade direction and tenant-claim ownership remain binding security semantics, not executable strings or privileges inferred from profile names. Retain existing OIDC/LDAP-TLS/SCIM meanings. |
| Participant interactive access | `raes/agents.py::ParticipantInteractiveAccess`, `raes/semantics/participant_interactive_access.py`. Extend the SSH/RDP containing channel/profile selection without changing exact node/account binding, account eligibility, authorization, or participant disclosure. Protocol support is not a grant to connect or reveal credentials. Coordinate the control/decision boundary with #1068–1072 and ADR-108. |
| Participant resource measure | `raes/participant_resource_budgets.py`, contracts `participant_resource_types.py`, `participant_resource_budgets.py`, `participant_resource_validation.py`, backend capability adapters and runtime accounting. Extend measure identity/semantics, not owner kinds, reset/accounting transitions, isolation or security dispositions. Pin unit, permitted accounting/reset behavior, meter semantics and enforcement/evidence contract together. Preserve the existing budget/pool/event owners. |
| OS family | Already aligned here: `Node.os` uses `GovernedVocabulary[OSFamily]`; `provisioner-os-families` governs both `sdl.definitions.OSFamily` and `capabilities.provisioner.supported_os_families`. Reuse `runtime_vocabulary.py`, `runtime_values.parse_runtime_enum_or_var` and the catalog. Preserve exact private identities and schema/instantiation parity; do not introduce another OS extension field or normalize a private family to `other`. `OperatingSystemCompatibility` and `operating_systems.validate_operating_system_pair` retain coupled family/distribution/release validation. |

These are owner-specific hosts of one neutral contract, not a universal
properties bag. A bare governed `x-owner:term` classifies an identity but does
not establish namespace trust, typed value semantics or execution support.
Existing legacy capability strings are compatibility projections only; never
derive full operation support from them. Reject contradictory legacy and typed
selections instead of choosing precedence silently.

## Account/materialization security boundary

The normative [account credential contract](../../specs/sdl/account-credential-bindings.md)
remains authoritative. A fixture literal stays under
`Account.credential_bindings[].material`; an operator secret stays a safe logical
reference. Preserve literal bytes, including an explicitly empty fixture, and
revalidate variables after instantiation. Profiles may identify an existing
account/credential binding and its required public semantics, but must not copy
fixture values, operator reference IDs, resolved values or material-derived
verifiers/digests into profile values, definitions, provenance or reports.
The publication-safe plan-profile host cannot be repurposed for those bytes.

The required demonstration must start with explicitly authored fixture-backed
account/mailbox intent, traverse `account-placement`, negotiate its exact typed
profile, and deliver fixture material only to an authorized protected backend
sink. Existing `supports_accounts` and the `credential_bindings` account feature
are necessary compatibility gates where applicable, not proof of this new
materialization semantics. Check method, purpose, material classification,
service/tenant/reset ownership and the account/mailbox join, not a Cartesian
product of independently advertised capabilities. Unknown or unsupported
required combinations fail before mutation, including direct plan submission.

The current mailbox semantic validator checks that `account_ref` exists. It
does not establish the full materialization join or authorize a sink. Preserve
module-qualified account references and stable service-local mailbox identity
through composition, instantiation and both plan codecs. Do not infer identity
or authorization by matching username, email address, node role or inventory
posture; different deployment nodes may legitimately serve a domain account.

`raes_contracts/account_credentials.py` provides structural value-free
projection; `planner/account_credentials.py::account_credential_spec_is_valid`
reuses the canonical Account model for direct plans;
`provisioner_account_features()` is the shared feature extractor.
`raes_runtime/backend_account_credentials.py::sanitize_account_credential_result`
enforces a closed result for credential-bearing plans: no arbitrary details or
unapproved snapshot carriers, failed apply preserves the baseline, and entries
match the submitted plan before projection. Keep this alongside #1204's
prepared-delivery and result-integrity gates. The credential checker compares
entry payloads but does not itself compare `profile_bindings`; those bindings
must remain public and pass the existing profile selection/delivery checks.
No new carrier may bypass either gate. Its closed entry-set rule also cannot be
silently relaxed to permit delegated extra resources; unsupported combinations
need pre-mutation refusal until an explicit safe owner contract covers them.

The portable reference demonstration must prove the enforcement and sink
boundary with an installed semantic implementation and honest result basis.
An echo backend, label-only profile, sanitized snapshot or passing schema is
not proof of mailbox service realization. Concrete docker-mailserver setup and
the service smoke test belong to Brad-Edwards/aptl#668; no APTL access or code
change is part of this repository preflight.

## Cross-cutting gates the design must pass

| Layer | Canonical incumbent and required treatment |
| --- | --- |
| Source, JSON and authored configuration | `SDLModel`, bounded safe YAML/source validation, `SDLParserLimits`, `raes_contracts/json_ingress.py`, `ContractModel`, composition and instantiation. Keep closed host shapes, duplicate-key/reference rejection, portable IDs, source provenance and post-binding revalidation. Public profile data must satisfy the owning schema; private fields cannot become an unchecked escape hatch. |
| Profile resolution and semantic admission | `raes_contracts/domain_profiles.py` and its `_domain_profile_*` implementation, `realization_structure`, `realization_profiles`. Reuse bounded local resolution, namespace admission, pinned digests, supported schema vocabulary, no-retrieval registry and operation-specific support. No remote `$ref`, ambient discovery, dynamic import, validator command or unbounded schema evaluation. Schema support is distinct from installed semantic enforcement; unavailable required meaning is a bounded refusal, not opaque success. |
| Compiler/plan/target configuration | `CompiledRealizationRequirement`, resolved realization authority, compiler `placement.py`, planner `manifest_validation.py`, `realization_profiles.py`, manifest dataclasses/contract models/adapters, runtime `registry.py` and `backend_profiles.py`. Preserve conjunction with core constraints, exact resource ownership, target/context/manifest digests, preparation commitments and contract-version negotiation. The target supplies support independently of plan data; recheck changed configuration. `reference_profile_configuration` currently rejects non-label semantic contracts and must gain genuine owner support before any new claim. |
| Alternate submission and workflow | `manager_plan_admission`, `control_plane_submission`, `backend_preparation`, `_call_backend_apply` and `_finalize_backend_apply`. Reuse shared account, topology, service-materialization and stateful admission on compiled and direct plans; reject unsupported semantics before driver/store effects. Preserve ordering, refresh, reconciliation, deletion and cleanup. A profile cannot introduce operations, dependencies, collection membership or another runtime domain. |
| Authentication and access authority | `ControlPlaneSecurityConfig.strict_defaults`, existing HTTP identity/role/target checks, request-size/idempotency guards, runtime plan authorization, participant access/visibility/crossing policy and governed configuration bindings. No new credential endpoint or auth scheme. Profile admission cannot grant caller, participant, tenant-claim or secret-resolution authority. Starting accounts and interactive access do not authorize fixture disclosure. |
| Secret/environment/configuration shapes | Account material union and safe reference-ID validation; `RuntimeEnvironmentVariable`, `RuntimeConfiguration`, `runtime_generated_value.resolve_consumable_generated_artifact_output`, planner `stateful_admission`. Preserve value/value-from exclusivity, classification, exact artifact/output/node joins, closed mode-specific environment consumer fields, env-file identity and duplicate-name/destination checks. Do not smuggle credentials through environment-binding, profile-choice, metadata or backend-option dictionaries. |
| Host/process and generated-file delivery | `raes_reference_backend/drivers/oci.py` supplies fixed argv, no shell, validated runtime names, bounded timeouts and coarse native errors. Libvirt `drivers/seed.py` supplies exclusive, no-follow, owner-only file creation. Reuse within package boundaries. Fixed argv alone does not make a credential argument safe: use an authorized protected sink, never literals/resolved secrets in argv, command text, environment dumps, stdout/stderr or shared temporary files. Preserve contained paths, symlink resistance, least-privilege output selection, producer-private denial, sensitivity and read-only delivery for private generators too. Do not infer that these driver patterns already implement the new sink. |
| Errors and observability | Existing SDL parse/validation/instantiation exceptions, structured `Diagnostic`, portable diagnostic conversion, backend result diagnostics, redacted HTTP 422/500 envelopes and audit/operation records. Reuse bounded stable codes, safe addresses and generic messages. Do not expose Pydantic rejected `input`, native exception strings, profile data, material or locators through messages, details, logs, traces or failure diffs. No second exception hierarchy, logger framework or evidence pipeline. |
| Results and durable publication | `backend_apply_results`, prepared delivery checks, credential projection, `RuntimeSnapshot`, `RuntimeSnapshotEnvelopeModel`, `control_plane_store_snapshots` codecs, `RuntimeDurabilityMixin` and existing memory/SQLite stores. Admit exact selected bindings before sanitization/publication, protect trusted predecessor state and preserve revision/CAS and history-generation checks. Generic plan/CLI/MCP/API output, snapshots, audits and recovery remain value-free; selected public typing survives round trips. Do not create a profile/credential repository or treat rejected result validation as infrastructure rollback. |
| Reporting, observation and evidence | Existing realization provenance/snapshot sanitization, observation demand/execution/binding and participant evidence/view contracts, ADR-066. Report a backend selection as a selection; only actual observation supports an observed basis. Keep #1209 report/capture fidelity and #1212 demand ownership. Selected operational readback/accounting evidence remains required at its own boundary; it does not automatically authorize experimental retention/export. |

## Resource and materialization gotchas

Resource closure occurs in several layers: SDL enums and `_RESOURCE_UNITS` /
`_RESOURCE_ACCOUNTING`, contract literals and `require_quantity_semantics`,
policy validation, configured pool capability models, compiled resource demands,
and runtime state/event models. Backend strings alone are not extensibility.
Reuse the contract quantity semantics for both SDL and portable models rather
than maintaining another unit/mode table. Keep the selected exact measure and
meter identities in pool matching, parent aggregation, capacity admission,
digests and persisted state/events; avoid collisions between private authorities
or revisions. Preserve existing pool identity compatibility deliberately.

`ParticipantResourceBudgetPolicy._validate_policy` currently requires the full
six-kind vector, and `ParticipantResourceBudgetPolicyModel` repeats complete
vector validation. Adding a private measure must not expand every policy's
mandatory vector. Completeness belongs to the selected policy/profile, not the
union of all known measures. Preserve existing built-in policy obligations;
coordinate general partial-description/completeness changes with #1207.

`participant_resource_budgets`, `participant_resource_accounting` and
`participant_resource_pool_ledger` already own reserve/commit/release/reconcile,
exact measured vectors, evidence, generation fences, shared physical pools and
fairness. Preserve atomic capacity admission, integer quantity bounds, parent
and sibling limits, reset ownership, idempotent settlement, protected capacity
and tenant isolation. Another measure under a supported accounting mode uses
these owners. A genuinely new accounting mode needs a reviewed runtime
transition contract; an arbitrary meter name or callback cannot supply one.

The existing service-content base requires readback assertions, evidence and
observation-boundary references, and the backend gate requires independent
readback. These are selected built-in profile obligations, not defaults to copy
onto every extension, account/mailbox declaration or abstract model. Preserve
those precise profiles; do not use the new seam to bypass an explicitly selected
obligation, silently weaken ADR-088, or manufacture evidence for omitted setup.

## Extensibility, evidence and repository boundaries

The future variation belongs in the existing owner's optional typed selection,
its exact locally admitted definition/schema/semantic contract, and the target's
installed operation support. Another private generator or access/materialization
profile changes those inputs, not a central enum or executable registry. Resource
variation additionally binds quantity/unit/meter semantics to existing accounting
modes. Backend-private mechanisms left open need none of these authored inputs.

Acceptance evidence should extend the existing #1202 profile, #1203 recursive,
#1204 preparation/delivery/offline/durability, #1206 vocabulary/schema/OS,
#673 credential, #1074 generated-environment and #899 resource-budget tests;
also retain `test_stateful_realization_resources`,
`test_authored_domain_topology`, `test_participant_interactive_access` and
control-plane API coverage. The necessary distinctions are private definitions
without catalog edits; explicit versus omitted mechanisms; selected public
typing through codecs/reconciliation; core/profile contradictions; unsupported
profiles before any sink/driver mutation; exact mailbox ownership; denied secret
and producer-private delivery; bounded unit/meter enforcement and settlement;
and value-free success/failure/durable/API/CLI outputs. Include a complete
abstract model requiring no concrete generator, identity setup or resource
mechanism, and requested reports without automatic experimental capture.

Repository authority stays in `specs/`, `contracts/`, `docs/` and
`implementations/`. Reuse `.ground-control.yaml`, `.gc/plan-rules.md`,
`tools/policy/adr_policy.yaml`, `.pre-commit-config.yaml`, `noxfile.py` and
`.github/workflows/canonical-verification.yml`. Maintain public package boundaries
and source-size rules: backends cannot import SDL/processor internals, and runtime
uses only public compiler/models/planner surfaces. Published carrier changes
require `schema_bundle()` parity, schema-publication ledger entries, fixtures,
and the existing generated-schema/publication/concept-authority gates. Private
profile definitions need not be copied into the core publication catalog.
Use the canonical `make policy` requirement-free lane; do not invent a formal
requirement UID. Full implementation verification follows the configured Nox
graph. No release version, changelog or accepted ADR mutation is needed here.

Non-goals: implementing #1208 in this note; generic imperative setup/actions;
new credential storage/resolution or participant disclosure; universal profile
registration, backend capture or concrete author recipes; replacing participant
controllers/schedulers (#1068–1072); reimplementing #1204 preservation/enforcement,
#1207 completeness, or #1209 report/capture ownership; concrete APTL mail-server
realization; and a second DTO, validation, exception, persistence or workflow
framework. This seam must extend existing owners without conflating them.

## Implementation acceptance mapping

The implementation uses these owners and executable checks. Paths below are
relative to `implementations/python/` unless otherwise identified.

- [x] Issue: common typed selection and candidate disposition —
  `packages/raes_contracts/profile_selections.py:27` and the ownership table in
  [`profile-selections.md`](../../specs/sdl/profile-selections.md).
- [x] Issue: authoring/manifest alignment, including existing OS extensions —
  `packages/raes_backend_protocols/provisioner_manifest.py:13`,
  `tests/test_issue_1208_profile_boundaries.py:108` and the existing
  `tests/test_issue_1206_vocabulary_roundtrips.py` regression suite.
- [x] Issue: private generator, materialization profile and resource measure —
  `packages/raes_reference_backend/artifact_generation.py:9`,
  `packages/raes_reference_backend/mailbox_materialization.py:16` and
  `tests/test_issue_1208_resource_profiles.py:101`.
- [x] Issue: sensitivity, delivery, authority, access and accounting —
  `packages/raes/stateful_resources.py:133`,
  `tests/test_issue_1208_profile_boundaries.py:12` and
  `packages/raes_contracts/resource_measure_profiles.py:34`.
- [x] Issue: participant-control ownership and closed security enums — the
  selection ownership table names #1068–1072; `packages/raes/enterprise_identity.py:64`
  preserves trust direction, federation direction and claim owner while
  extending the containing profile selections.
- [x] Issue: fixture account/mailbox through account placement —
  `packages/raes_contracts/account_materialization.py:97` and
  `tests/test_issue_1208_profile_selections.py:325`.
- [x] Issue: granular negotiation and refusal before mutation —
  `packages/raes_contracts/profile_selections.py:87`,
  `packages/raes_reference_backend/profile_preparation.py:85` and
  `tests/test_issue_1208_profile_selections.py:347`.
- [x] Issue: authorized fixture sink, reference-only operator material and
  value-free public output — `packages/raes_reference_backend/mailbox_materialization.py:16`
  and `tests/test_issue_1208_profile_boundaries.py:34`.
- [x] Issue: reference enforcement and APTL ownership — the protected sink
  verifies authentication candidates and cleans up materialized state;
  the selection contract identifies Brad-Edwards/aptl#668 as the concrete
  mail-server owner.
- [x] Issue: no implicit profile or capture duty —
  `tests/test_issue_1208_profile_boundaries.py:94` applies the complete abstract
  model without a profile authority or evidence declaration.
- [x] Issue: exact portable typing in selected results and requested reports —
  `tests/test_issue_1208_profile_boundaries.py:34` checks persisted and API
  projections, and `tests/test_issue_1208_resource_profiles.py:101` checks the
  existing measured-settlement ledger's typed state.

No formal requirement transition is in scope. Existing DSL-435, DSL-436,
ASR-530, ASR-532 and SEM-218 traceability gains links to the new helpers and regression
tests; their status and statements remain unchanged.

The canonical evidence gate pins the complete Python implementation surface.
New formal-validation release 14.0.0 and specification-coverage release 12.0.0
replay the retained observations against this implementation without changing
their claim ceilings. Historical captures remain unchanged. The formal baseline
loader can recover an exact checksum-addressed archived artifact when a later
repository revision has changed the original path; it still requires the indexed
release and exact captured manifest and snapshot bytes.

## Review repair evidence

The complete 102-file review in
[cycle 1](https://github.com/OpenRAE/rae/issues/1208#issuecomment-5650387270)
identified one composition class and three individual boundary defects. All
four have local repairs with regression evidence:

- Composition: `raes/composition/_profiles.py` rewrites every selected host and
  nested binding through the existing symbol map. The existing node pass also
  qualifies mailbox account references. `test_issue_1208_profile_composition.py`
  covers all nine fields, imported provisioning owners, opaque-value retention,
  and `test_imported_fixture_mailbox_reaches_its_exact_authorized_sink` exercises
  authentication and cleanup after import.
- Exact authority: `test_supplied_authority_cannot_broaden_any_authored_value`
  and `test_nested_authored_binding_also_requires_its_exact_constraint` in
  `test_issue_1208_review_boundaries.py` reject weakened or missing constraints;
  `test_exact_source_constraint_preserves_unrelated_programmatic_authority`
  preserves the separate programmatic case.
- Credential admission:
  `test_mailbox_target_refuses_credentials_without_materialization_before_driver_mutation`
  rejects a credential-bearing account without its installed materialization
  owner even when another sink is configured.
- Historical evidence: `test_archive_cannot_substitute_snapshot_pins_for_an_indexed_release`
  and `test_historical_archive_pin_record_cannot_be_rewritten` in
  `test_formal_semantic_validation_review.py` require the independently pinned
  immutable archive record, exact indexed identity, and original artifact bytes.

These tests reproduced the reported defects before repair. The cycle's automatic
decision record precedes the fixes; this section records subsequent local
verification, not a new reviewer verdict. The configured one-cycle cap remains
an explicit workflow boundary.

## Self-review after the cap

The user requested a local self-review before deciding whether another review
cycle is worthwhile. This pass found and repaired four additional boundaries:

- Native reference application now uses the incumbent profile-selection
  validator to reject absent authority, omitted bindings, substituted binding
  identities, out-of-constraint values, and bindings attached to deletion.
  The runtime wrapper's validation remains independently enforced.
- Failed operational readback blocks new mailbox credential and generated-output
  publication. Deleted mailbox credentials are still revoked and outdated
  generated projections invalidated after successful driver changes. Native
  resources already created remain in recoverable inventory with their changed
  addresses; this does not claim to roll back preceding driver effects.
- Credential-result sanitization accepts failed readback inventory only when it
  passes the same exact, closed, value-free projection as a successful result.
  This preserves native cleanup inventory through the runtime manager without
  admitting arbitrary partial entries or credential material into public results.
- Shared service admission and libvirt capability checks recognize both JSON
  mappings and typed binding objects. Direct Python submissions cannot bypass
  profile support checks by changing the carrier representation.

`test_issue_1208_self_review.py` locks these cases, and the existing native
capability tests now cover both representations. The mailbox-native negative
tests prepare their bindings first so each test still exercises its intended
semantic or authorization refusal. The review also checked composition identity,
exact recursive constraints, resource accounting, and the authenticated archive
pins. This is local verification, not another independent review verdict.

## Authorized second review cycle

The user authorized one additional review. Cycle 2 covered all 110 files across
two slices; its [findings](https://github.com/OpenRAE/rae/issues/1208#issuecomment-5655808629)
and [decision record](https://github.com/OpenRAE/rae/issues/1208#issuecomment-5655808812)
identify one recurring recognition defect and one mailbox ownership defect.

- `profile_selection_binding` now recognizes typed selections through the
  canonical binding model independently of whether callers serialized default
  fields. The six-site sweep covers source defaulting, both composition paths,
  authored plan authority, shared service admission, and the native libvirt
  capability envelope. Known legacy service mappings retain their defaults;
  malformed typed mappings cannot escape validation by adding legacy fields.
- Mailbox posture and inventory completeness checks now apply only to the exact
  references selected by account-materialization bindings. Exact account/target
  joins, uniqueness, fixture ownership, and protected sink authorization remain
  binding. Ordinary mailboxes and services retain their incumbent operational
  verification; absent selections create no materialization requests.

Regression evidence is in `test_issue_1208_overcap.py`:
`test_default_version_service_binding_retains_direct_plan_authority`,
`test_legacy_service_default_is_preserved_without_mutating_input`,
`test_malformed_profile_cannot_fall_back_to_legacy_service_shape`,
`test_selected_mailbox_does_not_claim_unrelated_inventory`, and
`test_unselected_mail_inventory_creates_no_materialization_request`.
The existing composition, native capability, and shared service gate cases also
run with serialized defaults omitted. Those cases reproduced the recognition
defect before repair; the mixed-inventory case reproduced the selected-profile
posture leaking to an ordinary mailbox. This records post-fix local evidence,
not a new independent reviewer verdict.

## Integration with current dev

The pre-PR synchronization merged dev at
`b5590207172ff2ce5fd2616d497024bb50164731`. Generated schemas were rebuilt
from the combined typed-selection, software-refinement and partial-inventory
models, with matching publication records. The incoming historical formal
captures through release 13.0.0 and coverage captures through release 11.0.0
retain their original bytes. This branch's new captures use the next available
revisions, replayed against the merged implementation; the formal baseline is
release 13.0.0. The preregistered protocols and claim limits remain unchanged.

The user authorized continuation without another code-review cycle after both
second-cycle findings were repaired. The initial test-quality review was clean.

The integration gate also caught two archive-test fixtures that inherited the
now-corrected release-10 baseline pointer. Both tests now explicitly select the
frozen archive from its pin record, prove that original selection succeeds, and
then reject the forged manifest or altered pin record. This preserves their
intended tampering boundary without changing production validation or history.

## Sonar maintenance repair

The first hosted analysis reported 40 maintainability findings and no security
hotspots. The repair separates source/profile recognition, owner lookup, mailbox
posture, service capability admission, generated-output projection, and archive
loading into bounded helpers. It reduces unnecessary early returns, supplies
composition mapping type arguments, and isolates exception-test subjects.
Existing authority, credential, readback, cleanup, and archive-tampering
regressions remain binding; 655 focused tests and the static lane pass.

Formal release 15.0.0 and coverage release 13.0.0 record fresh replay for this
refactor without modifying earlier captures. Formal observations have zero
deviations from release 14.0.0.

The second hosted analysis cleared 39 of the 40 findings and reported one file
size violation in the retest validator. Header validation now lives in its own
focused module; this is a structural move with unchanged validation rules.
