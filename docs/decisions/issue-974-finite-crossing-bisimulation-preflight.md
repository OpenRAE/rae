# Issue 974: finite participant-crossing bisimulation preflight

Requirements: SEM-232, ASR-535, SEM-230, API-423, RUN-319.
This note gives design constraints for issue 974.
It records no result.

## Exact subject

[ADR-100](adrs/adr-100-participant-crossing-bisimulation.md) remains the decision authority.
The profile is `participant-crossing-dpbb-finite-v1@rev2`.
Both models use rev2. The projection uses rev1. The catalog uses rev8.
The relation is `divergence-preserving-branching-bisimulation`.
The separate multi-operation profile receives no result from this check.

The abstract model has 88 states and 107 edges.
The concrete model has 178 states and 197 edges.
Both start at ordinal zero.
These counts are checks, not a proof of closure.
The exporter must derive every reachable state and edge from each model's own rules.
A shared transition table is forbidden.
A depth limit or sample is not the complete carrier.
Stored states, reachable states, semantic edges, and AUT edges have distinct counts.

Only the five declared mediation classes map to `internal`.
The fixed comparison mode is `dpbranching-bisim`, with `--tau=internal` and explicit AUT formats.
Denial, unsupported results, replay refusal, cut advance, delivery, and observation stay visible.
A redacted observation still has a visible event.
A completed crossing can still retry or advance its policy cut.
It is not global termination. AUT has no success predicate.

## Existing owners and interfaces

The formal package owns the check and its evidence.
`export.build_bundle` owns complete independent model construction.
`counterexample_corpus.load_retained` and `admit_bundle` own pinned corpus admission.
`counterexample_corpus.build_bundle` owns fresh native mutation and control replay.
`tools.mcrl2_tool.compare` owns native decisions.
Shared mechanics stay with their owner through a public interface.
ADR-117 forbids new private cross-module imports and cycles.

The existing bounded JSON reader and no-follow file reader own input safety.
They reject unsafe paths, links, nonregular files, duplicate keys, excess bytes, and excess depth.
The existing profile contract owns domains, sources, revisions, projection, and labels.
The existing AUT codec owns declared labels and hiding.
No parallel profile or label contract is needed.

The existing `BehavioralClaimBindingModel` owns claim shape.
`validate_behavioral_claim_binding` must resolve its exact catalog and profile joins.
Evidence admission must also bind the actual result, inputs, counts, sources, and initial states.
A positive claim uses the `model-check` axis and evidence scope, with `model-checked` status.
Its quantifier covers only all admitted inputs of the named complete finite profile.
The claim scanner must still inspect the nested claim.
No broad scanner exemption is permitted.

## Tool and host boundary

The existing lock, admission policy, selector bindings, and profiles own tool selection.
They pin mCRL2 202607.0, its archive checksum, executable, and complete installed tree.
No new downloader, cache, floating version, or PATH lookup is needed.
Tooling configuration stays plain data. It must not gain commands or hooks.

The existing adapter owns fixed non-shell arguments and private bounded output.
It uses read-only tool and input mounts, a cleared environment, and network isolation.
The sandbox receives no repository, home directory, credentials, or runtime authority.
Existing CPU, memory, file, descriptor, and wall-time limits remain mandatory.
The parent must reap children after success or failure.
No unsandboxed fallback or host security change is permitted.
The qualified host is `model-check-ubuntu-26.04-x86_64`.

Platform selection alone does not qualify the host.
Existing bootstrap probes own host-image identity and native capability checks.
Actual sandbox execution must also succeed.
Pinned tool bytes do not pin the kernel or host libraries.
Execution provenance must retain the exact observed runner image and native package versions.
It must use the existing Python closure profile and exact source SHA.
Only allowlisted fields may be collected. An environment dump is forbidden.

The current adapter permits at most 512 states and 65,536 AUT bytes per input.
An excess fails the check. It must never trim inputs.
The whole run needs a time limit and a fixed comparison inventory.
Per-child limits alone do not bound the complete job.
The existing opacity proof also uses the shared tooling gate.
Its source binding must cover the same validation chain and schemas.
Its theorem, profile, kernel result, and historical reproduction record keep their existing meanings.

## Result and trust boundary

A successful process must emit exactly `true` or `false` under the adapter's protocol.
Exit success alone is not a result.
Timeout, missing tools, malformed output, and resource failure produce no decision.
Use shared ADR-116 errors and the existing application logging boundary.
Messages must use fixed safe text. Raw diagnostics stay private.
A diagnostic shape check cannot make arbitrary message text safe.

Local evidence admission must close every field and join.
It must require actual Boolean decisions and integer counts that exclude Booleans.
Coercion, truthiness, unknown fields, and missing defaults must not create success.
A positive result requires all model, provenance, mutation, count, and drift gates.
Fresh replay must cover every reviewed mutation, unchanged-input control, and relation calibration.
Pinned corpus admission alone does not run the tool.
Candidate case lists cannot omit a required test.
The mutation review remains bound to its exact subject digest.

The adapter emits no positive proof certificate.
A proposed abstraction map is not a checked relation witness.
A negative result needs a safe witness checked against the actual ordered inputs.
Auxiliary branching formulas retain their actual relation.
The existing divergence check applies only when the abstract graph has no internal edges.
Unsupported witnesses leave evidence incomplete. They cannot support a positive claim.

Existing reviewed pins select inputs independently of candidate metadata.
Canonical JSON identity and exact file-byte checksums keep their distinct meanings.
The evidence has no signature. A policy requiring authenticity must refuse it.
Checksums cannot establish semantic correctness, review, or authenticity.
Historical construction and mapping bytes must remain unchanged.
Current source identities must be separate from historical source identities.
Mapping gaps and incompatibilities remain explicit; no current runtime claim follows.
A new source or tool pin needs a fresh capture and review, not rewritten history.

The digest graph must remain acyclic.
It binds consumed model bytes, sidecars, complete domains, counts, sources, tool, mapping, mutations, and results.
It must include all output-affecting producer, validator, adapter, claim, and witness code and locked dependencies.
A manifest cannot contain its own digest.
CI metadata stays outside reproducible semantic bytes.
Sources and the sealed tool tree need a trusted exclusive writer throughout execution.
The producer must check source stability before and after native work.

## Workflow and scope

Use exact issue-scope file assignments and the existing requirement predicates.
Set `RAES_REQUIREMENT_UID=SEM-232` on this issue branch.
Extend only the required ownership entries. Issue 973's allowlist does not authorize new files.
Keep requirement and test traceability accurate.

Extend the existing canonical CI model-check job and its required-job join.
Use a named nox session with `SessionReporter` and a helper under `tools/nox_support`.
Setup and acquisition stay separate from offline verification.
`uv run --frozen` alone does not prohibit downloads.
Verification must use installed inputs without sync or download fallback.

Keep exact-SHA checkout, read-only permissions, disabled stored credentials, and pinned actions.
Only a complete admitted inventory may reach the existing CI artifact destination.
Bound file counts, bytes, retention, and job time.
A failed, cancelled, or skipped check must publish no partial result.
Do not upload caches, the checkout, tool trees, or raw diagnostics.

Tests must cover false acceptance, incomplete closure, shared authority, wrong initial states, and changed hiding.
They must also cover drift, replaced metadata, wrong types, proof promotion, unsupported witnesses, and partial publication.
Mocks cannot produce native evidence.
Local tests stay targeted. Full, integration, and fuzz suites belong in CI.
Research changes use the existing content-addressed capture workflow without new numbered branch releases.

## Nonclaims

API-423, API-406, API-409, and inject carriers stay authoritative.
This offline check changes no runtime route, policy evaluator, transport, or store.
Runtime authentication, capability checks, context validation, and atomic history commits remain in their existing owners.
No runtime realization, backend conformance, noninterference, opacity, whole-runtime equivalence, or unbounded proof follows.
No result extends to another carrier, order, time, probability, controller, policy cut, or backend.
Issue 975 owns independent reproduction. Issue 976 owns subsequent public claims.
Public assurance and scientific-completion surfaces stay unchanged here.
