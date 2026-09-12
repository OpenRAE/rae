# ADR-101: Adversarial Participant Boundary Flow Control

## Status

accepted

ADR-108 amends the scope as recorded below. The security profile and historical
records retain their published meaning.

## Date

2026-07-30

## Classification

Classification: FM3

Required artifacts: a revisioned threat model, independent confidentiality and
integrity coordinates, conservative derivation rules, distinct release and
authority operations, an exact final-sink boundary, a revisioned
intentional-subversion evaluation profile, worked attacks, DRAFT Ground Control
ownership, and dependency-ordered implementation work.

Waivers: issue #812 is design authority. It does not publish portable wire
contracts, change runtime or backend behavior, run an adversarial evaluation,
or establish robustness against intentional subversion.

## Context

ADR-085 and SEM-230 define participant-relative information flow, exact-cut
policy decisions, declassification, memory, adaptive strategies, and explicit
noninterference boundaries. ADR-095 separates decision, state cut, projection,
delivery, and observation. ACT-617 and API-409 distinguish direction,
intervention, handoff, override, cancellation, admission, and execution.
API-423 and RUN-319 provide typed crossing occurrences and fail-closed reference
mediation. API-407 owns declared and effective backend capability strength.
ASR-535 owns bounded participant-flow evidence and overclaim prevention.

Those authorities do not yet carry independent confidentiality and
source-integrity coordinates from every observation or tool result through
participant context, retained memory, proposals, action arguments, handoffs,
outputs, and final sinks. A structurally valid and otherwise authorized action
can still have been redirected by untrusted content. Two individually
permitted operations can compose into confidential exfiltration. A valid
handoff can launder apparent authority. A monitor can be evaded by an attacker
that observes prior decisions.

Research systems provide useful but apparatus-specific responses:

- FIDES tracks confidentiality and integrity and applies deterministic
  information-flow policy to agent actions.
- CaMeL separates trusted control from untrusted data with quarantined
  processing and capability restrictions.
- SAMOS retains session flow context and intercepts MCP tool calls.
- AgentDojo evaluates utility and security under indirect injection and
  adaptive attacks.
- AI Control and ControlArena model intentionally subverting policies, trusted
  and untrusted model roles, audits, editing, deferral, and shutdown.
- runtime shielding mediates a formally declared property before output.
- capability systems make designation and least authority explicit.

RAES must adopt the general boundary lessons without becoming an LLM framework
or confusing a benchmark, gateway, monitor, model role, or prompt convention
with participant-neutral authority.

## Decision

### 1. Add two DRAFT owners

SEM-233, **Adversarial Participant Boundary Information-Flow Control**,
owns the portable explicit-flow and final-sink semantics. ASR-536,
**Intentional-Subversion Participant Control Evaluation**, owns the
experimental protocol and evidence surface.

Both remain DRAFT. Issue #812 defines their boundary and child program; it does
not satisfy their positive runtime or evaluation obligations.

### 2. Keep confidentiality and integrity independent

The flow-policy profile has two independent coordinates:

- confidentiality limits permitted audiences, principals, destinations, and
  sink classes; and
- integrity records origins and possible writers that may have influenced a
  value and the minimum trust required by a sink.

The profile defines ordering, conservative join, trusted-source declarations,
source defaults, release authorities, sink requirements, memory scope, and
unknown behavior. A single `trusted`, `safe`, secret, sensitivity, confidence,
role, marking, signature, hash, or monitor-score field cannot replace both
coordinates.

Opaque transformations retain the join of every input that could have
influenced the result. External sources default to confidential and untrusted
unless a revisioned resolver establishes narrower labels. Missing labels,
missing provenance, unknown profile revisions, ambiguous joins, and
unsupported propagation deny or produce an explicit unsupported result.

Historical labels and provenance are immutable.

### 3. Keep authority operations distinct

Authentication identifies a principal. Authorization permits an operation.
Admission validates a candidate fact or action. Approval records a control
decision. Declassification relaxes confidentiality. Integrity endorsement
raises the admitted origin-trust coordinate. Redaction and transformation
derive new values. Trusted editing creates a new proposal. Handoff changes
control. Interruption and shutdown change lifecycle.

