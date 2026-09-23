# Control applicability and evaluation migration

This is the adoption contract for [ADR-111](../decisions/adrs/adr-111-control-applicability-and-effect-decisions.md)
and [CA-01–CA-09](../../specs/formal/participant-semantics/control-applicability-and-evaluation.md).
It defines producer/reader obligations, not a working migrator or new schema.

## Explicit interpretation boundary

`participant-control-applicability/rev1` identifies the amendment. It is distinct
from `sem-235/rev1`, profile revisions, wire `participant-control-selection/v1`
and `participant-control-evaluation/v1`, and `participant-control-provider/v1`.
New invocation semantics must not be inferred from a `resolve` method or the
presence/absence of optional fields. Retain separate semantic, profile,
protocol, schema-content, implementation and storage pins.

The current selection/evaluation schemas have draft stability under ADR-061.
Their publication process may permit recorded changes in place; that does not
make old and new meanings interchangeable. Adoption must introduce an explicit
interpretation discriminator or new contract lineage, and negotiate exact
schema content and protocol support at apparatus admission. Stable breaking
contracts require a new contract ID under ADR-061. No schema, protocol or
deprecation/removal window is published by this design delivery.

| Artifact | Legacy reader | Amendment-aware reader |
| --- | --- | --- |
| Original selection/evaluation and provider/v1 | Retain original interpretation and constraints. | Select a retained legacy reader, without claiming CA-01–CA-09 satisfaction. |
| Revised coverage/invocation/effect record | Reject unsupported interpretation. | Resolve its exact semantic/protocol/schema pins, then validate closed data and independently trusted context. |
| Historical record missing an unambiguous interpretation pin | Preserve bytes; report the bounded legacy interpretation actually supported. | Use an explicit archive migration disposition backed by original content/release evidence; otherwise report unsupported/unverifiable, never guess new semantics. |
| Archive with both interpretations | Refuse unsupported reconstruction; preserve records. | Route each record through its exact reader; preserve history order, identities and evidence. |
| New live apparatus needing revised semantics | Refuse unsupported admission. | Require support across producer, provider, composition, runtime, store/history and selected downstream consumers. |

An older reader must never silently ignore new coverage or prerequisite
fields. A new reader must not globally apply the new composition reducer to
all old records. Schema validity alone does not establish compatibility.

## Conversion of apparatus and requests

An explicit conversion starts from pinned B and the published profile
obligations. Record source identity/digest, conversion identity, selected
semantic/protocol versions, author decisions and effective limitations.

1. Preserve the complete apparatus and derive obligation coverage separately.
   Do not infer obligations from the slots or results that happen to exist.
   Reconstruct inapplicability only from trusted profile/context evidence;
   absence and `None` cannot be upgraded into proof.
2. Bind each dependency to its typed predecessor output and consumer input.
   A provider/v1 adapter is admissible only for an independently verified
   dependency-free supported fragment with exactly the required input/state
   semantics. Method wrapping cannot fabricate predecessor consumption.
3. Declare mandatory input closure and support constraints. Previously
   advisory availability needed by a mandatory consumer is an explicit author
   requirement, while advice content retains no direct veto. Removing a
   required dependency or weakening a support threshold is not equivalent
   conversion.
4. Convert parent-targeted permit/deny/withhold to unscheduled decisions before
   composition. Preserve their target and authority; reject contradictions or
   an intent that requires denying an already released parent. Do not change
   historical decisions. Other effects bind their own target and exact
   execution prerequisites, including parent outcome/disposition conditions.
5. Pin shared-state scope and read versions, permitted writers, state-commit
   conditions and the combined parent/effect graph. Missing evidence, ambiguous
   sharing, cycles and absent outcome bindings stop conversion. Do not infer
   ordering from old array order or supply an invented owner receipt.

When information is insufficient, an author may make a new explicit design
and admission decision. Preserve the source and record the semantic change;
do not label it a lossless conversion. Exact support requirements cannot become
bounded merely because a provider advertises bounded support.

## Retained history, state and recovery

Persisted decisions, parent dispositions, result identities, effect keys,
allocated occurrences, receipts and budgets are immutable. In particular,
`RuntimeSnapshot.__post_init__`, evaluation-history validation,
`causal_state_from_history` and effect dispatch must select the historical
interpretation when loading/folding a legacy record. They must not derive new
executable effects or recalculate old consumption with the amended reducer.

A legacy record that marked a parent eligible despite a subsequent denial
remains evidence of that recorded legacy decision, with its limitation
disclosed. It is not a valid amended evaluation, and retaining it is not
authority for a new dispatch. Pending legacy work requiring unavailable or
unsafe interpretation is withheld for explicit owner reconciliation; no
provider re-run or manufactured revised record can repair its history.

Live interpretation/protocol replacement within an active evaluation is
unsupported. Quiesce admission, finish or explicitly reconcile pending claims
through the existing operation lifecycle, then admit a new apparatus binding
at a new cut with supported consumers. Do not assume durability authorizes
resumption, retry or a new trial. Indeterminate effects retain their state
until exact backend idempotency/readback and the authored recovery policy
authorize a conclusion. Changing binding, participant or episode cannot reset
a surviving causal root's consumed budget or turn an old key into a new effect.

Provider-state migration needs an explicit old/new scope/version mapping and
authority; an implementation rename is insufficient. Cross-scope migration
must retain isolation and atomicity or refuse. Append migration evidence;
never mutate old state/evaluation records to appear newly conforming.

## Coordinated publication and verification

Adoption uses the existing API-424 family and its owners:

- Closed selection/context/result/effect models and bounded ingress under
  `raes_contracts`; normative schemas, publication entries, fixtures, exports,
  `schema_bundle()` and packaged corpus remain identical representations.
- Typed protocol inputs under `raes_backend_protocols`, importing neutral
  contract DTOs, with no open kwargs or runtime/backend dependency.
- API-407 support negotiation and independently trusted context validation;
  one `derive_control_composition` authority for live and recorded decisions.
- RUN-320 slot/stage invocation, scoped state, ordinary crossings/effect owners,
  atomic commit, final-invocation fences and version-aware retained history.
- Conformance consumers and documentation, with explicit distinctions between
  declarations, installation, bounded contract evidence and realization.

Use publication `last_change` summaries/content hashes, removed-schema
tombstones when needed, explicit contract routing and package resources under
ADR-009/061. Do not manufacture a second publication ledger or new state store.

Required consumer evidence includes disjoint sinks under one B; zero-slot and
unknown-coverage rejection; A → B → A with exact predecessor binding; optional
malformed/support failures versus mandatory dependency loss; bounded-support
acceptance/refusal against admitted constraints; false-trigger records;
parent deny/withhold in all legacy-shaped phases; independently authorized
audit; phase-cycle rejection; shared-state conflict/failed commit; and old/new
snapshot replay preserving keys, budgets and no-new-dispatch behavior. The
bounded design witnesses in this delivery do not substitute for those real
consumer and backend checks.
