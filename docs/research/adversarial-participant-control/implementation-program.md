# Adversarial Participant Control Implementation Program

Date: 2026-07-30

Parent issue: [#812](https://github.com/OpenRAE/rae/issues/812)

Milestone: `Participant Information-Flow & Behavioral Equivalence`

The machine-readable authority is
[`implementation-program.json`](implementation-program.json).

## Definition delivered by issue 812

Issue #812 delivers ADR-101, the primary-source gap assessment, revisioned
threat model, SEM-233 flow-policy profile, ASR-536 control-evaluation profile,
four worked attack designs, two canonical DRAFT requirements, and the ordered
program.

It does not publish wire contracts, change runtime enforcement, prove backend
realization, run the attack cases, or establish intentional-subversion
robustness.

## Dependency graph

```text
#1001 semantic authority
   |
   v
#1002 portable contracts
   | \                 \
   |  v                 v
   | #1003 runtime      #1004 apparatus/backend
   |     \               /
   v      \             /
#1007 evaluation       /
       \              /
        +------------+
               |
               v
       #1008 evidenced docs
```

## Work packages

### #1001: Semantic authority

Publish the two-coordinate label algebra, conservative derivation, release
operations, final-sink relation, cross-participant/episode carriage, and
bounded falsification authority.

### #1002: Portable contracts

Publish closed label, derivation, release, sink-decision, and existing-carrier
binding contracts with contextual validation, fixtures, publication, and
generator parity.

### #1003: Runtime enforcement

Drive the real final boundary, commit before effect, and demonstrate zero
prohibited calls or disclosure for every denial, stale, unsupported, replay,
and persistence-conflict class.

### #1004: Apparatus and backend support

Declare quarantine, flow, monitor-topology, and sink-mediation capabilities;
resolve effective support deny-first; and publish bounded realization and
conformance evidence.

### #1007: Adversarial evaluation

Run honest and adaptive attack modes under declared knowledge, collusion,
monitor, audit, intervention, memory, and replay coordinates. Report safety,
usefulness, cost, uncertainty, limitations, and nonclaims separately.

### #1008: Documentation and claims

Issue #1008 amends this program on 2026-10-29.
After RAE runtime, fixture apparatus, and #1007 harness evidence are reconciled,
publish exact evaluated profiles, assurance limits, lineage, and public guidance.
Concrete backend realization is not a prerequisite for RAE evaluation or publication.
Backend claims require separate exact realization evidence from their owner.

## Program invariants

- Confidentiality and integrity stay independent.
- Unknown or missing flow state never becomes public or trusted.
- Declassification, endorsement, authorization, admission, approval,
  authentication, editing, and execution stay distinct.
- The final decision is committed immediately before effect or disclosure.
- A monitor score never authorizes an action.
- Honest and attack modes, knowledge, adaptation, collusion, audit, monitor
  correlation, and memory are explicit.
- Every denial case checks zero prohibited external effects.
- Human, scripted, RL, LLM, and external-service participants share portable
  semantics; apparatus internals remain capability declarations.
- Chain-of-thought, private model state, credentials, hidden objectives, and
  raw secrets remain outside portable evidence.
- Runtime, backend, intentional-subversion, alignment, monitor-trust, and
  covert-channel claims require separate exact evidence.
