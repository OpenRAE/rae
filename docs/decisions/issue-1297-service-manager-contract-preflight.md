# Issue 1297: Service-manager native identity and state preflight

Date: 2026-09-17. Inspected revision: `08c363f699a8`, branch
`1297-separate-service-manager-contract`.

This note is architecture guidance for issue #1297. The supplied issue is the
authoritative contract; there is no Ground Control requirement. This note does
not implement the issue, change a published schema, amend an accepted ADR, or
claim live service-manager support.

## Baseline findings

The defect crosses more than `_validate_unit_name()`:

- `ServiceManagerUnit(unit_id="web", manager_kind="x-openrc:openrc",
  unit_name="nginx")` is rejected by the Python model because the native name
  lacks a dot, while the generated authoring schema accepts the same record.
  The current schema therefore does not express the model's unconditional
  systemd suffix rule.
- A private-manager record that uses a fabricated-looking suffixed name parses,
  but a full model dump adds `unit_type=other` and systemd-shaped
  load/active/enabled/result defaults. Identity extension has not made the
  surrounding state contract portable.
- An omitted manager currently reads as `systemd` in the model. Nevertheless,
  under an authored open realization parent the compiler correctly uses
  instantiation explicitness provenance and lowers that omitted leaf to a
  delegated value. The default is not an authored constraint. This distinction
  is already carried by `model_fields_set`, `InstantiationProvenance`, and the
  recursive realization contract and must not be replaced with truthiness or a
  serialized-default test.
- `runtime-service-manager-units` is registered as a typed realization concern,
  but its collection identity is not explicitly declared as `unit_id`.
  Projection sorting currently finds `unit_id` through a generic `*_id`
  heuristic. Native-name portability and keyed comparison must not depend on
  that incidental fallback.
- The concern profile excludes `sub_state`, `result`, `exit_code`,
  `status_text`, and `main_pid` from desired-state comparison. These remain
  outcome/observation facts; their exclusion must not be interpreted as
  service presence, a live process, or successful execution.

## Architecture decisions

### Keep one portable row and one manager-specific semantic seam

`ServiceManagerUnit` remains the node-scoped owner. Its portable core is:

- required stable `unit_id`, used for author references and collection
  matching;
- presence-sensitive governed `manager_kind`;
- optional exact native `unit_name`, preserved byte-for-byte as supplied;
- the existing optional same-node `service` reference, native unit-file path,
  description, and their current reference/path rules.

`unit_name` is native data, not `unit_id`, a vocabulary term, or a portable
systemd name. When supplied it remains concrete, nonempty, and free of
whitespace and variable placeholders, but the portable validator must not
require a dot, normalize the name, infer its type, or append `.service`.
Omission represents missing knowledge; it does not authorize deriving a name
from `unit_id`, a service ref, a package, a process, or a path.

The existing unit-kind, load, active, enablement, result and `ExecStart`
meanings are a typed **systemd state profile**, not universal service-manager
state. Existing flat field spellings are the compatibility projection of that
one profile and remain valid for explicit systemd records. They must not become
a second semantic authority beside a new nested copy. A non-systemd record may
carry portable identity/name/reference facts without these fields. Rich state
for another manager uses the existing exact, pinned domain-profile definition,
binding, local resolution, and operation-support mechanisms; it does not add an
OpenRC/launchd/Windows/supervisord enum catalog or a raw configuration bag to
core SDL.

Selecting `manager_kind: systemd` selects the standard systemd contract and its
naming/state validators. An exact private `x-owner:value` manager is inert
identity, not proof that its state schema, comparison, capture, or execution is
supported. `unknown` and `other` remain knowledge states, not manager selection
or delegation. A whole-field variable may defer manager selection during
authoring, but instantiated concrete validation must apply the selected
contract before compilation or comparison.

### Preserve legacy omission without inventing new knowledge

Compatibility and partiality use the existing presence/closure owners:

- An explicitly supplied `systemd` manager keeps current names, state values,
  redaction behavior, and rejection of malformed systemd names.
- A legacy omitted-manager record retains its historical systemd interpretation
  only through the incumbent omission/default compatibility semantics. Do not
  infer legacy status from a dot, a state value, installed package version, or
  trial-and-error validation.
- Under an inherited open scope, omitted `manager_kind`, `unit_name`, and state
  leaves remain omitted/delegated according to recursive realization metadata.
  A default-filled Pydantic object or snapshot payload is not proof that the
  author selected systemd.
- Explicit `unknown` is unrecovered knowledge and must compile as knowledge,
  not delegation. Omission is delegation only where the enclosing realization
  authority actually opens that scope.
- Exact supplied siblings remain binding under an open parent. In particular,
  a supplied native name must survive unchanged even when the manager choice is
  omitted.

Model-local validation cannot decide inherited realization closure. Generic
native-name shape belongs in the model; the scope-aware semantic/compiler
boundary owns the legacy-default versus open-omission decision. Do not restore
the bug by making the base model assume systemd whenever `manager_kind` is
absent. Do not weaken explicit-systemd validation merely because an open form
also exists.

If a persisted historical artifact needs a reader migration, use the existing
named snapshot/source profile and migration owners. Authenticate the original
artifact before conversion, preserve its original identity, and emit a distinct
derived artifact. A schema hash or the presence of `.service` is not a semantic
revision selector.

### Keep presence, process, execution, and exposure separate

- A unit row says the inventory contains a service-manager unit requirement or
  description at the selected semantic depth. It does not prove a unit file is
  present, a process exists, a listener is exposed, or a command succeeded.
- `main_pid` is observed process linkage, not process inventory and not proof
  of active state. `runtime.processes` remains the process owner.
- `result=success` is a manager outcome under the systemd profile. It is not
  transport readiness, condition truth, or experiment success. Conversely,
  failed, inactive, disabled, and active/exited units may have no process.
- `service` remains a same-node `Node.services[]` transport reference. It grants
  no lifecycle authority and does not mutate the service.
- `unit_file_path` remains inert path evidence subject to the current optional
  filesystem-inventory cross-check. It is not a file read, executable path, or
  service-manager selection.
- Configuration/presence/enablement fields and outcome-only
  `sub_state`/`result`/`exit_code`/`status_text`/`main_pid` keep their existing
  realization-comparison disposition unless a separately governed observation
  change is made. Dropping an outcome field from equality must never synthesize
  a successful or unchanged result.

### Make round-trip and comparison identity explicit

The service-manager concern must declare `unit_id` as its collection identity
through the existing `RuntimeConcernProfile`/recursive-constraint seam. Native
`unit_name` remains compared data when present, never the collection key.
Reordering must not change meaning; duplicate nonempty `unit_id` and native-name
records remain rejected by `RuntimeConfiguration`.

Authoring, instantiated, materialized, and canonical instantiated-snapshot
forms must preserve omission provenance and exact supplied native names.
Typed observation/snapshot projection must not populate non-systemd records
with systemd defaults. Apply presence-sensitive projection at the existing
typed concern projector/sanitizer boundary rather than changing global
`model_dump()` behavior or adding another comparison engine.

## Canonical incumbents and required reuse

