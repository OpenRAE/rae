# DSL-118 verification mapping

Issue: #299. Requirement state is proposed until merge.

| Requirement or acceptance criterion | Implementation | Executable evidence |
| --- | --- | --- |
| Generic directives, policies, instructions, and guidance | Existing ACT-620 descriptor in `ScenarioContent.control_context_assets`; `ParticipantControlContextReference` | `test_dsl_118_control_context.py::test_published_examples_preserve_exact_assets_across_two_imports` |
| Participant and reusable behavior selection | `raes/agents.py:106`; `raes/participant_behavior_specification.py:272`; `raes/participant_control_context.py:106` | Shared, withheld, reusable-role, and conflicting-slot cases in `test_dsl_118_control_context.py` |
| Preserve identity, scope, and content commitments through imports and compilation | `raes/composition/_control_context.py:8`; `raes/composition/_expand.py:124`; `raes_processor/compiler/participant_behaviors.py:178` | Repeated-import, rename, typed projection, and JSON serialization cases |
| Reject missing, ambiguous, stale, or incompatible references | `raes/participant_control_context.py:50`; ordinary post-instantiation and direct-artifact admission | Reference failures, immutable-token, private-export, descriptor-conflict, concrete-role, and direct-artifact cases |
| Declaration grants no visibility or permission | Authored intent has no placement, exposure, or delivery operation | Shared/withheld case asserts no content placement, observation boundary, or directed delivery |
| Publication, navigation, examples, and migration agree | `specs/sdl/participant-control-context.md`; section/reference catalogs; published schemas and hash entries | Schema-key rejection, navigation, example tests, schema-bundle/publication and catalog checks |
| Per-trial factor selects a participant asset through ADR-094 | `raes_contracts/contracts/experiment_bindings.py:141`; `raes_contracts/participant_configuration.py:109`; concrete owner binding in `raes_processor/trial_compiler/bindings.py:217` | `test_dsl_118_trial_control_context.py`: factor-to-sealed-entry-to-public-result witness, reload, absent owner, stale pin, wrong scope, conflicts, and owner mutation refusal |

ACT-620 retains lifecycle, byte, authority, and delivery agreement.
Its existing contract tests cover those trusted boundaries.
DSL-118 adds no live delivery claim.
Local verification uses explicit relevant modules and cases.
CI owns full independent verification.
