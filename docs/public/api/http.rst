Control-plane routes
====================

``create_control_plane_app`` builds the reference Python HTTP adapter over a runtime control plane.
It returns a FastAPI application; it does not start a server.
The installed distribution supplies the API-description version.
See :doc:`runtime` for Python constructors and :doc:`control-plane tasks <../guides/control-plane>` for composition.

Authority and defaults
----------------------

P2 is an administrative, single-worker HTTP profile over an explicitly selected P1 core.
Participant-limited credentials do not satisfy its transport admission.
Core participant, audience, operation-actor and controller rules still apply after transport admission.
The default security configuration has no built-in credentials and does not trust proxy identity headers.
Each accepted identity needs the target binding and roles that the route requires.

Read authority admits backend, operator and auditor roles.
Mutation authority admits backend and operator roles.
Operator resolution requires the operator role.
Health probes are public and return no runtime payloads.
The application rejects later changes to its sealed routes, middleware, handlers or dependency overrides.

Requests use JSON unless an entry says otherwise.
Path identifiers are required and select the exact retained operation, participant, episode or control.
``Idempotency-Key`` defaults to an empty string on routes that pass it to the core.
It does not override scope, request commitments or authorization checks.
Reads that return ``X-RAES-Snapshot-Revision`` bind their result to the reported snapshot revision.
All responses use ``Cache-Control: no-store``.

The default request-body limit is 1,000,000 bytes.
The default pending-mutation bound is 32; the pending-rejection-audit bound is 8.
Route-specific limits can be tighter.
For example, participant control intents use at most 262,144 bytes and JSON depth 16.
Bounded offload and runtime budgets can refuse or time out a call.

Status codes
------------

.. list-table::
   :header-rows: 1
   :widths: 15 85

   * - Status
     - Meaning
   * - ``200``
     - A result or receipt was returned. Receipt acceptance is not successful completion.
   * - ``204``
     - Admission was stopped; the response has no body.
   * - ``400``
     - A request framing or route-specific input condition was refused.
   * - ``401`` / ``403``
     - Identity was not admitted, or the authenticated caller lacks authority.
   * - ``404``
     - The selected record is absent or unavailable to the caller.
   * - ``409``
     - The request conflicts with admitted state, scope, commitment or revision.
   * - ``413``
     - The body exceeds the admitted size bound.
   * - ``422``
     - Request validation failed. The response does not echo rejected values.
   * - ``500``
     - An unexpected failure or changed application composition was refused.
   * - ``503``
     - Capacity, readiness, a call deadline or an underlying service is unavailable.

Capacity refusal can include ``Retry-After: 1``.
Unexpected errors return a fixed detail rather than the exception text.
Some supervision reads mask authorization refusals as ``404``.
These middleware and authority failures apply even when a route's OpenAPI response list omits them.

Operations and snapshots
------------------------

The following POST routes require mutation authority unless marked as operator resolution.
GET routes require read authority.
Model names refer to the :doc:`shared contract reference <contracts>`.

.. list-table::
   :header-rows: 1
   :widths: 40 30 30

   * - Method and path
     - JSON body
     - Result
   * - ``POST /operations/provisioning``
     - ``ProvisioningPlanModel``
     - ``OperationReceiptModel``
   * - ``POST /operations/orchestration``
     - ``OrchestrationPlanModel``
     - ``OperationReceiptModel``
   * - ``POST /operations/evaluation``
     - ``EvaluationPlanModel``
     - ``OperationReceiptModel``
   * - ``POST /operations/{operation_id}/resolution``
     - Required ``disposition``; operator resolution.
     - ``OperationReceiptModel``
   * - ``GET /operations/{operation_id}``
     - None.
     - ``OperationStatusModel``
   * - ``GET /snapshot``
     - None.
     - ``RuntimeSnapshotEnvelopeModel``
   * - ``GET /apparatus/operational-summary``
     - None.
     - Operational apparatus summary object.

Plan submission can change stores and call an admitted backend.
A nonempty phase plan needs the authority produced by its planner.
Operator resolution accepts ``accept-current-snapshot`` for an indeterminate operation.
The result must still satisfy the core's reconciliation rules.

Injects and retained artifacts
------------------------------

Trigger and delivery routes require mutation authority.
The GET routes require read authority and select a retained operation.
Accepted trigger or delivery input does not prove that an inject took effect.

.. list-table::
   :header-rows: 1
   :widths: 40 30 30

   * - Method and path
     - JSON body
     - Result
   * - ``POST /injects/trigger``
     - ``InjectTriggerRequestModel``
     - ``OperationReceiptModel``
   * - ``POST /injects/deliver``
     - ``ParticipantInjectApplicationModel``
     - ``ParticipantInjectDeliveryReceiptModel``
   * - ``GET /operations/{operation_id}/inject-occurrence``
     - None.
     - ``InjectOccurrenceModel``
   * - ``GET /operations/{operation_id}/inject-outcome``
     - None.
     - ``InjectOccurrenceOutcomeModel``
   * - ``GET /operations/{operation_id}/inject-correlation``
     - None.
     - ``InjectOccurrenceCorrelationModel``
   * - ``GET /operations/{operation_id}/inject-result``
     - None.
     - ``AssociatedArtifactManifestModel``
   * - ``GET /operations/{operation_id}/inject-delivery``
     - None.
     - ``ParticipantInjectContentModel``
   * - ``GET /operations/{operation_id}/inject-capture``
     - None.
     - Capture-result record.
   * - ``GET /operations/{operation_id}/inject-artifacts/{artifact_id}``
     - None.
     - Authorized artifact bytes with their media type.