| Concern | Canonical owner and guardrail |
| --- | --- |
| Source and local shape | `raes/_yaml_loader.py`, `_source_validation.py`, `_mapping_key_analyzer.py`, `_source_profile.py::SDLParserLimits`, `parser.py`, and `_base.py::SDLModel`. Preserve safe bounded YAML, canonical keys, variables, and `extra="forbid"`; do not add a service-manager parser. |
| Portable model | `raes/runtime_service_units.py`, shared `runtime_values.py` and `_base.py` helpers. Keep `require_symbol`, governed vocabulary parsing, integer/path bounds, and `ServiceUnitExecStart` redaction. Manager-specific validation is selected, not unconditional. |
| Identity vocabulary | `raes/runtime_vocabulary.py`, `raes_contracts/controlled_vocabularies.py`, `runtime_vocabulary_scopes.py`, and `contracts/concept-authority/controlled-vocabularies-v1.json`. Keep `ServiceManagerKind` as one governed identity family; private identity grants no support. |
| Profiles | `raes_contracts/domain_profiles.py`, `_domain_profile_resolution.py`, `_domain_profile_validation.py`, `_domain_profile_admission.py`, and `realization_profiles.py`. Reuse exact coordinate/digest, local-only bounded schema resolution, binding owner/use, and operation-specific support for non-core manager state. |
| Duplicates and references | `RuntimeConfiguration.validate_unique_runtime_entries()` and `SemanticValidator._verify_runtime_service_manager_units()`. Keep duplicate IDs/names, same-node service resolution, variable deferral, and filesystem path cross-checks in their current owners. |
| Partiality and instantiation | `raes/explicitness.py`, `realization_designation.py`, `instantiate.py`, `phase_contracts.py`, `raes_contracts.realization_structure`, and processor recursive-constraint compilation. Preserve absent/default/exact/unknown/delegated distinctions and concrete post-substitution revalidation. |
| Compilation and comparison | `realization_runtime_concern_profiles.py`, `realization_typed_runtime_projection.py`, `realization_specialized_projection.py`, `realization_concerns.py`, `realization_requirements.py`, and `realization_snapshot_sanitization.py`. Keep one concern descriptor, explicit `unit_id` identity, safe typed observation projection, and existing outcome exclusions. |
| Schemas and canonical snapshots | `raes_contracts/contracts/bundle.py::schema_bundle()`, `raes/canonical.py`, `tools/generate_contract_schemas.py`, `tools/check_generated_schemas.py`, and the schema-publication entries. Python and all published SDL lifecycle schemas must move together; generated files are not an independent authority. |
| Errors and diagnostics | `raes/_errors.py`, `_model_diagnostics.py`, `raes_contracts/diagnostics.py::Diagnostic`, planner/runtime diagnostics, and redacted API handlers. Reuse bounded structured errors; do not add a service-manager exception or logger hierarchy. |
| Persistence | `RuntimeSnapshot`, `RuntimeSnapshotEnvelopeModel`, `ControlPlaneStore`, `LocalControlPlaneStore`, store codecs, and canonical instantiated snapshots. Validate and sanitize before persistence; no service-manager table, cache, or sidecar. |
| Workflow | `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`, `tools/check_repo_policy.py`, `tools/check_requirement_governance.py`, and `tools/verify_all.py`. Use the requirement-free issue lane; do not invent a UID, version bump, or changelog entry. |

Service-manager units intentionally remain outside the ref-targetable
`RUNTIME_SERVICE_FAMILIES` registry. `unit_id` becoming explicit comparison
identity does not by itself make units general relationship targets. Promotion
would require the registry, module aliasing, qualified-reference semantics,
composition, docs, and tests to change together and is outside this issue.

## Cross-cutting security and runtime gates

| Layer | Required treatment |
| --- | --- |
| YAML/JSON ingress and config shape | Apply parser byte/scalar/depth/node/alias limits, key diagnostics, closed Pydantic models, and equivalent direct-model/schema validation. Profile values, if used, remain closed bindings resolved from an explicit bounded local context; no remote `$ref`, ambient filesystem search, environment lookup, or executable callback. |
| Model and semantic validation | Generic names reject empty/whitespace/variable values without imposing a manager grammar. Explicit systemd applies its suffix/state/exit-code rules. `RuntimeConfiguration` keeps duplicates; `SemanticValidator` keeps same-node refs and resolves scope-sensitive legacy omission. Instantiation reruns concrete validation. Do not duplicate these checks in a backend. |
| Secret and environment surface | Retain `ServiceUnitExecStart`'s `command_kind` plus `command_redacted` invariant and the shared JSON-Schema redaction helpers. Secret-bearing argv stays omitted. This issue adds no environment-variable, secret-reference, credential-store, or generated-artifact binding. Native names, paths and bounded status text must not become covert raw configuration or journal-output carriers. |
| Auth and admission | Description parsing adds no authority. Existing `ControlPlaneSecurityConfig`, `_ControlPlaneApiAuth`, request-size/idempotency/target checks, planner authorization, and backend profile support remain authoritative if the concern reaches an operation. A manager identity, profile binding, unit path, PID, or service ref grants no permission to contact or control a daemon. |
| Host/OS exposure | Parse, schema, instantiation, compilation, snapshot, and comparison perform no `systemctl`, OpenRC command, DBus/socket access, process spawn, file read, or network retrieval. Any later live adapter must use its existing admitted backend owner, fixed argv/no shell, bounded time/output, restricted environment, and secret-safe channel. No token or raw command/profile value enters argv, logs, audit, or native object names. |
| Backend return and comparison | Revalidate returned values through the same typed concern/profile contract, sanitize before comparison/persistence, and refuse unsupported required semantics before mutation. Inventory equality is not execution success or independent observation. Preserve the trusted predecessor on rejected returned state through existing result-admission behavior. |
| Error envelopes and logging | Parser diagnostics remain source-anchored and bounded; runtime diagnostics use stable codes and value-free messages. Redacted 422/500 handlers remain unchanged. Because operation routes can expose `str(ValueError)` in 409 responses, new profile/admission failures must not interpolate native output, command text, profile payloads, paths containing credentials, or Pydantic inputs. No new logging sink. |
| Persistence/replay | Store only admitted, sanitized existing DTOs through current atomic/CAS codecs. Durable reload must retain manager/profile identity, exact native name, omission provenance where the carrier owns it, and redaction markers. Replay performs no profile discovery or service-manager access. |

