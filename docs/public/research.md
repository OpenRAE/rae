# Evaluate the research surface

Choose a question, inspect a concrete example, and identify what remains unknown.
The [concepts page](concepts.md) defines the terms used below.
These routes support study. They do not announce scientific results.

## Start from your first result

The [first-scenario exercise](tutorials/first-scenario.md) checks and formats a
network with one host. Its visible result concerns the document's structure.
No infrastructure is created. The first route below explains why this boundary matters.

For deeper study, each route links a specification, code, and tests.
It also links an architecture decision record (ADR). ADRs explain design reasons.
Specifications and published contracts define required meaning.
Code and tests show behavior at a stated revision.

All repository links below use commit
`e71ddbc29e9e06658ddbe2b2c12edf8ed424f044`, the inspected Python source snapshot.
This is not a release designation. Match your installation to its release tag
or commit before you apply a finding. Working records remain in the repository.
They are not included in this hosted guide or its search index.

## What meaning survives another realization

**Question.** Which facts must stay fixed when the same scenario reaches another
backend? A changed environment can change a result. That change can obscure
the effect of a participant's actions.

An exact declaration fixes a requirement. A constrained declaration permits
bounded choices. Realization fills only concerns that the governing rules leave
open. The [explicitness specification][explicitness] defines these rules.
A realization envelope records permitted choices and disclosure obligations.
The [envelope specification][envelopes] and [ADR-070][adr-envelope] explain
how those choices affect comparisons.

**Inspection task.** Start with the
[first scenario](_static/examples/first-scenario.sdl.yaml).
Locate its exact `os: linux` declaration. Then inspect
`test_planner_rejects_unrealizable_exact_declaration` and its accepting pair in
the [realization tests][realization-tests]. Compare their backend manifests.
The SDL request stays exact; the support declaration changes the planning result.

**Demonstrated behavior.** The tests exercise
[`compile_runtime_model`][compiler] and [`plan`][planner] with test manifests.
An unsupported exact request produces a diagnostic. The planner does not
silently permit an approximation.
The [explicitness tests][explicitness-tests] also check that variable substitution
does not turn a bounded choice into a falsely exact declaration.
These are compilation and planning checks, without a native deployment.

**Primary reference.** The
[Functional Mock-up Interface 3.0.2 specification](https://fmi-standard.org/docs/3.0.2/),
sections 1.2.2 and 4, separates co-simulation components from their coordination.
Co-simulation connects simulation components that keep their own solvers.
This explains why component support alone cannot establish coordinated behavior.
It does not establish that RAES implements that interface.

**Limits and next investigation.** A valid plan does not prove that an
environment exists. It does not prove equal timing or outcomes.
Compare one declared concern against native readback from two named backend setups.
Native readback checks state through the backend's owning interface.
Keep the same scenario, envelope, and observation rule.
The hypothesis is that these controls help explain the selected difference.
Whether they suffice for your outcome remains an open question.
Use the [limits reference](limitations.md#realization-and-composition) before
selecting a live task.

## What can a participant infer or control

**Question.** Can a participant infer a secret fact from a decision, omission,
or delivery pattern? The visible payload can hide a fact that these channels reveal.

The [information-flow specification][information-flow] separates world state,
participant views, policy, and allowed release.
The [control support reference][control-support] separates permission, execution,
delivery, and observation. Its unsupported combinations remain unsupported.
The [mixed-control fixture][control-fixture] supplies an authored control example;
it does not install a controller or prove runtime support.

Predicate opacity requires an alternative for each secret case.
The observer cannot distinguish that nonsecret alternative from the secret case.
The [opacity specification][opacity] defines the condition and its inputs.
They include memory, allowed strategies, observation order, and time.

**Inspection task.** Read
`test_finite_checker_reports_only_a_bounded_positive_result` in the
[finite opacity tests][opacity-tests]. It compares two possible points with
the same observation and different secret labels.
A possible point combines a modeled run, observer, state boundary, and declared assumptions.
Then read `test_one_equal_history_pair_does_not_cover_another_secret_point`.
Its third point exposes a secret case without an indistinguishable alternative.
The [checker kernel][opacity-kernel] implements the comparison.

**Demonstrated behavior.** The first case finds no counterexample within its
declared finite inputs. The second finds one.
A counterexample is an admitted case that violates the selected condition.
The tests select the historical `participant-opacity-baseline-v1@sem-231/rev2`
profile. Do not substitute the current profile without examining the difference.
The [design criteria][opacity-research] explain the observer choices and primary literature.
[ADR-099][adr-opacity] records the selected kernel.

**Primary reference.** Schoepe and Sabelfeld's
[Understanding and Enforcing Opacity](https://schoepe.org/~daniel/csf15-opacity.pdf)
(CSF 2015, DOI `10.1109/CSF.2015.41`) defines observer-relative secrecy and
distinguishes progress and timing assumptions.
That result motivates explicit observation assumptions; it does not certify RAES.

**Formal semantics.** A finite counterexample search and an abstract theorem
answer different questions. The [Isabelle/HOL theorem][opacity-theorem] has a
[proof evidence record][opacity-proof] with pinned dependencies and assumptions.
Isabelle/HOL is a proof assistant for higher-order logic.
The theorem establishes its conditional abstract result.
It does not establish correspondence with the Python checker or a concrete backend.
Compare those exclusions before reusing a proof claim.

**Historical finding.** The
[correction through issue 1374][opacity-history] describes an earlier test defect.
The backend transcripts were fixed test values.
Later work withdrew backend assurance statuses.
Those historical results do not qualify a current backend.

**Limits and next investigation.** Add one observable denial or timing difference
to a finite example and inspect the resulting information cells.
An information cell contains cases the observer cannot distinguish.
Keep the profile, bounds, strategy, and order explicit.
Whether a native backend exposes additional channels remains an open question.
No finite result establishes universal secrecy or runtime enforcement.

## What evidence supports another attempt

**Question.** Can another researcher find the inputs, observations, and losses
behind a result? These details matter when you compare runs or explain a metric.

The [experiment specification][experiment] separates task, apparatus, run,
captured evidence, derived measure, and study.
A capture requirement states what should be collected.
Provenance identifies origins and relationships.
[ADR-066][adr-evidence] separates operational observations from research evidence.

**Inspection task.** Compare the
[valid evidence-record fixture][evidence-valid] with the
[fixture missing a content checksum][evidence-invalid].
Both name a content location; only the first supplies the required checksum.
The [raw-content model][capture-code] rejects a content URI without its checksum.
The [evidence-record model][evidence-code] also requires loss disclosure for
redacted or withheld evidence. A checksum identifies bytes. It does not establish truth.

**Demonstrated behavior.** The
[evidence provenance tests][evidence-tests] validate run, task, apparatus,
measurement-channel, and content relationships.
Their [content-backed validator][evidence-validator] checks supplied material.
These tests use synthetic in-memory content.
The example fixture's timestamp and repeated checksum characters are test data,
not a published experiment or an available capture.

**Primary reference.** [W3C PROV-DM](https://www.w3.org/TR/2013/REC-prov-dm-20130430/)
(Recommendation, 30 April 2013), sections 2 and 5, defines entities, activities,
agents, and their provenance relationships.
This supports separating artifact identity from the activities that produced it.
It does not prove a RAES capture occurred or a study is valid.
The [experiment research explanation][experiment-research] connects this distinction
to experiment design and interpretation.

**Limits and next investigation.** Identify one claimed measurement and follow
its evidence references to supplied content.
Check its capture window, source, redaction, and loss disclosure.
Record anything unavailable without publishing restricted material.
Whether the measurement supports your intended construct remains an open question.
Use the [citation guide](citation.md) to identify the exact artifacts you examined.
Successful parsing, validation, or replay alone does not establish scientific reproducibility.

[explicitness]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/specs/formal/realization/explicitness-and-realization.md
[envelopes]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/specs/formal/realization/envelope-semantics.md
[adr-envelope]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/docs/decisions/adrs/adr-070-realization-envelope-semantics.md
[realization-tests]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/implementations/python/tests/test_sem_218_realization.py
[explicitness-tests]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/implementations/python/tests/test_sem_218_explicitness.py
[planner]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/implementations/python/packages/raes_processor/planner/__init__.py
[compiler]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/implementations/python/packages/raes_processor/compiler/__init__.py
[information-flow]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/specs/formal/participant-semantics/information-flow-control.md
[control-support]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/docs/explain/reference/revised-control-semantics.md
[control-fixture]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/contracts/fixtures/sdl/mixed-control-v1/valid/mixed-control-participant.yaml
[opacity]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/specs/formal/participant-semantics/participant-predicate-opacity.md
[opacity-tests]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/implementations/python/tests/test_issue_961_participant_opacity.py
[opacity-kernel]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/implementations/python/packages/raes_processor/participant_opacity/_kernel.py
[opacity-research]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/docs/research/participant-opacity/prior-art-and-design-criteria.md
[adr-opacity]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/docs/decisions/adrs/adr-099-participant-relative-predicate-opacity.md
[opacity-theorem]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/specs/formal/participant-semantics/isabelle/Participant_Opacity.thy
[opacity-proof]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/specs/formal/participant-semantics/participant-opacity-proof-evidence.json
[opacity-history]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/docs/research/participant-opacity/current-state-assessment.md#correction-through-issue-1374
[experiment]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/specs/formal/experiment-core/README.md
[adr-evidence]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/docs/decisions/adrs/adr-066-observability-evidence-plane-separation.md
[evidence-valid]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/contracts/fixtures/experiment-core/experiment-evidence-record-v1/valid/reference.json
[evidence-invalid]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/contracts/fixtures/experiment-core/experiment-evidence-record-v1/invalid/content-uri-without-checksum.json
[capture-code]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/implementations/python/packages/raes_contracts/contracts/experiment_capture.py
[evidence-code]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/implementations/python/packages/raes_contracts/contracts/experiment_evidence.py
[evidence-tests]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/implementations/python/tests/test_exp_732_evidence_provenance.py
[evidence-validator]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/implementations/python/packages/raes_contracts/contracts/experiment_run_evidence_validation.py
[experiment-research]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/docs/research/experiment-core/cyber-range-scientific-instrument.md
