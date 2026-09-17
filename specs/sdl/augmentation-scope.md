# Scenario augmentation scope

`augmentation_scope` controls whether a processor or backend may introduce
additional in-world effects to satisfy evidence, evaluation, or operational
requirements. It is independent of realization delegation, observation demand,
and visibility/comparability classification (SEM-225; issue #1242).

## Open by default

**Omitting `augmentation_scope` means open.** Authors must explicitly forbid
additions; they do not have to enumerate and authorize every collector, listener,
wrapper, or other implementation detail in advance. Closed-by-default semantics
would impose a large, unexpected burden on scenario authors, who cannot reasonably
anticipate every backend's implementation requirements. Open-by-default also
preserves compatibility with existing scenarios.

Open permission does not waive other requirements. A backend must still satisfy
the requested evidence, preserve exact authored values, obey realization authority,
honor prohibited observation, and disclose realized effects under its negotiated
reporting contract. Permission to add something is not evidence that it exists.

## Author declarations

Forbid all additional in-world effects:

```yaml
augmentation_scope:
  default: closed
```

Allow additions generally, but protect a particular node:

```yaml
augmentation_scope:
  default: open
  scopes:
    - scope: /nodes/subject
      permission: closed
```

A closed default can have an explicit open exception, for example
`/nodes/management`. The most specific applicable rule wins within one authoring
namespace. Equal-specificity duplicate rules are invalid. Scope addresses use
the existing SDL semantic-address system and must resolve to a node, collection,
or concern; prefix-like names such as `management-extra` are not descendants of
`management`. Collection member identity is preserved across reordering.

Composition qualifies scope addresses with the same declaration identities as
the rest of the imported module. Imported policies remain independently binding:
an importing document's open default cannot reopen a module's explicit closure.
An outer closure can further restrict an import. The `namespace` carrier records
this composition provenance; it is not another permission axis. It must own the
addressed declaration (or an ancestor module); naming an unrelated admitted
import is invalid. An imported open default does not override an outer closure:
the outer author must explicitly permit the affected scope as well.

## What counts as an addition

The boundary is the common SDL world described by
[materialization attestation](materialization-attestation.md), not whether an
object is called instrumentation or happens to be installed on a separate host.
Collectors, sidecars, listeners, process wrappers, mounts, environment changes,
network configuration, and injected content are in scope when they introduce
observable in-world effects. Replacing or removing something can also introduce
an effect; merely labeling a difference `selected` does not exempt it.

Ordinary selection of an explicitly delegated platform/OS concern is realization,
not augmentation. Out-of-world bookkeeping, archive writes, and passive processing
of already obtained observations do not themselves add to the scenario world.

Every affected scope must permit the effect, including its installation location
and its impact on other nodes or concerns. An open management node does not grant
permission to alter a closed subject. A logical observation boundary does not
establish network isolation. Unknown or incompletely described impact is not an
admissible prospective effect.

## Admission and refusal

Explicit policy requires negotiation of `backend-augmentation-scope-v1` and
`backend-materialization-attestation-v1`. An older backend must refuse an explicit
policy it cannot enforce, even if that policy says `open`; it must not silently
ignore the declaration. Historical documents with no policy retain their existing
negotiation behavior. A scope-capable backend evaluates omission as open.
The canonical phase plan retains `augmentation_scope_required` and its full
original source when an author declares policy, including when negotiation fails.
Runtime boundaries validate the source's bound identity and derive the requirement
from its policy as well as the plan flag. Clearing diagnostics or that flag cannot
erase the source's requirement.

Before mutation, the producer supplies a read-only preparation containing the
prospective common SDL content, complete effect coverage using the attestation's
`raes-materialization-effects/v1` comparison, the requirements needing each effect,
and all affected scopes. This is a prediction, not a post-materialization
attestation. It is bound to the full original source, plan, operation, run,
predecessor, and backend manifest/configuration identities.

The producer API is `prepare_augmentation(plan, snapshot)`. Preparation must not
install, initialize, collect, or otherwise mutate the world. Its `content` is
bounded JSON for the existing common SDL content, without phase provenance;
it must not fabricate a post-materialization report. Each effect identifies an
actual comparison pointer, at least one requirement, and all affected scopes.
Requirement references resolve to an original `/evidence_requirements/<name>`,
`/objectives/<name>`, `/assertions/<name>`, or `/propositions/<name>` declaration.
The fixed `backend-operational` reference denotes intrinsic backend execution
requirements, not arbitrary backend diagnostic prose. Content is limited to
1 MiB, effects to 4,096, and aggregate effect/scope/requirement references to
16,384, in addition to the shared portable-value bounds.

The manager prepares all active provisioning, evaluation, and orchestration
phases before its first mutation, then checks that each producer's immediate
preparation has not changed the admitted intent. Each producer declares only its
own changes from the original source. The runtime composes these into cumulative expectations
using native collection identities; a later producer cannot overwrite or claim
another producer's effects. Conflicting ownership is refused before mutation.
Later invocations retrieve the preceding attestation through the protected archive
and verify its bytes, identity, and source lineage before composing their effects.
Their actual attestation retains the cumulative world, including earlier phases.
Successful preparation warnings and informational diagnostics remain advisory
and are emitted once at the immediate preparation boundary. Time, participant, and
observation hooks must also prepare. These hooks do not have an in-world
attestation delivery boundary: any apparatus they need must be materialized
through an admitted, attested plan phase first. A hook declaring its own
in-world addition is therefore refused before mutation, even under open
permission. Read-only/out-of-world hooks can proceed. This prevents an
attestation archived before collection from concealing a later installation.
The independent durable control-plane path applies the same preparation and
observation-hook admission before its mutating call.

If required evidence cannot be obtained without an effect in closed scope, the
runtime refuses before materialization. The operator-facing diagnostic names the
requirement, needed effect, and governing closed scope. It must neither introduce
the forbidden effect nor omit the required evidence and report success. Optional
collection is not a loophole for an otherwise prohibited addition. Existing
complete-offer capture admission and observation lifecycle guarantees still apply.

Actual effects are checked against the admitted preview and original authority
before publishing an accepted attestation. A mismatch is failure, not permission
to replay with wider authority; valid cleanup inventory is retained. Attestation
and archival success cannot retrospectively authorize an addition.
