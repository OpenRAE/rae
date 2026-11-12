Runtime layer
=============

The ``raes_runtime`` package owns live runtime control. It manages targets,
backends, and their lifecycle. It also handles control-plane requests, stores
operations, applies access checks, and checks backend results.

Runtime APIs use shared data types from ``raes_contracts`` for backend and
control-plane calls. The control plane ignores identity headers by default.
To trust them, set ``trust_proxy_identity_headers=True`` in an explicit
``ControlPlaneSecurityConfig``.

.. currentmodule:: raes_runtime

Public API
----------

.. automodule:: raes_runtime
   :members:
   :undoc-members:

Runtime manager
---------------

.. automodule:: raes_runtime.manager
   :members:

Backend registry
----------------

.. automodule:: raes_runtime.registry
   :members:

Control plane
-------------

.. automodule:: raes_runtime.control_plane
   :members:

Control plane API
-----------------

.. automodule:: raes_runtime.control_plane_api
   :members:

Control plane store
-------------------

.. automodule:: raes_runtime.control_plane_store
   :members:

Assigned trials
---------------

The :doc:`../guides/assigned-trials` guide describes coordinator admission,
selected host execution, cancellation, and checked outcome ingestion.

.. automodule:: raes_runtime.runtime_assigned_trial
   :members: AssignedTrial

.. automodule:: raes_contracts.assigned_trial
   :members: TrialAssignmentModel, TrialAssignmentControlModel, TrialOutcomeModel

.. autoclass:: raes_runtime.runtime_trial_services.TrialOutcomeVerifier
   :members:

Control plane security
----------------------

.. automodule:: raes_runtime.control_plane_security
   :members:

Result contracts
----------------

.. automodule:: raes_runtime.result_contracts
   :members:
