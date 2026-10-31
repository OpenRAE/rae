# Issue 975: independent crossing reproduction

Requirements: SEM-232, ASR-535.
This note sets the design limits for issue 975.
It reports no native result or review acceptance.
[ADR-100](adrs/adr-100-participant-crossing-bisimulation.md) remains the authority.
The [issue 974 limits](issue-974-finite-crossing-bisimulation-preflight.md) still apply.
So does the [machine-check design](../../specs/formal/participant-semantics/participant-crossing-machine-check.md).
No new ADR or relation is needed.

## Exact subject and review

A fresh run checks one pinned claim.
The profile is `participant-crossing-dpbb-finite-v1@rev2`.
Both models remain at rev2, with projection rev1 and taxonomy rev8.
The relation is `divergence-preserving-branching-bisimulation`.
Resolve that catalog revision, never the latest revision by default.
Select the expected manifest, result, and claim through reviewed pins.
A candidate and its new checksum cannot choose their own expected result.

Admission checks bytes and joins.
It does not run the native checker.
The producer rebuilds both models and runs each native check.
Its publication path also checks the host.
Neither step alone establishes a separate review.

The review record must name its actual reviewer and their role.
An implementation agent can be the reviewer; a human is not required.
Keep the original producer run and the new review run distinct.
Bind the review to the new record digest and corpus subject.
A name, date, second job, or producer approval does not prove independence.
The fresh run and the review must supply that evidence.
Never invent a person, date, or acceptance.
Unsigned records still cannot satisfy a policy that requires authenticity.

## Existing owners

The formal crossing package owns the new record and its admission.
Reuse its public interfaces.
Do not copy model, mutation, witness, claim, or checker algorithms.
The existing corpus producer assumes a separate native sandbox per comparison.
The new driver may repeat its fixed invocation inventory inside one complete worker boundary.
This is needed where AppArmor denies nested namespaces.
Keep the original producer sources and claim unchanged.
Record the new driver sources and command layout separately.
ADR-117 applies to imports and module ownership.

| Boundary | Existing owner and required use |
| --- | --- |
| Expected and actual result | `machine_check.load_retained`, `admit_bundle`, and `build_bundle`. Admit the selected subject, then obtain fresh bytes. |
| Complete models | `export.build_bundle`, the independent abstract and concrete modules, and the AUT codec. Check closure, initial states, all states, edges, domains, and sidecars. Counts alone do not prove closure. |
| Claims | The existing profile models and `validate_behavioral_claim_binding`. Keep exact catalog, profile, projection, carrier, scope, and assurance joins. Retain nested claim scanning. |
| Negative evidence | `counterexample_corpus` and `counterexample_witnesses`. Repeat every reviewed case, control, calibration, and supported witness check. Never accept a candidate-selected subset. |
| Input files | `ingress.safe_path` and `read_bytes`, with bounded JSON parsing. Reject links, traversal, devices, duplicate keys, excess bytes, unknown fields, and type coercion. Counts exclude Booleans. |
| Tool selection | `tooling_policy_gate`, the lock, admission policy, selectors, profiles, and their schemas. Preserve artifact, version, platform, profile, locator, and validator-source joins. Configuration stays closed data. |
| Tool bytes | `mcrl2_tool`, verified tree admission, and the existing Debian reader. Check archive, executable, and complete-tree identities. Keep the license. Never run package scripts or accept a PATH fallback. |
| Host and Python | `bootstrap_profile`, `python_closure_profiles`, and `machine_check_publication.execution_record`. Use qualified host and closure selections. Observe allowed fields; do not copy the producer's host values. |
| Native process | `mcrl2_tool.compare` and `bounded_tool_process.run_bounded`. Keep fixed non-shell arguments, read-only inputs and tool mounts, no network, bounded output, resource limits, and child cleanup. Python and the admitted native checker may share the complete worker sandbox. No original checkout, home, credentials, or host processes enter it. |
| Errors and logs | ADR-116 shared exceptions, `operational_logging`, and `SessionReporter`. Keep safe messages and bounded failure codes. Raw diagnostics, rejected values, secrets, and host paths stay private. |
| Local storage | `publish_bundle`. Check the whole bounded inventory before atomic publication. Keep existing captures and their bytes. No self-digest, cyclic reference, partial success, or mutable success flag. |
| Hosted checks | The existing nox lane and canonical CI graph. Keep exact source revisions, pinned actions, required-job joins, read-only permissions, and disabled stored checkout credentials. Upload only admitted files to the existing approved artifact destination. |

