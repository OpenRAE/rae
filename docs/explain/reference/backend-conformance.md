# Backend conformance guardrails

This note is the architecture preflight for `ASR-502`. It is guidance, not an
implementation plan.

`ADR-009` makes `contracts/` the authority boundary for machine-readable
contracts, fixtures, and profiles. Backend conformance implementation code must
consume that authority. It must not recreate that authority in a runner-local
schema, fixture, or profile model.

## Architecture decisions

- Backend conformance is an implementation-side verifier under
  `implementations/python/packages/raes_conformance`. It is not a normative
  artifact family under `contracts/`.
- `contracts/fixtures/**/<contract-id>/{valid,invalid}/*.json` is the canonical
  fixture corpus. The runner may accept an override root for tests. The
  default root is the repository `contracts/fixtures` tree.
- `contracts/profiles/backend/*.json` is the canonical backend capability
  profile corpus. Load profile-to-contract requirements from these artifacts.
  Do not copy them into a second in-code table.
- Published payload validation must go through `raes_contracts.contracts`
  `ContractModel` descendants, `schema_bundle()`, and the existing semantic
  diagnostics helpers.
- Backend manifests must be rendered through
  `raes_backend_protocols.manifest.backend_manifest_payload()`. They must be
  validated as `backend-manifest-v2`. The conformance suite must not
  reassemble manifest JSON by hand.
- CLI entry points belong in the Typer-based `raes_cli` surface.
- End-to-end proof tests for backend conformance should exercise the public
  runner or CLI. They should run against a full backend profile and the
  published fixture corpus. Seeded-corruption tests should mutate a temporary
  copy of one existing required fixture. They should expect the shared
  conformance diagnostics to name the contract and the validation failure.

## Cross-cutting concerns

Reuse these existing surfaces before you add anything new:

- contract models and closed-world validation:
  `raes_contracts.contracts.ContractModel`, `BackendManifestV2Model`,
  runtime envelope models, plan models, and history event models
- contract publication inventory: `schema_bundle()` and
  `contracts/schema-publication-manifest.json`
- contract-corpus resolution: `raes_contracts.corpus.corpus_family_root()` with
  the `FIXTURES` and `PROFILES` family constants. With this seam, source
  checkouts and packaged installs resolve the same published corpus.
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

## Security and runtime gates

The conformance path touches these gates:

- JSON parsing: load only local fixture/profile files that explicit roots or
  canonical repo roots select. Do not fetch remote fixtures. Do not execute
  fixture content.
- Corpus path resolution: default fixture/profile roots must flow through
  `raes_contracts.corpus`. Tests may pass explicit temporary override roots for
  mutated corpora. Loaders must not add `Path(__file__).parents[N]`
  repo-root heuristics again.
- Profile id and path validation: profile ids must pass the backend-profile id
  grammar before path construction. Any caller-supplied `profiles_root`
  resolution must stay confined to that root.
- Contract shape validation: all fixture, manifest, plan, status, result,
  history, and snapshot payloads must pass the existing Pydantic contract
  models. They must also pass the closed-world `extra="forbid"` behavior.
- Manifest authority validation: `supported_contract_versions`,
  `concept_bindings`, capability vocabulary terms, and backend profile claims
  must resolve through existing authority helpers. They must not resolve
  through local string checks.
- Participant capability validation: role, behavior-feature, and
  interaction-feature support claims must resolve through the governed
  vocabulary scopes on `capabilities.participant_runtime`. Backend-specific
  terms must use the governed `x-<owner>:<term>` extension format.
- Participant capability evidence: standard API-405 claims must also have the
  published contract surfaces that
  `PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS` requires. A manifest can
  claim a role or feature without the runtime contract evidence surface that
  is necessary to check it. In that case, the conformance runner reports
  `conformance.unsupported-capability-claim`.
- Control-plane probe validation: target probes must use `RuntimeControlPlane`
  and existing operation receipt/status/snapshot envelopes. They must not use
  backend native objects.
- Error-envelope leakage: report failures as `Diagnostic` values with stable
  codes and messages. Do not show raw tracebacks, environment variables,
  bearer tokens, credentials, or backend-private object representations.
  Proof tests should assert stable `Diagnostic.code`, `contract_name`, and
  structured addresses. They should not assert exact Pydantic prose.
