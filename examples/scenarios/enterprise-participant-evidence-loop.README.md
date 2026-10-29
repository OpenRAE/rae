# Enterprise Participant Evidence Loop

`enterprise-participant-evidence-loop.sdl.yaml` is the RAES reference scenario for the
authored SDL -> processor -> runtime -> backend handoff. It is a generic
enterprise slice: a red participant workbench, a DMZ customer portal, an
internal database, a Wazuh evidence surface, and optional participant policy
provenance. It is a positive worked example, not a benchmark, backend profile,
APTL-private scenario, TechVault-specific scenario, or proof that a specific
coding-agent runner executed.

## Topology

The topology carries the participant-observation claim:

- `red-workbench`: the participant's runtime-facing host, attached to
  `redteam-net` and `dmz-net`.
- `customer-portal`: the DMZ web application, attached to `dmz-net` and
  `internal-net`.
- `customer-db`: the internal database, attached only to `internal-net`.
- `wazuh-manager` and `wazuh-indexer`: Wazuh evaluator evidence surfaces on
  `security-net`, with the manager also attached to `internal-net` so monitored
  hosts can report events.
- `participant-policy-gate`: an optional policy/provenance surface on
  `security-net`.

The participant host is not attached to `internal-net` or `security-net`. Direct
database and Wazuh API access from the participant host is outside the declared
participant action and is represented as negative evaluator evidence for live
backends that support those checks.

## Participant

The scenario declares one participant, `participant-agent`, bound to the
`enterprise-participant` red-role entity. Its authored behavior is intentionally
narrow: probe `nodes.customer-portal.services.http` and report a bounded
terminal observation. The concrete coding-agent runner is outside the SDL and
is referenced only through `participant-implementation-manifest:participant-agent` in
the behavior specification.

## Declared Action

`probe-customer-portal-login` is the governed action contract. It records the
participant's authority, DMZ target, realization preconditions, portable effect
classes, failure classes, backend diagnostic mappings, and a shared-state
interaction over the customer portal service. It also declares evaluator-only
evidence effects from Wazuh, optional policy provenance, and negative boundary
checks. The contract does not embed commands, prompts, runner config,
backend-native action labels, Wazuh rule bodies, credentials, or model-defense
policy internals.

## Observation Boundary

`participant-view` separates the public task brief, the DMZ service before and
after discovery, hidden internal resources, evaluator-only evidence, and hidden
adjudication material. The portal service becomes discovered only after the
terminal participant observation. `nodes.customer-db.services.postgres`, Wazuh
internals, `nodes.participant-policy-gate`, and `content.evaluator-notes` remain
outside the participant view.

This is stronger than saying the agent was not told something. The authored
topology places the participant host outside `internal-net` and `security-net`,
the agent operating scope names only the DMZ portal and task brief, and the
Wazuh/policy/boundary records are evidence-only surfaces for the evaluator.

## Expected Evidence

The expected evidence is deliberately bounded:

- `content.participant-observation`: the participant runtime observation
  envelope.
- `content.wazuh-evidence`: Wazuh evaluator evidence for the portal probe.
- `content.policy-decision-log`: optional model-defense or tool-use
  authorization provenance.
- `content.boundary-check-evidence`: negative evidence for direct DB and Wazuh
  API reachability from the participant host where supported by a live backend.

The objective and outcome interpretation rule use those records to support the
reference demonstration without treating local action success as broad benchmark
success, Wazuh effectiveness, or model-defense robustness.

## Runtime Binding

The runtime and backend binding is downstream of this scenario. A backend
distribution, such as [LilRAE](https://github.com/OpenRAE/lilrae), binds
`participant-agent` to a participant implementation manifest and provenance
record. It realizes the declared portal probe, keeps participant, Wazuh, and
policy evidence, and records negative boundary evidence where it supports live
checks. That binding must not require new SDL syntax, a new backend manifest
shape, or backend-private keys inside the scenario body.

## Historical Libvirt Evidence Artifact (#615)

RAES 7.0.0 and earlier bundled a libvirt evidence producer for this scenario
(`raes libvirt evidence validate`). Issue #967 removed it with the libvirt
backend. See the
[concrete backends migration](../../docs/migration/concrete-backends.md) and
[ADR-115](../../docs/decisions/adrs/adr-115-concrete-backends-owned-outside-raes.md).
RAES now ships no producer for this artifact. A backend distribution that
realizes this scenario owns its evidence artifact and its claims.

The historical artifact made a narrow claim. RAES can compile this authored
scenario and execute its deterministic participant contract. It disclosed that
the bounded libvirt mode did not realize the full guest and application
provisioning plane. It made no claim of full realization on two backends,
byte equivalence, Wazuh detection-quality parity, model-defense robustness, or
full semantic equivalence.

## Downstream Links

- RAES issue: OpenRAE/rae#598
- Participant implementation binding: OpenRAE/rae#599
- RAES n=2 backend proof: OpenRAE/rae#600
  (corpus: `examples/corpus/reference-demonstration/`)
- Libvirt participant runtime: OpenRAE/rae#614
- Libvirt evaluator/Wazuh evidence readback: OpenRAE/rae#615
- APTL realization and proof: Brad-Edwards/aptl#556,
  Brad-Edwards/aptl#557, Brad-Edwards/aptl#558

This RAES scenario supplies the authored scenario that downstream backend
distributions can consume.

## Limitations

- The scenario proves SDL parsing, semantic validation, and processor
  compilation of participant handoff surfaces.
- It does not claim TechVault coverage, purple-team benchmark coverage, or
  autonomous-agent capability.
- It does not evaluate Wazuh detection quality or model-defense robustness.
- It does not include a private runner command, prompt, sandbox policy,
  credential, backend log, Wazuh ruleset, model-defense policy body, or hidden
  answer key.
- It was designed for small n=2 backend proof work and remains reusable as a
  corpus example.
