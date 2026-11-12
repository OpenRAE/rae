# Glossary

This glossary is a reference aid. Normative definitions remain in `specs/`,
published schemas, source code, and ADRs.

## System And Environments

**RAES**
: Reproducible Agentic Environments System, the overall system of
  specifications, contracts, reference implementations, examples, and
  assurance material in this repository. RAES is broader than its SDL, any one
  backend, and any one application domain.

**Agentic environment**
: A declared and realized setting in which one or more participants receive
  observations, take actions, interact with resources or other participants,
  and are evaluated under stated controls. Participants can include software
  agents, policies, scripts, and human-control proxies. This explanatory term
  does not introduce a new schema or runtime guarantee.

**Reproducibility support**
: Preservation and connection of authored intent, deterministic or governed
  variation, realization inputs, participant behavior and observations,
  apparatus identity, provenance, evidence, replay boundaries, and conformance
  results so a bounded reproduction attempt can be made and assessed. RAES does
  not guarantee deterministic runtime behavior, equal outcomes, exact replay,
  scientific validity, or reproducibility.

**Realized environment**
: The concrete environment produced from an authored scenario by a selected
  processor, backend, participant implementations, configuration, and runtime
  choices. It is not identical to the authored scenario, and underspecified
  choices require realized-form and apparatus disclosure where the applicable
  contracts provide it.

## Authoring And SDL

**RAES SDL**
: The YAML-based scenario description language implemented in this repository.
  It starts from the Open Cyber Range SDL surface and adds RAES-specific
  sections and semantics. See [Open Cyber Range SDL](https://documentation.opencyberrange.ee/docs/sdl/).

**SDL document**
: A YAML document with a required `name`, optional composition fields, and up
  to 21 named SDL sections.

**Authored scenario meaning**
: The scenario and experiment intent encoded in SDL before processor
  instantiation, compilation, planning, or backend realization.

**Scenario**
: The authored topology, services, accounts, content, relationships,
  participants, objectives, workflows, and evaluation material described by an
  SDL document.

**Experiment**
: The evaluation context around a scenario, including objectives, workflows,
  observations, results, evidence, and provenance.

**Section**
: A top-level SDL mapping such as `nodes`, `infrastructure`, `features`,
  `conditions`, `relationships`, `agents`, `objectives`, `workflows`, or
  `variables`.

**Module**
: A publishable SDL unit with `id`, `version`, optional parameters, exports,
  and description.

**Import**
: A reference from one SDL module to another module source. Current source
  classes are `local:`, `oci:`, and `locked:`.

**Environment pack**
: A downstream packaging and distribution unit that may contain SDL scenarios
  and other reusable assets. It is not another name for a scenario, an SDL
  document phase or model, or a realized environment. The
  [env-packs repository](https://github.com/OpenRAE/env-packs) owns pack
  structure and pack tooling; this repository remains authoritative for the
  SDL, concept, and reusable-asset trust-policy meanings a pack relies on. See
  [Scenario And Environment-Pack Vocabulary](../../migration/raes-rename.md#scenario-and-environment-pack-vocabulary).

**Variable**
: A declared value placeholder for attribute values on already-declared SDL
  objects. Variables do not create or rename mapping keys. The variable lineage
  includes CACAO playbook variables. See [CACAO Security Playbooks v2.0](https://docs.oasis-open.org/cacao/security-playbooks/v2.0/security-playbooks-v2.0.pdf).

**Relationship**
: A typed directed edge between named scenario elements. The section is adapted
  from STIX relationship objects. See [STIX 2.1](https://docs.oasis-open.org/cti/stix/v2.1/stix-v2.1.html).

**Agent**
: An autonomous scenario participant declaration with action, knowledge, and
  scope fields. The section is informed by CybORG agent-facing scenario
  material. See [CybORG](https://arxiv.org/abs/2108.09118).

**Objective**
: A declarative experiment task binding actors, targets, timing, and success
  criteria.

**Workflow**
: A control graph over objectives and workflow steps. RAES workflow semantics
  are owned by this repository; CACAO is prior art for playbook workflow
  structure. See [CACAO Security Playbooks v2.0](https://docs.oasis-open.org/cacao/security-playbooks/v2.0/security-playbooks-v2.0.pdf).

## Processing And Contracts

**Processor**
: The layer that instantiates SDL, compiles runtime models, plans changes,
  validates apparatus capabilities, and coordinates live control-plane
  operations.

**Instantiation**
: The repo-owned pass that applies explicit parameter values and SDL variable
  defaults, rejects unresolved placeholders, and produces a concrete scenario.

**Runtime model**
: The typed compiled representation used by the processor after validation and
  instantiation.

**Execution plan**
: The processor output that reconciles a runtime model against a backend
  manifest and runtime snapshot.

**Provisioning plan**
: The execution-plan portion for deployable resources and bindings.

**Orchestration plan**
: The execution-plan portion for events, scripts, stories, workflows, and
  inject state.

**Evaluation plan**
: The execution-plan portion for condition bindings and objectives.

**Runtime snapshot**
: The typed state model used by the planner and manager to represent current
  runtime resources, dependencies, and statuses.

**Backend**
: An apparatus surface that realizes scenario targets against infrastructure,
  emulation, simulation, or stubs. This repository includes backend contracts,
  stubs, and conformance checks; it does not include a production cyber-range
  backend.

**Manifest**
: A machine-readable declaration of an apparatus surface's identity,
  compatibility, realization support, constraints, and capabilities.

**Portable contract**
: A language-neutral contract intended to preserve meaning across processors,
  backends, participants, and live execution surfaces.

**Control plane**
: The live execution surface implemented by the current processor layer for
  processor-managed operations, statuses, workflow results, evaluation
  results, and history streams.

**Participant implementation**
: An agent, policy, script, or human-control proxy that consumes participant
  contracts during a run. This surface is architecture-level in the current
  repository and is not fully materialized as published schemas.

**Reference implementation**
: The Python implementation under `implementations/python/`. It is the current
  executable implementation for parsing, validation, instantiation,
  compilation, planning, control-plane contracts, stubs, and conformance
  checks.

## Evidence, Authority, And Reference Material

**Live runtime state**
: Operational state used during planning, control, observation, or execution.

**Evidence artifact**
: A recorded observation, result, history event, or related output used to
  evaluate or compare runs.

**Provenance**
: Metadata that records source, transformation, runtime, apparatus, or evidence
  origin needed to interpret a scenario or run result.

**Authority boundary**
: The repository policy that identifies which roots carry normative authority
  and which roots provide implementation, explanation, or support material.

**Normative spec**
: A document under `specs/` that defines repository semantics independent of a
  single implementation.

**ADR**
: An architecture decision record under `docs/decisions/adrs/`.

**Formal artifact**
: A specification, invariant set, or model under `specs/formal/` used for
  semantic or stateful subsystem reasoning.

**Concept authority**
: The repository layer that binds recurrent concept families, controlled
  vocabularies, reference models, and semantic profiles to explicit authority
  records.

**Backend conformance**
: The contract and fixture discipline used to check that backend-facing
  declarations and results satisfy published RAES contracts.

**Surface**
: A named, bounded, contract-bearing scope of an RAES artifact or apparatus to
  which governed vocabularies and concept bindings apply. The normative
  definition, including the one-surface-versus-two decision rule, lives in
  `specs/concept-authority/concept-authority.md`.

**Apparatus**
: The processor, backend, participant, live execution, evidence, and provenance
  surfaces around an authored scenario.

## Primary References

- [Open Cyber Range SDL](https://documentation.opencyberrange.ee/docs/sdl/)
- [CACAO Security Playbooks v2.0](https://docs.oasis-open.org/cacao/security-playbooks/v2.0/security-playbooks-v2.0.pdf)
- [STIX 2.1](https://docs.oasis-open.org/cti/stix/v2.1/stix-v2.1.html)
- [OCSF](https://ocsf.io/)
- [CybORG](https://arxiv.org/abs/2108.09118)
- [IEEE HLA 1516 family](https://standards.ieee.org/ieee/1516/3744/)
- [SISO Cyber DEM](https://cdn.ymaws.com/www.sisostandards.org/resource/resmgr/standards_products/siso-std-025-2023_cyberdem.pdf)