- Host/OS exposure: CLI options may accept profile names and local roots. They
  must not require secrets or bearer tokens in process argv. Live-target
  authentication belongs in headers or process-local configuration.
  Diagnostics must not echo that configuration.
- Persistence: the suite is report-oriented. It should not write durable
  state, except explicit report output that the caller requests.

## Extension boundary

The seam is the published contract id and backend profile artifact. It is not
a Python enum branch or hard-coded path. To add a backend profile or contract
family, you should only need to add the contract schema/fixtures/profile
artifact and register the matching validator once. You should not need to edit
every call site.

Keep the profile loader parameterized by `profiles_root`. Keep the fixture
runner parameterized by `fixtures_root`. Then tests can use temporary corpora,
and the default path stays the published `contracts/` tree.

Participant capability declarations follow the same extension boundary. API-405
adds governed vocabulary surfaces under `capabilities.participant_runtime`. It
does not add a backend-profile branch, snapshot metadata field, or
control-plane role. If the `participant_runtime` block is absent, the backend
declares no participant runtime surface. If the block is present, the role and
feature declarations are mandatory and set-like.

The standard terms are grounded in `docs/explain/sdl/lineage.md`, ADR-020,
ADR-022, and `specs/formal/participant-semantics/`. Exercise roles map to the
existing `white`/`green`/`red`/`blue` framing vocabulary. Behavior terms map to
the action, observation, state-transition, failure, temporal, attribution, and
outcome semantics that RAES already models. Interaction terms map to the
SEM-209 coordination, contention, interference, and shared-state classes.

Standard terms are not accepted as prose-only promises. Target conformance
checks that the manifest also declares the published participant episode or
behavior-history contract surfaces. These surfaces carry the evidence for
those claims.

DSL-437 autonomous execution is an additional fail-closed participant
capability. A backend can include `autonomous_execution` in
`supported_behavior_features`. That backend must set
`supports_autonomous_execution`. It must list its supported selection
strategies, exact action contracts, observation boundaries, target addresses,
and policy profiles. It must list positive finite limits for participants,
attempts, in-flight actions, occurrences, retries per occurrence, and burst
size.

The backend must also publish relational execution bindings, all six
generation-fenced lifecycle controls, and bounded-concurrency support. It must
publish finite execution-service and concurrent-action limits too. The planner
compares each compiled action-to-target relation. It does not accept the
Cartesian product of separate action and target lists. The planner also
compares the required feature set of the parent behavior specification with
the runtime capability.

Runtime target registration requires the autonomous native-binding,
execution-control/readback, and bounded-batch methods. This is admission
evidence only. Conformance also requires the backend participant runtime to
invoke its native service adapter. The runtime must return a typed terminal
action outcome at the bound temporal coordinate. This outcome is distinct from
control-operation success.

The runtime must also keep episode, behavior-history, temporal-context, and
typed scheduler readback in durable and conformance snapshots. Stepped cadence
points must be reachable. The portable runtime drives real-time and dilated
participant cadence. Externally paced autonomous execution is not admissible
until a portable transition-notification contract is governed. Durable
readback must agree across scheduler policy identity, clock segment/lifecycle,
and live participant episode.

Conditional live conformance drives two bounded native actions. It also drives
start, pause, resume, bounded drain, reset, stale-generation fencing, and
teardown. Inert method implementations fail, and missing transition evidence
fails. The shared participant base exposes readback only. It cannot make a
backend lifecycle claim pass. Each successful control operation must come from
the backend handler, and it must produce changed action-specific readback and
new evidence.

The explicit `participant-autonomous-execution/v2` profile also requires exact
support for all governed activity features, `weighted` selection, shared-time
`window` constraints, and `blake3-xof-participant-v1`. The runtime records
dependency, retry, cooldown, burst, timing-disposition, and safe random-address
facts. It records these facts in typed continuation and participant behavior
history.

A backend must not substitute the experiment-selection `blake3-xof-v1`
address/profile. It must not silently drop occurrence provenance. It must not
treat an apparatus stochastic-control declaration as scenario variation.
Missing exact support fails planning.

The `participant-autonomous-execution/v3` profile also requires a closed
`resource_budgets` capability under the existing participant-runtime root.
Admission matches the complete compiled resource vector against declared
owner/resource/accounting/reset/fairness support and configuration-bound pool
entries. Owner, unit, meter, accounting mode, and capacity must match exactly.
Declared cross-range pools require `tenant_partitioned` isolation. Admission
is atomic. Thus a backend cannot accept action/concurrency bounds while it
drops storage, token, image, accelerator, ancestor, or fairness obligations.

