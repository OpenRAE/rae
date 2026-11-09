# Runtime inventory verification — issue 1784

This reference maps the issue to native Go assertions.
It does not replace the SDL specification or claim formal proof.
The design is [recorded separately](issue-1784-runtime-inventory-design.md).
Python and the published schemas are unchanged.

## Reference and owners

The starting Go revision is `17bf4515bf12747af69c8598a2fc82d73e9651b9`.
Each new fixture records the unchanged Python source revision.
The recorder refuses a different revision.
The runtime constructor manifest lists all 180 published model definitions and their Python owners.
It retains 4,406 independent constructor verdicts.
Shared baselines and existing field-change records avoid repeated input bodies.
Every model has a positive case.
The three case files stay below the repository file-size limit.

`internal/contract/sdlrules` owns the shared collection tree and collection identity lookup.
`contract/admission` owns field and local model checks.
`internal/sdl/authoring` owns construction, semantic joins, source locations, and admission state.
The existing scalar, vocabulary, canonical JSON, digest, and value owners retain their roles.
Paths below are relative to `implementations/go/` unless stated otherwise.

## Issue acceptance

| Criterion | Implementation and assertions |
| --- | --- |
| Golden runtime cases keep results and locations | `internal/sdl/authoring/semantic_api_test.go:TestSemanticReference` includes 232 `runtime-*` cases. It compares ordered errors, warnings, locations, canonical bytes, and digests. `semantic_corpus_test.go:TestSemanticCorpusReference` checks retained source inputs in CI. |
| Common structures have one implementation | `internal/contract/sdlrules/runtime_inventory.go:RuntimeFamilies` supplies both reference indexing and collection checks. Existing normalizer, field predicates, and identity helpers remain shared. |
| Runtime surfaces reproduce the reference | `contract/admission/runtime_constructors_test.go:TestRuntimeConstructorReference` covers all 180 runtime model definitions. Existing constructor, formatter, and semantic oracles retain their distinct stages. |
| Input limits and protections remain | Constructor range and text cases check numeric bounds, integer spelling, Unicode lengths, paths, identities, and withholding. `runtime_limits_test.go:TestRuntimeInventoryCollectionLimits` checks each software inventory collection at 256 and 257 entries. Existing source and portable-value tests retain ingress and work limits. |
| Error and recovery behavior remains | Runtime semantic cases retain missing targets, variable deferral, absent inventories, multiple errors, and finding order. Process-limit cases retain projection copies, exact identity, finite domains, and explicit refusal. |
| Historical defect behavior remains | The table below names the in-scope behavior and its native assertions. Execution and compiler assertions keep their separate delivery owners. |
| Findings are addressed | The descriptor tree has one owner. Existing family predicates remain separate. Python class names and export machinery are not a Go domain hierarchy. |
| Design passes before code | The issue has trusted preflight and design records. `archcheck -design` passed before source changes. The model declares the exact changed shared API. |
| Hosted quality checks pass | The delivery workflow retains architecture, lint, coverage, regression, parity, and security checks. CI owns full test, race, fuzz, and mutation runs. Readiness requires observed hosted results. |

## Family coverage

All listed models enter the runtime constructor oracle.
Each model receives a positive case and relevant field changes.
Numeric fields also receive boundary, fractional, boolean, and variable cases.
The existing constructor oracle adds cross-field and duplicate-identity cases.

