Processor semantics
===================

The ``raes_processor.semantics`` package helps compare compiled resources with
runtime snapshots. It builds dependency graphs, orders resources, and finds
the resource actions needed to bring runtime state in line with the plan.

SDL rules, such as objective windows, live in ``raes.semantics`` (ADR-015).
Shared workflow step types, branch closure, and step-result checks live in
``raes_contracts.workflow.semantics`` (ADR-121). See :doc:`sdl-semantics` for
both sets of rules.

.. currentmodule:: raes_processor.semantics

Planner semantics
-----------------

.. automodule:: raes_processor.semantics.planner
   :members:
