# Classification migration

Issue #989 removes external classifications from canonical SDL. Native
configuration and action contracts determine the environment and transitions.
Authored interpretations use the standalone
[external concept binding contract](external-concept-bindings.md).

## Inventory and disposition

| Surface | Classification | Canonical disposition |
| --- | --- | --- |
| `vulnerabilities` declarations, including `class`, `name`, `description`, `technical` | Compatibility syntax for authored weakness assertions | Removed from native SDL; original declarations remain in immutable migration source provenance. |
| Node, feature, and recursive entity `vulnerabilities` associations | External authored assertions | One binding per exact native subject and association; no intrinsic weakness predicate. |
| Application route `vulnerability_refs` | External authored assertions | Bind the exact `nodes.<node>.runtime.applications.<application_id>.routes.<route_id>` subject; ambiguous coordinates refuse. Never widen to a node. |
| Behavior `offensive_behavior_refs`, `ai_offensive_behavior_refs`, `defensive_behavior_refs` | External authored assertions | Complete generic binding against the exact behavior specification. |
| Action `external_mappings` | External authored assertions | Complete generic binding; retain source `system`, `identifier`, `loss_label`, and `rationale` through the exact provenance pointer. |
| Recursive entity `categories` | External authored assertions | Complete generic bindings with explicitly supplied scheme and perspective. |
| Entity `mission`, procedure basis, fidelity claims, names and descriptions | Authored narrative/claim text | Retained as narrative; not implicit participant knowledge or an alternate scheme-coordinate syntax. |
| Detection-definition tags/compliance tags and loaded source content | Participant/environment content | Retain the observed content; its presence does not establish compliance or native truth. |
| Content and dataset-item `tags` | Authored participant/environment content | Retained as ordinary content metadata, not scheme coordinates or native predicate evidence. |
| Participant roles, node access roles, credential purpose, endpoint persona | Native operational semantics | Retained: aggregate selection, access binding, credential constraints, and tenancy. |
| Action precondition/effect/failure/interaction classes, behavior modes, typed relationships, protocol families and time mappings | Native operational semantics | Retained: native validation, transition, protocol and realization contracts. |
| Sensitivity/credential classifications, evidence source/boundary classes | Native operational semantics | Retained: information flow, redaction, capture and disclosure policy. |
| Manifest `concept_bindings`, capabilities and support declarations | Native operational semantics | Retained: apparatus vocabulary and admission claims; distinct from authored external bindings. |
| Projection `witness`, `gap`, `unknown`, `ambiguous`, `excluded` | Derived report outcomes | Retained within the exact report frame; never native configuration labels. |

The removal includes canonical/instantiated models, generated schemas,
language metadata, declaration aliases, temporal subjects, composition,
variation slots, compiler tuples and raw specifications, vulnerability template
counts, comparison projections and MCP inspection. Optional pinned ATT&CK,
ATLAS and NIST source catalogs remain available, with no governed SDL scope.
Adding another scheme requires data in the existing generic contract.

## Explicit conversion

`externalize-sdl-classifications/v1` is an offline authoring transformation.
It accepts bounded, canonical-spelling legacy YAML, complete caller-authored
binding assertions, explicit local snapshots and an
`ArtifactTransformationPolicy`. Source bytes are never overwritten.
It returns the incumbent `SDLTransformationResult`: either admitted native
SDL, complete binding documents and an `ArtifactTransformationReportModel`,
or a refusal report with no output artifacts.

Every legacy association is identified by its exact source JSON pointer.
Each supplied assertion names that pointer and the source digest in a typed
`authoring-input` provenance reference, and names the exact native subject in
the same source artifact. The migrator changes only the subject digest to the
new SDL digest. Relationship, semantic effect, perspective, authority basis,
assertion time, source refs, confidence, approximation/loss, limitations and
review are explicitly authored. No field receives a guessed value.

Known behavior catalog keys differ from source concept ids: for example,
ATT&CK `execution` corresponds to `TA0002`. Authors select that mapping using
the pinned source and its neutral adapter. A governed extension has no implied
source coordinate. A CWE identifier alone is not a pinned CWE snapshot.

The exact source projection uses `raes-sdl-semantic/v1` over normalized,
uncomposed legacy authoring input. Native fields must already have canonical
typed values: a migration that would also normalize native data refuses.
Migrate imported source documents independently before composition and refresh
their import digests through the existing module workflow. Instantiated or
snapshot artifacts require their owning lifecycle migration; this operation
does not pretend they are authoring input.

Vulnerability declaration removal requires explicit `declaration-removed`
authorization. An unreferenced declaration additionally requires
`semantic-omission` authorization. Every authorized removal is reported.
References to a removed declaration must independently pass target validation;
objectives, propositions and temporal references are never silently retargeted.
Missing, duplicate, stale, ambiguous, unknown and superseded contexts refuse.
Existing binding documents are explicitly supplied and retargeted using the
incumbent exact-subject helper, then readmitted with the new bindings.

## Invariants and interpretation

1. Native projection equality is checked independently of binding admission.
2. Every classification association has exactly one explicit assertion.
3. A successful result includes all three artifact types atomically.
4. All output binding subjects resolve against the target digest; source
   provenance continues to name the historical source.
5. Pure conversion has no clock, environment, network, plugin or subprocess
   dependency and does not mutate supplied objects.
6. Binding admission cannot grant capability, change a transition, satisfy a
   proposition, or prove realization. Finite preservation checks are not a
   universal behavioral equivalence proof.

## Participant content and semantic comparison

A participant may receive a rendered classification as ordinary `content`,
with an exact binding-artifact reference in the content's provenance. Use the
existing participant-directed inject, observation-boundary and information-flow
contracts to mediate its disclosure and record the crossing/delivery evidence.
The source catalog and full assertion may remain withheld. A binding's
`participant_availability: eligibility-only` grants no access and records no
delivery or knowledge.

Compare native operands and external-binding operands separately through the
existing semantic-comparison operation. Migration intentionally changes SDL
identity by externalizing assertions; the transformation report explains the
removed source declarations and binds the target and sidecars. Projection
reports must be regenerated for the target frame. Neither a changed label nor
binding resolution provides native predicate evidence.

The lifecycle record is
[`sdl-domain-classification-fields`](../evolution/deprecation-records.yaml).
See the [migration guide](../../docs/migration/external-classifications.md)
for supported inputs, diagnostics and rollback.
