SDL semantics
=============

The ``raes.semantics`` package holds SDL rules, such as objective-window checks.
The SDL validator uses these rules. The processor uses them when it compiles
and runs a scenario.

These helpers live in the SDL package because ``raes`` defines the language
(ADR-015). They use only the standard library and do not import
``raes_processor``.

All layers share workflow step types, branch closure, and step-result checks.
These rules live in ``raes_contracts.workflow.semantics`` (ADR-121).

.. currentmodule:: raes.semantics

Objective semantics
-------------------

.. automodule:: raes.semantics.objectives
   :members:

Workflow semantics
------------------

.. automodule:: raes_contracts.workflow.semantics
   :members:
