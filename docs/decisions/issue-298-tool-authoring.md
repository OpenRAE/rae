# Issue #298 — Participant tool authoring across imports

Date: 2026-10-13. Delivery: DSL-117 and PR #1440.

## Decision

Keep the tool-affordance binding of the issue-294 preflight: `tool_ref`,
`action_contract_refs` and `observation_boundary_refs`. Composition rewrites an
imported unit's `tool_ref` like the unit's other references to its own
declarations (ADR-053; ADR-076 section 3). A bare name of a unit content
declaration goes through the unit's content symbols. Any other spelling,
including the section-qualified `content.<name>`, goes through the unit's named
symbols. Either spelling therefore binds the unit's own content in every
import, and declaration rename, which shares this rewrite, renames either
spelling. A ref that names a unit declaration of another kind keeps that
binding and fails with the standalone kind diagnostic. A ref that names nothing
in the unit stays unchanged and resolves against the complete composed
scenario, as the [issue-297 decision](issue-297-behavior-authoring.md)
requires.

Before an import is namespaced, composition resolves each authored `tool_ref`
of the unit through the unit's own declaration index, the index that standalone
validation uses. A ref with more than one candidate fails composition with the
standalone diagnostic, `... tool_ref '<ref>' is ambiguous; use one of: ...`. It
lists the unit's own addresses and is anchored at the unit file. Composition
never binds such a ref by section order or section preference (ADR-076 section
3; `specs/sdl/references.md` section 4). The check covers one field. It is not
the per-fragment semantic validation that the issue-297 decision rules out, and
it rejects only refs that the unit alone already rejects as ambiguous.

Three boundaries follow from accepted records. They are settled, not gaps:

- An unsupported access channel, such as `channel: telnet`, in an imported unit
  raises `SDLParseError` with the unit file and the
  `/agents/<name>/interactive_access/<id>/channel` pointer, as in a root
  document (issue-297 decision).
- Role selectors in a unit select every participant with that role in the
  composed scenario (issue-297 decision). A reusable tool binding uses explicit
  `participant_refs`.
- An importing scenario cannot add a tool affordance for an imported
  participant. ADR-053 rejects overlay patches of imported declarations, and
  the issue-294 preflight requires the participant's own observation boundary
  to classify the affordance without widening its view authority. The
  supported forms are a unit that declares and exports the affordance, and an
  importer that declares its own participant over imported actions and tools.
  ADR-053 keeps targeted patches as a later option; this decision does not
  propose them.

A tool affordance and its observation-boundary classification designate a
tool. They do not authorize it. Authority stays with the participant's own
`actions`, the bound action contract, and an implementation-bound admission
request. The invocation interface is the bound action contract's `arguments`,
reached through the compiled action address and never copied onto the
affordance. Declared, visible, supported, eligible, admitted and realized remain
separate SEM-219 predicates.

## Runtime Refactor alignment

Reviewed against the open issues of Runtime Refactor milestone 71 on
2026-10-13. This delivery changes no runtime, control-plane or backend code.

| Owner | Boundary preserved by this delivery |
| --- | --- |
| #1363 / #1364 | Importing a tool unit twice reuses declarations. It repeats no control occurrence and makes no mixed-control declaration reusable. |
| #1069 | Selecting participants for an affordance establishes no control-provider coverage or approval. |
| #1362 | Parsing, compiling or displaying an affordance dispatches no operation. |
| #1370 | Observation-boundary classification of an affordance is authored visibility, not an information-flow admission. |
| #1371 / #1372 / #1017 | Tool and access declarations create no mixed-backend execution binding or capability claim. |
| #1374 | A displayed tool is not evidence of observed execution. |
| #1019 | This record distinguishes declaration reuse from control-occurrence reuse and claims no runtime realization. |

## Verification and compatibility

`examples/scenarios/participant-tools/` holds a reusable tool unit and a
scenario that imports it twice. `test_issue_298_tool_authoring.py` reads both
files. It covers standalone and namespaced resolution, the invocation
interface, rename, and role-scoped and local affordances. Negative cases cover
ambiguous, missing and wrong-kind tools, unsupported carriers, and inconsistent
action and observation bindings. Runtime admission refuses declared or
displayed tools.

Migration. No schema, model or source format changes. In a composed document:

- An imported section-qualified `tool_ref` that bound the importing scenario's
  same-named content now binds the unit's own content.
- An imported `tool_ref` that names a unit declaration of another kind now
  fails with the standalone diagnostic, as the unit does on its own.
- An imported bare `tool_ref` that names the unit's content and another of the
  unit's declarations, a section entry or a content item, now fails
  composition with the standalone ambiguity diagnostic. Earlier composition
  bound the content silently, although the unit already failed on its own.
  Spell the ref `content.<name>` or rename the other declaration.

Unambiguous bare content refs bind as before. To keep binding the importing
scenario's content, declare the affordance in that scenario, or give the
unit's ref a name that the unit does not declare.

The formal obligation is the reference-rewrite invariant (FM1). After
composition or rename, an affordance's `tool_ref` resolves to the rewritten
form of the declaration it named before. Otherwise composition fails with the
diagnostic the unit gets on its own. Adjacent defects outside DSL-117 are
tracked in #1573 (rename of nested service and content-item refs), #1574
(reference-typed action argument values) and #1575 (ambiguous bare refs in
other reference families). #1498 tracks authored `__private` refs in importing
scenarios.