Runtime conformance then requires typed, generation-fenced, policy-scoped
budget state. It also requires one canonical cross-policy pool allocation
ledger. It also requires append-only reserve, measured commit, release,
throttle, and reconcile events. Native commits require a complete matching
measurement vector and evidence. Manifest support and configured capacity do
not count as measured-realization evidence.

## Gotchas and anti-patterns

Avoid:

- treating semantic profiles in `contracts/profiles/semantic` as backend
  capability profiles
- keeping a duplicate `_PROFILE_REQUIREMENTS` authority table after backend
  profile artifacts exist
- accepting `backend-manifest-v1` or legacy conformance paths as current
  defaults
- changing `contracts/schemas/` without the
  `contracts/schema-publication-manifest.json` change ledger, or changing only
  reference implementation models and not the published schema authority
- validating fixtures with ad hoc JSON key checks when contract models already
  exist
- adding a conformance-specific exception hierarchy, logging stack, schema
  registry, or DTO layer
- leaking backend exception strings that may include secrets into diagnostics
- making invalid fixtures multi-concern when a single-concern fixture can prove
  the same contract rule
- proving only an empty-root failure. Issue `#502` needs a realistic pass over
  the canonical corpus. It also needs a seeded violation in a temporary copy of
  a required contract fixture.
- mutating source fixtures in place, relying on exact validator prose, or
  making the test cover unrelated profile, schema, or live-backend behavior

## Authority and CLI

The published backend capability profile JSONs under
`contracts/profiles/backend/` are the single source of truth for the
profile-to-contract mapping. `raes_contracts.backend_profiles.load_backend_profile`
loads them through `BackendProfileModel`. This model is a closed-world
`ContractModel`. It validates `required_contracts` against the authoritative
`BACKEND_SUPPORTED_CONTRACT_IDS` set. The conformance runner reads its
required contract sets from those profiles. No second authority table lives in
code.

The canonical CLI surface is `raes conformance backend`. It is registered on
the Typer `raes_cli` app next to `raes sdl` and `raes processor`. It accepts
`--profile`, `--fixtures-root`, and `--profiles-root` overrides. The defaults
point at the canonical `contracts/` tree. The runner exits non-zero when the
report has any failing case or top-level diagnostic. Thus CI gates can run the
command directly. If a fixture file cannot be read, the command writes an error
to standard error, writes no report, and exits with status 1.

## Observability and evidence fixture profile

`raes conformance backend --profile observability-evidence` selects the
ASR-525 corpus. This corpus covers backend manifests, capture specifications,
evidence records, derived measures, and run augmentation disclosures. It uses
the same published profile loader and fixture runner as the other profiles.
This profile is optional. It does not add contracts to other backend profiles.
It does not request data collection from an executing backend.

The corpus accepts operational apparatus-only disclosure without augmentation
evidence. It also checks the conditional environment, participant, and
comparability disclosures, including additive classifications. Negative cases
separate missing effects or markings from missing portable carriers, affected
refs, and purpose-required evidence. SDL fixtures separately show that an
in-world listener creates no experimental demand. They also show that an
explicit request for its events can require collection with retention and
export disabled.

These are finite fixture checks. A passing report does not prove that a live
backend disclosed every actual augmentation. It also does not prove that the
backend performed participant visibility projection, captured evidence, or
satisfied a task. Those claims require their respective execution and evidence
owners. In particular, the evidence-bearing `experiment-run/v1` archive is not
a universal requirement for every execution. Its reference artifacts do not
impose experimental collection on an SDL scenario with no such demand.

## Target conformance reference scenario

