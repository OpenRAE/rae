"""Shared objective/window semantic tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import given
from hypothesis import strategies as st
from raes.parser import parse_sdl_file
from raes.semantics.assessment import AssessmentResourceKind
from raes.semantics.objective_semantics import (
    OBJECTIVE_ASSIGNMENT_DEPENDENCY_ROLES,
    OBJECTIVE_DEPENDENCY_DEPENDENCY_ROLES,
    OBJECTIVE_OWNER_DEPENDENCY_ROLES,
    OBJECTIVE_SUCCESS_DEPENDENCY_ROLES,
    OBJECTIVE_TARGET_DEPENDENCY_ROLES,
    OBJECTIVE_WINDOW_DEPENDENCY_ROLES,
    AssessmentResourceCatalog,
    ObjectiveReferenceKind,
    WindowResourceCatalog,
    analyze_objective_semantics,
    partition_objective_dependencies,
)
from raes.semantics.objectives import (
    ObjectiveDependencyRole,
    ObjectiveWindowReferenceKind,
    analyze_objective_window,
)


def _workflow(*step_names: str) -> SimpleNamespace:
    return SimpleNamespace(steps={name: object() for name in step_names})


def _window_analysis(
    *,
    story_refs: list[str] | None = None,
    script_refs: list[str] | None = None,
    event_refs: list[str] | None = None,
    workflow_refs: list[str] | None = None,
    step_refs: list[str] | None = None,
    stories_by_name: dict[str, object] | None = None,
    scripts_by_name: dict[str, object] | None = None,
    events_by_name: dict[str, object] | None = None,
    workflows_by_name: dict[str, object] | None = None,
):
    return analyze_objective_window(
        story_refs=list(story_refs or []),
        script_refs=list(script_refs or []),
        event_refs=list(event_refs or []),
        workflow_refs=list(workflow_refs or []),
        step_refs=list(step_refs or []),
        stories_by_name=stories_by_name or {},
        scripts_by_name=scripts_by_name or {},
        events_by_name=events_by_name or {},
        workflows_by_name=workflows_by_name or {},
    )


def _window_issue_codes(analysis) -> set[str]:
    return {issue.code for issue in analysis.issues}


def _write_objective_window_scenario(path: Path, *, namespace: str = "") -> None:
    prefix = f"{namespace}." if namespace else ""
    module_descriptor = ""
    if not namespace:
        module_descriptor = """
module:
  id: raes/window
  version: 1.0.0
  exports:
    propositions: [health-state]
    assertions: [health]
    entities: [blue]
    stories: [intro]
    scripts: [timeline]
    events: [kickoff]
    objectives: [observe]
    workflows: [flow]
"""
    path.write_text(
        f"""
name: {namespace or "window"}
version: 1.0.0
{module_descriptor}
entities:
  {prefix}blue:
    role: blue
propositions:
  {prefix}health-state:
    description: The blue entity is declared for the objective-window fixture.
    subjects: [entities.{prefix}blue]
    basis: declared_state
    predicate:
      kind: presence
      property: role
      semantic_ref: urn:raes:declared-property:entity-role
      operator: exists
assertions:
  {prefix}health:
    proposition: {prefix}health-state
    role: postcondition
stories:
  {prefix}intro:
    scripts: [{prefix}timeline]
scripts:
  {prefix}timeline:
    start_time: 0
    end_time: 60
    speed: 1
    events:
      {prefix}kickoff: 0
events:
  {prefix}kickoff: {{}}
objectives:
  {prefix}observe:
    owner: {prefix}blue
    success:
      assertions: [{prefix}health]
    window:
      stories: [{prefix}intro]
      scripts: [{prefix}timeline]
      events: [{prefix}kickoff]
      workflows: [{prefix}flow]
      steps: [{prefix}flow.start]
workflows:
  {prefix}flow:
    start: start
    steps:
      start:
        type: objective
        objective: {prefix}observe
        on_success: finish
      finish:
        type: end
