# Backend Conformance Guardrails

This note is the architecture preflight for `ASR-502`. It is guidance, not an
implementation plan.

`ADR-009` makes `contracts/` the authority boundary for machine-readable
contracts, fixtures, and profiles. Backend conformance implementation code must
consume that authority; it must not recreate it in a runner-local schema,
fixture, or profile model.

## Architecture Decisions

- Backend conformance is an implementation-side verifier under
  `implementations/python/packages/raes_conformance`, not a normative artifact
  family under `contracts/`.
- `contracts/fixtures/**/<contract-id>/{valid,invalid}/*.json` is the canonical
  fixture corpus. The runner may accept an override root for tests, but the
  default root is the repository `contracts/fixtures` tree.
- `contracts/profiles/backend/*.json` is the canonical backend capability
  profile corpus. Profile-to-contract requirements must be loaded from these
  artifacts instead of copied into a second in-code table.
- Published payload validation must go through `raes_contracts.contracts`
  `ContractModel` descendants, `schema_bundle()`, and the existing semantic
  diagnostics helpers.
- Backend manifests must be rendered through
  `raes_backend_protocols.manifest.backend_manifest_payload()` and validated as
  `backend-manifest-v2`; the conformance suite must not reassemble manifest
  JSON by hand.
- CLI entry points belong in the Typer-based `raes_cli` surface.
- End-to-end proof tests for backend conformance should exercise the public
  runner or CLI against a full backend profile and the published fixture corpus;
  seeded-corruption tests should mutate a temporary copy of one existing
  required fixture and expect the shared conformance diagnostics to name the
  contract and validation failure.

## Cross-Cutting Concerns

Reuse these existing surfaces before adding anything new:

- contract models and closed-world validation:
  `raes_contracts.contracts.ContractModel`, `BackendManifestV2Model`,
  runtime envelope models, plan models, and history event models
- contract publication inventory: `schema_bundle()` and
  `contracts/schema-publication-manifest.json`
- contract-corpus resolution: `raes_contracts.corpus.corpus_family_root()` with
  the `FIXTURES` and `PROFILES` family constants, so source checkouts and
  packaged installs resolve the same published corpus through one seam
- backend contract authority:
  `raes_contracts.manifest_authority.BACKEND_SUPPORTED_CONTRACT_IDS` and
  `validate_backend_supported_contract_versions()`
- controlled vocabulary and concept-binding gates:
  `raes_contracts.controlled_vocabularies`,
  `raes_contracts.apparatus`, and the `BackendManifestV2Model` validators
- manifest rendering: `raes_backend_protocols.manifest.backend_manifest_payload`
- participant capability declarations:
  `capabilities.participant_runtime.supported_participant_roles`,
  `supported_behavior_features`, and `supported_interaction_features`
- runtime behavior probes: `compile_runtime_model()`, `plan()`,
  `RuntimeControlPlane`, and `RuntimeTarget`
- diagnostics: `raes_processor.models.Diagnostic` and `Severity`
- participant-episode semantic invariants:
  `iter_participant_episode_snapshot_violations()`
- verification workflow: `.ground-control.yaml`, `.gc/plan-rules.md`,
  `tools/check_repo_policy.py`, `tools/check_requirement_governance.py`, and
  `tools/verify_all.py`

## Security And Runtime Gates

The conformance path touches these gates:

- JSON parsing: load only local fixture/profile files selected by explicit
  roots or canonical repo roots; do not fetch remote fixtures or execute fixture
  content.
- Corpus path resolution: default fixture/profile roots must flow through
  `raes_contracts.corpus`; tests may pass explicit temporary override roots for
  mutated corpora, but loaders must not reintroduce `Path(__file__).parents[N]`
  repo-root heuristics.
- Profile id and path validation: profile ids must pass the backend-profile id
  grammar before path construction, and any caller-supplied `profiles_root`
  resolution must remain confined to that root.
- Contract shape validation: all fixture, manifest, plan, status, result,
  history, and snapshot payloads must pass the existing Pydantic contract models
  and closed-world `extra="forbid"` behavior.
- Manifest authority validation: `supported_contract_versions`,
  `concept_bindings`, capability vocabulary terms, and backend profile claims
  must resolve through existing authority helpers, not local string checks.
- Participant capability validation: role, behavior-feature, and
  interaction-feature support claims must resolve through the governed
  vocabulary scopes on `capabilities.participant_runtime`; backend-specific
  terms must use the governed `x-<owner>:<term>` extension format.
- Participant capability evidence: standard API-405 claims must also have the
  published contract surfaces required by
  `PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS`; the conformance runner
  reports `conformance.unsupported-capability-claim` when a manifest claims a
  role or feature without the runtime contract evidence surface needed to check
  it.
- Control-plane probe validation: target probes must use `RuntimeControlPlane`
  and existing operation receipt/status/snapshot envelopes rather than backend
  native objects.
- Error-envelope leakage: report failures as `Diagnostic` values with stable
  codes and messages; do not surface raw tracebacks, environment variables,
  bearer tokens, credentials, or backend-private object representations.
  Proof tests should assert stable `Diagnostic.code`, `contract_name`, and
  structured addresses rather than exact Pydantic prose.
- Host/OS exposure: CLI options may accept profile names and local roots, but
  must not require secrets or bearer tokens in process argv. Live-target
  authentication belongs in headers or process-local configuration that is not
  echoed in diagnostics.
- Persistence: the suite is report-oriented and should not write durable state
  except explicit report output requested by the caller.

## Extension Boundary

The seam is the published contract id and backend profile artifact, not a Python
enum branch or hard-coded path. Adding a backend profile or contract
family should require adding the contract schema/fixtures/profile artifact and
registering the matching validator once, not editing every call site.

Keep the profile loader parameterized by `profiles_root` and the fixture runner
parameterized by `fixtures_root` so tests can use temporary corpora while the
default path remains the published `contracts/` tree.

Participant capability declarations follow the same extension boundary. API-405
adds governed vocabulary surfaces under `capabilities.participant_runtime`
instead of a backend-profile branch, snapshot metadata field, or control-plane
role. Absence of the `participant_runtime` block declares no participant runtime
surface; when the block is present, the role and feature declarations are
mandatory and set-like. The standard terms are grounded in
`docs/explain/sdl/lineage.md`, ADR-020, ADR-022, and
`specs/formal/participant-semantics/`: exercise roles map to the existing
`white`/`green`/`red`/`blue` framing vocabulary; behavior terms map to the
action, observation, state-transition, failure, temporal, attribution, and
outcome semantics already modeled in RAES; interaction terms map to the SEM-209
coordination, contention, interference, and shared-state classes. Standard terms
are not accepted as prose-only promises: target conformance checks that the
manifest also declares the published participant episode or behavior-history
contract surfaces that carry the evidence for those claims.

DSL-437 autonomous execution is an additional fail-closed participant
capability. A backend that includes `autonomous_execution` in
`supported_behavior_features` must set `supports_autonomous_execution`, list
its supported selection strategies, exact action contracts, observation
boundaries, target addresses, policy profiles, and positive finite limits for
participants, attempts, in-flight actions, occurrences, retries per occurrence,
and burst size. It must also publish relational execution bindings, all six
generation-fenced lifecycle controls, bounded-concurrency support, and finite
execution-service and concurrent-action limits. The planner compares each
compiled action-to-target relation rather than accepting the Cartesian product
of separate action and target lists. The planner also compares the parent behavior
specification's required feature set with the runtime capability. Runtime
target registration requires the autonomous native-binding,
execution-control/readback, and bounded-batch methods. This is
admission evidence only: conformance also requires the backend participant
runtime to invoke its native service adapter, return a typed terminal action
outcome at the bound temporal coordinate distinct from control-operation
success, and preserve episode, behavior-history, temporal-context, and typed
scheduler readback in durable and conformance snapshots. Stepped cadence points
must be reachable. The portable runtime drives real-time and dilated participant
cadence; externally paced autonomous execution is not admissible until a
portable transition-notification contract is governed. Durable readback must
agree across scheduler policy identity, clock segment/lifecycle, and live
participant episode. Conditional live conformance drives two bounded native
actions plus start, pause, resume, bounded drain, reset, stale-generation
fencing, and teardown; inert method implementations or missing transition
evidence fail. The shared participant base exposes readback only; it cannot
make a backend lifecycle claim pass. Each successful control operation must
come from the backend handler and produce changed action-specific readback and
new evidence.

