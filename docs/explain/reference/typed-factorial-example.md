# Model, prompt, and structural treatments

Use `factorial-treatments-v1` for a crossed experiment with structural choices.
The [public Python example](../../../implementations/python/examples/factorial_treatments.py) uses acquired trusted inputs.
It calls the public authoring loader, trial compiler, source-aware readmission, and one-entry realizer.
It makes no network request and executes no backend.

## Declare the effects

Each participant has its own manifest registry and address.
For example, declare these five independent factors:

| Factor | Levels | Owner target |
| --- | --- | --- |
| `pilot-engine` | `small`, `wide` | `agents.pilot`, manifest target `policy.model` |
| `pilot-brief` | `plain`, `revised` | `agents.pilot`, manifest target `context.briefing` |
| `observer-engine` | `small`, `wide` | `agents.observer`, manifest target `policy.model` |
| `observer-brief` | `plain`, `revised` | `agents.observer`, manifest target `context.briefing` |
| `terrain-x` | `isolated`, `observed` | SDL point `deployment-shape`, target `nodes.relay-47.presence` |

These names are examples.
No compiler rule assigns meaning to them.
Two levels per factor generate 32 conditions.
Two repetitions generate 64 trial entries.
Set `condition_bound: 32` and `target_runs_per_condition: 2`.

Put each level's effects under `factorial_design.level_effects`.
Model levels contain scalar `bindings` for the exact selected participant manifest.
Prompt levels also contain scalar bindings.
Their values name SDL control-context declarations from the manifest's pinned `control_context` domain.
Supply `SDLControlContextConfigurationValidator` through the trusted validator map.
The compiler checks its pins and applicability against each selected concrete scenario.
Content stays in consumer-controlled storage.
Selection does not establish prompt delivery or permission to disclose content.

The `terrain-x` levels contain typed `selections`.
Each selection carries the composed family digest, canonical target, SDL owner, and typed outcome.
Use `{kind: member, member_id: offline}` for an absent relay.
Use `{kind: member, member_id: instrumented}` for a present relay with its declared inventory.
The family owns both alternative definitions.
An alternative can couple presence with a selected scheduled-job inventory.
The experiment does not copy a node or encode a structural member as a string binding.

For SDL selection ownership, use these existing values:

```yaml
contract_id: sdl-authoring-input-v1
contract_version: '1'
validator_id: raes-selected-scenario
validator_version: '1'
```

Use the actual manifest registry owner for participant bindings.
Set family pins with `canonical_sdl_digest(family).value` after trusted composition.
Do not copy pins from an unrelated example.

## Fix invariant points

Select every family point exactly once in each condition.
Keep a non-treatment point fixed through an ordinary selection policy:

```yaml
selection_policies:
  fixed-path:
    kind: fixed
    policy_id: fixed-path
    purpose: fixed-configuration
    point_ref: payload-path
    outcome:
      kind: literal
      value: /opt/input
    output_bound: 1
```

This policy has no factor provenance or binding claims.
Selection-only designs need no dummy scalar descriptor.
Participant-only designs need no invented scenario point.
Node configuration uses declared scalar parameters or reviewed structural slots.
Arbitrary patches, nested writes, and unsupported configurations fail.

## Compile and realize

Supply an admitted `TrialCompilationRequest` with the compact design and exact owner artifacts.
Call `compile_example(request)` from the example.
The loader regenerates criteria and rejects inconsistent supplied materializations.
The compiler validates every requested combination before returning a sealed plan.
One invalid combination rejects the entire design.
It never removes or repairs a condition silently.
An incoming reference to a removed relay therefore rejects the design.
Absence also conflicts with a separate descendant write.

Call `realize_example(plan, request, plan_entry_id=entry_id, backend_key=backend_key)` for an admitted entry.
The backend manifest must support that entry's declared realization requirements.
The result contains the selected scenario, processor plans, and exact sealed participant configurations.
It does not execute the experiment.

`readmit_admitted_trial_plan(plan, request=request)` reconstructs the complete result from original authority.
The caller must trust those inputs and expected pins independently of the candidate plan.
Plan-only reload checks internal consistency.
Source-aware readmission also detects valid-looking resealed omissions or substitutions.
The full realizer checks authoring coordinates, bindings, typed selections, and fixed choices.
Supply participant manifests in `TrialRealizationInputs` when aliases need canonical resolution.
Dispatch does not rerun participant normalization.

Different labels cannot make equal effects distinct.
Comparison uses selected scenario content, operative realization constraints, complete defaults, and resolved pinned prompt content.
Provenance-only descriptor changes do not create a new prompt treatment.
Exact source labels and pins still remain mandatory in archive matching.
Runs carry `realized_selections` and `realized_bindings` from admitted records.
The run producer must separately establish execution and observed environment state.

Use the normal package release before downstream adoption.
Do not hand-edit the version or use an unreleased checkout as the release artifact.
