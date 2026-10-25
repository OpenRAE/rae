"""Deterministic delivery workflow; RAE's state authority owns every outcome."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .operation_temporal import EngineOperationReference
    from .operation_transcript_policy import automatic_poll_interval_ms


# Keep SDK JSON decoding separate from strict EngineOperationReference validation.
@workflow.defn(name="raes.operation")
class RaeOperationWorkflow:
    def __init__(self) -> None:
        self._reference = None

    @workflow.query(name="operation_reference")
    def operation_reference(self) -> dict[str, Any] | None:
        return self._reference

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> str:
        reference = EngineOperationReference.model_validate(payload)
        self._reference = reference.model_dump(mode="json")
        single_attempt = RetryPolicy(maximum_attempts=1)
        deadline = workflow.now() + timedelta(milliseconds=reference.execution_budget_ms)
        try:
            state = await workflow.execute_activity(
                "raes.invoke",
                self._reference,
                task_queue=reference.effect_queue,
                start_to_close_timeout=timedelta(milliseconds=reference.execution_budget_ms),
                schedule_to_close_timeout=timedelta(milliseconds=reference.execution_budget_ms),
                retry_policy=single_attempt,
            )
            while state in {"accepted", "running"} and workflow.now() < deadline:
                state = await workflow.execute_activity(
                    "raes.observe",
                    self._reference,
                    task_queue=reference.control_queue,
                    start_to_close_timeout=timedelta(milliseconds=reference.control_budget_ms),
                    schedule_to_close_timeout=timedelta(milliseconds=reference.control_budget_ms),
                    retry_policy=single_attempt,
                )
                if state in {"accepted", "running"}:
                    remaining = (deadline - workflow.now()).total_seconds()
                    if remaining > 0:
                        await workflow.sleep(
                            min(remaining, automatic_poll_interval_ms(reference.execution_budget_ms) / 1000)
                        )
            if state not in {"accepted", "running"}:
                return state
        except Exception:
            workflow.logger.warning("RAE operation delivery or observation could not be established")
        return await workflow.execute_activity(
            "raes.indeterminate",
            self._reference,
            task_queue=reference.control_queue,
            start_to_close_timeout=timedelta(milliseconds=reference.control_budget_ms),
            schedule_to_close_timeout=timedelta(milliseconds=reference.control_budget_ms),
            retry_policy=single_attempt,
        )


@workflow.defn(name="raes.supervision")
class RaeSupervisionWorkflow:
    """Controls remain deliverable after an effect workflow reaches a terminal cut."""

    def __init__(self) -> None:
        self._payload = None

    @workflow.query(name="control_reference")
    def control_reference(self) -> dict[str, Any] | None:
        return self._payload

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> str:
        reference = EngineOperationReference.model_validate(payload["reference"])
        self._payload = payload
        return await workflow.execute_activity(
            "raes.control",
            payload,
            task_queue=reference.control_queue,
            start_to_close_timeout=timedelta(milliseconds=reference.control_budget_ms),
            schedule_to_close_timeout=timedelta(milliseconds=reference.control_budget_ms),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
