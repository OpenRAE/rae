"""Software precision does not select acquisition telemetry or evidence work."""

from raes_contracts.observation_demand import (
    AchievedObservationValue,
    ObservationBasis,
    ObservationDemandRule,
    execute_observation_lifecycle,
    normalize_observation_demands,
    realization_description_report,
)
from test_issue_1212_observation_demand import _document, _selector


def test_requested_software_and_os_description_does_not_collect_internal_routes():
    software = _selector("/nodes/host", "software_components", kind="field")
    os = _selector("/nodes/host", "os_distribution", kind="field")
    route = _selector("/nodes/host", "acquisition", kind="field")
    resolution = normalize_observation_demands(
        _document(
            *(
                ObservationDemandRule(
                    rule_id=f"report-{index}",
                    scope="/nodes/host",
                    purpose="realization-description",
                    mode="selected",
                    selector=selector,
                    basis="backend-selected",
                    retention="forbid",
                    export="forbid",
                )
                for index, selector in enumerate((software, os))
            )
        ),
        target_scopes=("/nodes/host",),
    )
    selected = {
        software.key: AchievedObservationValue([{"name": "tool", "version": "1.0"}], ObservationBasis.BACKEND_SELECTED),
        os.key: AchievedObservationValue("kali", ObservationBasis.BACKEND_SELECTED),
        route.key: AchievedObservationValue("private-internal-route", ObservationBasis.BACKEND_SELECTED),
    }
    report = realization_description_report(resolution, selected)
    assert {item.selector_key for item in report} == {software.key, os.key}
    assert all(item.basis is ObservationBasis.BACKEND_SELECTED and not item.retention_required for item in report)
    assert "private-internal-route" not in repr(report)
    calls = []
    lifecycle = execute_observation_lifecycle(
        resolution, producers={route.key: lambda: calls.append("route") or ()}, supported=frozenset({route.key})
    )
    assert calls == []
    assert lifecycle.collected == lifecycle.retained == lifecycle.exported == ()