The explicit `participant-autonomous-execution/v2` profile additionally
requires exact support for all governed activity features, `weighted`
selection, shared-time `window` constraints, and
`blake3-xof-participant-v1`. The runtime records dependency, retry, cooldown,
burst, timing-disposition, and safe random-address facts in typed continuation
and participant behavior history. A backend must not substitute the
experiment-selection `blake3-xof-v1` address/profile, silently drop occurrence
provenance, or treat an apparatus stochastic-control declaration as scenario
variation. Missing exact support fails planning.

The `participant-autonomous-execution/v3` profile additionally requires a
closed `resource_budgets` capability under the existing participant-runtime
root. Admission matches the complete compiled resource vector against
declared owner/resource/accounting/reset/fairness support and
configuration-bound pool entries. Owner, unit, meter, accounting mode, and
capacity must match exactly; declared cross-range pools require
`tenant_partitioned` isolation. Admission is atomic, so a backend cannot accept
action/concurrency bounds while dropping storage, token, image, accelerator,
ancestor, or fairness obligations. Runtime conformance then requires typed,
generation-fenced, policy-scoped budget state; one canonical cross-policy pool
allocation ledger; and append-only reserve, measured commit, release, throttle,
and reconcile events. Native commits require a complete matching measurement
vector and evidence. Manifest support and configured capacity do not count as
measured-realization evidence.

## Gotchas And Anti-Patterns

Avoid:

- treating semantic profiles in `contracts/profiles/semantic` as backend
  capability profiles
- keeping a duplicate `_PROFILE_REQUIREMENTS` authority table after backend
  profile artifacts exist
- accepting `backend-manifest-v1` or legacy conformance paths as current
  defaults
- changing `contracts/schemas/` without the
  `contracts/schema-publication-manifest.json` change ledger, or changing only
  reference implementation models while leaving the published schema authority
  untouched
- validating fixtures with ad hoc JSON key checks when contract models already
  exist
- adding a conformance-specific exception hierarchy, logging stack, schema
  registry, or DTO layer
- leaking backend exception strings that may include secrets into diagnostics
- making invalid fixtures multi-concern when a single-concern fixture can prove
  the same contract rule
- proving only an empty-root failure; issue `#502` needs a realistic pass over
  the canonical corpus and a seeded violation in a temporary copy of a required
  contract fixture
- mutating source fixtures in place, relying on exact validator prose, or
  broadening the test into unrelated profile, schema, or live-backend behavior

## Authority and CLI

The published backend capability profile JSONs under
`contracts/profiles/backend/` are the single source of truth for the
profile-to-contract mapping. `raes_contracts.backend_profiles.load_backend_profile`
loads them through `BackendProfileModel` — a closed-world `ContractModel`
that validates `required_contracts` against the authoritative
`BACKEND_SUPPORTED_CONTRACT_IDS` set. The conformance runner reads its
required contract sets from those profiles; no second authority table
lives in code.

The canonical CLI surface is `raes conformance backend`, registered on the
Typer `raes_cli` app next to `raes sdl` and `raes processor`. It accepts
`--profile`, `--fixtures-root`, and `--profiles-root` overrides; the
defaults point at the canonical `contracts/` tree. The runner exits
non-zero when the report has any failing case or top-level diagnostic so
the command can be wired directly into CI gates.

## Observability and evidence fixture profile

`raes conformance backend --profile observability-evidence` selects the
ASR-525 corpus for backend manifests, capture specifications, evidence records,
derived measures, and run augmentation disclosures. It uses the same published
profile loader and fixture runner as the other profiles. Selecting this profile
is optional; it does not add contracts to other backend profiles or request
data collection from an executing backend.

The corpus accepts operational apparatus-only disclosure without augmentation
evidence, and checks the conditional environment, participant, and comparability
disclosures, including additive classifications. Negative cases distinguish
missing effects or markings from missing portable carriers, affected refs, and
purpose-required evidence. SDL fixtures separately demonstrate that an in-world
listener creates no experimental demand, while explicitly requesting its events
can require collection with retention and export disabled.

These are finite fixture checks. A passing report does not establish that a
live backend disclosed every actual augmentation, performed participant
visibility projection, captured evidence, or satisfied a task. Those claims
require their respective execution and evidence owners. In particular, the
evidence-bearing `experiment-run/v1` archive is not a universal requirement for
every execution: its reference artifacts do not impose experimental collection
on an SDL scenario with no such demand.

## Target Conformance Reference Scenario

Target conformance drives a provisioning/snapshot probe (issue #606) that proves
the target adapter accepts a plan, reports changed addresses, and mutates a
snapshot rather than passing on manifest shape alone. With a recording driver,
this is hermetic adapter evidence, not native libvirt or guest realization.
Native and guest certification require the stronger observation gates tracked
by issues #715-#717. The probe needs a scenario to exercise and defaults to a
generic linux-vm scenario (`_DEFAULT_CONFORMANCE_SCENARIO`).

A single hard-coded scenario wrongly assumes *every* backend can realize it.
Fixed-topology emulation backends (which map RAES nodes onto a pre-built
environment) and bounded simulation backends legitimately cannot realize an
arbitrary scenario, yet still honor the provisioning contract. `run_target_conformance`
therefore accepts an optional `reference_scenario` (issue #663): a backend or
caller supplies a scenario inside its declared envelope. The probe verifies
adapter-level accounting for that scenario; it does not upgrade driver-reported
facts to daemon- or guest-observed evidence.

Issue #100 publishes configuration-bound realization envelopes using the shared
parameterized SDL semantics from #667 and the membership/subsumption relation
from #668. Manifests, provisioning plans, and snapshots carry one immutable
envelope/configuration identity. For an envelope-bound target, target
conformance now derives deterministic positive witnesses and safe negative
probes through that shared relation. It does not fall back to
`_DEFAULT_CONFORMANCE_SCENARIO` when an envelope is non-constructive.

Each realization case records its `fixture-only`, `hermetic-live`, or
`native-live` execution basis, probe and probe-set digests, exact envelope and
configuration digests, operation accounting, declared and observed strength,
state-mutation checks, cleanup status, residual state, evidence references,
outcome, and diagnostics. Skipped and unsupported cases are gating failures;
only a passing `native-live` run can set `native_conformance`.

The execution seam is an injected operations-owned harness. It must supply an
independent expected-observation inventory and fresh addressed observations;
planned values, unbound or fabricated handles, stale samples, missing operation
results, silent transformations, and incomplete cleanup all fail closed.
Machine-readable reports are written only through the redaction-gated atomic
artifact path. The currently published open libvirt envelopes are deliberately
reported as non-constructive until the configuration-specific envelopes are
made executable; a caller-selected happy path cannot substitute for them.

Contract, adapter, native-daemon, and guest conformance remain distinct
reportable dimensions. The repository-wide guardrails for this work are recorded in the
[`issue #716 realization-honesty preflight`](../../decisions/issue-716-asr-519-realization-honesty-conformance-preflight.md).

## Participant-Policy Probes

API-407 lets a backend declare governed participant information-flow features
with a support strength. A declaration is not a realization, so
`run_target_conformance` accepts an optional `participant_policy_harness`
(issue #800).

**The runner owns execution and the verdict.** The harness supplies declarative
case inputs only — the deployment's validated exact-cut policy resolver, the
participant, audience, policy, projection and state-cut coordinates, the typed
carriers, the operation kind, and the expected disposition. It supplies no
control plane and no outcome. The runner constructs the real
`RuntimeControlPlane` on the target under evaluation, wraps that target's
participant runtime in a call counter, invokes the typed boundary itself, and
derives every reported fact. A harness able to supply the execution object or
the verdict could certify a backend it never ran. The harness is a typed
in-process option — never a module path, remote URL, or policy bag — and
operation kinds, not backend names, are the runner's dispatch key.

Each probe records a runner-derived ledger: whether the crossing was refused,
whether a participant-visible value was released, how many times the target's
participant runtime was actually invoked, whether any previously committed
append-only record moved, whether safe audit evidence appeared, and the declared
versus effective support strength. Every committed crossing record is
revalidated against the published API-423 contract, so a malformed record
cannot pass as a governed decision. Negative obligations assert the side-effect
boundary as well as the disposition — a refusal that already invoked the target
or serialized a participant-visible value is a failure.

Expectations are `denied`, `withheld`, or `released`. Denial and withholding
stay distinct because SEM-230 keeps refusal and intentional non-release as
separate transition facts; collapsing them would let a runtime that always
denies egress satisfy a claimed withholding obligation.

**Only an authorized outcome establishes a declared capability.** Failing closed
is what an absent implementation does too, so refusal-only coverage never marks
a feature as realized. A declared feature is covered only when a passing
`released` case resolved an effective backend strength against that target;
otherwise the feature gets an explicitly `unsupported`, non-passing case. The
same applies when no harness is supplied at all. Cases are never silently
skipped, and the fail-closed resolver used by unrelated adapter probes is not
participant-policy evidence.

Every participant-policy case carries a `policy_binding` whose `claim` is a real
`BehavioralClaimBindingModel`, so relation identity, carriers, quantifier and
evidence scope, assurance status, limitations, and nonclaims go through the same
catalog authority as the report claim. Alongside it the binding carries the
participant, audience, memory scope, policy id/revision/decision ref/state-cut
ref, declassification schedule, counterexample ref, and the named order,
scheduler, environment, nondeterminism, termination/progress, timing,
probability, and partial-order assumptions — declared fields, so the bindings
stay machine-reviewable rather than encoded in case names.

Finite probe results do not change what the report claims. The report relation
stays `bounded-probe-success`; a case may reference the SEM-230
`policy-noninterference` obligation it attempted to falsify, and that reference
is not an assertion that the obligation holds. Before any report is serialized
or persisted, `validate_backend_conformance_report` re-checks the report claim
and every case binding against the catalog, refuses a universal quantifier
backed only by finite evidence, refuses a `native_conformance` flag with no
natively-executed case, and refuses a claim whose cited cases — including
failed, unsupported, and counterexample cases — are not all present.

## Participant-Opacity Backend Probes

The `participant_predicate_opacity` family feature follows the same generic
target runner but is intentionally separate from participant-policy
operations. A typed in-process harness supplies only exact profile-bound case
inputs and an observation adapter. The runner instruments the target, invokes
both governed possible points, compares the complete closed transcript, and
owns the verdict. A declaration with no harness is an explicit unsupported
case; a harness that never calls the backend cannot claim backend-native
realization.

Each passing case carries three independent catalog-validated bindings:
`backend-declaration/declared/structural`,
`backend-realization/realized/finite`, and
`backend-conformance/conformant/finite`. The case separately records the
realization owner and execution basis, plus exact profile, manifest,
configuration, tool, environment, and probe-set digests. Report-level meaning
remains `bounded-probe-success`. A method, boolean, payload-redaction pair,
runtime-mediated denial, or `native-live` label cannot substitute for the
observed backend transcript, and finite conformance is not proof or universal
opacity.

## Non-Goals

This preflight does not implement `ASR-502`, change requirement status, add new
fixtures, add new schemas, migrate the CLI, or repair profile drift. It only
locks the repository-wide guardrails for the implementation work that follows.
