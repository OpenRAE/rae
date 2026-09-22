# External inject compatibility and adoption

[ADR-111](../../decisions/adrs/adr-111-external-inject-triggering-and-execution.md)
and [EI-01–EI-06](../../../specs/sdl/external-injects.md) publish
external-inject-occurrence/rev1. This identifier names a semantic decision;
it is not an installed schema, transport method or backend capability.

## Reader and producer rules

| Artifact | Existing reader | Reader implementing EI-01–EI-06 |
| --- | --- | --- |
| Existing inject/event/script/story authoring | Existing parsing, compilation and scheduling meaning | Same authoring; live triggering additionally needs an admitted versioned realization/invocation binding. |
| Legacy bound/queued snapshot or plan-start receipt | Original status only | Original status only; never infer an applied effect, delivery or observation. |
| Legacy DSL-142 fixed narrative anchor | Original mandatory fields and fixed-coordinate checks | Retain legacy reader and policy pins; do not fabricate omitted schedule fields. |
| New external occurrence, outcome or unscheduled delivery join | Refuse unsupported interpretation | Explicit closed discriminator, exact contextual joins and capability admission. |
| Mixed historical archive | Refuse unsupported segments for reconstruction; preserve bytes | Select each record's original reader, source/plan/policy pins and evidence. |

Omission of a participant binding continues to mean ordinary orchestration.
Absence of participants never selects a different or weaker world-effect
contract. Entity endpoints retain paired-or-absent authoring and do not become
runtime actor or physical target selectors. Current environment string lists
acquire no executable command, environment-variable or payload syntax.

Do not reinterpret old receipts, change their occurrence IDs, manufacture
backend evidence, relax old schemas, or infer the new form from missing fields.
A conversion may preserve source declarations and produce explicitly selected
new invocation bindings with recorded source provenance. New repeatability,
fan-out, runtime parameters or semantic order requires an author/admission
decision; it is not a lossless change to historical intent.

No live interpretation upgrade is supported while occurrences are queued,
running or indeterminate. Preserve claims and pins during recovery. Admit a
new run only through the existing lifecycle and independent authority; a run
reset is not proof that an old external effect ceased. Mixed archives retain
separate target/run scopes and never concatenate their order counters as one
continuous execution.

## Coordinated adoption boundary

The smallest executable adoption is a coherent slice through:

1. Closed versioned invocation/outcome carriers and strict bounded serialized
   ingress, plus direct-core and persistence contextual validation.
2. Trusted compiler/plan resolution of existing inject/narrative identities,
   concrete target sets and source/input/evidence contracts.
3. Target capability manifest, installed invokable protocol and contextual
   admission agreement. Missing backend execution support is an honest refusal.
4. ADR-104 authoritative operation/occurrence/slot/retry claims, running intent,
   supervised dispatch, immutable outcomes, atomic terminal state/audit and
   profile-specific recovery.
5. Backend result validation, per-binding evidence and residual/unknown effects.
6. Optional DSL-142/ADR-110/API-423/API-424 consumers, exact occurrence/result
   joins, independent control/disclosure authority and final-sink evidence.

Reuse existing owner modules named in the
[preflight](issue-1353-external-inject-triggering-preflight.md).
No second trigger database, scheduler, policy interpreter or permissive metadata
channel is authorized. Schema adoption must follow ADR-009/061, the publication
manifest and per-contract entries, change hashes, generated-bundle parity and
all embedded occurrence/snapshot consumers. This delivery changes none of them
and begins no deprecation/removal window.

Adoption evidence must exercise actual HTTP/embedder/store/backend consumers:
unauthorized trigger and receipt reads, malformed/oversized/secret-bearing input,
stale/ambiguous/multiple targets, unmet/unknown assertions, concurrent scheduled
and external claims, changed-key occurrence reuse, failed atomic writes, crashes
after effect before commit, invalid/partial/late outcomes, capability refusal
and required-delivery failure. Include no-participant execution on a real
selected backend, legacy fixture compatibility, and actual final-sink joins.
A bounded design model or successful status retrieval cannot replace these
tests or establish world effects.
