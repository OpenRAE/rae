# Issue #297 — Behavior authoring and composition boundaries

Date: 2026-10-11. Delivery: DSL-116 and PR #1426.

## Decision

Retain the single `ParticipantBehaviorSpecification` aggregate and the
composition semantics of ADR-053. Resolve semantic references against the
complete composed scenario after namespacing each unit's declarations. This
includes cross-fragment references to root declarations. A reference is dangling
when it resolves nowhere in that complete scenario, not merely because its
source file does not declare its target. Ambiguous references remain errors.
Do not independently run full semantic validation on each fragment before merge:
that would reject valid cross-fragment compositions supported by ADR-053.

Roles describe participants in the composed scenario; they are not module-local
identities or export capabilities. A `participant_role_refs` selector selects
all matching participants, including participants declared privately by a
module. Module exports control authored name access, not role membership,
authority, or information-flow permission. Explicit `participant_refs` select
particular participants and are rewritten with their declarations. A reusable
unit with participant-local tool bindings must use explicit participant refs
when selecting all participants of a role would include participants without
those tools. The validator must reject that inconsistent role-wide binding;
it must not silently narrow the selector to make it pass.

These choices preserve source-layout independence, valid existing authoring,
and compiler/runtime identities. The alternative of implicit lexical role or
reference resolution changes existing compositions and is unnecessary for
DSL-116: explicit participant refs already provide the needed reusable local
binding. No new participant root, model, scope switch, or runtime selector is
introduced. These are settled design choices, not deferred implementation gaps.

Enforce ADR-076's authored/generated identity boundary before expansion.
Authored behavior refs containing the reserved `__private` segment are invalid.
A module's own references may acquire that segment during composition when
pointing to its non-exported declarations; expanded and instantiated models
must continue to admit those generated identities. Public YAML and direct
`Scenario` construction enforce the same authoring boundary.

Use `SDLParseError` and the existing bounded `sdl.model.invalid` diagnostics for
invalid imported models and malformed import version constraints. Preserve the
source file, declaration/field pointer, and source range. Do not expose raw
Pydantic or packaging exception rendering. Behavior version labels remain
nonblank identifiers; import versions retain their separate exact/range
contract. Published behavior schemas must reject empty and whitespace-only
version labels just as the parser does.

## Runtime Refactor alignment

Reviewed against Runtime Refactor milestone 71 and the current issue bodies on
2026-10-11. Its design-before-implementation rule is satisfied by this decision
and the existing normative composition rules.

| Owner | Boundary preserved by this delivery |
| --- | --- |
| #1351 / ADR-110; implementation #1363 and #1364 | Reusing an SDL declaration is not repeating a control occurrence. Policy, occurrence, episode, state revision, authority, and replay retain their existing owners. No fixed-coordinate mixed-control declaration is silently made reusable. |
| #1352 / ADR-111; implementation #1365 and #1069 | Selecting participants by role establishes no applicable-provider coverage, approval, or runtime permission. Binding checks stay distinct from provider evaluation at a trusted cut. |
| #1348 / #1350 / ADR-113; #1360–#1362 | Parsing and compiling a behavior neither dispatches an operation nor authorizes retry, recovery, cancellation, or another trial. Existing execution and backend contracts remain authoritative. |
| #1353; #1366–#1369 | General injects and their world effects remain independent of participant declarations. Behavior bindings establish neither delivery nor observation. |
| #1356 / #1359 | Authentication principals are not SDL roles or controllers. Module name visibility is not an authorization or tenant isolation boundary. |
| #1371 / PR #1442 | Reusable behavior declarations do not create mixed-backend execution bindings, stage reports, or readback authority. Those runtime contracts remain distinct from SDL name resolution and role membership. |
| #1019 | Migration/reference guidance distinguishes declaration reuse from control occurrence reuse and makes no unfinished runtime-realization claim. |

## Verification and compatibility

The fixture pair exercises one standalone unit, two namespaced imports, and a
scenario-local aggregate through parsing and compilation. Negative cases cover
unresolved and ambiguous names, collisions, invalid field values and import
versions. Role-wide selection is checked with one and two imports, with explicit
participant selection as the compatible correction for local tool bindings.
Private-name rejection is checked separately from legitimate generated private
references and global role selection.

No valid reference or role resolution changes. Remove authored `__private`
references and export the intended target under its public module name instead.
Supply a nonblank behavior version if an older schema admitted a blank label;
such a document was already rejected by the parser. Error consumers should catch
`SDLParseError` for malformed imports, as they do for root declarations.

The formal obligation is the pre-expansion authoring boundary and preservation
of deterministic composition and compiled identities (FM2). Existing typed
models, published schemas, exact-reference tests and negative cases provide the
bounded evidence. This delivery does not claim live backend execution,
authorization, information-flow isolation, or repeatable control occurrences.
