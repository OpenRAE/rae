# Issue 1207: Partial inventory descriptions and selected admission

This delivery implements DSL-132, DSL-134, DSL-136, DSL-137 and SEM-218.
The native blocker #1204 was closed before implementation began. The
[implementation plan](https://github.com/OpenRAE/rae/issues/1207#issuecomment-5649707712)
and the architecture notes record the audit and existing-owner inventory.
SEM-218 supplies the shared declaration/delegation semantics; its inclusion
does not replace the four inventory requirements or create another executor.

## Decision and adjacent-family audit

The #959 rubric distinguishes structural integrity, explicit contradiction,
selected-operation prerequisites, and completeness inferred from one specimen.
Only the last category is removed from universal description validity.

| Surface | Audit disposition |
| --- | --- |
| Datastore | Remove mandatory persistence, search partitions/mappings/geometry and wide-column replication. Keep bounds, IDs, references and the explicit key-value/keyspace-or-column-family contradiction. |
| Forwarding | Remove kind-specific buffer/destination requirements and API-pull/IOC/reload recipes, including negative bans on otherwise valid pipeline composition. Keep endpoint types, classification and scoped references. Compare supplied known protocols for contradiction; a listener role alone does not demand a known port. |
| Orchestration | Permit unknown interface knowledge. Resolve every supplied concrete same-node reference. Neither `docker.sock` spelling nor read-write mount declaration proves effective privilege. Selected privileged operations independently require authorized supported access. |
| Application authorization | Permit empty, omitted, deny-only and mixed partial grant inventories. The store vocabulary is scalar; coverage is not effective access. Keep local grant/mapping role references and posture-only credentials. |
| Relational database | Permit omitted/unknown protocol; default omission to unknown so instantiation does not fabricate an incompatible `other`. Retain explicit incompatible engine/protocol rejection, object/grant references and redaction. |
| Platform applications | Preserve #956's composable capability correction and optional configured state; product identity does not restore a mandatory MISP recipe. |
| Directory, local identity, file and mail inventories | Keep distinct principal/reference ownership and existing closed credential postures. No cross-family raw-credential or generic configuration surface is introduced. |

The motivating counterexamples have independent domain support: Redis can run
with [persistence disabled](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/);
OpenSearch's [create-index API](https://docs.opensearch.org/latest/api-reference/index-apis/create-index/)
has optional settings and mappings; [Syncthing](https://syncthing.net/) supplies
a non-IOC file-synchronization example. Docker documents
[daemon access as a security boundary](https://docs.docker.com/engine/security/),
not a portable filename test. These examples refute universal recipes; they
do not select a backend, imply permissions, or install executable support.

Alternatives rejected: replacing known discriminators with sentinel values,
fabricating grants/configuration, a global partial-validation switch, a new
profile registry/executor, and using resource-label profiles as a substitute
for inventory semantics. The existing profile host already performs independent
trust/support admission and invokes installed semantics on the backend's selected
completion before apply. This change adds no production datastore or orchestration
executor. Tests install explicitly synthetic inventory semantics at that real
host; the reference backend's existing resource-label implementation remains
limited to labels.

## Clause mapping

Package paths below are relative to `implementations/python/packages/`; test
paths are relative to `implementations/python/tests/`. Line references point to
the owning implementation entry, with focused test files naming the assertions.

- [x] DSL-132: one typed node-scoped data-model surface, without overloading relational, transport, filesystem or component identity — `raes/runtime_datastore.py:84`; `raes/runtime_configuration.py:1`.
- [x] DSL-132: cluster/node topology, partitions and geometry — `raes/runtime_datastore_partitions.py:1`; retained full-family examples in `test_runtime_datastore.py:1`.
- [x] DSL-132: templates, aliases, bounded mappings, lifecycle/ingest, persistence/eviction, pubsub/streams/plugins, transport/backup/settings and referenced authorization — `raes/runtime_datastore.py:84`; `raes/runtime_datastore_partitions.py:1`; `raes/validator/_runtime_platform.py:1`.
- [x] DSL-132: partial/empty state without universal completeness, retaining supplied integrity and selected obligations — `raes/runtime_datastore.py:84`; `test_issue_1207_partial_descriptions.py:1`; `test_issue_1207_profile_admission.py:1`.
- [x] DSL-134: shared app-internal store referenced by datastore/platform, separate from OS/directory/relational identity — `raes/runtime_app_authorization.py:255`; `raes/validator/_runtime_platform.py:1`.
- [x] DSL-134: classified principals, roles, resource-scoped grants, mappings, tenants and auth posture — `raes/runtime_app_authorization.py:100`; `raes/runtime_app_authorization.py:255`.
- [x] DSL-134: empty/partial grants without invented coverage; references and credential classification remain validated — `raes/runtime_app_authorization.py:255`; `raes/validator/_runtime_services.py:1`; `test_runtime_app_authorization.py:1`.
- [x] DSL-134: actual selected coverage at admission — `raes_runtime/backend_profiles.py:1`; `raes_runtime/backend_preparation.py:228`; `test_issue_1207_profile_admission.py:1`.
- [x] DSL-136: typed node-scoped kind, sources/parse/selectors, transforms and targets with ingestion/enrollment/classification — `raes/runtime_forwarding_agent.py:89`; `raes/runtime_forwarding_agent.py:259`.
- [x] DSL-136: buffer/reload/settings without overloading manager/detection/process/evidence surfaces — `raes/runtime_forwarding_buffer.py:1`; `raes/runtime_forwarding_agent.py:192`.
- [x] DSL-136: partial/composed pipelines, scoped references, bounds/redaction and selected completeness — `raes/runtime_forwarding_agent.py:259`; `raes/validator/_relationships.py:108`; `test_runtime_forwarding_agent.py:1`; `test_issue_1207_profile_admission.py:1`.
- [x] DSL-137: typed authority references existing control interfaces; engine/version/scope/templates/lifecycle/children/privilege remain separate from mount and transport surfaces — `raes/runtime_orchestration.py:70`; `raes/runtime_orchestration.py:121`.
- [x] DSL-137: partial interface knowledge and concrete same-node reference integrity — `raes/validator/_runtime_orchestration.py:7`; `test_runtime_orchestration.py:1`.
- [x] DSL-137: independently authorized supported selected privileged access — existing `raes_runtime/backend_preparation.py:228`; `raes_runtime/control_plane_plan_authorization.py:1`; `test_issue_1207_profile_admission.py:1`; `test_issue_1204_reference_profiles.py:1`.
- [x] SEM-218: distinguish binding supplied declarations from open descendants — `raes_processor/compiler/realization_recursive_constraints.py:1`; `raes_contracts/realization_structure/_evaluation.py:1`; `test_issue_1207_recursive_inventory.py:1`.
- [x] SEM-218: realization permitted only under resolved authority, explicit choices honored and unsupported exact requests rejected — existing `raes_processor/planner/realization_preparation.py:153`; `raes_runtime/backend_preparation.py:228`; `test_issue_1207_profile_admission.py:1`.
- [x] SEM-218: stable nested identity without positional weakening — `raes/runtime_inventory.py:15`; `raes_processor/semantics/realization_runtime_concern_profiles.py:1`; `raes_processor/semantics/realization_specialized_projection.py:1`; `test_issue_1207_recursive_inventory.py:1`.
- [x] Issue: partial datastore/forwarding/orchestration descriptions do not invent facts or authorization — `test_issue_1207_partial_descriptions.py:1`.
- [x] Issue: selected completeness, trust/authority and required evidence remain enforced — `test_issue_1207_profile_admission.py:1`; `test_issue_1207_description_lifecycle.py:1`; existing authenticated and durable-carriage tests in `test_issue_1204_reference_profiles.py:1`.
- [x] Issue: nonpersistent cache, partial search/wide-column, non-IOC synchronization and incomplete privileged interface counterexamples — `test_issue_1207_partial_descriptions.py:1`.
- [x] Issue: adjacent audit and empty versus omitted/unknown state — audit above; `test_issue_1207_recursive_inventory.py:1`; `test_issue_1207_partial_descriptions.py:1`.
- [x] Issue: preserve #956 capability semantics and sensitive-value boundaries — `test_runtime_platform_application.py:1`; retained family redaction/reference tests; `test_issue_1204_prepared_credentials.py:1`.
- [x] Issue: backend-resolvable prerequisites inside open scopes are not compulsory author detail — `test_issue_1207_profile_admission.py:1` (paired incomplete/selected-completion cases and explicit-false refusal).
- [x] Issue: complete abstract execution and incomplete observations are distinct valid cases without automatic evidence — `test_issue_1207_description_lifecycle.py:1`; source-preserving round trips in `test_issue_1207_partial_descriptions.py:1`; existing description lifecycle in `test_issue_1209_description_lifecycle.py:1`.
- [x] Issue: preserve selected verification and #1112 required capture — `test_issue_1207_description_lifecycle.py:1`; `test_issue_1112_capture_admission.py:1`; delivery mismatch and missing corroboration in `test_issue_1207_profile_admission.py:1`.

## Delivery boundaries and verification

The test backend models admission and delivery claims, not live service
installation. Its explicit observation disclosures are synthetic test inputs;
neither a successful hook nor an echoed inventory proves real-world execution.
Rejected delivery preserves the trusted portable predecessor, not an implied
infrastructure rollback. Production authentication, replay, and required capture
continue through the existing control plane and store, with their incumbent tests.

Accepted ADR-029/046/048/050/051 amendments, publication hashes and reference
schema parity record the contract correction. Requirement statuses remain ACTIVE;
traceability changes become authoritative only when the delivery PR merges.
Ownership adds only the exact affected contract and documentation records to
SEM-218's existing policy phase, with an exclusion regression; no gate exception
or union of unrelated requirement links is used.

Source-bound research gates also required fresh captures. Formal release 13
and specification-coverage release 11 retain their preregistered cases,
classifications and claim limits after replay of the merged tree. The formal
index documents preservation of the incoming historical releases and their
baseline-link repair; no historical observation is relabeled as current evidence.

TDD recorded failing partial-description cases and positional-identity cases
before production changes, plus a failing omitted-protocol instantiation case
before correcting its default. The focused regression command also covers
the existing full inventory, #956, #1204 authentication/delivery, #1112 capture,
and #1209 description lifecycle suites. Ground Control's completion, review,
publication and readiness records own final verification status; this mapping
does not claim those gates passed before they run.
