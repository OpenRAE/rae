# Catalog 5 - Observability and Evidence Planes

This catalog states SDL authoring rules for ADR-066. The implemented
`evidence_requirements` top-level section carries authored capture intent;
scenario-native observability remains expressed through the relevant node
runtime families. A future field still has to update `sections.md`,
`references.md`, the published SDL schemas, the reference implementation,
fixtures, and tests.

## Plane Rule

An SDL authoring construct that makes an observability or evidence claim MUST
have a primary plane:

- scenario-native observability;
- authored evidence requirement;
- processor/backend operational observability;
- captured evidence; or
- derived analysis.

The carrier decides the plane. A string such as `log`, `trace`, `telemetry`,
`observation`, or `evidence` does not decide meaning on its own.

## Scenario-Native Observability

A scenario-native observability system is an in-world resource. It may be a
runtime service, sensor, detection engine, monitoring manager, telemetry
collector, tracing backend, metrics store, dashboard, forwarding agent, or
comparable scenario element when the scenario makes that system part of the
environment.

Scenario-native observability systems:

- MUST have stable SDL identity when they are targetable;
- MUST use the runtime-family model under `nodes.<node>.runtime.*` when the
  system is node-scoped logical service state;
- MAY use existing runtime families such as `network_sensors`,
  `network_detection_engines`, `security_monitoring_managers`,
  `forwarding_agents`, `service_listeners`, `platform_applications`, or
  `datastore_services` when those families carry the intended meaning;
- MUST NOT be represented as a generic top-level observability bag; and
- MUST NOT satisfy an authored evidence requirement merely by existing.

A new runtime family is appropriate only when the observability system has a
distinct product-neutral logical service identity, collection name, primary id,
child-ref tree, owning ADR, schema, validation, and tests.

## Authored Evidence Requirements

An authored evidence requirement says what data, evidence, or output must be
captured. It is an authoring obligation, not proof of capture.

SDL carries authored evidence requirements in the map-keyed
`evidence_requirements` section. Each entry is a portable capture-intent
declaration. It may cite a scenario-native observability runtime-family ref as
one source, but that source remains an in-world system and does not satisfy the
requirement merely by existing.

An authored evidence requirement MUST declare:

- the source refs or source class;
- the scope refs or scope;
- the capture window, trigger ref, boundary ref, or comparable boundary kind;
- the channel, channel refs, modality, or boundary kind;
- expected artifact role or media kind when applicable;
- sensitivity and redaction expectation;
- integrity or chain-of-custody expectation when applicable; and
- loss-disclosure expectation.

Requirements intended for executable admission also declare an exact
`output_contract` and one or more RFC 6901 `field_selectors`. These terms are
capture demand: they say which structured evidence fields must be emitted, not
merely which artifact type or channel may exist.

Authored evidence requirements:

- MAY reference a scenario-native observability system as a source;
- MAY map to `experiment-capture-spec-v1` concepts when executable capture
  contracts are generated;
- MUST remain independent of participant `objectives`;
- MUST NOT be objective targets or implied by objective success criteria;
- MUST remain distinct from `experiment-evidence-record-v1` raw evidence; and
- MUST remain distinct from `experiment-derived-measure-v1` interpreted
  outputs.

### Scoped observation demand

An evidence requirement may carry one `observation_demand` rule from the
versioned `observation-demand-v1` normal form. The rule independently states:

- purpose: experimental, realization description, or operational;
- mode: inherit, none, operational-only, selected, or exhaustive within a
  named finite coverage profile;
- a semantic-scope selector over fields, streams, or artifacts; and
- collection, retention, export, prohibition, redaction, integrity, and
  requested reporting basis.

An absent demand never means capture everything. At the root it means no
experimental data is requested, while separately owned operational checks may
still execute without becoming study evidence. Selected demand reaches only
its resolved selectors. Exhaustive demand is finite within its named coverage
profile. Experimental retention and export are disabled unless explicitly
required.