""",
        encoding="utf-8",
    )


def _write_importing_root(path: Path, imported_name: str, *, namespace: str) -> None:
    path.write_text(
        f"""
name: root
imports:
  - path: {imported_name}
    namespace: {namespace}
    version: 1.0.0
""",
        encoding="utf-8",
    )


def _strip_shared(name: str) -> str:
    return name.removeprefix("shared.")


class TestObjectiveWindowSemantics:
    def test_window_analysis_normalizes_references_and_reachability(self):
        analysis = analyze_objective_window(
            story_refs=["exercise"],
            script_refs=["timeline"],
            event_refs=["kickoff"],
            workflow_refs=["flow"],
            step_refs=["flow.branch"],
            stories_by_name={
                "exercise": SimpleNamespace(scripts=["timeline"]),
            },
            scripts_by_name={
                "timeline": SimpleNamespace(events={"kickoff": 10}),
            },
            events_by_name={"kickoff": SimpleNamespace()},
            workflows_by_name={"flow": _workflow("start", "branch", "end")},
        )

        assert not analysis.issues
        assert analysis.story_names == ("exercise",)
        assert analysis.script_names == ("timeline",)
        assert analysis.event_names == ("kickoff",)
        assert analysis.workflow_names == ("flow",)
        assert analysis.workflow_step_refs == ("flow.branch",)
        assert analysis.reachable_script_names == ("timeline",)
        assert analysis.reachable_event_names == ("kickoff",)
        assert analysis.refresh_workflow_names == ("flow",)
        assert [ref.reference_kind for ref in analysis.references] == [
            ObjectiveWindowReferenceKind.STORY,
            ObjectiveWindowReferenceKind.SCRIPT,
            ObjectiveWindowReferenceKind.EVENT,
            ObjectiveWindowReferenceKind.WORKFLOW,
            ObjectiveWindowReferenceKind.WORKFLOW_STEP,
        ]

    def test_window_analysis_reports_fail_closed_issues(self):
        analysis = analyze_objective_window(
            story_refs=["missing-story"],
            script_refs=["side"],
            event_refs=["cleanup"],
            workflow_refs=["flow"],
            step_refs=["bad", "other.done", "flow.missing"],
            stories_by_name={},
            scripts_by_name={
                "side": SimpleNamespace(events={"kickoff": 10}),
            },
            events_by_name={"cleanup": SimpleNamespace()},
            workflows_by_name={
                "flow": _workflow("start"),
                "other": _workflow("done"),
            },
        )

        assert {issue.code for issue in analysis.issues} == {
            "story-unbound",
            "event-outside-window-scripts",
            "step-invalid-format",
            "step-workflow-outside-window",
            "step-unbound",
        }

    @pytest.mark.parametrize(
        ("kwargs", "expected_code"),
        [
            pytest.param({"story_refs": ["missing-story"]}, "story-unbound", id="story-unbound"),
            pytest.param({"script_refs": ["missing-script"]}, "script-unbound", id="script-unbound"),
            pytest.param({"event_refs": ["missing-event"]}, "event-unbound", id="event-unbound"),
            pytest.param(
                {
                    "workflow_refs": ["flow"],
                    "step_refs": ["bad-step-ref"],
                    "workflows_by_name": {"flow": _workflow("start")},
                },
                "step-invalid-format",
                id="step-invalid-format",
            ),
            pytest.param({"workflow_refs": ["missing-flow"]}, "workflow-unbound", id="workflow-unbound"),
            pytest.param(
                {
                    "workflow_refs": ["flow"],
                    "step_refs": ["missing-flow.start"],
                    "workflows_by_name": {"flow": _workflow("start")},
                },
                "step-workflow-unbound",
                id="step-workflow-unbound",
            ),
            pytest.param(
                {
                    "workflow_refs": ["flow"],
                    "step_refs": ["flow.missing"],
                    "workflows_by_name": {"flow": _workflow("start")},
                },
                "step-unbound",
                id="step-unbound",
            ),
            pytest.param(
                {
                    "workflow_refs": ["flow"],
                    "step_refs": ["other.done"],
                    "workflows_by_name": {"flow": _workflow("start"), "other": _workflow("done")},
                },
                "step-workflow-outside-window",
                id="step-workflow-outside-window",
            ),
            pytest.param(
                {
                    "story_refs": ["intro"],
                    "script_refs": ["side"],
                    "stories_by_name": {"intro": SimpleNamespace(scripts=["main"])},
                    "scripts_by_name": {"main": SimpleNamespace(events={}), "side": SimpleNamespace(events={})},
                },
                "script-outside-window-stories",
                id="script-outside-window-stories",
            ),
            pytest.param(
                {
                    "script_refs": ["timeline"],
                    "event_refs": ["cleanup"],
                    "scripts_by_name": {"timeline": SimpleNamespace(events={"kickoff": 10})},
                    "events_by_name": {"cleanup": SimpleNamespace()},
                },
                "event-outside-window-scripts",
                id="event-outside-window-scripts",
            ),
        ],
    )
    def test_window_invariant_reference_must_resolve(self, kwargs, expected_code) -> None:
        analysis = _window_analysis(**kwargs)

        assert _window_issue_codes(analysis) == {expected_code}

    def test_window_invariant_steps_require_workflow_window(self) -> None:
        analysis = _window_analysis(
            step_refs=["flow.start"],
            workflows_by_name={"flow": _workflow("start")},
        )

        assert "step-requires-workflow-window" in _window_issue_codes(analysis)

    def test_composition_ready_invariant_imported_window_analysis_uses_expanded_canonical_identities(
        self, tmp_path: Path
    ) -> None:
        imported = tmp_path / "window-module.yaml"
        root = tmp_path / "root.yaml"
        _write_objective_window_scenario(imported)
        _write_importing_root(root, imported.name, namespace="shared")
        scenario = parse_sdl_file(root)

        analysis = _analyze(
            scenario.objectives,
            entity_names=set(scenario.entities),
            assertions_by_name=scenario.assertions,
            stories_by_name=scenario.stories,
            scripts_by_name=scenario.scripts,
            events_by_name=scenario.events,
            workflows_by_name=scenario.workflows,
        )

        assert not analysis.has_issues
        assert {ref.canonical_name for ref in analysis.references_of_kind(ObjectiveReferenceKind.WINDOW)} == {
            "shared.intro",
            "shared.timeline",
            "shared.kickoff",
            "shared.flow",
            "shared.flow.start",
        }
        window_step = [
            ref
            for ref in analysis.references_of_kind(ObjectiveReferenceKind.WINDOW)
            if ref.window_reference_kind == ObjectiveWindowReferenceKind.WORKFLOW_STEP
        ][0]
        assert window_step.workflow_name == "shared.flow"
        assert window_step.step_name == "start"

    def test_composition_ready_invariant_namespace_extends_window_identity_without_changing_kind_roles_or_ownership(
        self, tmp_path: Path
    ) -> None:
        plain = tmp_path / "plain.yaml"
        imported = tmp_path / "window-module.yaml"
        namespaced = tmp_path / "namespaced-root.yaml"
        _write_objective_window_scenario(plain)
        _write_objective_window_scenario(imported)
        _write_importing_root(namespaced, imported.name, namespace="shared")
        plain_scenario = parse_sdl_file(plain)
        namespaced_scenario = parse_sdl_file(namespaced)

        plain_window = plain_scenario.objectives["observe"].window
        namespaced_window = namespaced_scenario.objectives["shared.observe"].window
        plain_analysis = analyze_objective_window(
            story_refs=plain_window.stories,
            script_refs=plain_window.scripts,
            event_refs=plain_window.events,
            workflow_refs=plain_window.workflows,
            step_refs=plain_window.steps,
            stories_by_name=plain_scenario.stories,
            scripts_by_name=plain_scenario.scripts,
            events_by_name=plain_scenario.events,
            workflows_by_name=plain_scenario.workflows,
        )
        namespaced_analysis = analyze_objective_window(
            story_refs=namespaced_window.stories,
            script_refs=namespaced_window.scripts,
            event_refs=namespaced_window.events,
            workflow_refs=namespaced_window.workflows,
            step_refs=namespaced_window.steps,
            stories_by_name=namespaced_scenario.stories,
            scripts_by_name=namespaced_scenario.scripts,
            events_by_name=namespaced_scenario.events,
            workflows_by_name=namespaced_scenario.workflows,
        )

        assert [
            (ref.reference_kind, ref.dependency_roles, ref.step_name, _strip_shared(ref.workflow_name or ""))
            for ref in namespaced_analysis.references
        ] == [
            (ref.reference_kind, ref.dependency_roles, ref.step_name, ref.workflow_name or "")
            for ref in plain_analysis.references
        ]
        assert [_strip_shared(ref.canonical_name) for ref in namespaced_analysis.references] == [
            ref.canonical_name for ref in plain_analysis.references
        ]

    @given(st.lists(st.sampled_from(["flow.start", "flow.branch"]), max_size=12))
    def test_workflow_step_normalization_is_stable(self, step_refs: list[str]):
        analysis = analyze_objective_window(
            story_refs=[],
            script_refs=[],
            event_refs=[],
            workflow_refs=["flow"],
            step_refs=step_refs,
            stories_by_name={},
            scripts_by_name={},
            events_by_name={},
            workflows_by_name={"flow": _workflow("start", "branch")},
        )

        assert analysis.workflow_step_refs == tuple(dict.fromkeys(step_refs))


def _success(*, assertions=None, mode="all_of"):
    return SimpleNamespace(
        assertions=list(assertions or []),
        mode=mode,
    )


def _window(*, stories=None, scripts=None, events=None, workflows=None, steps=None):
    return SimpleNamespace(
        stories=list(stories or []),
        scripts=list(scripts or []),
        events=list(events or []),
        workflows=list(workflows or []),
        steps=list(steps or []),
    )


def _objective(
    *, assigned_participant="", owner="", actions=None, targets=None, success=None, window=None, depends_on=None
):
    return SimpleNamespace(
        assigned_participant=assigned_participant,
        owner=owner,
        actions=list(actions or []),
        targets=list(targets or []),
        success=success if success is not None else _success(assertions=["health"]),
        window=window,
        depends_on=list(depends_on or []),
    )


def _agent(*actions: str) -> SimpleNamespace:
    return SimpleNamespace(actions=list(actions))


def _is_var(value: object) -> bool:
    return isinstance(value, str) and value.startswith("${") and value.endswith("}")


def _analyze(objectives, **overrides):
    """Drive the analyzer with empty defaults; per-test overrides drop in.

    Resource maps are bundled into ``AssessmentResourceCatalog`` /
    ``WindowResourceCatalog`` for the analyzer; tests still pass the per-section
    overrides (``assertions_by_name``, ``stories_by_name``, …) for readability.
    """

    section_defaults = {
        "assertions_by_name": {},
        "stories_by_name": {},
        "scripts_by_name": {},
        "events_by_name": {},
        "workflows_by_name": {},
    }
    sections = {key: overrides.pop(key, default) for key, default in section_defaults.items()}
    kwargs: dict = {
        "objectives_by_name": objectives,
        "agents_by_name": {},
        "entity_names": set(),
        "action_contracts": {"Scan": object(), "Persist": object()},
        "assessment_resources": AssessmentResourceCatalog(
            assertions=sections["assertions_by_name"],
        ),
        "window_resources": WindowResourceCatalog(
            stories=sections["stories_by_name"],
            scripts=sections["scripts_by_name"],
            events=sections["events_by_name"],
            workflows=sections["workflows_by_name"],
        ),
        "targetable_name_index": {},
    }
    kwargs.update(overrides)
    return analyze_objective_semantics(**kwargs)


class TestObjectiveSemantics:
    def test_well_formed_objectives_normalize_references_and_dependencies(self) -> None:
        analysis = _analyze(
            {
                "base": _objective(owner="blue", success=_success(assertions=["c1"])),
                "follow": _objective(
                    assigned_participant="red",
                    actions=["Scan"],
                    targets=["nodes.web"],
                    success=_success(assertions=["c2"]),
                    window=_window(workflows=["flow"], steps=["flow.branch"]),
                    depends_on=["base"],
                ),
            },
            agents_by_name={"red": _agent("Scan", "Exploit")},
            entity_names={"blue"},
            assertions_by_name={"c1": object(), "c2": object()},
            workflows_by_name={"flow": _workflow("start", "branch")},
            targetable_name_index={"nodes.web": {"nodes.web"}},
        )

        assert not analysis.has_issues

        assert {ref.canonical_name for ref in analysis.references_of_kind(ObjectiveReferenceKind.ASSIGNMENT)} == {"red"}
        assert {ref.canonical_name for ref in analysis.references_of_kind(ObjectiveReferenceKind.OWNER)} == {
            "entities.blue"
        }
        assert {ref.canonical_name for ref in analysis.references_of_kind(ObjectiveReferenceKind.TARGET)} == {
            "nodes.web"
        }
        assert {ref.canonical_name for ref in analysis.references_of_kind(ObjectiveReferenceKind.SUCCESS)} == {
            "assertion.c1",
            "assertion.c2",
        }
        success_kinds = {
            ref.canonical_name: ref.success_resource_kind
            for ref in analysis.references_of_kind(ObjectiveReferenceKind.SUCCESS)
        }
        assert success_kinds["assertion.c1"] == AssessmentResourceKind.ASSERTION
        assert success_kinds["assertion.c2"] == AssessmentResourceKind.ASSERTION
        assert {ref.canonical_name for ref in analysis.references_of_kind(ObjectiveReferenceKind.WINDOW)} == {
            "flow",
            "flow.branch",
        }
        assert {ref.canonical_name for ref in analysis.references_of_kind(ObjectiveReferenceKind.DEPENDENCY)} == {
            "objective.base"
        }

        for ref in analysis.references_of_kind(ObjectiveReferenceKind.SUCCESS):
            assert ref.dependency_roles == OBJECTIVE_SUCCESS_DEPENDENCY_ROLES
        for ref in analysis.references_of_kind(ObjectiveReferenceKind.DEPENDENCY):
            assert ref.dependency_roles == OBJECTIVE_DEPENDENCY_DEPENDENCY_ROLES
        for ref in analysis.references_of_kind(ObjectiveReferenceKind.WINDOW):
            assert ObjectiveDependencyRole.REFRESH in ref.dependency_roles
            assert ObjectiveDependencyRole.ORDERING not in ref.dependency_roles
        for kind in (ObjectiveReferenceKind.ASSIGNMENT, ObjectiveReferenceKind.OWNER, ObjectiveReferenceKind.TARGET):
            for ref in analysis.references_of_kind(kind):
                assert ref.dependency_roles == ()

        assert analysis.dependencies_for("base").ordering_names == ("assertion.c1",)
        assert analysis.dependencies_for("base").refresh_names == ("assertion.c1",)
        assert analysis.dependencies_for("follow").ordering_names == ("assertion.c2", "objective.base")
        assert analysis.dependencies_for("follow").refresh_names == ("assertion.c2", "objective.base", "workflow.flow")
        assert "follow" in analysis.window_analyses

    def test_undeclared_actor_references_are_reported(self) -> None:
        analysis = _analyze(
            {
                "a": _objective(assigned_participant="ghost"),
                "b": _objective(owner="ghost-team"),
            },
            agents_by_name={"red": _agent()},
            entity_names={"blue"},
            assertions_by_name={"health": object()},
        )
        codes = {issue.code for issue in analysis.issues}
        assert "objective.assignment-undeclared" in codes
        assert "objective.owner-undeclared" in codes

    def test_agent_action_must_be_declared(self) -> None:
        analysis = _analyze(
            {"a": _objective(assigned_participant="red", actions=["Persist"])},
            agents_by_name={"red": _agent("Scan")},
            assertions_by_name={"health": object()},
        )
        issue = analysis.issues_of_code("objective.action-not-declared")[0]
        assert issue.ref == "Persist"
        assert issue.actor_name == "red"

    def test_unresolvable_target_is_reported(self) -> None:
        analysis = _analyze(
            {"a": _objective(owner="blue", targets=["ghost"])},
            entity_names={"blue"},
            assertions_by_name={"health": object()},
        )
        assert analysis.issues_of_code("objective.target-unresolvable")[0].ref == "ghost"

    def test_ambiguous_target_is_reported_with_sorted_candidates(self) -> None:
        analysis = _analyze(
            {"a": _objective(owner="blue", targets=["web"])},
            entity_names={"blue"},
            assertions_by_name={"health": object()},
            targetable_name_index={"web": {"nodes.web", "features.web"}},
        )
        issue = analysis.issues_of_code("objective.target-ambiguous")[0]
        assert issue.ref == "web"
        assert issue.candidates == ("features.web", "nodes.web")

    def test_undeclared_success_assertion_is_reported(self) -> None:
        analysis = _analyze(
            {
                "a": _objective(
                    owner="blue",
                    success=_success(assertions=["c?"]),
                )
            },
            entity_names={"blue"},
        )
        codes = {issue.code for issue in analysis.issues}
        assert "objective.success-assertion-undeclared" in codes

    def test_window_issues_are_resurfaced_under_objective_codes(self) -> None:
        analysis = _analyze(
            {
                "a": _objective(
                    owner="blue",
                    success=_success(assertions=["health"]),
                    window=_window(scripts=["s1"], events=["evt"]),
                )
            },
            entity_names={"blue"},
            assertions_by_name={"health": object()},
            scripts_by_name={"s1": SimpleNamespace(events={"kickoff": 1})},
            events_by_name={"evt": SimpleNamespace()},
        )
        assert analysis.issues_of_code("objective.window.event-outside-window-scripts")

    def test_undeclared_dependency_is_reported(self) -> None:
        analysis = _analyze(
            {"a": _objective(owner="blue", depends_on=["ghost"])},
            entity_names={"blue"},
            assertions_by_name={"health": object()},
        )
        assert analysis.issues_of_code("objective.dependency-undeclared")[0].ref == "ghost"

    def test_dependency_cycle_is_reported_once_globally(self) -> None:
        analysis = _analyze(
            {
                "a": _objective(owner="blue", depends_on=["b"]),
                "b": _objective(owner="blue", depends_on=["a"]),
            },
            entity_names={"blue"},
            assertions_by_name={"health": object()},
        )
        cycle_issues = analysis.issues_of_code("objective.dependency-cycle")
        assert len(cycle_issues) == 1
        assert cycle_issues[0].objective_name == ""

    def test_unresolved_variable_references_are_skipped(self) -> None:
        analysis = _analyze(
            {
                "a": _objective(
                    assigned_participant="${actor}",
                    actions=["${act}"],
                    targets=["${tgt}"],
                    success=_success(assertions=["${m}"]),
                    window=_window(stories=["${story}"]),
                    depends_on=["${dep}"],
                )
            },
            is_unresolved=_is_var,
        )
        assert not analysis.has_issues
        assert analysis.references == ()

    def test_no_objectives_is_empty_analysis(self) -> None:
        analysis = _analyze({})
        assert analysis.references == ()
        assert analysis.issues == ()
        assert analysis.dependencies == ()


class TestObjectiveDependencyPartition:
    def test_partition_orders_primary_then_refreshes_window(self) -> None:
        ordering, refresh = partition_objective_dependencies(
            success_refs=["a", "b"],
            dependency_refs=["c"],
            window_refresh_refs=["w1", "w2"],
        )
        assert ordering == ("a", "b", "c")
        assert refresh == ("a", "b", "c", "w1", "w2")

    def test_partition_dedupes_across_categories(self) -> None:
        ordering, refresh = partition_objective_dependencies(
            success_refs=["a", "a"],
            dependency_refs=["a", "b"],
            window_refresh_refs=["b", "w"],
        )
        assert ordering == ("a", "b")
        assert refresh == ("a", "b", "w")

    def test_partition_handles_empty_inputs(self) -> None:
        assert partition_objective_dependencies(success_refs=[], dependency_refs=[], window_refresh_refs=[]) == ((), ())

    def test_role_constants_are_sane(self) -> None:
        assert ObjectiveDependencyRole.ORDERING in OBJECTIVE_SUCCESS_DEPENDENCY_ROLES
        assert ObjectiveDependencyRole.REFRESH in OBJECTIVE_SUCCESS_DEPENDENCY_ROLES
        assert ObjectiveDependencyRole.ORDERING in OBJECTIVE_DEPENDENCY_DEPENDENCY_ROLES
        assert ObjectiveDependencyRole.REFRESH in OBJECTIVE_DEPENDENCY_DEPENDENCY_ROLES
        assert OBJECTIVE_WINDOW_DEPENDENCY_ROLES == (ObjectiveDependencyRole.REFRESH,)
        # Actor and target references are normalized for fail-closed validation
        # but the compiler does not propagate ordering or refresh through them.
        assert OBJECTIVE_ASSIGNMENT_DEPENDENCY_ROLES == ()
        assert OBJECTIVE_OWNER_DEPENDENCY_ROLES == ()
        assert OBJECTIVE_TARGET_DEPENDENCY_ROLES == ()

    def test_partition_emits_each_category_under_default_roles(self) -> None:
        # Default roles (success and depends_on both ORDERING+REFRESH; window
        # REFRESH only) place the success and dependency entries in both tuples
        # and the window entry in refresh only.
        ordering, refresh = partition_objective_dependencies(
            success_refs=["s"],
            dependency_refs=["d"],
            window_refresh_refs=["w"],
        )
        assert ordering == ("s", "d")
        assert refresh == ("s", "d", "w")

    def test_partition_reads_each_categorys_own_role_constant(self, monkeypatch) -> None:
        # The cycle-1 bug merged success+depends_on into one list and gated
        # both through OBJECTIVE_SUCCESS_DEPENDENCY_ROLES, so a hypothetical
        # change to the dependency-role constant alone never reached the
        # runtime tuples. Toggle just OBJECTIVE_DEPENDENCY_DEPENDENCY_ROLES to
        # refresh-only and assert the partition output reflects exactly that
        # difference — proving each category is keyed independently.
        import raes.semantics.objective_semantics as os_module

        monkeypatch.setattr(
            os_module,
            "OBJECTIVE_DEPENDENCY_DEPENDENCY_ROLES",
            (ObjectiveDependencyRole.REFRESH,),
        )
        ordering, refresh = partition_objective_dependencies(
            success_refs=["s"],
            dependency_refs=["d"],
            window_refresh_refs=["w"],
        )
        # success kept ORDERING; deps lost it; window unchanged.
        assert ordering == ("s",)
        assert refresh == ("s", "d", "w")

    @given(st.lists(st.sampled_from(["a", "b", "c", "d"]), max_size=16))
    def test_partition_ordering_is_dedup_stable(self, refs: list[str]) -> None:
        ordering, _refresh = partition_objective_dependencies(
            success_refs=refs,
            dependency_refs=[],
            window_refresh_refs=[],
        )
        assert ordering == tuple(dict.fromkeys(refs))