## Gotchas and acceptance evidence

- Do not fix only `_validate_unit_name()`. That would leave default-filled
  state, schema/model disagreement, unkeyed comparison, and legacy/open
  semantics unresolved.
- Do not make every name with a dot systemd, and do not strip or append suffixes.
  A native name is not a discriminator.
- Do not turn `unknown`, `other`, omission, a private token, or a profile-shaped
  payload into the same state. Unknown is knowledge, omission follows scope,
  private identity is exact, and profile support is separately admitted.
- Do not place manager-specific state in `dict[str, Any]`, metadata, snapshot
  metadata, or `status_text`. Do not create one core enum/model branch per
  service manager.
- Do not globally switch model serialization to `exclude_unset`; canonical and
  instantiated artifacts deliberately carry defaults plus explicitness
  provenance. Make service-manager projection presence-sensitive at its owner.
- Do not key units by native name or list position. `unit_id` is portable and
  stable; name changes are compared facts.
- Do not add service-manager discovery/execution or claim a model/schema
  round-trip proves a live manager, process, listener, or successful command.

Implementation evidence must cover one explicit systemd record, one
`x-openrc:openrc` record named exactly `nginx`, one other private-manager name,
one open-parent record with omitted manager/name choices, and one legacy
omitted-manager record. Exercise direct model and generated-schema validation,
YAML parsing, semantic validation, instantiation, recursive compilation,
canonical snapshot reload, typed concern projection, snapshot sanitization,
and declared/observed comparison. Preserve negative coverage for malformed
explicit-systemd names, duplicate IDs/names, unresolved/cross-node service
refs, inconsistent result/exit code, unsafe command redaction, altered returned
profile identity, and unsupported manager-specific semantics. Tests must state
that they exercise contracts only, not live service-manager execution.

## Documentation, migration, and non-goals

The implementation must reconcile ADR-035's “initially systemd” text and its
claim that manager identity alone is the extension seam. Because ADR-035 is
accepted, follow ADR-059: add an amendment row and matching `adr-index.yaml`
entry/pin update, or supersede it; never silently edit it. Update the vocabulary
policy wording and `specs/sdl/runtime-inventory.md` if their claims change.
Schema changes require model/generator parity, the hand-governed authoring,
instantiated, materialized, and instantiated-snapshot schemas, publication
entry hashes/summaries, and migration/fixture evidence. Do not hand-edit a
generated schema without the owning model change.

Non-goals are live OpenRC/systemd/launchd/Windows/supervisord discovery or
control; provisioning, restart or readiness policy; a universal normalized
lifecycle ontology; process/listener/file inference; new evidence collection,
retention or export; registering units as general runtime-family refs; adding a
backend, API, store, cache, logger, exception hierarchy, secret resolver, or
configuration bag; changing release versions or `CHANGELOG.md`; and completing
#1211's integrated acceptance. The boundary here is portable unit identity plus
an honest, explicitly selected manager-specific state contract.
