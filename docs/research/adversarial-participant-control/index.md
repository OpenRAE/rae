# Adversarial participant control and boundary flow

Issue [#812](https://github.com/OpenRAE/rae/issues/812) adopts the
participant-neutral lessons from information-flow security and AI-control
research without adding an LLM-agent framework.

The parent delivery defines the threat model, architecture, DRAFT authority,
and implementation program. Issues #1001 and #1002 now publish the SEM-233
semantic authority and portable contract boundary. They do not claim runtime
or backend enforcement or a successful adversarial evaluation.

- [Architecture preflight](../../decisions/issue-812-adversarial-agent-control-preflight.md)
- [Issue #1001 SEM-233 semantic-authority preflight](../../decisions/issue-1001-sem-233-boundary-flow-semantics-preflight.md)
- [Issue #1002 SEM-233 portable-contract preflight](../../decisions/issue-1002-sem-233-portable-flow-control-contracts-preflight.md)
- [Issue #1004 SEM-233 apparatus/backend capability preflight](../../decisions/issue-1004-adversarial-control-apparatus-backend-preflight.md)
- [ADR-101](../../decisions/adrs/adr-101-adversarial-participant-flow-control.md)
- [Current-state and primary-source assessment](current-state-assessment.md)
- [Threat model](threat-model.md)
- [Trust and flow architecture](trust-flow-architecture.md)
- [Worked attack cases](attack-cases.md)
- [Requirement disposition](requirement-disposition.md)
- [Implementation program](implementation-program.md)
- [Machine-readable program](implementation-program.json)
- [Formal authority](../../../specs/formal/participant-semantics/adversarial-flow-control.md)

The original #812 design cut recorded SEM-233 and ASR-536 as DRAFT.
The canonical requirement files now determine current status.
Issue #1008 separates backend-neutral RAE harness publication from concrete backend realization.
See the [executed evaluation guide](../../explain/reference/adversarial-control-evaluation.md)
for source-bound results, reproduction, separate measures, and explicit limits.
