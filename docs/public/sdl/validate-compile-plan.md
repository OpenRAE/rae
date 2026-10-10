# Validate, compile, and inspect a scenario plan

Build a small RAES SDL scenario one section at a time and check it after each
step. Then compile it and read the portable plan that RAES prepares for a backend.
The guide stops at that backend boundary. Nothing is provisioned or started.

## Install the command-line tool

You need Python 3.11 through 3.14. Install RAES in a virtual environment:

```console
python -m venv .venv
source .venv/bin/activate
python -m pip install raes
```

The package installs the `raes` command. After installation, the commands in
this guide work on local files and contact no backend. They use a POSIX shell
such as Bash or Zsh.

## Describe the topology

Save this file as `guided-web-probe.sdl.yaml`:

<!-- scenario-plan:topology:start -->
```yaml
name: guided-web-probe
description: A red participant tries to stop one web service while a blue team keeps it online.

nodes:
  lab-network:
    type: switch
  web:
    type: compute
    resources:
      ram: 1 GiB
      cpu: 1
    services:
      - name: http
        port: 80
        protocol: tcp
  workstation:
    type: compute
    resources:
      ram: 1 GiB
      cpu: 1

infrastructure:
  lab-network:
    count: 1
    properties:
      cidr: 10.20.0.0/24
      gateway: 10.20.0.1
  web:
    count: 1
    links:
      - lab-network
  workstation:
    count: 1
    links:
      - lab-network
```
<!-- scenario-plan:topology:end -->

`nodes` declares one switch and two hosts. The `services` entry gives the web
host an HTTP service that other sections can name as `nodes.web.services.http`.
`infrastructure` asks for one instance of each node and links both hosts to the
switch.

Validate the file:

```console
raes semantic validate guided-web-probe.sdl.yaml
```

<!-- scenario-plan:validate-output:start -->
```text
validate: success
```
<!-- scenario-plan:validate-output:end -->

Exit status `0` means that RAES accepted the file's structure and its semantic
rules. Run the same command after each of the next steps. Each finished step
prints the same result.

## Add a condition

A condition describes a probe that a backend can run. It names a command and
how often to run it. A condition does not decide what is true.

Add this top-level section to the end of the file:

<!-- scenario-plan:condition:start -->
```yaml
conditions:
  web-alive:
    command: curl -sf http://localhost/
    interval: 15
    timeout: 5
```
<!-- scenario-plan:condition:end -->

Next, attach the probe to the web host. Add `conditions` and `roles` under the
existing `web` entry in `nodes`. Do not add a second `nodes` key:

<!-- scenario-plan:condition-binding:start -->
```yaml
nodes:
  web:
    conditions:
      web-alive: operator
    roles:
      operator:
        username: operator
```
<!-- scenario-plan:condition-binding:end -->

`web-alive: operator` runs the probe on `web` as the node role `operator`.
The role must exist under `roles`.

## Add evidence

An evidence requirement states what a run must keep. It names the source, the
scope, the trigger, and how to handle the record. It is not evidence itself. It
does not prove that capture happened.

A proposition states a claim about the scenario. An observed-state
proposition lists the evidence requirements needed to decide it.

Add both sections:

<!-- scenario-plan:evidence:start -->
```yaml
evidence_requirements:
  web-health-evidence:
    description: Keep each result of the web-alive probe.
    source_refs:
      - nodes.web
    scope_refs:
      - nodes.web.services.http
    trigger_ref: conditions.web-alive
    channel: log
    sensitivity: plain
    redaction: none
    integrity: checksum
    retention: run_lifetime
    loss_disclosure: required

propositions:
  web-alive:
    description: The web service answers HTTP requests.
    subjects:
      - nodes.web.services.http
    basis: observed_state
    predicate:
      kind: boolean
      property: service-alive
      semantic_ref: urn:raes:observable:service-alive
      operator: equals
      expected: true
    evidence_requirements:
      - web-health-evidence
```
<!-- scenario-plan:evidence:end -->

`trigger_ref` ties capture to the `web-alive` probe. The five handling fields,
from `sensitivity` to `loss_disclosure`, are required. RAES also rejects an
evidence requirement that has neither `scope` nor `scope_refs`.

## Add attacker behavior

An action contract says what a participant action means. It states when the
action applies, what it should change, and how it can fail. It names no tool or
command. A backend supplies the mechanism.

<!-- scenario-plan:attacker-behavior:start -->
```yaml
action_contracts:
  stop-web:
    semantic_version: 1.0.0
    behavioral_granularity: atomic
    procedure_basis: Send one request that asks the web service to stop.
    realization_profile: backend-declared
    fidelity_claim: States intent and expected effect; a backend supplies the mechanism.
    preconditions:
      - precondition_id: web-reachable
        precondition_class: target
        description: The web service is reachable from the lab network.
        support_refs:
          - nodes.web.services.http
    effects:
      - effect_id: web-stopped
        effect_class: intended_effect
        description: The web service stops answering requests.
        target_refs:
          - nodes.web.services.http
    failure_classes:
      - target_unavailable
      - authority_denied
```
<!-- scenario-plan:attacker-behavior:end -->

A contract needs at least one precondition, one effect, and one failure class.
Each list uses a closed set of classes, such as `target` and `intended_effect`.

## Add participants

Entities are teams, organizations, or people. Each key under `agents` names
one participant.

<!-- scenario-plan:participants:start -->
```yaml
entities:
  red-team:
    role: red
  blue-team:
    role: blue

agents:
  red-agent:
    affiliations:
      - red-team
    actions:
      - stop-web
    initial_knowledge:
      hosts:
        - workstation
    allowed_subnets:
      - lab-network
```
<!-- scenario-plan:participants:end -->

`red-agent` takes the `red` role from its one affiliation. Each entry in
`actions` must name a declared action contract. `initial_knowledge` says what
the participant knows at the start. `allowed_subnets` limits where it may act.

## Add objectives

An assertion gives a proposition a role and a polarity. Here, both assertions
are postconditions about `web-alive`. One requires that the service answers.
The other requires that it does not.

An objective states who pursues what and how success is judged.

<!-- scenario-plan:objectives:start -->
```yaml
assertions:
  web-up-at-end:
    proposition: web-alive
    role: postcondition
    polarity: positive
  web-down-at-end:
    proposition: web-alive
    role: postcondition
    polarity: negative

objectives:
  take-web-offline:
    assigned_participant: red-agent
    actions:
      - stop-web
    targets:
      - nodes.web.services.http
    success:
      assertions:
        - web-down-at-end
  keep-web-online:
    owner: blue-team
    targets:
      - nodes.web.services.http
    success:
      assertions:
        - web-up-at-end
```
<!-- scenario-plan:objectives:end -->

Every objective needs an `owner`, an `assigned_participant`, or both.
`take-web-offline` is assigned to `red-agent`, so each of its actions must be one
that `red-agent` declares. `keep-web-online` has an owner and no assigned
participant. Each objective's `success` must name at least one invariant or
postcondition assertion.

Validate once more. The command prints `validate: success`. The finished file
is also in the RAES repository as
[`examples/scenarios/guided-web-probe.sdl.yaml`](https://github.com/OpenRAE/rae/blob/main/examples/scenarios/guided-web-probe.sdl.yaml).

## Read diagnostics

When RAES rejects a file, the command prints the result on standard output. It
prints one line per diagnostic on standard error. The exit status is `1`.

Suppose you appended the condition binding as a second `nodes` key. Validation
fails before any semantic check:

```console
raes semantic validate guided-web-probe.sdl.yaml
```

<!-- scenario-plan:invalid-output:start -->
```text
validate: invalid
error [sdl.mapping_key_conflict] SDL input was rejected at the parse stage.
```
<!-- scenario-plan:invalid-output:end -->

Add `--output json` for one JSON document with a `status` and a `diagnostics`
list. Each diagnostic has a `code`, `domain`, `address`, `message`, and
`severity`. The command-line message names the failed stage.

For the specific reason, ask the RAES language service:

<!-- scenario-plan:diagnostics-script:start -->
```console
python - <<'PY'
from pathlib import Path

from raes.language_service import language_diagnostics

report = language_diagnostics(Path("guided-web-probe.sdl.yaml").read_text(encoding="utf-8"))
for diagnostic in report["diagnostics"]:
    print(diagnostic["code"], diagnostic["message"])
PY
```
<!-- scenario-plan:diagnostics-script:end -->

<!-- scenario-plan:diagnostics-output:start -->
```text
sdl.mapping_key_conflict Duplicate mapping key 'nodes'.
```
<!-- scenario-plan:diagnostics-output:end -->

Parse diagnostics also carry a `path` and a source `range` with line and
column numbers.

`raes semantic parse` checks less than `validate`. It decodes the file and
builds the typed model without semantic checks. On the finished file, it
prints this result:

```console
raes semantic parse guided-web-probe.sdl.yaml
```

<!-- scenario-plan:parse-output:start -->
```text
parse: success
```
<!-- scenario-plan:parse-output:end -->

A file whose objective names a missing assertion also parses, but it does not
validate.

### Common failures

These are the results for small mistakes in the finished file:

| Mistake | Command-line code | Language service message |
| --- | --- | --- |
| A second top-level `nodes` key | `sdl.mapping_key_conflict` | `Duplicate mapping key 'nodes'.` |
| An evidence requirement without `scope_refs` | `sdl.model.invalid` | `evidence requirement must declare scope_refs or scope` |
| `retention: forever` | `sdl.model.invalid` | `retention must be one of: not_retained, run_lifetime, study_lifetime, archival, policy_defined, other` |
| The node binds `web-alive-check` | `sdl.validation` | `Node 'web' references undefined condition 'web-alive-check'` |
| `red-agent` no longer lists `stop-web` | `sdl.validation` | `Objective 'take-web-offline' action 'stop-web' is not declared by agent 'red-agent'` |
| An objective names `web-offline-at-end` | `sdl.validation` | `Objective 'take-web-offline' references undefined assertion 'web-offline-at-end' in success criteria` |

The last mistake reports two diagnostics. The second says that the assertion is
not in the `assertions` section.

## Compile the scenario

Compile the validated file and print the summary as JSON:

```console
raes semantic compile guided-web-probe.sdl.yaml --output json
```

This is part of the output:

<!-- scenario-plan:compile-output:start -->
```text
  "operation": "compile",
  "payload": {
    "diagnostic_count": 0,
    "phase": "compiled-runtime-summary",
    "resource_counts": {
      "assertions": 2,
      "events": 0,
      "feature_bindings": 0,
      "injects": 0,
      "networks": 1,
      "node_deployments": 2,
      "objectives": 2,
      "propositions": 1,
      "scripts": 0,
      "stories": 0,
      "workflows": 0
    },
    "root_type": "object",
    "scenario_name": "guided-web-probe"
  },
  "processor_profile": "raes-compiler/default",
```
<!-- scenario-plan:compile-output:end -->

The counts cover the runtime resources that the compiler built. They do not
include participants, action contracts, or evidence requirements. To list every
declaration with its address, run
`raes semantic inspect guided-web-probe.sdl.yaml --output json`.

## Inspect the plan

Plan the scenario and save the JSON:

```console
raes processor plan guided-web-probe.sdl.yaml --format json > plan.json
echo $?
```

```text
1
```

Exit status `1` means that the plan has an error diagnostic. RAES still writes
the complete plan. Its `provisioning`, `orchestration`, and `evaluation`
members each validate against a published plan contract. A top-level
`diagnostics` list holds the errors. If the file does not compile, the command
also exits `1`, but it writes nothing to standard output.

Print each planned operation and diagnostic:

<!-- scenario-plan:plan-script:start -->
```console
python - <<'PY'
import json

with open("plan.json", encoding="utf-8") as handle:
    plan = json.load(handle)
for domain in ("provisioning", "orchestration", "evaluation"):
    for operation in plan[domain]["operations"]:
        print(domain, operation["action"], operation["address"])
for diagnostic in plan["diagnostics"]:
    print(diagnostic["severity"], diagnostic["code"], diagnostic["address"])
PY
```
<!-- scenario-plan:plan-script:end -->

<!-- scenario-plan:plan-output:start -->
```text
provisioning create provision.network.lab-network
provisioning create provision.node.web
provisioning create provision.node.workstation
evaluation create evaluation.condition.web.web-alive
evaluation create evaluation.proposition.web-alive
evaluation create evaluation.assertion.web-down-at-end
evaluation create evaluation.assertion.web-up-at-end
evaluation create evaluation.objective.take-web-offline
evaluation create evaluation.objective.keep-web-online
error capture.offer-missing evidence_requirements.web-health-evidence
```
<!-- scenario-plan:plan-output:end -->

Provisioning creates the network and both hosts. Evaluation has operations for
the probe binding, the proposition, both assertions, and both objectives. The
scenario declares no events, scripts, stories, or workflows, so `orchestration`
has no operations.

Without `--manifest`, RAES plans against its reference dry-run manifest. That
manifest declares no capture offers, so no backend capability covers
`web-health-evidence`. The scenario is still valid. The error marks a gap
between what the scenario requires and what the selected backend declares.

## Task cards

Replace `scenario.sdl.yaml` with your file.

**Check a file in automation.**
Run `raes semantic validate scenario.sdl.yaml`. Exit `0` means accepted, `1`
means rejected, and `2` means an invalid command or option.

**Give an agent structured results.**
Add `--output json` to any `raes semantic` command. Read `status` and
`diagnostics`.

**Explain a rejection.**
Run the language service script from [read diagnostics](#read-diagnostics) on
the file.

**See what the compiler built.**
Run `raes semantic compile scenario.sdl.yaml --output json` and read
`resource_counts`.

**Plan for a specific backend.**
Run `raes processor plan scenario.sdl.yaml --manifest backend.json --format json`.
`backend.json` is the backend's manifest in the backend-manifest-v2 format.

## Know where RAES stops

The plan is a read-only dry run. RAES did not provision hosts, start the probe,
check readiness, capture evidence, or clean up. Those steps belong to a backend.
Environment-pack authoring, distribution, and scenario catalogs belong to their
own projects.

## Continue on a backend

- Run a lab with LilRAE:
  [run your first lab](https://openrae.github.io/lilrae/getting-started/quick-start/).
- Follow the bounded TechVault exercise from APTL's research profile:
  [lab walkthrough](https://openrae.github.io/lilrae/workshop/walkthrough/).
- Author and package environment packs with
  [env-packs](https://github.com/OpenRAE/env-packs).

For more detail, read the [SDL guide](index.md), the
[command-line guide](../guides/cli.md), and the
[backend and conformance guide](../backends.md).
