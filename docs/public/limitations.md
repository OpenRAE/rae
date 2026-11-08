# Check current limits

Use these limits to select a study and describe its results.
The links use inspected Python source at commit
`e71ddbc29e9e06658ddbe2b2c12edf8ed424f044`.
They do not identify the latest release. They do not qualify another installation.

## Validation and deployment

| Established boundary | Limit and source |
| --- | --- |
| SDL validation checks structure and implemented semantic rules. | The [first scenario](quickstart.md) creates no hosts. A valid document can exceed backend support. |
| The processor checks selected backend declarations during planning. | The [planner tests][realization-tests] reject unsupported exact requests. A valid plan does not prove that a run succeeds. |
| RAES supplies contracts, portable interfaces, stubs, and conformance checks. | It supplies no concrete deployment backend or managed service. An external project owns its native resources. It owns credentials and teardown too. See the [backend guide](backends.md). |

## Realization and composition

The [realization specification][explicitness] governs exact requests.
A backend must honor them or reject them.
Open concerns permit choices only under their governing rules.
The [envelope specification][envelopes] defines the permitted comparison boundary.
Identical authored files do not establish identical environments or timing.

The [control support reference][control-support] records tests of installed
mixed execution and staged handoffs. The tests use controlled providers.
The runtime refuses two configurations:

- reusable participant control combined with mixed runtime;
- a distributed dispatcher combined with portable mixed services.

Separate passing configurations do not establish joint support.
The reference separates execution, delivery, and observation.
Keep these facts separate in your result.
These tests check bounded runtime behavior. They do not certify a native backend.

## Information flow and formal assurance

The [finite opacity tests][opacity-tests] check declared possible points and
observer assumptions. They do not cover all runs or channels.
The [abstract proof evidence][opacity-proof] identifies a conditional theorem.
It lists its dependencies and exclusions. It does not prove that the Python
checker implements the theorem. It does not prove runtime enforcement or backend realization.

The [historical opacity correction][opacity-history] withdraws earlier backend
assurance claims. Those claims used fixed test transcripts.
Use the [participant research route](research.md#what-can-a-participant-infer-or-control)
to distinguish current checks from those historical findings.

## Evidence and reproducibility

The [evidence-record contract][evidence-code] checks supplied record structure
and loss disclosure. The [content-backed validator][evidence-validator] checks more
relationships. Callers must supply content and its required context for those checks.
A valid declaration does not prove collection occurred.
A matching checksum does not prove a measurement is accurate.

The [experiment specification][experiment] defines separate objects for a
scenario, task, apparatus, run, and study.
Saved inputs and evidence support another attempt.
They do not guarantee equal outcomes or deterministic execution.
They do not guarantee exact replay, scientific validity, or independent reproduction.

Fixture timestamps and example checksums are test data.
Historical corpus counts describe their original checks.
None proves that a new experiment ran.

## Stability and project support

The [schema publication manifest][schema-manifest] assigns stability labels to
schemas. A versioned name alone does not mean that a schema is stable.
Check the entry for every contract used in your result.

RAES is an academic and engineering project.
The inspected [maintainer record][maintainers] names one maintainer.
The [governance record][governance] does not require a second maintainer or
independent review for every change. Do not infer service guarantees from a release.

Use the [citation guide](citation.md) to identify the exact artifacts you used.
State how readers can access evidence. State which conditions remain untested.

[realization-tests]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/implementations/python/tests/test_sem_218_realization.py
[explicitness]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/specs/formal/realization/explicitness-and-realization.md
[envelopes]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/specs/formal/realization/envelope-semantics.md
[control-support]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/docs/explain/reference/revised-control-semantics.md
[opacity-tests]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/implementations/python/tests/test_issue_961_participant_opacity.py
[opacity-proof]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/specs/formal/participant-semantics/participant-opacity-proof-evidence.json
[opacity-history]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/docs/research/participant-opacity/current-state-assessment.md#correction-through-issue-1374
[evidence-code]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/implementations/python/packages/raes_contracts/contracts/experiment_evidence.py
[evidence-validator]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/implementations/python/packages/raes_contracts/contracts/experiment_run_evidence_validation.py
[experiment]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/specs/formal/experiment-core/README.md
[schema-manifest]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/contracts/schema-publication-manifest.json
[maintainers]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/MAINTAINERS.md
[governance]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/GOVERNANCE.md
