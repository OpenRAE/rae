# RAES shared time model

This specification defines the semantic authority implemented for SEM-227,
SEM-228, SEM-229, DSL-126, DSL-127, DSL-128, RUN-317, and RUN-318.

## Authority boundary

The SDL owns authored temporal meaning. The processor owns canonical compiled
identities. The runtime owns lifecycle control and observation. A backend may
realize those semantics only through the portable capability and conformance
contracts defined by API-421/ASR-528. Experiment records preserve the realized
model under EXP-734.

Neither host timestamps, backend scheduler order, transport receipt order, nor
map iteration order is semantic time.

## Domains and coordinates

A time domain is:

```text
D = (kind, tick-period, epoch, visibility)
```

`tick-period` is a reduced positive rational number of SI seconds. A coordinate
on a clock is superdense:

```text
T = (segment, tick, microstep)
```

Within one segment, lexicographic `(tick, microstep)` order is meaningful under
the clock's declared monotonicity. Coordinates from different domains are
incomparable unless an explicit admitted mapping connects them.

An affine rational mapping is:

```text
target_tick = source_tick * numerator / denominator + offset_ticks
```

The exact result may be fractional. Consumers must not round it silently.

## Clocks

A clock binds one domain to one authority and declares:

- authority kind and reference;
- monotonicity;
- pause support;
- reset support; and
- jump support.

A jump is a discontinuity. It creates a new segment even when the numeric tick
moves forward. A reset or replay also creates a new segment. Prior records
remain append-only.

## Progression

Progression policy is independent from the domain:

- `real_time`: semantic ticks are paced against an apparatus clock;
- `dilated`: the declared exact ratio relates semantic and pacing progress;
- `stepped`: each accepted advance has the declared quantum;
- `event_driven`: progress follows admitted events and microsteps;
- `externally_paced`: another declared authority grants progress.

Synchronization is separately declared as none, authority-following, barrier,
or conservative. Drift is a bounded claim, not prose. Pacing does not establish
ordering or causality.

## Temporal constraints

The first closed constraint family is:

- precedence over exactly two ordinary RAES subjects;
- duration;
- window;
- deadline; and
- cadence.

Constraints resolve one clock. Causality is intentionally absent: causal claims
remain governed by participant attribution and its evidence basis.

### Trace interpretation

A trace contains subject occurrences, state changes, and admitted ordering for
one run. Clock-control records alone are not a subject trace.
For participants, trace validity uses
[`ValidTrace` and `prefix_state`](../participant-runtime/README.md).
Other ordinary SDL subjects use an explicit projection of their existing
lifecycle or event records. They do not acquire participant-private state.

An interpretation `G` supplies:

- the run and owning scope occurrence;
- the required, finite occurrence set for each subject;
- the selected event points and start/end pairing for each occurrence;
- the resolved clock, domain, authority, and segment;
- the observation horizon and its closure or coverage basis; and
- any admitted coordinate mapping.

`G` is mathematical context, not a new SDL field or wire contract.
The owning semantics or governed profile must establish it before evaluation.
A resource address identifies a subject, not one occurrence.
Repeated occurrences require explicit selection and pairing.
List order matters only for the two precedence subjects.
Record arrival order cannot select or pair occurrences.

Within `G`, write a coordinate as `x = (tick, microstep)`.
Use lexicographic order for points on the same resolved clock and segment.
`tick(x)` selects its tick. Microsteps have no declared elapsed duration.
An admitted domain mapping preserves exact rational results without rounding.
It does not itself relate different clock authorities or reset segments.

Authored bounds have no segment field. `G` binds them to the selected segment.
Reset, replay, and jump start a separate interpretation; segment numbers do
not define elapsed time across a discontinuity.
Pacing and pause do not add wall time to semantic duration.
Equal ticks with different microsteps can have strict order.
Equal full coordinates do not establish strict precedence or causal order.

### Satisfaction of a complete trace

