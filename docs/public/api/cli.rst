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

Libvirt Commands
----------------

``raes libvirt`` holds the operational commands of the native libvirt backend.
``raes libvirt techvault validate-live`` and ``raes libvirt techvault
guest-certify`` create libvirt/QEMU resources and ask for confirmation unless
you pass ``--yes``. ``raes libvirt evidence validate`` writes the
evaluator-evidence archive for a scenario. It runs deterministically unless you
pass ``--native-live``, which needs a libvirt daemon.

.. automodule:: raes_cli.libvirt
   :members:

Corpus Commands
---------------

``raes corpus build`` builds the cross-backend evidence corpus for a reference
scenario and writes it to the ``--output`` file.

.. automodule:: raes_cli.corpus
   :members:

Runtime Commands
----------------

``raes runtime store`` checks, backs up, and restores an offline local
control-plane store.

.. automodule:: raes_cli.runtime
   :members:
   :ignore-module-all:
