"""SDL reference and learning tools.

These tools teach agents about the SDL from scratch — no prior knowledge
required.  They expose the language overview, per-section documentation,
and annotated real-world examples.
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Docs / examples on disk — allowlisted filenames only


def _find_repo_root(start: Path) -> Path:
    """Walk up from a known module file until a repo-root marker is found.

    Avoids hard-coded `parents[N]` indices that break when the package is
    relocated within the source tree.
    """
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists() or (candidate / ".ground-control.yaml").exists():
            return candidate
    raise RuntimeError(f"could not locate RAES repo root from {start}")


_REPO_ROOT = _find_repo_root(Path(__file__).resolve().parent)
_DOCS_DIR = _REPO_ROOT / "docs" / "explain" / "sdl"
_EXAMPLES_DIR = _REPO_ROOT / "examples" / "scenarios"

_ALLOWED_DOCS = frozenset({"sections.md", "parser.md", "validation.md"})
_ALLOWED_EXAMPLES = frozenset(
    {
        "hospital-ransomware-surgery-day.sdl.yaml",
        "satcom-release-poisoning.sdl.yaml",
        "port-authority-surge-response.sdl.yaml",
    }
)


def _read_doc(name: str) -> str:
    if name not in _ALLOWED_DOCS:
        return f"Documentation file not available: {name}"
    path = _DOCS_DIR / name
    if not path.exists():
        return f"Documentation file not found: {name}"
    return path.read_text()


def _read_example(name: str) -> str:
    if name not in _ALLOWED_EXAMPLES:
        return f"Example file not available: {name}"
    path = _EXAMPLES_DIR / name
    if not path.exists():
        return f"Example file not found: {name}"
    return path.read_text()


# Section-level reference snippets

# Maps each section name to the heading anchor used in sections.md so we
# can extract just the relevant portion.
_SECTION_NAMES: dict[str, str] = {
    "nodes": "Nodes",
    "infrastructure": "Infrastructure",
    "features": "Features",
    "conditions": "Conditions",
    "propositions": "Propositions",
    "assertions": "Assertions",
    "entities": "Entities",
    "injects": "Orchestration: Injects, Events, Scripts, Stories",
    "events": "Orchestration: Injects, Events, Scripts, Stories",
    "scripts": "Orchestration: Injects, Events, Scripts, Stories",
    "stories": "Orchestration: Injects, Events, Scripts, Stories",
    "orchestration": "Orchestration: Injects, Events, Scripts, Stories",
    "content": "Content",
    "accounts": "Accounts",
    "relationships": "Relationships",
    "forwarding_agents": "Forwarding Agents",
    "agents": "Agents",
    "action_contracts": "Action Contracts",
    "observation_boundaries": "Observation Boundaries",
    "outcome_interpretation_rules": "Outcome Interpretation Rules",
    "behavior_specifications": "Behavior Specifications",
    "evidence_requirements": "Evidence Requirements",
    "objectives": "Objectives",
    "workflows": "Workflows",
    "variables": "Variables",
}


def _extract_section(doc_text: str, heading: str) -> str:
    """Extract a single ## section from the sections.md document."""
    marker = f"## {heading}\n"
    start = doc_text.find(marker)
    if start == -1:
        return f"Section '{heading}' not found in reference docs."
    # Find end: next ## heading or end of file
    next_h2 = doc_text.find("\n## ", start + len(marker))
    if next_h2 == -1:
        return doc_text[start:]
    return doc_text[start:next_h2].rstrip()


# ---------------------------------------------------------------------------
# Tool registrations
# ---------------------------------------------------------------------------


def register(mcp: FastMCP) -> None:
    """Register SDL reference/learning tools on the MCP server."""

    @mcp.tool(
        name="sdl_overview",
        description=(
            "Get a comprehensive overview of the RAES Scenario Description "
            "Language (SDL). Returns what the SDL is, its authoring sections, how "
            "parsing/validation works, the variable system, and a complete "
            "minimal example. Start here if you have never seen the SDL before."
        ),
    )
    def sdl_overview() -> str:
        return _OVERVIEW_TEXT

    @mcp.tool(
        name="sdl_section_reference",
        description=(
            "Get detailed documentation for a specific SDL section including "
            "its schema, fields, YAML examples, shorthands, and validation "
            "rules.  Valid section names: nodes, infrastructure, features, "
            "conditions, entities, orchestration "
            "(injects+events+scripts+stories), content, accounts, "
            "relationships, forwarding_agents, agents, action_contracts, "
            "observation_boundaries, outcome_interpretation_rules, "
            "behavior_specifications, evidence_requirements, objectives, "
            "workflows, variables. You can "
            "also pass the individual section name like 'conditions' or "
            "'events'."
        ),
    )
    def sdl_section_reference(section: str) -> str:
        key = section.lower().strip()
        if key not in _SECTION_NAMES:
            valid = sorted(set(_SECTION_NAMES.keys()))
            return f"Unknown section '{section}'. Valid names: {', '.join(valid)}"
        heading = _SECTION_NAMES[key]
        doc_text = _read_doc("sections.md")
        extracted = _extract_section(doc_text, heading)

        # Append relevant validation rules
        validation_text = _read_doc("validation.md")
        verify_tag = f"verify_{key}"
        # Try to find the matching validation pass description
        val_lines: list[str] = []
        for line in validation_text.splitlines():
            if verify_tag in line.lower().replace("-", "_"):
                val_lines.append(line)
        if val_lines:
            extracted += "\n\n### Validation Rules\n\n" + "\n".join(val_lines)

        return extracted

    @mcp.tool(
        name="sdl_get_example",
        description=(
            "Get a complete, real-world annotated SDL scenario example. "
            "Available examples: 'hospital' (hospital ransomware exercise, "
            "~750 lines, broad language coverage), 'satcom' (satellite supply-chain "
            "exercise, ~750 lines), 'port' (port authority OT exercise, ~680 lines), "
            "'minimal' (a small annotated pentest-lab example to learn the basics). "
            "Use 'hospital' for a comprehensive reference of all SDL features."
        ),
    )
    def sdl_get_example(
        name: str,
    ) -> str:
        key = name.lower().strip()
        if key in ("hospital", "hospital-ransomware", "ransomware"):
            return _read_example("hospital-ransomware-surgery-day.sdl.yaml")
        if key in ("satcom", "satellite", "supply-chain", "release-poisoning"):
            return _read_example("satcom-release-poisoning.sdl.yaml")
        if key in ("port", "port-authority", "ot", "surge"):
            return _read_example("port-authority-surge-response.sdl.yaml")
        if key in ("minimal", "simple", "small", "pentest", "lab"):
            return _MINIMAL_EXAMPLE
        return f"Unknown example '{name}'. Available: 'hospital', 'satcom', 'port', 'minimal'"

    @mcp.tool(
        name="sdl_parser_reference",
        description=(
            "Get documentation about SDL parser behavior: key normalization "
            "(case-insensitive fields), shorthand expansion rules, the variable "
            "system (${var} syntax), OCR duration grammar (e.g. '1h 30min'), "
            "and the parse/validate pipeline stages."
        ),
    )
    def sdl_parser_reference() -> str:
        return _read_doc("parser.md")

    @mcp.tool(
        name="sdl_validation_reference",
        description=(
            "Get documentation about SDL semantic validation: the aggregated "
            "validation passes, cross-reference resolution rules, error "
            "reporting, advisories, and how ambiguous references are handled."
        ),
    )
    def sdl_validation_reference() -> str:
        return _read_doc("validation.md")


# ---------------------------------------------------------------------------
# Static content
# ---------------------------------------------------------------------------