The nearest authored declaration resolves each axis independently. Normalization
preserves a separate homogeneous obligation for each selector and authority;
requiredness or retention for one stream MUST NOT apply to an unrelated stream.
Selectorless policies govern their scope. Explicit prohibitions accumulate,
required rules from independent authorities compose, and conflicting uses of
overlapping selected data fail before collection. An omitted lifecycle axis is
not an explicit prohibition or disabling constraint on another authority.
Realization
precision, closure, image identity, filesystem detail, or backend capability
MUST NOT imply observation, retention, or export.

Authored component references are validated against SDL declarations and then
compiled to their unique canonical runtime addresses. Runtime demand matching
uses those addresses. When a more-specific descendant policy applies, it
partitions the broader selector; a positive ancestor rule MUST NOT bypass a
descendant prohibition or no-data rule. The normalized broad selector MUST
carry the excluded descendant scopes so collection remains permitted over its
unexcluded sibling remainder; inherited selectors are clipped to each child
partition, including mandatory selectors. Fully inherited selector regions
have one effective scope owner; a broader
rule scope MUST NOT cause duplicate collection of the same inherited selector.
Collection-member identities and authored exclusions MUST resolve uniquely
through the shared semantic address
resolver. Backend runtime support MUST be registered as a
stable selector-family pattern and MUST resolve each scenario-specific selector
to one unambiguous most-specific capability before any side effect.

All phase plans carry the normalized demand so each is meaningful when
submitted independently. Composite execution MUST designate exactly one phase
as the observation owner: the last actionable backend phase, or provisioning
when no later phase is actionable. Only that phase executes the shared demand
during composite apply.

Protected values explicitly selected for retention MUST be committed atomically
with terminal operation state. This store transaction is not a transaction over
backend resources: the current runtime MUST reject mandatory observation demand
combined with actionable backend operations before mutation, because it has no
compensating execution owner. Required read-only demand and supported optional
demand can execute through registered adapters. Export demand MUST be rejected
until a governed delivery owner exists; staging an outbox is not delivery.

Realization-description values selected for reporting are projected to the
canonical experiment realized-form disclosure contract. Backend-selected
compute-substrate descriptions use already-bound apparatus metadata without
probing. A nonretained description is available only in the immediate manager
result, not control-plane lookup, recovery, or a lifetime cache. Only explicit
retention permits storing its protected body. Native backend readback used for
operational validation travels as transient apply-result data, not persisted
snapshot observations. Demand selects optional native probes before the driver
observe call; required ownership, readiness, and security checks remain active.
If native readback fails after successful resource mutation, the operation MUST
fail while preserving the changed, contract-valid inventory for recovery and
cleanup. Missing data, malformed results, and readback exceptions MUST NOT
restore an obsolete snapshot or create new successful observation claims.

The task, run-plan, and capture-specification carriers declare policy; they do
not implement live capture or export. Those execution integrations remain with
#1112 and #1209. Unsupported mandatory selectors fail admission, and the current
runtime rejects requested export regardless of optionality.

### Forwarding agents used as measurement apparatus

A forwarding agent whose `ownership_role` is `measurement_apparatus` MUST be
named by at least one inbound apparatus-class evidence requirement through
`source_refs`. An apparatus-class requirement MUST NOT target a forwarding
agent whose role is `system_under_test`. The forwarding agent remains the
source inventory; the evidence requirement owns channel, artifact role,
sensitivity, redaction, integrity, retention, loss, and abstract destination
semantics.

The agent MUST NOT duplicate that relation with evidence refs and MUST NOT
carry an evidence path, pack URI, storage credential, or capture payload.
Environment-visible or comparability-relevant apparatus additionally maps to
the existing run-level augmentation disclosure. Neither ownership role nor a
configured ship target proves delivery or captured evidence.

## Processor/Backend Operational Observability

Processor/backend operational observability includes apparatus logs,
diagnostics, audit records, health checks, traces, setup evidence, measurement
channels, and capability declarations. These facts are not scenario meaning
unless an SDL or runtime contract explicitly projects them.

Mandatory internal inputs for readiness, reconciliation, and execution remain
under their existing owners. Native compute-substrate observation is a distinct
readback action and occurs only when explicit effective collection demand
selects it; realization posture or backend capability alone does not create that
demand.

SDL authoring MUST NOT depend on backend-private object ids, raw trace payloads,
operator secrets, process argv, environment dumps, full stack traces, or
diagnostic text as portable evidence or participant-visible state.

## Captured Evidence And Derived Analysis

Captured evidence belongs to evidence records or artifact references. Derived
analysis belongs to derived measures, result summaries, outcome
interpretations, studies, reports, exports, or claims.

SDL authoring MAY name the requirement or source that later evidence must
satisfy, but it MUST NOT treat a captured artifact, backend log, result
summary, metric value, or analysis output as the authored requirement itself.

Derived analysis MUST cite source evidence before it supports a claim. Hidden
truth, hidden answer keys, evaluator state, private traces, prompts, secrets,
and adjudication assets MUST NOT become participant-visible or public analysis
content without an explicit marking, redaction, and authorization boundary.

## Required-Capture Admission

Every explicit SDL or experiment capture demand is conjunctive. Before any
effect, the selected backend must provide one coherent versioned capture offer
that covers the demand's output contract and fields together with its artifact,
media, capture, source, scope, exact authored scope refs, channel, window,
integrity, sensitivity, loss/redaction, the exact redaction-policy identity,
retention, and export terms. Scope-ref offers name concrete targets; wildcard
scope refs are not admission authority. Support must not be synthesized by
combining legacy capability lists or independent offers.

An absent offer, or an offer marked unsupported, unavailable, lossy, redacted,
or withheld where the demand requires available complete full capture, fails
admission. Precise images, files, packages, and other installation detail do
not create capture demand by themselves.

An SDL requirement that names `capture_spec_ref` and
`capture_requirement_ref` must name both. It fails closed until the exact
capture-spec payload is available for resolution; a matching backend offer
cannot substitute for the referenced governed requirement.

After a run, a satisfaction claim is valid only when the task requirement
resolves through the admitted capture specification and evidence record to one
emitted artifact whose supplied bytes, digest, media/role, integrity mode, and
required fields validate through both the published schema and the owning
semantic model. Evidence-based study conditions consume only those validated
bindings, never run reference metadata. The record timestamp must also fall
inside the resolved capture window (and the run bounds for run/task windows). A redacted
record must bind the exact governed policy and fails closed unless a content
verifier for that policy is available. Artifact `satisfies_refs`, URIs, summaries, and
backend assertions are not content proof.

## Augmentation

When processor or backend augmentation is represented in SDL-adjacent
contracts, the augmentation classification is additive:

- `apparatus_only`;
- `environment_visible`;
- `participant_visible`; and
- `comparability_relevant`.

Participant-visible augmentation MUST route through visibility projection and
participant observation rules. Environment-visible and comparability-relevant
augmentation MUST have first-class provenance or evidence disclosure. They MUST
NOT be hidden in metadata, diagnostics, audit blobs, backend-native DTOs, or
raw logs.

Run-level processor/backend augmentation disclosures are carried by
`experiment-run-v1` `augmentation_disclosures`. That carrier records the
augmentation purpose, realization layer, additive classifications, portable
carrier refs, disclosure policy, markings, observer/comparability effects, and
run-traced evidence refs. SDL authoring that depends on augmentation output
must map to that run-provenance carrier rather than relying on backend logs,
free-form metadata, evaluator internals, or untyped diagnostic text.

## Reference And Validation Requirements

Future SDL fields for this catalog must satisfy the existing SDL gates:

- parser and model closure through `SDLModel`;
- concrete identifier keys, with no `${var}` placeholders in symbol-defining
  keys;
- fail-closed reference resolution through `references.md`;
- instantiation followed by full semantic revalidation;
- controlled vocabulary or concept-authority bindings for portable kinds;
- published schema parity with the reference implementation; and
- ADR-056/057 redaction for observed values and secret-bearing facts.

## Extension Rule

To add a scenario-native observability or authored evidence-requirement
surface, update the canonical catalogs instead of adding parallel prose:

1. add or amend the owning ADR;
2. add a row to `sections.md` and reference edges to `references.md` when a new
   SDL field exists;
3. add a runtime-family row to `runtime-inventory.md` when the surface is a
   node-scoped logical service;
4. update published schemas and the schema publication manifest when the
   structural contract changes;
5. update semantic validation and fixtures; and
6. add positive and negative tests from
   `specs/formal/observability-evidence-plane.md`.
