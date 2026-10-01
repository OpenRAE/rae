# Participant-local outcomes (ACT-618)

ACT-618 extends the SEM-215 interpretation owner. A participant outcome is a
local claim about declared criteria at an observation cut. Action completion,
local outcome, objective satisfaction, evaluation, reward and episode termination
remain distinct; none implicitly establishes a status at another layer.

## Existing coverage and added behavior

| Surface | Existing meaning | ACT-618 addition |
| --- | --- | --- |
| Action-result status | Status of one action attempt | No change; success alone supplies no attainment evidence |
| SEM-215 rule | Explicit relations between meaning layers | Versioned local definition with grounded criteria |
| Interpretation record | Provenance-bearing cross-layer interpretation | Legacy targets remain mandatory |
| API-411 report v1 | Sources and downstream relationships | Preserved reader and schema |
| API-411 report v2 | New local member of the same family | Category, attainment, knowledge, cut and revision |
| RUN-305/311 history | Observations and episode lifecycle | Reused evidence and episode owners |
| RuntimeSnapshot / ControlPlaneStore | Atomic revisioned runtime state | Append-only outcome reports and replay |

## Definition and evidence

A rule opts in with `semantic_version: 2.0.0` and `local_outcome` with
`model_version: 1.0.0`. Only these rules may have empty downstream targets.
The closed categories are `task_completion` (all declared criteria of a local
task) and `effect_realization` (a declared effect set without claiming completion
of the whole task). An offensive transfer, defensive containment and ordinary
service delivery use the same categories with their own criteria. Role and
backend do not affect category meaning.

`criterion_basis` explains the selection and is inert text. Unique criteria name
a rule-local `source_id` and an `effect_id` declared by that action source.
Composition rewrites cross-section references and preserves rule-local IDs.
Compilation retains the exact definition. A source's declared `evidence_refs`
bound evidence admitted to its criteria.

The producer resolves real behavior-history observations. Enclosing participant,
episode, action and contract coordinates must match the nested action result.
Observation identity comprises action-instance ID, observation point and
canonical content digest. A report records the exact history-prefix length and
digest, normalized through the incumbent contract so omitted defaults do not
change a cut during reload.

An evidenced effect supplies a positive criterion observation; evidenced
`no_effect` supplies a negative. Missing effects, `unknown_effect` and missing
admitted evidence supply no decided observation. Action status never supplies
positive/negative criterion evidence. Withheld action observations retain
withholding rather than disclosing effect attainment.

The fixed `retain_until_explicit_correction` policy aggregates all applicable
observations at the cut. Positive and negative evidence for one criterion is
conflicting regardless of arrival order. Both observation references and the
original history survive; no last-write-wins selection occurs.

| Evidence | Attainment | Knowledge |
| --- | --- | --- |
| All criteria positive | `attained` | `supported` |
| Decided criteria include positives and negatives | `partial` | `supported` |
| Some positive criteria, others unobserved | `partial` | `unknown` |
| All criteria negative | `not_attained` | `supported` |
| No positive evidence and an undecided criterion | `undetermined` | `unknown` |
| Contradictory observations for a criterion | `undetermined` | `conflicting` |
| Applicable withholding without contradiction | `undetermined` | `withheld` |

Partial attainment is distinct from incomplete knowledge. `absent` means no
report exists, not a recorded unknown observation. Under `exact_observation_cut`,
the projection is current only while its behavior-history cut matches. A later
event makes the projection stale; the old report stays valid at its recorded cut.

## Identity and evolution

Stable identity is `(run/snapshot scope, participant_address, episode_id,
outcome_id)`. `event_id` and positive `revision` identify an update, distinct from
the outcome and action attempts. Multiple outcomes per participant are supported.
Revision 1 has no predecessor. Later revisions name the exact preceding report
and increment by one. Rule reference and canonical rule digest are immutable for
that identity; a changed definition needs a new outcome identity. Every report
retains the complete rule specification, so replay never substitutes today's rule.

Any attainment state can change when evidence warrants it. Corrections name
excluded observation points plus a provenance-bearing `correction_basis`.
Exclusions must resolve at the cut and cannot silently disappear in later
revisions. Corrections append reports; they never edit old reports or evidence.

Updates require the exact running episode. `reset_without_transfer` preserves
history but selects no old head for the new episode. Reset/restart cannot carry
attainment forward; termination, timeout and interruption do not imply local
success/failure. Late updates to closed episodes are rejected. Holdings lifecycle
remains with ACT-616/#217; this contract adds no holdings owner.

## Production and authority

`RuntimeControlPlane.record_participant_outcome` uses the embedder-admitted
compiled model. Participant and rule must exist. A compiled behavior specification
must declare the rule and select the participant explicitly or by its entity role;
rule action sources must also be among the participant's declared actions. Callers supply references, never a
replacement rule or claimed attainment. An authenticated operator requires the
existing target and participant subject binding.

Existing mutation ownership, locking, operation admission, audit, history-head
checks and snapshot-revision CAS govern publication. Requests carry expected
outcome and snapshot revisions. Exact retry returns the existing receipt;
changed event-identity reuse fails. Report, terminal operation and audit commit
atomically, with existing durable cache reconciliation on failure.

The history is runtime-owned. Backend/native result admission rejects replacement;
transition validation rejects truncation/rewriting. Snapshot construction and
wire validation replay reports against actual observation prefixes. No second
database, event bus or mutable outcome cache is introduced.

Participant-local does not imply participant-visible. The embedded operator
operation adds no HTTP endpoint or participant retrieval projection. Existing
audience, visibility and redaction owners still govern participant views.
The generic HTTP snapshot response omits private outcome history as well.
Outcome criteria, knowledge and references are not inserted into those views;
references grant no evidence access. Errors expose bounded validation facts,
never raw evidence or caller payloads.

## Historical compatibility

`participant-outcome-report-v1` remains unchanged. The explicit
`decode_participant_outcome_report` reader dispatches `1.0.0` and `2.0.0`, rejecting
unsupported versions. V1 lacks the local definition, cut and revision chain, so
there is no lossless automatic upgrade. No category, attainment or unknown
observation is synthesized from historical status or absent fields.

Adoption retains the v1 artifact and produces a new v2 report under a declared
rule from grounded observations. A snapshot missing the additive
`participant_outcome_history` field reads as empty history without inventing
reports. New writers publish the field; old closed-schema readers need the
updated draft runtime-snapshot contract to consume it.

ACT-618 traceability and `test_act_618_outcome_*` supply finite executable
definition, runtime, rejection, persistence and compatibility evidence. This is
not a universal proof about arbitrary backends or the truth of supplied evidence.