## Clean execution

Start from pinned code in a fresh Python process and private workspace.
Import only the declared source and installed closure.
Do not reuse a producer workspace, result cache, bytecode cache, or import override.
The expected bundle is comparison input only.
It cannot supply the actual result.
Verified installed tools may be reused after full admission.

Several helpers bind roots and source digests at import time.
Passing another root does not move those imports.
Do not mix code from two checkouts or patch those roots.
Bind the producer source, reproducer source, Python locks, and tool validators.
Check source stability before and after the run.
Setup requires an exclusive trusted writer.
Verification requires read-only source and tool mounts.

Acquisition and replay are separate phases.
Offline flags prevent dependency acquisition; they are not a network boundary.
The boundary must also cover Python and its policy subprocesses.
Keep home files, proxies, keyrings, credentials, and ambient settings outside it.
Use fixed package roots and a cleared environment.
Never dump or hash ambient secret values.
No runtime authentication or secret-binding syntax is needed.

Keep each native input within 512 states and 65,536 bytes.
Keep the native resource limits and the 47-comparison producer budget.
Bound the whole worker and reap its child processes.
Missing tools, unsupported isolation, timeout, or malformed output produce no decision.
Do not disable host controls or add a privileged fallback.
A different valid result fails reproduction; it is not a successful positive result.

The hosted selection is `model-check-ubuntu-26.04-x86_64`.
Its Python closure is `public-linux-x86_64-cp314-all-extras`.
The existing observer requires actual runner image metadata.
Another host needs separate admission.
Do not fabricate that metadata or claim that tool pins also pin the kernel.
Validate the source SHA shape and its exact checkout revision.
Keep local observations distinct from qualified hosted evidence.

## Comparisons and claim limits

Recompute each published byte digest using its existing definition.
Use canonical JSON identity only where the contract requires it.
Keep file-byte and JSON subject identities distinct.
Check model, source, profile, catalog, mapping, tool, result, witness, and artifact joins.
Check state, semantic-edge, AUT-edge, and domain counts.
The current graphs have 88/107 abstract states/edges and 178/197 concrete states/edges.
Both initial ordinals are zero.

Keep the exact native mode, AUT formats, ordered inputs, and `--tau=internal`.
Only the five declared mediation classes are hidden.
Denial, unsupported results, redaction, delivery, observation, cut advance, and replay rejection remain visible.
Crossing completion still allows retries and cut advance.
It is not global LTS termination.

Keep auxiliary formulas bound to their actual branching relation.
The divergence witness retains its no-abstract-internal-edge restriction.
Neither witness is a general positive certificate.
Keep the complete reviewed mutation and calibration inventory.
Check each measured outcome and witness against its exact ordered inputs.

Require exact deterministic bundle bytes.
Do not remove a mismatch after seeing it.
Keep host image, package versions, execution reference, reviewer, and date outside those bytes.
Verify the producer's execution record separately from the new run's record.
Source changes may require a new capture and review.
Never refresh expected pins merely to hide drift.
Never rewrite historical artifacts or mapping gaps.

The new record references the original claim; it does not replace it.
Keep the original producer's nonclaims, including its reproduction nonclaim.
Retain the model-check axis and model-checked status.
No proof certificate, runtime realization, backend conformance, noninterference, or opacity follows.
No wider carrier, order, time, probability, concurrency, controller, policy cut, or backend follows.
The multi-operation profile needs its own admitted result.
Issue 976 owns later public and scientific claim changes.

## Workflow and verification

Use the existing process, closure, profile, claim, path, and storage owners.
No generic evidence framework, DTO family, schema, store, service, or workflow is needed.
Keep a small closed record with one admission boundary.
Another approved subject or host receives a separate record.
It does not change rev2 or its original result.

Use exact issue-975 file bindings and accurate code/test traceability.
Set `RAES_REQUIREMENT_UID=SEM-232`.
Research updates follow the [capture workflow](../develop/research-captures.md).
Keep retention records; do not allocate numbered releases on a feature branch.

Test missing or self-approved review, source drift, and replaced candidate-plus-pin pairs.
Test stale results, altered counts or hiding, omitted cases or limits, and host interference.
Test unsafe files, missing tools, unsupported witnesses, timeout, and partial publication.
Mocks check refusal paths; native execution supplies actual replay evidence.
Run targeted local tests.
Full, integration, and fuzz suites stay in CI.
