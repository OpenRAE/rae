Processor layer
===============

The ``raes_processor`` package compiles SDL, including instantiated scenarios.
It plans state changes, checks backend support and manifests, and owns the
compiled runtime models. Live runtime control belongs to ``raes_runtime``.
Shared runtime and backend data types belong to ``raes_contracts`` (ADR-036).

.. currentmodule:: raes_processor

Public API
----------

.. automodule:: raes_processor
   :members:
   :undoc-members:

Compiler
--------

.. automodule:: raes_processor.compiler
   :members:

Processor models
----------------

The ``raes_processor.models`` package owns the runtime data models. Its
``__init__`` exports the public types and functions. The sections below show
them from the modules that define them.

.. automodule:: raes_processor.models.resources
   :members:

.. automodule:: raes_processor.models.behavior_resources
   :members:

.. automodule:: raes_processor.models.action_results
   :members:

.. automodule:: raes_processor.models.attribution
   :members:

.. automodule:: raes_processor.models.outcome
   :members:

.. automodule:: raes_processor.models.outcome_interpretation_validation
   :members:

.. automodule:: raes_processor.models.temporal
   :members:

.. automodule:: raes_processor.models.history_event
   :members:

.. automodule:: raes_processor.models.behavior_history_violations
   :members:

.. automodule:: raes_processor.models.runtime_model
   :members:

Manifest authority
------------------

.. automodule:: raes_processor.manifest
   :members:

Planner
-------

.. automodule:: raes_processor.planner
   :members:

Capabilities
------------

.. automodule:: raes_processor.capabilities
   :members:

Exploit-path analysis
---------------------

.. automodule:: raes_processor.exploit_path
   :members:
