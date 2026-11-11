<a id="reusable-mixed-control-compatibility-and-migration"></a>

# Reusable mixed-control compatibility reference

This reference applies to Python RAES 11.0.2.
The source is fixed-coordinate declarations and `participant-control-occurrence-v1`.
The target is `mixed-control-policy-occurrence/rev1` with `participant-control-occurrence-v2`.
Each contract keeps its own identity and obligations.

[ADR-110](../decisions/adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md)
and [MC-01–MC-09](../../specs/formal/participant-semantics/reusable-mixed-control.md) own the adoption rules.
The [finite-script converter](mixed-control-finite-script-conversion.md) supplies the supported source conversion.
The compiler accepts explicit reusable-policy and finite-script forms.
API-409 v2 carries their occurrences.

After #1364, the compiler and API-409 v2 reader are available.
An explicitly configured RUN-310 control owner can execute reusable applications.
It can retain evidenced cancellation outcomes.
See [reusable participant control](../explain/reference/reusable-participant-control.md) for installation and original-policy recovery.
That reference gives the supported-path boundary too.
Ordinary planning and unsupported delivery/consumer paths still refuse unsupported work.
This does not establish coordinated adoption by every backend or consumer.

## Producer and reader boundary

`mixed-control-policy-occurrence/rev1` names the new semantic decision.
Existing `MixedControlTransition` declarations keep their fixed-coordinate meaning.
So do `participant-control-occurrence-v1` records with wire `1.0.0`.
A suffix does not promise stability.
The current publication is draft under ADR-061.
Historical meaning remains protected regardless.

Adoption needs explicit, closed interpretation discriminants.
They must cover authoring/compiled and occurrence/snapshot carriers.
A new occurrence lineage must carry the changed meaning.
Optional fields and defaults cannot reinterpret historical v1 data.
Record policy revision, semantic pin, and wire discriminator separately.
Keep schema hash and store version separate too.

### Legacy policy and v1 occurrence

Existing readers keep their original semantics and checks.
Readers that implement the amendment use the retained legacy meaning and pinned compiled policy.

### New policy forms

Existing readers reject unsupported forms or versions.
Readers that implement the amendment validate explicit reusable-policy or finite-script under its new semantic pin.
They instantiate fresh coordinates for each occurrence.
Those coordinates must be exact.

### New occurrence shapes

Existing readers reject unsupported lineage for revised accepted/rejected occurrences.
Readers that implement the amendment resolve the pinned policy before use.
They check kind, target, cut, and truthful disposition too.

### Mixed archives

Existing readers refuse reconstruction of unsupported episodes.
They must not reinterpret them.
Readers that implement the amendment select each episode's exact reader and policy.
They keep archive order and evidence.

### New live episodes

An unsupported compiler, runtime, or downstream consumer prevents admission.
Every selected path must support the required semantics and ranges.
This holds for both reader types.

Accepting a shape does not establish semantic compatibility.
It does not establish operational interoperability.
Unknown meaning cannot fall back to the latest reader or a generic dictionary.
A matching version string or ordinary environment inject is not a fallback.

## Authoring conversion

Keeping legacy authoring is valid. It remains finite.
Source-preserving conversion to **finite-script** must keep every accepted legacy trace constraint.
These constraints include initial state and from/to states.
They include kind, controller, authority, targets, and proposal links.
They also include exact revisions, order, windows, evidence, and finite extent.

A unique total order alone does not prove one executable sequence.
Legacy graph validation can establish revision pairs along different declarations.
Without a proven equivalent sequence, stop conversion and require an author decision.

A converter must refuse automatic conversion in these cases:

- Approval or direction also changes controller identity.
  The new rule permits transfer only through handoff.
- Acting-source and destination-authority joins disagree.
- Order was treated as a clock tick without an admitted mapping.
- Required historical validity or evidence is unavailable.
- Target identity/revision or finite branch/sequence intent is ambiguous.
- Equal revision strings conflated delivery and control policy identities.

An author can explicitly restructure these cases.
Record the source digest, decisions, and resulting semantic pin.
Those changes are semantic changes, not equivalent rewrites.
A legacy approval that moved control may need separate handoff and approval applications.
Each needs its own admitted order.
Each needs its own admitted evidence too.

A finite declaration's permitted trace set always changes when it becomes **reusable-policy**.
It needs an explicit author decision.
Removing fixed revisions does not authorize that change.
Neither does copying the same edge into a cycle.
Do not infer new authority or clock mappings.
Do not infer future completion receipts.
Keep transformed-proposal lineage and all original source artifacts.

## Occurrences, snapshots and ongoing episodes

Never rewrite historical IDs, actual order, revisions, or dispositions.
Never rewrite controller attribution, evidence, or markings.
Do not renumber an occurrence revision to match a state revision.
Occurrence revisions may count records across rejections and episodes.
V1 non-handoff history can depend on its original compiled transition.
That transition can determine the resulting state.
Keep that dependency and its content pin.

Historical v1 rejection records keep their original assertions.
The new rejected-attempt shape may express attempted/evaluated coordinates.
It can express them more truthfully than the old shape.
It does not change old records.
Conversion cannot manufacture missing historical evidence.
Old delivery bindings keep their original equality and destination-state rules.
The new source-controller rules do not apply retroactively.
Neither do the new independent-policy rules.

A live policy cannot be upgraded inside an episode.
Its meaning cannot be upgraded there either.
Drain or stop through the existing lifecycle.
Keep indeterminate effects for reconciliation.
Then explicitly admit a new episode with the selected supported policy.
Initialization must validate its authority.
It must mark the predecessor relation too.
Copying a policy address is insufficient.

Process recovery keeps the existing episode and store keys.
Exact old retries look up historical receipts.
Current access authorization still applies.
A new episode does not create a new namespace for the same principal/operation/client key.

Mixed-episode archives need per-episode pins and complete original context.
The reader verifies each episode using its own meaning.
It must not invent one contiguous controller-state revision across episodes.
The reader may lack historical policy, authority/cut evidence, or format.
It then reports reconstruction as unsupported/unverifiable.
Keep the bytes.

## Coordinated adoption and publication

The change must cover the existing owners together.
SDL owners cover closed models, safe parsing, and semantic references.
They cover variable instantiation and composition rewriting too.
Compiler children stay typed and deterministic.

API-409 owns occurrences and rejected-attempt carriers.
It owns their contextual joins too.
RUN-310 checks which targets are eligible.
It owns the state fold too.
It keeps history, receipt, and audit atomic at the exact cut.
DSL-142 covers directed-delivery declarations.
It also covers the actual joins to control applications.
It covers independent disclosure-policy resolution.
It covers delivery consumption and evidence too.

API-423/SEM-233 owns crossing joins.
API-424 owns effects and range/ref limits.
SEM-234 owns provider/phase links.
Adoption also covers conformance readers.
It covers runtime snapshot recovery too.

Capability admission must reject selected paths that lack the new semantics.
Do not weaken existing validators to accept new data.
A DSL-142 disclosure may have identical source/result refs.
That does not silently convert it to an API-424 inject effect.
Such an effect requires a fresh produced result.

Use the existing rules to govern every embedded schema affected by this change.
These include SDL authoring and instantiated scenario.
They include instantiated-scenario snapshot, materialized scenario, and satisfiability evidence too.
Include direct control occurrences and runtime snapshots too.
Use existing publication records for contract identity, schema path, and stability.
They contain no hash or change summary.
Resolve required schema-content pins from exact artifacts at a pinned release or Git revision.
Use the owning protocol's digest rule.
Git records schema history.
Use removal tombstones when applicable and `schema_bundle()` parity under ADR-009/061.

This design delivery changes or removes no schema.
It starts no deprecation/removal window.
It edits no package version or release history.

Required adoption evidence covers:

- Two cycles through the same compiled edge in one real episode.
- Positive and negative context checks for every kind.
- Exact concurrent, stale, authority, time, and target rejection.
- Finite-script bounds.
- Mixed archive replay with old policy pins.
- Unchanged legacy fixtures.
- Failed atomic commit and lost-response retry.
- Exact directed-delivery joins at the actual final sink.

The bounded design model cannot replace consumer tests or backend evidence.

## Continue

Use [finite-script conversion](mixed-control-finite-script-conversion.md) for local conversion.
Use [revised-control migration](revised-control.md) to coordinate installed readers and owners.
Read [reusable participant control](../explain/reference/reusable-participant-control.md) for runtime behavior.
