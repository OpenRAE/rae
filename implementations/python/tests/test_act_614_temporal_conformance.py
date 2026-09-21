"""Ownership of the temporal conformance probe's local clock driver."""

import pytest
from implementations.python.tests._act_614_temporal_fixtures import (
    _bound_deadline_payload,
    _temporal_target,
    _TemporalEvidenceRuntime,
)
from raes_conformance.conformance import participant_temporal_probes as probes
from raes_runtime.manager import RuntimeManager


def _wall_paced_target(mode):
    payload = _bound_deadline_payload()
    progression = payload["time_progression_policies"]["scenario-progression"]
    progression["advancement_mode"] = mode
    progression.pop("step_ticks")
    if mode == "dilated":
        progression["pacing_ratio"] = {"numerator": 2, "denominator": 1}
    # Leave a future attempt pending without relying on a timed sleep in the test.
    payload["temporal_constraints"]["green-cadence"]["cadence_ticks"] = 1000000
    return _temporal_target(payload, _TemporalEvidenceRuntime())


@pytest.mark.parametrize("mode", ["real_time", "dilated"])
@pytest.mark.parametrize("failure_stage", [None, "apply", "advance", "validation"])
def test_temporal_probe_joins_its_clock_driver_on_every_exit(monkeypatch, mode, failure_stage):
    drivers = []
    threads = []

    class ObservedManager(RuntimeManager):
        def apply(self, plan):
            result = super().apply(plan)
            assert result.success
            driver = self._participant_clock_driver
            assert driver is not None and driver.active
            drivers.append(driver)
            threads.append(driver._thread)
            if failure_stage == "apply":
                raise ValueError("fixture apply failure after driver startup")
            return result

        def advance_time(self, *args, **kwargs):
            if failure_stage == "advance":
                raise ValueError("fixture advance failure")
            return super().advance_time(*args, **kwargs)

    def reject_snapshot(_snapshot):
        raise ValueError("fixture validation failure")

    monkeypatch.setattr(
        probes,
        "participant_temporal_probe_manager",
        lambda target, *, stochastic_controls=(): ObservedManager(target, stochastic_controls=stochastic_controls),
    )
    if failure_stage == "validation":
        monkeypatch.setattr(probes, "require_participant_temporal_history", reject_snapshot)
    scenario, target = _wall_paced_target(mode)
    try:
        case = probes.participant_temporal_scenario_case(
            target,
            scenario,
            clock_advances=(("time.clock.scenario-clock", 1),) if failure_stage == "advance" else (),
        )
        assert case.passed is (failure_stage is None)
        assert len(target.participant_runtime.native_actions) == 1
        assert drivers and all(not driver.active for driver in drivers)
        assert all(not thread.is_alive() for thread in threads)
    finally:
        for driver in drivers:
            assert driver.stop()


@pytest.mark.parametrize("raises", [False, True])
def test_temporal_probe_reports_unsuccessful_driver_shutdown(monkeypatch, raises):
    shutdowns = []
    managers = []
    marker = "private-shutdown-detail"

    class StopFailureManager(RuntimeManager):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            managers.append(self)

        def _stop_participant_clock_driver(self):
            driver = self._participant_clock_driver
            stopped = super()._stop_participant_clock_driver()
            if driver is not None:
                shutdowns.append(stopped)
                if raises:
                    raise RuntimeError(marker)
                return False
            return stopped

    monkeypatch.setattr(
        probes,
        "participant_temporal_probe_manager",
        lambda target, *, stochastic_controls=(): StopFailureManager(target, stochastic_controls=stochastic_controls),
    )
    scenario, target = _wall_paced_target("real_time")
    try:
        case = probes.participant_temporal_scenario_case(target, scenario)
        assert shutdowns == [True]
        assert not case.passed
        assert case.cleanup_verified is False
        assert case.residual_state
        assert any(d.code == "conformance.participant-clock-driver-stop-failed" for d in case.diagnostics)
        assert marker not in repr(case)
    finally:
        for manager in managers:
            assert RuntimeManager._stop_participant_clock_driver(manager)
