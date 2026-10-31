CLI Reference
=============

The ``raes`` command-line interface is built with `Typer <https://pypi.org/project/typer/>`_
and lives in the canonical ``raes_cli`` package.

.. currentmodule:: raes_cli

Main CLI
--------

.. automodule:: raes_cli.main
   :members:

Semantic Commands
-----------------

``raes semantic`` is the offline, read-only human and automation surface.
Every command accepts a file path or ``-`` for stdin, requires an explicit
versioned contract selection (defaulting to ``sdl-yaml/v1`` for SDL), and
derives human and deterministic JSON presentation from one typed result.

.. automodule:: raes_cli.semantic
   :members:

SDL Commands
------------

The ``raes sdl`` group contains source-format and legacy module-registry
compatibility commands. Module acquisition, lock generation, and publication
are not part of the stable semantic command contract.

.. automodule:: raes_cli.sdl
   :members:

Processor Commands
------------------

.. automodule:: raes_cli.processor
   :members:

Conformance Commands
--------------------

.. automodule:: raes_cli.conformance
   :members:

Runtime Commands
----------------

``raes runtime store`` checks, backs up, and restores an offline local
control-plane store.

.. automodule:: raes_cli.runtime
   :members:
   :ignore-module-all:
