---
id: DSL-136
title: "Forwarding Agent Runtime Inventory"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-05-30T06:21:09.850175Z
updated_at: 2026-09-13T00:00:00Z
---

# DSL-136 — Forwarding Agent Runtime Inventory

## Statement

The language shall represent log-forwarding and content-synchronization agent logical runtime state as typed node-scoped runtime inventory, including agent kind, tailed or pulled sources with parse format and selectors, transforms, ship targets with ingestion and enrollment endpoints and classified enrollment identity, buffering policy, reload/control channels, and bounded settings, allowing partial knowledge and composed pipelines without an agent-kind deployment recipe, with supplied references, bounds and redaction validated and necessary selected-operation completeness enforced at admission, without overloading SIEM manager agent rosters, detection-engine rule sources, filesystem or process evidence, raw agent configuration, or prose-only relationships.

## Rationale

APTL SCN-010 wazuh-sidecar-db (#343), wazuh-sidecar-suricata (#344), and misp-suricata-sync (#349) are agent-side shippers whose defining (source, transform, ship-target, buffer) tuple is the structurally co-equal agent half of the manager/agent split wazuh.manager earned a family for. SecurityMonitoringManager.agents is a manager-side roster; NetworkDetectionRuleSource.generated_by records the consumed source, not the producer co-process; filesystem/process/service_units only attest existence.

## Traceability

- TESTS → TEST `implementations/python/tests/test_runtime_forwarding_agent.py` (test_runtime_forwarding_agent.py)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-050-forwarding-agent-runtime-inventory.md` (ADR-050 Forwarding Agent Runtime Inventory)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_forwarding_agent.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_relationships.py`
- IMPLEMENTS → SPEC `specs/sdl/runtime-inventory.md` (Partial description and selected-operation boundary)
- IMPLEMENTS → GITHUB_ISSUE `1207` (Correct specimen-shaped completeness guards)
- TESTS → TEST `implementations/python/tests/test_issue_1207_partial_descriptions.py`
- TESTS → TEST `implementations/python/tests/test_issue_1207_profile_admission.py`
