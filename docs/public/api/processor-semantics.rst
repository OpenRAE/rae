Processor semantics
===================

The ``raes_processor.semantics`` subpackage owns checks over compiled resources and runtime snapshots.
Planner helpers build dependency graphs, order resources and compare desired resources with retained state.
They return the values or findings shown in each signature.
They do not apply the resulting changes to a backend.

SDL-language rules remain in :doc:`sdl-semantics`.
The public planning boundary and its diagnostic behavior are in :doc:`processor`.

.. currentmodule:: raes_processor.semantics

Planner semantics
-----------------

.. automodule:: raes_processor.semantics.planner
   :members:
