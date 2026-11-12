# Enterprise participant evidence loop

Inspect an action and its evidence in [the scenario file](enterprise-participant-evidence-loop.sdl.yaml).
The example links authored SDL to the processor.
A runtime/backend binding is a later step.
It declares a red workbench, DMZ portal, and internal database.
It also declares Wazuh evidence and optional participant policy provenance.

Local parsing and compilation need RAES.
Native execution needs a backend.
That backend must supply a participant implementation, realize the application, and produce evidence.
The file supplies no coding-agent runner.
It includes no private APTL scenario or TechVault benchmark.

## Topology

| Node | Declared network attachment and purpose |
| --- | --- |
| `red-workbench` | Participant host on `redteam-net` and `dmz-net`. |
| `customer-portal` | DMZ web application on `dmz-net` and `internal-net`. |
| `customer-db` | Database on `internal-net` only. |
| `wazuh-manager` | Evaluator surface on `security-net` and `internal-net`, where monitored hosts can report events. |
| `wazuh-indexer` | Evaluator surface on `security-net`. |
| `participant-policy-gate` | Optional policy/provenance surface on `security-net`. |

The participant host has no attachment to `internal-net` or `security-net`.
Direct database and Wazuh API access are outside the declared participant action.
A supporting live backend can record negative reachability evidence.
The declared topology alone proves no network isolation.

## Participant

`participant-agent` is bound to the red-role entity `enterprise-participant`.
It probes `nodes.customer-portal.services.http`.
It reports a bounded terminal observation.
The behavior specification names the runner through `participant-implementation-manifest:participant-agent`.
The runner itself is outside SDL.

## Declared action

`probe-customer-portal-login` is the action contract.
It declares authority, target, and realization preconditions.
It names effect classes, failure classes, diagnostic mappings, and a shared-state interaction.
It also declares Wazuh evidence for the evaluator.
Policy provenance and negative boundary evidence have separate declarations.
It contains no commands, prompts, or runner configuration.
It includes no backend-native action labels, credentials, Wazuh rules, or model-defense internals.

## Observation boundary

`participant-view` separates the task brief and service discovery.
It also separates hidden resources, evaluator evidence, and adjudication material.
The portal service becomes discovered after the participant reports its terminal observation.
The database service and Wazuh internals stay outside that view.
The policy gate and evaluator notes also stay hidden.
The operating scope names only the DMZ portal and task brief.
The topology and view express separate boundaries.
The backend must realize the applicable controls.

## Expected evidence

| Record | Purpose |
| --- | --- |
| `content.participant-observation` | Participant runtime observation envelope. |
| `content.wazuh-evidence` | Evaluator evidence for the portal probe. |
| `content.policy-decision-log` | Optional model-defense or tool-use authorization provenance. |
| `content.boundary-check-evidence` | Negative direct database/Wazuh reachability evidence where a live backend supports it. |

The objective and outcome rule use these bounded records.
A successful local action proves no broad benchmark result.
It establishes neither Wazuh effectiveness nor model-defense robustness.

## Runtime binding

`OpenRAE/rae` owns this scenario, portable processing, and runtime contracts.
A backend owns native realization and produces evidence.
[ADR-115](../../docs/decisions/adrs/adr-115-concrete-backends-owned-outside-raes.md) assigns that role.
For example, [OpenRAE/lilrae](https://github.com/OpenRAE/lilrae) owns the separate PyPI distribution `lilrae`.
This link proves no compatible version.
It establishes no successful realization of this scenario.

The backend binding supplies the participant implementation manifest and its provenance record.
It realizes the declared portal probe and keeps participant, Wazuh, and policy evidence.
It records negative boundary evidence where it supports live checks.
The binding must not require new SDL syntax or a new backend manifest shape.
It must not require backend-private keys in this scenario.

## Historical libvirt evidence artifact (#615)

RAES 7.0.0 and earlier bundled `raes libvirt evidence validate` for this scenario.
Issue #967 removed the producer with the bundled libvirt backend.
See the [concrete-backend migration](../../docs/migration/concrete-backends.md).
RAES now ships no producer for that historical artifact.
A realizing backend distribution owns its artifact and claims.

The historical artifact covered compilation and deterministic execution of the participant contract.
Its bounded mode excluded full guest and application provisioning.
It established no full two-backend realization or byte equivalence.
It proved neither detection-quality parity nor model-defense robustness.
It established no full semantic equivalence.

## Downstream links

These links identify the original evidence work.
They give no current support guarantee:

- RAES scenario: [OpenRAE/rae#598](https://github.com/OpenRAE/rae/issues/598).
- Participant binding: [OpenRAE/rae#599](https://github.com/OpenRAE/rae/issues/599).
- Two-backend proof: [OpenRAE/rae#600](https://github.com/OpenRAE/rae/issues/600), formerly associated with `examples/corpus/reference-demonstration/`.
- Libvirt participant runtime: [OpenRAE/rae#614](https://github.com/OpenRAE/rae/issues/614).
- Libvirt evaluator readback: [OpenRAE/rae#615](https://github.com/OpenRAE/rae/issues/615).
- APTL realization work: Brad-Edwards/aptl#556, Brad-Edwards/aptl#557, and Brad-Edwards/aptl#558.

## Limitations

The [focused scenario test](../../implementations/python/tests/test_scenarios.py) parses and validates this file.
It also compiles the participant handoff declarations.
The example proves no TechVault coverage.
It proves no purple-team benchmark coverage.
It proves no autonomous-agent capability.
It does not test Wazuh detection quality.
It does not test model-defense robustness.
It includes no private runner, prompt, sandbox policy, or credential.
It includes no backend log, Wazuh ruleset, policy body, or hidden answer key.
It remains a corpus example for bounded backend proof work.
