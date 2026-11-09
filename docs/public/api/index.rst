.. _use-the-python-api:

Python API and command reference
================================

Find accepted inputs, defaults, results, errors and effects by interface.
For a procedure, use the :doc:`Python guide <../guides/python>` or
:doc:`command guide <../guides/cli>`.

Version and support boundary
----------------------------

This reference describes the Python source used for this documentation build.
The build reads the installed distribution version from package metadata.
That version alone does not establish that a checkout matches a published release.
The source comparison for this rewrite uses commit
``315e5d50ea55c7a209b22aac972cd5ba2bdbca77``.

The ``raes`` distribution requires Python ``>=3.14,<3.15``.
Its installed entry points are ``raes`` and ``raes-mcp``.
The reference retains the current Python interfaces during the Go migration.
Planned Go exports are not Python replacements or released support claims.

SDL parsing, compilation, execution and backend realization are different boundaries.
Parsing does not deploy a scenario.
Planning does not prove that a backend can execute it.
Contract models describe data; they do not grant execution or read authority.
Concrete backend implementations and credentials belong to their external backend distributions.

Reference map
-------------

* :doc:`sdl`: parsing, validation, instantiation, source transformations and SDL models.
* :doc:`sdl-semantics`: pure language checks.
* :doc:`processor`: compilation, planning, analysis and processor model types.
* :doc:`processor-semantics`: dependencies and reconciliation checks.
* :doc:`contracts`: shared data models, enums and backend protocol declarations.
* :doc:`runtime`: live execution, stores, profiles and protected readback.
* :doc:`cli`: the complete registered command tree and process exit meanings.
* :doc:`http`: HTTP routes, authority, status codes and model selection.
* :doc:`mcp`: the MCP console entry point and registered tools.

Signatures and model fields
---------------------------

Generated entries read their signatures and defaults from Python source.
An argument without a default is required.
``None`` and an empty collection have different meanings; use the displayed default.
Pydantic models validate constructor input and raise ``pydantic.ValidationError`` on invalid fields.
Their signatures show aliases, field types and defaults.
Cross-field rules remain in the owning contract and validator.

Some schema model types have no independent narrative docstring.
Their generated fields remain included rather than hidden.
Separate narrative descriptions are omitted where they would duplicate the
`published schema contracts <https://github.com/OpenRAE/rae/tree/315e5d50ea55c7a209b22aac972cd5ba2bdbca77/contracts/schemas>`_.
The schema owns exact constraints; an enum lists its accepted literal values.
Do not treat an inherited framework description as a claim about model support.

Only explicit facade exports and the documented public submodule interfaces are selected.
Underscore-prefixed helpers, dependency imports and unregistered Python callbacks are not additional public commands.
Re-export aliases refer to the same Python object; they do not define another wire contract.

.. toctree::
   :maxdepth: 2

   sdl
   sdl-semantics
   processor
   processor-semantics
   contracts
   runtime
   cli
   http
   mcp