Target conformance drives a provisioning/snapshot probe (issue #606). The probe
proves that the target adapter accepts a plan, reports changed addresses, and
mutates a snapshot. Thus the target does not pass on manifest shape alone.
With a recording driver, this is hermetic adapter evidence, not native or guest
realization. Native and guest certification require stronger observation
gates that the backend distribution supplies. The probe needs a scenario to
exercise, and it defaults to a generic linux-vm scenario
(`_DEFAULT_CONFORMANCE_SCENARIO`).

A single hard-coded scenario wrongly assumes that *every* backend can realize
it. Fixed-topology emulation backends map RAES nodes onto a pre-built
environment. These backends and bounded simulation backends legitimately
cannot realize an arbitrary scenario. But they still honor the provisioning
contract. Thus `run_target_conformance` accepts an optional
`reference_scenario` (issue #663). A backend or caller supplies a scenario
inside its declared envelope.

The probe verifies adapter-level accounting for that scenario. It does not
upgrade driver-reported facts to daemon- or guest-observed evidence.

Issue #100 publishes configuration-bound realization envelopes. These
envelopes use the shared parameterized SDL semantics from #667 and the
membership/subsumption relation from #668. Manifests, provisioning plans, and
snapshots carry one immutable envelope/configuration identity. For an
envelope-bound target, target conformance now derives deterministic positive
witnesses and safe negative probes through that shared relation. It does not
fall back to `_DEFAULT_CONFORMANCE_SCENARIO` when an envelope is
non-constructive.

Each realization case records its `fixture-only`, `hermetic-live`, or
`native-live` execution basis. It also records probe and probe-set digests,
exact envelope and configuration digests, and operation accounting. It records
declared and observed strength, state-mutation checks, cleanup status, and
residual state. It also records evidence references, outcome, and diagnostics.
Skipped and unsupported cases are gating failures. Only a passing
`native-live` run can set `native_conformance`.

The execution seam is an injected operations-owned harness. It must supply an
independent expected-observation inventory and fresh addressed observations.
These conditions all fail closed: planned values, unbound or fabricated
handles, stale samples, missing operation results, silent transformations, and
incomplete cleanup. Machine-readable reports are written only through the
redaction-gated atomic artifact path.

The published open libvirt-qemu envelopes are deliberately reported as
non-constructive. A caller-selected happy path cannot substitute for them.
RAES ships no concrete backend; see
[ADR-115](../../decisions/adrs/adr-115-concrete-backends-owned-outside-raes.md).

Contract, adapter, native-daemon, and guest conformance remain distinct
reportable dimensions. The
[`issue #716 realization-honesty preflight`](../../decisions/issue-716-asr-519-realization-honesty-conformance-preflight.md)
records the repository-wide guardrails for this work.

## Materialization producers

A target can declare `backend-materialization-attestation-v1` and
`backend-runtime-descendants-v1`. For that target, the runner plans the probe
with a new `PlanScope`. The scope binds `RuntimeTarget.name` and a fresh
`target-conformance-<id>` run identity. The control plane gets the matching
`run:<id>` scope.

The runner also supplies a `RunMaterializationArchive` in a private temporary
directory. The runner removes the directory after every probe runtime closes.
If a runtime cannot drain its backend calls, the directory stays and the runner
raises the drain error. The report contains no archive path. The backend must return a valid report, and
the runtime must admit and archive it. Otherwise the provisioning probe fails.
The snapshot probe then requires an archived attestation record
(`conformance.materialization-not-archived`).

The snapshot probe validates the same `runtime-snapshot-v1` projection that the
control-plane API publishes. Positive realization probes use the same run scope
rule. A planning error fails the positive probe before the harness runs.
Targets without the attestation contract keep the unscoped probe. See the
[issue #1667 design](../../decisions/issue-1667-target-materialization-conformance-design.md).

## Participant-policy probes

API-407 lets a backend declare governed participant information-flow features
with a support strength. A declaration is not a realization. Thus
`run_target_conformance` accepts an optional `participant_policy_harness`
(issue #800).

**The runner owns execution and the verdict.** The harness supplies
declarative case inputs only. These inputs are the validated exact-cut policy
resolver of the deployment, the participant, audience, policy, projection and
state-cut coordinates, the typed carriers, the operation kind, and the expected
disposition. The harness supplies no control plane and no outcome.

The runner constructs the real `RuntimeControlPlane` on the target under
evaluation. It wraps the participant runtime of that target in a call counter.
It invokes the typed boundary itself and derives every reported fact. A
harness that could supply the execution object or the verdict could certify a
backend that it never ran. The harness is a typed in-process option. It is
never a module path, remote URL, or policy bag. Operation kinds, not backend
names, are the dispatch key of the runner.

Each probe records a ledger that the runner derives. The ledger shows whether
the crossing was refused and whether a participant-visible value was released.
It shows how many times the participant runtime of the target was actually
invoked. It shows whether any previously committed append-only record moved
and whether safe audit evidence appeared. It also shows the declared versus
effective support strength.

The runner revalidates every committed crossing record against the published
API-423 contract. Thus a malformed record cannot pass as a governed decision.
Negative obligations assert the side-effect boundary as well as the
disposition. A refusal that already invoked the target or serialized a
participant-visible value is a failure.

Expectations are `denied`, `withheld`, or `released`. Denial and withholding
stay distinct because SEM-230 keeps refusal and intentional non-release as
separate transition facts. If the two collapsed, a runtime that always denies
egress could satisfy a claimed withholding obligation.

**Only an authorized outcome establishes a declared capability.** An absent
implementation also fails closed. Thus refusal-only coverage never marks a
feature as realized. A declared feature is covered only when a passing
`released` case resolved an effective backend strength against that target.
Otherwise the feature gets an explicitly `unsupported`, non-passing case. The
same rule applies when no harness is supplied at all.

Cases are never silently skipped. The fail-closed resolver that unrelated
adapter probes use is not participant-policy evidence.

Every participant-policy case carries a `policy_binding`. The `claim` of that
binding is a real `BehavioralClaimBindingModel`. Thus relation identity,
carriers, quantifier and evidence scope, assurance status, limitations, and
nonclaims go through the same catalog authority as the report claim. The
binding also carries the participant, audience, memory scope, policy
id/revision/decision ref/state-cut ref, declassification schedule, and
counterexample ref. It also carries the named order, scheduler, environment,
nondeterminism, termination/progress, timing, probability, and partial-order
assumptions. These are declared fields, so the bindings stay
machine-reviewable and are not encoded in case names.

Finite probe results do not change what the report claims. The report relation
stays `bounded-probe-success`. A case may reference the SEM-230
`policy-noninterference` obligation that it attempted to falsify. That
reference is not an assertion that the obligation holds.

`validate_backend_conformance_report` runs before any report is serialized or
persisted. It re-checks the report claim and every case binding against the
catalog. It refuses a universal quantifier that only finite evidence backs. It
refuses a `native_conformance` flag with no natively-executed case. It also
refuses a claim when its cited cases are not all present. This includes
failed, unsupported, and counterexample cases.

## Participant-opacity backend probes

The `participant_predicate_opacity` family feature follows the same generic
target runner. But it is intentionally separate from participant-policy
operations. A typed in-process harness supplies only exact profile-bound case
inputs and an observation adapter. The runner instruments the target and
invokes both governed possible points. It compares the complete closed
transcript and owns the verdict. A declaration with no harness is an explicit
unsupported case. A harness that never calls the backend cannot claim
backend-native realization.

Each passing case carries three independent catalog-validated bindings:
`backend-declaration/declared/structural`,
`backend-realization/realized/finite`, and
`backend-conformance/conformant/finite`. The case separately records the
realization owner and execution basis. It also records exact profile,
manifest, configuration, tool, environment, and probe-set digests. Report-level
meaning stays `bounded-probe-success`.

These items cannot substitute for the observed backend transcript: a method, a
boolean, a payload-redaction pair, a runtime-mediated denial, or a
`native-live` label. Finite conformance is not proof, and it is not universal
opacity.

## Non-goals

This preflight does not implement `ASR-502` or change requirement status. It
does not add new fixtures or new schemas. It does not migrate the CLI or repair
profile drift. It only locks the repository-wide guardrails for the
implementation work that follows.

## Participant tool profiles (API-414)

Processor `capabilities.participant_tools` declares ACT-619 semantic revision support.
Backend `capabilities.participant_runtime.tool_profiles` declares revisions and numeric capacity.
Backend feature strength remains in the existing `feature_support` list.
`tool_affordances` and `scoped_tool_affordances` require explicit evidence references.
They are declaration features. They are separate from runtime information-flow
policy enforcement.

Planning derives requirements from actual instantiated bindings and bound actions.
It checks each selected processor and backend independently.
Trial admission uses the same comparison before sealing entries.
Runtime apply checks backend support again before dispatch.

Static tool-feature cases record declared support and leave effective support unset.
Their execution basis remains `fixture-only`.
They cannot establish native tool execution from an evidence reference.
Observed runtime probes retain separate cases and execution bases.
See the [design](../../decisions/issue-304-participant-tool-support.md)
and [migration rules](../../migration/participant-tool-support.md).