| Python source family | Native semantic cases and rule owner |
| --- | --- |
| Application and exposed values | `runtime-application-*`; `semantic_runtime_applications.go` |
| Relational databases | `runtime-database-*`; `semantic_runtime_database.go` |
| Datastores and node topology | `runtime-datastore-*`; `semantic_runtime_platform.go` and local datastore rules |
| DNS and record data | `runtime-dns-*`; `semantic_runtime_database.go` and local DNS rules |
| Local and directory identities | `runtime-identity-*`, `runtime-cloud-*`; identity and cloud semantic rules |
| File services and filesystem | `runtime-file-*`, sensor file cases; `semantic_runtime_files.go` and filesystem predicates |
| Mail service and children | `runtime-mail-*`; `semantic_runtime_mail.go` |
| Monitoring and detection definitions | `runtime-monitor-*`; `semantic_runtime_monitoring.go` |
| Sensors and detection engines | `runtime-sensor-*`, `runtime-detection-*`; `semantic_runtime_sensors.go` |
| SSH and service-manager units | `runtime-ssh-*`, `runtime-service-unit-*`; authorization and application semantic rules |
| Application authorization | `runtime-authorization-*`; `semantic_runtime_authorization.go` |
| Platform applications and secrets | `runtime-platform-*`, `runtime-cloud-*`; platform and cloud semantic rules |
| Forwarding agents | `runtime-forward-*`, `relationship-forward-*`; forwarding semantic rules |
| Orchestration authority | `runtime-orchestration-*`; `semantic_runtime_platform.go` |
| Network, container, processes, and capabilities | `runtime-network-*`, `runtime-listener-*`, `runtime-process-limit-*`, `runtime-capability-*` |
| Scheduled jobs, software, packages, mounts, and environment | Direct model cases and existing formatter cases; shared source, field, and local model owners |
| Registry and pure helpers | `TestRuntimeCollectionReference`, `TestRuntimeCollectionsAreIndependent`, and `TestRuntimeProcessLimitReference` |

Vocabulary modules feed existing governed scalar normalization.
They do not add a second enumeration hierarchy.
The metadata oracle compares all 17 family trees and 255 collection lookups.
It includes nested children, malformed indices, Unicode digits, escaped names, and unknown families.
Copy tests cover nested descriptor storage and process command storage.

## Defect and protection cases

| Python defect source | In-scope native assertion |
| --- | --- |
| `test_issue_847_runtime_package_repositories.py` | APT constructor and formatter cases retain HTTPS, token, architecture, and component rules. |
| `test_issue_1043_forwarding_agent_posture.py` | Forwarding constructor cases retain ownership role; semantic evidence-source cases retain eligibility. |
| `test_issue_1066_runtime_resource_limits.py` | `TestRuntimeProcessLimitReference`, `TestRuntimeProcessLimitIdentityBounds`, and `runtime-process-limit-*` cases. |
| `test_issue_1074_generated_artifact_env_consumers.py` | Environment constructor cases and `stateful-environment-*` semantic cases retain literal/reference exclusion, output identity, and secret classification. |
| `test_issue_1078_runtime_boundary_coverage.py` | Direct runtime model cases retain typed family fields. Compiler projections and operational observation stay with their respective port issues. |
| `test_issue_1206_runtime_vocabularies.py` | Existing enum, private-identity, variable, and vocabulary formatter cases retain spelling and scope. |
| `test_issue_1207_recursive_inventory.py` | All registered child identity paths enter `TestRuntimeCollectionReference`. |
| `test_issue_1678_cycle2_pointers.py` | Canonical ASCII array-index tests reject leading zeros and non-ASCII digits. |
| `test_issue_1759_runtime_constraint_budget.py` | Existing `contract/admission` constraint-limit tests retain bounded contract evaluation. Compiler scope-tree construction remains with the processor port. |
| `test_runtime_observed_values.py` | Constructor withholding cases retain raw-value omission, permitted empty defaults, and advisory-only name heuristics. |
| `test_runtime_family_invariants.py` | The independent family tree oracle and shared constructor checks retain collection identity and child shape. Python class-name checks do not apply to Go. |

A Python test that also drives a compiler or backend does not move that operation into this issue.
Its authored model, references, and protection checks remain in scope here.
No execution, acquisition, capture, credential lookup, or host operation is added.

## Verification commands

Run targeted native cases in the affected package.
Use `-run` to select a named test or its relevant subtests.
The existing recorder has two added modes:

```shell
implementations/python/.venv/bin/python tools/parity_sdl_constructors.py --runtime-helpers --check
implementations/python/.venv/bin/python tools/parity_sdl_constructors.py --runtime-constructors --check
```

CI runs these beside the existing independent recorder checks.
The Go tests use recorded data only.
Product Go never invokes Python.
The field-predicate recorder reuses existing scalar-plan analysis.
It retains integer and fractional-number bounds as separate operations.

Local evidence includes focused red and green cases, targeted native oracles, architecture checks, lint, file-local policy, and changed-path prose checks.
The PR records exact commands and observed hosted results.
A passing style linter does not establish technical accuracy or complete STE conformance.