_MINIMAL_EXAMPLE = """\
# Minimal SDL Example: Pentest Lab
# This demonstrates the core SDL structure with a small, self-contained scenario.

name: simple-pentest-lab
description: Web app with SQL injection targeting a database

# --- Topology: nodes define compute resources and network switches ---
nodes:
  lab-net:
    type: Switch                         # pure connectivity, no OS/resources
    description: Lab network

  webapp:
    type: compute
    os: linux
    resources: {ram: 2 GiB, cpu: 1}      # human-readable RAM
    features: [flask-app]                 # list shorthand for feature bindings
    services:
      - {port: 8080, name: http}          # exposed network service

  database:
    type: compute
    os: linux
    resources: {ram: 1 GiB, cpu: 1}
    features: [postgres]
    services:
      - {port: 5432, name: postgresql}
    asset_value:
      confidentiality: high               # CIA triad classification

# --- Deployment: how many of each, which networks, IPs ---
infrastructure:
  lab-net:
    count: 1
    properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}
  webapp:
    count: 1
    links: [lab-net]                       # connected to lab-net switch
  database:
    count: 1
    links: [lab-net]

# --- Software deployed onto compute nodes ---
features:
  flask-app: {type: Service, source: vulnerable-flask-app}
  postgres: {type: Service, source: postgresql-16}

# External weakness assertions use standalone concept bindings.

# --- Typed edges between elements ---
relationships:
  app-to-db:
    type: connects_to                      # authenticates_with, trusts, federates_with,
    source: flask-app                      #   connects_to, depends_on, manages, replicates_to
    target: postgres
    properties: {protocol: tcp, port: "5432"}

# --- User accounts ---
accounts:
  db-admin:
    username: admin
    node: database                         # must reference a compute node
    password_strength: weak                # weak, medium, strong, none

# --- Health checks ---
conditions:
  web-alive:
    proposition: web-available
    command: "curl -sf http://localhost:8080/ || exit 1"
    interval: 15

propositions:
  web-available:
    description: The web service reports its availability as healthy.
    subjects: [nodes.web.services.http]
    basis: declared_state
    predicate:
      kind: presence
      property: service
      semantic_ref: urn:raes:declared-property:service
      operator: exists

assertions:
  web-alive:
    proposition: web-available
    role: postcondition

# --- Teams / people ---
entities:
  blue-team:
    name: Blue Team
    role: Blue                             # Blue, Red, White, Green
  red-team:
    name: Red Team
    role: Red

# Objective success references assertions over typed propositions per ADR-079.
# Graded scoring/reward lives in the experiment/evaluator plane, not the SDL.
objectives:
  keep-web-alive:
    description: Keep the web application available
    entity: blue-team
    success:
      assertions: [web-alive]

# --- Parameterization (${var} syntax, resolved at instantiation, not parse time) ---
variables:
  lab_cidr:
    type: string
    default: "10.0.0.0/24"
    description: Lab network CIDR block
"""

