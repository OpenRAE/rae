# ADR-001: Scenario Description Language (SDL)

**Status:** Accepted
**Date:** 2026-03-29
**Deciders:** Brad Edwards

## Context

The SDL needed a formal specification language with a documented grammar,
parser, and semantic validation. Research across cybersecurity SDLs, adjacent
DSLs, security
standards, and agent-evaluation frameworks identified the Open Cyber Range
(OCR) SDL as the closest existing precedent.

The OCR SDL is a YAML-based language with 14 sections (nodes, infrastructure, features, conditions, vulnerabilities, metrics/evaluations/TLOs/goals, entities, injects/events/scripts/stories) parsed by a Rust library. It separates logical topology from physical deployment and includes a full scoring pipeline and exercise orchestration model.

However, the OCR SDL lacks: data/content modeling, user accounts, network access controls, OS classification, asset values, service exposure, platform-targeted commands, relationships between services (authentication, trust, federation), agent specifications, and parameterization.

## Decision

Use the OCR SDL as the starting surface for `aces.core.sdl`, preserve coverage across the OCR-derived sections, extend that base with 7 new sections adapted from existing systems (not invented), and decouple the language from any specific deployment backend.

### Architecture

The SDL is a **specification language**, not a deployment tool. It describes
*what a scenario is*. Backend implementations translate SDL specifications into
concrete infrastructure and execution behavior.

That boundary also applies to other apparatus surfaces. The SDL may describe
participants, experiment intent, observability systems, and authored evidence
requirements, but it does not make concrete participant implementations,
processor choices, or backend realization details part of scenario meaning by
default.

### Sections (21 total)

14 OCR-derived base sections + 7 new:
- `content` (from CyRIS) — data placed into systems
- `accounts` (from CyRIS) — user accounts within nodes
- `relationships` (from STIX SRO) — typed edges between elements
- `agents` (from CybORG) — autonomous participants
- `objectives` (from OCR scoring + CACAO workflow context) — declarative experiment semantics
- `workflows` (from CACAO workflow patterns) — branching and parallel objective composition
- `variables` (from CACAO) — parameterization

### Identity Model

Identity is not a separate section. It emerges from the combination of:
- **Accounts** — who exists where (username, groups, SPN, password strength)
- **Features** — what provides authentication (AD, LDAP, RADIUS services)
- **Relationships** — how services connect (`authenticates_with`, `trusts`, `federates_with`)

This is simpler and more composable than a dedicated identity layer.

### Validation

Two-phase validation:
1. **Structural** (Pydantic) — types, ranges, required fields, intra-model constraints
2. **Semantic** (SemanticValidator) — 22 named passes checking cross-references, dependency cycles, IP/CIDR consistency, typed VM/network references, OCR count constraints, workflow graph integrity, and SDL domain rules

The validator collects all errors rather than failing on the first.

### Parser

The parser handles:
- Case-insensitive field keys (preserving user-defined names)
- Shorthand expansion (source strings, infrastructure counts, role strings, min-score integers, feature lists)
- SDL-only parsing with clean rejection of non-SDL `metadata` scenarios
- Clean error messages for all failure modes

### Format Boundary

None by design. The repository accepts SDL documents only:
- non-SDL metadata/mode-based scenario YAMLs do not parse through the SDL
- the SDL loader remains intentionally thin rather than acting as a
  generic scenario-ingestion layer
- non-SDL scenario/runtime entrypoints are outside this repository's scope

## Consequences

### Positive

- **19 real-world scenarios validated** from 8 platforms (OCR, CybORG, CALDERA, Atomic Red Team, CyRIS, KYPO, HTB, Locked Shields)
- **1,050+ fuzz test inputs** with zero unhandled crashes
- Every SDL element traces to a published precedent
- Backend-agnostic: no Docker, OpenStack, or cloud provider coupling
- The OCR-derived coverage gaps identified in review were closed: entity facts
  and orchestration time grammar now align with the verified OCR surface
- One clear specification surface for backend/runtime work
- One clear authored surface that can stay distinct from processor, backend,
  and participant-implementation apparatus

### Negative

- 21 source files in `aces.core.sdl/` — significant surface area
- Variables (`${var}`) are still unresolved at parse time; concrete binding now happens in the repo-owned instantiation phase before compilation/runtime planning
- Non-SDL scenario YAMLs require migration to SDL format
- No module composition system yet (Terraform-style imports)
- No formal verification (VSDL's SMT / CRACK's Datalog)
- Agent/participant authoring remains thinner than the broader participant
  architecture now recognized by the ecosystem requirements

### Risks

- The SDL has so far been designed and tested within one primary implementation ecosystem. Practitioner feedback may reveal ergonomic issues or missing concepts
- The relationship model uses a flat `properties` dict which could become a maintenance burden as relationship types proliferate
- Variable resolution semantics are now repo-defined, but composition/import semantics still need a mature multi-file design
- If the repository fails to keep authored participant intent distinct from
  participant implementation and runtime apparatus, future agent-support work
  could leak execution-stack concerns back into the SDL surface

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-07-11 | #721 | Replaced the original implicit case-insensitive parser convention with the normative `sdl-yaml/v1` source profile: YAML 1.2.2 Core resolution, exact `snake_case` structural fields, strict default rejection, and explicit diagnosed migration for legacy case/kebab spellings and disjoint `<<` merges. Distinguished raw YAML from the normalized authoring-object schema and added the `aces-sdl-semantic/v1` RFC 8785 identity profile. The accepted body above remains the historical 2026-03-29 decision; its parser-spelling statements are not the current syntax contract. |
| 2026-09-09 | #989 | Externalize classification coverage through the portable external concept bindings from #986 (DSL-114). This replaces the original requirement to preserve a native vulnerability section and domain-shaped classification associations; it does not remove native feature, condition, proposition, dependency, or transition semantics. Weakness, purpose, role, and family labels are digest-bound authored assertions with explicit perspective, relationship, provenance, and loss, not intrinsic environment facts or capability/realization evidence. Retired nonempty fields require explicit loss-aware migration; exact empty serializer defaults remain compatible at the versioned instantiated-snapshot boundary. Participant knowledge uses ordinary content and disclosure controls. The normative inventory and migration contract are in specs/concept-authority/classification-migration.md; the original section count above is historical, not a requirement to retain classification fields. |
