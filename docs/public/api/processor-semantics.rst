Processor Semantics
===================

The ``raes_processor.semantics`` subpackage holds processor-runtime
reconciliation helpers — dependency-graph construction over compiled
resources, topological ordering, and resource-action reconciliation between
compiled resources and runtime snapshots.

Per ADR-015, the SDL-language semantic helpers, such as objective windows,
live under ``raes.semantics``. The workflow step-type contract, branch closure,
and the workflow step-result validator live in
``raes_contracts.workflow.semantics`` (ADR-121). :doc:`sdl-semantics` documents
both.

.. currentmodule:: raes_processor.semantics

Planner Semantics
-----------------

.. automodule:: raes_processor.semantics.planner
   :members:
