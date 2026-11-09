# Autonomous behavior vocabulary bindings

## Scope

This specification defines how RAES behavior specifications may be related to
versioned external vocabularies for autonomous services and agents under
ACT-611.

It composes two existing authorities:

- ADR-067 and the participant behavior model own native RAES behavior meaning;
- `external-concept-bindings/v1` owns portable assertions about exact RAES
  subjects and arbitrary external concepts.

ACT-611 adds source snapshots and examples at that composition boundary. It
does not add SDL syntax, a participant subtype, a native autonomous-behavior
taxonomy, or another resolver.

## Initial schemes

<!-- vale RAES.HeadingCase = NO -->
### W3C ActivityStreams activity types

The directly adopted external identifiers are the 28 Activity types listed by
the dated W3C Activity Vocabulary Recommendation of 23 May 2017.

<!-- vale RAES.HeadingCase = YES -->

| Coordinate | Value |
| --- | --- |
| `scheme_id` | `w3c-activitystreams-activity-types` |
| `authority` | `World Wide Web Consortium` |
| `revision` | `REC-activitystreams-vocabulary-20170523` |
| source record | `contracts/concept-authority/w3c-activitystreams-activity-types-source-v1.json` |

Each `concept_id` is the full normative IRI, such as
`https://www.w3.org/ns/activitystreams#Create`. The adapter does not shorten,
case-fold, translate, merge, or deduplicate these identifiers.

`Application` and `Service` are ActivityStreams Actor/Object types. They are
not members of this behavior scheme, do not become RAES participant types, and
do not prove that an authored behavior is autonomous.

<!-- vale RAES.HeadingCase = NO -->
### FIPA communicative act library

The second scheme publishes the 22 exact lower-case communicative-act symbols
from FIPA specification SC00037J, Standard status dated 2002-12-03.

<!-- vale RAES.HeadingCase = YES -->

| Coordinate | Value |
| --- | --- |
| `scheme_id` | `fipa-communicative-act-library` |
| `authority` | `Foundation for Intelligent Physical Agents` |
| `revision` | `SC00037J-2002-12-03` |
| source record | `contracts/concept-authority/fipa-communicative-acts-source-v1.json` |

Symbols such as `inform`, `request`, `cfp`, and `not-understood` are external
annotations only. A binding does not import FIPA mental-state semantics,
feasibility preconditions, rational effects, message transport, content
language, or interaction protocols, and it does not claim FIPA ACL
conformance.

The required HTML locator contains dynamically rewritten email-protection
markup, so it is not byte-stable. The source record retains that locator and
pins the stable official `SC00037J.pdf` representation by SHA-256. The
maintenance verifier checks the PDF bytes and separately confirms the exact
act identifiers in the HTML specification.

## Candidate decisions

The complete primary-source comparison is recorded in
`docs/decisions/issue-211-act-611-autonomous-behavior-vocabularies-preflight.md`.
Its decisions are:

- directly adopt the W3C ActivityStreams Activity type IRIs;
- use the FIPA communicative-act symbols only as external annotations;
- do not use PROV-O `Activity`, `Agent`, or `SoftwareAgent` as behavior
  classifications because they own provenance and responsibility semantics;
- defer IEEE 1872.2 terms to robot-specific future work that can pin an exact
  licensed source revision and prove correspondence to the standard.

No copied FIPA formal model or purchased IEEE standard text is published.
Source records contain identifiers, citations, rights notices, and locally
authored scope constraints rather than copied definitions.

## Exact behavior subject

An ACT-611 assertion targets the exact coordinate returned by
`external_concept_subjects()` for a behavior declaration:

```yaml
subject:
  subject_kind: behavior_specifications
  owning_contract_id: sdl-authoring-input-v1
  lifecycle_phase: normalized-authoring
  canonical_ref: behavior_specifications.service-publication
  artifact_digest: sha256:<canonical SDL digest>
```

The behavior specification remains a complete native aggregate over its
participants, actions, observations, outcomes, authority/scope, behavior mode,
realization, and evidence. The external assertion only relates that aggregate
to another scheme. A map key, `spec_id`, participant name, label, compiled
address, JSON Pointer, or unqualified string is not an identity substitute.

## Portable assertion semantics

Both initial schemes use the unchanged
`external-concept-bindings/v1` syntax. Relationship, motivation, semantic
effect, perspective, provenance, evidence references, confidence,
approximation or loss, limitations, participant eligibility, and review status
retain their portable contract meanings.

Conservative behavior bindings use `related-to` and `annotates` with explicit
loss and limitations. Stronger `equivalent-to`, `aligns`, `refines`, or
`constrains` claims require independent review support. Even a resolved
`constrains` assertion has no validation effect unless an existing governed
RAES consumer independently owns that constraint.

External terms never replace or create:

- action contracts or executable actions;
- observation boundaries, outcomes, or runtime evidence;
- authority, operating scope, capabilities, or authorization;
- realization or participant information-flow controls;
- behavior modes or proof of autonomous execution.

Participant availability remains `eligibility-only`; disclosure, exposure,
delivery, and understanding continue through their existing deny-first
boundaries.

## Offline admission and extensibility

Each source-specific adapter projects its pinned record to
`ExternalConceptSchemeSnapshotModel`. It preserves the concept list, including
candidate multiplicity. Both schemes then use the same structural model,
exact-subject projection, and `admit_external_concept_bindings()` operation.

Normal loading and admission perform no network, environment, plugin,
subprocess, or latest-version lookup. The resolver continues to report
deterministic `resolved-current`, `unavailable`, `stale`, `ambiguous`,
`superseded`, `unknown-concept`, and `subject-not-found` outcomes.

A future third scheme adds its own source record/model/schema, corpus loader,
snapshot adapter, source-integrity proof, and fixtures. It must not add a
scheme discriminator to the authored contract, branch the resolver by
`scheme_id`, or create a global external-ontology registry.

## Conformance

The two valid fixtures are:

- `contracts/fixtures/concept-authority/external-concept-bindings-v1/valid/activitystreams-behavior.json`;
- `contracts/fixtures/concept-authority/external-concept-bindings-v1/valid/fipa-behavior.json`.

They target declarations in the focused
`context/autonomous-behavior-subject.sdl.yaml` artifact and exercise the same
published schema, conformance registration, exact subject adapter, neutral
snapshot, and offline admission function.

`tools/check_autonomous_behavior_vocabularies.py` enforces pinned metadata and
identifier order offline. Its optional `--verify-remote` maintenance mode is
limited to the official W3C and FIPA HTTPS hosts; normal conformance never
invokes it.

## Requirement

- ACT-611: autonomous service and agent behavior vocabularies.
