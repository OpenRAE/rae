# Scenario Description Language (SDL) Reference

RAES SDL is the YAML-based authored scenario language within Reproducible
Agentic Environments System. It describes declared intent for agentic
environments: settings in which participants can receive observations, take
actions, interact, and be evaluated under stated controls. The SDL is
domain-neutral, while its strongest current examples and lineage are in cyber.

The language starts from the
[Open Cyber Range SDL](https://github.com/Open-Cyber-Range/SDL-parser) surface,
preserves coverage across the OCR-derived sections, and extends that base with
content, accounts, relationships, agents, objectives, workflows, variables,
and other scenario concepts. It is intentionally its own SDL rather than a
clone-level derivative.

The SDL describes *what the scenario and experiment mean*; it is not a direct
deployment recipe. Backend implementations realize SDL specifications as
concrete agentic environments through runtime contracts. The repository
includes SDL-native instantiation,
compilation, planning, contracts, backend stubs, conformance checks, and a
reference control-plane surface. It does not include a production backend.

The SDL sits inside a broader ecosystem architecture with several distinct
surfaces:

- the **authored scenario and experiment** expressed in SDL
- the **processor** that instantiates, compiles, plans, and coordinates live
  execution
- the **backend** that realizes the scenario against infrastructure or
  simulation targets
- optional **participant implementations** such as agents, policies, scripts,
  or human-control proxies that consume participant contracts during a run
- **live runtime state** used for operational observation and control
- **archival run/evidence/provenance artifacts** used for comparison, replay,
  and experiment review

Those boundaries matter because authored scenario meaning is separate from the
apparatus that realizes or evaluates it. Current portability claims are limited
to the repository's schemas, contracts, stubs, examples, and tests.

The raw YAML document is only the entrypoint. The SDL's semantic behavior is
defined above that syntax layer through typed SDL models, semantic validation,
and the runtime/compiler/planner contracts. The repository-wide policy for when
to formalize those semantic layers lives in the
[coding standards](../reference/coding-standards.md).

Different SDL concerns also draw from different precedent families. OCR is the
main source for the section surface, CACAO contributes objectives/workflows and
variables, and the workflow/runtime semantics are further disciplined by mature
control-flow systems such as Step Functions, Argo, and SCXML plus portable
runtime-boundary patterns from systems such as Kubernetes and Temporal. The
crosswalk lives in [Design Precedents](precedents.md).

The imported research also informs ecosystem concerns that are only partly
surfaced in the current SDL syntax, including participant decision surfaces,
hidden benchmark assets, trajectory corpora, experiment evidence capture, and
participant-implementation apparatus. Cross-domain simulation and
co-simulation research shows that the time model cannot be treated as an
incidental runtime detail. Clock authority, time domains, pacing,
synchronization, and realized ordering guarantees are part of the broader
apparatus story, even when the current SDL syntax only exposes a subset of that
surface through timelines, timeouts, and budget-like controls. The primary
references collected in `research/primary/literature/time-and-simulation/`
are the current foundation for that time/clock work.

## Current Use Boundary

The current Python package supports parsing SDL, semantic validation,
variable instantiation, runtime-model compilation, planning against backend
manifests, control-plane contract exercise, and backend conformance checks.
It does not deploy scenarios to a real range by itself. Participant
implementation manifests, evidence-capture contracts, provenance contracts,
and the full time/clock authoring model remain partially materialized or
architecture-level surfaces.

## Stable IDs, Variable Values

The SDL keeps its **symbol table** concrete at parse time. User-defined identifiers such as node keys, feature keys, account keys, relationship keys, entity keys, and other named mapping keys are part of the language structure and must be literal.

Variables are for **attribute values** on already-declared things. That includes fields such as counts, ports, CIDRs, paths, timings, descriptions, and similar runtime-substituted values.

In other words:

- `nodes: {web: ...}` — `web` is a stable SDL identifier
- `content.hostname-file.text: ${hostname}` — `${hostname}` is a variable-backed attribute value

This means a hostname, IP, path, or display string can be variable-backed, but a node cannot be created or renamed through `${...}` inside a mapping key.

Generic cross-section refs such as relationship endpoints and objective targets accept either:

- bare names like `webapp` when the name is unambiguous
- qualified refs like `nodes.webapp`, `features.nginx`, `accounts.db-admin`, or `infrastructure.dmz-net` when disambiguation is needed

Named service bindings, named ACL rules, and workflow steps keep their existing qualified forms.

## Quick Example

```yaml
name: simple-pentest-lab
description: Web app with SQL injection targeting a database

nodes:
  lab-net:
    type: Switch
  webapp:
    type: compute
    os: linux
    resources: {ram: 2 gib, cpu: 1}
    features: [flask-app]
    services: [{port: 8080, name: http}]
    vulnerabilities: [sqli]
  database:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    features: [postgres]
    services: [{port: 5432, name: postgresql}]
    asset_value: {confidentiality: high}

infrastructure:
  lab-net: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
  webapp: {count: 1, links: [lab-net]}
  database: {count: 1, links: [lab-net]}

features:
  flask-app: {type: Service, source: vulnerable-flask-app}
  postgres: {type: Service, source: postgresql-16}

vulnerabilities:
  sqli:
    name: SQL Injection
    description: SQLi in login form
    technical: true
    class: CWE-89

relationships:
  app-to-db:
    type: connects_to
    source: flask-app
    target: postgres

accounts:
  db-admin:
    username: admin
    node: database
    password_strength: weak
```

## Documentation

- [SDL Sections Reference](sections.md) — Explanatory reference for the complete live authoring-section catalog
- [Parser Behavior](parser.md) — `sdl-yaml/v1`, explicit migration, typed normalization, and canonical identity
- [Scenario-Family Variation Points](variation-points.md) — Bounded domains, typed targets, constraints, and composition behavior
- [Language-Service Tools](language-service.md) — Agent-facing completions, references, formatting, diagnostics, and structured edits
- [Agent Guidance Profile](agent-guidance.md) — Machine-readable scope boundaries, invariants, review priorities, and safe-operating expectations
- [Semantic Validation](validation.md) — Cross-reference checks and what the validator enforces
- [Account Credential Bindings](../../../specs/sdl/account-credential-bindings.md) — Normative fixture/operator binding, redaction, and disclosure semantics
- [Design Precedents](precedents.md) — Where each SDL element comes from
- [Academic Lineage](lineage.md) — Primary-source lineage for SDL semantics
- [Scenario/Delivery Drift Audit](scenario-delivery-drift-audit.md) — Audit and remediation record for classification drift after ADR-033
- [Limitations](limitations.md) — Current expressiveness and materialization gaps
- [Scientific-Scenario Completeness](scientific-scenario-completeness.md) — REV1 intended-use profiles and current blocking concerns
- [Testing](testing.md) — How to run unit tests, stress tests, and fuzz tests
- [Complex Scenario Designs](complex-scenarios.md) — Up-front design briefs for large example exercises
- [Runtime Architecture](runtime-architecture.md) — SDL-native compiler, composite plans, and runtime targets
- [Control-Plane Recovery Operations](control-plane-operations.md) — Health, shutdown, recovery classification, local backup/restore, and upgrade procedures

## Usage

```python
from raes import parse_sdl, parse_sdl_file

# From a string
scenario = parse_sdl(yaml_string)

# From a file
scenario = parse_sdl_file(Path("scenarios/my-scenario.yaml"))

# Skip semantic validation (structural only)
scenario = parse_sdl(yaml_string, skip_semantic_validation=True)

# Non-fatal authoring advisories
for advisory in scenario.advisories:
    print(advisory)
```

## Format Boundary

This repository accepts SDL documents only. Older metadata/mode-based scenario
formats are out of scope and must be migrated before parsing.
