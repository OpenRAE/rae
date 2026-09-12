# Worked cases and counterexamples

All examples use [composition revision 1](composition.md). Identifiers are
illustrative semantic refs, not published profile artifacts or executable
fixtures. `K0`, `K1`, … name exact cuts with distinct expected history heads.
All effects require the ordinary gates G(K), successful commit and separately
observed realization. A refusal means zero prohibited parent effect, not zero
authorized audit or supervisory activity.

## A. Non-security treatment influence and teaching intervention

Select `teaching-influence/rev1` with mandatory dynamic-IFC propagation and an
admitted teaching rule, plus `session-budget/rev1` as a mandatory resource
constraint. The IFC domain is the powerset of the closed influence refs
`{worked-example, coached-hint}`. Order is subset, join is union, bottom is the
empty set for known uninfluenced inputs. Unresolved source coverage is missing,
not bottom. The profile tracks teaching history; it makes no security claim.

At K0, a declared hint observation H has `{coached-hint}`. The participant's
memory has `{worked-example}`. Its proposal P therefore has
`{worked-example, coached-hint}`. The profile permits that influence at the
practice-action sink. Resource admission also permits P. Rule `hint-followup/1`
requests a subsequent participant inject drawn from an admitted reflection
prompt artifact when `coached-hint` is present. No arbitrary content-generating
callback is embedded in the rule.

Commit P's decision and causal bindings before the practice action. At K1,
claim a new DSL-111 inject occurrence I with DSL-142 addressee, rule authority,
H/P provenance, visibility, and effect key `(run, P-root, hint-followup/1, 0, 0)`.
The inject source has its own declared labels; I joins those with P's declared
control-dependency influences, retaining both teaching tokens. Admit and commit
its crossing before delivery; record delivery and
observation separately. The delivered prompt may influence the next proposal.

Set root depth 2, one firing of `hint-followup/1`, and two total effect claims.
If I causes the same predicate again, the per-rule limit ends that trigger;
ordinary admission still governs the resulting proposal. Budget exhaustion
cannot produce a second inject or erase the original influence. A new exercise
is a new root only through independent input admission, not by renaming I.

Counterexamples: defaulting a missing source to the empty set, clearing labels
on a new episode with retained memory, scheduling I from a provider callback,
or delivering it before its own admission all violate PC-04/08/10/12.

## B. Adversarial input intentionally delivered under SEM-233

Select the existing `sem-233/rev1` security algebra with an exact source/sink
policy and a separate admitted observational intervention rule. A declared
attacker submits observation A in the RAES world. Its known source resolves
`Conf(A) = {}` and `Int(A) = {attacker-influence}`. The selected observation
sink satisfies `{attacker-influence}` because the experiment intentionally
exposes the participant to that source. This does not endorse the source or
delete its provenance. Missing source identity would still be unsupported.

At K0 all observation gates permit. Commit and deliver A. Memory M and a later
proposal P inherit `attacker-influence`. A rule matching that resolved fact
requests a subsequent evaluator inject with fresh occurrence I, exact rule and
apparatus refs, and supervisor-only visibility. I re-enters delivery admission
at K1. If it would reveal a hidden experimental condition to the subject, that
subject-facing projection is withheld; a supervisor receipt is not permission
for a second audience.

The backend successfully realizing this exposure is not contaminated merely
because A is adversarial. The attack is a declared experimental variable. If
an out-of-world process replaces the tracking engine or bypasses its
instrumentation, the backend marks realization invalid and the trial's
evidence is ineligible for a successful control claim.

## C. Permissive observation with advisory monitoring

Select `observe-influence/rev1` with mandatory propagation facts but no
additional flow-denial slot, ordinary action/crossing policy, and an optional
heuristic monitor. Known influence is permitted and recorded. A monitor's high
score is advisory; with no admitted effect rule it changes neither release nor
controller authority. Missing monitor output records lost advice and does not
turn the run into a different claimed profile.

With an explicitly admitted threshold rule, the score can instead request
review. If review is required before the parent, the rule commits a withhold
and a separate review request. An authorized approval at K1 satisfies only the
review obligation; the parent must pass G(K1) and all current mechanism gates.
Absent required assessment, expired approval or unavailable reviewer leaves
the parent withheld. Optional advice cannot be advertised as a mandatory
monitoring guarantee. Observe-only support cannot claim SEM-233 enforcement.

## D. Strict control with multiple profiles

Select the SEM-233 security profile, capability restriction and a budget gate
as mandatory. At K0 P contains confidential input with
`Conf(P) = {internal-audience}` and `Int(P) = {attacker-influence}`. The external
sink satisfies neither obligation. Capability restriction permits the tool;
the budget gate permits one call. IFC denies. The conjunction denies P and
the external call count is zero, regardless of provider evaluation order.

A trusted editor can request a transformed proposal P2, but P2 inherits both
obligations. An explicit authority may declassify the named confidentiality
obligation for a fresh result P3; the integrity obligation remains. P3 still
fails that sink until a separately authorized endorsement or an appropriate
sink policy satisfies it. Handoff to a supervisor changes no label by itself.

Counterexamples: a monitor permit overriding IFC deny; capability support
standing in for disclosure permission; mandatory abstain interpreted as permit;
or a missing resolver silently falling back to observe-only control.

## E. Conflicting corrections and resource constraints

An action-admission mechanism and two deterministic shields evaluate P at K0.
Shield S1 requires route R1; shield S2 requires R2 to a different destination.
Both are mandatory. Canonical sorting does not select a route: composition is
conflict and P has no effect. An advisory R2 alone would have no such authority.

If the admitted profile instead declares transform T1 → mask T2, T1 creates P1
and T2 creates P2 through separate admitted steps. Each result preserves all
possible inputs and re-enters every applicable gate. P itself is withheld and
never also executed. A delay window `[10, 20]` conjoined with `[15, 25]` in the
same declared clock becomes `[15, 20]`; `[10, 12]` and `[15, 20]` conflict. A
budget that expires at 14 cannot be rescued by silently ignoring the delay.

An interrupt and an action for the same participant need an explicit ordering
and enabledness check. Shutdown is not a universally dominant effect: an
incompatible mandatory handoff cannot be silently discarded. A profile with
no valid order is rejected before dispatch.

## F. Triggered inject across stale cuts and restart

At K0 an IFC fact triggers inject key E. Its required authority and destination
pass, but another control transition advances the history before the commit.
The compare-and-swap fails: zero delivery, no committed effect claim. A bounded
retry resolves K1 and claims E with a fresh occurrence identity I. After this
commit a retry retains I; changing the inject artifact under E is conflict.

If the process dies before durable dispatch-start and the store proves that
fact, recovery may continue ordinary final validation. If it dies after
dispatch may have started, E is indeterminate. Only exact backend idempotency
or readback can prove applied/absent. A second blind delivery is prohibited.
If applied, replay returns I's receipt. If required evidence remains unknown,
the parent remains withheld where I was a required predecessor.

The root firing count survives restart. I's delivery can trigger another rule
only within the same root budget and increased depth. Rewriting the retry cut,
transport id, controller or episode does not manufacture another E or reset
that budget. A process-local in-memory store cannot support this restart claim.

## G. Admitted live-world organizational control

A run explicitly admits a live work-queue service as observation source and
an approved response endpoint as a consequential sink. The apparatus pins
service identity refs, allowed actions, freshness/clock bounds, controller
authority, observation coverage and external variability. Backend-native
credentials and handles remain in the provider's protected configuration.

A resource-control mechanism requests delay when the service quota is reached.
A separate approval protocol requires review before a live change. Delay and
review are required predecessors of the parent. The runtime records withhold,
admits those operations and reevaluates the parent at K1 when the quota window
and authorized review allow it. A changed live target revision, expired
approval, failed capability or stale policy prevents dispatch at K1. A permitted
operation is committed before the backend invokes its existing authorized
service path; readback establishes whether the effect occurred.

If readback is inconclusive after a lost response, record indeterminate. Do not
claim reversal of the live action or exactly-once execution. Unobserved service
state bounds the result. A backend credential or provider integrity failure
outside the declared world invalidates realization. Conversely, a hostile
in-world queue item may be deliberately observed and tracked as in case B.

LilRAE could realize A/C with local IFC and resource accounting; Shifter could
realize G with approval, capability and resource controls. These are possible
design choices, not selections made for either backend. Their conformance
claims name the exact subsets and evidence; neither must implement the other's
mechanisms or can infer equivalent behavior from the common protocol.
