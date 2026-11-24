SDL semantics
=============

The ``raes.semantics`` subpackage owns pure language checks.
The SDL validator, compiler and runtime reuse these rules.
They do not acquire modules, provision a backend or authorize execution.

Objective checks inspect declared windows and their relations.
Workflow checks inspect step types, branches and result contracts.
Generated signatures give required inputs and returned findings.
A finding describes the checked boundary only; it is not a live execution result.
All layers share the workflow step types, branch closure and step-result checks in ``raes_contracts.workflow.semantics`` (ADR-121).
Processor reconciliation helpers are in :doc:`processor-semantics`.

.. currentmodule:: raes.semantics

Objective semantics
-------------------

.. automodule:: raes.semantics.objectives
   :members:

Workflow semantics
------------------

.. automodule:: raes_contracts.workflow.semantics
   :members:
