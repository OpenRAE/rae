Shared Contracts
================

The ``raes_contracts`` package owns neutral DTOs and enums shared across
processor, runtime, backend protocols, conformance, and authoring surfaces.
These contracts are the typed boundary for backend-facing runtime calls; they
must not live in runtime or processor implementation modules.

Diagnostics
-----------

.. automodule:: raes_contracts.diagnostics
   :members:

Artifact Transformation Reports
-------------------------------

.. automodule:: raes_contracts.contracts.artifact_transformations
   :members:

Planning
--------

.. automodule:: raes_contracts.planning
   :members:

Runtime State
-------------

.. automodule:: raes_contracts.runtime_state
   :members:

Workflow Results
----------------

.. automodule:: raes_contracts.workflow
   :members:

Evaluation Results
------------------

.. automodule:: raes_contracts.evaluation
   :members:

Participant Episodes
--------------------

.. automodule:: raes_contracts.participant_episode
   :members:

Participant Implementation Manifests
------------------------------------

``ParticipantImplementationManifestModel`` and
``ParticipantImplementationProvenanceModel`` live in
``raes_contracts.contracts`` with the other published contract models. The
manifest declares participant implementation identity, capabilities,
compatibility, decision-surface modes, tool-affordance expectations, and
constraints. The provenance record preserves the participant implementation,
selected manifest, selected configuration reference, participant contract
versions, and decision-surface exposure policy used in a run.

Backend operation supervision
-----------------------------

The optional backend protocol reports evidence for one admitted invocation.
The shared runtime retains authorization, scenario execution and terminal state.

.. automodule:: raes_contracts.contracts.backend_operation
   :members:

.. automodule:: raes_contracts.contracts.backend_operation_response
   :members:

.. automodule:: raes_contracts.contracts.backend_operation_validation
   :members:

.. automodule:: raes_backend_protocols.operation_supervision
   :members:
