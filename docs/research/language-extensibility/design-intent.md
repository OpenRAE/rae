# Design intent: author constraints, backend choices, requested observations

Maintainer clarification recorded 2026-09-05 for
[#1198](https://github.com/OpenRAE/rae/issues/1198) and
[#1201](https://github.com/OpenRAE/rae/issues/1201).
This is the governing intent for the remediation, not a claim that the current
SDL, schemas, backends or accepted formal contracts already implement it.

## The deliberate correction

The author constrains what matters. The backend resolves the remaining
materialization choices. RAE can describe the result at the requested depth.

The program deliberately corrects a tendency **against this design intent**:
backend installation recipes, captured specimens and implementation catalogs
have been promoted into mandatory author detail, universal type guards, and
unconditional evidence obligations. This is not merely a request to add DNF or
make an existing catalog extensible. An extensible catalog can still force the
wrong level of specification.

RAE must be capable of describing implementation detail without making that
detail mandatory, universal, or centrally enumerated. An author need not know
or name every public/private implementation that a backend might use.

## Open delegates; explicit constraints remain binding

An effective open scope delegates unspecified, realizable detail to the
backend, recursively through descendants. It is not a list of per-field
waivers and not an incomplete form the author must finish. A backend resolves
permitted choices within its capabilities and the selected execution policy.
It may reject an unsatisfiable or genuinely unsupported request; omission of
deliberately delegated implementation choices is not itself such a reason.

Explicit constraints remain binding inside an open scope. A precise child
does not close its siblings or the surrounding inventory. An open child does
not weaken a precise sibling. A closed scope restricts unspecified additions
only in its defined domain; it does not silently close the entire machine.
Closure must name its universe, including how modeled inventory relates to
incidental dependencies, rather than imply that no unmentioned OS file exists.

Undefined makes no local statement and inherits the applicable scope/policy.
It need not require an author to write `open` against every possible property.
Unknown is a state of knowledge, not a grant of discretion. Optional presence
is also distinct: an optional package may be absent, but if present must obey
the constraints attached to that optional declaration.

These are examples of intended meaning, not proposed SDL syntax:

| Request | Binding meaning | Backend-owned freedom |
|---|---|---|
| Five Linux boxes, open below | Exactly five requested boxes satisfying the Linux requirement | Distribution, release, image, resources and other unspecified realization choices |
| One Kali, open below | One Kali box | Kali release, tools, versions and configuration not otherwise constrained |
| One Kali with a specified nmap version, otherwise open | Kali and that nmap constraint | Other packages and configuration; the exact nmap constraint cannot be weakened |
| Kali release X, required tools Y, optional packages Z, configurations 1–3 | Each declared constraint, with conditional requirements for optional packages | Remaining unconstrained detail, without closing the whole package inventory |

Software presence can be required without any version restriction. A version
may instead be exact, a range, or an older/newer constraint under a defined
version relation. Package-manager coordinates, source repositories and final
repository configuration are refinements only when relevant. The backend may
use ordinary sources, a private source, an artifact or a prebuilt image without
those choices entering authored SDL when left open. Supply-chain execution
policy remains the backend/operator's responsibility, not compulsory study data.

## An abstract scenario can already be complete

Two abstract computers, a connection, and three defined possible actions each
can be a complete executable model at the selected abstraction level. It is
not necessarily a request for VMs with missing OS/package declarations.
A suitable backend can execute the declared transition/interaction semantics
without inventing concrete images, filesystems or packet networks. A concrete
backend may use those mechanisms internally where they satisfy the same
declared semantics; it must not substitute a weaker abstraction for an exact
requirement or claim equivalence without the required basis.

More detailed models can progressively constrain images, files, mounts, data,
network behavior and participant behavior. This principle applies throughout
the SDL, not only to infrastructure or packages. The language must not impose
a universal concrete-machine normal form on every scenario.

## Choosing one realization is not promising every realization

For a delegated request, the backend must find an allowed realization it can
deliver. If R is the acceptable request set and B the backend's actual offer,
the choice is a supported witness in R intersect B, subject to the selected
execution policy. A backend that can supply one permitted Linux distribution
need not supply every distribution/version imaginable to fulfill an open
Linux request. Finding a witness is an operational obligation, not merely an
assertion that the intersection might be nonempty.

This is different from a universal capability/conformance claim that every
member of R is supported, which requires R to be a subset of B. Preserve the
meaning and safeguards of that stronger claim. Do not silently redefine
`subsumes` or weaken every envelope gate. #1201/#1204 must identify the
quantifier at each admission/conformance boundary and version any change.
Experiment allocation/randomization is another distinct authority; ordinary
backend choices must not silently replace a selected experimental factor.

## Reporting choices and requesting measurements are separate

A backend must be able to describe what it actually selected or realized
through compatible RAE structures, to the requested and supported depth. A
selection known to the backend can be reported as its choice without claiming
that an independent scanner measured it. Additional observations carry their
actual basis and coverage. Neither kind of report rewrites authored intent.

That representation capability does not require every run to collect, retain
or export a full realization inventory, package digest, acquisition history,
trace, packet or other experimental datum. There are independent decisions:

- what the scenario requires to exist or happen;
- which materialization choices the backend may make;
- what realization information or observations the user requests back;
- what data must be collected, retained or exported, at which scopes/times;
- what operational state the backend needs to execute, clean up and meet
  separately applicable operator policy.

Specify these through existing scenario, task and evidence owners rather than
putting all experimental policy into node SDL. Choosing precise scenario
constraints does not automatically choose strong experimental evidence, and
choosing a detailed measurement stream does not require a detailed environment.
ADR-064/066 and the delivered #127/#337/#338 boundaries already provide the
capture, plane-separation and operational foundations. #1212 is corrective
scoped-demand work, not a replacement evidence system; #341 retains task/run/
study refinement, #340 augmentation conformance and #342 source provenance.

| Observation/reporting intent at a named scope | Meaning to preserve |
|---|---|
| No experimental data | Do not turn the scope into an experimental collection/export obligation; an explicit prohibition must also be enforceable |
| Operational only | Data needed to run, reconcile or clean up under the selected policy; not automatically a research dataset |
| No local preference / don't care | Inherit or use the explicitly selected default policy; neither a synonym for prohibition nor implicit capture-everything |
| Selected observations | Requested fields, events, streams or artifacts, with scope, timing, coverage and retention/export requirements |
| Exhaustive within a declared scope | All requested events/packets/traces within the named supported domain and bounds; not an impossible promise to observe everything everywhere |

The exact public syntax and defaults require design review. Explicitly forbidding
data is stronger than simply not requiring it. A request conflicting with a
mandatory operational policy needs an honest admission diagnostic, not hidden
collection or a claim that the policy vanished. Required inputs for scenario
execution, control, termination or selected analysis still have to be available;
internal use does not automatically authorize retention or export.

## Acceptance anchors and anti-regression rules

The remediation must demonstrate the following combinations, not only describe
them in prose:

- Five Linux boxes with one inherited open scope, no per-property waivers, and
  a backend choosing and reporting the actual boxes when requested.
- All three Kali refinements above, preserving exact siblings and optional
  presence while leaving incidental packages/configuration open.
- A complete abstract two-computer/three-action model with no invented OS,
  package, filesystem or packet-capture requirements.
- A deeply specified image/filesystem scenario with no experimental telemetry,
  and an abstract scenario with exhaustive action traces.
- Mixed per-component observation demand: packets on one link, operational-only
  data elsewhere, no experimental data at another scope, and explicitly chosen
  retention/export behavior.
- A private acquisition route used internally without author profiles or
  provenance requirements, plus a separate case where an explicitly authored
  private repository/profile constraint is binding.
- Failure for an exact-constraint violation or unsupported requested capture,
  but not merely because a backend supports only one allowed completion.

Do not declare the class fixed by adding another core catalog term, making
every field optional, forcing a profile for each internal backend choice,
requiring a complete hidden infrastructure model for abstract scenarios, or
collecting everything and merely hiding it from the final report. Preserve
honesty about achieved validation/evidence strength; no-data mode does not
justify an unsupported claim of independently verified conformance.
