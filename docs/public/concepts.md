# Understand the RAES model

Use these ideas to distinguish a scenario, its realization, and the evidence
from an investigation. Start with the [first scenario](quickstart.md), then
choose a [research question](research.md).

The source links below identify inspected Python behavior at commit
`e71ddbc29e9e06658ddbe2b2c12edf8ed424f044`. This is a source snapshot,
not a claim about the latest release. Compare it with your installed version.

## Authored scenario

A scenario records an author's intended environment and behavior.
The Scenario Description Language (SDL) expresses that intent in a file.
The [document model][document-model] defines its sections and relationships.
Nodes can describe hosts or networks. Other sections describe participants,
objectives, workflows, and evidence requirements.

The [first example](_static/examples/first-scenario.sdl.yaml) declares one
network and one Linux host. A successful parse establishes that this document
passes the implemented structural and semantic rules. It creates no host.
Structural rules check data shape. Semantic rules check meaning and relationships.

An objective states a desired outcome. Its declaration does not prove success.

Author declarations have different degrees of precision.
An **exact** declaration fixes a requirement. A **constrained** declaration
permits choices within stated bounds. An **open** concern permits realization
only where the governing rules allow it.
The [explicitness specification][explicitness] defines these distinctions.
An omitted field does not give unrestricted permission to add state.

## Realized environment

Realization builds an environment under admitted scenario requirements.
A processor compiles those requirements. It plans against a backend's declared
support. The backend performs concrete operations.
It must honor an exact request or reject it. It cannot silently approximate it.
The [planner tests][realization-tests] demonstrate this boundary with test manifests.

Different realizations can meet the same admitted constraints.
They can still differ in other ways.
A **realization envelope** defines permitted choices and required disclosure.
The [envelope specification][envelopes] defines that comparison.
Neither equal scenario files nor equal observations establish equal environments.
The [backend guide](backends.md) explains support declarations and reports.

At this source snapshot, `OpenRAE/rae` contains the Python runtime and processor.
It supplies portable backend interfaces and stubs, but no concrete deployment backend.
An external backend project, such as [LilRAE](https://github.com/OpenRAE/lilrae),
owns its native resources and credentials. The planned repository split does
not establish a shipped runtime product.

## Participants, control, and information

A participant is an entity that acts or receives observations in a scenario.
Its **view** is the information available under a selected projection rule.
A projection rule selects the information exposed in that view.
Its local history records the admitted sequence of its interactions.
World state can contain facts absent from that view.
The [participant semantics][participants] defines these objects.

Control can permit, deny, or withhold an action at a particular state boundary.
Permission, execution, delivery, and observation are separate facts.
A permitted action can fail. A completed world effect can remain undelivered.
The [control support reference][control-support] explains those outcomes and
the tested configurations.

**Information flow** concerns how information can reach a participant.
**Predicate opacity** asks whether a selected secret fact can remain uncertain
under a stated observer model. Each secret case needs an indistinguishable
nonsecret alternative. The [opacity specification][opacity] defines the exact
condition, including memory, strategy, order, and time assumptions.
Equal visible payloads alone do not establish secrecy.

## Bounded reproduction

A reproduction attempt checks a stated result under known conditions.
RAES can describe inputs and the apparatus for that attempt.
It can also describe observations and provenance.
**Provenance** records where an artifact came from and how it relates to other
artifacts. It identifies a history. It does not establish the artifact's truth.

The [experiment specification][experiment] separates the scenario, task,
apparatus, run, evidence, and study. A task states the evaluation problem.
The apparatus identifies the execution setup. A run records one execution.
A study relates runs to an analysis.

An authored evidence requirement states what should be collected.
An evidence record describes supplied captured material.
Neither a valid requirement nor a valid record proves that collection occurred.
RAES does not promise equal outcomes, exact replay, or scientific reproducibility.
Use the [evidence research route](research.md#what-evidence-supports-another-attempt)
to examine what a particular check establishes.

## Conformance

A contract defines an interface's required structure and meaning.
A **profile** selects a named set of conditions for a particular check.
A **fixture** is a controlled test input with an expected result.
The [conformance reference][conformance] distinguishes fixture checks from
checks against a running target.

Passing one profile establishes only the result of that check under its inputs.
It does not establish support for every SDL feature, backend security, or
scientific validity. The [current limits](limitations.md) and
[citation guide](citation.md) help you describe that boundary.

[document-model]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/specs/sdl/document-model.md
[explicitness]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/specs/formal/realization/explicitness-and-realization.md
[realization-tests]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/implementations/python/tests/test_sem_218_realization.py
[envelopes]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/specs/formal/realization/envelope-semantics.md
[participants]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/specs/formal/participant-semantics/README.md
[control-support]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/docs/explain/reference/revised-control-semantics.md
[opacity]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/specs/formal/participant-semantics/participant-predicate-opacity.md
[experiment]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/specs/formal/experiment-core/README.md
[conformance]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/docs/explain/reference/backend-conformance.md