Write `tau |=_G c` when a valid complete trace `tau` satisfies constraint `c`
under a well-defined interpretation `G`.
Completeness concerns the selected scope and obligations, not every event in
the run. Required occurrence sets are nonempty.
Each required occurrence must supply its selected points.
The relation is false when a required occurrence or point is absent from a
complete scope. Unresolved interpretation or invalid input is not falsity.

The following rules apply to every selected occurrence, or pair for precedence.
Their conjunction defines satisfaction of the constraint.

| Kind | Required interpretation and satisfaction rule |
| --- | --- |
| `precedence` | `G` pairs occurrences of `subject_refs[0]` and `subject_refs[1]` and selects one point from each. For each pair `(u, v)`, `point(u) < point(v)`. Ties and incomparable points do not establish precedence. |
| `duration` | `G` selects start `b(o)` and finish `e(o)` for each occurrence `o`. Require `b(o) <= e(o)` and `tick(e(o)) - tick(b(o)) = duration_ticks`. The duration is exact, neither a minimum nor a maximum. |
| `window` | For a selected point `x`, require `start <= x < end`. For a selected nonempty activity interval `[b(o), e(o))`, require `start <= b(o) < e(o) <= end`. Mere overlap is insufficient. |
| `deadline` | `G` selects the event whose timeliness is required. Its point `x` must satisfy `x <= end`. An on-time submission cannot establish on-time completion or effect. |
| `cadence` | `G` selects the repeated event and a finite horizon `[l, h)`. Let anchor `a` be `start`, or an explicit anchor supplied by the owning semantics. With `p = cadence_ticks`, due points are `D = {a + k*p : k is an integer, k >= 0, l <= a + k*p < h}`. For each subject, its selected occurrence points must equal `D`, with exactly one occurrence per due point. |

For cadence, addition changes the tick and preserves the anchor's microstep.
Require `D` to be nonempty. Zero occurrences therefore cannot satisfy cadence.
One occurrence suffices exactly when the horizon contains one due point.
Missing, duplicate, early, late, or extra selected occurrences violate cadence.
There is no implicit jitter tolerance or minimum-spacing interpretation.

If cadence supplies `end`, it is the exclusive horizon upper bound `h`.
Otherwise, the owning scope must supply a finite upper bound.
Without `start`, no anchor follows merely from a timestamp value.
The autonomous v1 participant profile supplies tick zero as its default anchor.
That profile's tick projection does not establish general microstep support.

Window bounds are half-open. A point at `end` is outside the window.
An activity may finish at `end` because its finish is excluded from its interval.
An empty authored window admits no point or nonempty activity interval.
Deadline equality compares the full coordinate and is inclusive.
Duration compares tick differences; a microstep difference adds no tick fraction.

Only the fields named by a kind's rule contribute to that relation.
For example, optional `start` does not add a lower bound to a deadline.
Optional coordinates do not replace a duration occurrence's selected endpoints.
Current shape validators can admit additional optional fields.
Those fields acquire no extra predicate through their presence.
Shape validity alone does not supply missing occurrence or scope interpretation.

### Finite observation and evidence

Ideal trace satisfaction and an evidence-backed decision are separate judgments.
A partial trace can omit an event that has not yet occurred.
Missing observation is not proof that a required occurrence is absent.

Let `Ext_G(pi)` be the valid complete extensions of prefix `pi` within `G`.
Extensions preserve admitted events, order, and established scope closure.
For a nonempty extension set, the semantic prefix judgment is:

```text
true     iff every tau in Ext_G(pi) satisfies c
false    iff no tau in Ext_G(pi) satisfies c
unknown  otherwise
```

An empty extension set indicates inconsistent input, not vacuous success.
An admitted violation can decide false before the scope closes.
An unfinished occurrence or unclosed cadence horizon can remain unknown.
After an event stream closes through a deadline, proven absence can decide false.
A late observation of an on-time event is distinct from a late event.
Receipt time cannot replace the selected event's semantic coordinate.

