# Executable design evidence and review record

The reference model evaluates the candidate in [semantics.md](semantics.md).
It is independent of the production envelope implementation and is excluded
from the published Python package list. It imports no backend, parser, capture
service or external solver. This is design evidence for #1201, not evidence of
production migration or live backend conformance.

## Reproduce

From the repository root, with the repository Python environment installed:

```bash
implementations/python/.venv/bin/python -m pytest -q \
  implementations/python/tests/test_issue_1201_partial_description.py \
  implementations/python/tests/test_issue_1201_description_lifecycle.py
```

Observed on 2026-09-05: **24 tests passed**. Targeted coverage of the two research
modules was 93% of statements (361 statements, 27 missed). The existing envelope
relation and scoped-realization suites also passed (76 tests). Whole-repository
verification and external review are separate workflow records on the issue;
these targeted results do not stand in for those gates.

The core is
[`partial_description.py`](../../../implementations/python/research/partial_description.py).
The lifecycle/version/capture and abstract transition examples are in
[`description_lifecycle.py`](../../../implementations/python/research/description_lifecycle.py).
`denotation` returns indices in one explicitly supplied finite world universe;
indices from different universes cannot be compared. `choose` enumerates actual
offered candidates and returns a copy of the first permitted member, or the distinct `NO_WITNESS` sentinel
when none is found (a null value remains a valid witness). It does not discover a backend's capabilities or execute it.

## Acceptance-to-evidence matrix

Test names below are in the two files named in the reproduce command.

| Issue criterion / anchor | Decision and executable evidence |
| --- | --- |
| Omission/undefined, inherited defaults, delegation, known absence, unknown/redacted information, domains and lifecycle | Semantics §§1, 2, 6; `test_defaults_are_lexical_not_conjunction_or_input_order`, `test_optional_presence_is_conditional_and_absence_is_not_unknown`, `test_partial_capture_keeps_unknown_redacted_absence_and_contradiction_separate`, `test_knowledge_never_grants_backend_discretion`. |
| Refinement, composition, conflicts and stable matching | §§2–3; exhaustive nine-world algebra check over 27 rule triples, `test_conjoined_explicit_fields_authorize_each_other_without_opening_extras`, `test_stable_identity_duplicate_rejection_and_typed_atoms`. |
| Schema/value recursion, cycles and finite limits | §3; `test_cycles_missing_references_and_budgets_are_not_empty_sets`, `test_source_and_model_budgets_include_direct_input_shapes`, `test_world_round_trip_and_domain_budget_preserve_type_sensitive_meaning`. Schema recursion policy is a proposed restriction; the model resolves local acyclic definition chains. |
| Compact executable model reviewed before public syntax | ADR-105; typed Python constructors and these tests. Public syntax remains unselected; the PR's review records cover this concrete candidate. |
| Software-only, deep private profile, mixed siblings, partial capture and non-cyber | §§5–6; `test_kali_ladder_software_presence_and_private_acquisition`, `test_inherited_open_does_not_weaken_an_exact_sibling`, partial-capture test above, `test_non_cyber_typed_domain_uses_the_same_recursive_relation`. |
| Reuse SEM-218/219, concept/profile authorities; separate validity, admission and evidence | §§4–7; `accepts`, `choose`, `assess` and capture admission exercise different questions. Owning software surface is ADR-034 `software_components`; package coordinates retain their owner. |
| Governing intent is binding for the candidate | ADR-105 decision and §1; all executable anchors below. Production adoption is explicitly separate. |
| Five Linux boxes, one inherited open scope, exactly five requested nodes | `test_five_linux_boxes_are_exactly_five_with_one_open_scope`; four/six-node mutations fail. Actual chosen fields are reportable through `report_choice`. |
| Kali, Kali plus exact nmap, release/tools/optional/configuration ladder | Kali ladder test plus optional wrong-version and exact-sibling mutations. Extra configuration/software remains open. |
| Abstract two-computer/three-action complete model | `test_abstract_two_computers_three_actions_execute_without_concrete_inventory`; six admitted transitions, disabled receive and unknown action refusals. No OS/package/filesystem or packet model is constructed. |
| One supported witness versus universal coverage; ADR-070 call-site review | §4 audit; `test_one_supported_witness_does_not_prove_universal_support` demonstrates overlap without subset coverage and vacuous subset truth without operational success. Shared `subsumes` is unchanged. |
| Independent observation/reporting, collection, retention and export | §6; detailed-filesystem/no-data, mixed-component, abstract exhaustive-action, unsupported-capture/prohibition tests. Prohibited producers fail the test if invoked. |
| Optional version, exact/older/newer/range and internal private route versus authored constraint | §5; version-relation and Kali/private-profile tests. Private-profile support must be declared and its exact revision constraint holds. Internal acquisition is a synthetic fixture choice, not a real private repository fetch. |
| Backend-selected reporting has honest basis and requested depth | `test_requested_choice_report_is_not_a_measurement_or_full_inventory`; a report contains only requested leaves and says `backend-selected`. No requested fields yields no facts. |

## Counterexamples that changed the prototype

The initial tests failed before their modules existed. Later behavioral red/green
cycles exposed and corrected these design-model defects:

- Conjoining separately declared `x` and `y` originally treated each other's
  field as an unauthorized extra. Permission now uses the union of declared
  semantic paths while every constraint and closed universe remains binding.
- Checking only the first undeclared record skipped a deeper closed scope.
  Permission now visits its descendants too.
- The abstract runner originally accumulated traces unconditionally. It now
  creates action records only when trace collection is selected.
- Initial budgets omitted atom-string size, direct integer width and individual
  domain comparisons. Those checks now produce a bounded limit diagnostic.

These are defects of the research model found during this work, not claims that
production defects were fixed by changing the oracle.

## Review decisions and limits

The proposed decisions are concrete: inherited recursive delegation;
type-sensitive conjunctive constraints; identity-based matching; named closure
universes; presence independent of knowledge; separate existential selection and
universal capability; and separate realization/report/capture authorities.
The architecture preflight and implementation plan are recorded on #1201;
the pre-push review and PR are the durable review of this implementation.
Maintainer acceptance is not claimed in advance.

The independent model was selected instead of CUE integration. CUE's
[constraint lattice](https://cuelang.org/docs/concept/the-logic-of-cue/) supports
the comparison with conjunctive refinement and conditional optional fields;
its [closed structs](https://cuelang.org/docs/tour/types/closed/) illustrate
local record closure. These are precedents, not RAE authority or a proof of
the candidate. The model runs without CUE and makes no cross-engine equivalence
claim.

The bounded universe is explicitly supplied and is not a universe of all Linux
machines. Finite enumeration checks algebraic behavior and counterexamples,
not a general completeness theorem. Version comparison covers only the toy
numeric-triplet profile. Graph aliases, sequence matching, recursive schemas,
scalar preference selection, full task/run demand refinement, migration codecs,
and provenance envelopes have specified ownership/policy but are not implemented
by the prototype. Capture sources are trusted synthetic finite tuples; a real
streaming implementation needs pre-buffer bounds, cancellation, loss disclosure,
window enforcement and retention expiry through existing owners. The research
modules are outside Sonar's production source roots; pytest, local coverage,
lint and code review validate them.

Every public adoption must still test parser/normalizer/compiler preservation,
configuration-bound planner and alternate-submission admission, actual delivered
state, requested observation and serialized compatibility. No finite model
result licenses a weaker existing contract or claims those migrations shipped.