None implies another. Declassification and endorsement name the exact source,
result, affected coordinate, destination or sink, authority, profile revision,
state cut, and evidence. They create a fresh derived identity and never mutate
history. Trusted editing inherits provenance and effective labels, then
re-enters ordinary validation, policy, capability, and action admission.

### 4. Propagate through existing typed carriers

The relation follows this path:

```text
observation, retrieval, tool result, or runtime fact
  -> participant context and retained memory
  -> proposal, output, transformation, and action arguments
  -> API-409 control or handoff and API-423 crossing
  -> participant-facing or external sink
```

The implementation reuses runtime facts, participant action admission,
API-409, API-423, runtime snapshots, experiment records, and typed refs. It
must not add an open `taint`, `security_labels`, `agent_message`, `context`,
`monitor_metadata`, or policy map, or a parallel action, crossing, handoff,
evidence, audit, trajectory, error, or persistence hierarchy.

Controller change, participant change, shared state, handoff, or episode reset
does not erase provenance or labels. Cross-episode replay names the SEM-230
memory scope and retains profile and policy revisions.

### 5. Enforce at the last RAES-controlled boundary

The final enforceable boundary is:

- after the last policy, authority, capability, destination, and state-cut
  resolution but immediately before `RuntimeTarget` or a backend performs an
  external action; and
- immediately before participant-facing or external data is serialized,
  streamed, delivered, written, returned in an error, or otherwise disclosed.

The runtime commits the decision through the existing atomic participant
transition before the effect. Missing labels or provenance, stale state,
unsupported capability, denial, history-head conflict, or failed commit causes
no backend call and no disclosure.

Planning validation, schema validation, action admission, proposal approval,
monitoring, gateway interception, and request construction are necessary
defense layers but not the final sink.

### 6. Separate deterministic policy from monitors and protocols

Deterministic policy and effective capability support decide authorization and
release. A heuristic monitor emits evidence or advice with revision,
visibility, provenance, limitations, and confidence. A monitor score never
authorizes an action, and missing monitor output never widens permission.

Human and trusted-system interventions state whether they authorize,
declassify, endorse, edit, defer, hand off, interrupt, shut down, or merely
advise. Multiple effects are independently named and authorized.

Trusted and untrusted monitors are evaluation roles, not intrinsic properties.
Profiles declare topology, inputs, visibility, policy knowledge, independence
or correlation assumptions, collusion channels, and failure behavior.
Different ids do not imply independence.

### 7. Add an intentional-subversion evaluation profile

ASR-536 profiles bind:

- honest or attack mode, main objective, side objective, and success
  conditions;
- participant capabilities and apparatus;
- policy, monitor, threshold, audit-budget, and prior-outcome knowledge;
- adaptive strategy over approvals, denials, edits, deferrals, audits,
  handoffs, interruptions, outputs, ordering, and declared timing facts;
- monitor identities, roles, topology, correlation, visibility, and failures;
- audit budget, selection rule, approval, trusted editing, defer-to-trusted,
  interruption, and shutdown protocol;
- cross-participant and cross-episode memory, replay, and policy revision; and
- separate safety, usefulness, attack success, audit cost, intervention cost,
  uncertainty, limitations, and nonclaims.

The profile reuses existing experiment task, protocol, study, run, apparatus,
factor, evidence, measure, traceability, and behavioral claim contracts. Until
a trajectory authority exists, replay uses a digest-bound graph of existing
episode, behavior, control, crossing, action/result, and evidence refs.

Ordinary negative tests, injection examples, monitor accuracy, and green
benchmarks are bounded falsification evidence. They do not establish
intentional-subversion robustness.

### 8. Keep portable semantics participant-neutral

Labels, derivations, authorities, capabilities, policy cuts, sinks, decisions,
provenance, and evidence apply to human, scripted, reinforcement-learning,
large-language-model, and external-service participants.

Prompt separation, privileged or quarantined models, model topology, MCP
gateways, tokenizers, credentials, private state, and chain-of-thought are
apparatus details. Apparatus contracts may declare bounded support, but those
details do not enter portable participant records.

### 9. Require boundary-faithful attacks

Downstream evidence covers:

1. prompt or tool-result injection;
2. confidential exfiltration through actions, outputs, arguments, errors, or a
   colluding participant;
3. adaptive monitor evasion under declared feedback and audit budgets; and
4. control-handoff manipulation.

Every case drives the real `RuntimeControlPlane` to `RuntimeTarget` boundary,
checks the semantic decision, counts external calls, checks participant-visible
output, append-only histories, safe audit/error evidence, and replay. A denied
case has zero prohibited external effects.

### 10. Allocate bounded child work

- #1001 publishes semantic authority.
- #1002 publishes portable contracts after #1001.
- #1003 implements final-sink runtime enforcement after #1002.
- #1004 implements apparatus and backend capability support after #1002.
- #1007 implements adversarial evaluation after #1001 and #1002.
- #1008 publishes evidenced claims after #1003, #1004, and #1007.

## Consequences

RAES gains a participant-neutral security boundary that can represent
adversarial influence and confidential composition without requiring an LLM,
MCP, or monitor framework. Runtime and evaluation claims remain honest because
the design separates authority, implementation, backend realization, and
evidence.

The cost is a cross-cutting profile and resolver relation that later work must
bind across semantics, contracts, runtime, stores, backends, apparatuses,
experiments, and documentation. Conservative propagation can reject useful
operations until a governed transformation or release exists.

## Non-Goals

- Solving model alignment or proving internal reasoning safe.
- Recording chain-of-thought, private model state, prompts, or credentials.
- Replacing participant-neutral contracts with LLM chat or tool formats.
- Treating a monitor, human, gateway, model, or backend as trusted by default.
- A general-purpose taint engine, policy language, agent framework, gateway,
  monitor service, trajectory store, or message bus.
- Protection from undeclared timing, storage, model-steganographic, or other
  covert channels.
- Positive runtime, backend, shielding, or intentional-subversion claims from
  this ADR alone.

## Modular participant-control scope amendment

[ADR-108](adr-108-modular-participant-control-and-governed-effects.md) places
this security profile within a broader experimental and organizational
participant-control architecture. SEM-233 and `sem-233/rev1` retain independent
confidentiality/integrity coordinates, conservative propagation, exact-sink
policy and explicit releases. Known in-world adversarial influence can be
intentionally admitted by a sink policy and tracked without endorsement;
unknown or missing flow authority retains the existing failure behavior.

The general-purpose taint-engine/policy-language non-goal is preserved for the
RAES runtime and portable executable surface. SEM-235 adds revisioned IFC
domains and mechanism-composition semantics; independently chosen backend
engines realize them behind a closed protocol. Labels and monitor results may
request governed typed effects, including injects, only through independently
authorized rules and ordinary downstream admission. They execute no hidden
code and do not widen authority.

Only attacks within the admitted world are participant occurrences here.
Integrity and containment outside it remain backend/provider responsibilities;
interference there fails or invalidates realization. A live environment can
belong to the world when explicitly admitted. The DRAFT statements in this
ADR describe the original #812 design cut; later requirement fulfillment and
evidence records retain their own dates and scope.

## Amendments

| Date | Commit/PR | Summary |
| --- | --- | --- |
| 2026-09-06 | #1068 | Clarify modular composition, governed effects and the declared-world boundary under ADR-108 while preserving the security profile and runtime interpreter non-goal. |

## References

- [SEM-233 and ASR-536 formal authority](../../../specs/formal/participant-semantics/adversarial-flow-control.md)
- [Issue #812 research record](../../research/adversarial-participant-control/)
- [FIDES](https://arxiv.org/abs/2505.23643)
- [CaMeL](https://arxiv.org/abs/2503.18813)
- [SAMOS](https://research.ibm.com/publications/securing-mcp-based-agent-workflows)
- [AgentDojo](https://proceedings.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html)
- [AI Control](https://arxiv.org/abs/2312.06942)
- [ControlArena](https://control-arena.aisi.org.uk/)
- [Shield Synthesis](https://arxiv.org/abs/1501.02573)
- [Capability-based authority control](https://doi.org/10.4230/LIPIcs.ECOOP.2017.20)
