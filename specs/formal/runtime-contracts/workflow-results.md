# Workflow result contract

## Envelope

Each workflow result is a plain-data portable envelope with:

- `state_schema_version`
- `workflow_status`
- `run_id`
- `started_at`
- `updated_at`
- optional `terminal_reason`
- `compensation_status`
- optional `compensation_started_at`
- optional `compensation_updated_at`
- `compensation_failures`
- `steps`

`state_schema_version` is fixed to `workflow-step-state/v1` in this rollout.

## Step state

Each observable step result contains:

- `lifecycle`: `pending | running | completed`
- `outcome`: optional until completion, then required
- `attempts`: non-negative integer

## Semantic constraints

- only observable step kinds may appear in `steps`
- all observable steps from the compiled workflow contract must appear in `steps`
- workflow-level status must be explicit and portable
- terminal workflow statuses require a `terminal_reason`
- non-terminal workflow states may not report compensation activity
- compensation activity is explicit and portable; it does not overwrite the primary `terminal_reason`
- non-completed steps may not report an outcome
- pending steps must report `0` attempts
- completed steps must report an outcome legal for their step kind
- fixed-attempt step kinds must report their fixed attempt count when completed

## History

Workflow observation is split into:

- the current execution-state envelope
- a separate ordered workflow history stream

History events are validated against the compiled workflow `execution_contract`
so the manager can reject impossible global causality as well as illegal step-local states.

When workflow compensation is configured, the history stream may also include:

- `compensation_registered`
- `compensation_started`
- `compensation_workflow_started`
- `compensation_workflow_completed`
- `compensation_workflow_failed`
- `compensation_completed`
- `compensation_failed`

## Validation boundary

The runtime produces the portable workflow result and history envelopes.
It validates them against the compiled workflow `result_contract` and
`execution_contract` before commit.
The admitted compiled `control_steps` determine executable transitions.
Backend step responses cannot replace the graph or workflow history.


Runtime-owned history correlates each invocation with `invocation_id`.
A dispatch event is `step_started`, with `origin: runtime`.
Its accepted response is `step_reported`, with `origin: backend`.
Both events carry `dispatch_id` and a positive `attempt`.

Control steps appear in history without becoming observable step results.
The latest workflow-address result identifies its invocation through `run_id`.
History validation uses that invocation's events and checks the ordered stream's timestamps.
Legacy streams without invocation correlation remain readable.


Python typed models normalize these payloads.
Published JSON Schemas remain the wire-shape authority.
