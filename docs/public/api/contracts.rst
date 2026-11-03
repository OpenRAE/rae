Shared contracts
================

The ``raes_contracts`` package owns shared data types and enums. The processor,
runtime, backend protocols, conformance tools, and authoring tools use them.
They define the typed boundary for runtime calls to backends. Keep them out of
runtime and processor modules.

Diagnostics
-----------

.. automodule:: raes_contracts.diagnostics
   :members:

Artifact transformation reports
-------------------------------

.. automodule:: raes_contracts.contracts.artifact_transformations
   :members:

Planning
--------

.. automodule:: raes_contracts.planning
   :members:

Runtime state
-------------

.. automodule:: raes_contracts.runtime_state
   :members:

Workflow results
----------------

.. automodule:: raes_contracts.workflow
   :members:

Evaluation results
------------------

.. automodule:: raes_contracts.evaluation
   :members:

Participant episodes
--------------------

.. automodule:: raes_contracts.participant_episode
   :members:

Participant implementation manifests
------------------------------------

``ParticipantImplementationManifestModel`` and
``ParticipantImplementationProvenanceModel`` live in
``raes_contracts.contracts`` with the other published contract models. The
manifest names the implementation and its supported behavior, limits, and
tool needs. The provenance record states which implementation, manifest,
configuration, contract versions, and decision-surface policy a run used.

Mixed-backend execution and readback
------------------------------------

Optional bindings and stage reports for one admitted mixed edge or native
handoff, exchanged through the backend operation protocol below. They grant no
authority, and the shared runtime does not read them.

.. automodule:: raes_contracts.contracts.mixed_backend_binding
   :members:

.. automodule:: raes_contracts.contracts.mixed_backend_stages
   :members:

.. automodule:: raes_contracts.contracts.mixed_backend_validation
   :members:

.. automodule:: raes_contracts.contracts.mixed_backend_transcript
   :members:

.. automodule:: raes_backend_protocols.mixed_backend
   :members:

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

External inject triggers, occurrences and readback
--------------------------------------------------

Draft ADR-112 carriers for an external inject request, its claimed occurrence,
per-binding readback and participant correlation. They grant no trigger
authority and do not execute an inject.

.. automodule:: raes_contracts.contracts.inject_occurrence
   :members:

.. automodule:: raes_contracts.contracts.inject_occurrence_outcome
   :members:
