# Scientific-Scenario Completeness Profiles

Status: **normative**.

This specification defines the REV1 intended-use scope contract required by
GOV-942. It answers which semantic concerns are required, may remain
underspecified, or are excluded for a stated scenario-use claim, and joins that
stable taxonomy to a separately versioned assessment of what RAES delivers.

It does not change ordinary SDL validity. A document containing only `name` may
be a valid SDL fragment while being unsuitable for deployment, participant
evaluation, controlled experimentation, or a reproducible benchmark.

## Normative Artifacts

The two machine-readable authorities are:

- [REV1 taxonomy](../../contracts/profiles/scientific-completeness/scientific-scenario-completeness-rev1.json),
  which owns atomic concern definitions, the five profile meanings, profile
  dispositions, and explicit non-claims; and
- [2026-10-31 delivery assessment](../../contracts/profiles/scientific-completeness/delivery-assessment-2026-10-31.json),
  which owns current delivery status, evidence, limitations, external-contract
  bindings, and issue references.

The [2026-07-12 delivery assessment](../../contracts/profiles/scientific-completeness/delivery-assessment-2026-07-12.json)
remains retained and unchanged.
The package loader selects the current assessment revision.

The taxonomy revision and assessment revision are independent. Implementing a
missing concern updates or supersedes the assessment. Changing what a concern
or profile means requires a new taxonomy revision. The join identity is:

```text
(profile_family, taxonomy_revision, assessment_revision, profile_id, concern_id)
```

## Disposition And Delivery

Profile disposition and delivery status are different dimensions:

| Dimension | Values |
| --- | --- |
| Profile disposition | `required`, `allowed-underspecified`, `excluded` |
| Delivery status | `implemented`, `partial`, `external-contract`, `deliberately-excluded`, `missing` |

`external-contract` means that a named, versioned non-SDL contract supplies the
concern, has at least one conforming checked-in instance as a satisfiability
witness, and states a binding obligation to the same scenario/run lineage. The
witness establishes that the structural contract is non-empty. It does not
prove that a backend can realize the obligation or that a particular run
satisfied it. A formal design, accepted ADR, open issue, example mention, or
schema property by itself is not implementation evidence.

For profile `p`, concern `c`, taxonomy `T`, and assessment `A`:

```text
Complete(T, A, p) iff
  A.taxonomy_revision = T.revision
  and concerns(A) = concerns(T)
  and for every c where T[p,c] = required,
      A[c].status is implemented or external-contract.
```

An implemented status requires executable evidence. An external-contract
status requires evidence for every named contract, a conforming satisfiability
witness, and an explicit binding obligation. `partial`, `missing`, and
`deliberately-excluded` never satisfy a required row. Completeness is computed;
it is not stored as a mutable boolean.

## REV1 Outcomes

The following block is checked mechanically against the normative artifacts.

<!-- scientific-completeness-summary:start -->
| Profile | Complete | Blocking required concerns |
| --- | --- | --- |
| `valid-sdl-fragment` | yes | none |
| `deployable-scenario-intent` | no | `authored-observed-state-separation`, `backend-teardown-reconciliation`, `credential-intent`, `scoped-specificity-open-world-intent` |
| `participant-evaluation-scenario` | no | `authored-observed-state-separation`, `backend-teardown-reconciliation`, `clock-declaration`, `credential-intent`, `deadlines-and-windows`, `flexible-step-tooling`, `pacing-and-synchronization`, `participant-action-observation`, `participant-budgets`, `participant-episode-reset`, `portable-behavior-contracts`, `scoped-specificity-open-world-intent`, `temporal-ordering-causality`, `time-domain-declaration`, `verifier-and-adjudication` |
| `controlled-experiment-scenario` | no | `authored-observed-state-separation`, `backend-teardown-reconciliation`, `clock-declaration`, `credential-intent`, `deadlines-and-windows`, `host-architecture-constraints`, `pacing-and-synchronization`, `scoped-specificity-open-world-intent`, `temporal-ordering-causality`, `time-domain-declaration`, `verifier-and-adjudication` |
| `reproducible-benchmark-study-input` | no | `authored-observed-state-separation`, `backend-teardown-reconciliation`, `clock-declaration`, `credential-intent`, `credential-materialization`, `deadlines-and-windows`, `flexible-step-tooling`, `hidden-benchmark-assets`, `host-architecture-constraints`, `pacing-and-synchronization`, `participant-action-observation`, `participant-budgets`, `participant-episode-reset`, `portable-behavior-contracts`, `reference-trajectories`, `scoped-specificity-open-world-intent`, `temporal-ordering-causality`, `time-domain-declaration`, `verifier-and-adjudication`, `weakness-exploitability-semantics` |
<!-- scientific-completeness-summary:end -->

Only a computed-complete profile may cite a minimal example as completeness
evidence. The current example for `valid-sdl-fragment` is admitted through the
production SDL parser. An incomplete stronger profile may have an illustration,
but that illustration MUST be labeled as a gap illustration and MUST NOT be
used to upgrade the profile.

## Composition Boundary

The stronger profiles compose SDL with existing experiment and evidence
contracts. Factors, allocation, stochastic controls, apparatus context, runs,
studies, captured evidence, and associated artifacts do not become new
`Scenario` fields. A binding obligation must connect those artifacts to the
same instantiated scenario and derivation lineage.

Profile validity is also distinct from:

- ASR-511/515 validation or admission strength;
- semantic and backend capability profiles;
- backend-relative realization support;
- successful deployment or finite conformance probes;
- statistical validity, replication, or generalizability; and
- trace equivalence, refinement, observational equivalence, Park-Milner
  bisimulation, epistemic equivalence, or multi-agent strategic equivalence.

The revisioned behavioral-relation taxonomy is defined by
`raes-behavioral-relations@rev1`. Every profile binds its intended claim to that
catalog and lists relations it does not claim. This implements the taxonomy
concern without promoting any currently incomplete stronger profile: passing
the same bounded probes or producing equal result tuples is not evidence of
bisimulation.

## Security And Evidence Boundary

Profile artifacts contain only identifiers, classifications, repository paths,
contract ids, issue references, and bounded claim summaries. They MUST NOT
contain credentials, bearer tokens, private keys, hidden answer material, raw
evidence, backend objects, prompts, environment dumps, or executable commands.
Evidence paths are fixed repository-relative paths and are checked for
containment and existence.
