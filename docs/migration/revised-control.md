# Migrate revised control producers and readers

## Versions and purpose

Source: `Legacy control declarations, v1 carriers, and their pinned readers`.
Target: `Explicit rev1 policy forms and separately negotiated v2 carrier/provider contracts`.

## Before you start

Use RAES 11.0.2 with the original source, apparatus selections, histories, stores, and content pins.
The author decides semantic changes. The runtime operator admits new bindings.
Backend owners supply native effects, evidence, and cleanup.
A file conversion is local.
Installing new live apparatus changes runtime admission.
Stop new affected admission.
Reconcile pending work before replacing its live meaning.

Use this checklist with the [current support reference](../explain/reference/revised-control-semantics.md).
The controls have no global v2 switch.
No single converter rewrites every archive.
Each selected path must support its own semantics and contracts.
It must support its profiles and installed owners too.

## Select the authoring meaning

1. Keep the original SDL and its content digest.
2. Select legacy control, a finite script, or a reusable policy.
3. Use the [conversion helper](mixed-control-finite-script-conversion.md) for a finite script.
4. Resolve every reported ambiguity.
5. Publish the converted artifact only after that review.
6. For reusable control, record the author's explicit decision to permit repeated applications.
7. Give each new application a fresh occurrence ID.
8. Supply its revisions, order, and evidence.

The rev1 declaration requires `semantics: mixed-control-policy-occurrence/rev1` and an explicit `form`.
Removing fixed coordinates alone is not a valid conversion.
A reusable edge authorizes no automatic execution.
An exact retry returns the saved receipt.
It does not request another cycle.
The [adoption contract](reusable-mixed-control.md) governs source-preserving conversion.
It also governs historical meaning.

## Coordinate contracts and interfaces

1. Use the [producer and reader map](../explain/reference/revised-control-adoption-map.md) for your selected path.
2. Before admission, negotiate the exact contract content.
3. Check its installed interfaces before admission.
4. Keep each historical reader and the original bytes for its records.

A matching version string or method name alone does not establish support.
Missing required support refuses admission.

## Select profiles and recovery choices

1. Pin semantics, profile, and protocol separately.
2. Pin schema content, implementation, and store reader separately.
3. Check each required obligation against the selected implementation's effective support.
4. Keep required dependency inputs even when their content is advisory.
5. Keep optional unavailability separate from missing required coverage.
6. Install each selected effect owner before admitting required effects.
7. Check the complete arrangement against the support table.

P0, P1, and P2 keep their existing process guarantees.
They keep their existing durability and transport guarantees too.
These contracts add no P3 guarantee.
They add no multi-owner or exactly-once-effects guarantee.
The inject guide records the applicable local and PostgreSQL ledger versions.
The applicability guide records v2 evaluation reader admission.
These internal versions do not replace wire or semantic pins.

Authored `execution_policy` keeps complete scoped choices during compilation.
Planning preserves those choices too.
Omitting it does not permit new repetition.
Read [execution and recovery](../explain/reference/execution-recovery-migration.md) for bounded retry choices.
It also identifies unsupported continuation choices.
Transport retries, durable queues, and backend idempotency cannot authorize another scenario effect.

## Preserve active work and history

1. Stop new admission before replacing a live policy or apparatus interpretation.
2. Finish or reconcile pending work through its existing owner and authorization path.
3. Preserve uncertain effects, claims, budgets, and the original admitted plan.
4. Admit a new episode or apparatus only through its existing lifecycle.
5. Read each archived record with its original discriminator and pinned context.
6. Report unsupported or unverifiable reconstruction when required historical context is missing.

Restart does not grant redispatch. A new ID does not reset a surviving causal budget.
Migration evidence appends facts.
It does not rewrite past outcomes or fabricate cessation.
The [executable examples](../examples/revised-control.md) check repeated control, world effects, and refusals.
They also check supported mixed arrangements.
They verify RAES behavior through test providers. Downstream native qualification remains separate.

## Check the result and recover

Success is an admitted arrangement.
It retains exact pins and historical readers.
On refusal, keep the source.
Keep the unsupported route closed until its required consumer, owner, or pin is available.
Do not erase uncertainty or reset consumed budgets.
Do not repeat effects to finish adoption.
The original backend owner must establish cessation.
That owner must also establish cleanup before resource reuse.
Read [current support](../explain/reference/revised-control-semantics.md)
and [participant-control explanation](../public/participant-control-explanation.md).