Workflow and participant control
--------------------------------

POST routes require mutation authority.
GET routes require read authority.
Mutations return ``OperationReceiptModel`` and can change retained state or dispatch admitted work.

.. list-table::
   :header-rows: 1
   :widths: 50 50

   * - Method and path
     - Request or response
   * - ``POST /workflows/{workflow_address}/cancel``
     - Optional ``WorkflowCancellationRequestModel`` body.
   * - ``POST /workflows/reconcile-timeouts``
     - No body; reconciles expired workflow steps.
   * - ``POST /participants/{participant_address}/episodes/initialize``
     - Optional body with ``episode_id=None``.
   * - ``POST /participants/{participant_address}/episodes/reset``
     - Optional ``episode_id=None`` and ``reason="reset by operator"``.
   * - ``POST /participants/{participant_address}/episodes/restart``
     - Optional ``episode_id=None`` and ``reason="restarted by operator"``.
   * - ``POST /participants/{participant_address}/episodes/terminate``
     - Optional ``terminal_reason="interrupted"`` and ``detail="terminated by operator"``.
   * - ``POST /participants/{participant_address}/control-occurrences``
     - Required discriminated participant control intent; ``kind`` selects its shape.
   * - ``POST /participant-executions/{execution_scope_ref}/control``
     - Required ``action`` and nonnegative ``expected_generation``; optional positive ``timeout_seconds=None``.
   * - ``GET /participant-executions/{execution_scope_ref}``
     - Returns ``ParticipantExecutionServiceStateModel``.
   * - ``GET /participants/{participant_address}/status``
     - Returns ``ParticipantStatusViewModel``.
   * - ``GET /participants/{participant_address}/episodes/{episode_id}/history``
     - Returns ``ParticipantHistoryViewModel``.
   * - ``GET /participants/{participant_address}/context``
     - Returns ``ParticipantContextViewModel``.

Execution control actions are ``start``, ``pause``, ``resume``, ``drain``, ``reset`` and ``teardown``.
Participant control intents select proposal, approval, denial, external direction, intervention, handoff, override or cancellation.
Private Python body-class names in OpenAPI are transport implementation details, not supported Python import paths.

The context read requires the ``view_ref`` query string.
Its optional query strings are ``episode_id``, ``derivation_basis_ref`` and ``payload_ref``; each defaults to ``None``.
They select the governed view and its bound context rather than grant read authority.

Supervision and worker transport
--------------------------------

These routes supervise admitted operations rather than grant arbitrary backend invocation.
Read routes require read authority.
Control and resolution routes require operator resolution authority.
Worker publication and claim routes require mutation authority.
Core bindings, digests and one-use grants still apply.

.. list-table::
   :header-rows: 1
   :widths: 45 30 25

   * - Method and path
     - Body or authority
     - Result
   * - ``GET /operations/{operation_id}/participant-cancellation``
     - Read authority.
     - Cancellation status.
   * - ``POST /operations/{operation_id}/participant-cancellation/dispatch``
     - Operator resolution; no body.
     - Cancellation status.
   * - ``POST /execution/stop``
     - Operator resolution; no body.
     - Empty ``204`` response.
   * - ``POST /operations/{operation_id}/controls``
     - Operator resolution; ``BackendOperationControlModel``.
     - Admitted control model.
   * - ``GET /operations/{operation_id}/controls/{control_id}``
     - Read authority.
     - ``BackendOperationResponseModel`` or ``null``.
   * - ``POST /operations/{operation_id}/absence-resolution``
     - Operator resolution; required ``control_id``.
     - ``OperationReceiptModel``.
   * - ``GET /operations/{operation_id}/invocation``
     - Read authority.
     - ``BackendOperationRequestModel``.
   * - ``POST /operations/{operation_id}/invocation/grant``
     - Required ``binding``, ``capabilities`` and ``admission`` models.
     - Invocation grant.
   * - ``POST /operations/{operation_id}/invocation/observations``
     - ``BackendOperationControlModel``.
     - Control delivery grant.
   * - ``POST /operations/{operation_id}/invocation/controls/{control_id}``
     - No body.
     - Control delivery grant.
   * - ``POST /operations/{operation_id}/invocation/responses``
     - ``BackendOperationResponseModel``.
     - ``OperationStatusModel``.
   * - ``POST /operations/{operation_id}/invocation/indeterminate``
     - ``BackendOperationBindingModel``.
     - ``OperationStatusModel``.

``POST /runtime/progress`` is reserved for the internal worker transport.
It accepts ``RuntimeSequenceReference`` and returns a string after an admitted progress call.
It requires mutation authority and exact worker ownership.
Its registration does not make it a general integration API.

Health and schema description
-----------------------------

``GET /health/live`` returns a value-free liveness object.
``GET /health/ready`` returns readiness with status ``200`` or ``503``.
Neither requires a caller credential.

The framework serves ``/openapi.json``, ``/docs``, ``/redoc`` and ``/docs/oauth2-redirect`` as API-description routes.
They expose no runtime state and are exempt from the runtime route-authority inventory.
The native OpenAPI document gives exact request properties, required fields, bounds, defaults and response schemas for the composed app.
It does not attest backend capability or include every middleware refusal.
Do not change the sealed application to add documentation routes.
