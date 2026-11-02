SDL Semantics
=============

The ``raes.semantics`` subpackage holds SDL-language semantic rules, such as
objective-window analysis. The SDL validator, the processor at compile time, and
the processor runtime use them.

Per ADR-015 these helpers live with the SDL package because ``raes``
defines the language; they depend only on the standard library and have no
import-time coupling to ``raes_processor``.

The workflow step-type contract, branch closure, and the pure workflow
step-result validator are shared by every layer. ADR-121 places them in
``raes_contracts.workflow.semantics``.

.. currentmodule:: raes.semantics

Objective Semantics
-------------------

.. automodule:: raes.semantics.objectives
   :members:

Workflow Semantics
------------------

.. automodule:: raes_contracts.workflow.semantics
   :members:
