Runtime layer
=============

The ``raes_runtime`` package owns live execution and protected readback in the current Python package.
It uses neutral data models from ``raes_contracts`` at backend and control-plane boundaries.
An admitted backend implements the capabilities it declares; a protocol or stub does not prove a live deployment.

Inputs, results and effects
---------------------------

``RuntimeManager`` applies admitted plans through a configured runtime target.
``RuntimeControlPlane`` submits work, keeps receipts and exposes operation state and snapshots.
An accepted receipt is not proof that an operation completed successfully.
The operation status and retained evidence describe its later outcome.
Mutations can call backend services and change retained state.
Reads remain subject to caller, target, run and participant authority.

The default run is fixed for legacy calls on a control-plane instance.
Opening or selecting another run does not change that default.
Store instances and their exclusive leases have explicit lifetimes.
Callers close the owning runtime or control plane when finished.
Use :doc:`control-plane tasks <../guides/control-plane>` for composition procedures.

The generated signatures give typed options and defaults.
Shared runtime failures use the ``RaesError`` categories; constructor shape errors can raise ``ValueError`` or ``TypeError``.
These Python exceptions differ from :doc:`HTTP status responses <http>` and :doc:`command exit codes <cli>`.

Profiles and compatibility
--------------------------

P0 is the embedded ephemeral profile.
P1 is the durable single-process core profile.
P2 adds the authenticated single-worker HTTP adapter over an explicitly selected P1 core.
P3 remains unavailable; declaring the enum value does not implement a distributed service.
Profile declarations give capabilities and nonclaims.
Backend support, store capabilities and profile admission are separate checks.

The default HTTP security configuration has no built-in principals or bearer tokens.
Proxy identity-header trust is disabled.
Enabling it requires an authenticated proxy that removes caller-supplied identity headers before setting its own.
Single-worker and store-maintenance limits remain applicable.

.. currentmodule:: raes_runtime

Public API
----------

.. automodule:: raes_runtime
   :members:
   :undoc-members:

Runtime configuration and profiles
----------------------------------

.. automodule:: raes_runtime.control_plane_configuration
   :members: ControlPlaneConfiguration, ControlPlaneOptions
   :undoc-members:

The exported ``ControlPlaneProfile`` and ``ControlPlaneProfileDeclaration`` entries above describe the selected profile and its claims.
``profile_declaration`` returns the immutable declaration for a profile.

Experiment records
------------------

The exported ``ExperimentRunMetadata``, ``ExperimentRecordBundle`` and archive protocols above describe retained experiment records.
Archive publication does not authorize execution.

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

Control plane security
----------------------

.. automodule:: raes_runtime.control_plane_security
   :members:

Offline store maintenance
-------------------------

.. automodule:: raes_runtime.control_plane_store_maintenance
   :members:

Result contracts
----------------

.. automodule:: raes_runtime.result_contracts
   :members:
