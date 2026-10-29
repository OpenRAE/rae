# Issue #1373 preflight

Date: 2026-10-27. Inspected base: `f7e5f49a9b3071b2cdd3c22521fda552fb633b91`.
The issue and its acceptance criteria define the work.
No formal requirement is assigned.
The #1369 commit, continuation, and effect-owner code is present.
The diagnosis is in local Git at `077f7d04:docs/research/runtime-refactor/diagnosis.md`, section 7.

Retain [ADR-104](adrs/adr-104-runtime-control-plane-architecture.md),
[ADR-108](adrs/adr-108-modular-participant-control-and-governed-effects.md),
[ADR-110](adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md),
[ADR-111](adrs/adr-111-control-applicability-and-effect-decisions.md),
[ADR-113](adrs/adr-113-reusable-execution-machinery.md), and the
[#1369 preflight](issue-1369-governed-effect-dispatch-preflight.md).
No new semantic primitive or ADR is needed.

## Keep the source and its owners

Saved history and operation records remain the source of truth.
Private indexes may speed up reads.
They must be safe to discard and rebuild from the store.
Do not put them in public DTOs, snapshot metadata, provider state, or information-state profiles.
Do not add a cache service or a second state machine.

Use the existing owner to apply a new batch to a checked prefix.
Keep proposed updates separate until the store confirms the commit.
Copy mutable maps and sets before a trial update.
Callbacks must receive detached values.
A frozen wrapper or object identity alone cannot prove that a nested value is safe.

| State | Existing owner and rules |
| --- | --- |
| Control episodes | `participant_control_occurrence_v2_validation.py` owns `_EpisodeFold.apply()`. Keep policy pins, script position, live handles, lifecycle, proposal and decision IDs, time windows, and completion evidence. Refusal adds a history event but does not advance accepted state. A new episode does not reset root budgets. |
| Crossings | `participant_crossing_validation.py` owns stage joins and transform graph checks. Keep exact subjects, policies, predecessors, owner joins, markings, order, and evidence. Reuse the existing event/head format. |
| Causal state | `participant_control_causal_state.py` owns claims, firing epochs, attempts, and declared-use watermarks. Legacy roots stay local until v2 sharing applies. A shared root includes prior v1 use across participants. Refused records can spend attempts. A realization does not spend its original attempt again. Preserve the union-of-claims rule; a maximum count alone is insufficient. |
| Provider state | `participant_control_provider_state.py` owns the full scope key and serial chain check. Keep run, sharing mode, participant, and episode coordinates. Repeated equal edges are legal. Reject forks, converging edges, cycles, conflicting writers, and disconnected chains. Preserve the two commit conditions. |
| Effects | The existing effect, continuation, evidence, receipt, and parent-outcome modules own execution. Index exact intent, logical key, actor, kind, origin, target/run, dependencies, and outcome joins. An index selects work; it grants no permission. |

Keep version choice with the original record parsers.
Give each index an explicit internal reducer version.
Do not confuse this version with a schema, policy, provider-state, or snapshot version.
Shared histories have no global timestamp order.
Respect each stream's order and the declared state/dependency links.

## Publish confirmed state

Bind an index to its store owner, target/run, checked prefixes, policy/context pins, and operation state.
Length or last-event identity cannot prove that an arbitrary prefix is unchanged.
Rebuild after reopen, restore, migration, owner change, or reducer change.
Reset on unknown source changes.
Corrupt source history must fail closed.
An unrelated append must not force a full rebuild on each call.

The existing mutation authority, commit adapter, and atomic store transaction own publication.
Seal new prepared records under the actual commit receipt.
Publish indexes under the existing writer/cache locks after store success.
A refused CAS, rolled-back batch, or losing claim publishes no proposed state.
An exact retry applies no delta twice.
After a lost acknowledgement, read the store before using an index.
Post-commit index failure must reset caches and preserve poisoned readiness.

Operation-only writes can change claims and outcomes without changing snapshot revision.
Give those changes their own sequence or another proven invalidation rule.
Prepared and rejected v2 records retain their original meaning, including declared use and state proposals.
They never gain execution permission from a reader.
If a private checkpoint is added, bind it to a proven prefix and write it in the same transaction.
A missing checkpoint must rebuild from history.
Keep the existing codecs, integrity checks, scope checks, and maintenance rules.

Applied or failed outcomes require the existing owner receipt join.
Keep uncertainty, reservations, and recovery barriers for indeterminate claims.
Reconsider withheld and unsupported work when the existing rules permit it.
Keep blocked graphs reachable for later evidence and continuation admission.
Generic owner success does not prove world application, delivery, observation, or prevented execution.
Preserve cancellation priority and its capacity while ordinary owners stall.
Repeated execution calls return prior completed outcomes as well as new ones.
Keep deterministic dependency order.

## Preserve the surrounding checks

- Keep closed configuration, installed capability checks, and compiled policy ownership.
  Fresh applicability, willingness, target, lifecycle, and original-cut checks remain required.
- Keep strict parsers, bounded input, duplicate-key and nonfinite-number rejection, and exact reference/count types.
  Do not add `trusted=True`, `model_construct()`, duplicate schemas, or a broad validation bypass.
  Public, backend, and restored input still requires full validation.
- Authorize before lookup or readback.
  Keep actor, audience, episode, controller, target, and run scopes.
  Never lend the execution caller's authority to an effect.
- Keep bounded callbacks, one writer, revision checks, and one-use dispatch.
  Do not run callbacks under an index mutex or store transaction.
  Do not rebase stale prepared results onto a new cut.
- Preserve exact history prefixes, global IDs, typed receipts, and backend-result checks.
  Memory, SQLite, and admitted PostgreSQL stores must agree.
  A public-field change requires every codec, schema, API, and manifest consumer under ADR-061.
- Keep secret references and value-free commitments only.
  Do not index resolved credentials, tokens, secret outputs, or ephemeral retry proof.
  Rebuild must resolve no secrets and rebind no environment values.
- Keep lease-before-inspection, private files, safe descriptors, link checks, backup/restore checks, and the existing worker constraints.
  Use the existing store paths and bound SQL values.
  Add no process, socket, telemetry destination, or external service.
- Reuse stable, value-free errors and actor-bound atomic audit.
  Keep non-revealing unauthorized lookups and poisoned readiness.
  Counts must not expose record contents or unbounded identifier labels.

## Test the real saving and execution calls

Compare indexes and decisions with complete folds of the same source cut.
Cover accepted and refused records, exact duplicates, changed content, mixed versions, and episode changes.
Include shared roots, watermarks, repeated provider edges, invalid chains, dependencies, parent outcomes, and cancellation.
Test before and after claims, rollback, lost acknowledgement, and owner application before outcome commit.
Include linked recovery children, stale callbacks, operation-only changes, and post-commit index failure.
Check for lost work, repeated owner calls, early release, and double budget spending.
Keep complete folds available as reference checks.

Reuse the existing crossing, mixed-control, provider, governed-effect, and store-failure fixtures.
Use the #1069 durability/provider, #1363 occurrence, #1369 recovery, #1092 failure, and #1187 security tests where relevant.
Run targeted tests locally.
CI owns full, integration, fuzz, process-loss, policy, and completion suites.

Measure real append and effect-execution calls as unrelated history grows.
Hold the new batch, touched graph, pending work, and output size fixed.
Also disclose the active sizes that still affect cost.
Count visited, parsed, and copied records and store reads.
Report timings without brittle time thresholds.
Disclose backend, profile, memory growth, warm-up, initial replay, and workload limits.
Retained IDs, claims, watermarks, old handles, and outcomes still consume memory.
Do not evict required state to claim fixed space.

Include snapshot construction, validation, callback copies, commit sealing, record retrieval, claim guards, and SQL writes.
Moving a full scan into reload does not fix it.
Full export and initial replay still read full history.
Returning retained results costs work in proportion to output size.
Do not claim constant time for arbitrary active state or external callbacks.

## Keep the change bounded

Add no queue, execution engine, generic event framework, public cache schema, or cross-store shared state.
Do not change policy, rewrite history, add automatic retries, or claim exactly-once external effects.
Keep dependency directions and the 500-line source cap.
Use repo policy tools before and after the work.
Follow `AGENTS.md`, `.ground-control.yaml`, `.gc/plan-rules.md`, and the pre-publish hooks.
Do not invent a requirement UID for this issue.
