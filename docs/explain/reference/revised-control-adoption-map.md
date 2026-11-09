# Revised-control producer and reader map

Use this reference with Python RAES 11.0.2.
Policy semantics, wire contracts, and installed owners have separate identities.
Use [migrate revised control](../../migration/revised-control.md) for the operating task.

## Coordinate contracts and interfaces

### API-409 occurrences

The producer selects rev1 semantics and `participant-control-occurrence-v2`.
It installs the compiled policy and live-cut resolver.
The reader handles v1 and v2 separately.
It keeps each episode's original policy and admissions.

### API-424 evaluation

The producer negotiates selection/evaluation v2 content hashes.
It uses `ParticipantControlProviderV2.resolve_stage`.
The reader checks complete coverage.
It checks exact predecessor inputs too.
It checks required support, state authorization, and the commit receipt.
It keeps v1 history's original meaning.

### Inject execution

The producer builds the closed trigger request.
It pins the exact plan, binding, placement, input, occurrence, key, and expected head.
The reader checks occurrence, per-binding outcome, and success correlation separately.
A queued receipt is not an effect.

### Participant delivery

The producer installs the matching compiled delivery model.
It also installs trusted projection/crossing owners.
The reader joins the exact world result, participant, episode, audience, and binding.
It includes the exact accepted control occurrence when required.

### Mixed execution

The host installs exact mixed binding/service pins through `MixedRuntimeBinding.backend_installations`.
The reader authenticates stage producers.
It checks committed clocks, mappings, reports, and owner readback.
Historical callback success is not stage evidence.

### Opacity harness

The harness supplies `reported_observation()` and fresh `backend_readback()`.
It also supplies pinned probe points.
The reader compares reported and measured transcripts.
Missing or conflicting evidence cannot establish a native claim.

## Content identities and support

The [schema publication manifest](../../../contracts/schema-publication-manifest.json) indexes contract records.
Each record gives `contract_id`, `schema_path`, and `stability`.
It gives no schema-content hash or change summary.
For required runtime content pins, use the exact schema from a pinned release or Git revision.
Use the owning protocol's digest rule for that schema artifact.
Git records schema history.
A method name or matching revision string does not establish support.
Neither does a manifest declaration alone.
An older consumer must refuse unsupported lineage or content pins.
It must keep the original bytes.

## Detailed boundaries

- [Control applicability and evaluation](../../migration/control-applicability-and-evaluation.md) covers complete apparatus and coverage.
  It also covers mandatory inputs, optional loss, and effects.
- [External inject adoption](../sdl/external-inject-compatibility.md) covers occurrence claims, original authoring, and consumer joins.
- [External inject operation](../../public/guides/external-injects.md) covers executing-provider installation and delivery.
  It also covers scheduled placement and capture.
- [Mixed backend execution](../../migration/mixed-backend-execution.md) covers independent service roles and stage settlement.
- [Opacity observed evidence](../../migration/participant-opacity-observed-evidence.md) covers harness interface changes and bounded claims.
