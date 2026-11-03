Runtime Layer
=============

The ``raes_runtime`` package owns live runtime control: runtime targets,
backend registry integration, manager lifecycle execution, control-plane
submission and observation, operation persistence, security, and backend
result-contract validation helpers.

Runtime APIs consume neutral DTOs from ``raes_contracts`` at backend and
control-plane boundaries. Header-based control-plane identity is disabled by
default and requires an explicit ``ControlPlaneSecurityConfig`` with
``trust_proxy_identity_headers=True``.

.. currentmodule:: raes_runtime

Public API
----------

.. automodule:: raes_runtime
   :members:
   :undoc-members:

Runtime Manager
---------------

.. automodule:: raes_runtime.manager
   :members:

Backend Registry
----------------

.. automodule:: raes_runtime.registry
   :members:

Control Plane
-------------

.. automodule:: raes_runtime.control_plane
   :members:

Control Plane API
-----------------

.. automodule:: raes_runtime.control_plane_api
   :members:

Control Plane Store
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

Control Plane Security
----------------------

.. automodule:: raes_runtime.control_plane_security
   :members:

Result Contracts
----------------

.. automodule:: raes_runtime.result_contracts
   :members:
