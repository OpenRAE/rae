"""Scaffold templates for the SDL authoring tools.

These are example documents, not schemas; ``sdl_scaffold`` substitutes
``{name}``/``{desc}`` placeholders into the selected template.
"""

_SCAFFOLD_MINIMAL = """\
name: {name}
description: {desc}

nodes:
  net-switch:
    type: Switch
    description: Main network

  server-01:
    type: compute
    os: linux
    resources: {ram: 2 GiB, cpu: 1}
    features: [my-service]
    services:
      - {port: 443, name: https}

infrastructure:
  net-switch:
    count: 1
    properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}
  server-01:
    count: 1
    links: [net-switch]

features:
  my-service: {type: Service, source: my-package}
"""

_SCAFFOLD_STANDARD = """\
name: {name}
description: {desc}

nodes:
  corp-net:
    type: Switch
    description: Corporate network

  web-server:
    type: compute
    os: linux
    resources: {ram: 4 GiB, cpu: 2}
    features: {web-app: web-admin}
    conditions: {web-healthy: web-admin}
    services:
      - {port: 443, name: https}
    roles:
      web-admin: www-data

  db-server:
    type: compute
    os: linux
    resources: {ram: 4 GiB, cpu: 2}
    features: {database: dba}
    services:
      - {port: 5432, name: postgres}
    roles:
      dba: postgres

infrastructure:
  corp-net:
    count: 1
    properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}
  web-server:
    count: 1
    links: [corp-net]
  db-server:
    count: 1
    links: [corp-net]

features:
  web-app: {type: Service, source: my-webapp}
  database: {type: Service, source: postgresql-16}

conditions:
  web-healthy:
    proposition: web-available
    command: "curl -sf https://localhost/ || exit 1"
    interval: 15

propositions:
  web-available:
    description: The web service reports its availability as healthy.
    subjects: [nodes.web-server.services.https]
    basis: observed_state
    predicate:
      kind: boolean
      property: service-healthy
      semantic_ref: urn:raes:observable:service-healthy
      operator: equals
      expected: true
    evidence_requirements: [web-health-evidence]

assertions:
  web-healthy:
    proposition: web-available
    role: postcondition

evidence_requirements:
  web-health-evidence:
    description: Capture evidence used to decide web availability.
    source_refs: [nodes.web-server.services.https]
    scope_refs: [nodes.web-server]
    boundary_kind: objective_completion
    channel: api_response
    artifact_role: proposition_truth_evidence
    media_types: [application/json]
    sensitivity: plain
    redaction: redact_secrets
    integrity: checksum
    retention: run_lifetime
    loss_disclosure: required

entities:
  blue-team:
    name: Blue Team
    role: Blue
  red-team:
    name: Red Team
    role: Red

# Objective success references assertions over typed propositions per ADR-079.
# Graded scoring/reward, if a study needs it, lives in the experiment/evaluator
# plane (ADR-055/064/069), not in the SDL.
objectives:
  keep-web-available:
    description: Keep the web application available
    entity: blue-team
    success:
      assertions: [web-healthy]

accounts:
  web-admin-account:
    username: webadmin
    node: web-server
    password_strength: strong
  db-admin-account:
    username: dbadmin
    node: db-server
    password_strength: medium

relationships:
  web-to-db:
    type: connects_to
    source: web-app
    target: database
    properties: {protocol: tcp, port: "5432"}
"""

_SCAFFOLD_FULL = """\
name: {name}
description: {desc}

# --- Parameterization ---
variables:
  exercise_speed:
    type: number
    default: 1.0
    description: Story playback speed multiplier
  admin_password_strength:
    type: string
    default: strong
    allowed_values: [weak, medium, strong]

# --- Topology ---
nodes:
  corp-net:
    type: Switch
    description: Corporate network

  web-server:
    type: compute
    os: linux
    resources: {ram: 4 GiB, cpu: 2}
    features: {web-app: web-admin}
    conditions: {web-healthy: web-admin}
    services:
      - {port: 443, name: https}
    roles:
      web-admin:
        username: www-data
        entities: [blue-team.web-ops]

  db-server:
    type: compute
    os: linux
    resources: {ram: 4 GiB, cpu: 2}
    features: {database: dba}
    services:
      - {port: 5432, name: postgres}
    roles:
      dba: postgres
    asset_value:
      confidentiality: high
      integrity: high

infrastructure:
  corp-net:
    count: 1
    properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}
  web-server:
    count: 1
    links: [corp-net]
  db-server:
    count: 1
    links: [corp-net]

# --- Software ---
features:
  web-app: {type: Service, source: my-webapp}
  database: {type: Service, source: postgresql-16}

conditions:
  web-healthy:
    proposition: web-available
    command: "curl -sf https://localhost/ || exit 1"
    interval: 15

propositions:
  web-available:
    description: The web service reports its availability as healthy.
    subjects: [nodes.web-server.services.https]
    basis: observed_state
    predicate:
      kind: boolean
      property: service-healthy
      semantic_ref: urn:raes:observable:service-healthy
      operator: equals
      expected: true
    evidence_requirements: [web-health-evidence]

assertions:
  web-healthy:
    proposition: web-available
    role: postcondition

evidence_requirements:
  web-health-evidence:
    description: Capture evidence used to decide web availability.
    source_refs: [nodes.web-server.services.https]
    scope_refs: [nodes.web-server]
    boundary_kind: objective_completion
    channel: api_response
    artifact_role: proposition_truth_evidence
    media_types: [application/json]
    sensitivity: plain
    redaction: redact_secrets
    integrity: checksum
    retention: run_lifetime
    loss_disclosure: required

entities:
  blue-team:
    name: Blue Team
    role: Blue
    entities:
      web-ops: {name: Web Operations}
  red-team:
    name: Red Team
    role: Red

# --- Orchestration ---
injects:
  attack-brief:
    source: attack-briefing-doc
    from_entity: red-team
    to_entities: [blue-team]

events:
  attack-start:
    injects: [attack-brief]

scripts:
  main-timeline:
    start_time: 0
    end_time: 4 hour
    speed: ${exercise_speed}
    events:
      attack-start: 30 min

stories:
  exercise:
    speed: ${exercise_speed}
    scripts: [main-timeline]

# --- Content ---
content:
  seed-data:
    type: dataset
    target: db-server
    format: sql
    source: seed-data-pkg

# --- Accounts ---
accounts:
  web-admin-account:
    username: webadmin
    node: web-server
    password_strength: ${admin_password_strength}
  db-admin-account:
    username: dbadmin
    node: db-server
    password_strength: medium

# --- Relationships ---
relationships:
  web-to-db:
    type: connects_to
    source: web-app
    target: database
    properties: {protocol: tcp, port: "5432"}

# --- Agents ---
agents:
  red-agent:
    entity: red-team
    actions: [Scan, Exploit]
    initial_knowledge:
      hosts: [web-server]
      subnets: [corp-net]
      services: [https]

# --- Objectives ---
objectives:
  red-access:
    agent: red-agent
    actions: [Scan, Exploit]
    targets: [web-server, sqli]
    success:
      assertions: [web-healthy]
    window:
      stories: [exercise]
  blue-defend:
    entity: blue-team
    success:
      assertions: [web-healthy]
    depends_on: [red-access]

# --- Workflows ---
workflows:
  exercise-flow:
    start: run-attack
    steps:
      run-attack:
        type: objective
        objective: red-access
        on_success: run-defense
      run-defense:
        type: objective
        objective: blue-defend
        on_success: done
      done:
        type: end
"""
