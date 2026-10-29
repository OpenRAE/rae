# Current control documentation design

Issue #1019 documents existing behavior and its evidence limits.
The [preflight](issue-1019-control-documentation-preflight.md) supplies the binding boundaries.
This design changes no runtime, contract, profile, or requirement status.

## Architecture and document ownership

The current reference connects four existing paths: reusable control, modular evaluation, world injects, and mixed execution.
Each path retains its own contract and installed owner.
The reference gives common terminology and a support table.
The migration guide connects the existing conversion and reader rules.
The examples select existing executable tests and the mixed demonstration collector.
They introduce no runner, provider, or support registry.

`specs/` defines semantics. `contracts/` defines wire formats and profiles.
Runtime code and test observations establish current support.
Public guides link to those authorities without embedding internal documents into the site.
Accepted ADRs, historical reports, and published captures retain their original interpretation.
The reusable-control specification's old implementation note is identified as a publication-time statement in current guidance.
Its normative relation remains unchanged.

The extension boundary remains `RuntimeTarget`, typed installed bindings, and existing conformance harness inputs.
A new implementation must supply its own admitted support and evidence.
Separate passing paths do not establish support for their combination.

## Data flow and trust boundaries

```text
Author / operator
  | authored SDL, exact request, authenticated identity
  v
[Caller boundary]
  Parser / compiler ---- admitted plan ----> Plan store
  Runtime admission <--- pins and policy --- Trusted resolver
  | exact-cut request, required coverage, authorized projection
  v
[Installed-provider boundary]
  Control provider ---- typed result -----> Atomic evaluation / operation store
  |                                        |
  | no world-effect authority               | committed one-use invocation
  |                                        v
  |                                  Backend effect owner
  |                                        | outcome and state readback
  +----------------------------------------v
                                   Retained evidence store
                                          | exact successful result join
                                          v
[Participant disclosure boundary]
  Final-sink policy ---- governed carrier --> Participant interface
  Independent observer --- observed fact --> Retained evidence store
```

This diagram shows ownership and data movement, not an automatic execution sequence.
World injects need no participant. A participant delivery requires a separate admitted join.
Mixed execution installs separate bridge, time, delivery, and observation services.
Their authenticated stage reports retain the distinction between execution, delivery, and observation.

## Systems security

| Asset and threat | Boundary and control | Verification |
| --- | --- | --- |
| Controller authority; a stale request repeats a transition | Exact policy, episode, revision, order, and grant checks at runtime admission | Reusable-control cycle, stale contender, and exact-retry tests |
| World state; recovery repeats an uncertain effect | Atomic claim and one-use dispatch at the backend boundary | Inject crash/reopen and readback tests |
| Participant information; world read access becomes disclosure | Separate audience authority and final-sink policy | Directed-delivery tests retain zero observation without evidence |
| Required decisions; optional failures hide missing obligations | Profile-owned coverage and required dependency closure | Existing modular-control conformance tests |
| Assurance integrity; test evidence becomes a native claim | Existing report validators and explicit evidence limits | Mixed demonstration and opacity evidence checks |
| Local evidence; examples leak credentials or overwrite records | Credential-free fixtures and collector refusal of existing output directories | Existing demonstration output and reuse tests |

Tests exercise RAE through controlled providers.
They cannot prove a downstream provider's truthfulness or operational independence.
Runtime-mediated opacity remains bounded by its selected profile.
Neither documentation nor a passing harness establishes backend equivalence or simulation-to-operation transfer.

## Policy, architecture, and records

Existing file-local repository policy, public-document checks, and Vale apply.
Existing contract, configuration, authorization, and report validators remain the executable architecture checks.
No policy or architecture enforcement changes are necessary because this delivery introduces no runtime behavior.
ADR-009/061, ADR-095/102/104/108/110/111/112/113/115 already cover these boundaries.
No new architectural decision is necessary.
Requirement records are interpreted within their stated clauses and evidence.
ASR-537 remains DRAFT; the narrower #1018 test demonstration does not complete its research protocol.

## Reference and writing review

The design uses these official references:

- [pytest invocation](https://docs.pytest.org/en/stable/how-to/usage.html), pytest 9, test selection: existing case-specific commands.
- [NIST SP 800-160 Volume 1 Revision 1](https://csrc.nist.gov/pubs/sp/800/160/v1/r1/final), November 2022: assets, boundaries, controls, and verification.
- [ASD-STE100 Issue 9](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf), January 2025, sections 1, 5, and 6: terminology, instructions, and descriptions.

The official STE text was available in a local copy when its web endpoint refused access.
The review checks consistent technical names, short sentences, one instruction per sentence, and one topic per paragraph.
Architecture describes ownership. Migration gives adoption steps. Examples state inputs, commands, expected results, and limits.
