# Participant-crossing reproduction

Requirements: SEM-232, ASR-535. Classification: FM3.

## Subject and evidence

The subject is the separately pinned finite machine-check capture.
Its profile is `participant-crossing-dpbb-finite-v1@rev2`.
The selected relation is `divergence-preserving-branching-bisimulation`.
The evidence boundary covers only the complete reachable carrier of this pinned finite profile.
Both models remain at rev2, with projection rev1 and taxonomy rev8.
The original result and its claim remain unchanged.

The formal package owns the reproduction controller and its measurement record.
The public interface is `reproduction.measure`.
`reproduction_checks` owns the fixed comparison inventory and native invocation inside the worker.
It uses `machine_check.load_retained` and `admit_bundle` for the expected subject.
The existing result formatter binds fresh decisions to the original claim.
The new driver does not call the producer replay inside another sandbox.
The existing exporter supplies complete model construction and counts.
The existing corpus supplies every mutation, calibration, control, and checked witness.
The existing native adapter owns tool admission, modes, and strict decision parsing.
The reproduction driver uses the same relation flags and ordered AUT bytes.
Its own command record names the declared comparison paths.
No second model or relation checker is needed.

The controller checks the expected bundle.
A separately selected digest fixes that subject.
It starts the reproduction driver in a fresh Python process.
The worker constructs actual bytes without reading the machine-check result directory.
Its own driver repeats the fixed comparisons through the admitted native executable.
The original model, corpus, witness, result, and admission interfaces remain unchanged.
Each output file must match exactly.
It records the expected and actual manifest, result, claim, and artifact digests.
It keeps every count and mutation outcome.
It keeps the command and original claim limits.
No candidate command or path controls execution.

Measurement does not authenticate a reviewer.
A separate review must name the record digest.
It must name the mutation review subject.
The review must name its reviewer.
It must state their role and separation from the original producer.
An implementation agent may perform that review.
The repository review authority owns that acceptance record.
A caller-supplied name, second CI job, or producer approval cannot replace it.
Missing acceptance leaves independent reproduction incomplete.
Unsigned evidence cannot satisfy a policy that requires authenticity.

The retained record is selected by `reproduction/pin.json`.
Its manifest binds exact measurement, execution, and review bytes.
The capture directory names the manifest digest.
The measurement retains its separate acceptance requirement.
The review names the current implementation-agent run and its acceptance comment.
It also binds the qualified run, source revision, parents, and artifact digest.
The earlier implementation-agent run remains the original producer.
No human review is claimed.
This immutable capture survives the hosted artifact retention period.

## Execution boundary and data flows

```mermaid
flowchart LR
  P[(Reviewed producer and corpus pins)] -->|Expected identities| A[Existing bundle admission]
  S[(Pinned sources and installed Python closure)] -->|Read-only code and dependencies| W[Fresh offline Python worker]
  S -->|Pinned model and mutation sources| I[Existing input constructors]
  I -->|Complete synthetic input pairs| D[(Read-only declared comparisons)]
  D -->|Mounted bytes checked against worker reconstruction| W
  T[(Admitted native tool)] -->|Verified archive and tree identity| W
  W -->|Synthetic model inputs| N[Admitted native checker within worker boundary]
  N -->|Bounded decisions and witnesses| W
  W -->|Fresh complete bundle| C[Exact byte comparison]
  A -->|Expected complete bundle| C
  C -->|Measured identities and claim limits| M[(Immutable measurement)]
  M -->|Exact digest and execution reference| R[Independent repository reviewer]
  R -->|Attributable acceptance| E[(Separate review record)]
```

The Python worker has a separate network namespace and a cleared environment.
Only declared source, dependency, and tool mounts are available.
The worker receives no home directory, Git credentials, result cache, or ambient import path.
Its temporary state and output directory are private and fresh.
The machine-check result directory is absent from the worker.
Python and the admitted native checker share this one sandbox boundary.
The checker also sees the copied public source and declared synthetic inputs.
It receives no original checkout, home data, credentials, or runtime authority.
This avoids nested namespaces, which the supported AppArmor policy can deny.
No host control is disabled, and no process gains privilege.
Source, tool, and prepared comparison inputs are read-only.
The worker rebuilds each comparison input before use.
Its bytes must match the mounted input pair.
The checker keeps its existing per-process limits and private bounded outputs.
Source stability is checked before and after execution.
An exclusive trusted writer remains necessary during setup.

The whole worker has a fixed deadline.
Its process group is killed and reaped on exit.
The native adapter retains its CPU, memory, output, and descriptor limits.
The worker permits no acquisition or unsandboxed fallback.
Acquisition and Python environment preparation occur before verification.
Missing inputs or isolation produce no completed decision.
A different valid result fails reproduction.
No partial measurement is published.

## Security and verification

| Threat and boundary | Control | Verification |
| --- | --- | --- |
| Substituted expected result | Caller-selected reviewed digest and existing admission | A candidate and replacement checksum cannot change the selected subject. |
| Reused result or stale workspace | Fresh worker, hidden producer results, private temporary state | Actual output must come from fresh construction and native comparisons. |
| Ambient network, imports, or credentials | Network namespace, fixed mounts, cleared environment | Synthetic environment and host-file sentinels remain inaccessible. |
| Source or tool substitution | Existing source, archive, executable, and complete-tree checks | Drift fails before publication. |
| Altered counts, hiding, mutations, or claim limits | Complete bundle comparison and existing validators | Each altered field or omitted case fails admission. |
| Unsafe artifact paths or diagnostics | Existing bounded readers and fixed output inventory | Links, excess bytes, extra files, and operational failure are refused. |
| Self-approved reproduction | Measurement and reviewer acceptance remain separate | A measurement alone never establishes independent acceptance. |

Keep result bytes separate from host records.
CI keeps its approved host and Python closure.
The new run records its own approved host fields.
Local observations do not impersonate the qualified hosted environment.
No environment dump or absolute source path enters the public record.

## Architecture constraints

ADR-100 remains the semantic authority.
ADR-071 keeps integrity, review, and authenticity separate.
ADR-117 governs the existing public package interfaces.
No new ADR, public schema, runtime interface, store, or service is needed.
Existing profile, claim, source, and tooling validators supply policy as code.
Exact inventory and digest joins supply the executable architecture constraints.
The canonical CI graph owns any hosted execution and approved artifact upload.
It must retain exact revisions, pinned actions, and required-job aggregation.

The result supplies no live-runtime realization or backend conformance.
It supplies no noninterference, opacity, unbounded proof, or broader profile result.
Historical runtime-mapping gaps remain explicit.
SEM-232 remains DRAFT until its remaining delivery obligations are met.
Issue 976 owns subsequent public and scientific claims.

## References and document review

- [mCRL2 202607.0 ltscompare](https://www.mcrl2.org/web/user_manual/tools/release/ltscompare.html): relation, explicit hiding, input order, and witness capabilities.
- [Bubblewrap reference architecture](https://github.com/containers/bubblewrap/blob/main/README.md): explicit filesystem, process, and network isolation policy.
- [ASD-STE100 Issue 9](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf): sections 1, 4, 5, and 6.
- [Architecture preflight](../../../docs/decisions/issue-975-independent-crossing-reproduction-preflight.md): exact subject, reviewer authority, and existing module boundaries.

The review checks technical names, sentence limits, and one fact per sentence.
It keeps architecture descriptions separate from implementation tasks.