An observed decision also requires admitted evidence, provenance, and loss bounds
under the [assertion evidence rules](../objectives/proposition-and-assertion-semantics.md#evidence-admission).
Missing realization capability yields `unsupported`, not semantic falsity.
Neither a capability declaration nor clock readback proves constraint satisfaction.
The current time conformance checker validates capability, readback, and provenance.
It does not implement this general subject-trace satisfaction relation.

### Boundary examples

These mathematical examples assume one clock and segment, admitted evidence,
and the stated occurrence selection. They are not serialized SDL fixtures.

| Constraint | Selected trace or scope | Judgment |
| --- | --- | --- |
| Precedence | First point `(5, 0)`; second `(5, 1)` | Satisfied. Equal ticks do not erase microstep order. |
| Precedence | Both selected points `(5, 0)` | Violated: order is strict. |
| Duration `3` | Start `(2, 1)`; finish `(5, 4)` | Satisfied: exactly three ticks, with no microstep duration. |
| Window `[(2, 0), (5, 0))` | Point `(5, 0)` | Violated. Activity `[(2, 0), (5, 0))` is contained. |
| Deadline `(5, 0)` | Selected completion `(5, 0)` or `(5, 1)` | Equality satisfies; the later microstep violates. |
| Cadence `2`, anchor `(0, 0)`, horizon `[(0, 0), (5, 0))` | Points `(0, 0)`, `(2, 0)`, `(4, 0)` | Satisfied. A closed trace missing `(4, 0)` violates. |
| Same cadence, open prefix | Only `(0, 0)`, `(2, 0)` observed | Unknown while a valid extension can still supply `(4, 0)`. |
| Any duration | Endpoints on opposite sides of a reset | No comparable interval under this interpretation. |

## Runtime state machine

For each compiled clock:

```text
uninitialized -> running
running -> running      (advance or jump)
running -> paused
paused -> running
running|paused -> running in new segment (reset or replay)
```

Every transition has a monotonically increasing sequence and records previous
and resulting coordinates. `advance` cannot move a paused clock. A stepped
clock accepts only its exact step. Unsupported lifecycle operations fail before
state mutation.

## Invariants

1. Every clock resolves exactly one domain.
2. Every progression policy resolves exactly one clock.
3. A clock has at most one effective progression policy.
4. Mapping endpoints resolve and the authored mapping graph is acyclic.
5. Domain conversion without a mapping is invalid.
6. Semantic movement uses exact integers and rationals.
7. A discontinuity creates a new segment and does not rewrite history.
8. Equal timestamp values do not prove simultaneity or causality.
9. Temporal subject references resolve through ordinary SDL declarations.
10. Runtime control does not prove backend capability or native realization.

## Compatibility

SEM-213 participant temporal contracts remain valid. A follow-on migration may
replace their legacy inline `time_domain` and `clock_authority` strings with
references to this shared model while retaining action-specific event points
and state-machine semantics. The migration must be explicit and cannot infer a
shared clock from matching strings.

## Implementation map

| Concern | Authority |
| --- | --- |
| SDL declarations | `raes.time_model` |
| Cross-reference validation | `raes.validator._time_model` |
| Compilation | `raes_processor.compiler.time_model` |
| Compiled identity | `raes_processor.models.time_model` |
| Runtime lifecycle | `raes_runtime.time_coordinator` |
| Focused evidence | `test_sem_227_shared_time_model.py` |
| Portable declaration contracts | `raes_contracts.contracts.time_model` |
| Backend capability and admission | `raes_backend_protocols.time_capabilities`, `raes_backend_protocols.capability_admission` |
| Runtime protocol and validated readback | `raes_backend_protocols.protocols.TimeRuntime`, `raes_runtime.time_control.RuntimeTimeControlMixin`, `raes_runtime.manager.RuntimeManager` |
| Semantic conformance | `raes_conformance.time_semantics` |
| Run provenance | `raes_contracts.contracts.experiment_run` |
| Focused portable-contract evidence | `test_api_421_time_contracts.py` |
