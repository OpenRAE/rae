"""Wall-paced clock driver for autonomous participant execution."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from fractions import Fraction
from typing import TypedDict, Unpack

from raes_contracts.contracts.participant_execution import ParticipantExecutionServiceStateModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.models import CompiledTimeModel, ParticipantAutonomousExecutionRuntime

_LOGGER = get_logger(__name__)


class ClockDriverOptions(TypedDict, total=False):
    publish_failure: Callable[[ApplyResult], None] | None
    mutation_scope: Callable[[], AbstractContextManager[object]]


@dataclass(frozen=True)
class _ClockRate:
    clock_address: str
    seconds_per_tick: Fraction


def _automatic_clock_rates(
    policies: Iterable[ParticipantAutonomousExecutionRuntime],
    time_model: CompiledTimeModel,
) -> tuple[_ClockRate, ...]:
    policy_clocks = {policy.clock_address for policy in policies}
    clocks = {clock.address: clock for clock in time_model.clocks}
    domains = {domain.address: domain for domain in time_model.domains}
    rates: list[_ClockRate] = []
    for progression in time_model.progression_policies:
        if progression.clock_address not in policy_clocks:
            continue
        if progression.advancement_mode not in {"real_time", "dilated"}:
            continue
        if clocks[progression.clock_address].authority_kind != "runtime":
            continue
        domain = domains[clocks[progression.clock_address].time_domain_address]
        tick_period = Fraction(domain.tick_period_numerator, domain.tick_period_denominator)
        pacing = Fraction(progression.pacing_numerator, progression.pacing_denominator)
        rates.append(
            _ClockRate(
                clock_address=progression.clock_address,
                seconds_per_tick=tick_period / pacing,
            )
        )
    return tuple(rates)


class ParticipantClockDriver:
    """Advance wall-paced shared clocks to each governed participant cadence."""

    def __init__(
        self,
        policies: Iterable[ParticipantAutonomousExecutionRuntime],
        time_model: CompiledTimeModel,
        *,
        snapshot: Callable[[], RuntimeSnapshot],
        advance: Callable[[str, int], ApplyResult],
        service_due: Callable[[], ApplyResult],
        lock: threading.RLock,
        **options: Unpack[ClockDriverOptions],
    ) -> None:
        self._rates = _automatic_clock_rates(policies, time_model)
        self._policy_clocks = {policy.address: policy.clock_address for policy in policies}
        self._snapshot = snapshot
        self._advance = advance
        self._service_due = service_due
        self._lock = lock
        self._publish_failure = options.pop("publish_failure", None)
        self._mutation_scope = options.pop("mutation_scope", nullcontext)
        if options:
            raise TypeError("unsupported participant clock driver option")
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._failure: ApplyResult | None = None
        self._deadlines: dict[tuple[str, int, int, int], float] = {}

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def failure(self) -> ApplyResult | None:
        return self._failure

    def start(self) -> None:
        if not self._rates or self.active:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="raes-participant-clock-driver",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout: float = 2.0) -> bool:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        if thread is not None and thread.is_alive():
            return False
        self._thread = None
        self._deadlines.clear()
        return True

    def _run(self) -> None:
        try:
            keep_running = True
            while keep_running and not self._stop.is_set():
                keep_running = self._run_once()
        # Boundary of the driver thread: record one typed failure and log it once. The serial
        # scheduler calls participant runtime backends directly, so log only RAES frames.
        except Exception as exc:
            _LOGGER.exception("participant clock driver terminated unexpectedly", exc_info=foreign_failure_record(exc))
            self._record_unexpected_failure(exc)

    def _run_once(self) -> bool:
        transition = self._next_transition()
        keep_running = True
        if transition is None:
            self._stop.wait(0.05)
        elif transition[2] > 0:
            delay = transition[2]
            self._stop.wait(delay)
            keep_running = not self._stop.is_set()
        else:
            result = self._service_current_transition()
            if result is not None and not result.success:
                self._failure = result
                keep_running = False
        return keep_running

    def _service_current_transition(self) -> ApplyResult | None:
        with self._mutation_scope(), self._lock:
            current = self._next_transition()
            if current is None:
                return None
            clock_address, ticks, current_delay = current
            if current_delay > 0:
                return None
            return self._service_due() if ticks == 0 else self._advance(clock_address, ticks)

    def _record_unexpected_failure(self, exc: BaseException) -> None:
        del exc
        snapshot = self._pacing_failure_snapshot(self._snapshot())
        self._failure = ApplyResult(
            success=False,
            snapshot=snapshot,
            diagnostics=[
                Diagnostic(
                    code="runtime.participant-clock-driver-failed",
                    domain="participant",
                    address="runtime.participant-clock-driver",
                    message="Participant clock driver terminated unexpectedly.",
                )
            ],
        )
        if self._publish_failure is not None:
            self._publish_failure(self._failure)

    def _pacing_failure_snapshot(
        self,
        snapshot: RuntimeSnapshot,
    ) -> RuntimeSnapshot:
        services = dict(snapshot.participant_execution_services)
        for policy_address, clock_address in self._policy_clocks.items():
            payload = services.get(policy_address)
            if payload is None:
                continue
            service = ParticipantExecutionServiceStateModel.model_validate(payload)
            evidence_ref = f"evidence:{policy_address}:pacing-loss:{clock_address}:generation-{service.generation}"
            services[policy_address] = service.model_copy(
                update={
                    "desired_lifecycle": "paused",
                    "observed_lifecycle": "paused",
                    "health": "degraded",
                    "readiness": "not_ready",
                    "accepting_new_work": False,
                    "last_transition_ref": (f"operation:{policy_address}:pacing-loss:generation-{service.generation}"),
                    "pacing_deviation_refs": tuple(dict.fromkeys([*service.pacing_deviation_refs, evidence_ref])),
                    "evidence_refs": tuple(dict.fromkeys([*service.evidence_refs, evidence_ref])),
                }
            ).model_dump(mode="json")
        return snapshot.with_entries(
            dict(snapshot.entries),
            participant_execution_services=services,
        )

    def _next_transition(self) -> tuple[str, int, float] | None:
        with self._mutation_scope(), self._lock:
            snapshot = self._snapshot()
            if snapshot.time_model_state is None:
                return None
            return self._next_transition_for_snapshot(snapshot)

    def _next_transition_for_snapshot(self, snapshot: RuntimeSnapshot) -> tuple[str, int, float] | None:
        candidates: list[tuple[float, str, int]] = []
        now = time.monotonic()
        active_keys: set[tuple[str, int, int, int]] = set()
        for rate in self._rates:
            candidate, key = self._rate_transition(snapshot, rate, now)
            if candidate is None:
                continue
            if candidate[0] <= 0.0:
                return candidate[1], candidate[2], candidate[0]
            candidates.append(candidate)
            if key is not None:
                active_keys.add(key)
        self._deadlines = {key: value for key, value in self._deadlines.items() if key in active_keys}
        if not candidates:
            return None
        delay, clock_address, ticks = min(candidates)
        return clock_address, ticks, delay

    def _rate_transition(
        self,
        snapshot: RuntimeSnapshot,
        rate: _ClockRate,
        now: float,
    ) -> tuple[tuple[float, str, int] | None, tuple[str, int, int, int] | None]:
        assert snapshot.time_model_state is not None
        clock = snapshot.time_model_state.clocks.get(rate.clock_address)
        next_tick = self._next_participant_tick(snapshot, rate.clock_address)
        if clock is None or clock.state != "running" or next_tick is None:
            return None, None
        current_tick = clock.coordinate.tick
        if next_tick <= current_tick:
            return (0.0, rate.clock_address, 0), None
        key = (rate.clock_address, clock.coordinate.segment, current_tick, next_tick)
        deadline = self._deadlines.setdefault(
            key,
            now + float(rate.seconds_per_tick * (next_tick - current_tick)),
        )
        return (max(0.0, deadline - now), rate.clock_address, next_tick - current_tick), key

    @staticmethod
    def _next_participant_tick(snapshot: RuntimeSnapshot, clock_address: str) -> int | None:
        next_ticks = [
            int(payload["next_tick"])
            for payload in snapshot.participant_autonomous_execution_states.values()
            if (
                payload.get("clock_address") == clock_address
                and payload.get("lifecycle_state") == "running"
                and int(payload.get("in_flight", 0)) == 0
            )
        ]
        return min(next_ticks) if next_ticks else None


__all__ = ["ParticipantClockDriver"]