_OVERVIEW_TEXT = """\
# RAES Scenario Description Language (SDL) Overview

## What is the SDL?

Reproducible Agentic Environments System (RAES) supports agentic environments \
across non-exhaustive application areas. RAES SDL is the **YAML-based, \
backend-agnostic authored scenario language** within that system. It defines \
what authored scenarios mean — not how to deploy them. Backend implementations \
produce realized environments through runtime contracts.

Its topology and exercise-narrative core descends from the Open Cyber Range
(OCR) SDL. RAES adds composition, participant, evidence, objective, workflow,
and runtime-inventory semantics; the exact live surface is governed by the
normative section catalog rather than a historical count.

## Authoring Sections

A scenario is a YAML document with a required `name`, optional metadata and
composition fields, and optional authoring sections organized by concern.

### Topology and Software
| Section | Purpose |
|---------|---------|
| `nodes` | Compute nodes and network switches — the compute/network topology |
| `infrastructure` | Deployment: counts, links, dependencies, IPs, CIDRs, ACLs |
| `features` | Software (Service/Configuration/Artifact) deployed to compute nodes |
| `conditions` | Health checks (command+interval or library source) |

Per ADR-073 the OCR scoring pipeline (`metrics` / `evaluations` / `tlos` / \
`goals`) and `agents.reward_calculator` were removed from the SDL. Objective \
success references observable state (`conditions`); graded scoring, reward, and \
evaluation outputs live in the experiment/evaluator plane (ADR-055/064/069).

### Exercise Orchestration
| Section | Purpose |
|---------|---------|
| `entities` | Teams, organizations, people (recursive hierarchy) |
| `injects` | Actions between entities |
| `events` | Triggered actions combining conditions + injects |
| `scripts` | Timed event sequences with human-readable durations |
| `stories` | Top-level orchestration grouping scripts |

### Extended Scenario and Experiment Semantics
| Section | Purpose |
|---------|---------|
| `content` | Data placed into systems (files, datasets, emails) |
| `accounts` | User accounts on nodes |
| `relationships` | Typed directed edges (auth, trust, federation, etc.) |
| `forwarding_agents` | Scenario-level logical forwarding and shipping agents |
| `agents` | Autonomous participants with actions/knowledge/scope |
| `action_contracts` | Participant action applicability, effects, failures, and interactions |
| `observation_boundaries` | Participant information projections and visibility changes |
| `outcome_interpretation_rules` | Interpretation of action observations and local outcomes |
| `behavior_specifications` | Versioned bindings across participant behavior surfaces |
| `evidence_requirements` | Authored capture obligations, distinct from captured evidence |
| `objectives` | Declarative tasks: actor + targets + success + window |
| `workflows` | Branching/parallel control graphs over objectives |
| `variables` | Parameterization via `${var_name}` syntax |

### Top-level Composition Fields
- `name` (required), `version`, `description`
- `module` — publishable module descriptor
- `imports` — module imports (`local:`, `oci:`, `locked:`)

## Key Concepts

### Variables
- `${var_name}` placeholders in field values (NOT in mapping keys)
- Preserved as literal strings during parsing; resolved at instantiation
- Types: string, integer, boolean, number
- Can have defaults, allowed_values, required flag

### Shorthand Expansion
The parser auto-expands common patterns:
- `source: "pkg"` → `{name: "pkg", version: "*"}`
- `infrastructure: {node: 3}` → `{node: {count: 3}}`
- `roles: {admin: "user"}` → `{admin: {username: "user"}}`
- `features: [nginx, php]` → `{nginx: "", php: ""}`

### Key Normalization
- Recognized legacy field spellings are migrated to canonical lowercase
  `snake_case` with source diagnostics; canonical authoring uses those names
- User-defined names (node names, feature names, etc.) are preserved as-is

### Cross-Reference System
- Named elements can be referenced by bare name when unambiguous: `webapp`
- Qualified refs when disambiguation needed: `nodes.webapp`, `features.nginx`
- Nested entities use dot-notation: `blue-team.alice`
- Named services: `nodes.<node>.services.<service_name>`
- Named ACLs: `infrastructure.<infra>.acls.<acl_name>`

### Validation Pipeline
1. Bounded YAML parsing with duplicate-key checks
2. Explicit migration to canonical field spelling
3. Shorthand expansion
4. Pydantic structural validation
5. Aggregated semantic validation (cross-references, cycles, IP/CIDR, etc.)
All errors collected before reporting — authors see every issue at once.

### Duration Grammar
Script/event times accept: `1h 30min`, `2 days`, `1m+30`, `500ms`
Units: y, mon, w, d, h, m/min, s/sec, ms, us, ns

## Quick Example

```yaml
name: simple-lab
description: Basic web app scenario

nodes:
  net: {type: Switch}
  web: {type: compute, os: linux, resources: {ram: 2 GiB, cpu: 1}, features: [app]}
  db:  {type: compute, os: linux, resources: {ram: 1 GiB, cpu: 1}, features: [postgres]}

infrastructure:
  net: {count: 1, properties: {cidr: 10.0.0.0/24}}
  web: {count: 1, links: [net]}
  db:  {count: 1, links: [net]}

features:
  app:      {type: Service, source: flask-app}
  postgres: {type: Service, source: postgresql-16}

relationships:
  app-to-db: {type: connects_to, source: app, target: postgres}
```

## Python API

```python
from raes import parse_sdl, parse_sdl_file, instantiate_scenario

# Parse from string or file
scenario = parse_sdl(yaml_string)
scenario = parse_sdl_file(Path("scenario.yaml"))

# Structural only (skip cross-reference checks)
scenario = parse_sdl(yaml_string, skip_semantic_validation=True)

# Instantiate with concrete variable values
concrete = instantiate_scenario(scenario, parameters={"domain": "corp.local"})

# Check non-fatal advisories
for advisory in scenario.advisories:
    print(advisory)
```

## Error Types
- `SDLParseError` — YAML syntax or structural issues
- `SDLValidationError` — semantic issues (has `.errors` list with ALL issues)
- `SDLInstantiationError` — variable binding failures

Use `sdl_section_reference` for details, `sdl_get_example` for scenarios, and
`sdl_validate` to validate SDL YAML.
"""
