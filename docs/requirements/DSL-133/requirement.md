---
id: DSL-133
title: "Platform Application Runtime Inventory"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-05-30T06:20:53.857422Z
updated_at: 2026-07-29T05:02:32.568799Z
---

# DSL-133 — Platform Application Runtime Inventory

## Statement

The language shall represent participant-visible platform-application logical runtime state as typed node-scoped inventory with stable application identity and zero or more composable, provider-neutral functional capabilities. Capabilities shall cover threat-intelligence management, intelligence exchange, case management, analysis execution, workflow automation, and analytics presentation without treating product identity or category as proof of configured content, bindings, distribution policy, execution, or completeness. Application capabilities and their stable identifiers shall be independently targetable, while transport services, application authorization, initial content and service materialization, integration bindings, policy, and evidence remain owned by their existing semantic surfaces. Legacy platform categories and bounded content-object manifests may remain accepted for compatibility but shall not drive capability inference or required-profile validation.

## Rationale

The original SCN-010 design generalized directly from MISP, TheHive, Cortex, Shuffle, and dashboard examples. Its single platform-kind discriminator coupled product classification to required product-shaped content profiles, admitted dummy manifests as supposed completeness, rejected legitimate default deployments, and could not represent multi-role applications such as OpenCTI. Provider-neutral composable capabilities follow the existing ADR-032 identity-authority precedent and adjacent TOSCA/CAMP, STIX/TAXII, and CACAO separations while preserving the established runtime, authorization, content, binding, and evidence ownership boundaries.

## Traceability

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_secret_service.py` (Application-owned secret metadata and version state)

- TESTS → TEST `implementations/python/tests/test_runtime_platform_application.py` (test_runtime_platform_application.py)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_platform_application.py` (Runtime platform application model)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_platform_application_content.py` (Runtime platform application capability model)
- IMPLEMENTS → SPEC `specs/sdl/runtime-inventory.md` (SDL runtime inventory specification)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_platform_application_vocab.py` (Runtime platform application capability vocabulary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_runtime_service_family_registry.py` (Runtime service family reference registry)
- IMPLEMENTS → GITHUB_ISSUE `956` (Issue #956)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-049-platform-application-runtime-inventory.md` (ADR-049 Platform Application Runtime Inventory)
