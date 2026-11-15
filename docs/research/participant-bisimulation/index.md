# Participant-crossing bisimulation design

Issue [#811](https://github.com/OpenRAE/rae/issues/811) selects one bounded,
genuine bisimulation target and makes its machine-checkable result mandatory
downstream.

Issue #811 defines the target and program. Issues #971 through #976 deliver the
finite result for `participant-crossing-dpbb-finite-v1@rev2`.

- [Architecture preflight](../../decisions/issue-811-participant-bisimulation-preflight.md)
- [Independent model preflight (#971)](../../decisions/issue-971-participant-crossing-models-preflight.md)
- [Executable model construction (#971)](model-construction.md)
- [Multi-operation model construction (#1395)](multi-operation-construction.md)
- [ADR-100](../../decisions/adrs/adr-100-participant-crossing-bisimulation.md)
- [Current-state assessment](current-state-assessment.md)
- [Candidate comparison](candidate-comparison.md)
- [Theorem and profile selection](theorem-selection.md)
- [Proof-tool decision](proof-tool-decision.md)
- [Worked evidence](worked-evidence.md)
- [Requirement disposition](requirement-disposition.md)
- [Implementation program](implementation-program.md)
- [Machine-readable program](implementation-program.json)
- [Formal authority](../../../specs/formal/participant-semantics/participant-crossing-bisimulation.md)
- [Historical finite machine check (#974)](https://github.com/OpenRAE/rae/blob/4120ee77a49e89dfe273016e7721b52b3b1b7dfd/specs/formal/participant-semantics/participant-crossing-machine-check.md)
- [Evidence identity and publication (#976)](../../decisions/issue-976-crossing-evidence-identity-design.md)

The pinned `dpbranching-bisim` decision relates the declared initial states of
the complete rev2 carrier. A separate implementation-agent reviewer accepted a
fresh qualified reproduction. The result is a finite model check, not an
unbounded proof. It establishes no runtime realization, backend conformance,
noninterference, opacity, or multi-operation result.

## Present applicability

The result above describes the retained historical investigation.
Commit `80b089b55b1f09ce594657d9c81cfa1f9a05e8a7` removed crossing captures and reproduction records under issue #1949.
The [original reproduction record](https://github.com/OpenRAE/rae/blob/4120ee77a49e89dfe273016e7721b52b3b1b7dfd/specs/formal/participant-semantics/participant-crossing-reproduction.md) names its source revision and limits.
The current checkout does not supply that retained reproduction package.
No new reproduction was performed for this documentation change.
Use the [current formal reference](../../../specs/formal/participant-semantics/participant-crossing-bisimulation.md) for required relation meaning.
