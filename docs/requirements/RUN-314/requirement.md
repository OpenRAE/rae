---
id: RUN-314
title: "Reference Emulation Backend"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-04-05T01:46:39.033909Z
updated_at: 2026-10-21T00:00:00Z
---

# RUN-314 — Reference Emulation Backend

## Statement

The ecosystem shall provide a reference emulation backend that realizes scenarios against emulated infrastructure such as virtual machines, virtual networks, containers, or equivalent infrastructure surfaces while publishing manifest, conformance, and provenance data through the ecosystem's standard contracts.

## Rationale

The ecosystem needs at least one concrete infrastructure-backed backend so its portability claims are exercised against real realization surfaces rather than only abstract contracts, fixtures, or in-memory stand-ins.

## Traceability

- IMPLEMENTS → ADR `docs/decisions/adrs/adr-063-reference-emulation-backend.md` (ADR-063 Reference Emulation Backend; superseded by ADR-115)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-115-concrete-backends-owned-outside-raes.md` (ADR-115: concrete realization is owned by LilRAE outside RAES)
- DOCUMENTS → DOCUMENTATION `docs/migration/concrete-backends.md` (Migration from the bundled backends to LilRAE)
- DOCUMENTS → GITHUB_ISSUE `967` (Remove the bundled concrete backends after the LilRAE release)
- DOCUMENTS → GITHUB_ISSUE `197` (RUN-314 reference-emulation backend root)
- IMPLEMENTS → GITHUB_ISSUE `1094` (Deterministic and cache-safe libvirt boot artifacts)
- IMPLEMENTS → DOCUMENTATION `docs/decisions/issue-1094-libvirt-boot-artifact-reliability.md` (Boot-artifact reliability architecture)
- DOCUMENTS → GITHUB_ISSUE `1105` (Guest-certified service protocol binding)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1105-libvirt-guest-service-protocol.md` (TCP-only admission and evidence decision)
- IMPLEMENTS → GITHUB_ISSUE `1110` (Exact-SHA real-container release admission)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1110-required-container-release-gate.md` (Release evidence architecture and limitations)

- IMPLEMENTS → GITHUB_ISSUE `1367` (Opt-in concrete OCI inject entrypoint execution and independent readback)
