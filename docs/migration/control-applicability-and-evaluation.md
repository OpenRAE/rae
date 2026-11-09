<a id="control-applicability-and-evaluation-migration"></a>

# Control applicability and evaluation

## Versions and purpose

Source: original selection/evaluation and provider/v1 contracts.
Target: v2 contracts negotiated separately under `participant-control-applicability/rev1`.
This reference applies to Python RAES 11.0.2.
Each contract keeps its own identity and obligations.
This page supplies no converter. It installs nothing.

[ADR-111](../decisions/adrs/adr-111-control-applicability-and-effect-decisions.md)
and [CA-01–CA-09](../../specs/formal/participant-semantics/control-applicability-and-evaluation.md) own the adoption rules.
This page gives producer/reader obligations. It supplies no working migrator.
Issue #1365 publishes the v2 form described below.
The [contract reference](../explain/reference/modular-participant-control-contracts.md#reference-runtime-v2-evaluation)
describes reference-runtime evaluation/history adoption.

<a id="explicit-interpretation-boundary"></a>

## Version boundaries

`participant-control-applicability/rev1` names the amendment.
It is distinct from `sem-235/rev1` and profile revisions.
It is also distinct from the following wire and protocol versions:

- `participant-control-selection/v1`.
- `participant-control-evaluation/v1`.
- `participant-control-provider/v1`.

Issue #1365 publishes separate v2 contracts for selection, evaluation, and the provider.
Their IDs are `participant-control-selection/v2`, `participant-control-evaluation/v2`, and `participant-control-provider/v2`.
Negotiate each separately for this amendment.
A `resolve` method does not establish new invocation semantics.
Neither does the presence or absence of optional fields.
Keep separate semantic, profile, protocol, schema-content, implementation, and storage pins.

Selection/evaluation schemas currently have draft stability under ADR-061.
Their process may permit recorded changes in place.
That permission does not make old and new meanings interchangeable.
Adoption must introduce an explicit interpretation discriminator or new contract lineage.
At apparatus admission, negotiate exact schema content and protocol support.
Stable breaking contracts need a new contract ID under ADR-061.
The #1352 design delivery published no schema or protocol.
Issue #1365 uses new contract IDs.
It opens no deprecation or removal window for v1.

<a id="published-v2-representation-and-negotiation-1365"></a>

## Published v2 contracts (#1365)

The v2 selection retains the complete admitted apparatus.
It pins profile obligations and binding configuration.
It also pins authority, provenance, and slot support.
Each evaluation embeds that selection.
It records total obligation coverage and the applicable slots at its exact context cut.

Use the profile to resolve coverage independently.
An absent record cannot prove inapplicability.
Neither can an empty applicable discharge.
A provider-returned `None` cannot prove it either.

Required-input closure is explicit.
A required advisory input must be available.
This holds even when its opinion cannot decide the parent.

Each v2 invocation binds the requested slots.
It also binds content-bound predecessor results.
It binds an authorized projection.

State inputs must be committed or declared tentative.
The invocation binds those inputs too.

Result digests bind the complete invocation.
Reduce invalid optional output to a lost-advice record at that invocation boundary.
The record must be value-independent.
The accepted parent outcome is an unscheduled permit, deny, or withhold.

Each effect has its own closed target.
It has separate origin, phase, and outcome prerequisites.
Only an independently authorized consequence may follow denial or withholding.
Decision-local runnable effects remain provisional.

`admitted_control_effect_ids_v2` joins them with mandatory composition before commit admits intent or dispatch.
If required composition fails, parent release receipts cannot survive.
Release-conditioned state cannot survive either.

The expected-head commit envelope binds coverage, results, and decision.
It also binds state proposals, effect intents, and consumption.
It specifies the incumbent store transaction. It does not prove commit or dispatch.

An explicit required deny or withhold is a complete parent outcome.
It is not a failed mandatory slot.

Independent consequences may follow that exact outcome.
They may do so only when no unrelated mandatory blocker remains.
Reject duplicate effect IDs across provider results before planning effects.
Result order cannot suppress a request.

The published set includes selection/evaluation schemas and `ParticipantControlProviderV2`.
It includes corpus examples, publication entries, and the conformance registry too.
The v2 conformance entry reports `structural-context-required`.
The operator must supply its resolver.
That resolver must resolve admitted coverage and installation.
It must resolve effective API-407 support and exact results.
It must resolve incumbent crossing and IFC fact owners.
It must also resolve safe references and effect authority.

A discharge slot must select the obligation's profile.
Lifecycle effects need an explicit order.
They must follow live-target operations that overlap them.
A realized effect must match a retained full-payload claim.
It also needs an operator-resolved earlier committed evaluation.
That evaluation must authorize the exact phase, parent outcome, and effect predecessors.
The realized effect must match its exact applied owner outcome.

The resolver must supply the authorized proposal for each state write, including commit timing.
A provider's `commit_on` record cannot authorize itself.
An exact/bounded compatibility claim needs constraint evidence.
That evidence must be independently resolved.
The wire relation alone is not proof.

A backend's v1 `participant_modular_control` declaration still requires the original v1 contracts.
The v2 IDs support exact contract declarations.
Neither a declaration nor a method proves installed v2 capability.

Before emitting v2 records, negotiate their IDs and content hashes.
Also negotiate their semantic meaning and provider/v2 support first.
Route each record by its recorded contract ID. There is no global reducer switch.

Issue #1365 left `RuntimeSnapshot` unchanged.
It left scheduling, store/history folds, and dispatch unchanged too.

The #1069 consumer explicitly admits v2 binding/content pins.
It also explicitly admits supervised dependency evaluation.
It admits scope-bound state through the existing atomic evaluation-history carrier.
Readers select the recorded discriminator. SQLite reader version 8 excludes v1-only readers.

Providers return prepared transaction content.

The runtime seals each new v2 evaluation, as specified in #1369.
It does so inside the existing atomic transaction.
The seal includes the actual operation receipt.
It also includes the committed dispatchable IDs.
A failed commit publishes neither.

Historical prepared evaluations stay unchanged and cannot dispatch.
Legacy claims and budgets remain intact. Never interpret v2 intents through v1.


The optional v2 `continuation` pins an immutable source evaluation.
It also pins the source commit receipt and exact realized claims.
A dependency cannot advance without separate trusted-context admission.
A parent receipt cannot be promoted without that admission either.
Fresh evaluation validation rejects a continuation when its source is missing.
Historical records omit an absent continuation field and retain their canonical bytes.
Negotiate the updated v2 schema content pin before consuming these records.

The v2 drain admits only installed, exactly bound effect owners.
Supported paths include compiled handoff and fresh world inject execution.
They also include execution-attempt cancellation with independently observed outcomes.
Other required combinations refuse at admission.
An optional contribution that is unsupported stays isolated advice.
These synthetic reference-runtime witnesses establish no production provider or distributed atomicity.

### Original v1 records

Legacy readers keep the original selection/evaluation and provider/v1 meaning and constraints.
Readers that implement the amendment must select the retained legacy reader for those records.
They cannot claim CA-01–CA-09 satisfaction from that legacy path.

### Revised records

Legacy readers reject unsupported meanings in revised coverage, invocation, or effect records.
Readers that implement the amendment resolve exact semantic, protocol, and schema pins.
They validate closed data against independently trusted context.

### Historical records without clear pins

Both reader types must preserve the bytes.
A legacy reader reports only its supported bounded legacy meaning.
A reader that implements the amendment needs an explicit archive migration disposition.
Original content and release evidence must support that disposition.
Otherwise it reports unsupported/unverifiable. It must never infer new semantics.

### Mixed archives and new apparatus

Legacy readers refuse unsupported archive reconstruction and keep the records.
Readers that implement the amendment route each record through its exact reader.
They keep history order, identities, and evidence.

Legacy readers refuse new live apparatus needing revised semantics.
Readers that implement the amendment require support across producer, provider, composition, runtime, and store/history.
That requirement also covers selected downstream consumers.

Older readers must not silently ignore new coverage or prerequisite fields.
New readers must not apply the new composition reducer to all old records.
Schema validity alone does not establish compatibility.

<a id="conversion-of-apparatus-and-requests"></a>

## Conversion rules

Explicit conversion starts from pinned apparatus B and published profile obligations.
Record the source identity/digest and conversion identity.
Record selected semantic/protocol versions, author decisions, and effective limitations too.

1. Preserve the complete apparatus.
   Derive obligation coverage separately.
   Existing slots or results cannot define the obligations.
   Only trusted profile/context evidence can establish inapplicability.
   Absence and `None` are not proof.
2. Bind each dependency to its typed predecessor output and consumer input.
   A provider/v1 adapter needs an independently verified, dependency-free supported fragment.
   Its input/state semantics must match exactly.
   Wrapping a method cannot prove predecessor consumption.
3. Declare mandatory input closure and support constraints.
   Advice needed by a mandatory consumer becomes an explicit author requirement for availability.
   Its content still has no direct veto.
   Removing a required dependency is not equivalent conversion.
   Neither is weakening a support threshold.
4. Convert parent-targeted permit/deny/withhold to unscheduled decisions before composition.
   Keep the target and authority.
   Reject contradictions and intents that require denying an already released parent.
   Do not change historical decisions.
   Other effects bind their own targets and exact execution prerequisites.
   These include parent outcome/disposition conditions.
5. Pin shared-state scope, read versions, and permitted writers.
   Pin state-commit conditions and the combined parent/effect graph too.
   Missing evidence, ambiguous sharing, cycles, or absent outcome bindings stop conversion.
   Do not infer order from old array order.
   Do not invent an owner receipt.

When information is insufficient, an author may explicitly choose a new design and admission decision.
Keep the source and record the semantic change.
Do not call it lossless conversion.
A provider may declare bounded support.
That cannot turn an exact support requirement into a bounded one.

## Retained history, state and recovery

Persisted decisions and parent dispositions are immutable.
Result identities and effect keys are immutable too.
So are allocated occurrences, receipts, and budgets.
For legacy records, the following consumers must select historical meaning.
This holds when loading or folding those records:

- `RuntimeSnapshot.__post_init__`.
- Evaluation-history validation.
- `causal_state_from_history`.
- Effect dispatch.

They must not derive new executable effects from old records.
They must not recalculate old consumption with the amended reducer.

A legacy record may mark a parent eligible despite later denial.
Keep it as evidence of that legacy decision and disclose the limitation.
It is not a valid amended evaluation.
Retaining it grants no authority for new dispatch.
Withhold pending legacy work if its meaning is unavailable or unsafe.
The owner must reconcile it explicitly.
Rerunning a provider or manufacturing a revised record cannot repair that history.

The meaning or protocol cannot be replaced inside a live evaluation.
Stop new admission first.
Finish or explicitly reconcile pending claims through the existing operation lifecycle.
Then admit a new apparatus binding at a new cut with supported consumers.
Durability does not authorize resumption, retry, or a new trial.
Indeterminate effects keep their state.
Exact backend idempotency/readback and authored recovery policy must authorize their resolution.
Changing binding, participant, or episode cannot reset a surviving causal root's consumed budget.
It cannot turn an old key into a new effect.

Provider-state migration needs explicit old/new scope/version mapping.
It also needs authority.
Renaming an implementation is insufficient.
Cross-scope migration must keep isolation and atomicity.
Otherwise, it must refuse.
Append migration evidence.
Never mutate old state/evaluation records to claim new conformance.

<a id="coordinated-publication-and-verification"></a>

## Publication and checks

Adoption uses the existing API-424 family and its owners.
`raes_contracts` owns closed selection/context/result/effect models and bounded ingress.
Normative schemas and publication entries must remain identical representations.
Fixtures and exports must do so too.
So must `schema_bundle()` and the packaged corpus.

`raes_backend_protocols` owns typed protocol inputs.
It imports neutral contract DTOs.
There are no open kwargs or runtime/backend dependencies.
API-407 owns support negotiation.
Context validation requires independently trusted inputs.
`derive_control_composition` remains the sole authority for live and recorded decisions.

RUN-320 owns slot/stage invocation.
It owns scoped state and ordinary crossings/effect owners too.
It owns atomic commit and final-invocation fences.
It owns version-aware retained history too.
Conformance readers must distinguish what is declared from what is installed.
Documentation must make the same distinction.
They must distinguish bounded contract evidence from realization too.

Publication records give contract identity, schema path, and stability.
They hold no content hash or change summary.
Use exact schemas from a pinned release or Git revision for required runtime content pins.
Apply the owning protocol's digest rule to those artifacts.
Git records schema changes.
Use removed-schema tombstones when needed.
Keep explicit contract routing and package resources under ADR-009/061.
Do not create a second publication ledger or state store.

Required consumer evidence covers these cases:

- Disjoint sinks under one apparatus B.
- Zero-slot and unknown-coverage rejection.
- A → B → A with exact predecessor binding.
- Optional malformed/support failures versus mandatory dependency loss.
- Bounded-support acceptance and refusal against admitted constraints.
- False-trigger records.
- Parent deny/withhold in all legacy-shaped phases.
- Independently authorized audit.
- Phase-cycle rejection.
- Shared-state conflict and failed commit.
- Old/new snapshot replay that preserves keys, budgets, and no-new-dispatch behavior.

The bounded design witnesses do not replace real consumer and backend checks.

## Continue

Use [revised-control migration](revised-control.md) for the task.
Read [modular control contracts](../explain/reference/modular-participant-control-contracts.md) for installed runtime behavior.
