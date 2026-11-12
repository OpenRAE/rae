# Typed factorial compilation

This design implements the profile published by issue #1665.
ADR-084 owns trial admission and deterministic reconstruction.
ADR-094 owns scalar bindings and complete participant configuration.
No authority boundary changes.

## Components and failure behavior

The authoring model generates the bounded Cartesian product.
Its generated allocation remains the source of condition criteria.
The compiler combines scalar scenario bindings, typed selections, and fixed configuration policies.
Every scenario point must have exactly one selection.
Fixed configuration has no factor source claim.
Manual typed criteria require the typed factorial design.

The SDL target resolver validates typed descriptors through its existing canonical target calculation.
It checks the family identity, family digest, point, target, owner, and outcome domain.
Its scalar resolver continues to reject structural targets.
The compiler uses the existing public scenario selector for combined effects.
That selector checks write conflicts, selection relations, and the complete selected scenario.
One invalid combination rejects the complete plan.

Participant targets resolve through the selected manifest registry.
Every participant configured anywhere in the design receives complete configuration in each condition.
Defaults remain effective when a level has no override for that participant.
Control-context validation uses the selected concrete scenario.
Opaque secret references remain unresolved.

Condition comparison uses selected scenario content and complete participant values.
Scenario selection labels and provenance-only instantiation fields cannot establish distinct effects.
Operative capability bounds, parameter derivations, and realization constraints remain in the comparison.
Prompt comparison uses pinned content and operative slot and scope.
Declaration spelling and descriptor-only digest changes cannot establish a new prompt effect.
Participant default and override origins cannot establish distinct effects.
The existing canonical JSON helper computes the comparison commitment.
The compiler retains comparison commitments only during admission.
Sealed entries retain exact source descriptors and complete configurations.
The optional treatment profile identifies typed semantics without changing scalar profile serialization.

Public one-entry instantiation reconstructs the sealed plan and repeats SDL selection.
It also checks typed targets against the supplied family.
Source-aware readmission recompiles trusted original inputs and compares the complete candidate plan.
The full realizer checks supplied authoring criteria before returning an entry.
Plan-only reload proves internal consistency, not agreement with unavailable original inputs.
Allocation replay uses the existing recorded allocation procedure.
Run/study matching requires both selection descriptors and participant bindings.
Plan-aware archive validation compares exact admitted treatment records.
Seals prove content identity; they do not prove backend execution.

## Security and data flow

Assets include treatment intent, family commitments, participant configuration, and archival source joins.
The authoring boundary accepts untrusted bounded documents through the existing closed models.
The owner boundary prevents writes outside declared SDL points and manifest targets.
Whole-scenario validation prevents dangling references after structural removal.
Complete participant validation prevents unsupported configurations and invalid prompt applicability.
The seal and archive boundaries detect omission, substitution, and changed source joins.
Targeted negative tests exercise each boundary.

```text
Author [external entity]
  -- bounded treatment design --> Authoring validation [process]
Authoring validation
  -- generated conditions --> Authoring artifact [store]
Family and manifest owners [external entities]
  -- pinned declarations --> Family and manifest artifacts [stores]
Authoring artifact
  -- scalar and typed criteria --> Owner admission [process]
Family and manifest artifacts
  -- targets, domains, defaults --> Owner admission
Owner admission
  -- joint outcomes --> Whole-scenario selection [process]
Whole-scenario selection
  -- concrete scenario --> Complete participant validation [process]
Complete participant validation
  -- admitted effects and source records --> Sealed trial plan [store]
Sealed trial plan
  -- exact entry --> Public realization [process]
Public realization
  -- scenario and configurations --> Run producer [external entity]
Run producer
  -- realized records --> Archival run [store]
Sealed trial plan and archival run
  -- exact commitments --> Archive validation [process]
```

Compiler diagnostics omit values and owner exception text.
The implementation adds no network call, subprocess, credential access, or storage service.
Runtime execution and observation remain backend responsibilities.
Shared runtime and record producers remain outside this change.

## Supporting artifacts

The existing closed contracts provide the architecture as code.
The existing schema, source-join, seal, and policy checks remain the policy controls.
No new enforcement layer or requirement is introduced.
The existing EXP-719 requirement owns this extension.
No schema shape, deployment component, or ADR decision changes.
The data flow above covers the changed components.
The public reference and example explain fixed points and invalid combinations.
The issue plan contains implementation tasks and verification commands.

## References and document review

- [Python 3.11 itertools](https://docs.python.org/3.11/library/itertools.html), `product`: retain deterministic bounded Cartesian generation.
- [Pydantic 2 validators](https://docs.pydantic.dev/latest/concepts/validators/), model validators: reconstruct closed records at ingress.
- [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785), section 3: reuse canonical JSON commitments.
- [NIST SP 800-160 Volume 1 Revision 1](https://csrc.nist.gov/pubs/sp/800/160/v1/r1/final), system security design: connect threats, boundaries, controls, and verification.
- [ASD-STE100 Issue 9](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf), sections 1, 5, 6, and 8: review terminology, sentence length, and document purpose.

The writing review uses consistent technical names and short descriptive sentences.
Architecture facts remain here; workflow tasks remain in the issue plan.
