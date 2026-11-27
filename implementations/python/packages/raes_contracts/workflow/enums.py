"""Portable workflow execution enumerations."""

from __future__ import annotations

from enum import Enum


class WorkflowStepLifecycle(str, Enum):
    """Portable execution lifecycle for workflow-visible step state."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"


class WorkflowStepOutcome(str, Enum):
    """Portable execution outcomes for workflow-visible step state."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXHAUSTED = "exhausted"


class WorkflowStatus(str, Enum):
    """Portable workflow-level execution status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class WorkflowCompensationStatus(str, Enum):
    """Portable workflow compensation status."""

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WorkflowHistoryEventType(str, Enum):
    """Portable workflow history event kinds."""

    WORKFLOW_STARTED = "workflow_started"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_REPORTED = "step_reported"
    SWITCH_CASE_SELECTED = "switch_case_selected"
    CALL_STARTED = "call_started"
    CALL_COMPLETED = "call_completed"
    BRANCH_ENTERED = "branch_entered"
    BRANCH_CONVERGED = "branch_converged"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_CANCELLED = "workflow_cancelled"
    WORKFLOW_TIMED_OUT = "workflow_timed_out"
    COMPENSATION_REGISTERED = "compensation_registered"
    COMPENSATION_STARTED = "compensation_started"
    COMPENSATION_WORKFLOW_STARTED = "compensation_workflow_started"
    COMPENSATION_WORKFLOW_COMPLETED = "compensation_workflow_completed"
    COMPENSATION_WORKFLOW_FAILED = "compensation_workflow_failed"
    COMPENSATION_COMPLETED = "compensation_completed"
    COMPENSATION_FAILED = "compensation_failed"
