# SCE-003 Adaptive-Difficulty Lineage And Validity Audit

Date: 2026-07-30

Issue: #784

Requirement: SCE-003

## Scope And Method

This audit asks whether the SCE-003 policy, decision, intervention, and
provenance design is defensible as both an engineering contract and a basis for
scientific analysis. It extends, without modifying, the digest-pinned SCE-002
[`prior-art-and-design-criteria.md`](prior-art-and-design-criteria.md) record.

The review used original papers, normative specifications, and the existing
RAES lineage. Publication title, author, year, venue, and DOI were checked as
separate fields against DOI publisher/registry metadata on 2026-07-30.
Secondary literature was not used to establish a design claim.

## Inherited RAES Lineage

SCE-003 inherits these already reviewed design criteria:

- Hunicke and Chapman's
  [AI for Dynamic Difficulty Adjustment in Games](https://www.cs.northwestern.edu/~hunicke/pubs/Hamlet.pdf)
  supplies the inspectable controller shape: observation, policy, prediction or
  trigger, intervention, and outcome are distinct concerns.
- The
  [MIASE paper](https://doi.org/10.1371/journal.pcbi.1001122) and
  [SED-ML specifications](https://sed-ml.org/specifications.html) separate a
  simulation model from its procedure, repeated tasks, processing, and
  outputs.
- Zeigler's
  [experimental-frame work](https://doi.org/10.1080/03081078408934871)
  separates the conditions under which a model is exercised and observed from
  the model itself.
- L'Ecuyer's
  [streams and substreams work](https://doi.org/10.1287/opre.50.6.1073.358)
  supports stable, independently addressable simulation streams rather than
  worker- or schedule-relative randomness.
- Sargent's
  [Verification and Validation of Simulation Models](https://doi.org/10.1109/WSC.2010.5679166)
  keeps implementation verification, model validation, intended use, and
  claim scope distinct.
- Cybench, AutoPenBench, and the agent-evaluation sources mapped in
  [`lineage.md`](../../explain/sdl/lineage.md#benchmark-and-experiment-lineage)
  motivate explicit task, evaluator, scaffold, assistance, repeated-run,
  baseline, resource, and information-boundary disclosure.

Together, these sources already imply that adaptive difficulty is an
experiment procedure and intervention. It is not a runtime rewrite of the
scenario model, an invisible evaluator setting, or a replacement for evidence.

## Adjacent Primary Literature

### Dynamic treatment regimes

Murphy's
[Optimal Dynamic Treatment Regimes](https://doi.org/10.1111/1467-9868.00389)
(2003) defines a dynamic regime as a sequence of decision rules that tailors
treatment to changing observed status. The useful transfer is the
history-dependent treatment-regime shape: assigned policy, decision history,
and realized treatment path are all analysis-relevant.

RAES does not adopt Murphy's estimator or potential-outcomes assumptions, and
the SCE-003 contracts do not establish causal identification. A study must
state its estimand and justify the assumptions needed by its chosen analysis.

### Adaptive testing and measurement validity

Weiss's
[Improving Measurement Quality and Efficiency with Adaptive Testing](https://doi.org/10.1177/014662168200600408)
(1982) makes adaptive-testing performance conditional on an item-response
model, item pool, selection strategy, and termination criteria. This is a
critical negative lesson for SCE-003: adapting from a score does not make that
score a validated difficulty or competence scale.

RAES therefore records a policy-local ordering and binds both an exact
versioned and digest-bound measurement-source definition and the exact
evidence instance used at a decision cut. It does not implement item response
theory, calibrate an item bank, estimate ability, or infer competence.

### Curriculum and treatment-path effects

Bengio, Louradour, Collobert, and Weston's
[Curriculum Learning](https://doi.org/10.1145/1553374.1553380) (2009)
demonstrates that the selection and order of examples can change learning
dynamics and outcomes. The transfer is that a scaffolded or adaptive path is
received treatment, not a presentation-neutral detail.

RAES records fixed, adaptive, and scaffolded allocations separately and
archives realized decisions and interventions. It does not claim curriculum
optimality, improved generalization, pedagogical benefit, or participant
learning from the fact that an intervention was selected or delivered.

### Common random numbers in simulation experiments

Heikes, Montgomery, and Rardin's
[Using Common Random Numbers in Simulation Experiments](https://doi.org/10.1177/003754977602700301)
(1976) treats reuse of a pseudo-random-number stream across alternatives as a
deliberate correlated experimental design with corresponding statistical
analysis. Combined with RAES's L'Ecuyer-derived stream coordinates, this means
a follow-up trial never inherits a stream merely because it descends from
another run.

An intentional common-random-number comparison retains the governed
randomness namespace and unchanged semantic stream addresses and declares the
paired analysis. An independent comparison declares independent
randomization. Run lineage alone implies neither relationship.

## Source-To-Design Mapping

| Scrutiny question | Adopted SCE-003 obligation | Explicit limit |
| --- | --- | --- |
| What exactly adapts? | A sealed experiment policy selects only declared actions or proposes a separately admitted follow-up. | No live SDL, topology, factor, identity, snapshot, or stream mutation. |
| What was observed? | The policy names an exact source definition; each decision names an exact evidence instance and state cut. | Identity and provenance do not prove construct validity or calibration. |
| What treatment was received? | Fixed, adaptive, and scaffolded assignments and realized intervention paths are archived separately. | A deterministic path is not a causal effect estimate. |
| How is sequential choice controlled? | Rules, priority, evaluator identity, cadence, cooldown, bounds, stopping disposition, and history heads are predeclared. | The contract does not correct optional-stopping or path-selection bias for an analyst. |
| Can a harder scenario replace the baseline? | A changed scenario becomes a new admitted trial and run linked to the source. | Descent does not authorize identity or random-stream reuse. |
| Can stochastic alternatives be compared? | Random-stream identity and semantic addresses remain governed experiment facts. | Common versus independent randomization must be declared and analyzed accordingly. |
| Does replay establish validity? | Replay establishes the same bounded resolver decision for the same governed inputs. | It does not validate the measurement model, simulation model, backend, pedagogy, or policy optimality. |

## Threats To Validity And Required Disclosures

### Construct and measurement validity

The study must identify the measurement definition, derivation method,
calibration or uncertainty basis, visibility, and known limitations. A
threshold over completion time, score, retry count, or objective progress is
not a universal competence measure. Substituting a different definition under
the same local source id fails contract validation, but semantic suitability
still requires domain evidence.

### Endogenous and time-varying treatment

An adaptive action depends on post-allocation observations. Naive analyses that
condition on the realized path or compare it as though it were a baseline
factor can introduce selection bias. The study must distinguish assigned
policy effects from per-decision, per-protocol, or descriptive path analyses
and state the assumptions used for any causal interpretation.

### Sequential looks, stopping, and missingness

Decision cadence, cooldown, intervention bounds, terminal rules,
path-dependent eligibility, denied/unsupported actions, and lost evidence can
change inclusion and stopping. These facts are archived so an analysis can
handle them; SCE-003 does not prescribe or certify a sequential estimator,
missing-data model, or multiplicity correction.

### Scaffolding and information boundaries

Guidance availability, delivery, participant observation, and downstream use
are separate events. Hidden or assurance-only evidence remains subject to
participant information-flow rules. A policy decision neither authorizes
disclosure nor proves that a participant received or used a scaffold.

### Simulation dependence and V&V

Paired/common and independent randomization answer different variance and
comparison questions. The analysis plan must name the relationship. It must
also state the simulation/backend validity evidence and intended-use boundary;
deterministic policy execution cannot compensate for an invalid scenario,
apparatus, observation model, or backend realization.

## Engineering Finding From This Audit

The initial SCE-003 implementation bound observation inputs to a local
`source_id` and carried an exact evidence reference, but did not require the
input to repeat and match the policy's immutable source-definition identity.
That permitted measurement substitution under the same local role.

The corrected contract:

1. models the source definition as an `ExperimentReferenceModel` specialization
   that requires both `ref_version` and `ref_digest` and forbids `ref_path`;
2. carries that source definition in transient inputs and archival observation
   references, separately from the exact evidence instance;
3. rejects source-definition mismatch in the pure resolver;
4. rejects substituted source definitions during run-provenance validation;
   and
5. publishes the same constraints in JSON Schema and tests model, resolver,
   archive, and schema failure modes.

This closes an identity and reproducibility gap. It still intentionally leaves
measurement construction and causal/statistical adequacy to evidence-bearing
study design and review.

## Minimum Defensible Analysis Record

A claim-bearing adaptive study should disclose:

1. assigned condition and exact policy identity;
2. policy-local difficulty ordering and rationale;
3. measurement definition, evidence derivation, uncertainty, and limitations;
4. exact observation and decision cuts;
5. realized intervention path, including denied, unsupported, failed, or
   missing interventions;
6. cadence, cooldown, stopping, and follow-up eligibility rules;
7. random-stream relationship across compared alternatives;
8. estimand and treatment-path handling;
9. missing-data, censoring, multiplicity, and sequential-analysis treatment;
   and
10. simulation/model/backend V&V scope and explicit nonclaims.

The portable contracts preserve the inputs needed to audit such a record. They
do not make every analysis using those inputs defensible.

## Source And Notice Disposition

The publications above are semantic design precedents. SCE-003 adopts no
source syntax, schema, code, estimator, item-response model, curriculum
optimizer, random-number algorithm, controller implementation, or wire
format. No compatibility or copied-code claim is made, no third-party notice is
introduced, and the normative `sdl-lineage-ledger-v2` subject/notice
disposition is unchanged because SCE-003 adds experiment-core contracts rather
than SDL subject derivations.

## References

- Susan A. Murphy, *Optimal Dynamic Treatment Regimes*, *Journal of the Royal
  Statistical Society: Series B* 65(2), 2003,
  <https://doi.org/10.1111/1467-9868.00389>.
- David J. Weiss, *Improving Measurement Quality and Efficiency with Adaptive
  Testing*, *Applied Psychological Measurement* 6(4), 1982,
  <https://doi.org/10.1177/014662168200600408>.
- Yoshua Bengio, Jérôme Louradour, Ronan Collobert, and Jason Weston,
  *Curriculum Learning*, *Proceedings of the 26th Annual International
  Conference on Machine Learning*, 2009,
  <https://doi.org/10.1145/1553374.1553380>.
- Russell G. Heikes, Douglas C. Montgomery, and Ronald L. Rardin, *Using
  Common Random Numbers in Simulation Experiments — An Approach to Statistical
  Analysis*, *SIMULATION* 27(3), 1976,
  <https://doi.org/10.1177/003754977602700301>.
